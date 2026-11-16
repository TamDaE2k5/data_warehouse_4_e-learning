WITH revenue AS (
 SELECT course_sk,sum(net_vnd) AS net_vnd FROM benchmark.fact_payments GROUP BY course_sk),
 enrollment AS (SELECT course_sk,count(*) AS enrollments,sum(is_completed) AS completed
 FROM benchmark.fact_enrollments GROUP BY course_sk)
 SELECT c.course_id,c.category,r.net_vnd,e.enrollments,e.completed FROM revenue r
 JOIN enrollment e ON r.course_sk=e.course_sk JOIN benchmark.dim_course c ON r.course_sk=c.course_sk
 ORDER BY c.course_id;
