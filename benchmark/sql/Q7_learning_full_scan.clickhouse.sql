SELECT c.category,count(*) AS completed_lessons,
 sum(f.time_spent_seconds) AS learning_seconds,count(DISTINCT u.user_id) AS distinct_learners
 FROM gold.fact_lesson_completions f JOIN gold.dim_course c ON f.course_sk=c.course_sk
 JOIN gold.dim_user u ON f.user_sk=u.user_sk GROUP BY c.category ORDER BY c.category;
