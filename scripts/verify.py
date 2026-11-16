"""Run the complete warehouse smoke suite in a new, isolated Compose project."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
PROJECT_PATTERN = re.compile(r"learning-dw-smoke-[a-z0-9][a-z0-9-]{0,42}\Z")
MEMORY_LIMITS = {
    "PG_MEMORY_LIMIT": "2g",
    "CH_MEMORY_LIMIT": "3g",
    "RUNNER_MEMORY_LIMIT": "1500m",
    "DASHBOARD_MEMORY_LIMIT": "1500m",
}


def project_name(value):
    if not PROJECT_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "project must start with learning-dw-smoke- and contain lowercase letters, digits or -"
        )
    return value


def enrollments(value):
    number = int(value)
    if number < 100 or number % 100:
        raise argparse.ArgumentTypeError("enrollments must be a positive multiple of 100")
    return number


def available_ports():
    """Reserve three distinct loopback ports while selecting them."""
    sockets = []
    try:
        for _ in range(3):
            connection = socket.socket()
            connection.bind(("127.0.0.1", 0))
            sockets.append(connection)
        return [connection.getsockname()[1] for connection in sockets]
    finally:
        for connection in sockets:
            connection.close()


def isolated_environment(project, ports, parent=None):
    environment = dict(os.environ if parent is None else parent)
    environment.update(
        COMPOSE_PROJECT_NAME=project,
        PG_PORT=str(ports[0]),
        CH_PORT=str(ports[1]),
        DASHBOARD_PORT=str(ports[2]),
        DW_MIN_SOURCE_ROWS="0",
        DW_ARTIFACTS_DIR=f"/app/artifacts/verification/{project}",
        DW_SCENARIO_PROJECT=project,
        DW_DASHBOARD_ALLOW_PIPELINE="0",
        PYTHONIOENCODING="utf-8",
    )
    environment["DW_CPUS"] = environment.get("DW_CPUS") or "2"
    for variable, default in MEMORY_LIMITS.items():
        environment[variable] = environment.get(variable) or default
    return environment


def assert_unused_project(project, environment):
    for command in [
        ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"],
        ["docker", "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={project}"],
    ]:
        result = subprocess.run(
            command, env=environment, capture_output=True, text=True, check=True, timeout=30
        )
        if result.stdout.strip():
            raise RuntimeError(
                f"Refusing to reuse existing containers or volumes for {project}. "
                "Choose a new project name; existing verification data is preserved."
            )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    generated = "learning-dw-smoke-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    generated += "-" + uuid.uuid4().hex[:8]
    parser.add_argument("--project", type=project_name, default=generated)
    parser.add_argument("--enrollments", type=enrollments, default=5000)
    parser.add_argument(
        "--skip-build", action="store_true", help="Use images already built locally"
    )
    args = parser.parse_args(argv)
    directory = ROOT / "artifacts" / "verification" / args.project
    if directory.exists():
        parser.error("verification artifact directory already exists; choose a new project name")
    directory.mkdir(parents=True)
    logs = directory / "logs"
    logs.mkdir()
    environment = isolated_environment(args.project, available_ports())
    compose = ["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "-p", args.project]
    receipt = dict(
        status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
        project=args.project,
        enrollments=args.enrollments,
        ports=dict(
            postgres=int(environment["PG_PORT"]),
            clickhouse_http=int(environment["CH_PORT"]),
            dashboard=int(environment["DASHBOARD_PORT"]),
        ),
        configured_limits=dict(
            cpu_quota=environment["DW_CPUS"],
            **{variable: environment[variable] for variable in MEMORY_LIMITS},
        ),
        scope="fresh-volume isolated synthetic smoke; not production load or backup recovery",
        steps=[],
    )
    started = time.perf_counter()
    services_created = False

    def save():
        (directory / "verification.json").write_text(
            json.dumps(receipt, indent=2), encoding="utf-8"
        )

    def run(name, arguments, timeout=900):
        print(f"[{name}] Running...", flush=True)
        begin = time.perf_counter()
        log = logs / f"{len(receipt['steps']) + 1:02d}-{name}.log"
        step = dict(name=name, status="running", log=f"logs/{log.name}")
        receipt["steps"].append(step)
        save()
        try:
            with log.open("w", encoding="utf-8") as output:
                result = subprocess.run(
                    arguments,
                    cwd=ROOT,
                    env=environment,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                    check=False,
                )
            step["returncode"] = result.returncode
            if result.returncode:
                print(
                    "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-60:])
                )
                raise RuntimeError(f"{name} failed with exit code {result.returncode}; see {log}")
            step["status"] = "passed"
        except Exception:
            step["status"] = "failed"
            raise
        finally:
            step["seconds"] = round(time.perf_counter() - begin, 3)
            save()
        print(f"[{name}] Passed in {step['seconds']} s", flush=True)

    try:
        run("docker-ready", ["docker", "version", "--format", "{{.Server.Version}}"], 30)
        assert_unused_project(args.project, environment)
        run("compose-config", [*compose, "config", "--quiet"], 30)
        if not args.skip_build:
            run("build", [*compose, "build", "runner", "dashboard"])
        # Mark ownership before startup so partial startup is also stopped on failure.
        services_created = True
        run("start", [*compose, "up", "-d", "--wait", "postgres", "clickhouse"], 180)
        runner = [*compose, "run", "--rm", "--no-deps", "runner"]
        run(
            "full-reports-benchmark",
            [
                *runner,
                "python",
                "cli.py",
                "all",
                "--enrollments",
                str(args.enrollments),
                "--runs",
                "3",
            ],
        )
        run(
            "unit-integration",
            [*runner, "python", "scripts/check.py", "--skip-style", "--integration"],
        )
        run(
            "dashboard-offline-unit",
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "dashboard",
                "python",
                "scripts/check.py",
                "--skip-style",
                "--module",
                "tests.test_dashboard_unit",
                "--fail-on-skip",
                "--receipt",
                "dashboard-unit-checks.json",
            ],
        )
        run(
            "failure-recovery",
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "-e",
                "DW_ALLOW_SCENARIOS=1",
                "runner",
                "python",
                "-m",
                "tests.scenarios",
            ],
        )
        run(
            "dashboard",
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "dashboard",
                "python",
                "-m",
                "tests.dashboard_check",
            ],
        )
        run("doctor", [*runner, "python", "cli.py", "doctor"])
        receipt["status"] = "success"
    except (OSError, subprocess.SubprocessError, RuntimeError, KeyboardInterrupt) as error:
        receipt.update(status="failed", error=str(error) or "Interrupted by user")
        print(f"Verification failed: {receipt['error']}", file=sys.stderr)
    finally:
        if services_created:
            for name, command in [
                ("service-logs", [*compose, "logs", "--no-color", "--tail", "200"]),
                ("stop", [*compose, "stop", "--timeout", "20"]),
            ]:
                try:
                    run(name, command, 90)
                except (OSError, subprocess.SubprocessError, RuntimeError) as error:
                    receipt.update(status="failed", cleanup_error=str(error))
        receipt.update(
            finished_at=datetime.now(timezone.utc).isoformat(),
            seconds=round(time.perf_counter() - started, 3),
            volumes_preserved=True,
        )
        save()
        print(f"Evidence: {directory / 'verification.json'}", flush=True)
        if services_created:
            print(
                f"Only project {args.project} was stopped; its volumes remain available.",
                flush=True,
            )
        else:
            print(
                "Services were not started; existing Docker resources were left unchanged.",
                flush=True,
            )
    return 0 if receipt["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
