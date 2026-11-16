# KẾ HOẠCH REBUILD HỆ THỐNG DATA WAREHOUSE TỪNG BƯỚC (STEP-BY-STEP REBUILD PLAN)
> **Thư mục triển khai:** `rebuild/`  
> **Phương pháp tiếp cận:** Chia nhỏ thành 8 giai đoạn logic tuần tự. Mỗi lần copy 1 vài file, bổ sung chú thích (comment) chi tiết bằng tiếng Việt, giải thích tường tận nguyên lý kỹ thuật và kiểm thử độc lập trước khi sang bước tiếp theo.

---

## 🗺️ TỔNG QUAN 8 GIAI ĐOẠN REBUILD

| Giai đoạn | Tên Giai Đoạn | Các File Cốt Lõi | Mục Tiêu & Tiêu Chí Nghiệm Thu | Trạng Thái |
| :---: | :--- | :--- | :--- | :---: |
| **1** | **Hạ Tầng, Môi Trường & Docker** | `requirements.txt`, `docker-compose.yml`, `Dockerfile`, `docker/*`, `.env.example` | Container PostgreSQL (55432) & ClickHouse (58123) khởi động `healthy`. | ✅ Đã hoàn thành (3 commits) |
| **2** | **Nguồn Tác Nghiệp OLTP** | `oltp/schema.sql`, `oltp/generate_data.py` | Tạo database `learning_oltp`, 11 bảng chuẩn hóa 3NF, sinh dữ liệu nguồn mẫu. | ✅ Đã hoàn thành (1 commit) |
| **3** | **Tiện Ích Chung & Quản Trị Hệ Thống** | `etl/config.py`, `etl/common.py`, `etl/bootstrap.py` | Kết nối DB, phân quyền 3 roles (`learning`, `learning_reader`, `learning_stage`). | ✅ Đã hoàn thành (1 commit) |
| **4** | **Staging, Vệ Sĩ Schema & Khu Cách Ly** | `dw/ddl/staging_schema.sql`, `etl/schema_guard.py`, `etl/validator.py`, `etl/watermark.py`, `etl/extract.py`, `etl/stage.py` | Trích xuất nguồn, ép kiểu an toàn, bắt dữ liệu bẩn vào `quarantine`, nạp `silver`. | ✅ Đã hoàn thành (2 commits) |
| **5** | **Kho Đa Chiều Gold & ClickHouse** | `dw/ddl/gold_schema.sql`, `dw/ddl/materialized_views.sql`, `etl/transform_gold.py`, `etl/load_clickhouse.py` | Galaxy Schema, xử lý SCD Type 2 (`user_sk`), nạp vào ClickHouse Gold qua Shadow Build. | ✅ Đã hoàn thành (2 commits) |
| **6** | **Cổng Kiểm Toán & Điều Phối Pipeline** | `etl/validate.py`, `etl/pipeline.py`, `cli.py` | 116 chỉ tiêu kiểm toán tự động, chạy pipeline full/incremental từ CLI. | ✅ Đã hoàn thành (1 commit) |
| **7** | **Phân Tích Nghiệp Vụ & Benchmark** | `analytics/queries.sql`, `analytics/reports.py`, `benchmark/postgres_schema.sql`, `benchmark/run_benchmark.py`, `benchmark/sql/*` | Xuất 10 báo cáo R01–R10, đo Benchmark Q1–Q7 và đối chiếu mã băm SHA256 khớp 100%. | ✅ Đã hoàn thành (2 commits) |
| **8** | **Kiểm Thử Chịu Lỗi, Datasets & Tài Liệu** | `tests/*`, `data/batch_*`, `demo/*`, `docs/*`, `README.md` | Bộ kiểm thử 3 đợt CSV, 10/10 unittest, bộ kịch bản E2E và hồ sơ tài liệu chuyên sâu 11 file. | ✅ Đã hoàn thành (3 commits) |

---

## 📋 CHI TIẾT KẾ HOẠCH TỪNG GIAI ĐOẠN

---

### 🚀 GIAI ĐOẠN 1: HẠ TẦNG, MÔI TRƯỜNG & DOCKER (INFRASTRUCTURE & DOCKER)
> **Mục tiêu:** Xây dựng nền tảng phần cứng ảo hóa, cấu hình RAM, CPU, mạng và dịch vụ cho cả 2 hệ quản trị cơ sở dữ liệu.

#### 📁 Danh sách file cần copy:
1. `requirements.txt` & `requirements.lock.txt`: Danh mục thư viện Python (psycopg2, clickhouse-connect, pandas, numpy, Faker...).
2. `Dockerfile`: Định nghĩa môi trường chạy cho service `runner` (Python 3.12, cài đặt thư viện).
3. `docker-compose.yml`: Điều phối 3 container:
   - `postgres`: PostgreSQL 16 bookworm (shared_buffers 256MB, work_mem 32MB, port 55432).
   - `clickhouse`: ClickHouse Server 24.8 LTS (port 58123 HTTP, port 59000 native).
   - `runner`: Container dùng chung để chạy các lệnh CLI.
4. `docker/clickhouse.xml`: Tinh chỉnh tài nguyên cho ClickHouse (bộ nhớ, luồng CPU).
5. `docker/init-databases.sql`: Script khởi tạo database ban đầu của PostgreSQL.
6. `.env.example`: File mẫu chứa các biến môi trường cấu hình cổng và mật khẩu.

#### 💡 Nội dung cần chú thích & giải thích:
- Tại sao phải cấu hình `shm_size: 256mb` và `shared_buffers=256MB` cho PostgreSQL khi xử lý triệu dòng.
- Cơ chế `healthcheck` của Docker để đảm bảo runner chỉ chạy khi database đã sẵn sàng kết nối.
- Cách ánh xạ cổng (Port mapping) tránh xung đột với PostgreSQL mặc định (5432 $\rightarrow$ 55432).

#### 🎯 Tiêu chí kiểm chứng:
```bash
docker compose up -d --wait postgres clickhouse
docker compose ps
# Cả 2 service đều hiển thị trạng thái "healthy"
```

---

### 🗄️ GIAI ĐOẠN 2: LỚP NGUỒN TÁC NGHIỆP OLTP (SOURCE OLTP LAYER)
> **Mục tiêu:** Thiết lập cấu trúc cơ sở dữ liệu giao dịch nguồn và cơ chế sinh dữ liệu mẫu giả lập thực tế.

#### 📁 Danh sách file cần copy:
1. `oltp/schema.sql`: DDL của 11 bảng tác nghiệp thuộc schema `oltp` (`users`, `courses`, `enrollments`, `payments`, `quiz_attempts`...).
2. `oltp/generate_data.py`: Script sinh dữ liệu giả lập thực tế với thư viện Faker (tên người Việt, email, thành phố) và NumPy (ma trận vector hóa hàng triệu dòng).

#### 💡 Nội dung cần chú thích & giải thích:
- Thiết kế chuẩn hóa 3NF của 11 bảng nguồn: tại sao tách `quizzes` và `quiz_attempts`, vai trò của `user_history`.
- Các ràng buộc toàn vẹn khóa ngoại (FK) và kiểm tra miền giá trị (`CHECK constraint`).
- Cách thức vector hóa bằng NumPy để sinh hàng triệu bản ghi trong thời gian dưới 2 phút.

#### 🎯 Tiêu chí kiểm chứng:
```bash
# Nạp schema và kiểm tra 11 bảng trong PostgreSQL learning_oltp:
psql -U learning -d learning_oltp -c "\dt oltp.*"
```

---

### ⚙️ GIAI ĐOẠN 3: TIỆN ÍCH CHUNG & QUẢN TRỊ BẢO MẬT (ETL CORE & BOOTSTRAP)
> **Mục tiêu:** Cài đặt các module tiện ích cốt lõi, quản lý kết nối và thiết lập ranh giới bảo mật 3 Roles.

#### 📁 Danh sách file cần copy:
1. `etl/config.py`: Đọc các biến môi trường cấu hình (`PGHOST`, `PGPORT`, `CH_HOST`, `CH_PORT`...).
2. `etl/common.py`: Các hàm tiện ích dùng chung: mở kết nối `source_connect()`, `staging_connect()`, `ch_connect()`, ghi JSON manifest, hàm `copy_frame` tối ưu tốc độ.
3. `etl/bootstrap.py`: Module quản trị hệ thống:
   - Tạo 2 database: `learning_oltp` và `dwh_staging`.
   - Tạo 2 Roles bảo mật: `learning_reader` (SELECT only, read-only transaction) và `learning_stage` (toàn quyền trên staging, cấm kết nối vào OLTP).
   - Cài đặt Trigger `set_updated_at` tự động trên toàn bộ 11 bảng để phục vụ CDC / High Water Mark.

#### 💡 Nội dung cần chú thích & giải thích:
- Nguyên tắc đặc quyền tối thiểu (Principle of Least Privilege) trong Enterprise Data Architecture.
- Tại sao phải ép `default_transaction_read_only = on` cho tài khoản `learning_reader`.
- Nguyên lý hoạt động của hàm trigger `clock_timestamp()` để bắt mốc trích xuất tăng dần.

#### 🎯 Tiêu chí kiểm chứng:
```bash
python -m etl.bootstrap
# Thử dùng user learning_reader chạy lệnh UPDATE trên oltp.users -> Phải bị từ chối với lỗi Read-only!
```

---

### 🛡️ GIAI ĐOẠN 4: VÙNG ĐỆM STAGING, VỆ SĨ SCHEMA & KHU CÁCH LY (STAGING & DATA CONTRACTS)
> **Mục tiêu:** Xây dựng tuyến phòng thủ đầu tiên của Data Warehouse: ép kiểu an toàn, bắt dữ liệu bẩn vào Quarantine và làm sạch dữ liệu vào Silver.

#### 📁 Danh sách file cần copy:
1. `dw/ddl/staging_schema.sql`: DDL của 3 schema trong `dwh_staging`:
   - `silver`: 11 bảng chứa dữ liệu sạch chuẩn hóa.
   - `quarantine`: Bảng `quarantine_records` (lưu mã lỗi, lý do và `raw_payload` dạng JSONB).
   - `staging`: Bảng `etl_watermarks` quản lý mốc thời gian trích xuất.
2. `etl/validator.py`: Kiểm định các quy tắc nghiệp vụ (Regex kiểm tra email, số tiền không âm, công thức `charged = original - discount`, thời gian logic).
3. `etl/schema_guard.py`: Tấm khiên bảo vệ schema: ép kiểu dữ liệu an toàn (`bigint`, `timestamp`, `text`), phòng ngừa Schema Drift.
4. `etl/watermark.py`: Đọc và cập nhật mốc High Water Mark cho từng bảng.
5. `etl/extract.py`: Trích xuất từng lô lớn (Batches 50,000 dòng) từ nguồn bằng Server-side Named Cursor.
6. `etl/stage.py`: Module điều phối trung tâm: Forking Pipeline rẽ 2 nhánh (sạch vào Silver, bẩn vào Quarantine), loại bỏ khóa ngoại mồ côi (`reject_orphans`), nạp siêu tốc qua Temp Table và UPSERT.

#### 💡 Nội dung cần chú thích & giải thích:
- Cơ chế Forking Pipeline: tại sao không ngắt sập hệ thống khi gặp dữ liệu lỗi mà đưa vào Quarantine.
- Bảng tạm `CREATE TEMP TABLE ... ON COMMIT DROP` kết hợp `COPY FROM STDIN` nhanh hơn hàng trăm lần so với `INSERT` từng dòng.
- Cách thiết kế bảng Watermark để đảm bảo tính bất biến (Idempotency) khi chạy lại nhiều lần.

#### 🎯 Tiêu chí kiểm chứng:
- Dữ liệu sạch được nạp đầy đủ vào các bảng `silver.*`.
- Bảng `quarantine.quarantine_records` bắt đúng các bản ghi vi phạm hợp đồng dữ liệu.

---

### 🌟 GIAI ĐOẠN 5: KHO ĐA CHIỀU GOLD & CLICKHOUSE (GOLD DIMENSIONAL MODELING)
> **Mục tiêu:** Chuyển đổi mô hình từ 3NF sang Galaxy Schema, xử lý lịch sử SCD Type 2 và nạp dữ liệu siêu nén vào ClickHouse.

#### 📁 Danh sách file cần copy:
1. `dw/ddl/gold_schema.sql`: DDL 7 Dimensions (`dim_user`, `dim_course`, `dim_date`...) và 4 Facts (`fact_payments`, `fact_enrollments`...) trên ClickHouse sử dụng động cơ `ReplacingMergeTree`.
2. `dw/ddl/materialized_views.sql` & `dw/ddl/aggregate_feeds.sql`: Bảng tổng hợp tính toán sẵn (Pre-aggregated MVs).
3. `etl/transform_gold.py`: Logic biến đổi nghiệp vụ:
   - Cấp phát Surrogate Keys (`user_sk`, `course_sk`...).
   - Xử lý SCD Type 2 cho học viên (`valid_from` $\rightarrow$ `valid_to`, `is_current`).
   - Phép nối thời gian ASOF / Point-in-time join giữa Facts và Dimensions.
   - Thêm phần tử `Unknown (sk = 0)` cho `dim_date`.
4. `etl/load_clickhouse.py`: Nạp dữ liệu vào ClickHouse theo kiến trúc **Shadow Build** (`gold_build` $\rightarrow$ Atomic Exchange sang `gold`).

#### 💡 Nội dung cần chú thích & giải thích:
- Mô hình Galaxy Schema và khái niệm Conformed Dimensions.
- Kỹ thuật SCD Type 2 và ví dụ thực tế học viên chuyển địa phương.
- Cơ chế khử trùng lặp tự động của động cơ `ReplacingMergeTree` trên ClickHouse.
- Kiến trúc Shadow Build Blue/Green giúp cập nhật kho dữ liệu mà không gây gián đoạn (Zero Downtime).

#### 🎯 Tiêu chí kiểm chứng:
```bash
# Kiểm tra dung lượng nén cột trên ClickHouse:
clickhouse-client -d gold --query "SELECT table, sum(rows), formatReadableSize(sum(data_compressed_bytes)) FROM system.parts WHERE database='gold' GROUP BY table;"
```

---

### 🚦 GIAI ĐOẠN 6: CỔNG KIỂM TOÁN CHẤT LƯỢNG & ĐIỀU PHỐI PIPELINE (QUALITY & CLI)
> **Mục tiêu:** Tích hợp quy trình kiểm toán tự động 116 chỉ tiêu và xây dựng giao diện dòng lệnh trung tâm.

#### 📁 Danh sách file cần copy:
1. `etl/validate.py`: Cổng kiểm toán tự động 116 chỉ tiêu (kiểm tra tính duy nhất, kiểm tra NULL, đối soát tổng tiền giữa PostgreSQL và ClickHouse, kiểm tra tính nhất quán giữa Facts và Dims).
2. `etl/pipeline.py`: Bộ điều phối luồng chạy hoàn chỉnh:
   - Chế độ `full`: Truncate và nạp lại toàn bộ.
   - Chế độ `incremental`: Chỉ nạp phần delta mới sinh, tái sử dụng Gold nếu không có thay đổi.
3. `cli.py`: Điểm vào thực thi duy nhất của dự án (`setup`, `generate`, `pipeline`, `validate`, `reports`, `benchmark`, `all`).

#### 💡 Nội dung cần chú thích & giải thích:
- Khái niệm Data Quality Gate: tại sao cần kiểm toán tự động trước khi công bố dữ liệu (Publishing).
- Thuật toán đối soát tiền tệ song song (Reconciliation): so sánh `sum(net_vnd)` giữa PostgreSQL và ClickHouse độc lập.
- Cách thiết kế CLI thân thiện, có tham số cấu hình rõ ràng.

#### 🎯 Tiêu chí kiểm chứng:
```bash
python cli.py pipeline --mode full
python cli.py validate
# Màn hình báo: "Quality: 116 checks passed"
```

---

### 📈 GIAI ĐOẠN 7: PHÂN TÍCH NGHIỆP VỤ & ĐỐI CHUẨN HIỆU NĂNG (ANALYTICS & BENCHMARK)
> **Mục tiêu:** Cài đặt 10 báo cáo phân tích kinh doanh chuẩn và bộ Benchmark Q1–Q7 đối chứng tốc độ giữa PostgreSQL và ClickHouse.

#### 📁 Danh sách file cần copy:
1. `analytics/queries.sql` & `analytics/reports.py`: 10 câu truy vấn phân tích nghiệp vụ (R01 Rollup, R02 Tỷ lệ hoàn thành, R04 Role-playing dates, R07 Drill-across, R09 CUBE...) và script tự động xuất CSV kèm SHA256 manifest.
2. `benchmark/postgres_schema.sql`: DDL tạo bản sao đối chứng 1:1 (`benchmark.*`) trong PostgreSQL.
3. `benchmark/queries.py` & `benchmark/run_benchmark.py`: Bộ điều phối Benchmark chạy 7 câu hỏi phân tích (Q1 đến Q7) đồng thời trên 2 database, so khớp mã băm SHA256 và tính tỷ lệ tăng tốc.
4. `benchmark/sql/*`: Các file SQL của từng câu hỏi phân tích cho cả 2 hệ quản trị.

#### 💡 Nội dung cần chú thích & giải thích:
- 6 phép toán phân tích OLAP kinh điển: ROLLUP, CUBE, Slice & Dice, Drill-Down, Drill-Across, Window Running Total.
- Ý nghĩa của việc băm SHA256 toàn bộ các dòng kết quả để chứng minh tính đúng đắn tuyệt đối.
- Phân tích nguyên nhân sâu xa vì sao ClickHouse nhanh hơn PostgreSQL từ 1.6x đến 38x.

#### 🎯 Tiêu chí kiểm chứng:
```bash
python cli.py reports
# Xuất đủ 10 file CSV tại artifacts/reports/
python cli.py benchmark --runs 3
# Khớp 100% SHA256 và ClickHouse nhanh vượt trội
```

---

### 🧪 GIAI ĐOẠN 8: BỘ KIỂM THỬ, DATASETS THỰC NGHIỆM & GIAO DIỆN (TESTING & DEMO)
> **Mục tiêu:** Hoàn thiện bộ kiểm thử tự động, 3 bộ Dataset CSV thực nghiệm chịu lỗi, giao diện Streamlit UI và toàn bộ hồ sơ tài liệu kỹ thuật.

#### 📁 Danh sách file cần copy:
1. `tests/test_schema_guard.py`, `tests/test_pipeline.py`, `tests/check_cube_parity.py`: 10 bài kiểm thử đơn vị và tích hợp chạy bằng Python unittest.
2. `data/batch_1/*`, `data/batch_2/*`, `data/batch_3/*`: 3 bộ dữ liệu CSV thực nghiệm (An toàn, Tăng dần + Trùng lặp, Chịu lỗi tiêm dữ liệu bẩn).
3. `demo/generate_csv_datasets.py` & `demo/load_dataset_to_oltp.py`: Script sinh và nạp dataset CSV vào PostgreSQL OLTP.
4. `demo/test_chaos_resilience.py`: Kịch bản kiểm thử chịu lỗi và khử trùng lặp 3 đợt tự động.
5. `demo/app.py`, `demo/Dockerfile`, `demo/requirements.txt`: Ứng dụng Web Dashboard tương tác bằng Streamlit.
6. `docs/*`: Toàn bộ 11 tài liệu kỹ thuật chuyên sâu (Data Quality, Lineage, Catalog, Contract, CLI Tour, Kimball Modeling...).
7. `README.md`: Cẩm nang hướng dẫn sử dụng và vận hành tổng thể dự án.

#### 💡 Nội dung cần chú thích & giải thích:
- Phương pháp kiểm thử khả năng chịu lỗi (Resilience Testing) trong hệ thống dữ liệu.
- Cách thiết kế giao diện Dashboard Streamlit để trực quan hóa dữ liệu từ ClickHouse.
- Cách tổ chức tài liệu kỹ thuật chuyên nghiệp theo tiêu chuẩn Data Governance quốc tế.

#### 🎯 Tiêu chí kiểm chứng:
```bash
python -m unittest discover tests           # 10/10 tests passed
python demo/test_chaos_resilience.py --all   # 3 đợt test passed
```

---

## 🎯 QUY TRÌNH PHỐI HỢP THỰC HIỆN TỪNG BƯỚC

Mỗi khi bạn sẵn sàng thực hiện một giai đoạn:
1. **Bạn copy 1 hoặc vài file** từ `btl/` sang `rebuild/` (theo đúng danh sách của giai đoạn đó).
2. **Tôi sẽ:**
   - Đọc và rà soát kỹ lưỡng nội dung các file bạn vừa copy.
   - Thêm **chú thích (comment) chi tiết bằng tiếng Việt** vào từng module: giải thích cấu trúc, ý nghĩa từng hàm/biến, các thuật ngữ kỹ thuật và lưu ý khi vận hành.
   - Viết phần giải thích trực quan, dễ hiểu gửi cho bạn, kèm câu lệnh kiểm thử thực tế ngay tại bước đó.
3. **Bạn kiểm tra và chạy thử**, sau khi bước đó hoạt động hoàn hảo, chúng ta sẽ chuyển sang giai đoạn tiếp theo!

---
*Kế hoạch đã được lưu trữ sẵn tại `rebuild/rebuild_plan.md`.*  
*Khi nào bạn sẵn sàng, chúng ta có thể bắt đầu ngay từ **Giai đoạn 1 (Hạ tầng, Môi trường & Docker)**!*
