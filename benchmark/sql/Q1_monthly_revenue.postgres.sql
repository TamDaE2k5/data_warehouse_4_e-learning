SELECT d.year, d.month, count(*) AS payments, sum(f.net_vnd) AS net_vnd
 FROM benchmark.fact_payments f JOIN benchmark.dim_date d ON f.date_sk=d.date_sk
 GROUP BY d.year,d.month ORDER BY d.year,d.month;
