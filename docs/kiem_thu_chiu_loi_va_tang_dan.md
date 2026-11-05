# HƯỚNG DẪN THỰC NGHIỆM: NẠP 3 BỘ DATASET (CSV) VÀO OLTP VÀ CHẠY PIPELINE SANG GOLD
> **Dành cho Giảng viên, Kiến trúc sư Dữ liệu và Kiểm thử viên Hệ thống**  
> *Đặc tả luồng xử lý chuẩn:*  
> `File CSV (data/batch_X/)` ➔ **PostgreSQL OLTP (`learning_oltp`)** ➔ **ETL Pipeline** ➔ **Staging/Silver & Quarantine** ➔ **ClickHouse Gold**

---

## 🧭 1. Ý NGHĨA VÀ KIẾN TRÚC 3 BỘ DATASET

Để kiểm chứng toàn diện năng lực của Data Warehouse, hệ thống tổ chức sẵn 3 bộ Dataset chuẩn dạng CSV tại thư mục `data/`:

```
                       LUỒNG DỮ LIỆU CHUẨN (END-TO-END PIPELINE)
                                        │
           ┌────────────────────────────┼────────────────────────────┐
           ▼                            ▼                            ▼
   [ĐỢT 1: AN TOÀN]            [ĐỢT 2: TĂNG DẦN & TRÙNG]    [ĐỢT 3: HỖN LOẠN & LỖI]
   data/batch_1/*.csv          data/batch_2/*.csv           data/batch_3/*.csv
   • 100 users, 100 enrolls    • 50 attempts MỚI            • 50 users SẠCH
   • 100 payments, 100 quiz    • 50 attempts TRÙNG LẶP      • 5 users CỐ TÌNH SAI EMAIL
           │                            │                            │
           ▼                            ▼                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     POSTGRESQL OLTP (learning_oltp)                         │
│                     (Được nạp qua: demo/load_dataset_to_oltp.py)            │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼ (python cli.py pipeline --mode incremental)
┌─────────────────────────────────────────────────────────────────────────────┐
│                     POSTGRESQL STAGING (dwh_staging)                        │
│  • silver.*: Dữ liệu sạch, chuẩn hóa kiểu, UPSERT chống trùng               │
│  • quarantine.quarantine_records: Tóm gọn 5 user lỗi email (JSON payload)   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼ (Zero Downtime Shadow Publish)
┌─────────────────────────────────────────────────────────────────────────────┐
│                     CLICKHOUSE GOLD (gold database)                         │
│  • Đợt 1: Nạp trọn vẹn 100 bản ghi sạch vào Gold                            │
│  • Đợt 2: ReplacingMergeTree khử 50 bản ghi trùng ➔ Gold chỉ tăng đúng 50   │
│  • Đợt 3: Zero-Crash! Bản ghi sạch vào Gold ➔ Quality Gate: 116 Checks PASS │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📂 2. CẤU TRÚC CHI TIẾT CÁC FILE CSV TRONG `data/`

```text
data/
├── batch_1/                      # Đợt 1: Dữ liệu nền tảng sạch 100%
│   ├── users.csv                 # 100 học viên mới (user_id: 50001 - 50100)
│   ├── user_history.csv          # 100 bản ghi lịch sử địa lý SCD2
│   ├── enrollments.csv           # 100 lượt đăng ký khóa học
│   ├── payments.csv              # 100 đơn hàng thanh toán
│   ├── lesson_completions.csv    # 100 lượt học bài
│   └── quiz_attempts.csv         # 100 lượt thi trắc nghiệm
│
├── batch_2/                      # Đợt 2: Nạp tăng dần & Khử trùng lặp
│   ├── payments.csv              # 50 giao dịch trùng lặp cập nhật hoàn tiền (refunded=1)
│   └── quiz_attempts.csv         # 50 lượt thi MỚI + 50 lượt thi TRÙNG LẶP ID Đợt 1
│
└── batch_3/                      # Đợt 3: Dữ liệu hỗn loạn & Chịu lỗi
    ├── users.csv                 # 50 học viên sạch + 5 học viên cố tình sai định dạng email
    └── quiz_attempts.csv         # 50 lượt thi trắc nghiệm sạch đi kèm
```

---

## ⚡ 3. HƯỚNG DẪN THỰC HIỆN TỪNG BƯỚC TRÊN TERMINAL

Mở Terminal tại thư mục `rebuild/` và chạy lần lượt 3 kịch bản:

### 🚀 KỊCH BẢN 1: NẠP DỮ LIỆU AN TOÀN (BATCH 1)

**Bước 1.1:** Nạp file CSV từ `data/batch_1/` vào PostgreSQL OLTP:
```bash
docker compose run --rm runner python demo/load_dataset_to_oltp.py --batch 1
```
*Kết quả:* Nạp thành công 600 dòng (6 bảng x 100 dòng) vào các bảng `oltp.*` trong PostgreSQL.

**Bước 1.2:** Chạy pipeline để xử lý từ PostgreSQL sang ClickHouse Gold:
```bash
docker compose run --rm runner python cli.py pipeline --mode incremental
```
*Kết quả:* Pipeline trích xuất 100 dòng từ mỗi bảng, kiểm toán đạt 116/116 checks!

---

### 🔄 KỊCH BẢN 2: NẠP TĂNG DẦN VÀ KHỬ TRÙNG LẶP (BATCH 2)

**Bước 2.1:** Nạp file CSV từ `data/batch_2/` vào PostgreSQL OLTP:
```bash
docker compose run --rm runner python demo/load_dataset_to_oltp.py --batch 2
```
*Kết quả:* Nạp 100 dòng `quiz_attempts` (50 mới + 50 trùng) và 50 dòng `payments` (cập nhật trạng thái) vào PostgreSQL.

**Bước 2.2:** Chạy pipeline ETL:
```bash
docker compose run --rm runner python cli.py pipeline --mode incremental
```
*Kết quả đối chứng trên Terminal:*
- `quiz_attempts: Đã trích xuất 100 dòng / Tổng sạch 1,010,350 dòng`.
- 👉 **Điểm sáng:** Trích xuất 100 dòng từ nguồn nhưng số dòng sạch chỉ tăng đúng **50 dòng**! Động cơ `ReplacingMergeTree` đã tự động khử trùng lặp 50 bản ghi cũ.

---

### 💥 KỊCH BẢN 3: TIÊM DỮ LIỆU BẨN & KIỂM THỬ KHẢ NĂNG CHỊU LỖI (BATCH 3)

**Bước 3.1:** Nạp file CSV từ `data/batch_3/` vào PostgreSQL OLTP:
```bash
docker compose run --rm runner python demo/load_dataset_to_oltp.py --batch 3
```
*Kết quả:* Nạp 55 dòng `users` (50 sạch + 5 email lỗi) và 50 dòng `quiz_attempts` sạch vào PostgreSQL.

**Bước 3.2:** Chạy pipeline ETL để xem khả năng chịu lỗi:
```bash
docker compose run --rm runner python cli.py pipeline --mode incremental
```
*Kết quả đối chứng:*
- `users: Đã trích xuất 55 dòng / Tổng sạch 50,150 dòng`.
- 👉 **Điểm sáng:** 50 học viên sạch được nạp vào Silver, **5 học viên email lỗi bị chặn đứng và đưa vào khu cách ly Quarantine**. Pipeline **KHÔNG BỊ SẬP (Zero-Crash)**!

**Bước 3.3:** Kiểm tra tận mắt 5 bản ghi bị cách ly trong Staging:
```bash
docker compose exec postgres psql -U learning_stage -d dwh_staging -c "
SELECT source_id, error_code, rejection_reason, raw_payload->>'email' AS bad_email
FROM quarantine.quarantine_records
WHERE source_id BETWEEN 50191 AND 50195;
"
```
*Kết quả hiển thị trên Terminal:*
```text
 source_id |    error_code     |                  rejection_reason                  |         bad_email          
-----------+-------------------+----------------------------------------------------+----------------------------
     50191 | ERR_INVALID_EMAIL | Email sai định dạng (thiếu @ hoặc có khoảng trắng) | user_missing_at_symbol.com
     50192 | ERR_INVALID_EMAIL | Email sai định dạng (thiếu @ hoặc có khoảng trắng) | user with space@domain.com
     50193 | ERR_INVALID_EMAIL | Email sai định dạng (thiếu @ hoặc có khoảng trắng) | bad_user_no_domain@
     50194 | ERR_INVALID_EMAIL | Email sai định dạng (thiếu @ hoặc có khoảng trắng) | bad@@domain.com
     50195 | ERR_INVALID_EMAIL | Email sai định dạng (thiếu @ hoặc có khoảng trắng) | @onlydomain.com
```

**Bước 3.4:** Kích hoạt cổng kiểm toán chất lượng dữ liệu:
```bash
docker compose run --rm runner python cli.py validate
```
*Kết quả:* `Kiểm toán chất lượng: ĐẠT 116/116 chỉ tiêu!`

---

## 🎯 4. TỔNG KẾT BẢO CHỨNG CHẤT LƯỢNG

Toàn bộ quy trình từ:  
**File CSV $\rightarrow$ PostgreSQL `oltp` $\rightarrow$ Pipeline ETL $\rightarrow$ PostgreSQL `silver` / `quarantine` $\rightarrow$ ClickHouse `gold`**  
đã diễn ra hoàn toàn tự nhiên theo đúng thiết kế kiến trúc chuẩn mực:
1. Pipeline đọc trực tiếp từ database nguồn PostgreSQL.
2. Nạp tăng dần thông minh dựa trên `updated_at > watermark`.
3. Tự động khử trùng lặp (Idempotent Deduplication).
4. Khả năng chịu lỗi cao (Fault-tolerant Forking Pipeline): Dữ liệu lỗi bị cách ly, dữ liệu sạch vẫn đi tiếp và hệ thống không bao giờ bị gián đoạn.
