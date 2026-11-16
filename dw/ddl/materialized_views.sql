CREATE TABLE gold.mv_monthly_revenue_summary
ENGINE = SummingMergeTree ORDER BY month AS
SELECT toYYYYMM(paid_at) AS month, sum(net_vnd) AS net_vnd,
 sum(original_vnd) AS gmv, sum(discount_vnd) AS discount_vnd,
 sum(charged_vnd * refunded) AS refund_vnd, sum(refunded) AS refunds, count() AS payments
FROM gold.fact_payments GROUP BY month;
CREATE TABLE gold.mv_course_completion_stats
ENGINE = SummingMergeTree ORDER BY course_sk AS
SELECT course_sk, count() AS enrollments, sum(is_completed) AS completions,
 sum(ifNull(dateDiff('day', enrolled_at, completed_at),0)) AS completion_days
FROM gold.fact_enrollments GROUP BY course_sk;

