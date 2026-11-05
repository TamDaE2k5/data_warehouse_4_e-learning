-- ==============================================================================
-- ĐẶC TẢ CẤU TRÚC KHO DỮ LIỆU ĐA CHIỀU GOLD TRÊN CLICKHOUSE (GALAXY SCHEMA DDL)
-- ==============================================================================
-- Hệ quản trị: ClickHouse Server 24.8 LTS | Database: gold
-- Kiến trúc: Mô hình chòm sao (Galaxy Schema / Fact Constellation) gồm:
--   - 7 Bảng chiều (Dimension Tables) dùng chung (Conformed Dimensions):
--       + dim_date, dim_user (SCD Type 2), dim_course, dim_instructor,
--       + dim_lesson, dim_quiz, dim_payment_method.
--   - 4 Bảng sự kiện (Fact Tables) phục vụ phân tích đa góc nhìn:
--       + fact_enrollments (Snapshot tích lũy tiến độ - Accumulating Snapshot Fact)
--       + fact_payments (Sự kiện giao dịch thanh toán - Transaction Fact)
--       + fact_lesson_completions (Sự kiện hoàn thành bài học - Activity Fact)
--       + fact_quiz_attempts (Sự kiện thi trắc nghiệm đánh giá - Performance Fact)
--
-- Kỹ thuật tối ưu hóa ClickHouse:
--   1. LowCardinality(String): Nén từ điển cho các trường chuỗi ít biến động (thành phố, danh mục, độ khó),
--      giúp giảm 80% RAM và tăng tốc độ GROUP BY lên gấp 5-10 lần.
--   2. Phân vùng theo tháng (PARTITION BY toYYYYMM): Hỗ trợ Partition Pruning và thao tác Attach siêu tốc.
--   3. ReplacingMergeTree(updated_at): Tự động khử trùng lặp và gộp bản ghi mới nhất cho bảng enrollments.
--   4. Chỉ mục thưa (Sparse Index qua ORDER BY): Sắp xếp đa tầng tối ưu cho các bộ lọc WHERE/JOIN phổ biến.
-- ==============================================================================

CREATE DATABASE IF NOT EXISTS gold;

-- ==============================================================================
-- PHẦN 1: CÁC BẢNG CHIỀU DÙNG CHUNG (CONFORMED DIMENSION TABLES)
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1.1 CHIỀU THỜI GIAN (DIM_DATE)
-- Đóng vai trò là Chiều thời gian đóng vai kép (Role-Playing Date Dimension)
-- cho cả ngày ghi danh (enrolled_date_sk) và ngày hoàn thành (completed_date_sk).
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.dim_date (
    date_sk     Int64,                           -- Khóa thay thế dạng số YYYYMMDD (ví dụ: 20240515; mốc 0 là 'Chưa xác định')
    full_date   Date,                            -- Ngày lịch dương chuẩn (YYYY-MM-DD)
    year        Int64,                           -- Năm (ví dụ: 2024)
    quarter     Int64,                           -- Quý trong năm (1, 2, 3, 4)
    month       Int64,                           -- Tháng trong năm (1 đến 12)
    day         Int64                            -- Ngày trong tháng (1 đến 31)
) ENGINE = MergeTree 
ORDER BY date_sk;

-- ------------------------------------------------------------------------------
-- 1.2 CHIỀU HỌC VIÊN LƯU VẾT LỊCH SỬ (DIM_USER - SCD TYPE 2)
-- Lưu lại các phiên bản thay đổi nơi cư trú của học viên theo thời gian.
-- Cho phép phân tích doanh thu theo địa phương tại đúng thời điểm học viên sinh sống.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.dim_user (
    user_sk     Int64,                           -- Khóa thay thế duy nhất cho từng phiên bản hiệu lực (Surrogate Key)
    user_id     Int64,                           -- Khóa tự nhiên từ nguồn OLTP (Natural Key)
    full_name   String,                          -- Họ tên học viên
    email       String,                          -- Email chuẩn hóa chữ thường
    city        LowCardinality(String),          -- Tỉnh/Thành phố (nén từ điển LowCardinality)
    country     LowCardinality(String),          -- Quốc gia (mặc định 'VN')
    valid_from  DateTime('UTC'),                 -- Thời điểm phiên bản bắt đầu có hiệu lực
    valid_to    DateTime('UTC'),                 -- Thời điểm phiên bản hết hiệu lực (vô tận là 2100-01-01)
    is_current  Int64                            -- Cờ báo phiên bản hiện hành (1 = mới nhất, 0 = lịch sử cũ)
) ENGINE = MergeTree 
ORDER BY (user_id, valid_from);

-- ------------------------------------------------------------------------------
-- 1.3 CHIỀU KHÓA HỌC (DIM_COURSE)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.dim_course (
    course_sk     Int64,                         -- Khóa thay thế khóa học (course_id + 1.000.000)
    course_id     Int64,                         -- Khóa nguồn OLTP
    title         String,                        -- Tiêu đề khóa học
    category      LowCardinality(String),        -- Danh mục (Data, Programming, Business, Design, Language)
    difficulty    LowCardinality(String),        -- Cấp độ (beginner, intermediate, advanced)
    instructor_id Int64,                         -- Khóa ngoại tham chiếu giảng viên
    price_vnd     Int64                          -- Học phí niêm yết (VND)
) ENGINE = MergeTree 
ORDER BY course_sk;

-- ------------------------------------------------------------------------------
-- 1.4 CHIỀU GIẢNG VIÊN (DIM_INSTRUCTOR)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.dim_instructor (
    instructor_sk Int64,                         -- Khóa thay thế giảng viên (instructor_id + 2.000.000)
    instructor_id Int64,                         -- Khóa nguồn OLTP
    full_name     String,                        -- Họ tên giảng viên
    expertise     LowCardinality(String)         -- Chuyên môn giảng dạy (Technology,...)
) ENGINE = MergeTree 
ORDER BY instructor_sk;

-- ------------------------------------------------------------------------------
-- 1.5 CHIỀU BÀI HỌC (DIM_LESSON)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.dim_lesson (
    lesson_sk     Int64,                         -- Khóa thay thế bài học (lesson_id + 3.000.000)
    lesson_id     Int64,                         -- Khóa nguồn OLTP
    course_id     Int64,                         -- Khóa khóa học sở hữu bài học
    title         String,                        -- Tiêu đề bài học
    position      Int64                          -- Thứ tự bài học trong khóa (1 đến 10)
) ENGINE = MergeTree 
ORDER BY lesson_sk;

-- ------------------------------------------------------------------------------
-- 1.6 CHIỀU BÀI KIỂM TRA (DIM_QUIZ)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.dim_quiz (
    quiz_sk         Int64,                       -- Khóa thay thế bài kiểm tra (quiz_id + 4.000.000)
    quiz_id         Int64,                       -- Khóa nguồn OLTP
    course_id       Int64,                       -- Khóa khóa học sở hữu bài kiểm tra
    title           String,                      -- Tiêu đề bài kiểm tra
    total_questions Int64                        -- Tổng số lượng câu hỏi (mặc định 20 câu)
) ENGINE = MergeTree 
ORDER BY quiz_sk;

-- ------------------------------------------------------------------------------
-- 1.7 CHIỀU HÌNH THỨC THANH TOÁN (DIM_PAYMENT_METHOD)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.dim_payment_method (
    method_sk   Int64,                           -- Khóa thay thế phương thức (method_id + 5.000.000)
    method_id   Int64,                           -- Khóa nguồn OLTP
    method_name LowCardinality(String)           -- Tên phương thức (bank_transfer, card, wallet)
) ENGINE = MergeTree 
ORDER BY method_sk;


-- ==============================================================================
-- PHẦN 2: CÁC BẢNG SỰ KIỆN FACT (GALAXY FACT TABLES)
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 2.1 BẢNG FACT GHI DANH & TIẾN ĐỘ KHÓA HỌC (FACT_ENROLLMENTS)
-- Dạng bảng: Accumulating Snapshot Fact Table (ghi nhận trạng thái biến chuyển theo thời gian).
-- Sử dụng ReplacingMergeTree để tự động ghi đè và cập nhật trạng thái khi học viên hoàn thành khóa.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.fact_enrollments (
    enrollment_id      Int64,                    -- Mã ghi danh từ nguồn OLTP
    user_sk            Int64,                    -- Khóa thay thế học viên tại thời điểm ghi danh (ASOF SCD2)
    course_sk          Int64,                    -- Khóa thay thế khóa học
    instructor_sk      Int64,                    -- Khóa thay thế giảng viên phụ trách
    enrolled_date_sk   Int64,                    -- Khóa ngày ghi danh (YYYYMMDD)
    completed_date_sk  Int64,                    -- Khóa ngày hoàn thành (YYYYMMDD hoặc 0 nếu chưa học xong)
    enrolled_at        DateTime('UTC'),          -- Mốc thời gian ghi danh
    completed_at       Nullable(DateTime('UTC')),-- Mốc thời gian hoàn thành khóa (có thể NULL)
    lessons_completed  Int64,                    -- Số bài học đã hoàn thành lũy kế (6 hoặc 10 bài)
    is_completed       Int64,                    -- Cờ hoàn thành khóa học (1 = đã tốt nghiệp, 0 = đang học)
    updated_at         DateTime64(6, 'UTC')      -- Mốc thời gian cập nhật để ReplacingMergeTree giữ bản mới nhất
) ENGINE = ReplacingMergeTree(updated_at) 
PARTITION BY toYYYYMM(enrolled_at)
ORDER BY enrollment_id;

-- ------------------------------------------------------------------------------
-- 2.2 BẢNG FACT GIAO DỊCH DOANH THU & HỌC PHÍ (FACT_PAYMENTS)
-- Dạng bảng: Transaction Fact Table (chứa các sự kiện thanh toán tài chính phát sinh).
-- Phân vùng theo tháng thanh toán để tối ưu tốc độ báo cáo tài chính hàng tháng (R01, R04, R06).
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.fact_payments (
    payment_id      Int64,                       -- Mã giao dịch thanh toán
    enrollment_id   Int64,                       -- Mã lượt ghi danh liên kết
    transaction_id  String,                      -- Mã hóa đơn ngân hàng (TXN-...)
    user_sk         Int64,                       -- Khóa học viên tại thời điểm thanh toán (ASOF SCD2)
    course_sk       Int64,                       -- Khóa khóa học
    instructor_sk   Int64,                       -- Khóa giảng viên được chia sẻ doanh thu
    method_sk       Int64,                       -- Khóa hình thức thanh toán
    date_sk         Int64,                       -- Khóa ngày thanh toán (YYYYMMDD)
    paid_at         DateTime('UTC'),             -- Mốc thời gian thanh toán chính xác
    original_vnd    Int64,                       -- Giá gốc niêm yết (Gross Merchandise Value - GMV)
    discount_vnd    Int64,                       -- Số tiền giảm giá voucher
    charged_vnd     Int64,                       -- Số tiền thực thu từ khách hàng
    refunded        Int64,                       -- Cờ hoàn tiền (1 = đã hoàn trả, 0 = không hoàn)
    net_vnd         Int64                        -- Doanh thu thuần = charged_vnd * (1 - refunded)
) ENGINE = MergeTree 
PARTITION BY toYYYYMM(paid_at)
ORDER BY (date_sk, course_sk, user_sk, payment_id);

-- ------------------------------------------------------------------------------
-- 2.3 BẢNG FACT CHI TIẾT HOÀN THÀNH BÀI HỌC (FACT_LESSON_COMPLETIONS)
-- Dạng bảng: Activity Fact Table (đo lường hành vi học tập và thời lượng tương tác).
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.fact_lesson_completions (
    completion_id      Int64,                    -- Mã lượt hoàn thành bài học
    enrollment_id      Int64,                    -- Mã lượt ghi danh
    user_sk            Int64,                    -- Khóa học viên tại thời điểm hoàn thành (ASOF SCD2)
    course_sk          Int64,                    -- Khóa khóa học
    lesson_sk          Int64,                    -- Khóa bài học
    date_sk            Int64,                    -- Khóa ngày hoàn thành (YYYYMMDD)
    completed_at       DateTime('UTC'),          -- Mốc thời gian học viên hoàn tất bài học
    time_spent_seconds Int64                     -- Thời lượng học tập thực tế (giây)
) ENGINE = MergeTree 
PARTITION BY toYYYYMM(completed_at)
ORDER BY (date_sk, course_sk, user_sk, completion_id);

-- ------------------------------------------------------------------------------
-- 2.4 BẢNG FACT KẾT QUẢ THI TRẮC NGHIỆM ĐÁNH GIÁ (FACT_QUIZ_ATTEMPTS)
-- Dạng bảng: Performance Fact Table (đo lường chất lượng đào tạo và tỉ lệ thi đạt).
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.fact_quiz_attempts (
    attempt_id         Int64,                    -- Mã lượt làm bài thi
    enrollment_id      Int64,                    -- Mã lượt ghi danh
    user_sk            Int64,                    -- Khóa học viên tại thời điểm làm bài (ASOF SCD2)
    course_sk          Int64,                    -- Khóa khóa học
    quiz_sk            Int64,                    -- Khóa bài kiểm tra
    date_sk            Int64,                    -- Khóa ngày nộp bài thi (YYYYMMDD)
    attempted_at       DateTime('UTC'),          -- Mốc thời gian nộp bài thi
    attempt_number     Int64,                    -- Lần thi thứ mấy (Lần 1 hoặc Lần 2)
    correct_count      Int64,                    -- Số câu trả lời đúng
    total_questions    Int64,                    -- Tổng số câu hỏi trong đề thi (20 câu)
    time_spent_seconds Int64,                    -- Thời gian làm bài (giây)
    is_passed          Int64                     -- Cờ đỗ kỳ thi (1 = đạt >= 70% số câu, 0 = trượt)
) ENGINE = MergeTree 
PARTITION BY toYYYYMM(attempted_at)
ORDER BY (date_sk, course_sk, user_sk, attempt_id);
