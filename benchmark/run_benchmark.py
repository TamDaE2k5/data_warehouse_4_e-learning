import csv
import hashlib
import io
import json
import platform
import statistics
import time
import uuid
import pandas as pd
from benchmark.queries import QUERIES
from etl.integrity import fingerprints
from benchmark.evidence import (
    canonical,
    row_bytes,
    summarize,
    configured_resources,
    publish_bundle,
)
from etl.common import (
    ARTIFACTS,
    ch_connect,
    staging_connect,
    copy_frame,
    require_success,
    save_json,
    utc_now,
)


def digest(rows):
    return hashlib.sha256("\n".join(canonical(rows)).encode()).hexdigest()


def verify_publication(ch, manifest):
    """Do not attach an old pipeline identity to manually modified serving data."""
    if fingerprints(ch) != manifest.get("fingerprints"):
        raise RuntimeError(
            "Gold differs from the published snapshot; rerun the pipeline before benchmarking"
        )


def mirror(ch, pg, tables):
    with pg.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS benchmark")
    counts = {}
    ddl = []
    for table in tables:
        columns = ch.query(f"DESCRIBE TABLE gold.{table}").result_rows
        definitions = []
        for c, t, *_ in columns:
            sql_type = (
                "TIMESTAMP"
                if "DateTime" in t
                else "DATE"
                if t == "Date"
                else "TEXT"
                if "String" in t
                else "BIGINT"
            )
            definitions.append(
                f'"{c}" {sql_type}' + ("" if t.startswith("Nullable") else " NOT NULL")
            )
        key = columns[0][0]
        create = f"CREATE TABLE benchmark.{table} ({','.join(definitions)}, PRIMARY KEY ({key}))"
        with pg.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS benchmark.{table}")
            cur.execute(create)
        ddl.append(create + ";")
        n = 0
        with ch.query_row_block_stream(
            f"SELECT * FROM gold.{table}", settings={"max_block_size": 50000}
        ) as stream:
            for rows in stream:
                copy_frame(
                    pg, "benchmark." + table, pd.DataFrame(rows, columns=[r[0] for r in columns])
                )
                n += len(rows)
        if table.startswith("fact_"):
            with pg.cursor() as cur:
                for col in ("date_sk", "enrolled_date_sk", "course_sk", "user_sk"):
                    if col in [r[0] for r in columns]:
                        cur.execute(f"CREATE INDEX ON benchmark.{table} ({col})")
        counts[table] = n
        print(f"Benchmark mirror {table}: {n:,}", flush=True)
    pg.commit()
    with pg.cursor() as cur:
        for table in tables:
            cur.execute(f"ANALYZE benchmark.{table}")
    pg.commit()
    schema_path = ARTIFACTS / "benchmark/postgres_schema.sql"
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text("\n".join(ddl) + "\n", encoding="utf-8")
    return counts


def benchmark(runs=5, reuse_mirror=False, warmups=2):
    if isinstance(runs, bool) or not isinstance(runs, int) or runs < 3:
        raise ValueError("At least 3 measured runs are required")
    if isinstance(warmups, bool) or not isinstance(warmups, int) or warmups < 0:
        raise ValueError("Warm-up count must be a nonnegative integer")
    resources = configured_resources()
    manifest = require_success()
    benchmark_id = uuid.uuid4().hex
    save_json(
        "benchmark/metadata.json",
        dict(
            status="running",
            benchmark_run=benchmark_id,
            pipeline_run=manifest["run_id"],
            started_at=utc_now(),
        ),
    )
    ch = pg = None
    try:
        ch, pg = ch_connect(), staging_connect()
        verify_publication(ch, manifest)
        tables = sorted(manifest["fingerprints"])
        begin = time.perf_counter()
        if reuse_mirror:
            with pg.cursor() as cur:
                counts = {}
                for table in tables:
                    cur.execute(f"SELECT count(*) FROM benchmark.{table}")
                    counts[table] = cur.fetchone()[0]
        else:
            counts = mirror(ch, pg, tables)
        mirror_seconds = round(time.perf_counter() - begin, 3)
        for t, n in counts.items():
            if n != manifest["fingerprints"][t][0]:
                raise AssertionError("Mirror count mismatch: " + t)
        # Full row SHA256 comparison, sorted by primary key, before any timing.
        equality = {}
        for table in tables:
            key = ch.query(f"DESCRIBE TABLE gold.{table}").first_row[0]
            ch_hash, pg_hash = hashlib.sha256(), hashlib.sha256()
            with ch.query_row_block_stream(
                f"SELECT * FROM gold.{table} ORDER BY {key}", settings={"max_block_size": 50000}
            ) as stream:
                for rows in stream:
                    # Each block is already ordered; preserve order across blocks.
                    for row in rows:
                        ch_hash.update(row_bytes(row))
            with pg.cursor(name="hash_" + table) as cur:
                cur.itersize = 50000
                cur.execute(f"SELECT * FROM benchmark.{table} ORDER BY {key}")
                while rows := cur.fetchmany(50000):
                    for row in rows:
                        pg_hash.update(row_bytes(row))
            # CH datetime may carry UTC tzinfo while PG is UTC-naive; normalized below if needed.
            equality[table] = dict(clickhouse=ch_hash.hexdigest(), postgres=pg_hash.hexdigest())
            if ch_hash.digest() != pg_hash.digest():
                raise AssertionError("Full row mirror hash mismatch: " + table)
            print("Full-row hash equal: " + table, flush=True)
        pg.commit()
        query_dir = ARTIFACTS / "benchmark/sql"
        query_dir.mkdir(parents=True, exist_ok=True)
        raw, summary, parity, executed_sql = [], [], {}, {}

        def execute(engine, sql):
            start = time.perf_counter_ns()
            if engine == "clickhouse":
                rows = ch.query(
                    sql, settings={"group_by_use_nulls": 1, "use_query_cache": 0}
                ).result_rows
            else:
                with pg.cursor() as cur:
                    cur.execute(sql)
                    rows = cur.fetchall()
            return (time.perf_counter_ns() - start) / 1e6, rows

        for name, template in QUERIES.items():
            queries = {
                "postgres": template.format(db="benchmark"),
                "clickhouse": template.format(db="gold"),
            }
            for engine, sql in queries.items():
                (query_dir / f"{name}.{engine}.sql").write_text(sql + ";\n", encoding="utf-8")
                executed_sql[f"sql/{name}.{engine}.sql"] = (sql + ";\n").encode()
            baseline = {}
            for engine in queries:
                # Establish parity even when the caller explicitly requests zero warm-ups.
                _, rows = execute(engine, queries[engine])
                for _ in range(warmups):
                    _, rows = execute(engine, queries[engine])
                baseline[engine] = canonical(rows)
            if baseline["postgres"] != baseline["clickhouse"]:
                save_json("benchmark/mismatch.json", dict(query=name, results=baseline))
                raise AssertionError("Query result mismatch: " + name)
            parity[name] = dict(
                equal=True,
                rows=len(baseline["postgres"]),
                sha256=hashlib.sha256("\n".join(baseline["postgres"]).encode()).hexdigest(),
            )
            times = {"postgres": [], "clickhouse": []}
            for run in range(runs):
                order = ["postgres", "clickhouse"] if run % 2 == 0 else ["clickhouse", "postgres"]
                for engine in order:
                    elapsed, rows = execute(engine, queries[engine])
                    if canonical(rows) != baseline[engine]:
                        raise AssertionError("Unstable results during timing: " + name)
                    times[engine].append(elapsed)
                    raw.append(
                        dict(
                            query=name,
                            engine=engine,
                            run=run + 1,
                            milliseconds=elapsed,
                            rows=len(rows),
                        )
                    )
            pg_ms, ch_ms = (
                statistics.median(times["postgres"]),
                statistics.median(times["clickhouse"]),
            )
            summary.append(summarize(name, times, parity[name]["rows"]))
            print(
                f"{name}: PG {pg_ms:.2f} ms / CH {ch_ms:.2f} ms = {pg_ms / ch_ms:.2f}x (equal)",
                flush=True,
            )
        pg.commit()
        with pg.cursor() as cur:
            cur.execute("SELECT version()")
            pg_version = cur.fetchone()[0]
            cur.execute(
                "SELECT name,setting,unit FROM pg_settings WHERE name IN ('work_mem','shared_buffers','max_parallel_workers_per_gather')"
            )
            pg_settings = cur.fetchall()
            pg_sizes = {}
            for table in tables:
                cur.execute("SELECT pg_total_relation_size(%s)", ("benchmark." + table,))
                pg_sizes[table] = int(cur.fetchone()[0])
            pg_bytes = sum(pg_sizes.values())
        parts = ch.query(
            "SELECT table,sum(bytes_on_disk),sum(data_uncompressed_bytes) "
            "FROM system.parts WHERE database='gold' AND active GROUP BY table"
        ).result_rows
        ch_sizes = {
            name: dict(bytes_on_disk=int(disk), uncompressed_column_bytes=int(raw))
            for name, disk, raw in parts
        }
        storage = (
            sum(ch_sizes.get(name, {}).get("bytes_on_disk", 0) for name in tables),
            sum(ch_sizes.get(name, {}).get("uncompressed_column_bytes", 0) for name in tables),
        )
        metadata = dict(
            status="success",
            benchmark_run=benchmark_id,
            measured_at=utc_now(),
            pipeline_run=manifest["run_id"],
            warmup_runs=warmups,
            measured_runs=runs,
            timing="client wall-clock execute+fetch, serial; CH query cache disabled",
            cache_scope="One untimed parity query plus configured warm-ups; caches are not flushed",
            postgres_version=pg_version,
            clickhouse_version=ch.query("SELECT version()").first_row[0],
            python_version=platform.python_version(),
            postgres_settings=pg_settings,
            resources=resources,
            limitations=[
                "Single Docker host; no cold-cache control",
                "Equal CPU quotas do not isolate engine CPU scheduling on a shared host",
                "Network/client latency included",
                "CPU, query peak memory and IO are not measured",
                "Synthetic data; cannot generalize to production",
            ],
            mirror_counts=counts,
            mirror_seconds=mirror_seconds,
            mirror_reused=reuse_mirror,
            mirror_hashes=equality,
            query_parity=parity,
            storage=dict(
                postgres_gold_with_indexes_bytes=pg_bytes,
                clickhouse_gold_bytes_on_disk=storage[0],
                clickhouse_gold_uncompressed_column_bytes=storage[1],
                scope="Exactly the mirrored Gold tables; PostgreSQL includes indexes; ClickHouse active parts include metadata",
                compared_tables=tables,
                postgres_tables=pg_sizes,
                clickhouse_tables={name: ch_sizes.get(name, {}) for name in tables},
                clickhouse_auxiliary_tables={
                    name: size for name, size in ch_sizes.items() if name not in tables
                },
            ),
        )
        if not resources["equal_engine_memory_limits"]:
            metadata["limitations"].append(
                "Memory budgets differ; not an equal-memory engine isolation test"
            )
        files = dict(executed_sql)
        schema_path = ARTIFACTS / "benchmark/postgres_schema.sql"
        if not reuse_mirror and schema_path.exists():
            files["postgres_schema.sql"] = schema_path.read_bytes()
        files["summary.json"] = json.dumps(summary, indent=2).encode()
        for filename, records in [("runs.csv", raw), ("summary.csv", summary)]:
            output = io.StringIO(newline="")
            writer = csv.DictWriter(output, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
            files[filename] = output.getvalue().encode()
        lines = [
            "# Benchmark — measured results",
            "",
            f"Pipeline: `{manifest['run_id']}`. Benchmark: `{benchmark_id}`.",
            f"One parity query, {warmups} warm-ups and {runs} measured runs per engine/query.",
            "",
            "Same Gold rows and columns; full row hashes and all query outputs matched. Timings include client execute + fetch.",
            "",
            "| Query | PostgreSQL median ms | ClickHouse median ms | PG / CH |",
            "|---|---:|---:|---:|",
        ]
        lines += [
            f"| {r['query']} | {r['postgres_median_ms']} | {r['clickhouse_median_ms']} | {r['speedup_pg_over_ch']}x |"
            for r in summary
        ]
        lines += ["", "## Limitations", ""] + ["- " + v for v in metadata["limitations"]]
        files["results.md"] = ("\n".join(lines) + "\n").encode()
        files["metadata.json"] = json.dumps(metadata, indent=2, default=str).encode()
        receipt = publish_bundle(ARTIFACTS / "benchmark", benchmark_id, files)
        metadata["publication"] = receipt["directory"]
        return metadata
    except Exception as exc:
        save_json(
            "benchmark/metadata.json",
            dict(
                status="failed",
                benchmark_run=benchmark_id,
                pipeline_run=manifest["run_id"],
                error=str(exc),
                finished_at=utc_now(),
            ),
        )
        raise
    finally:
        if ch is not None:
            ch.close()
        if pg is not None:
            pg.close()
