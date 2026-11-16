WITH monthly AS (
 SELECT d.year,d.month,sum(f.net_vnd) AS revenue FROM benchmark.fact_payments f
 JOIN benchmark.dim_date d ON f.date_sk=d.date_sk GROUP BY d.year,d.month)
 SELECT year,month,revenue,sum(revenue) OVER (PARTITION BY year ORDER BY month ROWS UNBOUNDED PRECEDING) AS running_revenue
 FROM monthly ORDER BY year,month;
