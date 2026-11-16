"""Regression coverage for publication readiness, locks and unsafe reuse."""

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from etl.common import project_lock, require_success, save_json
from etl.pipeline import gold_intact, peak_rss_mib, pipeline
from tests.scenarios import scenario_guard


class PublicationReliabilityTests(unittest.TestCase):
    def connection(self, rows):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = rows
        return connection, cursor

    def test_json_receipts_preserve_unicode_and_are_readable_after_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "nested" / "receipt.json"
            with patch("etl.common.ARTIFACTS", root):
                save_json("nested/receipt.json", {"status": "running"})
                receipt = {"status": "success", "details": {"label": "Kiểm tra dữ liệu", "rows": 7}}
                save_json("nested/receipt.json", receipt)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), receipt)
            self.assertIn("Kiểm tra dữ liệu", path.read_text(encoding="utf-8"))
            self.assertEqual(list(path.parent.iterdir()), [path])
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)

    def test_failed_receipt_replacement_preserves_previous_and_removes_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "nested" / "receipt.json"
            with patch("etl.common.ARTIFACTS", root):
                save_json("nested/receipt.json", {"status": "success", "run_id": "previous"})
                previous = path.read_bytes()
                with (
                    patch("etl.common.os.replace", side_effect=OSError("replace failed")),
                    self.assertRaisesRegex(OSError, "replace failed"),
                ):
                    save_json("nested/receipt.json", {"status": "running", "run_id": "new"})
            self.assertEqual(path.read_bytes(), previous)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_same_cardinality_content_changes_invalidate_gold_reuse(self):
        previous = {
            "gold_uuids": {"fact_payments": "stable-id"},
            "fingerprints": {"fact_payments": [100, 11, 22]},
        }
        with (
            patch(
                "etl.pipeline.table_uuids", return_value={("gold", "fact_payments"): "stable-id"}
            ),
            patch("etl.pipeline.fingerprints", return_value={"fact_payments": [100, 33, 44]}),
        ):
            self.assertFalse(gold_intact(MagicMock(), previous))

    def test_missing_publication_identifiers_cannot_enable_reuse(self):
        with patch("etl.pipeline.fingerprints") as content:
            self.assertFalse(gold_intact(MagicMock(), {"fingerprints": {}}))
            content.assert_not_called()

    def test_old_json_cannot_claim_a_fresh_database_is_published(self):
        connection, _ = self.connection([None, None])
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "pipeline.json").write_text(json.dumps({"status": "success"}))
            with (
                patch("etl.common.staging_connect", return_value=connection),
                patch("etl.common.ARTIFACTS", Path(directory)),
                self.assertRaisesRegex(RuntimeError, "No published warehouse"),
            ):
                require_success()
        connection.close.assert_called_once()

    def test_incomplete_publication_blocks_readiness(self):
        connection, _ = self.connection([({"status": "success"},), (1,)])
        with (
            patch("etl.common.staging_connect", return_value=connection),
            self.assertRaisesRegex(RuntimeError, "requires recovery"),
        ):
            require_success()

    def test_database_manifest_is_the_readiness_source(self):
        manifest = {"status": "success", "run_id": "published"}
        connection, _ = self.connection([(manifest,), None])
        with patch("etl.common.staging_connect", return_value=connection):
            self.assertEqual(require_success(), manifest)

    def test_lock_connection_closes_if_acquisition_query_fails(self):
        connection, cursor = self.connection([])
        cursor.execute.side_effect = RuntimeError("database unavailable")
        with (
            patch("etl.common.staging_connect", return_value=connection),
            self.assertRaisesRegex(RuntimeError, "database unavailable"),
        ):
            with project_lock():
                self.fail("Lock body must not execute")
        connection.close.assert_called_once()

    def test_lock_connection_closes_if_work_fails(self):
        connection, _ = self.connection([(True,)])
        with (
            patch("etl.common.staging_connect", return_value=connection),
            self.assertRaisesRegex(RuntimeError, "work failed"),
        ):
            with project_lock():
                raise RuntimeError("work failed")
        connection.close.assert_called_once()

    def test_invalid_pipeline_mode_fails_before_recording_a_run(self):
        with patch("etl.pipeline.record_run") as record:
            with self.assertRaisesRegex(ValueError, "Pipeline mode"):
                pipeline("invalid")
            record.assert_not_called()

    def test_peak_rss_is_explicitly_unavailable_without_resource_module(self):
        with patch.dict("sys.modules", {"resource": None}):
            self.assertIsNone(peak_rss_mib())

    def test_destructive_scenarios_reject_the_normal_project(self):
        with (
            patch.dict(
                "os.environ",
                {"DW_ALLOW_SCENARIOS": "1", "DW_SCENARIO_PROJECT": "online-learning-dw"},
            ),
            self.assertRaisesRegex(RuntimeError, "isolated verification project"),
        ):
            scenario_guard()

    def test_destructive_scenarios_reject_mismatched_artifact_paths(self):
        environment = {
            "DW_ALLOW_SCENARIOS": "1",
            "DW_SCENARIO_PROJECT": "learning-dw-smoke-unit",
            "DW_MIN_SOURCE_ROWS": "0",
        }
        with (
            patch.dict("os.environ", environment),
            patch("tests.scenarios.ARTIFACTS", Path("artifacts")),
            self.assertRaisesRegex(RuntimeError, "isolated verification project"),
        ):
            scenario_guard()

    def test_destructive_scenarios_accept_a_marked_isolated_verification(self):
        project = "learning-dw-smoke-unit"
        environment = {
            "DW_ALLOW_SCENARIOS": "1",
            "DW_SCENARIO_PROJECT": project,
            "DW_MIN_SOURCE_ROWS": "0",
        }
        with (
            patch.dict("os.environ", environment),
            patch("tests.scenarios.ARTIFACTS", Path("artifacts/verification") / project),
        ):
            self.assertEqual(scenario_guard(), project)
