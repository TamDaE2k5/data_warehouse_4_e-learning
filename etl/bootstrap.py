"""Provision database boundaries with the administrator, outside the ETL."""

import os
from contextlib import closing
import psycopg2
from etl.common import ROOT

TABLES = (
    "users",
    "user_history",
    "instructors",
    "courses",
    "lessons",
    "quizzes",
    "payment_methods",
    "enrollments",
    "payments",
    "lesson_completions",
    "quiz_attempts",
)


def setup():
    with closing(psycopg2.connect(dbname="postgres")) as admin:
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute("SELECT datname FROM pg_database")
            names = {row[0] for row in cur}
            if "learning_oltp" not in names:
                cur.execute(
                    "ALTER DATABASE learning RENAME TO learning_oltp"
                    if "learning" in names
                    else "CREATE DATABASE learning_oltp"
                )
            if "dwh_staging" not in names:
                cur.execute("CREATE DATABASE dwh_staging")
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname='learning_reader'")
            if not cur.fetchone():
                cur.execute("CREATE ROLE learning_reader LOGIN")
            cur.execute(
                "ALTER ROLE learning_reader PASSWORD %s", (os.environ["PG_READER_PASSWORD"],)
            )
            cur.execute("ALTER ROLE learning_reader SET default_transaction_read_only=on")
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname='learning_stage'")
            if not cur.fetchone():
                cur.execute("CREATE ROLE learning_stage LOGIN")
            cur.execute("ALTER ROLE learning_stage PASSWORD %s", (os.environ["PG_STAGE_PASSWORD"],))
            cur.execute("REVOKE CONNECT ON DATABASE learning_oltp FROM PUBLIC")
            cur.execute("GRANT CONNECT ON DATABASE learning_oltp TO learning_reader")
            cur.execute("GRANT CONNECT,CREATE,TEMPORARY ON DATABASE dwh_staging TO learning_stage")
    with (
        closing(psycopg2.connect(dbname="learning_oltp")) as source,
        source,
        source.cursor() as cur,
    ):
        cur.execute((ROOT / "oltp/schema.sql").read_text(encoding="utf-8"))
        cur.execute((ROOT / "oltp/change_journal.sql").read_text(encoding="utf-8"))
        for table in TABLES:
            cur.execute(f"""ALTER TABLE oltp.{table} ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
                ALTER TABLE oltp.{table} ADD COLUMN IF NOT EXISTS dw_revision BIGINT NOT NULL DEFAULT 0;
                CREATE INDEX IF NOT EXISTS {table}_updated_idx ON oltp.{table}(updated_at);
                CREATE OR REPLACE TRIGGER set_updated_at BEFORE INSERT OR UPDATE ON oltp.{table}
                FOR EACH ROW EXECUTE FUNCTION oltp.touch_row()""")
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema='oltp' AND table_name=%s ORDER BY ordinal_position LIMIT 1",
                (table,),
            )
            key = cur.fetchone()[0]
            cur.execute(f"""CREATE OR REPLACE TRIGGER record_dw_change AFTER INSERT OR UPDATE OR DELETE ON oltp.{table}
                FOR EACH ROW EXECUTE FUNCTION oltp.record_change('{key}')""")
        cur.execute(
            "GRANT CONNECT ON DATABASE learning_oltp TO learning_reader; GRANT USAGE ON SCHEMA oltp TO learning_reader; GRANT SELECT ON ALL TABLES IN SCHEMA oltp TO learning_reader"
        )
    with closing(psycopg2.connect(dbname="dwh_staging")) as stage, stage, stage.cursor() as cur:
        cur.execute((ROOT / "dw/ddl/staging_schema.sql").read_text(encoding="utf-8"))
        cur.execute((ROOT / "dw/ddl/control_schema.sql").read_text(encoding="utf-8"))

        cur.execute("GRANT USAGE ON SCHEMA silver,staging,quarantine TO learning_stage")
        cur.execute("GRANT ALL ON ALL TABLES IN SCHEMA silver,staging,quarantine TO learning_stage")
        cur.execute("CREATE SCHEMA IF NOT EXISTS benchmark AUTHORIZATION learning_stage")
        cur.execute("ALTER SCHEMA benchmark OWNER TO learning_stage")
