# Verification evidence

This directory separates historical measurements from the fresh upgrade acceptance run. A successful small-fixture check does not revalidate the old full-scale timings, and an old large benchmark is not a fresh result for the current revision.

## Fresh upgrade acceptance on 15 November 2026

The local Docker verifier started with new volumes, 5,000 synthetic enrollments and **69,203 source rows**. All **12 verification steps** succeeded in **217.351 seconds**, including building images, a full load, report export, benchmark parity, failure recovery, dashboard checks and stopping the isolated project. That duration covers the entire verifier, not the ETL alone. See the [curated verification receipt](upgrade/verification.json), [generation receipt](upgrade/generation.json) and [machine-readable summary](upgrade/summary.json).

| Evidence | Fresh result | Scope |
|---|---|---|
| [Offline checks](upgrade/offline-checks.json) | 69 tests, zero skips or failures | Dashboard image with networking disabled; four database integration tests explicitly excluded |
| [Runner unit/integration checks](upgrade/runner-checks.json) | 58 reported, 57 executed, one expected module skip; zero failures/errors | Includes the four database integration tests; runner image does not install Streamlit |
| [Strict focused dashboard units](upgrade/dashboard-unit-checks.json) | 14 tests, zero skips or failures | Runs in the dashboard image; rejects a skipped module as a failed gate |
| [Failure and recovery checks](upgrade/regression.json) | 23 checks passed | Deliberate mutations in the isolated synthetic database |
| [Live dashboard checks](upgrade/dashboard-tests.json) | 15 checks passed | Rendered pages, filters and independent reconciliation to Silver |
| [Quality checks](upgrade/quality.json) | 123 checks passed | Latest checked warehouse state within the smoke workflow |
| [Report export summary](upgrade/reports.json) | 10 CSV reports exported | Initial published snapshot, before failure scenarios modify the source |
| [Benchmark metadata](upgrade/benchmark/metadata.json) | 11 full-row table hashes and seven query outputs matched | Small fixture, two warm-ups and three measured runs per engine/query |

These counts overlap. The 14 focused dashboard tests are also part of the 69 offline tests. Do not add the offline, runner and dashboard counts to produce a combined test total. The single runner skip is explicit and is covered by the separate strict dashboard step.

The full smoke completed at **01:51:56 UTC**. Final UI polish and artifact receipt permission fixes were verified afterward by the 69-test strict offline gate at **02:14:47 UTC** and the 15 live dashboard checks at **02:14:58 UTC**. The later offline gate includes all 14 dashboard unit tests. The full pipeline, recovery and benchmark workflow was not repeated after those changes; its receipts keep their original timestamps.

A separate manual browser review covered all six pages, empty category selection, Reset, the desktop layout and a 390-pixel mobile viewport with no document-level horizontal overflow. A Streamlit session-state warning was corrected during this review. This is a manual usability observation, not a load test or an automated screenshot-diff gate.

The checker receipts mark lint and formatting as `not_run` because these particular commands used `--skip-style`. They are test receipts, not proof of Ruff execution. CI defines a separate lint/format/offline gate; the local Docker receipts here do not establish a GitHub-hosted CI outcome.

### What the failure checks establish

The [regression receipt](upgrade/regression.json) lists each assertion. Coverage includes reader/writer and writer/writer exclusion, same-count Gold corruption detection, additive and missing source columns, late commits, new invalid rows, invalid updates and correction, deletion propagation, quality-failure preservation, retained staging deltas, a process stopped after an actual table exchange, restart recovery and protection against resurrecting deleted rows.

The fixture changes during these scenarios. The initial benchmark contains **69,800 Gold rows**. After the deliberate deletions, the final source contains **69,201 rows** and Gold contains **69,798 rows**. This difference is expected: a separate source identity table is not copied as a second dimension, and the warehouse creates its date dimension. The [latest pipeline receipt](upgrade/pipeline.json) reuses the most recent successfully checked Gold, so its run ID can differ from the [quality receipt's](upgrade/quality.json) run ID. Reports and benchmark metadata refer to the initial pre-scenario snapshot; the live dashboard checks refer to the later published snapshot.

These are assertions for the encoded scenarios, not a guarantee against every failure. Whole-machine power loss, backup restoration, production concurrency and availability were not established by this smoke run.

### Reading the fresh benchmark

The [summary CSV](upgrade/benchmark/summary.csv), [per-run CSV](upgrade/benchmark/runs.csv) and [results narrative](upgrade/benchmark/results.md) describe the fresh **small** dataset. PostgreSQL has lower median latency for Q1–Q6 in this run; ClickHouse has lower median latency for Q7. This is not inconsistent with the historical large-data results: the dataset, CPU quota and amount of work differ.

Both engines have a configured CPU quota of 2. PostgreSQL has a 2 GiB memory limit and ClickHouse 3 GiB, so this is not an equal-memory comparison. Timings include client execution and fetching results, use serial queries and do not flush caches. Query CPU usage, peak query memory and I/O are not measured.

Storage metadata now enumerates **exactly the 11 mirrored Gold tables** on both engines; ClickHouse auxiliary aggregate tables are recorded separately. PostgreSQL includes its indexes, while ClickHouse measures active parts and their metadata. This corrected scope must not be retroactively applied to the older storage results.

The [benchmark manifest](upgrade/benchmark/manifest.json) retains the checksums of the immutable runtime bundle. It covers the measured SQL pairs, PostgreSQL schema, metadata, summary and raw timings. The [public bundle manifest](upgrade/MANIFEST.json) records sizes and SHA-256 values for all curated upgrade evidence.

## Historical baseline from 10–11 November 2026

The files directly in this directory predate the upgrade and are preserved unchanged:

| File | Recorded date | Meaning |
|---|---|---|
| [benchmark.md](benchmark.md) | 10 November 2026 | Large synthetic-data benchmark: 11 table copies and seven equivalent queries; two warm-ups and five measured runs |
| [quality.json](quality.json) | 10 November 2026 | 123 quality checks on the historical large dataset |
| [code-checks.json](code-checks.json) | 10 November 2026 | 12 unit/integration tests from the previous revision |
| [dashboard-tests.json](dashboard-tests.json) | 10 November 2026 | 13 checks for the previous dashboard revision |
| [publication-checks.json](publication-checks.json) | 11 November 2026 | Checks of the earlier curated publication; explicitly states that full generation and benchmark were not repeated for that publication |

The historical large-data run used approximately **5.76 million source rows** after incremental additions, with different engine memory budgets. Its full-load and query timings remain historical context. The 15 November acceptance described above did **not** rerun that scale. Use a new recorded full-scale run before attributing old performance figures to the upgraded implementation.

## Reproducing and interpreting checks

Run the commands from the repository root:

```sh
# Formatting, lint and all offline tests; install both runner and dashboard dependencies first
python scripts/check.py --fail-on-skip

# Full isolated Docker smoke; needs Docker and host Python, not host application dependencies
python scripts/verify.py
```

The verifier creates a new project, selects free local ports, records configured limits and writes a complete runtime evidence directory under `artifacts/verification/<project>/`. It preserves the project's volumes for inspection. See [operations](../operations.md), [recovery boundaries](../runbook.md) and the [verification implementation](../../scripts/verify.py).

Public evidence excludes logs, credentials, absolute host paths, raw quarantine payloads and database volumes. Original source files were copied unchanged where possible. The curated verifier receipt omits per-step log paths, and the report summary omits its runtime CSV directory; each records the original source checksum. Runtime evidence remains outside Git.
