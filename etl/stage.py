"""Snapshot-consistent extraction with a transactional source change journal."""

import io
import json
from contextlib import closing
from psycopg2.extras import execute_values
from etl.bootstrap import TABLES
from etl.common import source_connect, staging_connect
from etl.schema_guard import normalize

REFERENCES = {
    "user_history": [("user_id", "users", "user_id")],
    "courses": [("instructor_id", "instructors", "instructor_id")],
    "lessons": [("course_id", "courses", "course_id")],
    "quizzes": [("course_id", "courses", "course_id")],
    "enrollments": [("user_id", "users", "user_id"), ("course_id", "courses", "course_id")],
    "payments": [
        ("course_id", "courses", "course_id"),
        ("user_id", "users", "user_id"),
        ("enrollment_id", "enrollments", "enrollment_id"),
        ("method_id", "payment_methods", "method_id"),
    ],
    "lesson_completions": [
        ("course_id", "courses", "course_id"),
        ("user_id", "users", "user_id"),
        ("enrollment_id", "enrollments", "enrollment_id"),
        ("lesson_id", "lessons", "lesson_id"),
    ],
    "quiz_attempts": [
        ("course_id", "courses", "course_id"),
        ("user_id", "users", "user_id"),
        ("enrollment_id", "enrollments", "enrollment_id"),
        ("quiz_id", "quizzes", "quiz_id"),
    ],
}


def csv_field(value):
    return "\\N" if value is None else '"' + str(value).replace('"', '""') + '"'


def reject_orphans(writer, table, key):
    rejected = {}
    for column, parent, parent_key in REFERENCES.get(table, ()):
        code = "ERR_ORPHAN_COURSE" if column == "course_id" else "ERR_ORPHAN_REFERENCE"
        writer.execute(f"""DELETE FROM batch_{table} b WHERE NOT EXISTS
            (SELECT 1 FROM silver.{parent} p WHERE p.{parent_key}=b.{column}) RETURNING b.{key}""")
        rejected.update(
            (source_id, (code, f"Missing reference: {parent}.{parent_key}"))
            for (source_id,) in writer.fetchall()
        )
    return rejected


def contract(writer, catalog, table):
    writer.execute(
        """SELECT column_name,data_type FROM information_schema.columns
        WHERE table_schema='silver' AND table_name=%s ORDER BY ordinal_position""",
        (table,),
    )
    columns, types = map(list, zip(*writer.fetchall()))
    catalog.execute(
        """SELECT column_name,data_type FROM information_schema.columns
        WHERE table_schema='oltp' AND table_name=%s""",
        (table,),
    )
    actual = dict(catalog.fetchall())
    if (
        not set(columns) <= actual.keys()
        or actual.get(columns[0]) != "bigint"
        or actual.get("updated_at") != "timestamp with time zone"
        or actual.get("dw_revision") != "bigint"
    ):
        raise RuntimeError(f"Schema contract failed for oltp.{table}; run setup first")
    return columns, types


def source_batches(source, table, columns, mode, lower, upper):
    with source.cursor(name=f"extract_{table}") as cursor:
        if mode == "full":
            cursor.execute(
                f"SELECT {','.join(columns)},dw_revision FROM oltp.{table} ORDER BY {columns[0]}"
            )
        else:
            cursor.execute(
                """SELECT DISTINCT ON(source_id) raw_payload,revision,operation
                FROM oltp.change_journal WHERE table_name=%s AND source_xid >= %s AND source_xid < %s
                ORDER BY source_id,revision DESC""",
                (table, lower, upper),
            )
        while rows := cursor.fetchmany(50000):
            yield (
                [(dict(zip(columns, row[:-1])), row[-1], "SNAPSHOT") for row in rows]
                if mode == "full"
                else rows
            )


def process_batch(writer, table, columns, types, rows, full):
    key = columns[0]
    ids = [int(raw[key]) for raw, _, _ in rows]
    known = {}
    if not full:
        writer.execute(
            "SELECT source_id,revision FROM staging.source_versions WHERE table_name=%s AND source_id=ANY(%s)",
            (table, ids),
        )
        known = dict(writer.fetchall())
    versions, operations, errors = [], {}, []
    clean_buffer = io.StringIO()
    raw_by_id = {}
    for payload, revision, operation in rows:
        source_id = int(payload[key])
        if source_id in known and revision <= known[source_id]:
            continue
        # Revision zero is the implicit baseline after bulk seed / v2 migration.
        if revision:
            versions.append((table, source_id, revision))
        raw_by_id[source_id] = payload
        operations[source_id] = (revision, operation)
        if operation == "DELETE":
            continue
        values = [payload.get(column) for column in columns]
        clean, code, reason = normalize(columns, types, values)
        if code:
            errors.append(
                (
                    table,
                    source_id,
                    payload["updated_at"],
                    code,
                    reason,
                    json.dumps(payload, default=str),
                )
            )
            operations[source_id] = (revision, "REJECTED")
        else:
            clean_buffer.write(",".join(csv_field(value) for value in clean) + "\n")
    clean_buffer.seek(0)
    writer.copy_expert(f"COPY batch_{table} FROM STDIN WITH (FORMAT CSV,NULL '\\N')", clean_buffer)
    for source_id, (code, reason) in reject_orphans(writer, table, key).items():
        raw = raw_by_id[source_id]
        errors.append(
            (table, source_id, raw["updated_at"], code, reason, json.dumps(raw, default=str))
        )
        operations[source_id] = (operations[source_id][0], "REJECTED")
    if errors:
        execute_values(
            writer,
            """INSERT INTO quarantine.quarantine_records
            (table_name,source_id,source_updated_at,error_code,rejection_reason,raw_payload)
            VALUES %s ON CONFLICT DO NOTHING""",
            errors,
        )
    deleted = [source_id for source_id, (_, op) in operations.items() if op == "DELETE"]
    if deleted:
        writer.execute(f"DELETE FROM silver.{table} WHERE {key}=ANY(%s)", (deleted,))
        writer.execute(
            """UPDATE quarantine.quarantine_records SET resolved_at=now()
            WHERE table_name=%s AND source_id=ANY(%s) AND resolved_at IS NULL""",
            (table, deleted),
        )
    updates = ",".join(f"{column}=EXCLUDED.{column}" for column in columns[1:])
    writer.execute(f"""INSERT INTO silver.{table} SELECT * FROM batch_{table}
        ON CONFLICT ({key}) DO UPDATE SET {updates}""")
    writer.execute(
        f"""UPDATE quarantine.quarantine_records q SET resolved_at=now()
        FROM batch_{table} b WHERE q.table_name=%s AND q.source_id=b.{key}
        AND q.source_updated_at<=b.updated_at AND q.resolved_at IS NULL""",
        (table,),
    )
    writer.execute(f"TRUNCATE batch_{table}")
    if versions:
        # COPY avoids millions of bound INSERT statements on the initial load.
        buffer = io.StringIO("".join(",".join(map(csv_field, row)) + "\n" for row in versions))
        writer.copy_expert("COPY batch_versions FROM STDIN WITH (FORMAT CSV,NULL '\\N')", buffer)
        writer.execute("""INSERT INTO staging.source_versions SELECT * FROM batch_versions
            ON CONFLICT(table_name,source_id) DO UPDATE SET revision=EXCLUDED.revision""")
        writer.execute("TRUNCATE batch_versions")
    pending = [
        (table, source_id, op, revision)
        for source_id, (revision, op) in operations.items()
        if op != "REJECTED"
    ]
    if pending and not full:
        execute_values(
            writer,
            """INSERT INTO staging.pending_changes VALUES %s
            ON CONFLICT(table_name,source_id) DO UPDATE SET operation=EXCLUDED.operation,revision=EXCLUDED.revision""",
            pending,
        )
    return len(operations), len(errors)


def stage_source(mode):
    counts, marks, extracted, changed, rejected = {}, [], {}, {}, {}
    with closing(source_connect()) as source, closing(staging_connect()) as destination:
        source.set_session(readonly=True, isolation_level="REPEATABLE READ")
        with destination, destination.cursor() as writer, source.cursor() as catalog:
            writer.execute("SELECT safe_xid FROM staging.published_state WHERE singleton=true")
            row = writer.fetchone()
            lower = row[0] if row else None
            if mode == "incremental" and lower is None:
                raise RuntimeError("Run pipeline --mode full once to initialize journal tracking")
            # Every XID below xmin has finished, including transactions that began before this run.
            catalog.execute("SELECT pg_snapshot_xmin(pg_current_snapshot())::text::bigint")
            upper = catalog.fetchone()[0]
            if mode == "full":
                writer.execute("TRUNCATE staging.source_versions,staging.pending_changes")
                writer.execute(
                    "UPDATE staging.stage_state SET needs_full=true WHERE singleton=true"
                )
            writer.execute(
                "CREATE TEMP TABLE batch_versions (LIKE staging.source_versions) ON COMMIT DROP"
            )
            for table in TABLES:
                columns, types = contract(writer, catalog, table)
                if mode == "full":
                    writer.execute(f"TRUNCATE silver.{table}")
                writer.execute(
                    f"CREATE TEMP TABLE batch_{table} (LIKE silver.{table}) ON COMMIT DROP"
                )
                extracted[table] = changed[table] = rejected[table] = 0
                for batch in source_batches(source, table, columns, mode, lower, upper):
                    accepted, invalid = process_batch(
                        writer, table, columns, types, batch, mode == "full"
                    )
                    extracted[table] += len(batch)
                    changed[table] += accepted
                    rejected[table] += invalid
                writer.execute(f"SELECT count(*) FROM silver.{table}")
                counts[table] = writer.fetchone()[0]
                writer.execute(
                    f"SELECT updated_at,{columns[0]} FROM silver.{table} ORDER BY updated_at DESC,{columns[0]} DESC LIMIT 1"
                )
                if row := writer.fetchone():
                    marks.append((table, *row))
                print(
                    f"{table}: {extracted[table]:,} extracted / {counts[table]:,} clean", flush=True
                )
            if mode == "full":
                # A full snapshot may already see a DELETE above its safe XID.
                # Retain that tombstone so an older journal UPDATE cannot resurrect it.
                with source.cursor(name="snapshot_tombstones") as tombstones:
                    tombstones.execute("""SELECT table_name,source_id,revision FROM
                        (SELECT DISTINCT ON(table_name,source_id) table_name,source_id,revision,operation
                         FROM oltp.change_journal ORDER BY table_name,source_id,revision DESC) latest
                        WHERE operation='DELETE' """)
                    while rows := tombstones.fetchmany(50000):
                        execute_values(
                            writer,
                            """INSERT INTO staging.source_versions VALUES %s
                            ON CONFLICT(table_name,source_id) DO UPDATE SET revision=EXCLUDED.revision
                            WHERE source_versions.revision < EXCLUDED.revision""",
                            rows,
                            page_size=1000,
                        )
            writer.execute(
                "SELECT table_name,count(*) FROM staging.pending_changes GROUP BY table_name"
            )
            pending = dict(writer.fetchall())
            writer.execute(
                "SELECT DISTINCT table_name FROM staging.pending_changes WHERE operation='DELETE'"
            )
            deleted = [row[0] for row in writer.fetchall()]
            writer.execute("SELECT needs_full FROM staging.stage_state WHERE singleton=true")
            needs_full = writer.fetchone()[0]
    return dict(
        tables=counts,
        marks=marks,
        extracted=extracted,
        changed=changed,
        rejected=rejected,
        pending=pending,
        deleted=deleted,
        safe_xid=upper,
        needs_full=needs_full,
    )
