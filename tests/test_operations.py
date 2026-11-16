"""Verify isolation guard behavior without starting Docker or modifying data."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from scripts.verify import (
    available_ports,
    assert_unused_project,
    isolated_environment,
    project_name,
)
from scripts.verify import main as verify


class VerificationIsolationTests(unittest.TestCase):
    def test_main_project_names_are_rejected(self):
        for value in ["online-learning-dw", "learning-dw-ci", "../project", "learning-dw-smoke-"]:
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                project_name(value)

    def test_project_configuration_overrides_main_runtime_destinations(self):
        parent = {
            "COMPOSE_PROJECT_NAME": "main",
            "DW_ARTIFACTS_DIR": "/app/artifacts",
            "DW_DASHBOARD_ALLOW_PIPELINE": "1",
            "DW_CPUS": "4",
        }
        environment = isolated_environment("learning-dw-smoke-unit", [15001, 15002, 15003], parent)
        self.assertEqual(environment["DW_SCENARIO_PROJECT"], "learning-dw-smoke-unit")
        self.assertEqual(
            environment["DW_ARTIFACTS_DIR"], "/app/artifacts/verification/learning-dw-smoke-unit"
        )
        self.assertEqual(environment["DW_DASHBOARD_ALLOW_PIPELINE"], "0")
        self.assertEqual(environment["PG_PORT"], "15001")
        self.assertEqual(environment["DW_CPUS"], "4")
        self.assertEqual(environment["PG_MEMORY_LIMIT"], "2g")
        self.assertEqual(environment["CH_MEMORY_LIMIT"], "3g")
        self.assertEqual(parent["COMPOSE_PROJECT_NAME"], "main")

    def test_empty_resource_overrides_use_verifier_defaults(self):
        environment = isolated_environment(
            "learning-dw-smoke-unit",
            [15001, 15002, 15003],
            {"DW_CPUS": "", "PG_MEMORY_LIMIT": "", "CH_MEMORY_LIMIT": "4g"},
        )
        self.assertEqual(environment["DW_CPUS"], "2")
        self.assertEqual(environment["PG_MEMORY_LIMIT"], "2g")
        self.assertEqual(environment["CH_MEMORY_LIMIT"], "4g")

    def test_selected_ports_are_distinct_and_valid(self):
        ports = available_ports()
        self.assertEqual(len(set(ports)), 3)
        self.assertTrue(all(0 < port < 65536 for port in ports))

    @patch("scripts.verify.subprocess.run")
    def test_existing_containers_or_volumes_are_never_reused(self, run):
        run.return_value = SimpleNamespace(stdout="an-existing-resource\n")
        with self.assertRaisesRegex(RuntimeError, "Refusing to reuse"):
            assert_unused_project("learning-dw-smoke-unit", {})

    @patch("scripts.verify.subprocess.run")
    def test_unused_project_checks_both_containers_and_volumes(self, run):
        run.return_value = SimpleNamespace(stdout="")
        assert_unused_project("learning-dw-smoke-unit", {})
        self.assertEqual(run.call_count, 2)

    @patch("scripts.verify.subprocess.run")
    def test_partial_startup_failure_stops_only_the_owned_project(self, run):
        commands = []

        def execute(command, **kwargs):
            commands.append(command)
            return SimpleNamespace(returncode=1 if "up" in command else 0, stdout="")

        run.side_effect = execute
        project = "learning-dw-smoke-cleanup-test"
        with tempfile.TemporaryDirectory() as temporary:
            with patch("scripts.verify.ROOT", Path(temporary)):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    code = verify(["--project", project, "--skip-build"])
            receipt = json.loads(
                (
                    Path(temporary) / "artifacts/verification" / project / "verification.json"
                ).read_text(encoding="utf-8")
            )
        self.assertEqual(code, 1)
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(set(receipt["ports"]), {"postgres", "clickhouse_http", "dashboard"})
        self.assertEqual(receipt["configured_limits"]["PG_MEMORY_LIMIT"], "2g")
        stop_commands = [command for command in commands if "stop" in command]
        self.assertEqual(len(stop_commands), 1)
        self.assertEqual(stop_commands[0][stop_commands[0].index("-p") + 1], project)
        self.assertFalse(any("down" in command or "prune" in command for command in commands))
        self.assertTrue(receipt["volumes_preserved"])
