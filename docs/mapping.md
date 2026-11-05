# Source-to-target mapping

## Bronze → Silver

Mọi bảng OLTP được copy đủ cột vào Bronze, giữ kiểu dữ liệu tương ứng (PostgreSQL integer → Int64, text → String, timestamp → DateTime UTC, nullable giữ Nullable), thêm `_run_id`, `_loaded_at`, `_source`. Full snapshot được đọc trong một transaction REPEATABLE READ.

Silver nhận đủ hàng/cột nghiệp vụ từ Bronze, bỏ ba metadata cột ingest. `full_name`, `city`, `country`, `title`, `category`, `difficulty`, `method_name`, `expertise` được trim; email trim/lowercase; country uppercase. Facts không chứa thuộc tính cần normalize nên INSERT SELECT trực tiếp. Không bỏ hàng lỗi: quality gate fail pipeline. Source PK/unique enforce dedup từ đầu.

## Dimensions

| Nguồn | Đích | Ánh xạ |
|---|---|---|
| generated dates | dim_date | 2022-01-01…2024-12-31, YYYYMMDD key và year/quarter/month/day; thêm unknown key 0 |
| silver.user_history | dim_user | history_id+10000000 → user_sk; giữ natural user_id, text đã clean, valid_from/to; is_current khi valid_to=2100-01-01 |
| silver.courses | dim_course | course_id+1000000 → course_sk; giữ course_id, title/category/difficulty, instructor_id, price_vnd |
| silver.instructors | dim_instructor | instructor_id+2000000 → instructor_sk; giữ natural key, full_name, expertise |
| silver.lessons | dim_lesson | lesson_id+3000000 → lesson_sk; giữ natural key, course_id, title, position |
| silver.quizzes | dim_quiz | quiz_id+4000000 → quiz_sk; giữ natural key, course_id, title, total_questions |
| silver.payment_methods | dim_payment_method | method_id+5000000 → method_sk; giữ method_id/name |

`silver.users` phục vụ snapshot người dùng hiện tại và audit; Gold SCD2 được lấy từ `silver.user_history`, không tạo lịch sử giả bằng cách nhân bản snapshot hiện tại.

## Facts

Mỗi fact giữ nguyên event primary key nguồn và enrollment_id nếu có. Course key luôn lookup dim_course bằng course_id. User key luôn lookup ASOF theo user_id và thời điểm sự kiện; validation bắt buộc kiểm tra sự kiện nằm trước valid_to. INNER JOIN các dim Type 1 có thể làm mất dòng nếu thiếu dimension: đối chiếu count và FK làm pipeline fail trong trường hợp đó.

| Đích | Event time dùng SCD2 | Key bổ sung | Measures / passthrough |
|---|---|---|---|
| fact_enrollments | enrolled_at | instructor lookup qua course.instructor_id; enrolled_date_sk=YYYYMMDD(enrolled_at); completed_date_sk=YYYYMMDD(completed_at) hoặc 0 | enrollment_id, enrolled_at/completed_at, lessons_completed; is_completed=completed_at IS NOT NULL |
| fact_payments | paid_at | instructor lookup qua course; method lookup qua method_id; date_sk=YYYYMMDD(paid_at) | payment_id, enrollment_id, transaction_id, paid_at, original_vnd/discount_vnd/charged_vnd/refunded giữ nguyên; net_vnd=charged_vnd×(1-refunded) |
| fact_lesson_completions | completed_at | lesson lookup qua lesson_id; date_sk=YYYYMMDD(completed_at) | completion_id, enrollment_id, completed_at, time_spent_seconds |
| fact_quiz_attempts | attempted_at | quiz lookup qua quiz_id; date_sk=YYYYMMDD(attempted_at) | attempt_id, enrollment_id, attempted_at, attempt_number, correct_count/total_questions/time_spent_seconds; is_passed=correct_count×100≥total_questions×70 |

Fact enrollment dùng user version lúc ghi danh, không đổi theo ngày hoàn thành. Nếu cùng học viên có sự kiện sau ngày đổi city, payment/lesson/quiz sẽ có user_sk phiên bản mới; dùng natural user_id để đếm người duy nhất qua các facts.

## SQL reports và truy nguyên

Các report trỏ trực tiếp Gold; không dùng CSV làm input tính toán. Mỗi CSV đi kèm pipeline_run, row count, SHA256 và source SQL trong `artifacts/reports/manifest.json`. Benchmark tải cùng Gold sang `PostgreSQL benchmark`, đối chiếu toàn bộ dòng bằng SHA256 rồi mới đo query. SQL thực thi được lưu tại `benchmark/sql/`.
