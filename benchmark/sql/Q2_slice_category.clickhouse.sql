SELECT c.category, sum(f.net_vnd) AS net_vnd, sum(f.refunded) AS refunds
 FROM gold.fact_payments f JOIN gold.dim_course c ON f.course_sk=c.course_sk
 WHERE f.date_sk BETWEEN 20240101 AND 20240331 AND c.difficulty IN ('beginner','intermediate')
 GROUP BY c.category ORDER BY c.category;
