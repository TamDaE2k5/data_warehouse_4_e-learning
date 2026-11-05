-- ==============================================================================
-- ĐẶC TẢ CẤU TRÚC BẢNG CƠ SỞ DỮ LIỆU TÁC NGHIỆP NGUỒN (OLTP SCHEMA DDL)
-- ==============================================================================
-- Database: learning_oltp | Schema: oltp | Hệ quản trị: PostgreSQL 16
-- Thiết kế theo mô hình chuẩn hóa bậc 3 (3NF) gồm 11 bảng thuộc 4 phân hệ chính:
--   1. Phân hệ Người dùng & Lịch sử SCD: users, user_history
--   2. Phân hệ Danh mục Đào tạo:        instructors, courses, lessons, quizzes
--   3. Phân hệ Ghi danh & Tiến độ:      enrollments, lesson_completions, quiz_attempts
--   4. Phân hệ Tài chính & Giao dịch:    payment_methods, payments
-- ==============================================================================

CREATE SCHEMA IF NOT EXISTS oltp;

-- ------------------------------------------------------------------------------
-- 1. BẢNG NGƯỜI DÙNG HIỆN HÀNH (CURRENT USERS)
-- Lưu trạng thái mới nhất của tài khoản học viên trong hệ thống.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS oltp.users (
    user_id     BIGINT PRIMARY KEY,                      -- Mã định danh duy nhất của học viên
    full_name   TEXT NOT NULL,                           -- Họ và tên đầy đủ
    email       TEXT NOT NULL UNIQUE,                    -- Email đăng nhập (ràng buộc duy nhất toàn hệ thống)
    city        TEXT NOT NULL,                           -- Tỉnh / Thành phố cư trú hiện tại
    country     CHAR(2) NOT NULL,                        -- Mã quốc gia chuẩn ISO (mặc định 'VN')
    created_at  TIMESTAMP NOT NULL                       -- Thời điểm tạo tài khoản
);

-- ------------------------------------------------------------------------------
-- 2. BẢNG LỊCH SỬ THAY ĐỔI ĐỊA LÝ CỦA HỌC VIÊN (USER GEOGRAPHIC HISTORY)
-- Lưu vết các lần dọn nhà/đổi tỉnh thành theo thời gian để phục vụ SCD Type 2 ở kho Gold.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS oltp.user_history (
    history_id  BIGINT PRIMARY KEY,                      -- Khóa chính của bản ghi lịch sử
    user_id     BIGINT NOT NULL REFERENCES oltp.users,   -- Khóa ngoại tham chiếu học viên
    full_name   TEXT NOT NULL,                           -- Họ tên tại thời điểm hiệu lực
    email       TEXT NOT NULL,                           -- Email tại thời điểm hiệu lực
    city        TEXT NOT NULL,                           -- Tỉnh thành trong khoảng thời gian này
    country     CHAR(2) NOT NULL,                        -- Mã quốc gia
    valid_from  TIMESTAMP NOT NULL,                      -- Mốc bắt đầu có hiệu lực
    valid_to    TIMESTAMP NOT NULL,                      -- Mốc kết thúc hiệu lực (vô tận là 2100-01-01)
    UNIQUE(user_id, valid_from),                         -- Một học viên tại một thời điểm chỉ có 1 nơi ở
    CHECK(valid_to > valid_from)                         -- Ràng buộc logic: Ngày kết thúc phải sau ngày bắt đầu
);

-- ------------------------------------------------------------------------------
-- 3. BẢNG DANH MỤC GIẢNG VIÊN (INSTRUCTORS)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS oltp.instructors (
    instructor_id BIGINT PRIMARY KEY,                    -- Mã giảng viên
    full_name     TEXT NOT NULL,                         -- Họ tên giảng viên
    expertise     TEXT NOT NULL                          -- Lĩnh vực chuyên môn giảng dạy
);

-- ------------------------------------------------------------------------------
-- 4. BẢNG DANH MỤC KHÓA HỌC (COURSES)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS oltp.courses (
    course_id     BIGINT PRIMARY KEY,                    -- Mã khóa học
    instructor_id BIGINT NOT NULL REFERENCES oltp.instructors, -- Giảng viên phụ trách
    title         TEXT NOT NULL,                         -- Tiêu đề khóa học
    category      TEXT NOT NULL,                         -- Phân loại (Data, Programming, Business...)
    difficulty    TEXT NOT NULL,                         -- Độ khó (beginner, intermediate, advanced)
    price_vnd     BIGINT NOT NULL CHECK(price_vnd >= 0)  -- Giá niêm yết (không được âm)
);

-- ------------------------------------------------------------------------------
-- 5. BẢNG DANH SÁCH BÀI HỌC (LESSONS)
-- Mỗi khóa học có 10 bài học đánh số thứ tự từ 1 đến 10.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS oltp.lessons (
    lesson_id     BIGINT PRIMARY KEY,                    -- Mã bài học
    course_id     BIGINT NOT NULL REFERENCES oltp.courses, -- Thuộc khóa học nào
    title         TEXT NOT NULL,                         -- Tiêu đề bài học
    position      SMALLINT NOT NULL CHECK(position BETWEEN 1 AND 10), -- Thứ tự bài trong khóa
    UNIQUE(course_id, position)                          -- Không được trùng lặp số thứ tự bài học trong 1 khóa
);

-- ------------------------------------------------------------------------------
-- 6. BẢNG ĐỀ THI TRẮC NGHIỆM TỔNG HỢP (QUIZZES)
-- Mỗi khóa học có 1 bài thi kiểm tra trắc nghiệm cuối khóa.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS oltp.quizzes (
    quiz_id         BIGINT PRIMARY KEY,                  -- Mã đề thi
    course_id       BIGINT NOT NULL REFERENCES oltp.courses, -- Thuộc khóa học nào
    title           TEXT NOT NULL,                       -- Tiêu đề đề thi
    total_questions SMALLINT NOT NULL CHECK(total_questions > 0) -- Tổng số câu hỏi trong đề
);

-- ------------------------------------------------------------------------------
-- 7. BẢNG PHƯƠNG THỨC THANH TOÁN (PAYMENT METHODS)
-- Danh mục 3 cổng thanh toán: card, bank_transfer, wallet.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS oltp.payment_methods (
    method_id   BIGINT PRIMARY KEY,                      -- Mã phương thức
    method_name TEXT NOT NULL UNIQUE                     -- Tên phương thức giao dịch
);

-- ------------------------------------------------------------------------------
-- 8. BẢNG GHI DANH KHÓA HỌC (ENROLLMENTS)
-- Ghi nhận sự kiện học viên đăng ký tham gia khóa học và theo dõi tiến độ tốt nghiệp.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS oltp.enrollments (
    enrollment_id     BIGINT PRIMARY KEY,                -- Mã lượt ghi danh
    user_id           BIGINT NOT NULL REFERENCES oltp.users, -- Học viên đăng ký
    course_id         BIGINT NOT NULL REFERENCES oltp.courses, -- Khóa học được chọn
    enrolled_at       TIMESTAMP NOT NULL,                -- Thời điểm đăng ký học
    completed_at      TIMESTAMP,                         -- Thời điểm học xong (NULL nếu chưa xong)
    lessons_completed SMALLINT NOT NULL CHECK(lessons_completed BETWEEN 0 AND 10), -- Số bài đã học
    UNIQUE(user_id, course_id),                          -- Một học viên chỉ ghi danh 1 lần vào 1 khóa
    CHECK(completed_at IS NULL OR completed_at >= enrolled_at), -- Ngày hoàn thành phải sau ngày đăng ký
    CHECK((completed_at IS NOT NULL) = (lessons_completed = 10)) -- Chỉ tính là hoàn thành khi đã học đủ 10/10 bài
);

-- ------------------------------------------------------------------------------
-- 9. BẢNG GIAO DỊCH THANH TOÁN HỌC PHÍ (PAYMENTS)
-- Ghi nhận hóa đơn thanh toán cho từng lượt ghi danh (Quan hệ 1 - 1 với enrollments).
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS oltp.payments (
    payment_id      BIGINT PRIMARY KEY,                  -- Mã giao dịch thanh toán
    enrollment_id   BIGINT NOT NULL UNIQUE REFERENCES oltp.enrollments, -- Mỗi lượt ghi danh chỉ thanh toán 1 lần
    user_id         BIGINT NOT NULL REFERENCES oltp.users,
    course_id       BIGINT NOT NULL REFERENCES oltp.courses,
    method_id       BIGINT NOT NULL REFERENCES oltp.payment_methods,
    transaction_id  TEXT NOT NULL UNIQUE,                -- Mã tham chiếu cổng thanh toán (chuỗi TXN-...)
    paid_at         TIMESTAMP NOT NULL,                  -- Thời điểm thanh toán thành công
    original_vnd    BIGINT NOT NULL,                     -- Giá gốc khóa học
    discount_vnd    BIGINT NOT NULL,                     -- Số tiền giảm giá khuyến mãi
    charged_vnd     BIGINT NOT NULL,                     -- Số tiền thực thu (charged = original - discount)
    refunded        SMALLINT NOT NULL CHECK(refunded IN (0,1)), -- Cờ hoàn tiền (0: hợp lệ, 1: đã hoàn tiền)
    CHECK(original_vnd >= 0 AND discount_vnd BETWEEN 0 AND original_vnd),
    CHECK(charged_vnd = original_vnd - discount_vnd)     -- Ràng buộc đối soát toán học chính xác tuyệt đối
);

-- ------------------------------------------------------------------------------
-- 10. BẢNG TIẾN ĐỘ HOÀN THÀNH TỪNG BÀI HỌC (LESSON COMPLETIONS)
-- Nhật ký chi tiết mỗi lần học viên học xong 1 bài (Quy mô lớn nhất: 3.6 triệu dòng).
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS oltp.lesson_completions (
    completion_id      BIGINT PRIMARY KEY,               -- Mã lượt hoàn thành bài học
    enrollment_id      BIGINT NOT NULL REFERENCES oltp.enrollments,
    user_id            BIGINT NOT NULL REFERENCES oltp.users,
    course_id          BIGINT NOT NULL REFERENCES oltp.courses,
    lesson_id          BIGINT NOT NULL REFERENCES oltp.lessons,
    completed_at       TIMESTAMP NOT NULL,               -- Thời điểm bấm hoàn thành bài học
    time_spent_seconds INTEGER NOT NULL CHECK(time_spent_seconds > 0), -- Thời gian xem video bài học (giây)
    UNIQUE(enrollment_id, lesson_id)                     -- Mỗi bài học chỉ được hoàn thành 1 lần trong 1 lượt ghi danh
);

-- ------------------------------------------------------------------------------
-- 11. BẢNG NHẬT KÝ NỘP BÀI THI TRẮC NGHIỆM (QUIZ ATTEMPTS)
-- Ghi nhận từng lần làm bài thi của học viên (Cho phép thi lại nhiều lần: attempt_number).
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS oltp.quiz_attempts (
    attempt_id         BIGINT PRIMARY KEY,               -- Mã lượt nộp bài
    enrollment_id      BIGINT NOT NULL REFERENCES oltp.enrollments,
    user_id            BIGINT NOT NULL REFERENCES oltp.users,
    course_id          BIGINT NOT NULL REFERENCES oltp.courses,
    quiz_id            BIGINT NOT NULL REFERENCES oltp.quizzes,
    attempt_number     SMALLINT NOT NULL,                -- Số thứ tự lần thi (Lần 1, Lần 2, ...)
    attempted_at       TIMESTAMP NOT NULL,               -- Thời điểm nộp bài
    correct_count      SMALLINT NOT NULL CHECK(correct_count BETWEEN 0 AND 20), -- Số câu trả lời đúng
    total_questions    SMALLINT NOT NULL CHECK(total_questions = 20),           -- Tổng số câu trong đề thi
    time_spent_seconds INTEGER NOT NULL CHECK(time_spent_seconds > 0),          -- Thời gian làm bài thi (giây)
    UNIQUE(enrollment_id, quiz_id, attempt_number)       -- Ràng buộc duy nhất cho từng lần nộp bài
);

-- ------------------------------------------------------------------------------
-- CHỈ MỤC TỐI ƯU TRUY VẤN THEO KHOẢNG THỜI GIAN (TIME-RANGE INDEXES)
-- ------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS enrollments_time_idx ON oltp.enrollments(enrolled_at);
CREATE INDEX IF NOT EXISTS payments_time_idx ON oltp.payments(paid_at);
