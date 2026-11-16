# Verification and operating boundaries

## Two verification levels

`python scripts/check.py` runs formatting, lint and offline unit tests. It records explicitly excluded integration tests. `--integration` includes those tests and requires a populated warehouse; it does not create services or data.

Use `--fail-on-skip` when every selected test must execute. CI installs both runner and dashboard dependencies and uses this strict mode. The isolated verifier also runs the focused dashboard unit module strictly in the dashboard image, with its own `dashboard-unit-checks.json` receipt; an expected missing-Streamlit skip in the lean runner image does not cover those tests.

`python scripts/verify.py` creates a new Compose project and tests the vertical slice from empty volumes: source generation, full ETL, quality gate, CSV reports, benchmark parity, unit/integration tests, deliberate failure scenarios, dashboard checks and diagnostics. Every step has a log and elapsed time in `artifacts/verification/<project>/verification.json`.

The verifier refuses to reuse existing project containers, volumes or artifact directories. Three distinct free loopback ports are selected at startup. Another process can still claim a port between selection and Docker binding; rerun with a new project if startup reports a port collision. The default fixture has 5,000 enrollments and is a smoke test, not the full-scale benchmark.

```sh
python scripts/verify.py
python scripts/verify.py --enrollments 10000
python scripts/verify.py --skip-build
```

The last command requires current runner and dashboard images. Do not use it to validate changes to dependencies or Docker build instructions.

## Evidence and cleanup

The verifier stops only its own project after success or failure and keeps its volumes for inspection. It never uses `down -v`, prunes Docker resources or touches another project's containers. Read its project name from the receipt before inspecting or cleaning up resources. Runtime evidence is ignored by Git; CI uploads it as a separate artifact even when a test fails.

The pure unit suite and the Docker suite have separate CI jobs. The smoke job starts only after static checks pass. Repository automation has read-only contents permission.

Reviewed public results and their exact data scales are listed in the [verification evidence index](verification/README.md). Test suites overlap; keep their counts and historical dates separate.

## Memory and UI configuration

Set resource limits before starting services:

| Variable | Default | Applies to |
|---|---|---|
| `DW_CPUS` | `4` | PostgreSQL, ClickHouse and runner CPU quota |
| `PG_MEMORY_LIMIT` | `2g` | PostgreSQL container |
| `CH_MEMORY_LIMIT` | `3g` | ClickHouse container |
| `RUNNER_MEMORY_LIMIT` | `1500m` | ETL and benchmark client container |
| `DASHBOARD_MEMORY_LIMIT` | `1500m` | Streamlit container |
| `DW_DASHBOARD_ALLOW_PIPELINE` | `0` | Explicit local operator opt-in |

The memory strings use Docker's units. They are configuration limits, not measured query memory. Changing a limit can invalidate comparisons with historical benchmarks. Keep the values and actual query settings with every result.

The verifier defaults to 2 CPU quotas per engine and explicitly supplies its memory defaults, overriding values from a local `.env` unless the caller sets corresponding environment variables. Its receipt records the non-secret limits and selected ports used for that isolated project.

The dashboard is read-only by default. Enabling pipeline controls is intended only for a trusted localhost operator demo. It does not add authentication or authorization.

## Recovering an interrupted run

Inspect the failed run's receipt and logs before changing state. Run the pipeline again to execute the durable publication recovery plan. Do not delete `gold_build`, edit checkpoints or remove pending changes to make an error disappear. An interrupted run and an unavailable source are different failures; keep both pieces of evidence when reporting an issue.

The automated recovery suite covers the points encoded in its assertions. It is not a backup restore exercise, a power-loss guarantee or a distributed transaction across the two database engines. Backup restoration and multi-user production load remain separate acceptance exercises.
