# Runbook

## Start and inspect

Run commands from the repository root with Docker running Linux containers. Copy `.env.example` to `.env` before creating volumes if you want different ports, passwords or resource limits. Updating environment passwords after a database exists also requires updating its database roles; editing `.env` alone does not rotate existing credentials.

```sh
docker compose up -d --wait postgres clickhouse
docker compose build runner dashboard
docker compose run --rm runner python cli.py all
docker compose --profile demo up -d --wait dashboard
```

The default source has 500,000 enrollments and more than 5.7 million rows. `all` initializes, generates only if empty, runs full ETL, exports reports and benchmarks. It takes longer than an ETL-only timing because it includes all these steps. Ports default to PostgreSQL 55432, ClickHouse HTTP 58123 and dashboard 8501, bound only to `127.0.0.1`.

```sh
docker compose ps
docker compose logs --tail 80 postgres clickhouse dashboard
docker compose run --rm runner python cli.py doctor
```

`doctor` reads connectivity, role boundaries, publication state and open quarantine. It does not fix data. `setup` initializes database contracts; do not run it concurrently with ingestion or source writes. Fresh volumes and existing volumes are different cases: an exported JSON file alone does not make new databases ready.

## Normal update cycle

```sh
docker compose run --rm runner python -m demo.seed_incremental
docker compose run --rm runner python cli.py pipeline --mode incremental
docker compose run --rm runner python cli.py reports
```

The first command deliberately inserts synthetic activity. Omit it when your source already contains the changes you want to process. Empty incremental runs scan Gold fingerprints before reuse, so they perform integrity work even when extraction finds no changes. A long open source transaction can defer newer committed changes; check source transaction age before assuming ingestion has stalled.

Open the dashboard and use **Refresh data** to load the latest committed publication. Dashboard requests read a coherent snapshot under a shared lock. Cached results are tied to the publication run. Pipeline execution from the browser is disabled by default; use the CLI for operational changes.

## Failed ingestion or publication

Inspect `artifacts/pipeline.json`, the matching file under `artifacts/runs`, and runner logs. The last attempt may be failed while an earlier committed Gold remains available. Do not manually advance checkpoints or delete pending changes/revision state.

```sh
docker compose run --rm runner python cli.py pipeline --mode incremental
```

Retry performs pending-publication recovery before new ingestion. If UUIDs do not match the recovery plan, preserve `gold_build` and `staging.pipeline_runs` for investigation. Do not drop candidate tables to suppress the error. SQL clients outside the project must avoid partial publication or cooperate with the project lock.

After a required source-column/type change, update schema contracts and mapping and run a full load. Additive fields outside the contract are ignored. A valid source correction resolves the corresponding rejection; an invalid update keeps the preceding clean Silver row. Failures in cross-table or aggregate checks block candidate publication.

## Benchmark

```sh
docker compose run --rm runner python cli.py benchmark --runs 5 --warmups 2
```

This creates/replaces only the comparison mirror, verifies complete data parity and measures queries serially. It is not a source write. `--reuse-mirror` avoids the copy only when the existing mirror passes parity. Even `--warmups 0` executes an untimed parity query, so it is not a cold-cache experiment. See [benchmark methodology](benchmark.md).

`artifacts/benchmark/metadata.json` describes the latest attempt, including failure. `latest.json` points only to a complete successful bundle in `history/<benchmark_run>`. Use that pointer and its SHA-256 list when consuming multiple result files. Compatibility CSV/Markdown paths remain convenient individual copies; they are not a transaction across all files.

## Verify safely

```sh
python scripts/verify.py
```

Only Python's standard library and Docker are needed on the host. Verification allocates a unique Compose project, unused loopback ports and isolated artifacts. It refuses to reuse existing project resources. The suite initializes 5,000 enrollments, runs ETL/reports/benchmark, offline and live integration checks, deliberate fault scenarios and dashboard reconciliation. It then stops only its own project and preserves its volumes and logs. `scripts/verify.ps1` is a compatibility wrapper on Windows.

Deliberate failure scenarios require the explicit test-project marker and matching artifact path, as well as the opt-in flag. They reject an ordinary main project. Never repoint their connection variables to shared data. A small fresh-volume smoke proves the tested scenarios, not full-scale throughput or production availability.

## Stop, retain and restore

```sh
docker compose stop
docker compose up -d --wait postgres clickhouse
docker compose --profile demo up -d --wait dashboard
```

These commands preserve volumes. `down -v` destroys project data and is not part of normal operation. Keep both source and staging/control backups aligned with the corresponding Gold state. Back up PostgreSQL databases with `pg_dump` and Gold through supported ClickHouse backups or consistent stopped-volume snapshots. This repository does not yet qualify a full backup restoration process; do not treat crash-recovery tests as backup-restore evidence.

## Evidence and known boundaries

Versioned summaries live in [verification](verification/README.md). Runtime artifacts, caches, credentials and database volumes stay outside Git. Historical large-data measurements retain their original dates and resource budgets; current upgrade smoke evidence has its own scope and timestamps. Local-host credentials and shared ClickHouse roles are intended for a learning demo, not public network deployment.
