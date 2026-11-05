-- ==============================================================================
-- CẦU TRUYỀN PHÁT DỮ LIỆU TỰ ĐỘNG VÀO BẢNG TỔNG HỢP (MATERIALIZED VIEW FEEDS)
-- ==============================================================================
-- Hệ quản trị: ClickHouse Server 24.8 LTS | Database: gold
-- Mục tiêu:
--   - Đóng vai trò là Triggers truyền phát dòng dữ liệu (Stream Ingestion Trigger):
--       + Bất cứ khi nào có bản ghi mới được nạp vào bảng Fact (`fact_payments`, `fact_enrollments`),
--         ClickHouse sẽ tự động tính toán tổng hợp sơ bộ (Partial Aggregates) và đẩy vào
--         bảng đích `SummingMergeTree` tương ứng (`TO gold.mv_*`).
--   - Mẫu thiết kế phân tách chuyên nghiệp của ClickHouse:
--       + Bảng lưu trữ (Storage): `gold.mv_monthly_revenue_summary` (chịu trách nhiệm lưu trữ và gộp số liệu).
--       + Cầu nạp (Feed Trigger): `gold.feed_monthly_revenue` (chỉ phụ trách hứng sự kiện INSERT).
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. CẦU TRUYỀN PHÁT TỔNG HỢP DOANH THU HÀNG THÁNG (FEED_MONTHLY_REVENUE)
-- Bắt mọi sự kiện nạp vào gold.fact_payments để cập nhật ngay vào bảng mv_monthly_revenue_summary.
-- ------------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS gold.feed_monthly_revenue 
TO gold.mv_monthly_revenue_summary AS
SELECT 
    toYYYYMM(paid_at)               AS month,        -- Tháng thanh toán
    sum(net_vnd)                    AS net_vnd,      -- Tổng doanh thu thuần
    sum(original_vnd)               AS gmv,          -- Tổng giá trị giao dịch gộp (GMV)
    sum(discount_vnd)               AS discount_vnd, -- Tổng tiền chiết khấu
    sum(charged_vnd * refunded)     AS refund_vnd,   -- Tổng số tiền hoàn trả
    sum(refunded)                   AS refunds,      -- Số lượt hoàn tiền
    count()                         AS payments      -- Số lượng giao dịch
FROM gold.fact_payments 
GROUP BY month;

-- ------------------------------------------------------------------------------
-- 2. CẦU TRUYỀN PHÁT TIẾN ĐỘ & TỶ LỆ HOÀN THÀNH KHÓA HỌC (FEED_COURSE_COMPLETION)
-- Bắt mọi sự kiện nạp vào gold.fact_enrollments để cập nhật ngay vào bảng mv_course_completion_stats.
-- ------------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS gold.feed_course_completion 
TO gold.mv_course_completion_stats AS
SELECT 
    course_sk                       AS course_sk,    -- Mã định danh khóa học
    count()                         AS enrollments,  -- Tổng số lượt ghi danh
    sum(is_completed)               AS completions,  -- Số học viên tốt nghiệp hoàn thành khóa
    sum(ifNull(dateDiff('day', enrolled_at, completed_at), 0)) AS completion_days -- Tổng số ngày tích lũy để tốt nghiệp
FROM gold.fact_enrollments 
GROUP BY course_sk;
