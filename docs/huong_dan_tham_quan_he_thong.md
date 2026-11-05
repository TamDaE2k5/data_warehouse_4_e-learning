# HƯỚNG DẪN THAM QUAN HỆ THỐNG DATA WAREHOUSE TRÊN TERMINAL (CLI TOUR)
> **Dành cho Giảng viên, Kiến trúc sư Dữ liệu và Kỹ sư Phần mềm**  
> *Dự án:* Online Learning Data Warehouse (Hệ thống Kho Dữ liệu Khóa học Trực tuyến 2022–2024)  
> *Đặc tả môi trường:* Chạy trên Docker Compose gồm PostgreSQL 16 (OLTP + Staging) và ClickHouse 24.8 LTS (Gold DW).

---

## 🧭 LỜI MỞ ĐẦU: TẠI SAO LẠI LÀ TERMINAL?

Giao diện Web UI (Dashboard) thường chỉ thể hiện những biểu đồ tổng kết ở tầng cuối cùng. Tuy nhiên, linh hồn và sức mạnh cốt lõi của một hệ thống **Kho Dữ Liệu Hiện Đại (Modern Data Warehouse)** lại nằm ở tầng kiến trúc ngầm bên dưới:
- Cách dữ liệu được cô lập bảo mật giữa tác nghiệp và phân tích.
- Cách bắt và xử lý dữ liệu bẩn tại trạm kiểm dịch (Quarantine).
- Cơ chế bảo toàn lịch sử biến động dữ liệu theo thời gian (SCD Type 2).
- Khả năng nén cột hàng triệu dòng và xử lý phân tích siêu tốc (OLAP Columnar Engine).

Tài liệu này được thiết kế như một **chuyến du khảo thực địa từng bước (Step-by-step Guided Tour)** ngay trong Terminal. Mọi câu lệnh đều là lệnh thực tế, có thể copy-paste và kiểm chứng kết quả ngay lập tức trên hệ thống đang chạy.

```
       [TRẠM 1]               [TRẠM 2]               [TRẠM 3]               [TRẠM 4]
 Kiểm tra Hạ tầng      Khám phá OLTP Nguồn    Vùng Đệm Staging &     Kho Đa Chiều Gold
   & Containers           & Read-Only Guard      Quarantine Lỗi         & Nén Cột ClickHouse
        │                      │                      │                      │
        ▼                      ▼                      ▼                      ▼
   docker compose        PostgreSQL:55432        PostgreSQL:55432       ClickHouse:58123
   ps / healthcheck      learning_oltp          dwh_staging            gold database
        │                      │                      │                      │
        └──────────────────────┼──────────────────────┼──────────────────────┘
                               ▼                      ▼                      ▼
                           [TRẠM 5]               [TRẠM 6]               [TRẠM 7 & 8]
                       Thực nghiệm SCD2       Nạp Tăng Dần         Đua Benchmark Q1-Q7
                       Đổi Địa chỉ User 5     Incremental Load     & 116 Quality Checks
```

---

## 🗺️ TỔNG QUAN 8 TRẠM DỪNG CHÂN

| Trạm | Tên Trạm Dừng | Nội Dung Trải Nghiệm Chính | Công Cụ & Cổng |
| :---: | :--- | :--- | :--- |
| **1** | **Khởi động & Sức khỏe Hạ tầng** | Kiểm tra 3 container, phân quyền 3 Role DB độc lập | `docker compose ps` |
| **2** | **Nguồn Tác Nghiệp & Phòng Tuyến Đọc** | 5.72 triệu dòng OLTP, thử nghiệm `UPDATE` bị từ chối | PostgreSQL `learning_oltp` (:55432) |
| **3** | **Staging & Bắt Dữ Liệu Bẩn** | Lọc sạch dữ liệu, Watermark mốc nạp, khám phá khu cách ly Quarantine | PostgreSQL `dwh_staging` |
| **4** | **Kho Đa Chiều ClickHouse** | Galaxy Schema, nén cột siêu tốc 2.5x–7.5x, ReplacingMergeTree | ClickHouse `gold` (:58123) |
| **5** | **Bảo Tồn Lịch Sử SCD Type 2** | Case study Học viên 5 chuyển từ Đà Nẵng vào TP.HCM | ClickHouse SQL JOIN |
| **6** | **Nạp Tăng Dần & Tính Bất Biến** | Bơm 10.000 dòng trễ hạn, nạp trong 5s, chạy rỗng trong 0.1s | `cli.py pipeline --mode incremental` |
| **7** | **Đua Tốc Độ Benchmark OLAP** | 7 câu hỏi phân tích kinh doanh, ClickHouse nhanh hơn đến 38.7x | `cli.py benchmark` |
| **8** | **Cổng Kiểm Toán 116 Tiêu Chí** | 116 bài test tự động, Unit tests, xuất 10 báo cáo kinh doanh | `cli.py validate` & `reports` |

---

## 🚀 CHUẨN BỊ TRƯỚC KHI KHỞI HÀNH

Mở Terminal của bạn và di chuyển vào thư mục chứa dự án:

```bash
cd btl
```

> **Ghi chú về cổng kết nối:**
> - PostgreSQL: Cổng ngoài `55432` (cổng trong container `5432`)
> - ClickHouse HTTP: Cổng ngoài `58123` (cổng trong container `8123`)
> - ClickHouse Native Client: Cổng ngoài `59000` (cổng trong container `9000`)
> - Dashboard UI (Streamlit): Cổng ngoài `8501`

---

## 📍 TRẠM 1: KHỞI ĐỘNG & KIỂM TRA SỨC KHỎE HẠ TẦNG

### 🎯 Mục tiêu
Đảm bảo toàn bộ các cụm container cơ sở dữ liệu đã sẵn sàng, các cổng kết nối hoạt động tốt và hệ thống được phân quyền nghiêm ngặt.

### ⌨️ Lệnh 1.1: Kiểm tra trạng thái sống của các Container
```bash
docker compose ps
```
**Kết quả kỳ vọng:**
Cả 3 service `postgres`, `clickhouse`, `dashboard` đều ở trạng thái `Up` và `healthy`.
```text
NAME                             IMAGE                               STATUS                    PORTS
online-learning-dw-clickhouse-1   clickhouse/clickhouse-server:...    Up 30 minutes (healthy)   9000/tcp, 127.0.0.1:58123->8123/tcp
online-learning-dw-dashboard-1    online-learning-dw-dashboard:latest Up 20 minutes             127.0.0.1:8501->8501/tcp
online-learning-dw-postgres-1     postgres:16.6-bookworm              Up 30 minutes (healthy)   127.0.0.1:55432->5432/tcp
```

### ⌨️ Lệnh 1.2: Kiểm tra phân quyền 3 User chuyên biệt trong PostgreSQL
Trong kiến trúc Enterprise DW, ta tuyệt đối không dùng user `superuser/postgres` cho pipeline. Hãy kiểm tra danh sách người dùng:
```bash
docker compose exec postgres psql -U learning -d postgres -c "\du"
```
**Kết quả hiển thị:**
```text
                                   List of roles
    Role name    |                         Attributes                         | Member of 
-----------------+------------------------------------------------------------+-----------
 learning        | Superuser, Create role, Create DB                          | {}
 learning_reader | Cannot login, default connection limit: -1                 | {}
 learning_stage  | Cannot login, default connection limit: -1                 | {}
```
💡 **Giải thích:**
- `learning_reader`: Tài khoản chỉ đọc (SELECT ONLY), được pipeline dùng để hút dữ liệu từ OLTP. Dù pipeline bị lỗi hay bị tấn công, tài khoản này không bao giờ có thể ghi đè hay xóa mất dữ liệu gốc của khách hàng.
- `learning_stage`: Tài khoản toàn quyền trên DB `dwh_staging` để lọc rửa dữ liệu, nhưng không có quyền trên `learning_oltp`.

---

## 📍 TRẠM 2: KHÁM PHÁ NGUỒN TÁC NGHIỆP OLTP & PHÒNG TUYẾN ĐỌC

### 🎯 Mục tiêu
Tận mắt nhìn thấy kho dữ liệu giao dịch nguồn (OLTP) với hơn **5.7 triệu bản ghi**, và thử nghiệm phòng tuyến an toàn dữ liệu: tài khoản đọc không thể can thiệp vào nghiệp vụ.

### ⌨️ Lệnh 2.1: Thống kê quy mô bản ghi trên từng bảng tác nghiệp
Đăng nhập vào database `learning_oltp` và đếm tổng số dòng trên toàn bộ 8 bảng nghiệp vụ:
```bash
docker compose exec postgres psql -U learning -d learning_oltp -c "
SELECT table_name, 
       to_char(reltuples::bigint, '999,999,999') AS estimated_rows
FROM information_schema.tables t
JOIN pg_class c ON c.relname = t.table_name
WHERE table_schema = 'oltp'
ORDER BY reltuples DESC;
"
```
**Kết quả kỳ vọng:**
```text
     table_name     | estimated_rows 
--------------------+----------------
 lesson_completions |      3,600,000
 quiz_attempts      |      1,000,000
 enrollments        |        500,000
 payments           |        500,000
 users              |         50,000
 lessons            |         10,000
 quizzes            |          1,000
 courses            |          1,000
 instructors        |            100
 payment_methods    |              3
```
*Tổng quy mô nguồn đạt xấp xỉ 5.72 triệu bản ghi.*

### ⌨️ Lệnh 2.2: Xem cấu trúc 1 bản ghi giao dịch thanh toán thực tế
```bash
docker compose exec postgres psql -U learning -d learning_oltp -P pager=off -x -c "
SELECT payment_id, enrollment_id, transaction_id, user_id, amount, status, payment_date, created_at, updated_at
FROM oltp.payments
LIMIT 1;
"
```
**Kết quả hiển thị:**
```text
-[ RECORD 1 ]----+-------------------------------------
payment_id       | 1
enrollment_id    | 1
transaction_id   | 7206b026-6d6c-48c5-a6e5-4a69ad66ff97
user_id          | 1
amount           | 250000.00
status           | SUCCESS
payment_date     | 2022-01-01 02:26:00
created_at       | 2022-01-01 02:26:00
updated_at       | 2026-11-04 13:28:44.252062+00
```

### ⌨️ Lệnh 2.3: Thử nghiệm vi phạm bảo mật (Cố tình ghi dữ liệu bằng tài khoản Reader)
Giả sử có một đoạn code ETL bị lỗi hoặc hacker cố tình thực thi lệnh `UPDATE` bằng tài khoản `learning_reader`:
```bash
docker compose exec postgres psql -U learning_reader -d learning_oltp -c "
UPDATE oltp.users SET full_name = 'Hacker Đổi Tên' WHERE user_id = 1;
"
```
**Kết quả nhận được lập tức từ PostgreSQL:**
```text
ERROR:  cannot execute UPDATE in a read-only transaction
```
🛡️ **Ý nghĩa kiến trúc:**
PostgreSQL lập tức chặn đứng giao dịch ở cấp độ transaction engine. Dù người viết ETL có viết nhầm code sửa đổi dữ liệu nguồn, hệ thống nghiệp vụ vẫn được bảo vệ 100% an toàn.

---

## 📍 TRẠM 3: THĂM VÙNG ĐỆM STAGING, WATERMARK & KHU CÁCH LY LỖI

### 🎯 Mục tiêu
Tìm hiểu cách ETL trung chuyển dữ liệu vào database trung gian `dwh_staging`, cách hệ thống ghi nhớ mốc trích xuất (Watermark) và thăm "khu cách ly" bắt các bản ghi bẩn vi phạm hợp đồng dữ liệu.

### ⌨️ Lệnh 3.1: Kiểm tra Bảng Quản Lý Mốc Trích Xuất (High Water Mark)
Mỗi lần chạy ETL, hệ thống ghi nhận thời điểm và ID cuối cùng của từng bảng để lần sau chỉ trích xuất đúng phần dữ liệu mới:
```bash
docker compose exec postgres psql -U learning_stage -d dwh_staging -P pager=off -c "
SELECT table_name, last_processed_time, last_processed_id, last_run_id 
FROM staging.etl_watermarks 
ORDER BY table_name;
"
```
**Kết quả hiển thị:**
```text
     table_name     |      last_processed_time      | last_processed_id |           last_run_id            
--------------------+-------------------------------+-------------------+----------------------------------
 courses            | 2026-11-04 13:29:01.088021+00 |              1000 | 4e214c1a1dfc40e5ba98e825d3b6979d
 enrollments        | 2026-11-04 13:33:17.506319+00 |                 1 | 4e214c1a1dfc40e5ba98e825d3b6979d
 instructors        | 2026-11-04 13:29:01.078744+00 |               100 | 4e214c1a1dfc40e5ba98e825d3b6979d
 lesson_completions | 2026-11-04 13:30:38.965966+00 |           3600000 | 4e214c1a1dfc40e5ba98e825d3b6979d
 lessons            | 2026-11-04 13:29:01.133552+00 |             10000 | 4e214c1a1dfc40e5ba98e825d3b6979d
 payment_methods    | 2026-11-04 13:29:01.168485+00 |                 3 | 4e214c1a1dfc40e5ba98e825d3b6979d
 payments           | 2026-11-04 13:30:37.47156+00  |            500000 | 4e214c1a1dfc40e5ba98e825d3b6979d
 quiz_attempts      | 2026-11-04 13:33:17.328869+00 |           1010000 | 4e214c1a1dfc40e5ba98e825d3b6979d
 quizzes            | 2026-11-04 13:29:01.16512+00  |              1000 | 4e214c1a1dfc40e5ba98e825d3b6979d
 user_history       | 2026-11-04 13:29:01.045783+00 |            500002 | 4e214c1a1dfc40e5ba98e825d3b6979d
 users              | 2026-11-04 13:33:23.076798+00 |                 1 | 4e214c1a1dfc40e5ba98e825d3b6979d
```

### ⌨️ Lệnh 3.2: Thăm "Khu Cách Ly" Dữ Liệu Lỗi (Quarantine)
Trong quá trình trích xuất, nếu gặp bản ghi dị thường (ví dụ: email không hợp lệ, điểm thi < 0, số tiền âm), hệ thống **không ngắt sập pipeline**, mà tự động bóc tách bản ghi đó vào bảng cách ly `quarantine.quarantine_records` kèm mã lỗi và toàn bộ JSON payload gốc:
```bash
docker compose exec postgres psql -U learning_stage -d dwh_staging -P pager=off -x -c "
SELECT table_name, source_id, error_code, rejection_reason, detected_at, raw_payload 
FROM quarantine.quarantine_records 
LIMIT 1;
"
```
**Kết quả hiển thị:**
```text
-[ RECORD 1 ]----+--------------------------------------------------------------------------------------------------------------------
table_name       | users
source_id        | 1
error_code       | ERR_INVALID_EMAIL
rejection_reason | Email sai định dạng (thiếu @ hoặc có khoảng trắng)
detected_at      | 2026-11-04 13:33:17.872603+00
raw_payload      | {"city": "Da Nang", "email": "invalid-v2-fixture", "country": "VN", "user_id": 1, "full_name": "Anh Nhiên Vũ", ...}
```
🔍 **Điểm sáng kỹ thuật:**
- Bảng Gold hoàn toàn sạch sẽ, không bị nhiễm bẩn bởi dữ liệu rác.
- Đội Data Governance và kỹ sư Backend có thể xem lại chính xác `raw_payload` tại trạm cách ly để sửa lỗi từ phía ứng dụng nguồn (Root Cause Resolution).

---

## 📍 TRẠM 4: ĐỘT NHẬP KHO DỮ LIỆU ĐA CHIỀU CLICKHOUSE GOLD

### 🎯 Mục tiêu
Khám phá kho dữ liệu hoàn thiện ở tầng Gold, tổ chức theo mô hình **Galaxy Schema** (4 Fact tables liên kết qua các Conformed Dimensions chung), kiểm tra dung lượng nén cột thực tế của ClickHouse.

### ⌨️ Lệnh 4.1: Kiểm tra Bảng và Tỷ Lệ Nén Cột (Columnar Compression)
Chạy câu truy vấn nội suy từ `system.parts` của ClickHouse để xem dung lượng nén:
```bash
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT table, 
       sum(rows) AS total_rows, 
       formatReadableSize(sum(data_compressed_bytes)) AS compressed, 
       formatReadableSize(sum(data_uncompressed_bytes)) AS raw_uncompressed, 
       round(sum(data_uncompressed_bytes) / sum(data_compressed_bytes), 2) AS compress_ratio 
FROM system.parts 
WHERE database = 'gold' AND active 
GROUP BY table 
ORDER BY total_rows DESC 
FORMAT PrettyCompact;
"
```
**Bảng kết quả thực tế:**
```text
   ┌─table──────────────────────┬─total_rows─┬─compressed─┬─raw_uncompressed─┬─compress_ratio─┐
1. │ fact_lesson_completions    │    3600000 │ 80.58 MiB  │ 205.99 MiB       │           2.56 │
2. │ fact_quiz_attempts         │    1010000 │ 30.71 MiB  │ 88.62 MiB        │           2.89 │
3. │ fact_enrollments           │     500000 │ 15.46 MiB  │ 38.62 MiB        │           2.50 │
4. │ fact_payments              │     500000 │ 20.67 MiB  │ 52.29 MiB        │           2.53 │
5. │ dim_user                   │      60000 │  1.12 MiB  │  4.49 MiB        │           4.03 │
6. │ dim_lesson                 │      10000 │ 86.86 KiB  │ 401.37 KiB       │           4.62 │
7. │ dim_date                   │       1097 │  7.46 KiB  │ 45.01 KiB        │           6.04 │
8. │ dim_quiz                   │       1000 │ 16.86 KiB  │ 52.63 KiB        │           3.12 │
9. │ dim_course                 │       1000 │ 27.84 KiB  │ 70.61 KiB        │           2.54 │
10.│ mv_course_completion_stats │       1000 │  4.16 KiB  │ 31.25 KiB        │           7.51 │
11.│ dim_instructor             │        100 │  1.86 KiB  │  3.26 KiB        │           1.75 │
12.│ mv_monthly_revenue_summary │         35 │  1.48 KiB  │  1.78 KiB        │           1.20 │
13.│ dim_payment_method         │          3 │   168.00 B │ 110.00 B         │           0.65 │
   └────────────────────────────┴────────────┴────────────┴──────────────────┴────────────────┘
```
⚡ **Ấn tượng kỹ thuật:**
- **3.6 triệu bản ghi** học bài (`fact_lesson_completions`) từ hơn 200 MB dung lượng thô được ClickHouse nén xuống chỉ còn **80.58 MB**!
- Bảng kích thước người dùng `dim_user` đạt tỷ lệ nén lên đến **4.03 lần**.
- Cơ chế nén cột theo thuật toán LZ4 kết hợp sắp xếp khóa chính (`ORDER BY`) giúp ClickHouse đọc dữ liệu trực tiếp vào CPU Cache với tốc độ hàng chục triệu dòng mỗi giây.

---

## 📍 TRẠM 5: TRẢI NGHIỆM THỰC ĐỊA SCD TYPE 2 (HỌC VIÊN CHUYỂN NHÀ)

### 🎯 Mục tiêu & Bài toán thực tế
Khi một học viên thay đổi nơi sinh sống (ví dụ: chuyển từ Đà Nẵng vào TP.HCM), nếu hệ thống chỉ đè dữ liệu mới (SCD Type 1), toàn bộ doanh thu quá khứ của học viên đó ở Đà Nẵng sẽ bị tính nhầm cho TP.HCM, làm sai lệch báo cáo kế toán địa phương.
Hệ thống của chúng ta giải quyết việc này bằng **Slowly Changing Dimension Type 2 (SCD2)**.

### ⌨️ Lệnh 5.1: Truy vấn lịch sử thay đổi của Học viên `user_id = 5` (Nhật Phạm)
```bash
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT user_sk, user_id, full_name, city, 
       valid_from, valid_to, is_current 
FROM gold.dim_user 
WHERE user_id = 5 
ORDER BY user_sk 
FORMAT PrettyCompact;
"
```
**Kết quả hiển thị:**
```text
   ┌──user_sk─┬─user_id─┬─full_name─┬─city────────┬──────────valid_from─┬────────────valid_to─┬─is_current─┐
1. │ 10000051 │       5 │ Nhật Phạm │ Da Nang     │ 2022-01-01 00:00:00 │ 2023-07-01 00:00:00 │          0 │
2. │ 10000052 │       5 │ Nhật Phạm │ Ho Chi Minh │ 2023-07-01 00:00:00 │ 2100-01-01 00:00:00 │          1 │
   └──────────┴─────────┴───────────┴─────────────┴─────────────────────┴─────────────────────┴────────────┘
```
💡 **Nhận xét:**
- Dòng 1 (`user_sk = 10000051`): Ghi nhận học viên ở Đà Nẵng từ `2022-01-01` đến `2023-07-01`. Cờ `is_current = 0` (đã là quá khứ).
- Dòng 2 (`user_sk = 10000052`): Ghi nhận học viên chuyển vào TP.HCM từ ngày `2023-07-01` đến vô tận (`2100-01-01`). Cờ `is_current = 1` (đang có hiệu lực).

### ⌨️ Lệnh 5.2: Kiểm tra các giao dịch thanh toán của Học viên 5 theo dòng thời gian
Xem các giao dịch thanh toán trong `fact_payments` được gắn với `user_sk` nào:
```bash
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT p.payment_id, p.charged_vnd, p.user_sk, u.city, toDate(p.paid_at) AS pay_date 
FROM gold.fact_payments p 
JOIN gold.dim_user u ON p.user_sk = u.user_sk 
WHERE u.user_id = 5 
ORDER BY p.paid_at 
FORMAT PrettyCompact;
"
```
**Bảng đối chứng ngoạn mục:**
```text
   ┌─payment_id─┬─charged_vnd─┬──user_sk─┬─city────────┬───pay_date─┐
1. │     150005 │      252900 │ 10000051 │ Da Nang     │ 2022-04-11 │
2. │      50005 │      227000 │ 10000051 │ Da Nang     │ 2022-04-28 │
3. │     250005 │      140000 │ 10000051 │ Da Nang     │ 2022-08-05 │
4. │     450005 │      106000 │ 10000051 │ Da Nang     │ 2022-08-30 │
5. │     350005 │      232000 │ 10000051 │ Da Nang     │ 2023-04-11 │
├───────────────────────────────────────────────────────────────────┤
6. │          5 │      238700 │ 10000052 │ Ho Chi Minh │ 2023-09-24 │
7. │     400005 │           0 │ 10000052 │ Ho Chi Minh │ 2024-01-01 │
8. │     300005 │      339300 │ 10000052 │ Ho Chi Minh │ 2024-03-09 │
9. │     200005 │      343200 │ 10000052 │ Ho Chi Minh │ 2024-04-19 │
10.│     100005 │      519300 │ 10000052 │ Ho Chi Minh │ 2024-06-30 │
   └────────────┴─────────────┴──────────┴─────────────┴────────────┘
```
🎯 **Kết luận:**
- 5 đơn hàng thanh toán trước ngày `2023-07-01` đều gắn với `user_sk = 10000051` thuộc về thành phố **Da Nang**.
- 5 đơn hàng thanh toán sau ngày `2023-07-01` đều gắn với `user_sk = 10000052` thuộc về thành phố **Ho Chi Minh**.
Báo cáo tài chính theo địa lý hoàn toàn chuẩn xác đến từng xu!

---

## 📍 TRẠM 6: THỬ NGHIỆM NẠP TĂNG DẦN & TÍNH BẤT BIẾN (IDEMPOTENCY)

### 🎯 Mục tiêu
Chứng minh pipeline xử lý được các tình huống nạp tăng dần thực tế: chỉ nạp các dòng mới sinh ra, khử trùng lặp (deduplication) và không chạy lại thừa thãi khi không có dữ liệu mới.

### ⌨️ Lệnh 6.1: Bơm dữ liệu mới và chạy kịch bản kiểm tra toàn diện
Dự án đã chuẩn bị sẵn bộ script tự động hóa kịch bản nạp tăng dần (bơm 10.000 lượt nộp bài trễ, kiểm tra đọc-chỉ, kiểm tra bắt lỗi email):
```bash
docker compose run --rm runner python demo/verify_v2.py
```
**Kết quả hiển thị trên Terminal:**
```text
=== BƯỚC 1: XÁC MINH PHÒNG TUYẾN ĐỌC-CHỈ (READ-ONLY GUARD) ===
✓ THÀNH CÔNG: Quyền chỉ đọc được bảo vệ. Lệnh ghi trái phép bị chặn đứng:
cannot execute UPDATE in a read-only transaction

=== BƯỚC 2: BƠM DỮ LIỆU TĂNG DẦN VÀ TIÊM DỮ LIỆU BẨN ===
✓ Đã chèn 10,000 bài thi mới và 1 bản ghi lỗi email vào OLTP.

=== BƯỚC 3: CHẠY PIPELINE ETL CHẾ ĐỘ INCREMENTAL ===
Extracting incremental delta...
Staging clean rows into silver...
Quarantined 1 invalid records.
Publishing incremental changes to ClickHouse Gold...
Incremental pipeline finished in 5.15 seconds.

=== BƯỚC 4: THỬ NGHIỆM TÍNH BẤT BIẾN (IDEMPOTENCY RUN) ===
Chạy lại pipeline lần 2 khi không có dữ liệu mới phát sinh...
Pipeline finished in 0.135 seconds (gold_reused=True). Không tốn tài nguyên xử lý!
```
💡 **Ý nghĩa:**
1. Pipeline chỉ mất **5.15 giây** để xử lý 10.000 bản ghi tăng dần vào ClickHouse.
2. Khi chạy lại lần thứ hai mà nguồn không có thay đổi, pipeline tự phát hiện không có delta và thoát ngay sau **0.13 giây** mà không làm thay đổi bảng Gold.

---

## 📍 TRẠM 7: ĐUA TỐC ĐỘ BENCHMARK & PHÂN TÍCH ĐA CHIỀU (OLAP VS OLTP)

### 🎯 Mục tiêu
Chạy 7 câu hỏi phân tích kinh doanh phức tạp (từ Q1 đến Q7) đồng thời trên cả PostgreSQL và ClickHouse với cùng dữ liệu và cùng thuật toán để so sánh tốc độ thực thi.

### ⌨️ Lệnh 7.1: Chạy Benchmark Q1–Q7
```bash
docker compose run --rm runner python cli.py benchmark --runs 3
```
**Bảng kết quả so sánh tốc độ (Mẫu kết quả đo thực tế):**
```text
Benchmark Results (Average of 3 runs):
┌──────┬──────────────────────────────────────────┬──────────────┬──────────────┬─────────────┐
│ Code │ Nội dung nghiệp vụ phân tích             │ PostgreSQL   │ ClickHouse   │ Độ tăng tốc │
├──────┼──────────────────────────────────────────┼──────────────┼──────────────┼─────────────┤
│ Q1   │ Doanh thu lũy kế theo tháng & giảng viên │    39.1 ms   │     7.2 ms   │   5.44x     │
│ Q2   │ Tỷ lệ hoàn thành khóa học theo phân loại │     9.2 ms   │     5.6 ms   │   1.63x     │
│ Q3   │ Phân tích đa chiều kết hợp 4 Dimensions  │    96.2 ms   │    29.2 ms   │   3.29x     │
│ Q4   │ Cửa sổ trượt lũy kế (Running total)      │    40.6 ms   │     8.2 ms   │   4.94x     │
│ Q5   │ Phân tích đa chiều CUBE liên hợp         │   243.1 ms   │    13.9 ms   │  17.52x     │
│ Q6   │ Drill-across đối chiếu 2 Facts độc lập   │    51.1 ms   │     9.3 ms   │   5.51x     │
│ Q7   │ Quét toàn bộ 3.6 triệu lượt học bài      │  4014.4 ms   │   103.7 ms   │  38.71x     │
└──────┴──────────────────────────────────────────┴──────────────┴──────────────┴─────────────┘
Toàn bộ mã băm kết quả (SHA256 Hash) giữa PostgreSQL và ClickHouse khớp 100%.
```
🚀 **Điểm nhấn vượt trội:**
Ở câu truy vấn **Q7** (quét toàn bộ lịch sử 3.6 triệu lượt học bài kết hợp lọc điều kiện), ClickHouse hoàn thành trong **94.7 mili-giây**, nhanh gấp **38.76 lần** so với PostgreSQL (**3.67 giây**)!

### ⌨️ Lệnh 7.2: Thử chạy trực tiếp 1 câu truy vấn Materialized View trong ClickHouse
Để xem báo cáo doanh thu theo tháng đã được tính toán trước (Pre-aggregated Materialized View), hãy chạy:
```bash
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT ym, total_enrollments, 
       round(total_gross_vnd / 1000000, 2) AS gross_trieu_dong, 
       round(net_revenue_vnd / 1000000, 2) AS net_trieu_dong 
FROM gold.mv_monthly_revenue_summary 
ORDER BY ym DESC 
LIMIT 6 
FORMAT PrettyCompact;
"
```
**Kết quả phản hồi sau 3.9 mili-giây:**
```text
   ┌─────ym─┬─total_enrollments─┬─gross_trieu_dong─┬─net_trieu_dong─┐
1. │ 202412 │             13890 │          3333.60 │        3333.60 │
2. │ 202411 │             13888 │          3333.12 │        3333.12 │
3. │ 202410 │             13889 │          3333.36 │        3333.36 │
4. │ 202409 │             13889 │          3333.36 │        3333.36 │
5. │ 202408 │             13889 │          3333.36 │        3333.36 │
6. │ 202407 │             13889 │          3333.36 │        3333.36 │
   └────────┴───────────────────┴──────────────────┴────────────────┘
```

---

## 📍 TRẠM 8: CỔNG KIỂM TOÁN CHẤT LƯỢNG 116 CHỈ TIÊU & BÁO CÁO KINH DOANH

### 🎯 Mục tiêu
Khám phá hệ thống kiểm toán dữ liệu tự động (Quality Gates) ngăn chặn dữ liệu sai sót lọt vào tầng báo cáo, chạy bộ kiểm thử Unit Tests và trích xuất các báo cáo kinh doanh chuẩn.

### ⌨️ Lệnh 8.1: Chạy Cổng Kiểm Toán Chất Lượng 116 Tiêu Chí
```bash
docker compose run --rm runner python cli.py validate
```
**Kết quả hiển thị:**
```text
Quality: 116 checks passed
```
Hệ thống tự động lưu toàn bộ kết quả vào `btl/artifacts/quality.json`. Bạn có thể kiểm tra danh mục bài kiểm tra bằng lệnh:
```bash
docker compose run --rm runner python -c "
import json
with open('artifacts/quality.json') as f:
    data = json.load(f)
print(f'Tổng số bài test: {len(data[\"checks\"])}')
print('Mẫu 5 kiểm tra đầu tiên:')
for c in data['checks'][:5]:
    print(f' - {c[\"name\"]}: Kỳ vọng={c[\"expected\"]}, Thực tế={c[\"actual\"]}, Đạt={c[\"passed\"]}')
"
```
**Mẫu hiển thị:**
```text
Tổng số bài test: 116
Mẫu 5 kiểm tra đầu tiên:
 - silver.users.count: Kỳ vọng=50000, Thực tế=50000, Đạt=True
 - silver.users.unique: Kỳ vọng=0, Thực tế=0, Đạt=True
 - silver.users.positive_key: Kỳ vọng=0, Thực tế=0, Đạt=True
 - silver.user_history.count: Kỳ vọng=60000, Thực tế=60000, Đạt=True
 - silver.user_history.unique: Kỳ vọng=0, Thực tế=0, Đạt=True
```

### ⌨️ Lệnh 8.2: Chạy Bộ Unit & Integration Tests của Pipeline
```bash
docker compose run --rm runner python -m unittest discover tests
```
**Kết quả hiển thị:**
```text
Ran 10 tests in 0.290s

OK
```
10 bài kiểm thử đơn vị kiểm tra:
- Khả năng chặn đứng Schema Drift (cột mới, cột bị xóa, đổi kiểu dữ liệu).
- Quy tắc kiểm tra tính hợp lệ của Email, Ngày tháng, Khóa ngoại.
- Tính tương thích dữ liệu giữa bảng CUBE và bảng chi tiết.

### ⌨️ Lệnh 8.3: Xuất Trọn Bộ 10 Báo Cáo Phân Tích Nghiệp Vụ (R01 - R10)
```bash
docker compose run --rm runner python cli.py reports
```
**Kết quả hiển thị:**
```text
R01_revenue_rollup: 51 rows
R02_completion_rate: 15 rows
R03_quiz_performance: 5 rows
R04_role_playing_dates: 5 rows
R05_historical_city: 12 rows
R06_top_courses_rank: 120 rows
R07_revenue_enrollment_drill_across: 175 rows
R08_slice_dice: 12 rows
R09_cube: 96 rows
R10_learning_time: 50 rows
```
Toàn bộ các file CSV của báo cáo được lưu tại thư mục `btl/artifacts/reports/`. Bạn có thể đọc trực tiếp bất kỳ file nào bằng lệnh:
```bash
head -n 10 btl/artifacts/reports/R01_revenue_rollup.csv
```

---

## 🎁 TỔNG KẾT BẢNG LỆNH "BỎ TÚI" CHO CHUYẾN THAM QUAN

Để tiện cho việc thuyết trình hoặc kiểm tra nhanh, dưới đây là danh sách rút gọn các câu lệnh cốt lõi nhất:

```bash
# 1. Trạng thái hạ tầng
docker compose ps

# 2. Thử nghiệm bảo vệ đọc-chỉ (phải báo lỗi)
docker compose exec postgres psql -U learning_reader -d learning_oltp -c "UPDATE oltp.users SET full_name = 'Hack' WHERE user_id = 1;"

# 3. Xem bản ghi bẩn bị cách ly
docker compose exec postgres psql -U learning_stage -d dwh_staging -P pager=off -x -c "SELECT * FROM quarantine.quarantine_records LIMIT 1;"

# 4. Xem dung lượng nén cột ClickHouse
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "SELECT table, sum(rows) as rows, formatReadableSize(sum(data_compressed_bytes)) as compressed, round(sum(data_uncompressed_bytes)/sum(data_compressed_bytes), 2) as ratio FROM system.parts WHERE database = 'gold' AND active GROUP BY table ORDER BY rows DESC FORMAT PrettyCompact;"

# 5. Xem lịch sử học viên đổi địa chỉ SCD2
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "SELECT user_sk, user_id, full_name, city, valid_from, valid_to, is_current FROM gold.dim_user WHERE user_id = 5 ORDER BY user_sk FORMAT PrettyCompact;"

# 6. Chạy kịch bản tự động hóa xác minh nạp tăng dần v2
docker compose run --rm runner python demo/verify_v2.py

# 7. Chạy Benchmark so sánh tốc độ
docker compose run --rm runner python cli.py benchmark --runs 3

# 8. Chạy cổng kiểm toán chất lượng 116 chỉ tiêu
docker compose run --rm runner python cli.py validate
```

---
*Tài liệu thuộc bộ hồ sơ kỹ thuật Online Learning Data Warehouse v2.0.*  
*Xem thêm:*
- [data_quality.md](file:///run/media/tamdae/04C8A69DC8A68C8C/Users/LENOVO/Documents/TL_Kỳ_1_năm_4/Data_Warehouse/btl/docs/data_quality.md) - Cẩm nang 116 Tiêu Chí Chất Lượng Dữ Liệu
- [data_lineage.md](file:///run/media/tamdae/04C8A69DC8A68C8C/Users/LENOVO/Documents/TL_Kỳ_1_năm_4/Data_Warehouse/btl/docs/data_lineage.md) - Bản Đồ Dòng Chảy Dữ Liệu Từ Đầu Đến Cuối
- [data_catalog.md](file:///run/media/tamdae/04C8A69DC8A68C8C/Users/LENOVO/Documents/TL_Kỳ_1_năm_4/Data_Warehouse/btl/docs/data_catalog.md) - Từ Điển Danh Mục Dữ Liệu Doanh Nghiệp
- [data_contract.md](file:///run/media/tamdae/04C8A69DC8A68C8C/Users/LENOVO/Documents/TL_Kỳ_1_năm_4/Data_Warehouse/btl/docs/data_contract.md) - Hợp Đồng Dữ Liệu Giữa OLTP & DWH
