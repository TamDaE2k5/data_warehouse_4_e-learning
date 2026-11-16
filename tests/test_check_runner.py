"""Guard CI against an apparently green suite that skipped or ran no selected tests."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.check import main, receipt_name, test_suite as selected_suite


class CheckRunnerTests(unittest.TestCase):
    def execute(self, suite, strict=False):
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with (
                patch("scripts.check.ROOT", directory),
                patch.dict(os.environ, {"DW_ARTIFACTS_DIR": str(directory)}),
                patch("scripts.check.test_suite", return_value=(suite, [])),
                redirect_stderr(io.StringIO()),
                redirect_stdout(io.StringIO()),
            ):
                try:
                    arguments = ["--skip-style", "--receipt", "selected-checks.json"]
                    if strict:
                        arguments.append("--fail-on-skip")
                    code = main(arguments)
                    receipt = json.loads(
                        (directory / "selected-checks.json").read_text(encoding="utf-8")
                    )
                finally:
                    os.chdir(original)
        return code, receipt

    def test_ci_strict_mode_fails_when_a_selected_module_skips(self):
        class UnavailableDependencies(unittest.TestCase):
            @unittest.skip("fixture missing a dashboard dependency")
            def test_dashboard(self):
                pass

        code, receipt = self.execute(
            unittest.defaultTestLoader.loadTestsFromTestCase(UnavailableDependencies), strict=True
        )
        self.assertEqual(code, 1)
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failures"], 0)
        self.assertEqual(receipt["skipped"], 1)
        self.assertIn("dashboard dependency", receipt["skipped_tests"][0]["reason"])

    def test_optional_skips_remain_visible_outside_strict_mode(self):
        class OptionalDependencies(unittest.TestCase):
            @unittest.skip("fixture intentionally optional")
            def test_dashboard(self):
                pass

        code, receipt = self.execute(
            unittest.defaultTestLoader.loadTestsFromTestCase(OptionalDependencies)
        )
        self.assertEqual(code, 0)
        self.assertEqual(receipt["status"], "success")
        self.assertEqual(receipt["skipped"], 1)

    def test_an_empty_selection_is_never_successful(self):
        code, receipt = self.execute(unittest.TestSuite())
        self.assertEqual(code, 1)
        self.assertEqual(receipt["tests"], 0)
        self.assertEqual(receipt["status"], "failed")

    def test_module_level_skip_is_reported_instead_of_losing_the_receipt(self):
        with patch(
            "scripts.check.unittest.defaultTestLoader.loadTestsFromName",
            side_effect=unittest.SkipTest("dashboard dependency absent"),
        ):
            suite, excluded = selected_suite(module="tests.optional_dashboard")
        code, receipt = self.execute(suite, strict=True)
        self.assertEqual(code, 1)
        self.assertEqual(excluded, [])
        self.assertEqual(receipt["skipped"], 1)
        self.assertIn("dashboard dependency absent", receipt["skipped_tests"][0]["reason"])

    def test_focused_selection_retains_explicit_integration_exclusions(self):
        class Offline(unittest.TestCase):
            def test_offline(self):
                pass

        class Database(unittest.TestCase):
            integration = True

            def test_database(self):
                pass

        suite = unittest.TestSuite([Offline("test_offline"), Database("test_database")])
        with patch(
            "scripts.check.unittest.defaultTestLoader.loadTestsFromName", return_value=suite
        ):
            selected, excluded = selected_suite(module="tests.example")
        self.assertEqual(selected.countTestCases(), 1)
        self.assertEqual(len(excluded), 1)
        self.assertIn("test_database", excluded[0])

    def test_receipt_cannot_escape_evidence_directory(self):
        for value in [
            "../receipt.json",
            "C:receipt.json",
            ".json",
            "folder/receipt.json",
            "log.txt",
        ]:
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                receipt_name(value)
        self.assertEqual(receipt_name("dashboard-unit-checks.json"), "dashboard-unit-checks.json")
