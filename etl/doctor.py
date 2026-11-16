"""Read-only health and permission checks."""

from contextlib import closing
from etl.common import source_connect, staging_connect, ch_connect, project_lock, utc_now
from etl.watermark import published


def doctor():
    result = dict(checked_at=utc_now(), checks={})
    with project_lock(shared=True):
        with closing(source_connect()) as source, source.cursor() as cursor:
            cursor.execute(
                "SELECT current_user,current_database(),current_setting('transaction_read_only')"
            )
            result["checks"]["source"] = cursor.fetchone()
            cursor.execute("SELECT has_table_privilege(current_user,'oltp.users','INSERT')")
            assert cursor.fetchone()[0] is False, "Source reader must not have INSERT"
        with closing(staging_connect()) as stage, stage.cursor() as cursor:
            cursor.execute(
                "SELECT current_user,current_database(),has_database_privilege(current_user,'learning_oltp','CONNECT')"
            )
            role, database, can_connect = cursor.fetchone()
            assert not can_connect, "Staging role must not connect to OLTP"
            result["checks"]["staging"] = [role, database, "isolated from OLTP"]
            cursor.execute("SELECT phase,count(*) FROM staging.pipeline_runs GROUP BY phase")
            result["runs"] = dict(cursor.fetchall())
            cursor.execute(
                "SELECT count(*) FROM quarantine.quarantine_records WHERE resolved_at IS NULL"
            )
            result["open_quarantine"] = cursor.fetchone()[0]
        with closing(ch_connect()) as client:
            result["checks"]["clickhouse"] = client.query("SELECT version()").first_row[0]
        result["published"] = published()
    result["status"] = "success"
    return result
