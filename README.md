# Online Learning Data Warehouse (Hệ Thống Kho Dữ Liệu Học Trực Tuyến 2022–2024)

[![Database: PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16.6-blue.svg)](https://www.postgresql.org/)
[![OLAP: ClickHouse 24.8 LTS](https://img.shields.io/badge/ClickHouse-24.8%20LTS-yellow.svg)](https://clickhouse.com/)
[![Language: Python 3.12](https://img.shields.io/badge/Python-3.12%2B-green.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-lightgrey.svg)](LICENSE)
[![Quality: 116 Checks Passed](https://img.shields.io/badge/Quality%20Gates-116%2F116%20Passed-brightgreen.svg)](docs/data_quality.md)

---

## 🧭 1. GIỚI THIỆU TỔNG QUAN

Dự án **Online Learning Data Warehouse** là hệ thống kho dữ liệu cấp doanh nghiệp được thiết kế theo phương pháp luận chiều của **Ralph Kimball**, mô phỏng nền tảng đào tạo trực tuyến quy mô lớn giai đoạn 2022–2024 (quy mô trên **5.72 triệu bản ghi sự kiện**).

Hệ thống giải quyết trọn vẹn các thách thức kỹ thuật phức tạp trong kỹ nghệ dữ liệu hiện đại:
1. **Phân tách bảo mật nghiêm ngặt (Zero Trust RBAC):** Cách ly hoàn toàn nguồn tác nghiệp OLTP với tầng phân tích thông qua 3 tài khoản chuyên biệt (`learning_reader`, `learning_stage`, `learning_admin`). Tài khoản ETL đọc nguồn chỉ có quyền `SELECT` và ép giao dịch `READ ONLY`.
2. **Phòng thủ trôi dạt lược đồ (Schema Drift Defense):** Module `Schema Guard` giám sát từng cột dữ liệu, tự động chặn đứng và cảnh báo khi nguồn OLTP tự ý đổi kiểu dữ liệu, đổi tên cột hoặc xóa cột.
3. **Trạm kiểm dịch dữ liệu lỗi (Quarantine Pattern):** Bắt và cô lập các bản ghi dị thường (email sai định dạng, ngày tương lai, số tiền âm) vào vùng cách ly `quarantine_records` dưới dạng JSON nguyên bản, giúp toàn bộ luồng nạp tiếp tục chạy an toàn (**Zero-Crash ETL**).
4. **Lịch sử biến động đa thời gian (SCD Type 2):** Quản lý lịch sử học viên thay đổi nơi cư trú bằng kỹ thuật khoảng thời gian có hiệu lực `[valid_from, valid_to)` và thực hiện ghép dữ liệu chính xác bằng thuật toán `ASOF JOIN`.
5. **Kho dữ liệu đa chiều hiệu năng cao (ClickHouse Galaxy Schema):** 4 bảng Fact độc lập đa hạt (*multi-grain*) dùng chung các Dimension chuẩn hóa (*Conformed Dimensions*), kết hợp bảng tổng hợp tính sẵn (*Materialized Views*) và cơ chế nén cột giúp tăng tốc truy vấn phân tích từ **1.25× đến 38.75×** so với CSDL quan hệ.
6. **Công bố không gián đoạn (Zero-Downtime Shadow Publishing):** Dựng toàn bộ kho Gold trong database bóng tạm thời (`gold_shadow`), vượt qua cổng kiểm toán rồi mới hoán đổi nguyên tử (*atomic exchange*), bảo vệ 100% người dùng truy vấn không bị gián đoạn.

---

## 🏛️ 2. KIẾN TRÚC TỔNG THỂ HỆ THỐNG

```
                          LUỒNG DỮ LIỆU ĐI QUA 4 TẦNG (DATA FLOW PIPELINE)
                                                   
   [1. NGUỒN TÁC NGHIỆP OLTP]        [2. VÙNG ĐỆM STAGING & QUARANTINE]       [3. KHO ĐA CHIỀU GOLD DW]
        PostgreSQL :55432                     PostgreSQL :55432                    ClickHouse :58123
   ┌───────────────────────────┐         ┌───────────────────────────┐         ┌───────────────────────┐
   │ database: learning_oltp   │         │ database: dwh_staging     │         │ database: gold        │
   │ • 11 bảng 3NF tác nghiệp  │ ──────> │ • schema: staging (đệm)   │ ──────> │ • 4 Fact Tables       │
   │ • 5.72M bản ghi 2022-2024 │  (ETL)  │ • schema: silver (sạch)   │ (Shadow)│ • 6 Conformed Dims    │
   │ • Quyền: SELECT READ-ONLY │         │ • schema: quarantine (lỗi)│         │ • 5 Materialized Views│
   └───────────────────────────┘         └───────────────────────────┘         └───────────────────────┘
                                                       │                                   │
                                                       ▼                                   ▼
                                            [CỔNG KIỂM TOÁN TỰ ĐỘNG]             [PHÂN TÍCH & BENCHMARK]
                                            • 116 Quality Gates                  • 10 Báo cáo SQL (R01-R10)
                                            • Đối soát tài chính 100%            • Đo tốc độ PG vs CH (Q1-Q7)
```

### Bảng Ma Trận Chiều (Bus Matrix)

| Bảng Sự Kiện (Fact Table) | Hạt Dữ Liệu (Grain) | Date Dim | User Dim (SCD2) | Course Dim | Instructor Dim | Lesson Dim | Quiz Dim | Payment Method |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`fact_payments`** | 1 giao dịch thanh toán | ✓ (paid) | ✓ | ✓ | ✓ | | | ✓ |
| **`fact_enrollments`** | 1 lượt ghi danh (Accumulating) | ✓ (enrolled/completed) | ✓ | ✓ | ✓ | | | |
| **`fact_lesson_completions`** | 1 bài giảng học xong | ✓ (completed) | ✓ | ✓ | | ✓ | | |
| **`fact_quiz_attempts`** | 1 lượt thử làm bài quiz | ✓ (attempted) | ✓ | ✓ | | | ✓ | |

---

## 🚀 3. HƯỚNG DẪN KHỞI CHẠY SIÊU TỐC (QUICK START)

### Yêu Cầu Môi Trường
* Hệ điều hành: Linux, macOS hoặc Windows (WSL2 / Docker Desktop).
* **Docker Engine** có hỗ trợ **Docker Compose v2**.
* Không cần cài đặt Python, PostgreSQL hay ClickHouse trên máy host; tất cả đều chạy hoàn toàn bên trong Docker.

### Các Bước Vận Hành Qua Dòng Lệnh (CLI)

Mở Terminal tại thư mục dự án và thực hiện tuần tự các lệnh sau:

```bash
# ------------------------------------------------------------------------------
# BƯỚC 1: KHỞI ĐỘNG CÁC MÁY CHỦ CƠ SỞ DỮ LIỆU
# ------------------------------------------------------------------------------
docker compose up -d --wait postgres clickhouse

# ------------------------------------------------------------------------------
# BƯỚC 2: BUILD MÔI TRƯỜNG THỰC THI PYTHON (RUNNER)
# ------------------------------------------------------------------------------
docker compose build runner

# ------------------------------------------------------------------------------
# BƯỚC 3: KHỞI TẠO HẠ TẦNG VÀ PHÂN QUYỀN BẢO MẬT (SETUP)
# Cài đặt schema, hàm băm, trigger tự động cập nhật mốc thời gian, tạo 3 roles
# ------------------------------------------------------------------------------
docker compose run --rm runner python cli.py setup

# ------------------------------------------------------------------------------
# BƯỚC 4: SINH DỮ LIỆU TÁC NGHIỆP MẪU (500K ENROLLMENTS, ~5.72M SỰ KIỆN)
# (Chỉ cần chạy 1 lần nếu cơ sở dữ liệu OLTP chưa có dữ liệu)
# ------------------------------------------------------------------------------
docker compose run --rm runner python cli.py generate

# ------------------------------------------------------------------------------
# BƯỚC 5: KÍCH HOẠT LUỒNG NẠP ETL SANG KHO ĐA CHIỀU (FULL PIPELINE)
# Trích xuất OLTP -> Staging -> Silver -> Dựng kho bóng ClickHouse -> Công bố Gold
# ------------------------------------------------------------------------------
docker compose run --rm runner python cli.py pipeline --mode full

# ------------------------------------------------------------------------------
# BƯỚC 6: KÍCH HOẠT CỔNG KIỂM TOÁN CHẤT LƯỢNG (116 QUALITY CHECKS)
# Đối soát ranh giới SCD2, kiểm tra doanh thu từng xu, kiểm tra tính duy nhất
# ------------------------------------------------------------------------------
docker compose run --rm runner python cli.py validate

# ------------------------------------------------------------------------------
# BƯỚC 7: XUẤT 10 BÁO CÁO PHÂN TÍCH QUẢN TRỊ KINH DOANH (CSV EXPORT)
# Thực thi các câu truy vấn phức tạp (Slice, Dice, Drill-down, Pivot, CUBE)
# ------------------------------------------------------------------------------
docker compose run --rm runner python cli.py reports

# ------------------------------------------------------------------------------
# BƯỚC 8: ĐO KIỂM HIỆU NĂNG ĐỐI CHUẨN BENCHMARK (CLICKHOUSE VS POSTGRESQL)
# Đối chiếu SHA256 11 bảng, chạy 7 bài toán phân tích Q1-Q7 với thời gian trung vị P50
# ------------------------------------------------------------------------------
docker compose run --rm runner python cli.py benchmark
```

---

## 🔬 4. KIỂM THỬ NÂNG CAO: TĂNG DẦN, CHỊU LỖI & SCD2

### 1. Thử Nghiệm Nạp Tăng Dần & Dữ Liệu Đến Muộn (Incremental & Late-Arriving)
```bash
# Bơm 10.000 lượt làm quiz đến muộn vào OLTP
docker compose run --rm runner python -m demo.seed_incremental

# Chạy nạp tăng dần lần 1: ClickHouse chỉ nạp +10.000 dòng mới (hành động: appended)
docker compose run --rm runner python cli.py pipeline --mode incremental

# Chạy nạp tăng dần lần 2: Đọc 0 dòng, mã băm không đổi, tái sử dụng Gold (gold_reused = True)
docker compose run --rm runner python cli.py pipeline --mode incremental
```

### 2. Kịch Bản Nghiệm Thu Tự Động Toàn Chu Trình (Automated E2E Verifier)
Tự động xác minh quyền Read-Only của ETL, bơm dữ liệu bẩn, kích hoạt Quarantine, cập nhật trạng thái SCD2 và kiểm tra tính bất biến:
```bash
docker compose run --rm runner python -m demo.verify_v2
```

### 3. Thực Nghiệm Kiểm Thử Chịu Lỗi Qua 3 Đợt Dataset CSV
Hệ thống cung cấp sẵn 3 tập dữ liệu CSV tại thư mục `data/` để mô phỏng sự cố thực tế:
* **Đợt 1 (`data/batch_1/`):** Nạp dữ liệu an toàn ban đầu (100% bản ghi hợp lệ).
* **Đợt 2 (`data/batch_2/`):** Nạp tăng dần kèm 50% bản ghi bị gửi trùng lặp (*ReplacingMergeTree tự động khử trùng lặp*).
* **Đợt 3 (`data/batch_3/`):** Cố ý tiêm 5 bản ghi sai email (*Zero-Crash, bản ghi bẩn bị tóm gọn vào Quarantine*).

```bash
# Nạp đợt 1
docker compose run --rm runner python demo/load_dataset_to_oltp.py --batch data/batch_1
docker compose run --rm runner python cli.py pipeline --mode incremental

# Nạp đợt 2
docker compose run --rm runner python demo/load_dataset_to_oltp.py --batch data/batch_2
docker compose run --rm runner python cli.py pipeline --mode incremental

# Nạp đợt 3
docker compose run --rm runner python demo/load_dataset_to_oltp.py --batch data/batch_3
docker compose run --rm runner python cli.py pipeline --mode incremental
```
*(Xem hướng dẫn chi tiết tại [docs/kiem_thu_chiu_loi_va_tang_dan.md](docs/kiem_thu_chiu_loi_va_tang_dan.md))*

---

## 📊 5. KẾT QUẢ ĐỐI CHUẨN HIỆU NĂNG (BENCHMARK Q1–Q7)

Cả hai hệ quản trị (PostgreSQL Mirror và ClickHouse Gold) được nạp dữ liệu hoàn toàn giống nhau, kiểm tra toàn vẹn bằng mã băm **SHA256 trên từng dòng**. Kết quả đo lường trung vị (P50 Median) qua 5 lượt chạy:

| Truy Vấn (Query) | Nghiệp Vụ Phân Tích | PostgreSQL (ms) | ClickHouse (ms) | Tăng Tốc (Speedup) |
| :--- | :--- | :---: | :---: | :---: |
| **Q1: monthly_revenue** | Tổng doanh thu theo từng tháng | 51.77 ms | 13.73 ms | **3.77×** |
| **Q2: slice_category** | Cắt lát doanh thu theo danh mục | 11.89 ms | 9.54 ms | **1.25×** |
| **Q3: four_dimensions** | Xoay 4 chiều (Tháng, Vùng, Danh mục, Trình độ) | 127.46 ms | 52.11 ms | **2.45×** |
| **Q4: window_running_total** | Doanh thu tích lũy cộng dồn (Window Function) | 50.70 ms | 14.08 ms | **3.60×** |
| **Q5: cube** | Gom cụm đa chiều CUBE kết hợp | 357.06 ms | 36.85 ms | **9.69×** |
| **Q6: drill_across** | Nối chéo Fact-to-Fact (Doanh thu & Số học viên) | 76.78 ms | 17.77 ms | **4.32×** |
| **Q7: learning_full_scan** | Quét toàn bộ 5.72 triệu bản ghi học tập | 6,533.24 ms | 168.62 ms | **38.75×** |

$\rightarrow$ **Nhận xét:** Trong các phép toán quét bảng lớn và gom cụm đa chiều (`Q5`, `Q7`), cơ chế lưu trữ theo cột và nén dữ liệu theo khối của ClickHouse vượt trội từ **9.7× đến 38.7×** so với CSDL quan hệ truyền thống.

---

## 📚 6. HỒ SƠ TÀI LIỆU KỸ THUẬT CHUYÊN SÂU

Toàn bộ tài liệu chi tiết được tổ chức có hệ thống trong thư mục [`docs/`](docs/):

1. **[docs/report_tom_tat.md](docs/report_tom_tat.md):** Báo cáo tóm tắt kiến trúc, kết quả đo nghiệm thu và các giới hạn kỹ thuật.
2. **[docs/huong_dan_tham_quan_he_thong.md](docs/huong_dan_tham_quan_he_thong.md):** Cẩm nang hướng dẫn tham quan 8 trạm dừng chân thực nghiệm trực tiếp trong Terminal.
3. **[docs/architecture.md](docs/architecture.md):** Bản thiết kế kiến trúc 4 tầng, Bus Matrix, kỹ thuật xử lý Surrogate Keys, SCD Type 2 và Role-Playing Dimensions.
4. **[docs/quy_trinh_mo_hinh_hoa_silver_sang_gold.md](docs/quy_trinh_mo_hinh_hoa_silver_sang_gold.md):** Phương pháp luận chuyển đổi mô hình 3NF (Silver) sang Galaxy Schema (Gold), kỹ thuật xử lý khoảng thời gian hiệu lực và ASOF JOIN.
5. **[docs/kiem_thu_chiu_loi_va_tang_dan.md](docs/kiem_thu_chiu_loi_va_tang_dan.md):** Cẩm nang thực nghiệm nạp 3 đợt dữ liệu CSV, kiểm tra khử trùng lặp và cách ly lỗi.
6. **[docs/data_quality.md](docs/data_quality.md):** Danh mục 116 chỉ tiêu kiểm toán chất lượng dữ liệu tự động.
7. **[docs/oltp_schema.md](docs/oltp_schema.md):** Đặc tả chi tiết 11 bảng CSDL tác nghiệp OLTP kèm sơ đồ quan hệ ERD.
8. **[docs/data_lineage.md](docs/data_lineage.md):** Bản đồ dòng chảy dữ liệu từ nguồn tác nghiệp đến các báo cáo phân tích.
9. **[docs/data_catalog.md](docs/data_catalog.md):** Từ điển dữ liệu chuẩn hóa và danh mục phân loại metadata toàn doanh nghiệp.
10. **[docs/data_contract.md](docs/data_contract.md):** Hợp đồng dữ liệu ràng buộc trách nhiệm giữa đội phát triển nguồn và đội kỹ sư kho dữ liệu.
11. **[docs/mapping.md](docs/mapping.md):** Bảng ánh xạ trường thuộc tính tương ứng qua từng tầng chuyển đổi.

---

## 🛠️ 7. DANH MỤC LỆNH CLI ĐIỀU HÀNH

```bash
python cli.py setup       # Khởi tạo DB, trigger và 3 roles bảo mật
python cli.py generate    # Sinh 5.72M dòng dữ liệu tác nghiệp
python cli.py pipeline    # Chạy ETL (--mode full hoặc --mode incremental)
python cli.py validate    # Kích hoạt 116 bài kiểm toán chất lượng
python cli.py reports     # Xuất 10 báo cáo kinh doanh R01-R10 sang CSV
python cli.py benchmark   # Chạy đo kiểm hiệu năng ClickHouse vs PostgreSQL
python cli.py all         # Thực hiện toàn bộ chu trình tự động liên hoàn
```
