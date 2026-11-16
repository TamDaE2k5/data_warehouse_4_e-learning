"""Regenerate the English field reference from live PostgreSQL/Gold schemas."""

import json
from contextlib import closing
from etl.common import ROOT, ch_connect, source_connect, staging_connect, project_lock

DESCRIPTIONS = json.loads((ROOT / "docs/field_descriptions.json").read_text(encoding="utf-8"))


def description(column):
    return DESCRIPTIONS.get(column, "Derived from the table DDL; see the source-to-target mapping.")


def main():
    lines = [
        "# Data dictionary",
        "",
        "Physical types are read from running schemas. Timestamps use UTC and money uses integer VND.",
        "Gold event timestamps have second precision. The quality gate verifies Gold foreign keys.",
        "See [architecture](architecture.md) for grain and history, and [mapping](mapping.md) for formulas.",
        "Regenerate with `docker compose run --rm runner python -m docs.generate_dictionary`.",
        "",
    ]
    with project_lock(shared=True):
        for connector, schemas, label in [
            (source_connect, ("oltp",), "learning_oltp"),
            (staging_connect, ("silver", "staging", "quarantine"), "dwh_staging"),
        ]:
            with closing(connector()) as connection, connection.cursor() as cursor:
                cursor.execute(
                    """SELECT table_schema,table_name,column_name,data_type,is_nullable
                    FROM information_schema.columns WHERE table_schema=ANY(%s)
                    ORDER BY table_schema,table_name,ordinal_position""",
                    (list(schemas),),
                )
                previous = None
                for schema, table, column, kind, nullable in cursor.fetchall():
                    if (schema, table) != previous:
                        lines += [
                            f"## PostgreSQL {label}.{schema}.{table}",
                            "",
                            "| Column | Type | Nullable | Meaning |",
                            "|---|---|---|---|",
                        ]
                        previous = schema, table
                    lines.append(f"| {column} | {kind} | {nullable} | {description(column)} |")
        with closing(ch_connect()) as client:
            for (table,) in client.query("SHOW TABLES FROM gold").result_rows:
                lines += [
                    "",
                    f"## ClickHouse gold.{table}",
                    "",
                    "| Column | Type | Meaning |",
                    "|---|---|---|",
                ]
                for column, kind, *_ in client.query(f"DESCRIBE TABLE gold.{table}").result_rows:
                    lines.append(f"| {column} | {kind} | {description(column)} |")
    (ROOT / "docs/data_dictionary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
