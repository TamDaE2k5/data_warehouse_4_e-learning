SELECT c.category,count(*) AS completed_lessons,
 sum(f.time_spent_seconds) AS learning_seconds,count(DISTINCT u.user_id) AS distinct_learners
 FROM benchmark.fact_lesson_completions f JOIN benchmark.dim_course c ON f.course_sk=c.course_sk
 JOIN benchmark.dim_user u ON f.user_sk=u.user_sk GROUP BY c.category ORDER BY c.category;
