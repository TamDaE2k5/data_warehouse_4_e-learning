# HƯỚNG DẪN THỰC THI & KIỂM CHỨNG BẠCH HÓA HỆ THỐNG DATA WAREHOUSE (WHITE-BOX PLAYBOOK)
> **Tài liệu hướng dẫn thực nghiệm trực tiếp trong Service (PostgreSQL & ClickHouse)**  
> *Áp dụng cho thư mục:* `rebuild/`  
> *Mục tiêu:* Đi sâu vào bản chất kỹ thuật bên trong từng cơ sở dữ liệu thay vì dùng "hộp đen" Runner. Hướng dẫn cách vào từng service kiểm tra cấu trúc bảng, theo dõi dòng chảy dữ liệu qua 3 đợt thực nghiệm (Batch 1, Batch 2, Batch 3), kiểm chứng tận mắt cơ chế Mốc phân thủy (*Watermark*), Khử trùng lặp (*ReplacingMergeTree*) và Trạm kiểm dịch (*Quarantine*), sau đó chạy trực tiếp 7 câu truy vấn phân tích chiến lược (Q1–Q7) ngay trong ClickHouse Client.

---

## 🧭 PHẦN 1: KHỞI ĐỘNG HẠ TẦNG & CÁCH KẾT NỐI VÀO CÁC SERVICE

### 1.1 Khởi động các container máy chủ CSDL
Tại thư mục `rebuild`, mở Terminal và chạy:
```bash
cd /run/media/tamdae/04C8A69DC8A68C8C/Users/LENOVO/Documents/TL_Kỳ_1_năm_4/Data_Warehouse/rebuild
docker compose up -d --wait postgres clickhouse
docker compose build runner
```

### 1.2 Cách kết nối tương tác trực tiếp (Interactive Shell) vào các Service

Hệ thống của chúng ta gồm 2 máy chủ CSDL độc lập:

*   **Vào PostgreSQL Tác nghiệp (`learning_oltp`):**
    ```bash
    docker compose exec -it postgres psql -U learning -d learning_oltp
    ```
    *Lệnh kiểm tra bảng và schema bên trong:*
    ```sql
    \dn               -- Xem danh sách Schema (oltp, public)
    \dt oltp.*        -- Xem danh sách 11 bảng tác nghiệp nguồn
    \d oltp.users     -- Xem cấu trúc chi tiết bảng users
    \q                -- Thoát ra terminal
    ```

*   **Vào PostgreSQL Kho trung chuyển (`dwh_staging`):**
    ```bash
    docker compose exec -it postgres psql -U learning_stage -d dwh_staging
    ```
    *Lệnh kiểm tra bên trong:*
    ```sql
    \dn               -- Xem 3 schema: staging (đệm), silver (sạch), quarantine (lỗi)
    \dt staging.*     -- Xem bảng quản lý mốc nạp etl_watermarks
    \dt silver.*      -- Xem các bảng dữ liệu sạch sau khi khử trùng
    \dt quarantine.*  -- Xem bảng lưu trữ dữ liệu lỗi quarantine_records
    \q                -- Thoát ra terminal
    ```

*   **Vào ClickHouse Kho phân tích Gold (`gold`):**
    ```bash
    docker compose exec -it clickhouse clickhouse-client -u learning --password local_learning_demo -d gold
    ```
    *Lệnh kiểm tra bên trong:*
    ```sql
    SHOW TABLES;                    -- Xem 11 bảng Gold (Fact & Dim) và các Materialized Views
    DESCRIBE TABLE fact_payments;   -- Xem cấu trúc kiểu cột và kiểu nén
    exit                            -- Thoát ra terminal
    ```

---

## 📍 PHẦN 2: THIẾT LẬP NỀN TẢNG (BASELINE) VÀ KIỂM TRA MỐC BAN ĐẦU

Trước khi tiến hành thử nghiệm 3 đợt dữ liệu, ta cần khởi tạo cấu trúc và sinh tập dữ liệu nền tảng ban đầu (Snapshot 2022–2024).

### 2.1 Cài đặt Schema và Sinh dữ liệu nền tảng
Chạy 2 lệnh khởi tạo một lần duy nhất:
```bash
docker compose run --rm runner python cli.py setup
docker compose run --rm runner python cli.py generate --enrollments 500000 --seed 2024
```

### 2.2 Trực tiếp kiểm tra số dòng trên 8 bảng tác nghiệp nguồn (OLTP)
Bạn có thể vào thẳng PostgreSQL hoặc chạy lệnh một dòng:
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
*Kết quả:* ~3.6 triệu bản ghi `lesson_completions`, ~1.0 triệu `quiz_attempts`, 500k `enrollments`, 500k `payments`, 50k `users`.

### 2.3 Nạp mẻ toàn phần ban đầu (Full Load) để thiết lập kho Gold
```bash
docker compose run --rm runner python cli.py pipeline --mode full
```

### 2.4 Kiểm tra Mốc phân thủy (Watermark) ban đầu trong PostgreSQL Staging
Đăng nhập vào `dwh_staging` để xem hệ thống ghi nhận mốc nạp như thế nào:
```bash
docker compose exec postgres psql -U learning_stage -d dwh_staging -c "
SELECT table_name, last_processed_time, last_processed_id, last_run_id 
FROM staging.etl_watermarks 
ORDER BY table_name;
"
```
> 💡 **Bản chất của Watermark (Mốc phân thủy):**  
> Mỗi bảng được lưu giữ một cặp mốc kép `(last_processed_time, last_processed_id)`. Ở các lần chạy tăng dần tiếp theo, truy vấn nguồn sẽ chỉ lấy:  
> `WHERE (updated_at, id) > (last_processed_time, last_processed_id)`.  
> Điều này đảm bảo dù có hàng nghìn bản ghi cùng 1 microsecond cũng không bao giờ bị bỏ sót.

---

## 🔬 PHẦN 3: ĐI SÂU THỰC NGHIỆM 3 ĐỢT DỮ LIỆU (DEEP DIVE STAGE 6)

Đây là trọng tâm của toàn bộ hệ thống. Ta sẽ không dùng `verify_v2.py` (vốn là một script bọc tự động) mà sẽ tự tay nạp từng đợt, kiểm tra trước và sau từng bước để bạch hóa hoàn toàn cách dữ liệu di chuyển.

```
                  LUỒNG ĐỐI SOÁT DỮ LIỆU TỪ NGUỒN SANG KHO
                                    │
    ┌───────────────────────────────┼───────────────────────────────┐
    ▼                               ▼                               ▼
[ĐỢT 1: AN TOÀN]           [ĐỢT 2: TRÙNG LẶP]             [ĐỢT 3: DỮ LIỆU BẨN]
100 bản ghi sạch           50 mới + 50 trùng ID           50 sạch + 5 email sai
    │                               │                               │
    ▼                               ▼                               ▼
PostgreSQL OLTP            PostgreSQL OLTP                PostgreSQL OLTP
(clock_timestamp)          (Cập nhật updated_at)          (5 email cố ý sai)
    │                               │                               │
    ▼ (Extract > Watermark)         ▼                               ▼
PostgreSQL Staging         PostgreSQL Staging             PostgreSQL Staging
• Silver: 100 sạch         • Silver: UPSERT ghi đè        • Silver: CHỈ nhận 50 sạch
• Quarantine: 0            • Quarantine: 0                • Quarantine: Tóm gọn 5 lỗi
    │                               │                               │
    ▼                               ▼                               ▼
ClickHouse Gold            ClickHouse Gold                ClickHouse Gold
Tăng đúng +100 dòng        ReplacingMergeTree khử trùng   Chỉ tăng +50 dòng sạch!
                           Gold chỉ tăng đúng +50 dòng    5 dòng bẩn KHÔNG VÀO GOLD!
```

---

### 🚀 ĐỢT 1: NẠP DỮ LIỆU AN TOÀN (BATCH 1 - SAFE BASELINE)

Mục tiêu: Nạp 100 bản ghi mới trên mỗi bảng vào nguồn tác nghiệp, kiểm tra xem mốc Watermark và số dòng trong Gold có tăng khớp 100% hay không.

#### Bước 1.1: Kiểm tra trạng thái TRƯỚC khi nạp Đợt 1
Kiểm tra số dòng hiện tại của `quiz_attempts` ở cả OLTP và ClickHouse Gold:
```bash
# 1. Đếm số dòng quiz_attempts trong OLTP
docker compose exec postgres psql -U learning -d learning_oltp -c "SELECT count(*) AS oltp_quiz_before FROM oltp.quiz_attempts;"

# 2. Đếm số dòng fact_quiz_attempts trong ClickHouse Gold
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "SELECT count(*) AS gold_quiz_before FROM gold.fact_quiz_attempts;"

# 3. Kiểm tra số dòng đang có trong khu cách ly Quarantine
docker compose exec postgres psql -U learning_stage -d dwh_staging -c "SELECT count(*) AS quarantine_before FROM quarantine.quarantine_records;"
```

#### Bước 1.2: Bơm dữ liệu Batch 1 vào OLTP
Batch 1 chứa 100 bản ghi sạch cho mỗi bảng (`users`, `user_history`, `enrollments`, `payments`, `lesson_completions`, `quiz_attempts`):
```bash
docker compose run --rm runner python demo/load_dataset_to_oltp.py --batch 1
```

#### Bước 1.3: Kiểm tra OLTP sau khi bơm Batch 1
```bash
docker compose exec postgres psql -U learning -d learning_oltp -c "SELECT count(*) AS oltp_quiz_after_batch1 FROM oltp.quiz_attempts;"
```
*Hiện tượng:* `oltp.quiz_attempts` tăng chính xác **+100 dòng** (các ID từ 1010001 đến 1010100). Đồng thời cột `updated_at` của 100 dòng này được gán bằng `clock_timestamp()` mới nhất.

#### Bước 1.4: Chạy luồng nạp tăng dần (Incremental ETL)
```bash
docker compose run --rm runner python cli.py pipeline --mode incremental
```

#### Bước 1.5: Kiểm tra kết quả SAU khi chạy Đợt 1
*   **Kiểm tra ClickHouse Gold:**
    ```bash
    docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "SELECT count(*) AS gold_quiz_after_batch1 FROM gold.fact_quiz_attempts;"
    ```
    👉 **Khẳng định:** Số dòng trong `gold.fact_quiz_attempts` tăng chính xác **đúng 100 dòng** (bằng đúng số dòng nguồn phát sinh).
*   **Kiểm tra Watermark mới:**
    ```bash
    docker compose exec postgres psql -U learning_stage -d dwh_staging -c "SELECT table_name, last_processed_time, last_processed_id FROM staging.etl_watermarks WHERE table_name = 'quiz_attempts';"
    ```
    👉 Mốc `last_processed_id` đã nhảy lên `1010100` và `last_processed_time` đã được cập nhật bằng thời điểm nạp vừa rồi.
*   **Kiểm tra Quarantine:**
    ```bash
    docker compose exec postgres psql -U learning_stage -d dwh_staging -c "SELECT count(*) AS quarantine_after_batch1 FROM quarantine.quarantine_records;"
    ```
    👉 Bằng `0` (không có bản ghi nào bị lỗi).

---

### 🔄 ĐỢT 2: NẠP TĂNG DẦN & KHỬ TRÙNG LẶP (BATCH 2 - DEDUPLICATION & REPLACINGMERGETREE)

Mục tiêu: Mô phỏng bài toán thực tế khi hệ thống mạng gửi lặp lại giao dịch hoặc học viên làm lại bài thi. Kiểm chứng cách động cơ `ReplacingMergeTree` của ClickHouse và UPSERT của Staging xử lý loại bỏ bản ghi trùng lặp.

#### Bước 2.1: Bản chất dữ liệu Batch 2 gồm những gì?
Mở file CSV ra xem, bạn sẽ thấy:
*   `payments.csv`: Gồm 50 giao dịch cũ từ Batch 1 nhưng được cập nhật trạng thái `refunded = 1` (hoàn tiền).
*   `quiz_attempts.csv`: Gồm **100 dòng**, trong đó:
    *   **50 dòng MỚI TINH** (attempt_id: 1010101 – 1010150).
    *   **50 dòng TRÙNG LẶP ID với Đợt 1** (attempt_id: 1010001 – 1010050) nhưng điểm số `correct_count` được sửa đổi.

#### Bước 2.2: Kiểm tra số dòng TRƯỚC khi nạp Đợt 2
```bash
# Ghi nhớ số lượng bản ghi quiz trong Gold trước khi nạp
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "SELECT count(*) FROM gold.fact_quiz_attempts;"
```

#### Bước 2.3: Bơm dữ liệu Batch 2 vào OLTP
```bash
docker compose run --rm runner python demo/load_dataset_to_oltp.py --batch 2
```
*Cơ chế xảy ra tại OLTP:* Lệnh SQL thực thi:  
`INSERT INTO oltp.quiz_attempts ... ON CONFLICT (attempt_id) DO UPDATE SET correct_count = EXCLUDED.correct_count, updated_at = clock_timestamp()`  
Do đó, cả 50 dòng mới và 50 dòng trùng đều có `updated_at > watermark cũ`.

#### Bước 2.4: Chạy luồng nạp tăng dần (Incremental ETL)
```bash
docker compose run --rm runner python cli.py pipeline --mode incremental
```
*Quan sát Terminal:* Pipeline trích xuất từ nguồn: `quiz_attempts: 100` dòng (gồm 50 mới + 50 trùng).

#### Bước 2.5: Kiểm chứng tính năng Khử trùng lặp (Deduplication) của ClickHouse Gold
Bây giờ hãy đếm số lượng bản ghi trong ClickHouse Gold:
```bash
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT count(*) AS total_rows_after_dedup 
FROM gold.fact_quiz_attempts 
FINAL;
"
```
⚡ **Hiện tượng kỳ diệu:**  
Nguồn trích xuất **100 dòng**, nhưng tổng số dòng trong Gold chỉ tăng thêm **đúng 50 dòng**!

#### Bước 2.6: Tận mắt soi 1 bản ghi bị trùng lặp (Case Study: attempt_id = 1010001)
Hãy truy vấn chi tiết bản ghi `attempt_id = 1010001` trong ClickHouse:
```bash
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT attempt_id, user_sk, correct_count, time_spent_seconds, is_passed 
FROM gold.fact_quiz_attempts 
FINAL 
WHERE attempt_id = 1010001;
"
```
👉 Kết quả hiển thị chính xác **duy nhất 1 dòng** mang điểm số mới nhất của Đợt 2. Bản ghi cũ từ Đợt 1 đã bị ClickHouse tự động loại bỏ thông qua cơ chế gộp phân vùng và khóa chính `ORDER BY (date_sk, course_sk, user_sk, attempt_id)`. Báo cáo kinh doanh hoàn toàn không bị tính trùng lặp!

---

### 💥 ĐỢT 3: TIÊM DỮ LIỆU BẨN & CƠ CHẾ KIỂM DỊCH (BATCH 3 - CHAOS & QUARANTINE DLQ)

Mục tiêu: Trả lời câu hỏi quan trọng nhất của bạn: **"Dữ liệu bẩn có bị lọt vào Gold hay không, và nó bị giam giữ ở đâu?"**

#### Bước 3.1: Dữ liệu bẩn trong Batch 3 gồm những gì?
Trong file `data/batch_3/users.csv` có tổng cộng 55 học viên:
*   **50 học viên sạch** (user_id: 50101 – 50150).
*   **5 học viên cố tình sai định dạng email nghiêm trọng** (user_id: 50191 – 50195):
    *   `50191`: `user_missing_at_symbol.com` (thiếu ký tự @)
    *   `50192`: `user with space@domain.com` (chứa dấu cách)
    *   `50193`: `bad_user_no_domain@` (thiếu tên miền sau @)
    *   `50194`: `bad@@domain.com` (hai ký tự @ liền nhau)
    *   `50195`: `@onlydomain.com` (thiếu tên người dùng trước @)
*   Đi kèm là 50 lượt thi sạch trong `quiz_attempts.csv`.

#### Bước 3.2: Kiểm tra số dòng TRƯỚC khi nạp Đợt 3
```bash
# 1. Đếm số học viên hiện tại trong ClickHouse Gold
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "SELECT count(*) FROM gold.dim_user;"

# 2. Đếm số dòng hiện có trong bảng cách ly Quarantine
docker compose exec postgres psql -U learning_stage -d dwh_staging -c "SELECT count(*) FROM quarantine.quarantine_records;"
```

#### Bước 3.3: Bơm dữ liệu bẩn vào OLTP
```bash
docker compose run --rm runner python demo/load_dataset_to_oltp.py --batch 3
```

#### Bước 3.4: Kích hoạt luồng nạp ETL
```bash
docker compose run --rm runner python cli.py pipeline --mode incremental
```
*Kết quả trên Terminal:* Pipeline hoàn tất 100% an toàn (**Zero-Crash**)! Không hề bị dừng sập giữa chừng.

#### Bước 3.5: Trả lời 3 câu hỏi cốt tử về kiểm dịch dữ liệu

##### ❓ CÂU HỎI 1: NĂM HỌC VIÊN BỊ LỖI EMAIL CÓ BỊ LỌT VÀO GOLD HAY KHÔNG?
Hãy thực hiện truy vấn tìm kiếm 5 học viên đó trong ClickHouse Gold:
```bash
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "
SELECT count(*) AS leaked_bad_records
FROM gold.dim_user 
WHERE user_id BETWEEN 50191 AND 50195;
"
```
🎯 **KẾT QUẢ TRẢ VỀ: `0`!**  
Tuyệt đối không có bất kỳ bản ghi nào trong 5 học viên sai email lọt được vào kho dữ liệu Gold!

##### ❓ CÂU HỎI 2: NĂM BẢN GHI LỖI ĐANG BỊ GIAM GIỮ Ở ĐÂU?
Đăng nhập vào PostgreSQL `dwh_staging` và kiểm tra bảng `quarantine.quarantine_records`:
```bash
docker compose exec postgres psql -U learning_stage -d dwh_staging -P pager=off -x -c "
SELECT table_name, source_id, error_code, rejection_reason, raw_payload, detected_at
FROM quarantine.quarantine_records
WHERE source_id BETWEEN 50191 AND 50195;
"
```
🔍 **Tận mắt nhìn thấy:**  
Toàn bộ 5 bản ghi bị tóm gọn tại đây với mã lỗi `ERR_INVALID_EMAIL`, nguyên nhân từ chối rõ ràng và lưu nguyên vẹn chuỗi JSON gốc `raw_payload`.

> 🛡️ **Tại sao dữ liệu lỗi không thể lọt vào Gold? (Giải thích mã nguồn):**  
> Trong file `etl/stage.py`, khi đọc từng dòng dữ liệu từ OLTP:
> ```python
> clean, code, reason = normalize(cols, types, raw)
> if code:
>     errors.append((table, raw[0], raw[-1], code, reason, json.dumps(...)))
>     # KHÔNG GHI VÀO BUFFER CỦA SILVER!
> else:
>     buffer.write(...) # Chỉ bản ghi sạch mới được ghi vào buffer
> ```
> *   Dòng bị lỗi lập tức bị đẩy sang mảng `errors` và ghi thẳng vào bảng `quarantine.quarantine_records`.
> *   Chỉ những dòng hợp lệ mới được đưa vào `buffer` và nạp vào schema `silver`.
> *   Kho Gold của ClickHouse chỉ đọc dữ liệu sạch từ schema `silver` thông qua cơ chế `stage_bridge`. Vì thế dữ liệu bẩn **100% bị chặn đứng tại phòng tuyến Staging**, không có bất kỳ cơ hội nào xâm nhập vào kho phân tích Gold!

##### ❓ CÂU HỎI 3: DỮ LIỆU SẠCH ĐI KÈM CÓ ĐƯỢC VÀO GOLD BÌNH THƯỜNG KHÔNG?
Kiểm tra số dòng tăng thêm trong `gold.dim_user`:
```bash
docker compose exec clickhouse clickhouse-client -u learning --password local_learning_demo -d gold --query "SELECT count(*) FROM gold.dim_user;"
```
👉 `gold.dim_user` tăng chính xác **+50 dòng** (chính là 50 học viên sạch).  
👉 `gold.fact_quiz_attempts` tăng thêm **+50 dòng** (50 bài thi sạch đi kèm).

---

## 📊 PHẦN 4: THỰC THI 7 CÂU TRUY VẤN PHÂN TÍCH (Q1–Q7) TRỰC TIẾP TRONG CLICKHOUSE

Thay vì để runner chạy ngầm đo benchmark, bạn hãy kết nối trực tiếp vào `clickhouse-client` và thực thi từng câu truy vấn SQL để thấy được kết quả kinh doanh và tốc độ xử lý véc-tơ siêu tốc.

Mở phiên làm việc trong ClickHouse Client:
```bash
docker compose exec -it clickhouse clickhouse-client -u learning --password local_learning_demo -d gold
```

### 🔹 Q1: Doanh thu theo chuỗi thời gian Năm & Tháng (Basic Aggregation)
*Ý nghĩa nghiệp vụ:* Gom nhóm 500.000 giao dịch thanh toán theo thời gian để tính tổng doanh thu thuần thực thu:
```sql
SELECT d.year, d.month, count(*) AS payments, sum(f.net_vnd) AS net_vnd
FROM gold.fact_payments f 
JOIN gold.dim_date d ON f.date_sk = d.date_sk
GROUP BY d.year, d.month 
ORDER BY d.year, d.month;
```

### 🔹 Q2: Cắt lát lọc theo Quý và Độ khó khóa học (Slicing & Dicing)
*Ý nghĩa nghiệp vụ:* Phân tích doanh thu và số tiền hoàn trả trong Quý 1/2024 đối với các khóa học cơ bản và trung cấp:
```sql
SELECT c.category, sum(f.net_vnd) AS net_vnd, sum(f.refunded) AS refunds
FROM gold.fact_payments f 
JOIN gold.dim_course c ON f.course_sk = c.course_sk
WHERE f.date_sk BETWEEN 20240101 AND 20240331 
  AND c.difficulty IN ('beginner', 'intermediate')
GROUP BY c.category 
ORDER BY c.category;
```

### 🔹 Q3: Phép nối hình sao 4 chiều đồng thời (4-Way Star Schema Join)
*Ý nghĩa nghiệp vụ:* Phân tích đa chiều kết hợp đồng thời Năm, Danh mục, Chuyên môn giảng viên và Hình thức thanh toán:
```sql
SELECT d.year, c.category, i.expertise, m.method_name,
       count(*) AS transactions, sum(f.net_vnd) AS net_vnd
FROM gold.fact_payments f 
JOIN gold.dim_date d ON f.date_sk = d.date_sk
JOIN gold.dim_course c ON f.course_sk = c.course_sk
JOIN gold.dim_instructor i ON f.instructor_sk = i.instructor_sk
JOIN gold.dim_payment_method m ON f.method_sk = m.method_sk
GROUP BY d.year, c.category, i.expertise, m.method_name 
ORDER BY d.year, c.category, i.expertise, m.method_name
LIMIT 20;
```

### 🔹 Q4: Tính doanh thu lũy kế dồn tích bằng hàm cửa sổ (Window Function Running Total)
*Ý nghĩa nghiệp vụ:* Theo dõi doanh thu tăng trưởng dồn tích qua từng tháng trong năm:
```sql
WITH monthly AS (
    SELECT d.year, d.month, sum(f.net_vnd) AS revenue 
    FROM gold.fact_payments f
    JOIN gold.dim_date d ON f.date_sk = d.date_sk 
    GROUP BY d.year, d.month
)
SELECT year, month, revenue, 
       sum(revenue) OVER (PARTITION BY year ORDER BY month ROWS UNBOUNDED PRECEDING) AS running_revenue
FROM monthly 
ORDER BY year, month;
```

### 🔹 Q5: Khối lập phương đa chiều Năm & Danh mục (Multidimensional CUBE)
*Ý nghĩa nghiệp vụ:* Tự động tính toán toàn bộ các tổ hợp tổng con (Subtotals) và tổng toàn cục (Grand Total):
```sql
SELECT d.year, CAST(c.category AS String) AS category, 
       sum(f.net_vnd) AS net_vnd, count(*) AS transactions
FROM gold.fact_payments f 
JOIN gold.dim_date d ON f.date_sk = d.date_sk
JOIN gold.dim_course c ON f.course_sk = c.course_sk
GROUP BY CUBE(d.year, CAST(c.category AS String)) 
ORDER BY d.year, category;
```

### 🔹 Q6: Khoan chéo đối chiếu giữa Doanh thu và Ghi danh (Fact-to-Fact Drill Across)
*Ý nghĩa nghiệp vụ:* Đặt cạnh nhau 2 quy trình kinh doanh độc lập (Số tiền thu được vs Lượt ghi danh thực tế) trên từng khóa học mà không bị nhân đôi số tiền:
```sql
WITH revenue AS (
    SELECT course_sk, sum(net_vnd) AS net_vnd 
    FROM gold.fact_payments 
    GROUP BY course_sk
),
enrollment AS (
    SELECT course_sk, count(*) AS total_enrollments 
    FROM gold.fact_enrollments 
    GROUP BY course_sk
)
SELECT c.course_title, c.category, 
       coalesce(r.net_vnd, 0) AS revenue, 
       coalesce(e.total_enrollments, 0) AS enrollments
FROM gold.dim_course c
LEFT JOIN revenue r ON c.course_sk = r.course_sk
LEFT JOIN enrollment e ON c.course_sk = e.course_sk
ORDER BY revenue DESC 
LIMIT 15;
```

### 🔹 Q7: Quét toàn bộ 3.6 triệu bản ghi học bài & Đếm học viên duy nhất (Full Scan & High Cardinality)
*Ý nghĩa nghiệp vụ:* Quét bảng sự kiện khổng lồ `fact_lesson_completions` (3.6 triệu dòng), tính tổng thời lượng học tập và đếm số học viên phân biệt tham gia học:
```sql
SELECT c.category, 
       count(*) AS total_completions, 
       count(DISTINCT f.user_sk) AS active_students,
       round(sum(f.time_spent_seconds) / 3600.0, 1) AS total_study_hours
FROM gold.fact_lesson_completions f
JOIN gold.dim_course c ON f.course_sk = c.course_sk
GROUP BY c.category
ORDER BY total_completions DESC;
```
*(Gõ `exit` để thoát khỏi ClickHouse Client sau khi thử nghiệm xong)*.

---

## 🧹 PHẦN 5: DỌN DẸP HẠ TẦNG KHI KẾT THÚC

Sau khi đã hoàn tất toàn bộ quá trình kiểm thử bạch hóa và lưu lại các số liệu cần thiết, bạn tắt hệ thống bằng lệnh:

```bash
docker compose --profile demo down
```
*(Nếu muốn xóa sạch toàn bộ dữ liệu để bắt đầu lại từ đầu: `docker compose --profile demo down -v`)*.
