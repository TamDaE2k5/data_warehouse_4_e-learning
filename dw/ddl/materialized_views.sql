-- ==============================================================================
-- BẢNG TỔNG HỢP TIỀN TÍNH TOÁN DÙNG SUMMINGMERGETREE (MATERIALIZED SUMMARY TABLES)
-- ==============================================================================
-- Hệ quản trị: ClickHouse Server 24.8 LTS | Database: gold
-- Mục tiêu:
--   - Tạo các bảng đệm tổng hợp sẵn số liệu (Pre-aggregated Summary Tables) phục vụ các
--     Dashboard giám đốc và Báo cáo quản trị (R01, R04) với tốc độ phản hồi tính bằng mili-giây (< 5ms).
--   - Sử dụng Engine đặc thù của ClickHouse: `SummingMergeTree`:
--       + Khác với Materialized View truyền thống của Oracle/PostgreSQL đòi hỏi REFRESH toàn bộ
--         tốn nhiều phút, `SummingMergeTree` tự động cộng dồn các cột số đo (numeric metrics)
--         trong nền (Background Merge) mỗi khi có dữ liệu mới được chèn vào.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. BẢNG TỔNG HỢP DOANH THU & HOÀN TIỀN THEO THÁNG (MV_MONTHLY_REVENUE_SUMMARY)
-- Phục vụ Báo cáo R01 (Executive Financial Summary) và R04 (Doanh thu theo thời gian).
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.mv_monthly_revenue_summary
ENGINE = SummingMergeTree 
ORDER BY month AS
SELECT 
    toYYYYMM(paid_at)               AS month,        -- Khóa sắp xếp: Tháng thanh toán (YYYYMM)
    sum(net_vnd)                    AS net_vnd,      -- Doanh thu thuần sau hoàn tiền
    sum(original_vnd)               AS gmv,          -- Tổng giá trị giao dịch gộp (Gross Merchandise Value)
    sum(discount_vnd)               AS discount_vnd, -- Tổng tiền giảm giá khuyến mãi
    sum(charged_vnd * refunded)     AS refund_vnd,   -- Tổng số tiền đã hoàn trả cho học viên
    sum(refunded)                   AS refunds,      -- Tổng số lượt giao dịch bị hoàn tiền
    count()                         AS payments      -- Tổng số lượng giao dịch thanh toán
FROM gold.fact_payments 
GROUP BY month;

-- ------------------------------------------------------------------------------
-- 2. BẢNG TỔNG HỢP TIẾN ĐỘ & TỶ LỆ HOÀN THÀNH KHÓA HỌC (MV_COURSE_COMPLETION_STATS)
-- Phục vụ Báo cáo R02 (Phân tích hiệu quả đào tạo) và R03 (Khóa học giữ chân học viên tốt nhất).
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gold.mv_course_completion_stats
ENGINE = SummingMergeTree 
ORDER BY course_sk AS
SELECT 
    course_sk                       AS course_sk,    -- Khóa sắp xếp: Khóa thay thế của khóa học
    count()                         AS enrollments,  -- Tổng số lượt ghi danh khóa học
    sum(is_completed)               AS completions,  -- Tổng số học viên đã tốt nghiệp hoàn thành khóa
    sum(ifNull(dateDiff('day', enrolled_at, completed_at), 0)) AS completion_days -- Tổng số ngày để tốt nghiệp
FROM gold.fact_enrollments 
GROUP BY course_sk;
