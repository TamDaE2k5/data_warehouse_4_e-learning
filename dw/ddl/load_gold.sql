-- ==============================================================================
-- KỊCH BẢN BIẾN ĐỔI VÀ NẠP DỮ LIỆU TỪ SILVER SANG GOLD (GOLD TRANSFORMATION ETL)
-- ==============================================================================
-- Hệ quản trị: ClickHouse Server 24.8 LTS | Target Database: gold (hoặc gold_build)
-- Nguồn dữ liệu: Các bảng sạch tại PostgreSQL dwh_staging (thông qua stage_bridge)
-- Kỹ thuật nâng cao:
--   1. Tạo khóa thay thế phân dải theo miền (Domain-Offset Surrogate Keys).
--   2. Tạo chiều thời gian tự động bằng hàm sinh dãy số `numbers(1096)` (3 năm 2022-2024).
--   3. Ghép nối thời gian SCD Type 2 bằng phép toán siêu tốc ClickHouse `ASOF LEFT JOIN`.
--   4. Tính toán độ đo kinh doanh (Doanh thu thuần net_vnd, Tỷ lệ đỗ kỳ thi is_passed).
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. NẠP CHIỀU THỜI GIAN (DIM_DATE)
-- Sinh tự động 1.096 ngày từ 2022-01-01 đến 2024-12-31 bằng hàm numbers() của ClickHouse.
-- Thêm bản ghi đặc biệt date_sk = 0 ('1970-01-01') để đại diện cho mốc "Chưa hoàn thành / Không áp dụng".
-- ------------------------------------------------------------------------------
INSERT INTO gold.dim_date
SELECT 
    toYYYYMMDD(d) AS date_sk,
    d             AS full_date,
    toYear(d)     AS year,
    toQuarter(d)  AS quarter,
    toMonth(d)    AS month,
    toDayOfMonth(d) AS day
FROM (
    SELECT toDate('2022-01-01') + toIntervalDay(number) AS d 
    FROM numbers(1096)
);

-- Bản ghi phòng thủ cho các khóa ngoại thời gian mang giá trị NULL
INSERT INTO gold.dim_date VALUES (0, '1970-01-01', 0, 0, 0, 0);

-- ------------------------------------------------------------------------------
-- 2. NẠP CHIỀU HỌC VIÊN BIẾN ĐỘNG CHẬM (DIM_USER - SCD TYPE 2)
-- Lấy dữ liệu từ bảng silver.user_history.
-- Tạo user_sk duy nhất bằng cách cộng độ lệch miền: history_id + 10.000.000.
-- Gán cờ is_current = 1 cho bản ghi có valid_to = '2100-01-01'.
-- ------------------------------------------------------------------------------
INSERT INTO gold.dim_user
SELECT 
    history_id + 10000000 AS user_sk,
    user_id,
    full_name,
    email,
    city,
    country,
    valid_from,
    valid_to,
    toInt64(valid_to = toDateTime('2100-01-01 00:00:00', 'UTC')) AS is_current
FROM silver.user_history;

-- ------------------------------------------------------------------------------
-- 3. NẠP CÁC BẢNG CHIỀU DANH MỤC CÒN LẠI (CONFORMED DIMENSIONS)
-- Mỗi chiều sử dụng một dải độ lệch khóa thay thế (Offset) riêng biệt để chống xung đột:
--   - Courses:     + 1.000.000
--   - Instructors: + 2.000.000
--   - Lessons:     + 3.000.000
--   - Quizzes:     + 4.000.000
--   - Payments:    + 5.000.000
-- ------------------------------------------------------------------------------
INSERT INTO gold.dim_course
SELECT 
    course_id + 1000000 AS course_sk,
    course_id,
    title,
    category,
    difficulty,
    instructor_id,
    price_vnd
FROM silver.courses;

INSERT INTO gold.dim_instructor
SELECT 
    instructor_id + 2000000 AS instructor_sk,
    instructor_id,
    full_name,
    expertise
FROM silver.instructors;

INSERT INTO gold.dim_lesson
SELECT 
    lesson_id + 3000000 AS lesson_sk,
    lesson_id,
    course_id,
    title,
    position
FROM silver.lessons;

INSERT INTO gold.dim_quiz
SELECT 
    quiz_id + 4000000 AS quiz_sk,
    quiz_id,
    course_id,
    title,
    total_questions
FROM silver.quizzes;

INSERT INTO gold.dim_payment_method
SELECT 
    method_id + 5000000 AS method_sk,
    method_id,
    method_name
FROM silver.payment_methods;

-- ------------------------------------------------------------------------------
-- 4. NẠP BẢNG FACT GHI DANH & TIẾN ĐỘ HỌC TẬP (FACT_ENROLLMENTS)
-- Sử dụng ASOF LEFT JOIN để gán đúng phiên bản học viên (user_sk) tại thời điểm ghi danh.
-- ------------------------------------------------------------------------------
INSERT INTO gold.fact_enrollments
SELECT 
    e.enrollment_id,
    u.user_sk,
    c.course_sk,
    i.instructor_sk,
    toYYYYMMDD(e.enrolled_at) AS enrolled_date_sk,
    ifNull(toYYYYMMDD(e.completed_at), 0) AS completed_date_sk,
    e.enrolled_at,
    e.completed_at,
    e.lessons_completed,
    toInt64(e.completed_at IS NOT NULL) AS is_completed,
    e.updated_at
FROM silver.enrollments e
INNER JOIN gold.dim_course c ON e.course_id = c.course_id
INNER JOIN gold.dim_instructor i ON c.instructor_id = i.instructor_id
ASOF LEFT JOIN gold.dim_user u ON e.user_id = u.user_id AND e.enrolled_at >= u.valid_from;

-- ------------------------------------------------------------------------------
-- 5. NẠP BẢNG FACT DOANH THU & GIAO DỊCH HỌC PHÍ (FACT_PAYMENTS)
-- Tính toán độ đo tài chính:
--   - net_vnd = charged_vnd * (1 - refunded): Doanh thu thực nhận sau khi trừ các khoản hoàn tiền.
-- Gán user_sk chính xác tại thời điểm giao dịch phát sinh qua ASOF LEFT JOIN.
-- ------------------------------------------------------------------------------
INSERT INTO gold.fact_payments
SELECT 
    p.payment_id,
    p.enrollment_id,
    p.transaction_id,
    u.user_sk,
    c.course_sk,
    i.instructor_sk,
    m.method_sk,
    toYYYYMMDD(p.paid_at) AS date_sk,
    p.paid_at,
    p.original_vnd,
    p.discount_vnd,
    p.charged_vnd,
    p.refunded,
    p.charged_vnd * (1 - p.refunded) AS net_vnd
FROM silver.payments p
INNER JOIN gold.dim_course c ON p.course_id = c.course_id
INNER JOIN gold.dim_instructor i ON c.instructor_id = i.instructor_id
INNER JOIN gold.dim_payment_method m ON p.method_id = m.method_id
ASOF LEFT JOIN gold.dim_user u ON p.user_id = u.user_id AND p.paid_at >= u.valid_from;

-- ------------------------------------------------------------------------------
-- 6. NẠP BẢNG FACT CHI TIẾT HOÀN THÀNH BÀI HỌC (FACT_LESSON_COMPLETIONS)
-- ------------------------------------------------------------------------------
INSERT INTO gold.fact_lesson_completions
SELECT 
    l.completion_id,
    l.enrollment_id,
    u.user_sk,
    c.course_sk,
    d.lesson_sk,
    toYYYYMMDD(l.completed_at) AS date_sk,
    l.completed_at,
    l.time_spent_seconds
FROM silver.lesson_completions l
INNER JOIN gold.dim_course c ON l.course_id = c.course_id
INNER JOIN gold.dim_lesson d ON l.lesson_id = d.lesson_id
ASOF LEFT JOIN gold.dim_user u ON l.user_id = u.user_id AND l.completed_at >= u.valid_from;

-- ------------------------------------------------------------------------------
-- 7. NẠP BẢNG FACT KẾT QUẢ THI ĐÁNH GIÁ (FACT_QUIZ_ATTEMPTS)
-- Tính toán cờ đỗ kỳ thi (is_passed): Điểm số phải đạt từ 70% trở lên (>= 14/20 câu đúng).
-- ------------------------------------------------------------------------------
INSERT INTO gold.fact_quiz_attempts
SELECT 
    q.attempt_id,
    q.enrollment_id,
    u.user_sk,
    c.course_sk,
    d.quiz_sk,
    toYYYYMMDD(q.attempted_at) AS date_sk,
    q.attempted_at,
    q.attempt_number,
    q.correct_count,
    q.total_questions,
    q.time_spent_seconds,
    toInt64(q.correct_count * 100 >= q.total_questions * 70) AS is_passed
FROM silver.quiz_attempts q
INNER JOIN gold.dim_course c ON q.course_id = c.course_id
INNER JOIN gold.dim_quiz d ON q.quiz_id = d.quiz_id
ASOF LEFT JOIN gold.dim_user u ON q.user_id = u.user_id AND q.attempted_at >= u.valid_from;
