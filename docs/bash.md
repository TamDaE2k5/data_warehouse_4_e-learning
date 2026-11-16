# 🧭 CẨM NANG TOÀN DIỆN CÁC LỆNH BASH & SQL HỆ THỐNG DATA WAREHOUSE
> **Dành cho Quản trị viên, Kỹ sư Dữ liệu và Người vận hành**  
> *Đặc tả định dạng:* Mỗi mục gồm mô tả ngắn gọn chức năng. Bên dưới là khối lệnh Bash có **dòng trống (Enter) ở đầu** để bạn copy-paste thẳng vào Terminal mà không bị dính vào dấu nhắc lệnh prompt.

---

## 📑 MỤC LỤC NHANH

1. [Quản Trị Hạ Tầng & Container Docker](#1-quản-trị-hạ-tầng--container-docker)
2. [Điều Hành Chu Trình Dữ Liệu Qua CLI (Setup, Pipeline, Validate, Benchmark)](#2-điều-hành-chu-trình-dữ-liệu-qua-cli)
3. [Khám Phá & Truy Vấn PostgreSQL (OLTP & Staging)](#3-khám-phá--truy-vấn-postgresql-oltp--staging)
4. [Khám Phá & Truy Vấn ClickHouse (Gold Data Warehouse)](#4-khám-phá--truy-vấn-clickhouse-gold-data-warehouse)
5. [Kiểm Thử Nghiệm Thu & Thử Nghiệm Chịu Lỗi (Resilience & Unit Tests)](#5-kiểm-thử-nghiệm-thu--thử-nghiệm-chịu-lỗi)
6. [Các Lệnh SQL Báo Cáo Phân Tích Nghiệp Vụ (SQL Business Reports)](#6-các-lệnh-sql-báo-cáo-phân-tích-nghiệp-vụ)
7. [Soi Chiến Lược Thực Thi Truy Vấn Của 2 Bên (Execution Plan: PostgreSQL vs ClickHouse)](#7-soi-chiến-lược-thực-thi-truy-vấn-của-2-bên)

---

## 1. QUẢN TRỊ HẠ TẦNG & CONTAINER DOCKER

### 1.1 Khởi động các dịch vụ cơ sở dữ liệu (PostgreSQL & ClickHouse)
Khởi động 2 container ở chế độ nền và chờ đến khi đạt trạng thái hoàn toàn sẵn sàng (`healthy`):
```bash

docker compose up -d --wait postgres clickhouse
```

---

### 1.2 Build lại môi trường thực thi lệnh Python (Runner)
Cập nhật mã nguồn và cài đặt lại môi trường runner khi có thay đổi code:
```bash

docker compose build runner
```

---

### 1.3 Kiểm tra trạng thái và sức khỏe của các container
Xem danh sách container đang chạy, cổng ánh xạ và trạng thái healthcheck:
```bash

docker compose ps
```

---

### 1.4 Xem log thời gian thực của ClickHouse
Theo dõi log hoạt động của máy chủ ClickHouse (bấm `Ctrl + C` để thoát):
```bash

docker compose logs -f --tail=100 clickhouse
```

---

### 1.5 Xem log thời gian thực của PostgreSQL
Theo dõi log kết nối và giao dịch của máy chủ PostgreSQL:
```bash

docker compose logs -f --tail=100 postgres
```

---

### 1.6 Xem tài nguyên RAM và CPU đang tiêu thụ thực tế
Giám sát mức tiêu thụ RAM, CPU của các container đang hoạt động:
```bash

docker stats
```

---

### 1.7 Khởi động lại một container cụ thể (ví dụ ClickHouse)
Restart container nhanh chóng khi cần làm mới dịch vụ:
```bash

docker compose restart clickhouse
```

---

### 1.8 Tạm dừng toàn bộ hệ thống (Giữ nguyên dữ liệu trên ổ đĩa)
Dừng tất cả container, dữ liệu trong volume vẫn được bảo toàn nguyên vẹn:
```bash

docker compose stop
```

---

### 1.9 Hạ toàn bộ container (Giữ nguyên volume dữ liệu)
Tắt và xóa các container trung gian nhưng bảo lưu 100% dữ liệu:
```bash

docker compose down
```

---

### 1.10 Vào thẳng terminal bash bên trong container ClickHouse
Mở shell bash trực tiếp bên trong hệ điều hành của container ClickHouse:
```bash

docker exec -it online-learning-dw-clickhouse-1 clickhouse-client -u learning --password local_learning_demo -d gold
```

---

### 1.11 Vào thẳng bên trong container PostgreSQL
Mở shell bash trực tiếp bên trong hệ điều hành của container PostgreSQL:
```bash

docker exec -it online-learning-dw-postgres-1 psql -U learning -d postgres
```

---

## 2. ĐIỀU HÀNH CHU TRÌNH DỮ LIỆU QUA CLI

### 2.1 Khởi tạo hạ tầng, cơ sở dữ liệu và 3 roles phân quyền (Setup)
Tạo 2 database (`learning_oltp`, `dwh_staging`), cài đặt trigger mốc thời gian và 3 tài khoản RBAC:
```bash

docker compose run --rm runner python cli.py setup
```

---

### 2.2 Sinh tập dữ liệu tác nghiệp mẫu (~5.72 triệu bản ghi sự kiện)
Sinh dữ liệu giả lập 500k lượt ghi danh bằng thư viện Faker và NumPy vector hóa:
```bash

docker compose run --rm runner python cli.py generate --enrollments 500000 --seed 2024
```

---

### 2.3 Chạy toàn bộ luồng ETL nạp dữ liệu từ đầu (Pipeline Full Mode)
Trích xuất OLTP $\rightarrow$ Staging $\rightarrow$ Silver $\rightarrow$ Dựng kho bóng ClickHouse $\rightarrow$ Công bố Gold:
```bash

docker compose run --rm runner python cli.py pipeline --mode full
```

---

### 2.4 Chạy luồng nạp tăng dần các bản ghi mới (Pipeline Incremental Mode)
Chỉ quét dữ liệu phát sinh qua mốc Watermark và tái sử dụng phân vùng cũ (ATTACH PARTITION):
```bash

docker compose run --rm runner python cli.py pipeline --mode incremental
```

---

### 2.5 Kích hoạt cổng kiểm toán chất lượng tự động (116 Quality Checks)
Đối soát ranh giới SCD2, kiểm tra khớp doanh thu từng xu, kiểm tra tính duy nhất:
```bash

docker compose run --rm runner python cli.py validate
```

---

### 2.6 Xuất 10 báo cáo phân tích quản trị nghiệp vụ (R01–R10 sang CSV)
Thực thi các câu truy vấn đa chiều và lưu kết quả vào thư mục `artifacts/reports/`:
```bash

docker compose run --rm runner python cli.py reports
```

---

### 2.7 Chạy đo kiểm đối chuẩn hiệu năng Benchmark (Chế độ nhanh mặc định)
Nhân bản dữ liệu sang PostgreSQL `benchmark`, đối soát 100% số lượng dòng và kết quả truy vấn Q1–Q7 (bỏ qua băm SHA-256 từng dòng để tiết kiệm tài nguyên trên máy local):
```bash

docker compose run --rm runner python cli.py benchmark --runs 3
```

---

### 2.8 Chạy Benchmark siêu tốc (Tái sử dụng bản sao đối chiếu đã có)
Bỏ qua bước copy dữ liệu, tái sử dụng schema `benchmark` trên PostgreSQL và đo tốc độ ngay lập tức trong 2–3 giây:
```bash

docker compose run --rm runner python cli.py benchmark --reuse-mirror --runs 3
```

---

### 2.9 Chạy Benchmark kiểm toán mã băm SHA-256 toàn phần (Tùy chọn)
Quét toàn bộ hơn 11 triệu bản ghi ở cả hai bên và so khớp mã băm SHA-256 từng dòng (dùng cho báo cáo kiểm toán mật mã học):
```bash

docker compose run --rm runner python cli.py benchmark --runs 3 --full-hash
```

---

### 2.10 Chạy toàn bộ chu trình khép kín tự động (All-in-One)
Thực hiện liên hoàn: Sinh dữ liệu $\rightarrow$ Pipeline Full $\rightarrow$ Xuất 10 báo cáo $\rightarrow$ Đo Benchmark:
```bash

docker compose run --rm runner python cli.py all
```

---

## 3. KHÁM PHÁ & TRUY VẤN POSTGRESQL (OLTP & STAGING)

### 3.1 Đăng nhập psql vào cơ sở dữ liệu tác nghiệp nguồn (`learning_oltp`)
Vào shell tương tác của PostgreSQL database tác nghiệp bằng tài khoản quản trị `learning`:
```bash

docker exec -it online-learning-dw-postgres-1 psql -U learning -d learning_oltp
```

---

### 3.2 Đăng nhập psql vào cơ sở dữ liệu trung chuyển (`dwh_staging`)
Vào shell tương tác của database Staging (nơi chứa schema `silver`, `quarantine`, `benchmark`):
```bash

docker exec -it online-learning-dw-postgres-1 psql -U learning -d dwh_staging
```

---

### 3.3 Xem danh sách tất cả các bảng trong schema `oltp`
Kiểm tra cấu trúc 11 bảng tác nghiệp nguồn:
```bash

docker exec online-learning-dw-postgres-1 psql -U learning -d learning_oltp -c "\dt oltp.*"
```

---

### 3.4 Xem danh sách tất cả các bảng trong schema `silver`
Kiểm tra 11 bảng sạch của tầng trung chuyển Staging:
```bash

docker exec online-learning-dw-postgres-1 psql -U learning -d dwh_staging -c "\dt silver.*"
```

---

### 3.5 Đếm số dòng thực tế của các bảng nguồn tác nghiệp OLTP
Thống kê số lượng bản ghi của các bảng nguồn chính:
```bash

docker exec online-learning-dw-postgres-1 psql -U learning -d learning_oltp -c "
SELECT 'users' AS bang, count(*) AS so_dong FROM oltp.users
UNION ALL SELECT 'user_history', count(*) FROM oltp.user_history
UNION ALL SELECT 'courses', count(*) FROM oltp.courses
UNION ALL SELECT 'enrollments', count(*) FROM oltp.enrollments
UNION ALL SELECT 'payments', count(*) FROM oltp.payments
UNION ALL SELECT 'lesson_completions', count(*) FROM oltp.lesson_completions
UNION ALL SELECT 'quiz_attempts', count(*) FROM oltp.quiz_attempts;
"
```

---

### 3.6 Tra cứu các bản ghi lỗi bị bắt vào trạm kiểm dịch (Quarantine)
Xem chi tiết các dòng dữ liệu bẩn bị hệ thống chặn đứng kèm mã lỗi:
```bash

docker exec online-learning-dw-postgres-1 psql -U learning -d dwh_staging -c "
SELECT table_name, source_id, error_code, rejection_reason, detected_at, raw_payload 
FROM quarantine.quarantine_records 
ORDER BY detected_at DESC 
LIMIT 5;
"
```

---

### 3.7 Kiểm tra trạng thái các mốc phân thủy nạp tăng dần (Watermarks)
Xem mốc thời gian cập nhật lớn nhất của từng bảng đã được nạp ở mẻ trước:
```bash

docker exec online-learning-dw-postgres-1 psql -U learning -d dwh_staging -c "
SELECT table_name, last_processed_time, last_processed_id, last_run_id 
FROM staging.etl_watermarks;
"
```

---

### 3.8 Thử nghiệm kiểm tra quyền Read-Only của tài khoản ETL đọc nguồn
Xác nhận tài khoản `learning_reader` chỉ có quyền SELECT và bị từ chối lệnh UPDATE:
```bash

docker exec online-learning-dw-postgres-1 psql -U learning_reader -d learning_oltp -c "
UPDATE oltp.users SET full_name = 'Hacked' WHERE user_id = 1;
"
```
*(Kết quả kỳ vọng: Báo lỗi `ERROR: permission denied for table users`)*.

---

## 4. KHÁM PHÁ & TRUY VẤN CLICKHOUSE (GOLD DATA WAREHOUSE)

### 4.1 Đăng nhập vào ClickHouse Client (Giao diện dòng lệnh tương tác)
Vào thẳng shell `clickhouse-client` tại database `gold`:
```bash

docker exec -it online-learning-dw-clickhouse-1 clickhouse-client -u learning --password local_learning_demo -d gold
```

---

### 4.2 Thống kê số dòng thực tế của toàn bộ các bảng trong kho Gold
Xem bảng nào có bao nhiêu triệu dòng, sắp xếp theo dung lượng giảm dần:
```bash

docker exec online-learning-dw-clickhouse-1 clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT table, total_rows 
FROM system.tables 
WHERE database = 'gold' 
ORDER BY total_rows DESC 
FORMAT PrettyCompact;
"
```

---

### 4.3 Xem chi tiết 1 dòng dữ liệu thanh toán theo chiều dọc (Không bị tràn màn hình)
Sử dụng toán tử `\G` để đọc chi tiết toàn bộ các cột:
```bash

docker exec online-learning-dw-clickhouse-1 clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT * FROM fact_payments LIMIT 1 \G
"
```

---

### 4.4 Xem 5 dòng đầu tiên của bảng khóa học (Kẻ bảng ô đẹp mắt)
Hiển thị dạng bảng rút gọn bằng `FORMAT PrettyCompact`:
```bash

docker exec online-learning-dw-clickhouse-1 clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT course_sk, title, category, difficulty, price_vnd 
FROM dim_course 
LIMIT 5 
FORMAT PrettyCompact;
"
```

---

### 4.5 Tra cứu lịch sử đổi chỗ ở của Học viên số 5 (SCD Type 2)
Kiểm tra 2 phiên bản địa chỉ cư trú của học viên chuyển nhà ngày 01/07/2023:
```bash

docker exec online-learning-dw-clickhouse-1 clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT user_sk, user_id, full_name, city, valid_from, valid_to, is_current 
FROM dim_user 
WHERE user_id = 5 
FORMAT PrettyCompact;
"
```

---

### 4.6 Kiểm tra dung lượng và tỷ lệ nén cột trên ổ đĩa của ClickHouse
Xem dung lượng byte thực tế lưu trên đĩa so với dữ liệu gốc chưa nén:
```bash

docker exec online-learning-dw-clickhouse-1 clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT 
    table,
    formatReadableSize(sum(data_compressed_bytes)) AS dung_luong_nen,
    formatReadableSize(sum(data_uncompressed_bytes)) AS dung_luong_goc,
    round(sum(data_uncompressed_bytes) / sum(data_compressed_bytes), 2) AS he_so_nen
FROM system.parts 
WHERE database = 'gold' AND active 
GROUP BY table 
ORDER BY sum(data_compressed_bytes) DESC 
FORMAT PrettyCompact;
"
```

---

## 5. KIỂM THỬ NGHIỆM THU & THỬ NGHIỆM CHỊU LỖI

### 5.1 Chạy kịch bản kiểm thử nghiệm thu tự động tích hợp (E2E Verifier)
Tự động xác minh quyền Read-Only, bơm dữ liệu bẩn, kích hoạt Quarantine và kiểm tra tính bất biến:
```bash

docker compose run --rm runner python -m demo.verify_v2
```

---

### 5.2 Bơm 10.000 bản ghi làm bài thi trắc nghiệm đến muộn (Late-Arriving Facts)
Tạo dữ liệu thử nghiệm tăng dần với `attempt_number = 99` vào OLTP:
```bash

docker compose run --rm runner python -m demo.seed_incremental --attempt-number 99
```

---

### 5.3 Nạp bộ dữ liệu thực nghiệm ĐỢT 1: An toàn ban đầu (100% Sạch)
Nạp 100 bản ghi mẫu vào OLTP rồi chạy pipeline tăng dần sang Gold:
```bash

docker compose run --rm runner python demo/load_dataset_to_oltp.py --batch data/batch_1
docker compose run --rm runner python cli.py pipeline --mode incremental
```

---

### 5.4 Nạp bộ dữ liệu thực nghiệm ĐỢT 2: Kiểm thử nạp tăng dần & khử trùng lặp
Bơm dữ liệu mới kèm 50% bản ghi trùng lặp (ReplacingMergeTree tự động khử trùng):
```bash

docker compose run --rm runner python demo/load_dataset_to_oltp.py --batch data/batch_2
docker compose run --rm runner python cli.py pipeline --mode incremental
```

---

### 5.5 Nạp bộ dữ liệu thực nghiệm ĐỢT 3: Cố ý tiêm dữ liệu bẩn & cách ly lỗi
Bơm 5 bản ghi sai email (Zero-Crash, dữ liệu bẩn bị tóm gọn vào Quarantine):
```bash

docker compose run --rm runner python demo/load_dataset_to_oltp.py --batch data/batch_3
docker compose run --rm runner python cli.py pipeline --mode incremental
```

---

### 5.6 Chạy toàn bộ bộ kiểm thử tự động Python Unit Tests
Thực thi kiểm tra Schema Guard, ranh giới SCD2 từng giây và tính chẵn lẻ CUBE:
```bash

docker compose run --rm runner python -m unittest discover tests
```

---

## 6. CÁC LỆNH SQL BÁO CÁO PHÂN TÍCH NGHIỆP VỤ

*(Bạn có thể copy các câu lệnh này chạy thẳng trong Terminal hoặc paste vào Web UI `http://localhost:58123/play`)*.

### 6.1 Báo cáo R01: Doanh thu theo Tháng và Năm (Roll-up / Drill-down)
```bash

docker exec online-learning-dw-clickhouse-1 clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT 
    d.year AS nam,
    d.month AS thang,
    count() AS so_giao_dich,
    sum(f.net_vnd) AS doanh_thu_thuan_vnd,
    sum(f.refunded) AS so_don_hoan_tien
FROM fact_payments f 
JOIN dim_date d ON f.date_sk = d.date_sk
GROUP BY nam, thang 
ORDER BY nam, thang
LIMIT 12
FORMAT PrettyCompact;
"
```

---

### 6.2 Báo cáo R02: Cắt lát & Xẻ khối (Slice & Dice: Năm 2024, Ngành Data & Programming)
```bash

docker exec online-learning-dw-clickhouse-1 clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT 
    c.category AS nganh_hoc,
    c.difficulty AS cap_do,
    count() AS so_giao_dich,
    sum(f.net_vnd) AS doanh_thu_vnd
FROM fact_payments f
JOIN dim_course c ON f.course_sk = c.course_sk
WHERE f.date_sk BETWEEN 20240101 AND 20241231
  AND c.category IN ('Data', 'Programming')
GROUP BY nganh_hoc, cap_do
ORDER BY doanh_thu_vnd DESC
FORMAT PrettyCompact;
"
```

---

### 6.3 Báo cáo R03: Bảng xoay ma trận doanh thu (Pivot Table: Phương thức $\times$ Danh mục)
```bash

docker exec online-learning-dw-clickhouse-1 clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT 
    c.category AS danh_muc,
    sumIf(f.net_vnd, m.method_name = 'bank_transfer') AS ck_ngan_hang,
    sumIf(f.net_vnd, m.method_name = 'card') AS the_tin_dung,
    sumIf(f.net_vnd, m.method_name = 'wallet') AS vi_dien_tu,
    sum(f.net_vnd) AS tong_doanh_thu
FROM fact_payments f
JOIN dim_course c ON f.course_sk = c.course_sk
JOIN dim_payment_method m ON f.method_sk = m.method_sk
GROUP BY danh_muc
ORDER BY tong_doanh_thu DESC
FORMAT PrettyCompact;
"
```

---

### 6.4 Báo cáo R04: Khối lập phương đa chiều gom nhóm CUBE
```bash

docker exec online-learning-dw-clickhouse-1 clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT 
    d.year AS nam,
    CAST(c.category AS String) AS danh_muc,
    sum(f.net_vnd) AS doanh_thu_vnd,
    count() AS so_don_hang
FROM fact_payments f 
JOIN dim_date d ON f.date_sk = d.date_sk
JOIN dim_course c ON f.course_sk = c.course_sk
GROUP BY CUBE(d.year, CAST(c.category AS String)) 
ORDER BY nam, danh_muc
LIMIT 15
FORMAT PrettyCompact;
"
```

---

### 6.5 Báo cáo R05: Doanh thu tích lũy dồn tích theo thời gian (Running Total)
```bash

docker exec online-learning-dw-clickhouse-1 clickhouse-client -u learning --password local_learning_demo -d gold --query "
WITH doanh_thu_thang AS (
    SELECT 
        d.year AS nam, 
        d.month AS thang, 
        sum(f.net_vnd) AS doanh_thu
    FROM fact_payments f
    JOIN dim_date d ON f.date_sk = d.date_sk 
    GROUP BY nam, thang
)
SELECT 
    nam, 
    thang, 
    doanh_thu,
    sum(doanh_thu) OVER (PARTITION BY nam ORDER BY thang ROWS UNBOUNDED PRECEDING) AS doanh_thu_tich_luy
FROM doanh_thu_thang 
ORDER BY nam, thang
LIMIT 12
FORMAT PrettyCompact;
"
```

---

### 6.6 Báo cáo R06: Đối chiếu chéo 2 Fact độc lập (Fact-to-Fact Drill Across)
Nối song song Doanh thu và Số lượng ghi danh thực tế của từng khóa học:
```bash

docker exec online-learning-dw-clickhouse-1 clickhouse-client -u learning --password local_learning_demo -d gold --query "
WITH rev AS (
    SELECT course_sk, sum(net_vnd) AS doanh_thu 
    FROM fact_payments 
    GROUP BY course_sk
),
enr AS (
    SELECT course_sk, count() AS tong_hoc_vien, sum(is_completed) AS tot_nghiep 
    FROM fact_enrollments 
    GROUP BY course_sk
)
SELECT 
    c.title AS ten_khoa_hoc,
    c.category AS danh_muc,
    r.doanh_thu AS doanh_thu_vnd,
    e.tong_hoc_vien,
    e.tot_nghiep,
    round(e.tot_nghiep * 100.0 / e.tong_hoc_vien, 1) AS ty_le_tot_nghiep_pct
FROM rev r
JOIN enr e ON r.course_sk = e.course_sk 
JOIN dim_course c ON r.course_sk = c.course_sk
ORDER BY r.doanh_thu DESC
LIMIT 10
FORMAT PrettyCompact;
"
```

---

### 6.7 Báo cáo R07: Đánh giá tỷ lệ thi trắc nghiệm Đỗ/Trượt theo danh mục môn học
```bash

docker exec online-learning-dw-clickhouse-1 clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT 
    c.category AS danh_muc,
    count() AS tong_luot_thi,
    sum(q.is_passed) AS so_luot_do,
    count() - sum(q.is_passed) AS so_luot_truot,
    round(sum(q.is_passed) * 100.0 / count(), 2) AS ty_le_do_pct,
    round(avg(q.time_spent_seconds) / 60, 1) AS phut_lam_bai_tb
FROM fact_quiz_attempts q
JOIN dim_course c ON q.course_sk = c.course_sk
GROUP BY danh_muc
ORDER BY ty_le_do_pct ASC
FORMAT PrettyCompact;
"
```

---

## 7. SOI CHIẾN LƯỢC THỰC THI TRUY VẤN CỦA 2 BÊN

### 7.1 Bên PostgreSQL: Dùng `EXPLAIN ANALYZE`
Chạy thực tế và in ra toàn bộ cây chi phí, bộ nhớ RAM, số worker CPU:
```bash

docker exec online-learning-dw-postgres-1 psql -U learning -d dwh_staging -c "
EXPLAIN (ANALYZE, BUFFERS, TIMING)
SELECT d.year, d.month, count(*) AS payments, sum(f.net_vnd) AS net_vnd
FROM benchmark.fact_payments f 
JOIN benchmark.dim_date d ON f.date_sk = d.date_sk
GROUP BY d.year, d.month 
ORDER BY d.year, d.month;
"
```

---

### 7.2 Bên ClickHouse: Chế độ `EXPLAIN PLAN` (Xem cây logic & Index/Granules)
Kiểm tra xem ClickHouse có đọc đúng phân vùng và mốc chỉ mục Granules hay không:
```bash

docker exec online-learning-dw-clickhouse-1 clickhouse-client -u learning --password local_learning_demo -d gold --query "
EXPLAIN PLAN indexes=1
SELECT d.year, d.month, count(*) AS payments, sum(f.net_vnd) AS net_vnd
FROM gold.fact_payments f 
JOIN gold.dim_date d ON f.date_sk = d.date_sk
GROUP BY d.year, d.month 
ORDER BY d.year, d.month;
"
```

---

### 7.3 Bên ClickHouse: Chế độ `EXPLAIN PIPELINE` (Soi đường ống luồng đa nhân)
Xem số luồng CPU xử lý song song (`× 4`) trên các khối vector dữ liệu:
```bash

docker exec online-learning-dw-clickhouse-1 clickhouse-client -u learning --password local_learning_demo -d gold --query "
EXPLAIN PIPELINE
SELECT d.year, d.month, count(*) AS payments, sum(f.net_vnd) AS net_vnd
FROM gold.fact_payments f 
JOIN gold.dim_date d ON f.date_sk = d.date_sk
GROUP BY d.year, d.month 
ORDER BY d.year, d.month;
"
```

---

### 7.4 Bên ClickHouse: Chế độ `EXPLAIN ESTIMATE` (Dự toán tài nguyên trước khi chạy)
Ước tính số dòng và số block (granules) phải đọc từ đĩa mà không tốn tài nguyên chạy thật:
```bash

docker exec online-learning-dw-clickhouse-1 clickhouse-client -u learning --password local_learning_demo -d gold --query "
EXPLAIN ESTIMATE
SELECT d.year, d.month, count(*) AS payments, sum(f.net_vnd) AS net_vnd
FROM gold.fact_payments f 
JOIN gold.dim_date d ON f.date_sk = d.date_sk
GROUP BY d.year, d.month 
ORDER BY d.year, d.month;
"
```

---

### 7.5 Bên ClickHouse: Chế độ `EXPLAIN SYNTAX` (Xem Compiler tối ưu lại câu lệnh)
Xem cách trình biên dịch ClickHouse tự động sắp xếp lại các mệnh đề để đạt tốc độ cao nhất:
```bash

docker exec online-learning-dw-clickhouse-1 clickhouse-client -u learning --password local_learning_demo -d gold --query "
EXPLAIN SYNTAX
SELECT d.year, d.month, count(*) AS payments, sum(f.net_vnd) AS net_vnd
FROM gold.fact_payments f 
JOIN gold.dim_date d ON f.date_sk = d.date_sk
GROUP BY d.year, d.month 
ORDER BY d.year, d.month;
"
```
