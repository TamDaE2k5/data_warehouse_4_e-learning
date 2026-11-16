"""Offline checks for fair comparisons and coherent benchmark evidence."""

import hashlib
import json
import os
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from benchmark.evidence import (
    canonical,
    configured_resources,
    memory_bytes,
    publish_bundle,
    row_bytes,
    summarize,
)


class BenchmarkEvidenceTests(unittest.TestCase):
    def test_benchmark_rejects_same_count_unpublished_changes(self):
        from benchmark.run_benchmark import verify_publication

        with patch("benchmark.run_benchmark.fingerprints", return_value={"fact": [4, 99, 2]}):
            with self.assertRaisesRegex(RuntimeError, "published snapshot"):
                verify_publication(object(), {"fingerprints": {"fact": [4, 98, 2]}})
            verify_publication(object(), {"fingerprints": {"fact": [4, 99, 2]}})

    def test_timezone_offsets_compare_by_instant(self):
        utc = datetime(2024, 7, 1, tzinfo=timezone.utc)
        local = datetime(2024, 7, 1, 7, tzinfo=timezone(timedelta(hours=7)))
        self.assertEqual(row_bytes((utc,)), row_bytes((local,)))
        self.assertEqual(canonical([(utc,)]), canonical([(local,)]))
        self.assertNotEqual(row_bytes((utc,)), row_bytes((local.replace(tzinfo=None),)))

    def test_duplicate_and_null_semantics_survive_canonicalization(self):
        self.assertNotEqual(canonical([(None,), (None,)]), canonical([(None,)]))
        self.assertNotEqual(canonical([(None,)]), canonical([("",)]))
        self.assertEqual(canonical([(2,), (1,), (1,)]), canonical([(1,), (2,), (1,)]))

    def test_summary_reports_outlier_without_replacing_median(self):
        result = summarize("Q", {"postgres": [10, 11, 12, 13, 100], "clickhouse": [2] * 5}, 8)
        self.assertEqual(result["postgres_median_ms"], 12)
        self.assertEqual(result["postgres_max_ms"], 100)
        self.assertEqual(result["speedup_pg_over_ch"], 6)
        self.assertGreater(result["postgres_stdev_ms"], 0)
        self.assertEqual(result["measured_runs"], 5)

    def test_summary_rejects_invalid_measurements(self):
        for values in ([1, 2], [0, 1, 2], [-1, 1, 2], [float("nan"), 1, 2]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                summarize("Q", {"postgres": values, "clickhouse": [1, 2, 3]}, 1)
        with self.assertRaises(ValueError):
            summarize("Q", {"postgres": [1] * 4, "clickhouse": [1] * 3}, 1)

    def test_limits_keep_units_and_equality_explicit(self):
        with patch.dict(
            "os.environ", {"PG_MEMORY_LIMIT": "2g", "CH_MEMORY_LIMIT": "2048MiB", "DW_CPUS": "1.5"}
        ):
            result = configured_resources()
        self.assertTrue(result["equal_engine_memory_limits"])
        self.assertEqual(result["postgres_memory_bytes"], 2 * 1024**3)
        self.assertEqual(result["postgres_cpu"], 1.5)
        self.assertEqual(memory_bytes("1500m"), 1500 * 1024**2)
        for value in ("auto", "-1g", "0", "nan", "2 elephants"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                memory_bytes(value)

    def test_publication_retains_complete_history_and_checksums(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "benchmark"
            files = {"metadata.json": b'{"status":"success"}', "runs.csv": b"query,ms\nQ1,2\n"}
            receipt = publish_bundle(parent, "a" * 32, files)
            pointer = json.loads((parent / "latest.json").read_text())
            self.assertEqual(pointer, receipt)
            for name, data in files.items():
                archived = parent / pointer["directory"] / name
                self.assertEqual(archived.read_bytes(), data)
                self.assertEqual(pointer["sha256"][name], hashlib.sha256(data).hexdigest())
                self.assertEqual((parent / name).read_bytes(), data)
                if os.name == "posix":
                    self.assertEqual(stat.S_IMODE(archived.stat().st_mode), 0o644)
                    self.assertEqual(stat.S_IMODE((parent / name).stat().st_mode), 0o644)
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE((parent / "latest.json").stat().st_mode), 0o644)
            with self.assertRaises(FileExistsError):
                publish_bundle(parent, "a" * 32, files)

    def test_failed_publication_does_not_advance_latest(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            publish_bundle(parent, "a" * 32, {"metadata.json": b"first"})
            before = (parent / "latest.json").read_bytes()
            with patch("benchmark.evidence.atomic_bytes", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    publish_bundle(parent, "b" * 32, {"metadata.json": b"second"})
            self.assertEqual((parent / "latest.json").read_bytes(), before)
            self.assertFalse((parent / "history" / ("b" * 32)).exists())

    def test_publication_rejects_paths_outside_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("../escape.json", str(Path(directory) / "absolute.json")):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    publish_bundle(directory, "a" * 32, {name: b"invalid"})


if __name__ == "__main__":
    unittest.main()
