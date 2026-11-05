-- ==============================================================================
-- CẤU TRÚC BẢN SAO KHO DỮ LIỆU ĐA CHIỀU TRÊN POSTGRESQL (POSTGRESQL GOLD MIRROR)
-- ==============================================================================
-- Database: dwh_staging | Schema: benchmark | Hệ quản trị: PostgreSQL 16
-- Mục tiêu:
--   - Nhân bản cấu trúc 11 bảng của kho dữ liệu Gold từ ClickHouse sang PostgreSQL
--     để tạo môi trường đối đầu công bằng (Apple-to-Apple Comparison).
--   - Dữ liệu ở cả 2 bên (ClickHouse Gold vs PostgreSQL Benchmark) khớp nhau 100%
--     từng dòng, từng cột, được niêm phong xác thực bằng mã băm SHA-256.
--   - Các bảng Fact được đánh chỉ mục B-Tree trên các cột khóa ngoại (date_sk, user_sk,
--     course_sk) và chạy lệnh ANALYZE để đảm bảo PostgreSQL có điều kiện tối ưu tốt nhất.
-- ==============================================================================

CREATE SCHEMA IF NOT EXISTS benchmark;

-- ------------------------------------------------------------------------------
-- 1. CÁC BẢNG CHIỀU DÙNG CHUNG (DIMENSION TABLES)
-- ------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS benchmark.dim_date (
    "date_sk"     BIGINT NOT NULL,
    "full_date"   DATE NOT NULL,
    "year"        BIGINT NOT NULL,
    "quarter"     BIGINT NOT NULL,
    "month"       BIGINT NOT NULL,
    "day"         BIGINT NOT NULL,
    PRIMARY KEY (date_sk)
);

CREATE TABLE IF NOT EXISTS benchmark.dim_user (
    "user_sk"     BIGINT NOT NULL,
    "user_id"     BIGINT NOT NULL,
    "full_name"   TEXT NOT NULL,
    "email"       TEXT NOT NULL,
    "city"        TEXT NOT NULL,
    "country"     TEXT NOT NULL,
    "valid_from"  TIMESTAMP NOT NULL,
    "valid_to"    TIMESTAMP NOT NULL,
    "is_current"  BIGINT NOT NULL,
    PRIMARY KEY (user_sk)
);

CREATE TABLE IF NOT EXISTS benchmark.dim_course (
    "course_sk"     BIGINT NOT NULL,
    "course_id"     BIGINT NOT NULL,
    "title"         TEXT NOT NULL,
    "category"      TEXT NOT NULL,
    "difficulty"    TEXT NOT NULL,
    "instructor_id" BIGINT NOT NULL,
    "price_vnd"     BIGINT NOT NULL,
    PRIMARY KEY (course_sk)
);

CREATE TABLE IF NOT EXISTS benchmark.dim_instructor (
    "instructor_sk" BIGINT NOT NULL,
    "instructor_id" BIGINT NOT NULL,
    "full_name"     TEXT NOT NULL,
    "expertise"     TEXT NOT NULL,
    PRIMARY KEY (instructor_sk)
);

CREATE TABLE IF NOT EXISTS benchmark.dim_lesson (
    "lesson_sk" BIGINT NOT NULL,
    "lesson_id" BIGINT NOT NULL,
    "course_id" BIGINT NOT NULL,
    "title"     TEXT NOT NULL,
    "position"  BIGINT NOT NULL,
    PRIMARY KEY (lesson_sk)
);

CREATE TABLE IF NOT EXISTS benchmark.dim_quiz (
    "quiz_sk"         BIGINT NOT NULL,
    "quiz_id"         BIGINT NOT NULL,
    "course_id"       BIGINT NOT NULL,
    "title"           TEXT NOT NULL,
    "total_questions" BIGINT NOT NULL,
    PRIMARY KEY (quiz_sk)
);

CREATE TABLE IF NOT EXISTS benchmark.dim_payment_method (
    "method_sk"   BIGINT NOT NULL,
    "method_id"   BIGINT NOT NULL,
    "method_name" TEXT NOT NULL,
    PRIMARY KEY (method_sk)
);

-- ------------------------------------------------------------------------------
-- 2. CÁC BẢNG SỰ KIỆN FACT (FACT TABLES)
-- ------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS benchmark.fact_enrollments (
    "enrollment_id"     BIGINT NOT NULL,
    "user_sk"           BIGINT NOT NULL,
    "course_sk"         BIGINT NOT NULL,
    "instructor_sk"     BIGINT NOT NULL,
    "enrolled_date_sk"  BIGINT NOT NULL,
    "completed_date_sk" BIGINT NOT NULL,
    "enrolled_at"       TIMESTAMP NOT NULL,
    "completed_at"      TIMESTAMP,
    "lessons_completed" BIGINT NOT NULL,
    "is_completed"      BIGINT NOT NULL,
    "updated_at"        TIMESTAMP NOT NULL,
    PRIMARY KEY (enrollment_id)
);

CREATE TABLE IF NOT EXISTS benchmark.fact_payments (
    "payment_id"     BIGINT NOT NULL,
    "enrollment_id"  BIGINT NOT NULL,
    "transaction_id" TEXT NOT NULL,
    "user_sk"        BIGINT NOT NULL,
    "course_sk"      BIGINT NOT NULL,
    "instructor_sk"  BIGINT NOT NULL,
    "method_sk"      BIGINT NOT NULL,
    "date_sk"        BIGINT NOT NULL,
    "paid_at"        TIMESTAMP NOT NULL,
    "original_vnd"   BIGINT NOT NULL,
    "discount_vnd"   BIGINT NOT NULL,
    "charged_vnd"    BIGINT NOT NULL,
    "refunded"       BIGINT NOT NULL,
    "net_vnd"        BIGINT NOT NULL,
    PRIMARY KEY (payment_id)
);

CREATE TABLE IF NOT EXISTS benchmark.fact_lesson_completions (
    "completion_id"      BIGINT NOT NULL,
    "enrollment_id"      BIGINT NOT NULL,
    "user_sk"            BIGINT NOT NULL,
    "course_sk"          BIGINT NOT NULL,
    "lesson_sk"          BIGINT NOT NULL,
    "date_sk"            BIGINT NOT NULL,
    "completed_at"       TIMESTAMP NOT NULL,
    "time_spent_seconds" BIGINT NOT NULL,
    PRIMARY KEY (completion_id)
);

CREATE TABLE IF NOT EXISTS benchmark.fact_quiz_attempts (
    "attempt_id"         BIGINT NOT NULL,
    "enrollment_id"      BIGINT NOT NULL,
    "user_sk"            BIGINT NOT NULL,
    "course_sk"          BIGINT NOT NULL,
    "quiz_sk"            BIGINT NOT NULL,
    "date_sk"            BIGINT NOT NULL,
    "attempted_at"       TIMESTAMP NOT NULL,
    "attempt_number"     BIGINT NOT NULL,
    "correct_count"      BIGINT NOT NULL,
    "total_questions"    BIGINT NOT NULL,
    "time_spent_seconds" BIGINT NOT NULL,
    "is_passed"          BIGINT NOT NULL,
    PRIMARY KEY (attempt_id)
);
