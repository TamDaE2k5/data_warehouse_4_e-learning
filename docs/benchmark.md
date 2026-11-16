# Benchmark methodology

The comparison answers a narrow question: how do PostgreSQL and ClickHouse execute seven analytical queries over the same Gold model on one Docker host? PostgreSQL is a relational analytical baseline (ROLAP-style), and ClickHouse is a column-oriented analytical engine. The project does not build a separate MOLAP cube.

## Preconditions and correctness

The caller acquires the project writer lock. The benchmark verifies live Gold fingerprints against the committed publication before copying data, so manually edited same-count data cannot inherit an old pipeline identity.

Exactly eleven fact/dimension tables are mirrored with identical rows and columns. PostgreSQL receives primary keys and selected fact-key indexes, followed by `ANALYZE`. Full-row SHA-256 is calculated in key order with UTC-normalized timestamps. The seven query outputs are compared as multisets: duplicate rows count, incidental result order does not.

Every measured result is checked again against its untimed baseline. A mismatch fails the benchmark instead of producing a successful timing table.

## Timing protocol

There is one untimed parity query per engine and query, then the configured number of warm-ups and at least three measured runs. Default settings are two warm-ups and five measurements. Engines alternate first position in successive measured rounds; queries run serially.

Timing uses the client wall clock from execution through result fetching. It includes network/client overhead. ClickHouse query cache is disabled, but filesystem and database caches are not flushed. Even `--warmups 0` is not a cold-cache test, because parity has already read the data.

`runs.csv` preserves the measured floating-point millisecond samples without display rounding. Summary medians, means, sample standard deviations, minima, maxima and PG/CH ratios can be reproduced from those samples. Spread is observational; it is not a statistical confidence interval. Do not collapse all seven query-specific ratios into one universal speedup claim.

## Resources

Metadata records the CPU quota and memory-limit strings forwarded by Compose, plus normalized byte limits and whether the engine limits are equal. These are configuration, not observed CPU consumption or query peak RAM. Python ETL RSS is another measure and must not be substituted for database query RAM.

To compare equal memory budgets on a fresh project, configure both limits before starting services, for example:

```dotenv
DW_CPUS=2
PG_MEMORY_LIMIT=3g
CH_MEMORY_LIMIT=3g
```

Recreate affected containers when changing their limits; do not compare a new environment variable with containers still using old limits. Equal quotas on a shared host do not isolate engine scheduling, cache or disk effects. The existing defaults retain PostgreSQL 2 GiB and ClickHouse 3 GiB, so default results remain an unequal-memory comparison.

## Storage boundaries

PostgreSQL uses `pg_total_relation_size` for each of the eleven mirrored tables, including their indexes. ClickHouse sums active parts for exactly those tables; uncompressed column bytes are recorded separately. Auxiliary Gold summaries are reported separately and excluded from the core comparison.

These measurements are not whole-container usage and do not define a universal compression ratio. Copy preparation time is recorded separately from query latency. A `--reuse-mirror` run still checks data parity and labels that the copy was reused.

## Publication and provenance

Each successful run creates `artifacts/benchmark/history/<benchmark_run>/` with metadata, raw and summary results, executed SQL and generated mirror DDL when copied. After the complete set is written, `latest.json` advances atomically to it and lists SHA-256 hashes. Consumers of multiple files should follow this pointer and verify the hashes.

The convenient top-level CSV/Markdown copies are replaced individually. They are not a multi-file transaction. `metadata.json` tracks the latest attempt, so a failed attempt can coexist with an older successful `latest.json` pointer. This distinction preserves useful historical results without presenting stale success as the latest attempt.

## What this does not establish

The experiment does not measure query CPU, engine peak memory, I/O, concurrent users, cold-cache performance, multiple hosts or production availability. Data is synthetic and fixed to the modeled learning scenario. Historical results in [verification](verification/README.md) retain their original dates and protocol; the new explicit parity query, storage boundary and integrity checks are not retroactively applied to them.
