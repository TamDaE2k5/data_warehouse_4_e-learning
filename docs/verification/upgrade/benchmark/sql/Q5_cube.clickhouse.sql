SELECT d.year,CAST(c.category AS TEXT) AS category,sum(f.net_vnd) AS net_vnd,count(*) AS transactions
 FROM gold.fact_payments f JOIN gold.dim_date d ON f.date_sk=d.date_sk
 JOIN gold.dim_course c ON f.course_sk=c.course_sk
 GROUP BY CUBE(d.year,CAST(c.category AS TEXT)) ORDER BY d.year,category;
