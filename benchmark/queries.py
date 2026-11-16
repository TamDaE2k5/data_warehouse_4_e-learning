"""Portable queries over identical Gold models. No pre-aggregated shortcuts."""

QUERIES = {
    "Q1_monthly_revenue": """SELECT d.year, d.month, count(*) AS payments, sum(f.net_vnd) AS net_vnd
 FROM {db}.fact_payments f JOIN {db}.dim_date d ON f.date_sk=d.date_sk
 GROUP BY d.year,d.month ORDER BY d.year,d.month""",
    "Q2_slice_category": """SELECT c.category, sum(f.net_vnd) AS net_vnd, sum(f.refunded) AS refunds
 FROM {db}.fact_payments f JOIN {db}.dim_course c ON f.course_sk=c.course_sk
 WHERE f.date_sk BETWEEN 20240101 AND 20240331 AND c.difficulty IN ('beginner','intermediate')
 GROUP BY c.category ORDER BY c.category""",
    "Q3_four_dimensions": """SELECT d.year,c.category,i.expertise,m.method_name,
 count(*) AS transactions,sum(f.net_vnd) AS net_vnd
 FROM {db}.fact_payments f JOIN {db}.dim_date d ON f.date_sk=d.date_sk
 JOIN {db}.dim_course c ON f.course_sk=c.course_sk
 JOIN {db}.dim_instructor i ON f.instructor_sk=i.instructor_sk
 JOIN {db}.dim_payment_method m ON f.method_sk=m.method_sk
 GROUP BY d.year,c.category,i.expertise,m.method_name ORDER BY d.year,c.category,i.expertise,m.method_name""",
    "Q4_window_running_total": """WITH monthly AS (
 SELECT d.year,d.month,sum(f.net_vnd) AS revenue FROM {db}.fact_payments f
 JOIN {db}.dim_date d ON f.date_sk=d.date_sk GROUP BY d.year,d.month)
 SELECT year,month,revenue,sum(revenue) OVER (PARTITION BY year ORDER BY month ROWS UNBOUNDED PRECEDING) AS running_revenue
 FROM monthly ORDER BY year,month""",
    "Q5_cube": """SELECT d.year,CAST(c.category AS TEXT) AS category,sum(f.net_vnd) AS net_vnd,count(*) AS transactions
 FROM {db}.fact_payments f JOIN {db}.dim_date d ON f.date_sk=d.date_sk
 JOIN {db}.dim_course c ON f.course_sk=c.course_sk
 GROUP BY CUBE(d.year,CAST(c.category AS TEXT)) ORDER BY d.year,category""",
    "Q6_drill_across": """WITH revenue AS (
 SELECT course_sk,sum(net_vnd) AS net_vnd FROM {db}.fact_payments GROUP BY course_sk),
 enrollment AS (SELECT course_sk,count(*) AS enrollments,sum(is_completed) AS completed
 FROM {db}.fact_enrollments GROUP BY course_sk)
 SELECT c.course_id,c.category,r.net_vnd,e.enrollments,e.completed FROM revenue r
 JOIN enrollment e ON r.course_sk=e.course_sk JOIN {db}.dim_course c ON r.course_sk=c.course_sk
 ORDER BY c.course_id""",
    "Q7_learning_full_scan": """SELECT c.category,count(*) AS completed_lessons,
 sum(f.time_spent_seconds) AS learning_seconds,count(DISTINCT u.user_id) AS distinct_learners
 FROM {db}.fact_lesson_completions f JOIN {db}.dim_course c ON f.course_sk=c.course_sk
 JOIN {db}.dim_user u ON f.user_sk=u.user_sk GROUP BY c.category ORDER BY c.category""",
}
