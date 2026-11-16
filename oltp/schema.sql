CREATE SCHEMA IF NOT EXISTS oltp;
CREATE TABLE IF NOT EXISTS oltp.users (
 user_id BIGINT PRIMARY KEY, full_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
 city TEXT NOT NULL, country CHAR(2) NOT NULL, created_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS oltp.user_history (
 history_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES oltp.users,
 full_name TEXT NOT NULL, email TEXT NOT NULL, city TEXT NOT NULL, country CHAR(2) NOT NULL,
 valid_from TIMESTAMP NOT NULL, valid_to TIMESTAMP NOT NULL,
 UNIQUE(user_id, valid_from), CHECK(valid_to > valid_from)
);
CREATE TABLE IF NOT EXISTS oltp.instructors (
 instructor_id BIGINT PRIMARY KEY, full_name TEXT NOT NULL, expertise TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS oltp.courses (
 course_id BIGINT PRIMARY KEY, instructor_id BIGINT NOT NULL REFERENCES oltp.instructors,
 title TEXT NOT NULL, category TEXT NOT NULL, difficulty TEXT NOT NULL,
 price_vnd BIGINT NOT NULL CHECK(price_vnd >= 0)
);
CREATE TABLE IF NOT EXISTS oltp.lessons (
 lesson_id BIGINT PRIMARY KEY, course_id BIGINT NOT NULL REFERENCES oltp.courses,
 title TEXT NOT NULL, position SMALLINT NOT NULL CHECK(position BETWEEN 1 AND 10),
 UNIQUE(course_id, position)
);
CREATE TABLE IF NOT EXISTS oltp.quizzes (
 quiz_id BIGINT PRIMARY KEY, course_id BIGINT NOT NULL REFERENCES oltp.courses,
 title TEXT NOT NULL, total_questions SMALLINT NOT NULL CHECK(total_questions > 0)
);
CREATE TABLE IF NOT EXISTS oltp.payment_methods (
 method_id BIGINT PRIMARY KEY, method_name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS oltp.enrollments (
 enrollment_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES oltp.users,
 course_id BIGINT NOT NULL REFERENCES oltp.courses, enrolled_at TIMESTAMP NOT NULL,
 completed_at TIMESTAMP, lessons_completed SMALLINT NOT NULL CHECK(lessons_completed BETWEEN 0 AND 10),
 UNIQUE(user_id, course_id), CHECK(completed_at IS NULL OR completed_at >= enrolled_at),
 CHECK((completed_at IS NOT NULL) = (lessons_completed = 10))
);
CREATE TABLE IF NOT EXISTS oltp.payments (
 payment_id BIGINT PRIMARY KEY, enrollment_id BIGINT NOT NULL UNIQUE REFERENCES oltp.enrollments,
 user_id BIGINT NOT NULL REFERENCES oltp.users, course_id BIGINT NOT NULL REFERENCES oltp.courses,
 method_id BIGINT NOT NULL REFERENCES oltp.payment_methods, transaction_id TEXT NOT NULL UNIQUE,
 paid_at TIMESTAMP NOT NULL, original_vnd BIGINT NOT NULL, discount_vnd BIGINT NOT NULL,
 charged_vnd BIGINT NOT NULL, refunded SMALLINT NOT NULL CHECK(refunded IN (0,1)),
 CHECK(original_vnd >= 0 AND discount_vnd BETWEEN 0 AND original_vnd),
 CHECK(charged_vnd = original_vnd - discount_vnd)
);
CREATE TABLE IF NOT EXISTS oltp.lesson_completions (
 completion_id BIGINT PRIMARY KEY, enrollment_id BIGINT NOT NULL REFERENCES oltp.enrollments,
 user_id BIGINT NOT NULL REFERENCES oltp.users, course_id BIGINT NOT NULL REFERENCES oltp.courses,
 lesson_id BIGINT NOT NULL REFERENCES oltp.lessons, completed_at TIMESTAMP NOT NULL,
 time_spent_seconds INTEGER NOT NULL CHECK(time_spent_seconds > 0),
 UNIQUE(enrollment_id, lesson_id)
);
CREATE TABLE IF NOT EXISTS oltp.quiz_attempts (
 attempt_id BIGINT PRIMARY KEY, enrollment_id BIGINT NOT NULL REFERENCES oltp.enrollments,
 user_id BIGINT NOT NULL REFERENCES oltp.users, course_id BIGINT NOT NULL REFERENCES oltp.courses,
 quiz_id BIGINT NOT NULL REFERENCES oltp.quizzes, attempt_number SMALLINT NOT NULL,
 attempted_at TIMESTAMP NOT NULL, correct_count SMALLINT NOT NULL CHECK(correct_count BETWEEN 0 AND 20),
 total_questions SMALLINT NOT NULL CHECK(total_questions = 20),
 time_spent_seconds INTEGER NOT NULL CHECK(time_spent_seconds > 0),
 UNIQUE(enrollment_id, quiz_id, attempt_number)
);
CREATE INDEX IF NOT EXISTS enrollments_time_idx ON oltp.enrollments(enrolled_at);
CREATE INDEX IF NOT EXISTS payments_time_idx ON oltp.payments(paid_at);
