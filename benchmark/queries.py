"""
==================================================================================
MODULE ĐỊNH NGHĨA 7 TRUY VẤN ĐỐI CHUẨN HIỆU NĂNG (BENCHMARK QUERIES TEMPLATES: Q1-Q7)
==================================================================================
Mục tiêu:
  - Cung cấp 7 mẫu câu truy vấn SQL phân tích chuẩn (Portable SQL Templates)
    có thể thực thi độc lập trên cả 2 hệ quản trị cơ sở dữ liệu:
      1. ClickHouse Gold (`{db} = 'gold'`)
      2. PostgreSQL Mirror (`{db} = 'benchmark'`)
  - Nguyên tắc đối chuẩn công bằng (Fair Benchmark Principle):
      + Không sử dụng bất kỳ bảng tổng hợp sẵn nào (No Pre-aggregated shortcuts/views).
      + Cả 2 hệ thống đều phải truy vấn trực tiếp trên cùng các bảng Fact và Dimension cơ sở.
      + Cú pháp SQL được chuẩn hóa để trả về tập kết quả giống hệt nhau từng dòng (Identical Results).

Danh mục 7 kịch bản kiểm thử:
  - Q1: Aggregation & Group By cơ bản (Doanh thu theo tháng)
  - Q2: Slicing & Dicing (Lọc theo quý và độ khó khóa học)
  - Q3: 4-Way Star Join (Phép nối hình sao 4 chiều: Date, Course, Instructor, Method)
  - Q4: Window Function (Tính tổng doanh thu lũy kế dồn tích Running Total)
  - Q5: Multi-dimensional CUBE (Khối lập phương đa chiều Năm & Danh mục)
  - Q6: Fact-to-Fact Drill Across (Phân tích đối chiếu giữa 2 bảng Fact Doanh thu & Ghi danh)
  - Q7: Full Table Scan & High-cardinality DISTINCT (Quét hàng triệu dòng hoàn thành bài học
        kết hợp đếm số lượng học viên phân biệt COUNT(DISTINCT user_id)).
==================================================================================
"""

QUERIES = {
    # --------------------------------------------------------------------------
    # Q1: DOANH THU THEO THÁNG (BASIC AGGREGATION & JOIN)
    # Kiểm tra tốc độ quét bảng Fact giao dịch và phép JOIN đơn giản với Dimension thời gian.
    # --------------------------------------------------------------------------
    "Q1_monthly_revenue": """SELECT d.year, d.month, count(*) AS payments, sum(f.net_vnd) AS net_vnd
FROM {db}.fact_payments f 
JOIN {db}.dim_date d ON f.date_sk = d.date_sk
GROUP BY d.year, d.month 
ORDER BY d.year, d.month""",

    # --------------------------------------------------------------------------
    # Q2: CẮT LÁT DANH MỤC & ĐỘ KHÓ (SLICING & DICING)
    # Đo lường hiệu quả của chỉ mục và bộ lọc phạm vi ngày trong Quý 1/2024.
    # --------------------------------------------------------------------------
    "Q2_slice_category": """SELECT c.category, sum(f.net_vnd) AS net_vnd, sum(f.refunded) AS refunds
FROM {db}.fact_payments f 
JOIN {db}.dim_course c ON f.course_sk = c.course_sk
WHERE f.date_sk BETWEEN 20240101 AND 20240331 
  AND c.difficulty IN ('beginner', 'intermediate')
GROUP BY c.category 
ORDER BY c.category""",

    # --------------------------------------------------------------------------
    # Q3: PHÉP NỐI 4 CHIỀU HÌNH SAO (4-WAY STAR SCHEMA JOIN)
    # Kiểm tra năng lực xử lý phép JOIN đồng thời 4 bảng Dimension với bảng Fact 500k dòng.
    # --------------------------------------------------------------------------
    "Q3_four_dimensions": """SELECT d.year, c.category, i.expertise, m.method_name,
       count(*) AS transactions, sum(f.net_vnd) AS net_vnd
FROM {db}.fact_payments f 
JOIN {db}.dim_date d ON f.date_sk = d.date_sk
JOIN {db}.dim_course c ON f.course_sk = c.course_sk
JOIN {db}.dim_instructor i ON f.instructor_sk = i.instructor_sk
JOIN {db}.dim_payment_method m ON f.method_sk = m.method_sk
GROUP BY d.year, c.category, i.expertise, m.method_name 
ORDER BY d.year, c.category, i.expertise, m.method_name""",

    # --------------------------------------------------------------------------
    # Q4: TÍNH TỔNG DỒN TÍCH BẰNG HÀM CỬA SỔ (WINDOW FUNCTION RUNNING TOTAL)
    # Kiểm tra hiệu năng thực thi phép toán phân tích thứ tự thời gian theo năm.
    # --------------------------------------------------------------------------
    "Q4_window_running_total": """WITH monthly AS (
    SELECT d.year, d.month, sum(f.net_vnd) AS revenue 
    FROM {db}.fact_payments f
    JOIN {db}.dim_date d ON f.date_sk = d.date_sk 
    GROUP BY d.year, d.month
)
SELECT year, month, revenue, 
       sum(revenue) OVER (PARTITION BY year ORDER BY month ROWS UNBOUNDED PRECEDING) AS running_revenue
FROM monthly 
ORDER BY year, month""",

    # --------------------------------------------------------------------------
    # Q5: KHỐI LẬP PHƯƠNG ĐA CHIỀU (MULTIDIMENSIONAL CUBE)
    # Kiểm tra khả năng gom nhóm đa mức tổ hợp giữa Năm và Danh mục môn học.
    # --------------------------------------------------------------------------
    "Q5_cube": """SELECT d.year, CAST(c.category AS TEXT) AS category, 
       sum(f.net_vnd) AS net_vnd, count(*) AS transactions
FROM {db}.fact_payments f 
JOIN {db}.dim_date d ON f.date_sk = d.date_sk
JOIN {db}.dim_course c ON f.course_sk = c.course_sk
GROUP BY CUBE(d.year, CAST(c.category AS TEXT)) 
ORDER BY d.year, category""",

    # --------------------------------------------------------------------------
    # Q6: PHÂN TÍCH ĐỐI CHIẾU 2 BẢNG SỰ KIỆN (FACT-TO-FACT DRILL ACROSS)
    # Ghép nối độc lập Fact Doanh thu và Fact Ghi danh trên cùng chiều Dim Course.
    # --------------------------------------------------------------------------
    "Q6_drill_across": """WITH revenue AS (
    SELECT course_sk, sum(net_vnd) AS net_vnd 
    FROM {db}.fact_payments 
    GROUP BY course_sk
),
enrollment AS (
    SELECT course_sk, count(*) AS enrollments, sum(is_completed) AS completed
    FROM {db}.fact_enrollments 
    GROUP BY course_sk
)
SELECT c.course_id, c.category, r.net_vnd, e.enrollments, e.completed 
FROM revenue r
JOIN enrollment e ON r.course_sk = e.course_sk 
JOIN {db}.dim_course c ON r.course_sk = c.course_sk
ORDER BY c.course_id""",

    # --------------------------------------------------------------------------
    # Q7: QUÉT TOÀN BỘ BẢNG LỚN & ĐẾM PHÂN BIỆT (FULL SCAN & COUNT DISTINCT)
    # Thử thách nặng nhất: Quét bảng fact_lesson_completions (> 3 triệu dòng),
    # tính tổng thời lượng và đếm số lượng học viên duy nhất (COUNT DISTINCT user_id).
    # --------------------------------------------------------------------------
    "Q7_learning_full_scan": """SELECT c.category, count(*) AS completed_lessons,
       sum(f.time_spent_seconds) AS learning_seconds, 
       count(DISTINCT u.user_id) AS distinct_learners
FROM {db}.fact_lesson_completions f 
JOIN {db}.dim_course c ON f.course_sk = c.course_sk
JOIN {db}.dim_user u ON f.user_sk = u.user_sk 
GROUP BY c.category 
ORDER BY c.category""",
}
