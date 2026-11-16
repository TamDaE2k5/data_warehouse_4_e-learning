# Benchmark — measured results

Pipeline: `3674992fa2fb4b738fe0fa0f4d1957e7`. 2 warm-ups + 5 measured runs per engine/query.

Same Gold rows and columns; full row hashes and all query outputs matched. Timings include client execute + fetch.

| Query | PostgreSQL median ms | ClickHouse median ms | PG / CH |
|---|---:|---:|---:|
| Q1_monthly_revenue | 56.712 | 15.321 | 3.702x |
| Q2_slice_category | 12.355 | 9.926 | 1.245x |
| Q3_four_dimensions | 141.474 | 56.871 | 2.488x |
| Q4_window_running_total | 57.772 | 15.503 | 3.726x |
| Q5_cube | 281.256 | 24.086 | 11.677x |
| Q6_drill_across | 80.165 | 18.045 | 4.442x |
| Q7_learning_full_scan | 7111.603 | 223.077 | 31.88x |

## Limitations

- Single host Docker/WSL; no cold-cache control
- Memory budgets differ; not an equal-memory engine isolation test
- Network/client latency included
- CPU, query peak memory and IO are not measured
- Synthetic data; cannot generalize to production
