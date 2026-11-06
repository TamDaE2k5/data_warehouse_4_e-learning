# 📖 TỪ ĐIỂN DỮ LIỆU KHO DỮ LIỆU (DATA DICTIONARY)
## Hệ Thống Kho Dữ Liệu Học Trực Tuyến E-Learning (2022–2024)

> **Mô tả chung:**  
> Tài liệu này đặc tả chi tiết cấu trúc cột, kiểu dữ liệu, ràng buộc giá trị Nullable và ý nghĩa nghiệp vụ của toàn bộ các bảng trong hệ thống, bao gồm 3 tầng kiến trúc:
> 1. **Tầng Nguồn Tác Nghiệp (OLTP):** PostgreSQL `learning_oltp` (Schema `oltp`).
> 2. **Tầng Trung Chuyển (Staging & Silver):** PostgreSQL `dwh_staging` (Schema `staging`, `quarantine`, `silver`).
> 3. **Tầng Kho Dữ Liệu Đa Chiều (Gold):** ClickHouse `gold` (Galaxy Schema: 7 Dimensions, 4 Facts, 2 Aggregate Feeds).
> 
> *Quy ước chuẩn:* Toàn bộ mốc thời gian là chuẩn **UTC**. Đơn vị tiền tệ là **VND** (số nguyên).

---

## 📑 MỤC LỤC ĐIỀU HƯỚNG

- [1. Tầng Nguồn Tác Nghiệp: PostgreSQL `learning_oltp`](#1-tầng-nguồn-tác-nghiệp-postgresql-learning_oltp)
  - [1.1 oltp.courses](#11-oltpcourses)
  - [1.2 oltp.enrollments](#12-oltpenrollments)
  - [1.3 oltp.instructors](#13-oltpinstructors)
  - [1.4 oltp.lesson_completions](#14-oltplesson_completions)
  - [1.5 oltp.lessons](#15-oltplessons)
  - [1.6 oltp.payment_methods](#16-oltppayment_methods)
  - [1.7 oltp.payments](#17-oltppayments)
  - [1.8 oltp.quiz_attempts](#18-oltpquiz_attempts)
  - [1.9 oltp.quizzes](#19-oltpquizzes)
  - [1.10 oltp.user_history](#110-oltpuser_history)
  - [1.11 oltp.users](#111-oltpusers)
- [2. Tầng Trung Chuyển: PostgreSQL `dwh_staging`](#2-tầng-trung-chuyển-postgresql-dwh_staging)
  - [2.1 staging.etl_watermarks](#21-stagingetl_watermarks)
  - [2.2 quarantine.quarantine_records](#22-quarantinequarantine_records)
  - [2.3 Lớp dữ liệu sạch: schema `silver`](#23-lớp-dữ-liệu-sạch-schema-silver)
- [3. Tầng Kho Đa Chiều: ClickHouse `gold`](#3-tầng-kho-đa-chiều-clickhouse-gold)
  - [3.1 Các Bảng Chiều (Dimension Tables)](#31-các-bảng-chiều-dimension-tables)
    - [gold.dim_date](#golddim_date)
    - [gold.dim_user (SCD Type 2)](#golddim_user-scd-type-2)
    - [gold.dim_course](#golddim_course)
    - [gold.dim_instructor](#golddim_instructor)
    - [gold.dim_lesson](#golddim_lesson)
    - [gold.dim_payment_method](#golddim_payment_method)
    - [gold.dim_quiz](#golddim_quiz)
  - [3.2 Các Bảng Sự Kiện (Fact Tables)](#32-các-bảng-sự-kiện-fact-tables)
    - [gold.fact_payments](#goldfact_payments)
    - [gold.fact_enrollments](#goldfact_enrollments)
    - [gold.fact_lesson_completions](#goldfact_lesson_completions)
    - [gold.fact_quiz_attempts](#goldfact_quiz_attempts)
  - [3.3 Các Bảng Tổng Hợp Tính Sẵn (Aggregate Feeds)](#33-các-bảng-tổng-hợp-tính-sẵn-aggregate-feeds)
    - [gold.agg_monthly_revenue](#goldagg_monthly_revenue)
    - [gold.agg_course_completion](#goldagg_course_completion)

---

## 1. Tầng Nguồn Tác Nghiệp: PostgreSQL `learning_oltp`

### 1.1 `oltp.courses`
* **Mô tả:** Danh mục các khóa học được mở trên nền tảng.

| Tên cột | Kiểu dữ liệu | Nullable | Ràng buộc / Ý nghĩa nghiệp vụ |
| :--- | :--- | :---: | :--- |
| `course_id` | bigint | NO | Khóa chính (PK). Mã định danh khóa học. |
| `instructor_id` | bigint | NO | Khóa ngoại (FK $\rightarrow$ `instructors.instructor_id`). |
| `title` | text | NO | Tiêu đề tên khóa học. |
| `category` | text | NO | Nhóm khóa học: `Data`, `Programming`, `Business`, `Design`, `Language`. |
| `difficulty` | text | NO | Cấp độ: `beginner`, `intermediate`, `advanced`. |
| `price_vnd` | bigint | NO | Giá niêm yết của khóa học, VND integer $\ge 0$. |
| `created_at` | timestamptz | NO | Thời điểm tạo khóa học trên hệ thống (UTC). |
| `updated_at` | timestamptz | NO | Thời điểm cập nhật cuối cùng (phục vụ CDC Watermark). |

---

### 1.2 `oltp.enrollments`
* **Mô tả:** Thông tin đăng ký khóa học của học viên và trạng thái học tập.

| Tên cột | Kiểu dữ liệu | Nullable | Ràng buộc / Ý nghĩa nghiệp vụ |
| :--- | :--- | :---: | :--- |
| `enrollment_id` | bigint | NO | Khóa chính (PK). Mã lượt ghi danh. Khóa suy biến (Degenerate Key). |
| `user_id` | bigint | NO | Khóa ngoại (FK $\rightarrow$ `users.user_id`). Mã học viên. |
| `course_id` | bigint | NO | Khóa ngoại (FK $\rightarrow$ `courses.course_id`). Mã khóa học. |
| `enrolled_at` | timestamptz | NO | Thời điểm ghi danh (UTC). Dùng để tra cứu phiên bản SCD2 của User. |
| `completed_at` | timestamptz | YES | Thời điểm hoàn thành đủ 10 bài. NULL nếu chưa hoàn thành. |
| `lessons_completed` | smallint | NO | Số bài học đã hoàn thành cuối kỳ (10 nếu tốt nghiệp, 6 nếu đang học). |
| `updated_at` | timestamptz | NO | Thời điểm cập nhật trạng thái gần nhất (UTC). |

---

### 1.3 `oltp.instructors`
* **Mô tả:** Danh sách giảng viên giảng dạy trên nền tảng.

| Tên cột | Kiểu dữ liệu | Nullable | Ràng buộc / Ý nghĩa nghiệp vụ |
| :--- | :--- | :---: | :--- |
| `instructor_id` | bigint | NO | Khóa chính (PK). Mã định danh giảng viên. |
| `full_name` | text | NO | Họ và tên đầy đủ của giảng viên. |
| `expertise` | text | NO | Lĩnh vực chuyên môn chính của giảng viên. |
| `created_at` | timestamptz | NO | Thời điểm tạo hồ sơ giảng viên (UTC). |
| `updated_at` | timestamptz | NO | Thời điểm cập nhật thông tin giảng viên (UTC). |

---

### 1.4 `oltp.lesson_completions`
* **Mô tả:** Nhật ký chi tiết mỗi lần học viên hoàn thành xong một bài học cụ thể.

| Tên cột | Kiểu dữ liệu | Nullable | Ràng buộc / Ý nghĩa nghiệp vụ |
| :--- | :--- | :---: | :--- |
| `completion_id` | bigint | NO | Khóa chính (PK). Mã sự kiện hoàn thành bài. |
| `enrollment_id` | bigint | NO | Khóa ngoại (FK $\rightarrow$ `enrollments.enrollment_id`). |
| `user_id` | bigint | NO | Khóa ngoại (FK $\rightarrow$ `users.user_id`). |
| `course_id` | bigint | NO | Khóa ngoại (FK $\rightarrow$ `courses.course_id`). |
| `lesson_id` | bigint | NO | Khóa ngoại (FK $\rightarrow$ `lessons.lesson_id`). Mỗi khóa gồm 10 bài. |
| `completed_at` | timestamptz | NO | Mốc thời gian hoàn thành bài học (UTC). |
| `time_spent_seconds`| integer | NO | Thời gian học bài thực tế tính bằng giây ($>0$). |
| `updated_at` | timestamptz | NO | Thời điểm ghi nhận sự kiện (UTC). |

---

### 1.5 `oltp.lessons`
* **Mô tả:** Cấu trúc bài giảng chi tiết của từng khóa học.

| Tên cột | Kiểu dữ liệu | Nullable | Ràng buộc / Ý nghĩa nghiệp vụ |
| :--- | :--- | :---: | :--- |
| `lesson_id` | bigint | NO | Khóa chính (PK). Mã bài học. |
| `course_id` | bigint | NO | Khóa ngoại (FK $\rightarrow$ `courses.course_id`). Khóa học chứa bài này. |
| `title` | text | NO | Tiêu đề tên bài giảng. |
| `position` | smallint | NO | Thứ tự bài học trong giáo trình (từ 1 đến 10). |
| `created_at` | timestamptz | NO | Thời điểm tạo bài học (UTC). |
| `updated_at` | timestamptz | NO | Thời điểm chỉnh sửa nội dung bài học (UTC). |

---

### 1.6 `oltp.payment_methods`
* **Mô tả:** Danh mục các hình thức thanh toán được hỗ trợ.

| Tên cột | Kiểu dữ liệu | Nullable | Ràng buộc / Ý nghĩa nghiệp vụ |
| :--- | :--- | :---: | :--- |
| `method_id` | bigint | NO | Khóa chính (PK). Mã phương thức thanh toán. |
| `method_name` | text | NO | Tên phương thức: `bank_transfer`, `card`, `wallet`. |
| `created_at` | timestamptz | NO | Thời điểm khai báo phương thức (UTC). |
| `updated_at` | timestamptz | NO | Thời điểm cập nhật (UTC). |

---

### 1.7 `oltp.payments`
* **Mô tả:** Lịch sử các giao dịch thanh toán học phí của học viên.

| Tên cột | Kiểu dữ liệu | Nullable | Ràng buộc / Ý nghĩa nghiệp vụ |
| :--- | :--- | :---: | :--- |
| `payment_id` | bigint | NO | Khóa chính (PK). Mã thanh toán nội bộ. |
| `enrollment_id` | bigint | NO | Khóa ngoại (FK $\rightarrow$ `enrollments.enrollment_id`). Mỗi enrollment có 1 payment. |
| `user_id` | bigint | NO | Khóa ngoại (FK $\rightarrow$ `users.user_id`). Học viên trả tiền. |
| `course_id` | bigint | NO | Khóa ngoại (FK $\rightarrow$ `courses.course_id`). Khóa học được mua. |
| `method_id` | bigint | NO | Khóa ngoại (FK $\rightarrow$ `payment_methods.method_id`). |
| `transaction_id` | text | NO | Mã giao dịch ngân hàng duy nhất dạng `TXN-...`. Chiều suy biến. |
| `paid_at` | timestamptz | NO | Thời điểm thanh toán thành công (UTC). |
| `original_vnd` | bigint | NO | Giá gốc danh nghĩa trước giảm giá (VND). |
| `discount_vnd` | bigint | NO | Tiền giảm giá khuyến mại (VND, trong khoảng $[0, \text{original\_vnd}]$). |
| `charged_vnd` | bigint | NO | Tiền thực tế bị trừ: $\text{original\_vnd} - \text{discount\_vnd}$. |
| `refunded` | smallint | NO | Cờ trạng thái: `1` là giao dịch đã hoàn tiền, `0` là bình thường. |
| `updated_at` | timestamptz | NO | Thời điểm cập nhật trạng thái thanh toán (UTC). |

---

### 1.8 `oltp.quiz_attempts`
* **Mô tả:** Nhật ký từng lần học viên bấm nộp bài thi trắc nghiệm.

| Tên cột | Kiểu dữ liệu | Nullable | Ràng buộc / Ý nghĩa nghiệp vụ |
| :--- | :--- | :---: | :--- |
| `attempt_id` | bigint | NO | Khóa chính (PK). Mã lượt làm bài thi. |
| `enrollment_id` | bigint | NO | Khóa ngoại (FK $\rightarrow$ `enrollments.enrollment_id`). |
| `user_id` | bigint | NO | Khóa ngoại (FK $\rightarrow$ `users.user_id`). |
| `course_id` | bigint | NO | Khóa ngoại (FK $\rightarrow$ `courses.course_id`). |
| `quiz_id` | bigint | NO | Khóa ngoại (FK $\rightarrow$ `quizzes.quiz_id`). Mỗi khóa có 1 quiz tổng kết. |
| `attempt_number` | smallint | NO | Số thứ tự lần thi (1 hoặc 2; dải 99–119 dùng cho dữ liệu test tăng dần). |
| `attempted_at` | timestamptz | NO | Thời điểm nộp bài thi (UTC). |
| `correct_count` | smallint | NO | Số câu trả lời đúng (từ 0 đến `total_questions`). |
| `total_questions`| smallint | NO | Tổng số câu hỏi của đề thi (mặc định 20 câu). |
| `time_spent_seconds`| integer | NO | Thời gian làm bài thi tính bằng giây ($>0$). |
| `updated_at` | timestamptz | NO | Thời điểm ghi nhận kết quả thi (UTC). |

---

### 1.9 `oltp.quizzes`
* **Mô tả:** Cấu hình đề thi trắc nghiệm đánh giá cuối khóa học.

| Tên cột | Kiểu dữ liệu | Nullable | Ràng buộc / Ý nghĩa nghiệp vụ |
| :--- | :--- | :---: | :--- |
| `quiz_id` | bigint | NO | Khóa chính (PK). Mã bài kiểm tra. |
| `course_id` | bigint | NO | Khóa ngoại (FK $\rightarrow$ `courses.course_id`). Khóa học áp dụng bài thi này. |
| `title` | text | NO | Tiêu đề bài kiểm tra. |
| `total_questions`| smallint | NO | Tổng số câu hỏi trong bài kiểm tra (mặc định 20 câu). |
| `created_at` | timestamptz | NO | Thời điểm tạo đề thi (UTC). |
| `updated_at` | timestamptz | NO | Thời điểm cập nhật đề thi (UTC). |

---

### 1.10 `oltp.user_history`
* **Mô tả:** Bảng lưu vết lịch sử thay đổi thông tin cư trú của học viên (SCD Type 2 Nguồn).

| Tên cột | Kiểu dữ liệu | Nullable | Ràng buộc / Ý nghĩa nghiệp vụ |
| :--- | :--- | :---: | :--- |
| `history_id` | bigint | NO | Khóa chính (PK). Mã định danh phiên bản lịch sử. |
| `user_id` | bigint | NO | Khóa ngoại (FK $\rightarrow$ `users.user_id`). Một học viên có thể có nhiều phiên bản. |
| `full_name` | text | NO | Họ và tên học viên tại thời điểm có hiệu lực. |
| `email` | text | NO | Email học viên tại thời điểm có hiệu lực. |
| `city` | text | NO | Thành phố cư trú trong phiên bản này (Ha Noi, Da Nang, Ho Chi Minh, Can Tho). |
| `country` | char(2) | NO | Mã quốc gia ISO alpha-2 (`VN`). |
| `valid_from` | timestamptz | NO | Mốc thời gian bắt đầu có hiệu lực của phiên bản (bao gồm mốc này). |
| `valid_to` | timestamptz | NO | Mốc thời gian hết hiệu lực (không bao gồm; `2100-01-01` đối với bản ghi hiện hành). |
| `updated_at` | timestamptz | NO | Thời điểm hệ thống ghi nhận phiên bản (UTC). |

---

### 1.11 `oltp.users`
* **Mô tả:** Bảng thông tin học viên hiện hành tại hệ thống tác nghiệp.

| Tên cột | Kiểu dữ liệu | Nullable | Ràng buộc / Ý nghĩa nghiệp vụ |
| :--- | :--- | :---: | :--- |
| `user_id` | bigint | NO | Khóa chính (PK). Mã định danh học viên duy nhất. |
| `full_name` | text | NO | Họ và tên học viên. |
| `email` | text | NO | Địa chỉ email của học viên. |
| `city` | text | NO | Thành phố cư trú hiện tại. |
| `country` | char(2) | NO | Mã quốc gia ISO alpha-2 (`VN`). |
| `created_at` | timestamptz | NO | Thời điểm đăng ký tài khoản học viên (UTC). |
| `updated_at` | timestamptz | NO | Thời điểm cập nhật tài khoản gần nhất (UTC). |

---

## 2. Tầng Trung Chuyển: PostgreSQL `dwh_staging`

### 2.1 `staging.etl_watermarks`
* **Mô tả:** Bảng theo dõi mốc phân thủy (Watermark) phục vụ cơ chế nạp tăng dần (CDC) không sót dòng.

| Tên cột | Kiểu dữ liệu | Nullable | Ràng buộc / Ý nghĩa nghiệp vụ |
| :--- | :--- | :---: | :--- |
| `table_name` | text | NO | Khóa chính (PK). Tên bảng nguồn tác nghiệp (ví dụ: `payments`, `quiz_attempts`). |
| `last_processed_time`| timestamptz | NO | Mốc `updated_at` lớn nhất đã nạp thành công ở mẻ trước. |
| `last_processed_id` | bigint | NO | Khóa chính lớn nhất tại mốc thời gian đó (chống trùng mốc cùng giây). |
| `last_run_id` | text | NO | Mã UUID của lần chạy pipeline thành công gần nhất. |

---

### 2.2 `quarantine.quarantine_records`
* **Mô tả:** Trạm kiểm dịch bắt giữ các bản ghi bẩn vi phạm luật nghiệp vụ hoặc sai kiểu dữ liệu.

| Tên cột | Kiểu dữ liệu | Nullable | Ràng buộc / Ý nghĩa nghiệp vụ |
| :--- | :--- | :---: | :--- |
| `table_name` | text | NO | Tên bảng phát hiện bản ghi lỗi. |
| `source_id` | bigint | NO | Khóa chính từ bảng nguồn của bản ghi bị từ chối. |
| `source_updated_at` | timestamptz | NO | Mốc `updated_at` của bản ghi lỗi tại nguồn. |
| `error_code` | text | NO | Mã phân loại lỗi (ví dụ: `ERR_INVALID_EMAIL`, `ERR_FUTURE_TIMESTAMP`). |
| `rejection_reason` | text | NO | Diễn giải chi tiết lý do bản ghi bị cách ly. |
| `detected_at` | timestamptz | NO | Thời điểm hệ thống phát hiện và đưa vào cách ly (mặc định: `now()`). |
| `raw_payload` | jsonb | NO | Bản chụp toàn bộ dòng dữ liệu nguyên trạng ở định dạng JSONB để tra cứu và khôi phục. |

---

### 2.3 Lớp dữ liệu sạch: schema `silver`
* **Mô tả:** Bao gồm 11 bảng tương ứng với 11 bảng nguồn OLTP nhưng đã được:
  - Cắt tỉa khoảng trắng dư thừa (`TRIM`).
  - Chuẩn hóa email thành chữ thường (`LOWERCASE`).
  - Chuẩn hóa mã quốc gia thành chữ hoa (`UPPERCASE`).
  - Lọc bỏ 100% bản ghi vi phạm luật chất lượng.
  - Phục vụ làm nguồn cấp dữ liệu sạch (*Trusted Staging*) để tải vào ClickHouse Gold.

---

## 3. Tầng Kho Đa Chiều: ClickHouse `gold`

### 3.1 Các Bảng Chiều (Dimension Tables)

#### `gold.dim_date`
* **Đặc tính:** Chiều Thời gian chuẩn hóa (Conformed Role-Playing Dimension).
* **Engine:** `MergeTree() ORDER BY date_sk`. Quy mô: 1.097 dòng (3 năm 2022–2024 + dòng 0 cho Unknown).

| Tên cột | Kiểu dữ liệu | Ý nghĩa nghiệp vụ |
| :--- | :--- | :--- |
| `date_sk` | Int64 | Khóa chính chiều (PK). Định dạng số nguyên YYYYMMDD (ví dụ: `20230701`). Dòng `0` là Unknown. |
| `full_date` | Date | Ngày lịch chuẩn. Giá trị `1970-01-01` đại diện cho ngày chưa xác định. |
| `year` | Int64 | Năm dương lịch (2022, 2023, 2024). |
| `quarter` | Int64 | Quý trong năm (1, 2, 3, 4). |
| `month` | Int64 | Tháng trong năm (1 đến 12). |
| `day` | Int64 | Ngày trong tháng (1 đến 31). |

---

#### `gold.dim_user` (SCD Type 2)
* **Đặc tính:** Chiều Học viên bảo toàn lịch sử cư trú (Slowly Changing Dimension Type 2).
* **Engine:** `ReplacingMergeTree() ORDER BY (user_id, valid_from)`. Quy mô: 60.000 dòng.

| Tên cột | Kiểu dữ liệu | Ý nghĩa nghiệp vụ |
| :--- | :--- | :--- |
| `user_sk` | Int64 | Khóa thay thế chiều (Surrogate Key) = `history_id + 10000000`. Mỗi phiên bản có `user_sk` riêng. |
| `user_id` | Int64 | Khóa tự nhiên nguồn. Dùng để đếm số học viên phân biệt (`COUNT(DISTINCT user_id)`). |
| `full_name` | String | Họ và tên học viên (đã làm sạch khoảng trắng). |
| `email` | String | Email học viên (đã chuẩn hóa chữ thường). |
| `city` | LowCardinality(String) | Thành phố cư trú (tối ưu nén bộ nhớ qua từ điển LowCardinality). |
| `country` | LowCardinality(String) | Mã quốc gia ISO alpha-2 (`VN`). |
| `valid_from` | DateTime('UTC') | Mốc thời gian bắt đầu có hiệu lực của phiên bản cư trú (inclusive). |
| `valid_to` | DateTime('UTC') | Mốc thời gian hết hiệu lực của phiên bản (exclusive; `2100-01-01` cho bản ghi hiện hành). |
| `is_current` | Int64 | Cờ hiệu: `1` là phiên bản địa chỉ hiện tại, `0` là phiên bản lịch sử cũ. |

---

#### `gold.dim_course`
* **Engine:** `MergeTree() ORDER BY course_sk`. Quy mô: 1.000 dòng.

| Tên cột | Kiểu dữ liệu | Ý nghĩa nghiệp vụ |
| :--- | :--- | :--- |
| `course_sk` | Int64 | Khóa thay thế chiều = `course_id + 1000000`. |
| `course_id` | Int64 | Mã khóa học ở hệ thống tác nghiệp nguồn. |
| `title` | String | Tiêu đề tên khóa học. |
| `category` | LowCardinality(String) | Nhóm ngành đào tạo: Data, Programming, Business, Design, Language. |
| `difficulty` | LowCardinality(String) | Cấp độ khó: beginner, intermediate, advanced. |
| `instructor_id` | Int64 | Khóa ngoại tham chiếu giảng viên phụ trách. |
| `price_vnd` | Int64 | Giá niêm yết hiện hành của khóa học (VND). |

---

#### `gold.dim_instructor`
* **Engine:** `MergeTree() ORDER BY instructor_sk`. Quy mô: 100 dòng.

| Tên cột | Kiểu dữ liệu | Ý nghĩa nghiệp vụ |
| :--- | :--- | :--- |
| `instructor_sk` | Int64 | Khóa thay thế chiều = `instructor_id + 2000000`. |
| `instructor_id` | Int64 | Mã giảng viên ở hệ thống tác nghiệp nguồn. |
| `full_name` | String | Họ và tên giảng viên. |
| `expertise` | LowCardinality(String) | Lĩnh vực chuyên môn chính. |

---

#### `gold.dim_lesson`
* **Engine:** `MergeTree() ORDER BY lesson_sk`. Quy mô: 10.000 dòng.

| Tên cột | Kiểu dữ liệu | Ý nghĩa nghiệp vụ |
| :--- | :--- | :--- |
| `lesson_sk` | Int64 | Khóa thay thế chiều = `lesson_id + 3000000`. |
| `lesson_id` | Int64 | Mã bài giảng nguồn. |
| `course_id` | Int64 | Mã khóa học chứa bài giảng này. |
| `title` | String | Tiêu đề tên bài giảng. |
| `position` | Int64 | Thứ tự bài trong chương trình đào tạo (1–10). |

---

#### `gold.dim_payment_method`
* **Engine:** `MergeTree() ORDER BY method_sk`. Quy mô: 3 dòng.

| Tên cột | Kiểu dữ liệu | Ý nghĩa nghiệp vụ |
| :--- | :--- | :--- |
| `method_sk` | Int64 | Khóa thay thế chiều = `method_id + 5000000`. |
| `method_id` | Int64 | Mã phương thức thanh toán nguồn. |
| `method_name` | LowCardinality(String) | Tên phương thức: `bank_transfer`, `card`, `wallet`. |

---

#### `gold.dim_quiz`
* **Engine:** `MergeTree() ORDER BY quiz_sk`. Quy mô: 1.000 dòng.

| Tên cột | Kiểu dữ liệu | Ý nghĩa nghiệp vụ |
| :--- | :--- | :--- |
| `quiz_sk` | Int64 | Khóa thay thế chiều = `quiz_id + 4000000`. |
| `quiz_id` | Int64 | Mã đề thi trắc nghiệm nguồn. |
| `course_id` | Int64 | Mã khóa học có đề thi này. |
| `title` | String | Tiêu đề đề thi. |
| `total_questions`| Int64 | Tổng số câu hỏi của đề thi (20 câu). |

---

### 3.2 Các Bảng Sự Kiện (Fact Tables)

#### `gold.fact_payments`
* **Loại Fact:** Transaction Fact (Sự kiện giao dịch thanh toán).
* **Engine:** `MergeTree() PARTITION BY toYYYYMM(paid_at) ORDER BY (date_sk, payment_id)`. Quy mô: 500.000 dòng.

| Tên cột | Kiểu dữ liệu | Ý nghĩa nghiệp vụ |
| :--- | :--- | :--- |
| `payment_id` | Int64 | Khóa suy biến định danh giao dịch nguồn. |
| `enrollment_id` | Int64 | Khóa lượt ghi danh tương ứng. |
| `transaction_id` | String | Mã giao dịch ngân hàng/cổng thanh toán (Degenerate Dimension). |
| `user_sk` | Int64 | Khóa nối `dim_user` theo giải thuật ASOF JOIN SCD2 tại thời điểm trả tiền. |
| `course_sk` | Int64 | Khóa ngoại nối `dim_course`. |
| `instructor_sk` | Int64 | Khóa ngoại nối `dim_instructor` nhận doanh thu. |
| `method_sk` | Int64 | Khóa ngoại nối `dim_payment_method`. |
| `date_sk` | Int64 | Khóa ngoại nối `dim_date` theo ngày thanh toán (`paid_at`). |
| `paid_at` | DateTime('UTC') | Mốc thời gian giao dịch thanh toán thành công (UTC). |
| `original_vnd` | Int64 | Độ đo (Measure): Giá gốc của khóa học (GMV). |
| `discount_vnd` | Int64 | Độ đo (Measure): Tiền chiết khấu giảm giá. |
| `charged_vnd` | Int64 | Độ đo (Measure): Tiền thực thu từ tài khoản học viên. |
| `refunded` | Int64 | Cờ hoàn tiền: `1` là giao dịch đã hoàn trả, `0` là giữ lại. |
| `net_vnd` | Int64 | Độ đo tính toán: Doanh thu thuần = `charged_vnd * (1 - refunded)`. |

---

#### `gold.fact_enrollments`
* **Loại Fact:** Accumulating Snapshot Fact (Tiến độ học tập tích lũy).
* **Engine:** `ReplacingMergeTree(updated_at) PARTITION BY toYYYYMM(enrolled_at) ORDER BY enrollment_id`. Quy mô: 500.000 dòng.

| Tên cột | Kiểu dữ liệu | Ý nghĩa nghiệp vụ |
| :--- | :--- | :--- |
| `enrollment_id` | Int64 | Khóa suy biến định danh lượt ghi danh. |
| `user_sk` | Int64 | Khóa nối `dim_user` tại thời điểm bắt đầu ghi danh (`enrolled_at`). |
| `course_sk` | Int64 | Khóa ngoại nối `dim_course`. |
| `instructor_sk` | Int64 | Khóa ngoại nối `dim_instructor`. |
| `enrolled_date_sk` | Int64 | Khóa nối `dim_date` theo ngày ghi danh (Role-Playing Date 1). |
| `completed_date_sk`| Int64 | Khóa nối `dim_date` theo ngày tốt nghiệp (Role-Playing Date 2; `0` nếu chưa xong). |
| `enrolled_at` | DateTime('UTC') | Mốc thời gian ghi danh (UTC). |
| `completed_at` | Nullable(DateTime('UTC')) | Mốc thời gian hoàn thành khóa học (UTC). |
| `lessons_completed`| Int64 | Số bài giảng đã hoàn thành tích lũy. |
| `is_completed` | Int64 | Cờ hoàn thành: `1` khi học đủ 10 bài, `0` khi đang học dở. |

---

#### `gold.fact_lesson_completions`
* **Loại Fact:** Transaction Fact (Hành vi học tập từng bài).
* **Engine:** `MergeTree() PARTITION BY toYYYYMM(completed_at) ORDER BY (date_sk, completion_id)`. Quy mô: 4.190.000 dòng.

| Tên cột | Kiểu dữ liệu | Ý nghĩa nghiệp vụ |
| :--- | :--- | :--- |
| `completion_id` | Int64 | Khóa định danh sự kiện hoàn thành bài. |
| `enrollment_id` | Int64 | Khóa lượt ghi danh chứa bài này. |
| `user_sk` | Int64 | Khóa nối `dim_user` tại thời điểm hoàn thành bài học. |
| `course_sk` | Int64 | Khóa ngoại nối `dim_course`. |
| `lesson_sk` | Int64 | Khóa ngoại nối `dim_lesson`. |
| `date_sk` | Int64 | Khóa ngoại nối `dim_date` theo ngày học xong. |
| `completed_at` | DateTime('UTC') | Mốc thời gian học xong bài (UTC). |
| `time_spent_seconds`| Int64 | Thời gian học bài thực tế tính bằng giây. |

---

#### `gold.fact_quiz_attempts`
* **Loại Fact:** Transaction Fact (Kết quả làm bài thi trắc nghiệm).
* **Engine:** `ReplacingMergeTree() PARTITION BY toYYYYMM(attempted_at) ORDER BY (enrollment_id, quiz_sk, attempt_number)`. Quy mô: 1.030.000 dòng.

| Tên cột | Kiểu dữ liệu | Ý nghĩa nghiệp vụ |
| :--- | :--- | :--- |
| `attempt_id` | Int64 | Khóa định danh lượt thi. |
| `enrollment_id` | Int64 | Khóa lượt ghi danh tham gia thi. |
| `user_sk` | Int64 | Khóa nối `dim_user` tại thời điểm làm bài thi. |
| `course_sk` | Int64 | Khóa ngoại nối `dim_course`. |
| `quiz_sk` | Int64 | Khóa ngoại nối `dim_quiz`. |
| `date_sk` | Int64 | Khóa ngoại nối `dim_date` theo ngày nộp bài thi. |
| `attempted_at` | DateTime('UTC') | Mốc thời gian nộp bài thi (UTC). |
| `attempt_number` | Int64 | Lần thi thứ mấy (1, 2 hoặc 99..119 khi nạp tăng dần). |
| `correct_count` | Int64 | Số câu trả lời đúng (từ 0 đến 20). |
| `total_questions`| Int64 | Tổng số câu hỏi của bài thi (20 câu). |
| `time_spent_seconds`| Int64 | Thời gian làm bài thi tính bằng giây. |
| `is_passed` | Int64 | Cờ đạt: `1` khi điểm $\ge 70\%$ (đúng $\ge 14/20$ câu), `0` khi trượt. |

---

### 3.3 Các Bảng Tổng Hợp Tính Sẵn (Aggregate Feeds)

#### `gold.agg_monthly_revenue`
* **Engine:** `SummingMergeTree() ORDER BY month`.
* **Mục đích:** Phục vụ tức thì các báo cáo tài chính hàng tháng với độ trễ dưới 4 ms.

| Tên cột | Kiểu dữ liệu | Ý nghĩa nghiệp vụ |
| :--- | :--- | :--- |
| `month` | Int64 | Khóa tháng định dạng số nguyên YYYYMM (ví dụ: `202405`). |
| `gmv` | Int64 | Tổng giá trị giao dịch gộp trước giảm giá trong tháng ($\sum \text{original\_vnd}$). |
| `discount_vnd` | Int64 | Tổng số tiền đã chiết khấu giảm giá trong tháng. |
| `refund_vnd` | Int64 | Tổng số tiền đã hoàn trả cho học viên trong tháng. |
| `net_vnd` | Int64 | Doanh thu thuần thực tế giữ lại của tháng. |
| `refunds` | Int64 | Tổng số giao dịch bị hoàn tiền trong tháng. |
| `payments` | Int64 | Tổng số giao dịch thanh toán phát sinh trong tháng. |

---

#### `gold.agg_course_completion`
* **Engine:** `SummingMergeTree() ORDER BY course_sk`.
* **Mục đích:** Đánh giá hiệu quả đào tạo và tỷ lệ hoàn thành theo từng khóa học.

| Tên cột | Kiểu dữ liệu | Ý nghĩa nghiệp vụ |
| :--- | :--- | :--- |
| `course_sk` | Int64 | Khóa thay thế của khóa học. |
| `enrollments` | Int64 | Tổng số lượt học viên đã ghi danh vào khóa học. |
| `completions` | Int64 | Số lượng học viên đã hoàn thành xuất sắc đủ 10 bài giảng. |
| `completion_days` | Int64 | Tổng số ngày học cần thiết để hoàn thành (dùng tính số ngày trung bình). |
