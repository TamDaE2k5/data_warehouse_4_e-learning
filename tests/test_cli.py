"""CLI validation must reject bad arguments before opening database connections."""

from contextlib import redirect_stderr, redirect_stdout
import io
import subprocess
import sys
import unittest
from pathlib import Path

from cli import parse_args


class CliTests(unittest.TestCase):
    def test_documented_small_run_and_warmup_controls(self):
        args = parse_args(["all", "--enrollments", "5000", "--runs", "3", "--warmups", "0"])
        self.assertEqual((args.enrollments, args.runs, args.warmups), (5000, 3, 0))

    def test_invalid_size_and_timing_arguments_fail_during_parse(self):
        for arguments in [
            ["generate", "--enrollments", "0"],
            ["all", "--enrollments", "101"],
            ["benchmark", "--runs", "2"],
            ["benchmark", "--warmups", "-1"],
            ["generate", "--seed", "-1"],
            ["reports", "--reuse-mirror"],
            ["doctor", "--mode", "incremental"],
        ]:
            with self.subTest(arguments=arguments), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    parse_args(arguments)
                self.assertEqual(error.exception.code, 2)

    def test_help_does_not_import_database_dependencies(self):
        root = Path(__file__).resolve().parents[1]
        code = """import builtins, runpy, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith(('etl', 'psycopg2', 'clickhouse_connect')):
        raise AssertionError('Database import attempted for --help')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
sys.argv = ['cli.py', '--help']
runpy.run_path('cli.py', run_name='__main__')
"""
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=root, capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--warmups", result.stdout)

    def test_help_returns_success(self):
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as error:
            parse_args(["--help"])
        self.assertEqual(error.exception.code, 0)
