-- ==============================================================================
-- BỘ 10 TRUY VẤN PHÂN TÍCH NGHIỆP VỤ QUẢN TRỊ (EXECUTIVE ANALYTICS QUERIES: R01-R10)
-- ==============================================================================
-- Hệ quản trị: ClickHouse Server 24.8 LTS | Target Database: gold
-- Mục tiêu:
--   - Minh họa toàn diện các kỹ thuật phân tích OLAP theo chuẩn kiến trúc Kimball:
--       + R01: Phân cấp tổng hợp đa tầng (Rollup)
--       + R02: Tỷ lệ hoàn thành theo danh mục & độ khó (Completion Rate)
--       + R03: Đánh giá chất lượng thi cử theo trọng số (Quiz Weighted Performance)
--       + R04: Chiều thời gian đóng vai kép (Role-Playing Date Dimensions)
--       + R05: Báo cáo theo địa phương theo dấu vết lịch sử (SCD Type 2 Point-in-time)
--       + R06: Xếp hạng top khóa học theo quý dùng Window Function (Ranking)
--       + R07: Kỹ thuật Fact-to-Fact Drill Across kết hợp 2 quy trình kinh doanh độc lập
--       + R08: Cắt lát & xẻ khối dữ liệu (Slice & Dice)
--       + R09: Khối lập phương đa chiều toàn phần (Multidimensional Cube)
--       + R10: Đường cong thời lượng học tập theo vị trí bài học (Learning Curve)
--
-- Lưu ý định dạng:
--   - Mỗi truy vấn bắt đầu bằng thẻ ghi chú: `-- name: Rxx_tên_báo_cáo`
--   - Được phân tích tự động bằng biểu thức chính quy (Regex) trong module reports.py.
-- ==============================================================================


-- ==============================================================================
-- R01: PHÂN CẤP TỔNG HỢP DOANH THU THEO NĂM, QUÝ, THÁNG (ROLLUP HIERARCHY)
-- Kỹ thuật: Sử dụng mệnh đề ROLLUP để tính toán tự động các cấp tổng con (Subtotals)
-- và tổng toàn cục (Grand Total) theo thứ tự thứ bậc thời gian: Năm -> Quý -> Tháng.
-- ==============================================================================
-- name: R01_revenue_rollup
SELECT 
    d.year, 
    d.quarter, 
    d.month, 
    sum(f.net_vnd)      AS net_vnd,               -- Doanh thu thuần sau hoàn tiền
    sum(f.charged_vnd)  AS charged_vnd,           -- Tổng số tiền thực thu từ học viên
    sum(f.refunded)     AS refunded_transactions  -- Tổng số giao dịch bị hoàn tiền
FROM gold.fact_payments f 
JOIN gold.dim_date d ON f.date_sk = d.date_sk
GROUP BY ROLLUP(d.year, d.quarter, d.month)
ORDER BY d.year, d.quarter, d.month;


-- ==============================================================================
-- R02: TỶ LỆ HOÀN THÀNH KHÓA HỌC THEO DANH MỤC VÀ ĐỘ KHÓ (DRILL-DOWN & RETENTION)
-- Kỹ thuật: Tính toán tỷ lệ phần trăm giữ chân học viên và tốt nghiệp khóa học.
-- ==============================================================================
-- name: R02_completion_rate
SELECT 
    c.category,
    c.difficulty,
    count(*)                                      AS enrollments,    -- Tổng số lượt ghi danh
    sum(e.is_completed)                           AS completed,      -- Số học viên hoàn thành trọn vẹn
    round(100.0 * sum(e.is_completed) / count(*), 2) AS completion_pct  -- Tỷ lệ phần trăm hoàn thành (%)
FROM gold.fact_enrollments e 
JOIN gold.dim_course c ON e.course_sk = c.course_sk
GROUP BY c.category, c.difficulty 
ORDER BY c.category, c.difficulty;


-- ==============================================================================
-- R03: ĐÁNH GIÁ CHẤT LƯỢNG THI CỬ THEO TRỌNG SỐ (WEIGHTED QUIZ PERFORMANCE)
-- Kỹ thuật: Đo lường chất lượng câu hỏi, tính điểm trung bình có trọng số theo danh mục
-- và tỷ lệ đỗ kỳ thi (Pass Rate >= 70% số câu đúng).
-- ==============================================================================
-- name: R03_quiz_performance
SELECT 
    c.category,
    count(*)                                      AS attempts,       -- Tổng số lượt nộp bài thi
    sum(q.correct_count)                          AS correct_answers, -- Tổng số câu trả lời đúng
    sum(q.total_questions)                        AS questions,      -- Tổng số câu hỏi trong đề
    round(100.0 * sum(q.correct_count) / sum(q.total_questions), 2) AS weighted_score_pct, -- Điểm chuẩn hóa (%)
    round(100.0 * sum(q.is_passed) / count(*), 2) AS pass_pct        -- Tỷ lệ đỗ (%)
FROM gold.fact_quiz_attempts q 
JOIN gold.dim_course c ON q.course_sk = c.course_sk
GROUP BY c.category 
ORDER BY c.category;


-- ==============================================================================
-- R04: THỜI GIAN ĐÓNG VAI KÉP (ROLE-PLAYING DATE DIMENSIONS)
-- Kỹ thuật: Bảng gold.dim_date được JOIN 2 lần độc lập vào bảng fact_enrollments:
--   - Lần 1 (ed): Chiều thời gian ghi danh (enrolled_date_sk)
--   - Lần 2 (cd): Chiều thời gian tốt nghiệp (completed_date_sk)
-- Đo lường số ngày trung bình để một học viên hoàn thành khóa học qua hàm dateDiff.
-- ==============================================================================
-- name: R04_role_playing_dates
SELECT 
    ed.year                                       AS enrollment_year, -- Năm đăng ký học
    cd.year                                       AS completion_year, -- Năm tốt nghiệp
    count(*)                                      AS completed_enrollments, -- Số lượt đã tốt nghiệp
    avg(dateDiff('day', e.enrolled_at, e.completed_at)) AS average_days_to_complete -- Số ngày học trung bình
FROM gold.fact_enrollments e
JOIN gold.dim_date ed ON e.enrolled_date_sk = ed.date_sk
JOIN gold.dim_date cd ON e.completed_date_sk = cd.date_sk
WHERE e.is_completed = 1 
GROUP BY ed.year, cd.year 
ORDER BY ed.year, cd.year;


-- ==============================================================================
-- R05: BÁO CÁO THEO ĐỊA PHƯƠNG THEO DẤU VẾT LỊCH SỬ (SCD TYPE 2 ACCURACY)
-- Kỹ thuật: Nhờ phép toán ASOF JOIN khi nạp Gold, mỗi lượt ghi danh được gắn chính xác
-- vào thành phố mà học viên đang cư trú TẠI THỜI ĐIỂM ĐĂNG KÝ, bảo toàn tính chân thực lịch sử.
-- ==============================================================================
-- name: R05_historical_city
SELECT 
    d.year,
    u.city,                                       -- Thành phố của học viên tại thời điểm ghi danh
    count(*)                                      AS enrollments,    -- Lượt đăng ký
    sum(e.is_completed)                           AS completed       -- Lượt tốt nghiệp
FROM gold.fact_enrollments e 
JOIN gold.dim_date d ON e.enrolled_date_sk = d.date_sk
JOIN gold.dim_user u ON e.user_sk = u.user_sk
GROUP BY d.year, u.city 
ORDER BY d.year, u.city;


-- ==============================================================================
-- R06: TOP 10 KHÓA HỌC DOANH THU CAO NHẤT MỖI QUÝ (WINDOW FUNCTION RANKING)
-- Kỹ thuật: Sử dụng hàm cửa sổ ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)
-- để xếp hạng độc lập các khóa học có doanh thu cao nhất trong từng quý.
-- ==============================================================================
-- name: R06_top_courses_rank
WITH revenue AS (
    SELECT 
        d.year,
        d.quarter,
        c.course_id,
        c.title,
        sum(f.net_vnd) AS net_vnd
    FROM gold.fact_payments f 
    JOIN gold.dim_date d ON f.date_sk = d.date_sk
    JOIN gold.dim_course c ON f.course_sk = c.course_sk
    GROUP BY d.year, d.quarter, c.course_id, c.title
), ranked AS (
    SELECT 
        *,
        row_number() OVER (
            PARTITION BY year, quarter 
            ORDER BY net_vnd DESC, course_id
        ) AS rank
    FROM revenue
)
SELECT * FROM ranked 
WHERE rank <= 10 
ORDER BY year, quarter, rank;


-- ==============================================================================
-- R07: PHÂN TÍCH ĐỐI CHIẾU DOANH THU & GHI DANH (FACT-TO-FACT DRILL ACROSS)
-- Kỹ thuật: Đỉnh cao của mô hình Galaxy Schema theo chuẩn Ralph Kimball.
-- Kết nối 2 quy trình kinh doanh độc lập (Fact Doanh Thu & Fact Ghi Danh) thông qua
-- 2 chiều dùng chung (Conformed Dimensions: dim_course và dim_date) bằng kỹ thuật Full Outer Union.
-- ==============================================================================
-- name: R07_revenue_enrollment_drill_across
WITH revenue AS (
    -- Tổng hợp doanh thu theo khóa học và ngày
    SELECT course_sk, date_sk, sum(net_vnd) AS net_vnd 
    FROM gold.fact_payments 
    GROUP BY course_sk, date_sk
), enrollment AS (
    -- Tổng hợp số lượt ghi danh theo khóa học và ngày
    SELECT course_sk, enrolled_date_sk AS date_sk, count(*) AS enrollments
    FROM gold.fact_enrollments 
    GROUP BY course_sk, enrolled_date_sk
), keys AS (
    -- Hợp nhất tập hợp các cặp khóa chung từ cả 2 quy trình
    SELECT course_sk, date_sk FROM revenue 
    UNION DISTINCT 
    SELECT course_sk, date_sk FROM enrollment
)
SELECT 
    d.year,
    d.month,
    c.category,
    sum(coalesce(r.net_vnd, 0))                   AS net_vnd,        -- Doanh thu thuần từ fact_payments
    sum(coalesce(e.enrollments, 0))               AS enrollments     -- Lượt đăng ký từ fact_enrollments
FROM keys k 
LEFT JOIN revenue r ON k.course_sk = r.course_sk AND k.date_sk = r.date_sk
LEFT JOIN enrollment e ON k.course_sk = e.course_sk AND k.date_sk = e.date_sk
JOIN gold.dim_date d ON k.date_sk = d.date_sk 
JOIN gold.dim_course c ON k.course_sk = c.course_sk
GROUP BY d.year, d.month, c.category 
ORDER BY d.year, d.month, c.category;


-- ==============================================================================
-- R08: CẮT LÁT VÀ XẺ KHỐI DỮ LIỆU ĐA CHIỀU (SLICE & DICE)
-- Kỹ thuật: Cắt lát (Slice) năm 2024 và Quý 1, 2; Xẻ khối (Dice) danh mục 'Data' & 'Programming'.
-- ==============================================================================
-- name: R08_slice_dice
SELECT 
    d.year,
    d.quarter,
    c.category,
    c.difficulty,
    sum(p.net_vnd) AS net_vnd
FROM gold.fact_payments p 
JOIN gold.dim_date d ON p.date_sk = d.date_sk
JOIN gold.dim_course c ON p.course_sk = c.course_sk
WHERE d.year = 2024 
  AND d.quarter IN (1, 2) 
  AND c.category IN ('Data', 'Programming')
GROUP BY d.year, d.quarter, c.category, c.difficulty 
ORDER BY d.quarter, c.category, c.difficulty;


-- ==============================================================================
-- R09: KHỐI LẬP PHƯƠNG ĐA CHIỀU TOÀN PHẦN (MULTIDIMENSIONAL CUBE)
-- Kỹ thuật: Mệnh đề CUBE tính toán toàn bộ 2^3 = 8 tổ hợp phân nhóm giữa Năm, Danh mục
-- và Hình thức thanh toán. ClickHouse yêu cầu CAST LowCardinality sang String khi dùng CUBE.
-- ==============================================================================
-- name: R09_cube
SELECT 
    d.year,
    CAST(c.category AS String)                    AS category,
    CAST(m.method_name AS String)                 AS method_name,
    sum(p.net_vnd)                                AS net_vnd
FROM gold.fact_payments p 
JOIN gold.dim_date d ON p.date_sk = d.date_sk
JOIN gold.dim_course c ON p.course_sk = c.course_sk
JOIN gold.dim_payment_method m ON p.method_sk = m.method_sk
GROUP BY CUBE(d.year, CAST(c.category AS String), CAST(m.method_name AS String)) 
ORDER BY d.year, category, method_name;


-- ==============================================================================
-- R10: PHÂN TÍCH ĐƯỜNG CONG THỜI LƯỢNG HỌC TẬP (LEARNING PROGRESSION CURVE)
-- Kỹ thuật: Đo lường thời gian tương tác thực tế của học viên trên từng vị trí bài học (từ 1 đến 10).
-- ==============================================================================
-- name: R10_learning_time
SELECT 
    c.category,
    l.position,                                   -- Thứ tự bài học trong khóa (Bài 1 -> Bài 10)
    count(*)                                      AS completions,    -- Số lượt học viên hoàn tất bài học
    sum(f.time_spent_seconds)                     AS seconds,        -- Tổng số giây học tập tích lũy
    round(avg(f.time_spent_seconds), 2)           AS average_seconds -- Thời lượng học trung bình mỗi bài (giây)
FROM gold.fact_lesson_completions f 
JOIN gold.dim_lesson l ON f.lesson_sk = l.lesson_sk
JOIN gold.dim_course c ON f.course_sk = c.course_sk
GROUP BY c.category, l.position 
ORDER BY c.category, l.position;
