"""Build, validate and publish Gold with durable crash recovery."""

import sys
import time
import uuid
from contextlib import closing
import psycopg2
from etl.load_clickhouse import publish, recover, publication_plan, table_uuids
from etl.watermark import published, record_run, commit_publication
from etl.common import ROOT, ch_connect, save_json, utc_now
from etl.stage import stage_source
from etl.transform_gold import load_gold_rows, silver_bridge
from etl.integrity import fingerprints


def peak_rss_mib():
    """Return the process high-water mark, or None when the OS does not expose it."""
    try:
        import resource
    except ImportError:
        return None
    maximum = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return round(maximum / divisor, 2)


def statements(path):
    return [sql.strip() for sql in path.read_text(encoding="utf-8").split(";") if sql.strip()]


def clean_frame(df):
    result = df.copy()
    for column in (
        "full_name",
        "email",
        "city",
        "country",
        "title",
        "category",
        "difficulty",
        "method_name",
        "expertise",
    ):
        if column in result:
            result[column] = result[column].str.strip()
    if "email" in result:
        result["email"] = result["email"].str.lower()
    if "country" in result:
        result["country"] = result["country"].str.upper()
    return result


def gold_intact(ch, previous):
    if not previous:
        return False
    identifiers = table_uuids(ch)
    for table, identifier in previous.get("gold_uuids", {}).items():
        if identifiers.get(("gold", table)) != identifier:
            return False
    if not previous.get("gold_uuids"):
        return False
    # UUIDs and row counts alone cannot detect an out-of-band UPDATE with the
    # same cardinality. Verify every column before reusing existing partitions.
    return fingerprints(ch) == previous.get("fingerprints")


def pipeline(mode="full"):
    from etl.validate import validate

    if mode not in ("full", "incremental"):
        raise ValueError("Pipeline mode must be full or incremental")
    started = time.perf_counter()
    manifest = dict(
        run_id=uuid.uuid4().hex, status="running", mode=mode, started_at=utc_now(), version=3
    )
    record_run(manifest, "extracting")
    save_json("pipeline.json", manifest)
    committed = False
    with closing(ch_connect()) as ch:
        try:
            manifest["recovered_runs"] = recover(ch)
            previous = published()
            for attempt in range(3):
                try:
                    staged = stage_source(mode)
                    break
                except (psycopg2.OperationalError, psycopg2.InterfaceError):
                    if attempt == 2:
                        raise
                    time.sleep(2**attempt)
            manifest.update(
                {
                    key: staged[key]
                    for key in (
                        "tables",
                        "extracted",
                        "changed",
                        "rejected",
                        "pending",
                        "deleted",
                        "safe_xid",
                    )
                }
            )
            # A full build cannot reuse existing partitions, so avoid an
            # unnecessary scan of the old warehouse in that path.
            intact = (
                mode == "incremental" and not staged["needs_full"] and gold_intact(ch, previous)
            )
            manifest["previous_gold_intact"] = intact
            if (
                mode == "incremental"
                and not staged["needs_full"]
                and not staged["pending"]
                and intact
            ):
                manifest.update(
                    fingerprints=previous["fingerprints"],
                    quality_checks=previous["quality_checks"],
                    quality_checked_at=previous["quality_checked_at"],
                    gold_uuids=previous["gold_uuids"],
                    gold_reused=True,
                    fact_actions={},
                )
            else:
                record_run(manifest, "building")
                ch.command("DROP DATABASE IF EXISTS gold_build SYNC")
                fact_actions = {}
                with silver_bridge(ch):
                    for file in ("gold_schema.sql", "load_gold.sql", "materialized_views.sql"):
                        for sql in statements(ROOT / "dw/ddl" / file):
                            shadow = (
                                sql.replace("gold.", "gold_build.")
                                .replace(
                                    "CREATE DATABASE IF NOT EXISTS gold",
                                    "CREATE DATABASE IF NOT EXISTS gold_build",
                                )
                                .replace("silver.", "stage_bridge.")
                            )
                            if file == "load_gold.sql":
                                build_mode = "full" if staged["needs_full"] else mode
                                action = load_gold_rows(
                                    ch,
                                    shadow,
                                    build_mode,
                                    staged["pending"],
                                    staged["deleted"],
                                    intact,
                                )
                                if shadow.startswith("INSERT INTO gold_build.fact_"):
                                    fact_actions[shadow.split()[2].split(".")[1]] = action
                            else:
                                ch.command(shadow)
                    quality = validate(
                        ch=ch, expected=staged["tables"], require_ready=False, database="gold_build"
                    )
                    quality["run_id"] = manifest["run_id"]
                    save_json(f"runs/{manifest['run_id']}-quality.json", quality)
                    save_json("quality.json", quality)
                tables = [row[0] for row in ch.query("SHOW TABLES FROM gold_build").result_rows]
                plan = publication_plan(ch, tables)
                manifest.update(
                    fact_actions=fact_actions,
                    fingerprints=quality["fingerprints"],
                    quality_checks=len(quality["checks"]),
                    quality_checked_at=quality["checked_at"],
                    gold_uuids={entry["table"]: entry["new"] for entry in plan},
                    gold_reused=False,
                )
                # The recovery plan is durable BEFORE the first table is exchanged.
                record_run(manifest, "publishing", plan)
                publish(ch, plan)
            manifest.update(
                status="success",
                finished_at=utc_now(),
                seconds=round(time.perf_counter() - started, 3),
                peak_rss_mib=peak_rss_mib(),
            )
            commit_publication(manifest, staged)
            committed = True
        except Exception as exc:
            manifest.update(status="failed", error=str(exc), finished_at=utc_now())
            # If rollback itself fails, leave phase=publishing for restart recovery.
            recover(ch)
            record_run(manifest, "failed")
            raise
        finally:
            save_json("pipeline.json", manifest)
            save_json(f"runs/{manifest['run_id']}.json", manifest)
        if committed:
            try:
                ch.command("DROP DATABASE IF EXISTS gold_build SYNC")
            except Exception:
                print(
                    "Gold committed. Old gold_build cleanup will be retried on the next build.",
                    flush=True,
                )
    print(
        f"Pipeline {manifest['status']} · {manifest['seconds']} s · {manifest['run_id']}",
        flush=True,
    )
    return manifest
