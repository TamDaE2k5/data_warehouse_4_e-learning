# Contributing

Use a separate Compose project for experiments that modify or delete synthetic data. Never run failure scenarios against a shared source or a published demo dataset.

## Before submitting a change

```sh
python -m pip install -r requirements.lock.txt -r demo/requirements.lock.txt -r requirements-dev.txt
python scripts/check.py
```

The default check runs Ruff and offline unit tests. Database-backed `unittest.TestCase` classes must declare `integration = True`; this makes exclusions explicit rather than silently treating unavailable services as passing tests.

For ETL, schema, SQL, dashboard or container changes, also run the complete fresh-volume check:

```sh
python scripts/verify.py
```

It selects unused localhost ports, creates a unique Compose project and writes logs and a receipt under `artifacts/verification/<project>/`. The verifier stops only its own project and preserves its volumes. `scripts/verify.ps1` remains a Windows compatibility wrapper.

Failure scenarios require an isolated project marker and isolated artifact path in addition to `DW_ALLOW_SCENARIOS=1`. Let the verifier set these; do not copy the override into your regular `.env`.

## Pull requests

Explain the concrete behavior before and after the change. Include the checks run, the data scale and any checks not run. Keep historical benchmark results separate from fresh measurements. A small smoke test does not replace a full-scale benchmark or a production load test.

Use English for repository documentation, interface text and new code comments. Preserve metric definitions, historical attribution and grain when changing presentation. Keep schema and mapping documentation in sync with the implementation.

Do not commit credentials, `.env`, database volumes, real personal data or generated runtime artifacts. Curated verification summaries belong in `docs/verification/` only after their source evidence has been reviewed.
