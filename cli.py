"""Single entry point for setup, data, ETL, analytics and diagnostics."""

import argparse
import json
import sys
from contextlib import closing


def enrollment_count(value):
    number = int(value)
    if number < 100 or number % 100:
        raise argparse.ArgumentTypeError("must be a positive multiple of 100 (at least 100)")
    return number


def measured_runs(value):
    number = int(value)
    if number < 3:
        raise argparse.ArgumentTypeError("must be at least 3")
    return number


def nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return number


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Online Learning Warehouse: synthetic data, ETL, analytics and diagnostics"
    )
    parser.add_argument(
        "command",
        choices=[
            "setup",
            "generate",
            "pipeline",
            "validate",
            "reports",
            "benchmark",
            "doctor",
            "all",
        ],
    )
    parser.add_argument(
        "--enrollments",
        type=enrollment_count,
        default=500000,
        help="Synthetic source size for generate/all; multiple of 100 (default: 500000)",
    )
    parser.add_argument(
        "--seed", type=nonnegative, default=2024, help="Deterministic generator seed"
    )
    parser.add_argument(
        "--runs", type=measured_runs, default=5, help="Measured benchmark runs, >=3"
    )
    parser.add_argument(
        "--warmups", type=nonnegative, default=2, help="Benchmark warm-up runs, >=0"
    )
    parser.add_argument(
        "--reuse-mirror",
        action="store_true",
        help="Verify and reuse the existing PostgreSQL Gold mirror",
    )
    parser.add_argument("--mode", choices=["full", "incremental"], default="full")
    args = parser.parse_args(argv)
    if args.reuse_mirror and args.command not in ("benchmark", "all"):
        parser.error("--reuse-mirror is only valid for benchmark/all")
    if args.mode != "full" and args.command not in ("pipeline", "all"):
        parser.error("--mode is only valid for pipeline/all")
    return args


def main(argv=None):
    # Parse before importing database clients so --help and invalid input work offline.
    args = parse_args(argv)
    from etl.common import project_lock, source_connect

    if args.command in ("setup", "all"):
        from etl.bootstrap import setup

        setup()
        if args.command == "setup":
            print("Setup complete. Source reader and staging roles are ready.")
            return
    if args.command == "doctor":
        from etl.doctor import doctor

        print(json.dumps(doctor(), indent=2, ensure_ascii=False, default=str))
        return
    with project_lock(shared=args.command == "reports"):
        if args.command in ("generate", "all"):
            with closing(source_connect()) as source, source.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM oltp.enrollments")
                populated = cursor.fetchone()[0] > 0
            if args.command == "generate" or not populated:
                from oltp.generate_data import generate

                generate(args.enrollments, args.seed)
            else:
                print("Source already populated. Reusing source data.")
        if args.command in ("pipeline", "all"):
            from etl.pipeline import pipeline

            pipeline(args.mode)
        if args.command == "validate":
            from etl.validate import validate

            validate()
        if args.command in ("reports", "all"):
            from analytics.reports import reports

            reports()
        if args.command in ("benchmark", "all"):
            from benchmark.run_benchmark import benchmark

            benchmark(args.runs, reuse_mirror=args.reuse_mirror, warmups=args.warmups)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, AssertionError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print(
            "Interrupted. Run pipeline again to recover any unfinished publication.",
            file=sys.stderr,
        )
        sys.exit(130)
