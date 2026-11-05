-- ==============================================================================
-- ĐẶC TẢ CẤU TRÚC BẢNG KHO TRUNG CHUYỂN DWH_STAGING (STAGING, SILVER & QUARANTINE)
-- ==============================================================================
-- Database: dwh_staging | Hệ quản trị: PostgreSQL 16
-- Bao gồm 3 Schema chức năng chuyên biệt:
--   1. Schema `staging`:     Vùng đệm chứa bảng quản lý mốc phân thủy nạp tăng dần.
--   2. Schema `quarantine`:  Khu cách ly các bản ghi vi phạm schema hoặc luật nghiệp vụ.
--   3. Schema `silver`:      Lớp dữ liệu sạch, đã chuẩn hóa và khử trùng lặp (11 bảng).
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. KHỞI TẠO CÁC SCHEMA CHỨC NĂNG
-- ------------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS quarantine;

-- ------------------------------------------------------------------------------
-- 2. BẢNG MỐC PHÂN THỦY NẠP TĂNG DẦN (WATERMARK TRACKING TABLE)
-- Ghi vết tiến độ nạp của từng bảng để các mẻ chạy sau chỉ quét dữ liệu mới (CDC).
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS staging.etl_watermarks (
    table_name          TEXT PRIMARY KEY,              -- Tên bảng nguồn (ví dụ: 'payments', 'enrollments')
    last_processed_time TIMESTAMPTZ NOT NULL,          -- Mốc thời gian updated_at lớn nhất của mẻ trước
    last_processed_id   BIGINT NOT NULL,               -- Khóa chính lớn nhất tại mốc thời gian đó (chống trùng mốc)
    last_run_id         TEXT NOT NULL                  -- Mã UUID của lần chạy ETL thành công gần nhất
);

-- ------------------------------------------------------------------------------
-- 3. BẢNG KHU VỰC CÁCH LY BẢN GHI LỖI (DEAD-LETTER QUARANTINE TABLE)
-- Chứa các dòng dữ liệu bị từ chối do sai kiểu dữ liệu (Schema Drift) hoặc vi phạm nghiệp vụ.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quarantine.quarantine_records (
    table_name          TEXT NOT NULL,                 -- Tên bảng phát hiện bản ghi lỗi
    source_id           BIGINT NOT NULL,               -- Khóa chính từ hệ thống nguồn
    source_updated_at   TIMESTAMPTZ NOT NULL,          -- Mốc thời gian cập nhật của bản ghi nguồn
    error_code          TEXT NOT NULL,                 -- Mã phân loại lỗi (ví dụ: ERR_SCHEMA_TYPE_MISMATCH)
    rejection_reason    TEXT NOT NULL,                 -- Mô tả chi tiết lý do từ chối
    detected_at         TIMESTAMPTZ DEFAULT now(),     -- Thời điểm phát hiện và cách ly bản ghi
    raw_payload         JSONB NOT NULL,                -- Bản chụp nguyên trạng toàn bộ dòng dữ liệu dưới dạng JSONB
    PRIMARY KEY (table_name, source_id, source_updated_at)
);

-- ------------------------------------------------------------------------------
-- 4. CÁC BẢNG LỚP SILVER (CLEANSED & CONFORMED SILVER LAYER)
-- Chứa dữ liệu đã được làm sạch kiểu, cắt khoảng trắng, loại bỏ trùng lặp và sẵn sàng
-- nạp vào các mô hình hình sao (Star/Galaxy) ở tầng Gold.
-- ------------------------------------------------------------------------------

-- 4.1 Bảng học viên chuẩn hóa
CREATE TABLE IF NOT EXISTS silver.users (
    user_id     BIGINT PRIMARY KEY,
    full_name   TEXT NOT NULL,
    email       TEXT NOT NULL,
    city        TEXT NOT NULL,
    country     TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL
);

-- 4.2 Bảng lịch sử thay đổi địa lý (chuẩn bị cho SCD Type 2)
CREATE TABLE IF NOT EXISTS silver.user_history (
    history_id  BIGINT PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    full_name   TEXT NOT NULL,
    email       TEXT NOT NULL,
    city        TEXT NOT NULL,
    country     TEXT NOT NULL,
    valid_from  TIMESTAMP NOT NULL,
    valid_to    TIMESTAMP NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL
);

-- 4.3 Bảng danh mục giảng viên
CREATE TABLE IF NOT EXISTS silver.instructors (
    instructor_id BIGINT PRIMARY KEY,
    full_name     TEXT NOT NULL,
    expertise     TEXT NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL
);

-- 4.4 Bảng danh mục khóa học
CREATE TABLE IF NOT EXISTS silver.courses (
    course_id     BIGINT PRIMARY KEY,
    instructor_id BIGINT NOT NULL,
    title         TEXT NOT NULL,
    category      TEXT NOT NULL,
    difficulty    TEXT NOT NULL,
    price_vnd     BIGINT NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL
);

-- 4.5 Bảng danh mục bài học
CREATE TABLE IF NOT EXISTS silver.lessons (
    lesson_id   BIGINT PRIMARY KEY,
    course_id   BIGINT NOT NULL,
    title       TEXT NOT NULL,
    position    BIGINT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL
);

-- 4.6 Bảng bài kiểm tra
CREATE TABLE IF NOT EXISTS silver.quizzes (
    quiz_id         BIGINT PRIMARY KEY,
    course_id       BIGINT NOT NULL,
    title           TEXT NOT NULL,
    total_questions BIGINT NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL
);

-- 4.7 Bảng phương thức thanh toán
CREATE TABLE IF NOT EXISTS silver.payment_methods (
    method_id   BIGINT PRIMARY KEY,
    method_name TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL
);

-- 4.8 Bảng sự kiện ghi danh
CREATE TABLE IF NOT EXISTS silver.enrollments (
    enrollment_id     BIGINT PRIMARY KEY,
    user_id           BIGINT NOT NULL,
    course_id         BIGINT NOT NULL,
    enrolled_at       TIMESTAMP NOT NULL,
    completed_at      TIMESTAMP,
    lessons_completed BIGINT NOT NULL,
    updated_at        TIMESTAMPTZ NOT NULL
);

-- 4.9 Bảng sự kiện thanh toán học phí
CREATE TABLE IF NOT EXISTS silver.payments (
    payment_id     BIGINT PRIMARY KEY,
    enrollment_id  BIGINT NOT NULL,
    user_id        BIGINT NOT NULL,
    course_id      BIGINT NOT NULL,
    method_id      BIGINT NOT NULL,
    transaction_id TEXT NOT NULL,
    paid_at        TIMESTAMP NOT NULL,
    original_vnd   BIGINT NOT NULL,
    discount_vnd   BIGINT NOT NULL,
    charged_vnd    BIGINT NOT NULL,
    refunded       BIGINT NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL
);

-- 4.10 Bảng sự kiện hoàn thành bài học
CREATE TABLE IF NOT EXISTS silver.lesson_completions (
    completion_id      BIGINT PRIMARY KEY,
    enrollment_id      BIGINT NOT NULL,
    user_id            BIGINT NOT NULL,
    course_id          BIGINT NOT NULL,
    lesson_id          BIGINT NOT NULL,
    completed_at       TIMESTAMP NOT NULL,
    time_spent_seconds BIGINT NOT NULL,
    updated_at         TIMESTAMPTZ NOT NULL
);

-- 4.11 Bảng sự kiện làm bài kiểm tra trắc nghiệm
CREATE TABLE IF NOT EXISTS silver.quiz_attempts (
    attempt_id         BIGINT PRIMARY KEY,
    enrollment_id      BIGINT NOT NULL,
    user_id            BIGINT NOT NULL,
    course_id          BIGINT NOT NULL,
    quiz_id            BIGINT NOT NULL,
    attempt_number     BIGINT NOT NULL,
    attempted_at       TIMESTAMP NOT NULL,
    correct_count      BIGINT NOT NULL,
    total_questions    BIGINT NOT NULL,
    time_spent_seconds BIGINT NOT NULL,
    updated_at         TIMESTAMPTZ NOT NULL
);
