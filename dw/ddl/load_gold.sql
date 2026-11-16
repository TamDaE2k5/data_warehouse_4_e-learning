INSERT INTO gold.dim_date
SELECT toYYYYMMDD(d), d, toYear(d), toQuarter(d), toMonth(d), toDayOfMonth(d)
FROM (SELECT toDate('2022-01-01') + toIntervalDay(number) AS d FROM numbers(1096));
INSERT INTO gold.dim_date VALUES (0, '1970-01-01', 0, 0, 0, 0);
INSERT INTO gold.dim_user
SELECT history_id + 10000000, user_id, full_name, email, city, country, valid_from, valid_to,
 toInt64(valid_to = toDateTime('2100-01-01 00:00:00', 'UTC')) FROM silver.user_history;
INSERT INTO gold.dim_course
SELECT course_id + 1000000, course_id, title, category, difficulty, instructor_id, price_vnd FROM silver.courses;
INSERT INTO gold.dim_instructor
SELECT instructor_id + 2000000, instructor_id, full_name, expertise FROM silver.instructors;
INSERT INTO gold.dim_lesson
SELECT lesson_id + 3000000, lesson_id, course_id, title, position FROM silver.lessons;
INSERT INTO gold.dim_quiz
SELECT quiz_id + 4000000, quiz_id, course_id, title, total_questions FROM silver.quizzes;
INSERT INTO gold.dim_payment_method
SELECT method_id + 5000000, method_id, method_name FROM silver.payment_methods;
INSERT INTO gold.fact_enrollments
SELECT e.enrollment_id, u.user_sk, c.course_sk, i.instructor_sk,
 toYYYYMMDD(e.enrolled_at), ifNull(toYYYYMMDD(e.completed_at), 0),
 e.enrolled_at, e.completed_at, e.lessons_completed, toInt64(e.completed_at IS NOT NULL), e.updated_at
FROM silver.enrollments e
INNER JOIN gold.dim_course c ON e.course_id = c.course_id
INNER JOIN gold.dim_instructor i ON c.instructor_id = i.instructor_id
ASOF LEFT JOIN gold.dim_user u ON e.user_id = u.user_id AND e.enrolled_at >= u.valid_from;
INSERT INTO gold.fact_payments
SELECT p.payment_id, p.enrollment_id, p.transaction_id, u.user_sk, c.course_sk, i.instructor_sk,
 m.method_sk, toYYYYMMDD(p.paid_at), p.paid_at, p.original_vnd, p.discount_vnd,
 p.charged_vnd, p.refunded, p.charged_vnd * (1-p.refunded)
FROM silver.payments p
INNER JOIN gold.dim_course c ON p.course_id = c.course_id
INNER JOIN gold.dim_instructor i ON c.instructor_id = i.instructor_id
INNER JOIN gold.dim_payment_method m ON p.method_id = m.method_id
ASOF LEFT JOIN gold.dim_user u ON p.user_id = u.user_id AND p.paid_at >= u.valid_from;
INSERT INTO gold.fact_lesson_completions
SELECT l.completion_id, l.enrollment_id, u.user_sk, c.course_sk, d.lesson_sk,
 toYYYYMMDD(l.completed_at), l.completed_at, l.time_spent_seconds
FROM silver.lesson_completions l
INNER JOIN gold.dim_course c ON l.course_id = c.course_id
INNER JOIN gold.dim_lesson d ON l.lesson_id = d.lesson_id
ASOF LEFT JOIN gold.dim_user u ON l.user_id = u.user_id AND l.completed_at >= u.valid_from;
INSERT INTO gold.fact_quiz_attempts
SELECT q.attempt_id, q.enrollment_id, u.user_sk, c.course_sk, d.quiz_sk,
 toYYYYMMDD(q.attempted_at), q.attempted_at, q.attempt_number, q.correct_count,
 q.total_questions, q.time_spent_seconds, toInt64(q.correct_count * 100 >= q.total_questions * 70)
FROM silver.quiz_attempts q
INNER JOIN gold.dim_course c ON q.course_id = c.course_id
INNER JOIN gold.dim_quiz d ON q.quiz_id = d.quiz_id
ASOF LEFT JOIN gold.dim_user u ON q.user_id = u.user_id AND q.attempted_at >= u.valid_from;

