CREATE DATABASE IF NOT EXISTS gold;
CREATE TABLE IF NOT EXISTS gold.dim_date (
 date_sk Int64, full_date Date, year Int64, quarter Int64, month Int64, day Int64
) ENGINE = MergeTree ORDER BY date_sk;
CREATE TABLE IF NOT EXISTS gold.dim_user (
 user_sk Int64, user_id Int64, full_name String, email String, city LowCardinality(String),
 country LowCardinality(String), valid_from DateTime('UTC'), valid_to DateTime('UTC'), is_current Int64
) ENGINE = MergeTree ORDER BY (user_id, valid_from);
CREATE TABLE IF NOT EXISTS gold.dim_course (
 course_sk Int64, course_id Int64, title String, category LowCardinality(String),
 difficulty LowCardinality(String), instructor_id Int64, price_vnd Int64
) ENGINE = MergeTree ORDER BY course_sk;
CREATE TABLE IF NOT EXISTS gold.dim_instructor (
 instructor_sk Int64, instructor_id Int64, full_name String, expertise LowCardinality(String)
) ENGINE = MergeTree ORDER BY instructor_sk;
CREATE TABLE IF NOT EXISTS gold.dim_lesson (
 lesson_sk Int64, lesson_id Int64, course_id Int64, title String, position Int64
) ENGINE = MergeTree ORDER BY lesson_sk;
CREATE TABLE IF NOT EXISTS gold.dim_quiz (
 quiz_sk Int64, quiz_id Int64, course_id Int64, title String, total_questions Int64
) ENGINE = MergeTree ORDER BY quiz_sk;
CREATE TABLE IF NOT EXISTS gold.dim_payment_method (
 method_sk Int64, method_id Int64, method_name LowCardinality(String)
) ENGINE = MergeTree ORDER BY method_sk;
CREATE TABLE IF NOT EXISTS gold.fact_enrollments (
 enrollment_id Int64, user_sk Int64, course_sk Int64, instructor_sk Int64,
 enrolled_date_sk Int64, completed_date_sk Int64, enrolled_at DateTime('UTC'),
 completed_at Nullable(DateTime('UTC')), lessons_completed Int64, is_completed Int64, updated_at DateTime64(6, 'UTC')
) ENGINE = ReplacingMergeTree(updated_at) PARTITION BY toYYYYMM(enrolled_at)
ORDER BY enrollment_id;
CREATE TABLE IF NOT EXISTS gold.fact_payments (
 payment_id Int64, enrollment_id Int64, transaction_id String, user_sk Int64,
 course_sk Int64, instructor_sk Int64, method_sk Int64, date_sk Int64,
 paid_at DateTime('UTC'), original_vnd Int64, discount_vnd Int64, charged_vnd Int64,
 refunded Int64, net_vnd Int64
) ENGINE = MergeTree PARTITION BY toYYYYMM(paid_at)
ORDER BY (date_sk, course_sk, user_sk, payment_id);
CREATE TABLE IF NOT EXISTS gold.fact_lesson_completions (
 completion_id Int64, enrollment_id Int64, user_sk Int64, course_sk Int64,
 lesson_sk Int64, date_sk Int64, completed_at DateTime('UTC'), time_spent_seconds Int64
) ENGINE = MergeTree PARTITION BY toYYYYMM(completed_at)
ORDER BY (date_sk, course_sk, user_sk, completion_id);
CREATE TABLE IF NOT EXISTS gold.fact_quiz_attempts (
 attempt_id Int64, enrollment_id Int64, user_sk Int64, course_sk Int64,
 quiz_sk Int64, date_sk Int64, attempted_at DateTime('UTC'), attempt_number Int64,
 correct_count Int64, total_questions Int64, time_spent_seconds Int64, is_passed Int64
) ENGINE = MergeTree PARTITION BY toYYYYMM(attempted_at)
ORDER BY (date_sk, course_sk, user_sk, attempt_id);

