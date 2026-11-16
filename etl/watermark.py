"""Durable run state and checkpoint, committed only with a published Gold."""

from contextlib import closing
from psycopg2.extras import Json, execute_values
from etl.config import staging_connect


def published():
    with closing(staging_connect()) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT manifest FROM staging.published_state WHERE singleton=true")
        row = cursor.fetchone()
        return row[0] if row else None


def record_run(manifest, phase, publication=None):
    with closing(staging_connect()) as connection, connection, connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO staging.pipeline_runs(run_id,phase,manifest,publication)
            VALUES (%s,%s,%s,%s) ON CONFLICT(run_id) DO UPDATE SET
            phase=EXCLUDED.phase,manifest=EXCLUDED.manifest,
            publication=coalesce(EXCLUDED.publication,pipeline_runs.publication),
            finished_at=CASE WHEN EXCLUDED.phase IN ('completed','failed','recovered') THEN now() END""",
            (
                manifest["run_id"],
                phase,
                Json(manifest),
                Json(publication) if publication is not None else None,
            ),
        )


def incomplete_publications():
    with closing(staging_connect()) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT manifest,publication FROM staging.pipeline_runs WHERE phase='publishing' ORDER BY started_at"
        )
        return cursor.fetchall()


def commit_publication(manifest, staged):
    with closing(staging_connect()) as connection, connection, connection.cursor() as cursor:
        if staged["marks"]:
            execute_values(
                cursor,
                """INSERT INTO staging.etl_watermarks
                (table_name,last_processed_time,last_processed_id,last_run_id) VALUES %s
                ON CONFLICT(table_name) DO UPDATE SET last_processed_time=EXCLUDED.last_processed_time,
                last_processed_id=EXCLUDED.last_processed_id,last_run_id=EXCLUDED.last_run_id""",
                [(table, stamp, key, manifest["run_id"]) for table, stamp, key in staged["marks"]],
            )
        cursor.execute(
            """INSERT INTO staging.published_state(singleton,manifest,safe_xid)
            VALUES(true,%s,%s) ON CONFLICT(singleton) DO UPDATE SET
            manifest=EXCLUDED.manifest,safe_xid=EXCLUDED.safe_xid,published_at=now()""",
            (Json(manifest), staged["safe_xid"]),
        )
        cursor.execute("DELETE FROM staging.pending_changes")
        cursor.execute("UPDATE staging.stage_state SET needs_full=false WHERE singleton=true")
        cursor.execute(
            "UPDATE staging.pipeline_runs SET phase='completed',manifest=%s,finished_at=now() WHERE run_id=%s",
            (Json(manifest), manifest["run_id"]),
        )
