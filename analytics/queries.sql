-- name: R01_revenue_rollup
SELECT d.year, d.quarter, d.month, sum(f.net_vnd) AS net_vnd,
       sum(f.charged_vnd) AS charged_vnd, sum(f.refunded) AS refunded_transactions
FROM gold.fact_payments f JOIN gold.dim_date d ON f.date_sk=d.date_sk
GROUP BY ROLLUP(d.year,d.quarter,d.month)
ORDER BY d.year,d.quarter,d.month;

-- name: R02_completion_rate
SELECT c.category,c.difficulty,count(*) AS enrollments,sum(e.is_completed) AS completed,
       round(100.0*sum(e.is_completed)/count(*),2) AS completion_pct
FROM gold.fact_enrollments e JOIN gold.dim_course c ON e.course_sk=c.course_sk
GROUP BY c.category,c.difficulty ORDER BY c.category,c.difficulty;

-- name: R03_quiz_performance
SELECT c.category,count(*) AS attempts,sum(q.correct_count) AS correct_answers,
       sum(q.total_questions) AS questions,
       round(100.0*sum(q.correct_count)/sum(q.total_questions),2) AS weighted_score_pct,
       round(100.0*sum(q.is_passed)/count(*),2) AS pass_pct
FROM gold.fact_quiz_attempts q JOIN gold.dim_course c ON q.course_sk=c.course_sk
GROUP BY c.category ORDER BY c.category;

-- name: R04_role_playing_dates
SELECT ed.year AS enrollment_year,cd.year AS completion_year,count(*) AS completed_enrollments,
       avg(dateDiff('day',e.enrolled_at,e.completed_at)) AS average_days_to_complete
FROM gold.fact_enrollments e
JOIN gold.dim_date ed ON e.enrolled_date_sk=ed.date_sk
JOIN gold.dim_date cd ON e.completed_date_sk=cd.date_sk
WHERE e.is_completed=1 GROUP BY ed.year,cd.year ORDER BY ed.year,cd.year;

-- name: R05_historical_city
SELECT d.year,u.city,count(*) AS enrollments,sum(e.is_completed) AS completed
FROM gold.fact_enrollments e JOIN gold.dim_date d ON e.enrolled_date_sk=d.date_sk
JOIN gold.dim_user u ON e.user_sk=u.user_sk
GROUP BY d.year,u.city ORDER BY d.year,u.city;

-- name: R06_top_courses_rank
WITH revenue AS (
 SELECT d.year,d.quarter,c.course_id,c.title,sum(f.net_vnd) AS net_vnd
 FROM gold.fact_payments f JOIN gold.dim_date d ON f.date_sk=d.date_sk
 JOIN gold.dim_course c ON f.course_sk=c.course_sk
 GROUP BY d.year,d.quarter,c.course_id,c.title
), ranked AS (
 SELECT *,row_number() OVER(PARTITION BY year,quarter ORDER BY net_vnd DESC,course_id) AS rank
 FROM revenue
)
SELECT * FROM ranked WHERE rank<=10 ORDER BY year,quarter,rank;

-- name: R07_revenue_enrollment_drill_across
WITH revenue AS (
 SELECT course_sk,date_sk,sum(net_vnd) AS net_vnd FROM gold.fact_payments GROUP BY course_sk,date_sk
), enrollment AS (
 SELECT course_sk,enrolled_date_sk AS date_sk,count(*) AS enrollments
 FROM gold.fact_enrollments GROUP BY course_sk,enrolled_date_sk
), keys AS (
 SELECT course_sk,date_sk FROM revenue UNION DISTINCT SELECT course_sk,date_sk FROM enrollment
)
SELECT d.year,d.month,c.category,sum(coalesce(r.net_vnd,0)) AS net_vnd,
       sum(coalesce(e.enrollments,0)) AS enrollments
FROM keys k LEFT JOIN revenue r ON k.course_sk=r.course_sk AND k.date_sk=r.date_sk
LEFT JOIN enrollment e ON k.course_sk=e.course_sk AND k.date_sk=e.date_sk
JOIN gold.dim_date d ON k.date_sk=d.date_sk JOIN gold.dim_course c ON k.course_sk=c.course_sk
GROUP BY d.year,d.month,c.category ORDER BY d.year,d.month,c.category;

-- name: R08_slice_dice
SELECT d.year,d.quarter,c.category,c.difficulty,sum(p.net_vnd) AS net_vnd
FROM gold.fact_payments p JOIN gold.dim_date d ON p.date_sk=d.date_sk
JOIN gold.dim_course c ON p.course_sk=c.course_sk
WHERE d.year=2024 AND d.quarter IN (1,2) AND c.category IN ('Data','Programming')
GROUP BY d.year,d.quarter,c.category,c.difficulty ORDER BY d.quarter,c.category,c.difficulty;

-- name: R09_cube
SELECT d.year,CAST(c.category AS String) AS category,CAST(m.method_name AS String) AS method_name,sum(p.net_vnd) AS net_vnd
FROM gold.fact_payments p JOIN gold.dim_date d ON p.date_sk=d.date_sk
JOIN gold.dim_course c ON p.course_sk=c.course_sk
JOIN gold.dim_payment_method m ON p.method_sk=m.method_sk
GROUP BY CUBE(d.year,CAST(c.category AS String),CAST(m.method_name AS String)) ORDER BY d.year,category,method_name;

-- name: R10_learning_time
SELECT c.category,l.position,count(*) AS completions,sum(f.time_spent_seconds) AS seconds,
       round(avg(f.time_spent_seconds),2) AS average_seconds
FROM gold.fact_lesson_completions f JOIN gold.dim_lesson l ON f.lesson_sk=l.lesson_sk
JOIN gold.dim_course c ON f.course_sk=c.course_sk
GROUP BY c.category,l.position ORDER BY c.category,l.position;
