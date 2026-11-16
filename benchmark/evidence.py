"""Deterministic comparison, timing summaries and complete benchmark publications."""

import hashlib
import json
import math
import os
import re
import statistics
import tempfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path


def normalize(value):
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else str(value.normalize())
    return value


def canonical(rows):
    """Compare multisets, retaining duplicate rows and distinguishing NULL/empty."""
    return sorted(
        json.dumps([normalize(v) for v in row], ensure_ascii=False, separators=(",", ":"))
        for row in rows
    )


def row_bytes(row):
    """The same UTC instant hashes equally across naive PG and aware CH values."""
    return (
        json.dumps([normalize(v) for v in row], ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode()


def summarize(name, times, rows):
    result = dict(query=name)
    for engine in ("postgres", "clickhouse"):
        values = times[engine]
        if len(values) < 3 or any(not math.isfinite(v) or v <= 0 for v in values):
            raise ValueError("At least three finite, positive timings per engine are required")
        result.update(
            {
                engine + "_median_ms": round(statistics.median(values), 3),
                engine + "_min_ms": round(min(values), 3),
                engine + "_max_ms": round(max(values), 3),
                engine + "_mean_ms": round(statistics.mean(values), 3),
                engine + "_stdev_ms": round(statistics.stdev(values), 3),
            }
        )
    if len(times["postgres"]) != len(times["clickhouse"]):
        raise ValueError("Both engines must have the same number of measured runs")
    result["speedup_pg_over_ch"] = round(
        statistics.median(times["postgres"]) / statistics.median(times["clickhouse"]), 6
    )
    result["measured_runs"] = len(times["postgres"])
    result["result_rows"] = rows
    return result


def memory_bytes(value):
    """Parse Docker byte limits using binary unit multipliers, without guessing."""
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([kmgt]?)(?:i?b)?\s*", str(value), re.I)
    if not match:
        raise ValueError("Invalid Docker memory limit: " + str(value))
    number, unit = match.groups()
    result = int(Decimal(number) * (1024 ** ("kmgt".index(unit.lower()) + 1) if unit else 1))
    if result <= 0:
        raise ValueError("Memory limit must be positive")
    return result


def configured_resources():
    limits = {
        "postgres": os.getenv("PG_MEMORY_LIMIT", "2g"),
        "clickhouse": os.getenv("CH_MEMORY_LIMIT", "3g"),
        "runner": os.getenv("RUNNER_MEMORY_LIMIT", "1500m"),
    }
    cpu = float(os.getenv("DW_CPUS", "4"))
    if not math.isfinite(cpu) or cpu <= 0:
        raise ValueError("DW_CPUS must be finite and positive")
    result = {"postgres_cpu": cpu, "clickhouse_cpu": cpu}
    for engine, limit in limits.items():
        result[engine + "_memory"] = limit
        result[engine + "_memory_bytes"] = memory_bytes(limit)
    result["equal_engine_memory_limits"] = (
        result["postgres_memory_bytes"] == result["clickhouse_memory_bytes"]
    )
    result["scope"] = "Configured Compose limits, not observed query resource consumption"
    return result


def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            # Evidence written by container root must remain readable by the host runner.
            if os.name == "posix":
                os.fchmod(output.fileno(), 0o644)
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def publish_bundle(parent, run_id, files):
    """Publish an immutable complete bundle; only then advance latest.json.

    Compatibility files are individual atomic copies. Readers requiring a coherent
    set follow latest.json into its immutable run directory and verify the hashes.
    A failed run never advances the pointer to an earlier partial result set.
    """
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise ValueError("Benchmark run_id must be a 32-character lowercase UUID hex")
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    final = parent / "history" / run_id
    if final.exists():
        raise FileExistsError("Benchmark publication already exists: " + run_id)
    for name in files:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Benchmark artifact path must remain inside its bundle")
    with tempfile.TemporaryDirectory(prefix=".pending-", dir=parent) as temporary:
        staged = Path(temporary) / "bundle"
        staged.mkdir()
        hashes = {}
        for name, data in files.items():
            path = staged / name
            atomic_bytes(path, data)
            hashes[name] = hashlib.sha256(data).hexdigest()
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged, final)
    # Metadata is updated last among compatibility paths.
    for name in sorted(files, key=lambda name: name == "metadata.json"):
        atomic_bytes(parent / name, files[name])
    receipt = dict(
        status="success", benchmark_run=run_id, directory="history/" + run_id, sha256=hashes
    )
    atomic_bytes(parent / "latest.json", json.dumps(receipt, indent=2).encode())
    return receipt
