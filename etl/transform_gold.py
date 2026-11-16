"""Expose PostgreSQL Silver tables to ClickHouse for candidate builds."""

import os
from contextlib import closing, contextmanager
from etl.config import staging_connect
from etl.bootstrap import TABLES


@contextmanager
def silver_bridge(ch):
    ch.command("DROP DATABASE IF EXISTS stage_bridge SYNC")
    ch.command("CREATE DATABASE stage_bridge")
    try:
        for table in TABLES:
            ch.command(
                f"""CREATE TABLE stage_bridge.{table}
                ENGINE=PostgreSQL(%(host)s,'dwh_staging',%(table)s,%(user)s,%(password)s,'silver')""",
                parameters=dict(
                    host=os.environ["PGHOST"] + ":5432",
                    table=table,
                    user="learning_stage",
                    password=os.environ["PG_STAGE_PASSWORD"],
                ),
            )
        yield
    finally:
        ch.command("DROP DATABASE IF EXISTS stage_bridge SYNC")


# Pending journal revisions identify the Silver rows that actually changed.
def prepare_delta(ch, fact, key):
    target = f"stage_bridge.delta_{fact}"
    ch.command(f"CREATE TABLE {target} AS stage_bridge.{fact} ENGINE=MergeTree ORDER BY {key}")
    with closing(staging_connect()) as pg, pg.cursor(name=f"delta_{fact}") as cursor:
        cursor.execute(
            f"""SELECT s.* FROM silver.{fact} s JOIN staging.pending_changes p
            ON p.source_id=s.{key} AND p.table_name=%s WHERE p.operation != 'DELETE' """,
            (fact,),
        )
        while rows := cursor.fetchmany(50000):
            ch.insert(target, rows)
    return target


EVENT_FACTS = {
    "payments": "payment_id",
    "lesson_completions": "completion_id",
    "quiz_attempts": "attempt_id",
    "enrollments": "enrollment_id",
}


def load_gold_rows(ch, sql, mode, pending, deleted, reuse_safe):
    fact = next(
        (name for name in EVENT_FACTS if sql.startswith(f"INSERT INTO gold_build.fact_{name}\n")),
        None,
    )
    if (
        not fact
        or mode != "incremental"
        or not reuse_safe
        or any(pending.get(name, 0) for name in TABLES[1:7])
        or fact in deleted
    ):
        ch.command(sql)
        return "rebuilt"
    table = f"fact_{fact}"
    delta = None
    changed_partitions = []
    if pending.get(fact, 0):
        key = EVENT_FACTS[fact]
        delta = prepare_delta(ch, fact, key)
        if fact == "enrollments":
            must_rebuild = ch.query(f"""SELECT count() FROM gold.{table} g INNER JOIN {delta} s
                USING(enrollment_id) WHERE toYYYYMM(g.enrolled_at) != toYYYYMM(s.enrolled_at)""").first_row[
                0
            ]
            changed_partitions = ch.query(
                f"SELECT DISTINCT toYYYYMM(enrolled_at) FROM {delta}"
            ).result_rows
        else:
            must_rebuild = ch.query(f"""SELECT count() FROM {delta}
                WHERE {key} IN (SELECT {key} FROM gold.{table})""").first_row[0]
        if must_rebuild:
            ch.command(sql)
            return "rebuilt"
    partitions = ch.query(
        """SELECT DISTINCT partition_id FROM system.parts
        WHERE active AND database='gold' AND table=%(table)s""",
        parameters={"table": table},
    ).result_rows
    for (partition,) in partitions:
        if not partition.isdecimal():
            raise ValueError(f"Unexpected fact partition: {partition}")
        ch.command(
            f"ALTER TABLE gold_build.{table} ATTACH PARTITION ID '{partition}' FROM gold.{table}"
        )
    if delta:
        ch.command(sql.replace(f"FROM stage_bridge.{fact} ", f"FROM {delta} "))
        for (partition,) in changed_partitions:
            ch.command(f"OPTIMIZE TABLE gold_build.{table} PARTITION ID '{int(partition)}' FINAL")
        return "versioned" if fact == "enrollments" else "appended"
    return "reused"
