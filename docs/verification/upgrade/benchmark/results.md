# Benchmark — measured results

Pipeline: `3e69663b45de4fc5883192e87ad48ac6`. Benchmark: `e134f4f34d004b99b6a1cbd6d5c8daba`.
One parity query, 2 warm-ups and 3 measured runs per engine/query.

Same Gold rows and columns; full row hashes and all query outputs matched. Timings include client execute + fetch.

| Query | PostgreSQL median ms | ClickHouse median ms | PG / CH |
|---|---:|---:|---:|
| Q1_monthly_revenue | 3.292 | 12.878 | 0.255669x |
| Q2_slice_category | 0.858 | 8.897 | 0.096405x |
| Q3_four_dimensions | 4.562 | 10.947 | 0.41678x |
| Q4_window_running_total | 2.089 | 9.645 | 0.216578x |
| Q5_cube | 3.496 | 12.666 | 0.276013x |
| Q6_drill_across | 4.181 | 12.918 | 0.323657x |
| Q7_learning_full_scan | 36.511 | 13.184 | 2.769249x |

## Limitations

- Single Docker host; no cold-cache control
- Equal CPU quotas do not isolate engine CPU scheduling on a shared host
- Network/client latency included
- CPU, query peak memory and IO are not measured
- Synthetic data; cannot generalize to production
- Memory budgets differ; not an equal-memory engine isolation test
