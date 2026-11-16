import io
import json
import os
import tempfile
from contextlib import closing
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from etl.config import (
    ch_connect as ch_connect,
    pg_connect as pg_connect,
    source_connect as source_connect,
    staging_connect,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = Path(os.getenv("DW_ARTIFACTS_DIR", str(ROOT / "artifacts")))


def save_json(name, data):
    path = ARTIFACTS / name
    path.parent.mkdir(parents=True, exist_ok=True)
    # Each writer gets a private temporary file before atomic replacement.
    fd, temp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(data, output, indent=2, ensure_ascii=False, default=str)
            output.flush()
            # Container-written evidence must remain readable by the host runner.
            if os.name == "posix":
                os.fchmod(output.fileno(), 0o644)
            os.fsync(output.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def copy_frame(conn, table, frame):
    buf = io.StringIO()
    frame.to_csv(buf, index=False, header=False, na_rep="\\N", date_format="%Y-%m-%d %H:%M:%S.%f")
    buf.seek(0)
    with conn.cursor() as cur:
        cols = ",".join('"' + c + '"' for c in frame.columns)
        cur.copy_expert(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT CSV, NULL '\\N')", buf)


@contextmanager
def project_lock(shared=False):
    with closing(staging_connect()) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            function = "pg_try_advisory_lock_shared" if shared else "pg_try_advisory_lock"
            cur.execute(f"SELECT {function}(202210132024)")
            if not cur.fetchone()[0]:
                raise RuntimeError("Another project command is running; retry after it finishes")
        yield


def require_success():
    # PostgreSQL is authoritative. A leftover JSON export must never make a
    # fresh database appear ready after its volumes have been replaced.
    with closing(staging_connect()) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT manifest FROM staging.published_state WHERE singleton=true")
        row = cursor.fetchone()
        cursor.execute("SELECT 1 FROM staging.pipeline_runs WHERE phase='publishing' LIMIT 1")
        if cursor.fetchone():
            raise RuntimeError(
                "Warehouse publication requires recovery. Run the pipeline and retry."
            )
        if row:
            if row[0].get("status") != "success":
                raise RuntimeError(
                    "Published warehouse state is not successful; rerun the pipeline"
                )
            return row[0]
    raise RuntimeError("No published warehouse exists in PostgreSQL. Run a full pipeline first.")
