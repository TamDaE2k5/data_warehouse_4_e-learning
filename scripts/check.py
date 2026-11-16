"""Run formatting, lint and explicit offline or database-backed test suites."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def iter_tests(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from iter_tests(item)
        else:
            yield item


def test_suite(include_integration=False, module=None):
    selected, excluded = [], []
    if module:
        try:
            discovered = unittest.defaultTestLoader.loadTestsFromName(module)
        except unittest.SkipTest as error:
            # Unlike discovery, loadTestsFromName propagates module-level SkipTest.
            # Keep it in the result so the strict gate and evidence report see it.
            reason = str(error)

            def skipped_module(reason=reason):
                raise unittest.SkipTest(reason)

            discovered = unittest.TestSuite(
                [unittest.FunctionTestCase(skipped_module, description=module)]
            )
    else:
        discovered = unittest.defaultTestLoader.discover(
            str(ROOT / "tests"), top_level_dir=str(ROOT)
        )
    for test in iter_tests(discovered):
        if getattr(test.__class__, "integration", False) and not include_integration:
            excluded.append(test.id())
        else:
            selected.append(test)
    return unittest.TestSuite(selected), excluded


def receipt_name(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.json", value):
        raise argparse.ArgumentTypeError("receipt must be a plain .json filename")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--integration", action="store_true", help="Include tests that require populated databases"
    )
    parser.add_argument("--skip-style", action="store_true", help="Run tests without Ruff checks")
    parser.add_argument(
        "--module", help="Run one dotted test module instead of discovering all tests"
    )
    parser.add_argument(
        "--fail-on-skip", action="store_true", help="Fail if any selected test skips"
    )
    parser.add_argument(
        "--receipt", type=receipt_name, default="code-checks.json", help="Evidence JSON filename"
    )
    args = parser.parse_args(argv)
    os.chdir(ROOT)
    if not args.skip_style:
        for arguments in [["check", "."], ["format", "--check", "."]]:
            subprocess.run([sys.executable, "-m", "ruff", *arguments], check=True)
    suite, excluded = test_suite(args.integration, args.module)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = (
        result.wasSuccessful()
        and result.testsRun > 0
        and not (args.fail_on_skip and result.skipped)
    )
    receipt = dict(
        status="success" if passed else "failed",
        checked_at=datetime.now(timezone.utc).isoformat(),
        lint="not_run" if args.skip_style else "passed",
        formatting="not_run" if args.skip_style else "passed",
        tests=result.testsRun,
        skipped=len(result.skipped),
        skipped_tests=[dict(test=test.id(), reason=reason) for test, reason in result.skipped],
        fail_on_skip=args.fail_on_skip,
        selected_module=args.module,
        failures=len(result.failures),
        errors=len(result.errors),
        integration_included=args.integration,
        integration_excluded=excluded,
        scope="unit and database integration" if args.integration else "offline unit tests",
    )
    directory = Path(os.getenv("DW_ARTIFACTS_DIR", str(ROOT / "artifacts")))
    directory.mkdir(parents=True, exist_ok=True)
    (directory / args.receipt).write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    if args.fail_on_skip and result.skipped:
        print("Selected tests skipped; --fail-on-skip requires all selected tests to execute.")
    print(f"Evidence: {directory / args.receipt}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
