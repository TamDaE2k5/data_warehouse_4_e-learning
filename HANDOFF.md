# Project handoff

Source: https://github.com/longieoo/online-learning-warehouse

Commit: `3f52ef82b97b71935a061f4a6769a85e256ca98c`

Start with [README.md](README.md). All source, configuration, dashboard labels and repository documentation are in English. Data is generated locally and is synthetic.

## First run

```sh
docker compose up -d --wait postgres clickhouse
docker compose build runner dashboard
docker compose run --rm runner python cli.py all
docker compose --profile demo up -d --wait dashboard
```

Open http://localhost:8501. The default generation has 500,000 enrollments; use the smaller first-run option in the README if needed. Create `.env` from `.env.example` before first startup to customize settings. Bundled passwords are local demo defaults, not production secrets.

## Verification

```sh
python scripts/verify.py
```

This creates a separate test project and preserves its volumes after stopping its own services. Current curated evidence and historical benchmark scope are documented in [docs/verification/README.md](docs/verification/README.md). The November 15 local smoke used 5,000 enrollments; it did not repeat the historical 5.7M-row experiment.

## Package contents

This handoff contains committed source and curated public evidence, plus this note and `PACKAGE_MANIFEST.json`. It excludes Git history, real credentials, local `.env`, database volumes, virtual environments, caches and runtime artifacts. Clone the repository if you need Git history. The manifest records each delivered file's size and SHA-256.
