# TẬP LỆNH THỰC THI BẠCH HÓA CHƯƠNG 3 (COMMANDS PLAYBOOK)
> File hướng dẫn chi tiết bản chất kỹ thuật: [huong_dan_thuc_thi_chuong_3.md](file:///run/media/tamdae/04C8A69DC8A68C8C/Users/LENOVO/Documents/TL_Kỳ_1_năm_4/Data_Warehouse/rebuild/huong_dan_thuc_thi_chuong_3.md)

```bash
# ==============================================================================
# BƯỚC 0: CHUYỂN VÀO THƯ MỤC DỰ ÁN VÀ KHỞI ĐỘNG HẠ TẦNG
# ==============================================================================
cd /run/media/tamdae/04C8A69DC8A68C8C/Users/LENOVO/Documents/TL_Kỳ_1_năm_4/Data_Warehouse/rebuild

# 0.1 Khởi động các container PostgreSQL và ClickHouse
docker compose up -d --wait postgres clickhouse

# 0.2 Build image runner và dashboard
docker compose build runner dashboard

# ==============================================================================
# BƯỚC 1: TRUY CẬP TRỰC TIẾP VÀO CÁC SERVICE ĐỂ XEM BẢNG & SCHEMA
# ==============================================================================
# Vào PostgreSQL OLTP:
# docker compose exec -it postgres psql -U learning -d learning_oltp
# Lệnh bên trong: \dn (xem schema), \dt oltp.* (xem bảng), \d oltp.users, \q (thoát)

# Vào PostgreSQL Staging:
# docker compose exec -it postgres psql -U learning_stage -d dwh_staging
# Lệnh bên trong: \dn (xem staging, silver, quarantine), \dt silver.*, \q (thoát)

# Vào ClickHouse Gold:
# docker compose exec -it clickhouse clickhouse-client -u learning --password local_learning_demo -d gold
# Lệnh bên trong: SHOW TABLES; DESCRIBE TABLE fact_payments; exit (thoát)

# ==============================================================================
# BƯỚC 2: KHỞI TẠO CSDL VÀ DỰNG NỀN TẢNG (BASELINE)
# ==============================================================================
# 2.1 Cài đặt Schema và sinh 5.72M dòng dữ liệu mẫu ban đầu
docker compose run --rm runner python cli.py setup
docker compose run --rm runner python cli.py generate --enrollments 500000 --seed 2024

# 2.2 Thống kê số dòng trên các bảng tác nghiệp nguồn (OLTP)
docker compose exec postgres psql -U learning -d learning_oltp -c "
SELECT table_name, to_char(reltuples::bigint, '999,999,999') AS estimated_rows
FROM information_schema.tables t
JOIN pg_class c ON c.relname = t.table_name
WHERE table_schema = 'oltp'
ORDER BY reltuples DESC;
"

# 2.3 Nạp mẻ toàn phần ban đầu (Full Load)
docker compose run --rm runner python cli.py pipeline --mode full

# 2.4 Xem mốc Watermark ban đầu trong PostgreSQL Staging
docker compose exec postgres psql -U learning_stage -d dwh_staging -c "
SELECT table_name, last_processed_time, last_processed_id, last_run_id 
FROM staging.etl_watermarks 
ORDER BY table_name;
"

# 2.5 Kiểm tra sức khỏe toàn diện hệ thống (Doctor Diagnostics)
docker compose run --rm runner python cli.py doctor

# ==============================================================================
# BƯỚC 3: THỰC NGHIỆM ĐỢT 1 (BATCH 1 - NẠP AN TOÀN 100 BẢN GHI/BẢNG)
# ==============================================================================
# 3.1 Kiểm tra TRƯỚC khi nạp Đợt 1
docker compose exec postgres psql -U learning -d learning_oltp -c "SELECT count(*) AS oltp_quiz_before FROM oltp.quiz_attempts;"
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "SELECT count(*) AS gold_quiz_before FROM gold.fact_quiz_attempts;"
docker compose exec postgres psql -U learning_stage -d dwh_staging -c "SELECT count(*) AS quarantine_before FROM quarantine.quarantine_records;"

# 3.2 Nạp Batch 1 vào OLTP
docker compose run --rm runner python demo/load_dataset_to_oltp.py --batch 1

# 3.3 Chạy pipeline nạp tăng dần
docker compose run --rm runner python cli.py pipeline --mode incremental

# 3.4 Kiểm tra SAU khi nạp Đợt 1 (Gold tăng đúng +100 dòng, Watermark cập nhật, Quarantine = 0)
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "SELECT count(*) AS gold_quiz_after_batch1 FROM gold.fact_quiz_attempts;"
docker compose exec postgres psql -U learning_stage -d dwh_staging -c "SELECT table_name, last_processed_time, last_processed_id FROM staging.etl_watermarks WHERE table_name = 'quiz_attempts';"
docker compose exec postgres psql -U learning_stage -d dwh_staging -c "SELECT count(*) AS quarantine_after_batch1 FROM quarantine.quarantine_records;"

# ==============================================================================
# BƯỚC 4: THỰC NGHIỆM ĐỢT 2 (BATCH 2 - KHỬ TRÙNG LẶP & REPLACINGMERGETREE)
# ==============================================================================
# 4.1 Kiểm tra TRƯỚC khi nạp Đợt 2
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "SELECT count(*) AS gold_quiz_before_batch2 FROM gold.fact_quiz_attempts;"

# 4.2 Nạp Batch 2 vào OLTP (gồm 50 dòng MỚI + 50 dòng TRÙNG ID Đợt 1 + 50 payments hoàn tiền)
docker compose run --rm runner python demo/load_dataset_to_oltp.py --batch 2

# 4.3 Chạy pipeline nạp tăng dần (Nguồn trích xuất 100 dòng quiz)
docker compose run --rm runner python cli.py pipeline --mode incremental

# 4.4 Kiểm tra SAU khi nạp Đợt 2 (Khử trùng lặp: Gold chỉ tăng đúng +50 dòng mới!)
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT count(*) AS gold_quiz_after_batch2_dedup FROM gold.fact_quiz_attempts FINAL;
"

# 4.5 Soi chi tiết 1 bản ghi bị trùng lặp (attempt_id = 1010001): chỉ giữ duy nhất 1 bản mới nhất
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT attempt_id, user_sk, correct_count, time_spent_seconds, is_passed 
FROM gold.fact_quiz_attempts 
FINAL 
WHERE attempt_id = 1010001;
"

# ==============================================================================
# BƯỚC 5: THỰC NGHIỆM ĐỢT 3 (BATCH 3 - TIÊM DỮ LIỆU BẨN & CÁCH LY QUARANTINE)
# ==============================================================================
# 5.1 Kiểm tra TRƯỚC khi nạp Đợt 3
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "SELECT count(*) AS users_before FROM gold.dim_user;"
docker compose exec postgres psql -U learning_stage -d dwh_staging -c "SELECT count(*) AS quarantine_before FROM quarantine.quarantine_records;"

# 5.2 Nạp Batch 3 vào OLTP (gồm 50 học viên sạch + 5 học viên email sai cú pháp + 50 quiz sạch)
docker compose run --rm runner python demo/load_dataset_to_oltp.py --batch 3

# 5.3 Chạy pipeline nạp tăng dần (Pipeline KHÔNG CRASH!)
docker compose run --rm runner python cli.py pipeline --mode incremental

# 5.4 KIỂM CHỨNG CÂU HỎI 1: Liệu 5 học viên lỗi có lọt vào Gold? (Kỳ vọng: 0)
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT count(*) AS leaked_bad_records FROM gold.dim_user WHERE user_id BETWEEN 50191 AND 50195;
"

# 5.5 KIỂM CHỨNG CÂU HỎI 2: 5 bản ghi lỗi đang bị giam giữ ở đâu? (Kỳ vọng: bắt gọn 5 lỗi)
docker compose exec postgres psql -U learning_stage -d dwh_staging -P pager=off -x -c "
SELECT table_name, source_id, error_code, rejection_reason, raw_payload, detected_at
FROM quarantine.quarantine_records
WHERE source_id BETWEEN 50191 AND 50195;
"

# 5.6 KIỂM CHỨNG CÂU HỎI 3: Dữ liệu sạch có vào Gold bình thường? (Kỳ vọng: +50 users, +50 quiz)
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "SELECT count(*) AS users_after FROM gold.dim_user;"

# ==============================================================================
# BƯỚC 6: CHẠY TRỰC TIẾP 7 TRUY VẤN PHÂN TÍCH (Q1 - Q7) TRONG CLICKHOUSE
# ==============================================================================
# Mở ClickHouse Client để thực thi các câu truy vấn:
# docker compose exec -it clickhouse clickhouse-client -u learning --password local_learning_demo -d gold

# Hoặc chạy nhanh từng câu từ Terminal:

# Q1: Doanh thu theo tháng
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT d.year, d.month, count(*) AS payments, sum(f.net_vnd) AS net_vnd
FROM gold.fact_payments f JOIN gold.dim_date d ON f.date_sk = d.date_sk
GROUP BY d.year, d.month ORDER BY d.year, d.month;
"

# Q2: Cắt lát Quý 1/2024 & Độ khó
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT c.category, sum(f.net_vnd) AS net_vnd, sum(f.refunded) AS refunds
FROM gold.fact_payments f JOIN gold.dim_course c ON f.course_sk = c.course_sk
WHERE f.date_sk BETWEEN 20240101 AND 20240331 AND c.difficulty IN ('beginner', 'intermediate')
GROUP BY c.category ORDER BY c.category;
"

# Q3: Phép nối hình sao 4 chiều
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT d.year, c.category, i.expertise, m.method_name, count(*) AS transactions, sum(f.net_vnd) AS net_vnd
FROM gold.fact_payments f 
JOIN gold.dim_date d ON f.date_sk = d.date_sk
JOIN gold.dim_course c ON f.course_sk = c.course_sk
JOIN gold.dim_instructor i ON f.instructor_sk = i.instructor_sk
JOIN gold.dim_payment_method m ON f.method_sk = m.method_sk
GROUP BY d.year, c.category, i.expertise, m.method_name 
ORDER BY d.year, c.category, i.expertise, m.method_name LIMIT 10;
"

# Q4: Window Function tính doanh thu dồn tích (Running Total)
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "
WITH monthly AS (
    SELECT d.year, d.month, sum(f.net_vnd) AS revenue FROM gold.fact_payments f
    JOIN gold.dim_date d ON f.date_sk = d.date_sk GROUP BY d.year, d.month
)
SELECT year, month, revenue, sum(revenue) OVER (PARTITION BY year ORDER BY month ROWS UNBOUNDED PRECEDING) AS running_revenue
FROM monthly ORDER BY year, month;
"

# Q5: Khối CUBE đa chiều Năm & Danh mục
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT d.year, CAST(c.category AS String) AS category, sum(f.net_vnd) AS net_vnd, count(*) AS transactions
FROM gold.fact_payments f 
JOIN gold.dim_date d ON f.date_sk = d.date_sk
JOIN gold.dim_course c ON f.course_sk = c.course_sk
GROUP BY CUBE(d.year, CAST(c.category AS String)) ORDER BY d.year, category;
"

# Q6: Fact-to-Fact Drill Across (Doanh thu vs Ghi danh)
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "
WITH revenue AS( SELECT course_sk, sum(net_vnd) AS net_vnd FROM gold.fact_payments GROUP BY course_sk),
    enrollment AS(SELECT course_sk, count(*) AS total_enrollments FROM gold.fact_enrollments GROUP BY course_sk)
SELECT c.course_id, c.title, c.category, coalesce(r.net_vnd, 0) AS revenue, coalesce(e.total_enrollments, 0) AS enrollments
FROM gold.dim_course AS c LEFT JOIN revenue AS r ON c.course_sk = r.course_sk
LEFT JOIN enrollment AS e ON c.course_sk = e.course_sk
ORDER BY revenue DESC LIMIT 10;
"

# Q7: Quét toàn bảng 3.6 triệu bản ghi học bài & Đếm học viên duy nhất
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT c.category, count(*) AS total_completions, count(DISTINCT f.user_sk) AS active_students, round(sum(f.time_spent_seconds) / 3600.0, 1) AS total_study_hours
FROM gold.fact_lesson_completions f
JOIN gold.dim_course c ON f.course_sk = c.course_sk
GROUP BY c.category ORDER BY total_completions DESC;
"

# ==============================================================================
# BƯỚC 7: KHỞI ĐỘNG VÀ KHÁM PHÁ DASHBOARD STREAMLIT (PORTAL PHÂN TÍCH)
# ==============================================================================
# 7.1 Khởi động dịch vụ Dashboard trên cổng 8501
docker compose --profile demo up -d --wait dashboard

# 7.2 Mở trình duyệt Web tại địa chỉ:
# http://localhost:8501

# 7.3 Các tab chức năng trên Dashboard:
# - Overview: Tổng quan doanh thu, lượt ghi danh, bài học hoàn thành, lượt thi quiz
# - Finance: Phân tích doanh thu thuần, chiết khấu, tỷ lệ hoàn tiền theo kênh & giảng viên
# - Learning: Tỷ lệ hoàn thành theo khóa học, phân bố thời gian học tập thực tế
# - Quizzes: Đánh giá chất lượng đề thi, tỷ lệ đỗ (pass rate), số lần thử lại
# - Markets: Phân bố học viên theo thành phố/quốc gia theo lịch sử SCD Type 2
# - Quality & Operations: Trạng thái 116 chỉ tiêu kiểm toán, nhật ký nạp, vùng Quarantine

# ==============================================================================
# BƯỚC 8: CHẠY BỘ KIỂM THỬ TỰ ĐỘNG & ĐO KIỂM BENCHMARK
# ==============================================================================
# 8.1 Xuất 10 báo cáo chiến lược ra file CSV
docker compose run --rm runner python cli.py reports

# 8.2 Chạy benchmark đo tốc độ ClickHouse vs PostgreSQL
docker compose run --rm runner python cli.py benchmark --runs 5

# 8.3 Chạy bộ kiểm thử toàn diện
docker compose run --rm runner pytest tests/

# ==============================================================================
# BƯỚC 9: DỌN DẸP HẠ TẦNG KHI KẾT THÚC
# ==============================================================================
# Dừng container nhưng giữ lại dữ liệu volume:
# docker compose --profile demo stop

# Hoặc xóa sạch container & mạng (nếu muốn reset):
# docker compose --profile demo down
```
