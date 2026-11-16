"""Recover publication using table UUIDs even after the process disappears."""

from etl.common import ROOT
from etl.watermark import incomplete_publications, record_run

FEEDS = ("feed_monthly_revenue", "feed_course_completion")


def table_uuids(ch):
    rows = ch.query(
        "SELECT database,name,toString(uuid) FROM system.tables WHERE database IN ('gold','gold_build')"
    ).result_rows
    return {(database, name): identifier for database, name, identifier in rows}


def drop_feeds(ch):
    for name in FEEDS:
        ch.command(f"DROP VIEW IF EXISTS gold.{name}")


def create_feeds(ch):
    for sql in (ROOT / "dw/ddl/aggregate_feeds.sql").read_text(encoding="utf-8").split(";"):
        if sql.strip():
            ch.command(sql.strip())


def publication_plan(ch, tables):
    identifiers = table_uuids(ch)
    return [
        dict(table=name, old=identifiers.get(("gold", name)), new=identifiers[("gold_build", name)])
        for name in sorted(tables)
    ]


def publish(ch, plan):
    ch.command("CREATE DATABASE IF NOT EXISTS gold")
    drop_feeds(ch)
    for entry in plan:
        name = entry["table"]
        if entry["old"]:
            ch.command(f"EXCHANGE TABLES gold.{name} AND gold_build.{name}")
        else:
            ch.command(f"RENAME TABLE gold_build.{name} TO gold.{name}")
    create_feeds(ch)


def recover(ch):
    recovered = []
    for manifest, plan in incomplete_publications():
        ch.command("CREATE DATABASE IF NOT EXISTS gold")
        drop_feeds(ch)
        identifiers = table_uuids(ch)
        for entry in reversed(plan):
            name, old, new = entry["table"], entry["old"], entry["new"]
            live = identifiers.get(("gold", name))
            build = identifiers.get(("gold_build", name))
            if live == new and build == old:
                if old:
                    ch.command(f"EXCHANGE TABLES gold.{name} AND gold_build.{name}")
                else:
                    ch.command(f"RENAME TABLE gold.{name} TO gold_build.{name}")
            elif live == old and build == new:
                continue
            else:
                raise RuntimeError(
                    f"Cannot recover {name}: unexpected table UUIDs. Preserve gold_build and inspect pipeline_runs."
                )
        if all(entry["old"] for entry in plan):
            create_feeds(ch)
        manifest.update(
            status="recovered", recovery="Previous Gold restored; source checkpoint unchanged"
        )
        record_run(manifest, "recovered")
        recovered.append(manifest["run_id"])
    return recovered
