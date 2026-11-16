"""Export a complete report set, then atomically publish its manifest."""

import csv
import hashlib
import os
import re
import time
import uuid
from etl.common import ROOT, ARTIFACTS, require_success, ch_connect, save_json, utc_now


def reports():
    manifest = require_success()
    export_id = manifest["run_id"] + "-" + uuid.uuid4().hex[:8]
    parent = ARTIFACTS / "reports"
    temporary = parent / (".tmp-" + export_id)
    temporary.mkdir(parents=True)
    sql = (ROOT / "analytics/queries.sql").read_text(encoding="utf-8")
    parts = re.split(r"-- name: (\w+)\s*\n", sql)
    metadata = dict(
        status="running",
        pipeline_run=manifest["run_id"],
        generated_at=utc_now(),
        synthetic=True,
        export_dir="reports/" + export_id,
        reports={},
    )
    ch = ch_connect()
    try:
        for index in range(1, len(parts), 2):
            name, query = parts[index], parts[index + 1].strip().rstrip(";")
            tick = time.perf_counter()
            result = ch.query(query, settings={"group_by_use_nulls": 1})
            path = temporary / (name + ".csv")
            with path.open("w", newline="", encoding="utf-8-sig") as output:
                writer = csv.writer(output)
                writer.writerow(result.column_names)
                writer.writerows(result.result_rows)
            metadata["reports"][name] = dict(
                rows=len(result.result_rows),
                seconds=round(time.perf_counter() - tick, 4),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                source_sql="analytics/queries.sql",
                null_representation="empty CSV cell; subtotal dimensions are NULL for ROLLUP/CUBE",
            )
            print(f"{name}: {len(result.result_rows)} rows", flush=True)
        os.replace(temporary, parent / export_id)
        metadata["status"] = "success"
        save_json("reports/manifest.json", metadata)
        save_json("reports/" + export_id + "/manifest.json", metadata)
    finally:
        ch.close()
