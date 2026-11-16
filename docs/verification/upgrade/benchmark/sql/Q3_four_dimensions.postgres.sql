SELECT d.year,c.category,i.expertise,m.method_name,
 count(*) AS transactions,sum(f.net_vnd) AS net_vnd
 FROM benchmark.fact_payments f JOIN benchmark.dim_date d ON f.date_sk=d.date_sk
 JOIN benchmark.dim_course c ON f.course_sk=c.course_sk
 JOIN benchmark.dim_instructor i ON f.instructor_sk=i.instructor_sk
 JOIN benchmark.dim_payment_method m ON f.method_sk=m.method_sk
 GROUP BY d.year,c.category,i.expertise,m.method_name ORDER BY d.year,c.category,i.expertise,m.method_name;
