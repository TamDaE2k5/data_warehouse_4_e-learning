# Data dictionary

Sinh từ schema đang chạy; mô tả nghiệp vụ được quản lý trong `docs/generate_dictionary.py`.

Timestamps đều UTC. Tiền là integer VND. Null chỉ được chấp nhận nơi kiểu Nullable/nullable ghi rõ.
Gold không enforce FK vật lý; `etl/validate.py` enforce quality gate. Grain và mapping xem `architecture.md`.

## PostgreSQL oltp.courses

| Cột | Kiểu | Nullable | Ý nghĩa |
|---|---|---|---|
| course_id | bigint | NO | Khóa nghiệp vụ khóa học. |
| instructor_id | bigint | NO | Khóa nghiệp vụ giảng viên. |
| title | text | NO | Tiêu đề khóa/bài/quiz theo bảng. |
| category | text | NO | Nhóm khóa: Data, Programming, Business, Design, Language. |
| difficulty | text | NO | beginner, intermediate, advanced. |
| price_vnd | bigint | NO | Giá hiện tại khóa, VND integer ≥0. |
## PostgreSQL oltp.enrollments

| Cột | Kiểu | Nullable | Ý nghĩa |
|---|---|---|---|
| enrollment_id | bigint | NO | Khóa ghi danh; unique user/course; degenerate reference trên facts. |
| user_id | bigint | NO | Khóa nghiệp vụ học viên, dùng distinct learner qua nhiều phiên bản. |
| course_id | bigint | NO | Khóa nghiệp vụ khóa học. |
| enrolled_at | timestamp without time zone | NO | Thời điểm ghi danh UTC; Gold user version được tra tại thời điểm này. |
| completed_at | timestamp without time zone | YES | Thời điểm hoàn thành UTC; nullable cho enrollment chưa hoàn thành, không null cho lesson completion. |
| lessons_completed | smallint | NO | Số bài đã hoàn thành cuối kỳ; 10 nếu complete, 6 nếu chưa complete trong generator. |
## PostgreSQL oltp.instructors

| Cột | Kiểu | Nullable | Ý nghĩa |
|---|---|---|---|
| instructor_id | bigint | NO | Khóa nghiệp vụ giảng viên. |
| full_name | text | NO | Tên giả lập Faker; Silver trim khoảng trắng. |
| expertise | text | NO | Lĩnh vực chuyên môn giảng viên giả lập. |
## PostgreSQL oltp.lesson_completions

| Cột | Kiểu | Nullable | Ý nghĩa |
|---|---|---|---|
| completion_id | bigint | NO | Khóa sự kiện hoàn thành bài; unique enrollment/lesson. |
| enrollment_id | bigint | NO | Khóa ghi danh; unique user/course; degenerate reference trên facts. |
| user_id | bigint | NO | Khóa nghiệp vụ học viên, dùng distinct learner qua nhiều phiên bản. |
| course_id | bigint | NO | Khóa nghiệp vụ khóa học. |
| lesson_id | bigint | NO | Khóa nghiệp vụ bài học, mỗi khóa có 10 bài. |
| completed_at | timestamp without time zone | NO | Thời điểm hoàn thành UTC; nullable cho enrollment chưa hoàn thành, không null cho lesson completion. |
| time_spent_seconds | integer | NO | Thời gian học/làm quiz, giây dương; additive trên events. |
## PostgreSQL oltp.lessons

| Cột | Kiểu | Nullable | Ý nghĩa |
|---|---|---|---|
| lesson_id | bigint | NO | Khóa nghiệp vụ bài học, mỗi khóa có 10 bài. |
| course_id | bigint | NO | Khóa nghiệp vụ khóa học. |
| title | text | NO | Tiêu đề khóa/bài/quiz theo bảng. |
| position | smallint | NO | Thứ tự bài trong khóa, 1–10. |
## PostgreSQL oltp.payment_methods

| Cột | Kiểu | Nullable | Ý nghĩa |
|---|---|---|---|
| method_id | bigint | NO | Khóa nghiệp vụ phương thức thanh toán. |
| method_name | text | NO | bank_transfer, card, wallet. |
## PostgreSQL oltp.payments

| Cột | Kiểu | Nullable | Ý nghĩa |
|---|---|---|---|
| payment_id | bigint | NO | Khóa nghiệp vụ thanh toán, 1 payment/enrollment. |
| enrollment_id | bigint | NO | Khóa ghi danh; unique user/course; degenerate reference trên facts. |
| user_id | bigint | NO | Khóa nghiệp vụ học viên, dùng distinct learner qua nhiều phiên bản. |
| course_id | bigint | NO | Khóa nghiệp vụ khóa học. |
| method_id | bigint | NO | Khóa nghiệp vụ phương thức thanh toán. |
| transaction_id | text | NO | Mã giao dịch unique TXN-…; degenerate dimension. |
| paid_at | timestamp without time zone | NO | Thời điểm thanh toán UTC = enrolled_at + 60 giây trong generator. |
| original_vnd | bigint | NO | Giá gốc tại giao dịch, VND integer. |
| discount_vnd | bigint | NO | Số tiền giảm, VND integer trong [0,original_vnd]. |
| charged_vnd | bigint | NO | Số tiền thu trước hoàn tiền = original_vnd - discount_vnd. |
| refunded | smallint | NO | Cờ 0/1 hoàn tiền toàn phần; không có thời điểm refund riêng. |
## PostgreSQL oltp.quiz_attempts

| Cột | Kiểu | Nullable | Ý nghĩa |
|---|---|---|---|
| attempt_id | bigint | NO | Khóa lần làm quiz. |
| enrollment_id | bigint | NO | Khóa ghi danh; unique user/course; degenerate reference trên facts. |
| user_id | bigint | NO | Khóa nghiệp vụ học viên, dùng distinct learner qua nhiều phiên bản. |
| course_id | bigint | NO | Khóa nghiệp vụ khóa học. |
| quiz_id | bigint | NO | Khóa nghiệp vụ quiz, một quiz/khóa. |
| attempt_number | smallint | NO | Lần 1 hoặc 2 trong mỗi enrollment/quiz. |
| attempted_at | timestamp without time zone | NO | Thời điểm làm quiz UTC. |
| correct_count | smallint | NO | Số câu đúng từ 0 đến total_questions. |
| total_questions | smallint | NO | Số câu hỏi, hiện tại 20 mỗi quiz/attempt. |
| time_spent_seconds | integer | NO | Thời gian học/làm quiz, giây dương; additive trên events. |
## PostgreSQL oltp.quizzes

| Cột | Kiểu | Nullable | Ý nghĩa |
|---|---|---|---|
| quiz_id | bigint | NO | Khóa nghiệp vụ quiz, một quiz/khóa. |
| course_id | bigint | NO | Khóa nghiệp vụ khóa học. |
| title | text | NO | Tiêu đề khóa/bài/quiz theo bảng. |
| total_questions | smallint | NO | Số câu hỏi, hiện tại 20 mỗi quiz/attempt. |
## PostgreSQL oltp.user_history

| Cột | Kiểu | Nullable | Ý nghĩa |
|---|---|---|---|
| history_id | bigint | NO | Khóa phiên bản lịch sử nguồn; một user có thể nhiều dòng. |
| user_id | bigint | NO | Khóa nghiệp vụ học viên, dùng distinct learner qua nhiều phiên bản. |
| full_name | text | NO | Tên giả lập Faker; Silver trim khoảng trắng. |
| email | text | NO | Email giả example.invalid; Bronze giữ raw, Silver trim và lowercase. |
| city | text | NO | Thành phố; lịch sử lưu tại user_history / dim_user. |
| country | character | NO | ISO alpha-2; dữ liệu hiện tại VN, Silver uppercase. |
| valid_from | timestamp without time zone | NO | Bắt đầu hiệu lực SCD2, inclusive (UTC). |
| valid_to | timestamp without time zone | NO | Kết thúc hiệu lực SCD2, exclusive; sentinel 2100-01-01. |
## PostgreSQL oltp.users

| Cột | Kiểu | Nullable | Ý nghĩa |
|---|---|---|---|
| user_id | bigint | NO | Khóa nghiệp vụ học viên, dùng distinct learner qua nhiều phiên bản. |
| full_name | text | NO | Tên giả lập Faker; Silver trim khoảng trắng. |
| email | text | NO | Email giả example.invalid; Bronze giữ raw, Silver trim và lowercase. |
| city | text | NO | Thành phố; lịch sử lưu tại user_history / dim_user. |
| country | character | NO | ISO alpha-2; dữ liệu hiện tại VN, Silver uppercase. |
| created_at | timestamp without time zone | NO | Thời điểm tạo UTC, đầu kỳ 2022 trong bộ dữ liệu này. |

## ClickHouse bronze.courses

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| course_id | Int64 | Khóa nghiệp vụ khóa học. |
| instructor_id | Int64 | Khóa nghiệp vụ giảng viên. |
| title | String | Tiêu đề khóa/bài/quiz theo bảng. |
| category | String | Nhóm khóa: Data, Programming, Business, Design, Language. |
| difficulty | String | beginner, intermediate, advanced. |
| price_vnd | Int64 | Giá hiện tại khóa, VND integer ≥0. |
| _run_id | String | UUID hex nhận diện snapshot ETL. |
| _loaded_at | DateTime('UTC') | Thời điểm ingest UTC. |
| _source | String | Tên nguồn postgres.oltp.<table>. |

## ClickHouse bronze.enrollments

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| enrollment_id | Int64 | Khóa ghi danh; unique user/course; degenerate reference trên facts. |
| user_id | Int64 | Khóa nghiệp vụ học viên, dùng distinct learner qua nhiều phiên bản. |
| course_id | Int64 | Khóa nghiệp vụ khóa học. |
| enrolled_at | DateTime('UTC') | Thời điểm ghi danh UTC; Gold user version được tra tại thời điểm này. |
| completed_at | Nullable(DateTime('UTC')) | Thời điểm hoàn thành UTC; nullable cho enrollment chưa hoàn thành, không null cho lesson completion. |
| lessons_completed | Int64 | Số bài đã hoàn thành cuối kỳ; 10 nếu complete, 6 nếu chưa complete trong generator. |
| _run_id | String | UUID hex nhận diện snapshot ETL. |
| _loaded_at | DateTime('UTC') | Thời điểm ingest UTC. |
| _source | String | Tên nguồn postgres.oltp.<table>. |

## ClickHouse bronze.instructors

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| instructor_id | Int64 | Khóa nghiệp vụ giảng viên. |
| full_name | String | Tên giả lập Faker; Silver trim khoảng trắng. |
| expertise | String | Lĩnh vực chuyên môn giảng viên giả lập. |
| _run_id | String | UUID hex nhận diện snapshot ETL. |
| _loaded_at | DateTime('UTC') | Thời điểm ingest UTC. |
| _source | String | Tên nguồn postgres.oltp.<table>. |

## ClickHouse bronze.lesson_completions

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| completion_id | Int64 | Khóa sự kiện hoàn thành bài; unique enrollment/lesson. |
| enrollment_id | Int64 | Khóa ghi danh; unique user/course; degenerate reference trên facts. |
| user_id | Int64 | Khóa nghiệp vụ học viên, dùng distinct learner qua nhiều phiên bản. |
| course_id | Int64 | Khóa nghiệp vụ khóa học. |
| lesson_id | Int64 | Khóa nghiệp vụ bài học, mỗi khóa có 10 bài. |
| completed_at | DateTime('UTC') | Thời điểm hoàn thành UTC; nullable cho enrollment chưa hoàn thành, không null cho lesson completion. |
| time_spent_seconds | Int64 | Thời gian học/làm quiz, giây dương; additive trên events. |
| _run_id | String | UUID hex nhận diện snapshot ETL. |
| _loaded_at | DateTime('UTC') | Thời điểm ingest UTC. |
| _source | String | Tên nguồn postgres.oltp.<table>. |

## ClickHouse bronze.lessons

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| lesson_id | Int64 | Khóa nghiệp vụ bài học, mỗi khóa có 10 bài. |
| course_id | Int64 | Khóa nghiệp vụ khóa học. |
| title | String | Tiêu đề khóa/bài/quiz theo bảng. |
| position | Int64 | Thứ tự bài trong khóa, 1–10. |
| _run_id | String | UUID hex nhận diện snapshot ETL. |
| _loaded_at | DateTime('UTC') | Thời điểm ingest UTC. |
| _source | String | Tên nguồn postgres.oltp.<table>. |

## ClickHouse bronze.payment_methods

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| method_id | Int64 | Khóa nghiệp vụ phương thức thanh toán. |
| method_name | String | bank_transfer, card, wallet. |
| _run_id | String | UUID hex nhận diện snapshot ETL. |
| _loaded_at | DateTime('UTC') | Thời điểm ingest UTC. |
| _source | String | Tên nguồn postgres.oltp.<table>. |

## ClickHouse bronze.payments

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| payment_id | Int64 | Khóa nghiệp vụ thanh toán, 1 payment/enrollment. |
| enrollment_id | Int64 | Khóa ghi danh; unique user/course; degenerate reference trên facts. |
| user_id | Int64 | Khóa nghiệp vụ học viên, dùng distinct learner qua nhiều phiên bản. |
| course_id | Int64 | Khóa nghiệp vụ khóa học. |
| method_id | Int64 | Khóa nghiệp vụ phương thức thanh toán. |
| transaction_id | String | Mã giao dịch unique TXN-…; degenerate dimension. |
| paid_at | DateTime('UTC') | Thời điểm thanh toán UTC = enrolled_at + 60 giây trong generator. |
| original_vnd | Int64 | Giá gốc tại giao dịch, VND integer. |
| discount_vnd | Int64 | Số tiền giảm, VND integer trong [0,original_vnd]. |
| charged_vnd | Int64 | Số tiền thu trước hoàn tiền = original_vnd - discount_vnd. |
| refunded | Int64 | Cờ 0/1 hoàn tiền toàn phần; không có thời điểm refund riêng. |
| _run_id | String | UUID hex nhận diện snapshot ETL. |
| _loaded_at | DateTime('UTC') | Thời điểm ingest UTC. |
| _source | String | Tên nguồn postgres.oltp.<table>. |

## ClickHouse bronze.quiz_attempts

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| attempt_id | Int64 | Khóa lần làm quiz. |
| enrollment_id | Int64 | Khóa ghi danh; unique user/course; degenerate reference trên facts. |
| user_id | Int64 | Khóa nghiệp vụ học viên, dùng distinct learner qua nhiều phiên bản. |
| course_id | Int64 | Khóa nghiệp vụ khóa học. |
| quiz_id | Int64 | Khóa nghiệp vụ quiz, một quiz/khóa. |
| attempt_number | Int64 | Lần 1 hoặc 2 trong mỗi enrollment/quiz. |
| attempted_at | DateTime('UTC') | Thời điểm làm quiz UTC. |
| correct_count | Int64 | Số câu đúng từ 0 đến total_questions. |
| total_questions | Int64 | Số câu hỏi, hiện tại 20 mỗi quiz/attempt. |
| time_spent_seconds | Int64 | Thời gian học/làm quiz, giây dương; additive trên events. |
| _run_id | String | UUID hex nhận diện snapshot ETL. |
| _loaded_at | DateTime('UTC') | Thời điểm ingest UTC. |
| _source | String | Tên nguồn postgres.oltp.<table>. |

## ClickHouse bronze.quizzes

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| quiz_id | Int64 | Khóa nghiệp vụ quiz, một quiz/khóa. |
| course_id | Int64 | Khóa nghiệp vụ khóa học. |
| title | String | Tiêu đề khóa/bài/quiz theo bảng. |
| total_questions | Int64 | Số câu hỏi, hiện tại 20 mỗi quiz/attempt. |
| _run_id | String | UUID hex nhận diện snapshot ETL. |
| _loaded_at | DateTime('UTC') | Thời điểm ingest UTC. |
| _source | String | Tên nguồn postgres.oltp.<table>. |

## ClickHouse bronze.user_history

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| history_id | Int64 | Khóa phiên bản lịch sử nguồn; một user có thể nhiều dòng. |
| user_id | Int64 | Khóa nghiệp vụ học viên, dùng distinct learner qua nhiều phiên bản. |
| full_name | String | Tên giả lập Faker; Silver trim khoảng trắng. |
| email | String | Email giả example.invalid; Bronze giữ raw, Silver trim và lowercase. |
| city | String | Thành phố; lịch sử lưu tại user_history / dim_user. |
| country | String | ISO alpha-2; dữ liệu hiện tại VN, Silver uppercase. |
| valid_from | DateTime('UTC') | Bắt đầu hiệu lực SCD2, inclusive (UTC). |
| valid_to | DateTime('UTC') | Kết thúc hiệu lực SCD2, exclusive; sentinel 2100-01-01. |
| _run_id | String | UUID hex nhận diện snapshot ETL. |
| _loaded_at | DateTime('UTC') | Thời điểm ingest UTC. |
| _source | String | Tên nguồn postgres.oltp.<table>. |

## ClickHouse bronze.users

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| user_id | Int64 | Khóa nghiệp vụ học viên, dùng distinct learner qua nhiều phiên bản. |
| full_name | String | Tên giả lập Faker; Silver trim khoảng trắng. |
| email | String | Email giả example.invalid; Bronze giữ raw, Silver trim và lowercase. |
| city | String | Thành phố; lịch sử lưu tại user_history / dim_user. |
| country | String | ISO alpha-2; dữ liệu hiện tại VN, Silver uppercase. |
| created_at | DateTime('UTC') | Thời điểm tạo UTC, đầu kỳ 2022 trong bộ dữ liệu này. |
| _run_id | String | UUID hex nhận diện snapshot ETL. |
| _loaded_at | DateTime('UTC') | Thời điểm ingest UTC. |
| _source | String | Tên nguồn postgres.oltp.<table>. |

## ClickHouse silver.courses

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| course_id | Int64 | Khóa nghiệp vụ khóa học. |
| instructor_id | Int64 | Khóa nghiệp vụ giảng viên. |
| title | String | Tiêu đề khóa/bài/quiz theo bảng. |
| category | String | Nhóm khóa: Data, Programming, Business, Design, Language. |
| difficulty | String | beginner, intermediate, advanced. |
| price_vnd | Int64 | Giá hiện tại khóa, VND integer ≥0. |

## ClickHouse silver.enrollments

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| enrollment_id | Int64 | Khóa ghi danh; unique user/course; degenerate reference trên facts. |
| user_id | Int64 | Khóa nghiệp vụ học viên, dùng distinct learner qua nhiều phiên bản. |
| course_id | Int64 | Khóa nghiệp vụ khóa học. |
| enrolled_at | DateTime('UTC') | Thời điểm ghi danh UTC; Gold user version được tra tại thời điểm này. |
| completed_at | Nullable(DateTime('UTC')) | Thời điểm hoàn thành UTC; nullable cho enrollment chưa hoàn thành, không null cho lesson completion. |
| lessons_completed | Int64 | Số bài đã hoàn thành cuối kỳ; 10 nếu complete, 6 nếu chưa complete trong generator. |

## ClickHouse silver.instructors

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| instructor_id | Int64 | Khóa nghiệp vụ giảng viên. |
| full_name | String | Tên giả lập Faker; Silver trim khoảng trắng. |
| expertise | String | Lĩnh vực chuyên môn giảng viên giả lập. |

## ClickHouse silver.lesson_completions

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| completion_id | Int64 | Khóa sự kiện hoàn thành bài; unique enrollment/lesson. |
| enrollment_id | Int64 | Khóa ghi danh; unique user/course; degenerate reference trên facts. |
| user_id | Int64 | Khóa nghiệp vụ học viên, dùng distinct learner qua nhiều phiên bản. |
| course_id | Int64 | Khóa nghiệp vụ khóa học. |
| lesson_id | Int64 | Khóa nghiệp vụ bài học, mỗi khóa có 10 bài. |
| completed_at | DateTime('UTC') | Thời điểm hoàn thành UTC; nullable cho enrollment chưa hoàn thành, không null cho lesson completion. |
| time_spent_seconds | Int64 | Thời gian học/làm quiz, giây dương; additive trên events. |

## ClickHouse silver.lessons

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| lesson_id | Int64 | Khóa nghiệp vụ bài học, mỗi khóa có 10 bài. |
| course_id | Int64 | Khóa nghiệp vụ khóa học. |
| title | String | Tiêu đề khóa/bài/quiz theo bảng. |
| position | Int64 | Thứ tự bài trong khóa, 1–10. |

## ClickHouse silver.payment_methods

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| method_id | Int64 | Khóa nghiệp vụ phương thức thanh toán. |
| method_name | String | bank_transfer, card, wallet. |

## ClickHouse silver.payments

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| payment_id | Int64 | Khóa nghiệp vụ thanh toán, 1 payment/enrollment. |
| enrollment_id | Int64 | Khóa ghi danh; unique user/course; degenerate reference trên facts. |
| user_id | Int64 | Khóa nghiệp vụ học viên, dùng distinct learner qua nhiều phiên bản. |
| course_id | Int64 | Khóa nghiệp vụ khóa học. |
| method_id | Int64 | Khóa nghiệp vụ phương thức thanh toán. |
| transaction_id | String | Mã giao dịch unique TXN-…; degenerate dimension. |
| paid_at | DateTime('UTC') | Thời điểm thanh toán UTC = enrolled_at + 60 giây trong generator. |
| original_vnd | Int64 | Giá gốc tại giao dịch, VND integer. |
| discount_vnd | Int64 | Số tiền giảm, VND integer trong [0,original_vnd]. |
| charged_vnd | Int64 | Số tiền thu trước hoàn tiền = original_vnd - discount_vnd. |
| refunded | Int64 | Cờ 0/1 hoàn tiền toàn phần; không có thời điểm refund riêng. |

## ClickHouse silver.quiz_attempts

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| attempt_id | Int64 | Khóa lần làm quiz. |
| enrollment_id | Int64 | Khóa ghi danh; unique user/course; degenerate reference trên facts. |
| user_id | Int64 | Khóa nghiệp vụ học viên, dùng distinct learner qua nhiều phiên bản. |
| course_id | Int64 | Khóa nghiệp vụ khóa học. |
| quiz_id | Int64 | Khóa nghiệp vụ quiz, một quiz/khóa. |
| attempt_number | Int64 | Lần 1 hoặc 2 trong mỗi enrollment/quiz. |
| attempted_at | DateTime('UTC') | Thời điểm làm quiz UTC. |
| correct_count | Int64 | Số câu đúng từ 0 đến total_questions. |
| total_questions | Int64 | Số câu hỏi, hiện tại 20 mỗi quiz/attempt. |
| time_spent_seconds | Int64 | Thời gian học/làm quiz, giây dương; additive trên events. |

## ClickHouse silver.quizzes

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| quiz_id | Int64 | Khóa nghiệp vụ quiz, một quiz/khóa. |
| course_id | Int64 | Khóa nghiệp vụ khóa học. |
| title | String | Tiêu đề khóa/bài/quiz theo bảng. |
| total_questions | Int64 | Số câu hỏi, hiện tại 20 mỗi quiz/attempt. |

## ClickHouse silver.user_history

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| history_id | Int64 | Khóa phiên bản lịch sử nguồn; một user có thể nhiều dòng. |
| user_id | Int64 | Khóa nghiệp vụ học viên, dùng distinct learner qua nhiều phiên bản. |
| full_name | String | Tên giả lập Faker; Silver trim khoảng trắng. |
| email | String | Email giả example.invalid; Bronze giữ raw, Silver trim và lowercase. |
| city | String | Thành phố; lịch sử lưu tại user_history / dim_user. |
| country | String | ISO alpha-2; dữ liệu hiện tại VN, Silver uppercase. |
| valid_from | DateTime('UTC') | Bắt đầu hiệu lực SCD2, inclusive (UTC). |
| valid_to | DateTime('UTC') | Kết thúc hiệu lực SCD2, exclusive; sentinel 2100-01-01. |

## ClickHouse silver.users

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| user_id | Int64 | Khóa nghiệp vụ học viên, dùng distinct learner qua nhiều phiên bản. |
| full_name | String | Tên giả lập Faker; Silver trim khoảng trắng. |
| email | String | Email giả example.invalid; Bronze giữ raw, Silver trim và lowercase. |
| city | String | Thành phố; lịch sử lưu tại user_history / dim_user. |
| country | String | ISO alpha-2; dữ liệu hiện tại VN, Silver uppercase. |
| created_at | DateTime('UTC') | Thời điểm tạo UTC, đầu kỳ 2022 trong bộ dữ liệu này. |

## ClickHouse gold.dim_course

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| course_sk | Int64 | Khóa dimension course = course_id+1000000. |
| course_id | Int64 | Khóa nghiệp vụ khóa học. |
| title | String | Tiêu đề khóa/bài/quiz theo bảng. |
| category | LowCardinality(String) | Nhóm khóa: Data, Programming, Business, Design, Language. |
| difficulty | LowCardinality(String) | beginner, intermediate, advanced. |
| instructor_id | Int64 | Khóa nghiệp vụ giảng viên. |
| price_vnd | Int64 | Giá hiện tại khóa, VND integer ≥0. |

## ClickHouse gold.dim_date

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| date_sk | Int64 | Khóa ngày YYYYMMDD, khóa 0 dành cho unknown. |
| full_date | Date | Ngày lịch; 1970-01-01 là placeholder riêng dòng unknown. |
| year | Int64 | Năm lịch (0 cho unknown). |
| quarter | Int64 | Quý 1–4 (0 cho unknown). |
| month | Int64 | Tháng 1–12 (0 cho unknown). |
| day | Int64 | Ngày trong tháng (0 cho unknown). |

## ClickHouse gold.dim_instructor

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| instructor_sk | Int64 | Khóa dimension instructor = instructor_id+2000000. |
| instructor_id | Int64 | Khóa nghiệp vụ giảng viên. |
| full_name | String | Tên giả lập Faker; Silver trim khoảng trắng. |
| expertise | LowCardinality(String) | Lĩnh vực chuyên môn giảng viên giả lập. |

## ClickHouse gold.dim_lesson

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| lesson_sk | Int64 | Khóa dimension lesson = lesson_id+3000000. |
| lesson_id | Int64 | Khóa nghiệp vụ bài học, mỗi khóa có 10 bài. |
| course_id | Int64 | Khóa nghiệp vụ khóa học. |
| title | String | Tiêu đề khóa/bài/quiz theo bảng. |
| position | Int64 | Thứ tự bài trong khóa, 1–10. |

## ClickHouse gold.dim_payment_method

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| method_sk | Int64 | Khóa dimension method = method_id+5000000. |
| method_id | Int64 | Khóa nghiệp vụ phương thức thanh toán. |
| method_name | LowCardinality(String) | bank_transfer, card, wallet. |

## ClickHouse gold.dim_quiz

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| quiz_sk | Int64 | Khóa dimension quiz = quiz_id+4000000. |
| quiz_id | Int64 | Khóa nghiệp vụ quiz, một quiz/khóa. |
| course_id | Int64 | Khóa nghiệp vụ khóa học. |
| title | String | Tiêu đề khóa/bài/quiz theo bảng. |
| total_questions | Int64 | Số câu hỏi, hiện tại 20 mỗi quiz/attempt. |

## ClickHouse gold.dim_user

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| user_sk | Int64 | Khóa thay thế theo phiên bản SCD2 = history_id+10000000. |
| user_id | Int64 | Khóa nghiệp vụ học viên, dùng distinct learner qua nhiều phiên bản. |
| full_name | String | Tên giả lập Faker; Silver trim khoảng trắng. |
| email | String | Email giả example.invalid; Bronze giữ raw, Silver trim và lowercase. |
| city | LowCardinality(String) | Thành phố; lịch sử lưu tại user_history / dim_user. |
| country | LowCardinality(String) | ISO alpha-2; dữ liệu hiện tại VN, Silver uppercase. |
| valid_from | DateTime('UTC') | Bắt đầu hiệu lực SCD2, inclusive (UTC). |
| valid_to | DateTime('UTC') | Kết thúc hiệu lực SCD2, exclusive; sentinel 2100-01-01. |
| is_current | Int64 | 1 nếu phiên bản hiện hành (valid_to=2100-01-01), ngược lại 0. |

## ClickHouse gold.fact_enrollments

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| enrollment_id | Int64 | Khóa ghi danh; unique user/course; degenerate reference trên facts. |
| user_sk | Int64 | Khóa thay thế theo phiên bản SCD2 = history_id+10000000. |
| course_sk | Int64 | Khóa dimension course = course_id+1000000. |
| instructor_sk | Int64 | Khóa dimension instructor = instructor_id+2000000. |
| enrolled_date_sk | Int64 | Role enrolled của dim_date, suy từ enrolled_at. |
| completed_date_sk | Int64 | Role completed của dim_date; 0 nếu chưa complete. |
| enrolled_at | DateTime('UTC') | Thời điểm ghi danh UTC; Gold user version được tra tại thời điểm này. |
| completed_at | Nullable(DateTime('UTC')) | Thời điểm hoàn thành UTC; nullable cho enrollment chưa hoàn thành, không null cho lesson completion. |
| lessons_completed | Int64 | Số bài đã hoàn thành cuối kỳ; 10 nếu complete, 6 nếu chưa complete trong generator. |
| is_completed | Int64 | 1 khi enrollment có completed_at; metric numerator completion rate. |

## ClickHouse gold.fact_lesson_completions

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| completion_id | Int64 | Khóa sự kiện hoàn thành bài; unique enrollment/lesson. |
| enrollment_id | Int64 | Khóa ghi danh; unique user/course; degenerate reference trên facts. |
| user_sk | Int64 | Khóa thay thế theo phiên bản SCD2 = history_id+10000000. |
| course_sk | Int64 | Khóa dimension course = course_id+1000000. |
| lesson_sk | Int64 | Khóa dimension lesson = lesson_id+3000000. |
| date_sk | Int64 | Khóa ngày YYYYMMDD, khóa 0 dành cho unknown. |
| completed_at | DateTime('UTC') | Thời điểm hoàn thành UTC; nullable cho enrollment chưa hoàn thành, không null cho lesson completion. |
| time_spent_seconds | Int64 | Thời gian học/làm quiz, giây dương; additive trên events. |

## ClickHouse gold.fact_payments

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| payment_id | Int64 | Khóa nghiệp vụ thanh toán, 1 payment/enrollment. |
| enrollment_id | Int64 | Khóa ghi danh; unique user/course; degenerate reference trên facts. |
| transaction_id | String | Mã giao dịch unique TXN-…; degenerate dimension. |
| user_sk | Int64 | Khóa thay thế theo phiên bản SCD2 = history_id+10000000. |
| course_sk | Int64 | Khóa dimension course = course_id+1000000. |
| instructor_sk | Int64 | Khóa dimension instructor = instructor_id+2000000. |
| method_sk | Int64 | Khóa dimension method = method_id+5000000. |
| date_sk | Int64 | Khóa ngày YYYYMMDD, khóa 0 dành cho unknown. |
| paid_at | DateTime('UTC') | Thời điểm thanh toán UTC = enrolled_at + 60 giây trong generator. |
| original_vnd | Int64 | Giá gốc tại giao dịch, VND integer. |
| discount_vnd | Int64 | Số tiền giảm, VND integer trong [0,original_vnd]. |
| charged_vnd | Int64 | Số tiền thu trước hoàn tiền = original_vnd - discount_vnd. |
| refunded | Int64 | Cờ 0/1 hoàn tiền toàn phần; không có thời điểm refund riêng. |
| net_vnd | Int64 | charged_vnd × (1-refunded), giữ lại cuối kỳ quy về ngày giao dịch gốc. |

## ClickHouse gold.fact_quiz_attempts

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| attempt_id | Int64 | Khóa lần làm quiz. |
| enrollment_id | Int64 | Khóa ghi danh; unique user/course; degenerate reference trên facts. |
| user_sk | Int64 | Khóa thay thế theo phiên bản SCD2 = history_id+10000000. |
| course_sk | Int64 | Khóa dimension course = course_id+1000000. |
| quiz_sk | Int64 | Khóa dimension quiz = quiz_id+4000000. |
| date_sk | Int64 | Khóa ngày YYYYMMDD, khóa 0 dành cho unknown. |
| attempted_at | DateTime('UTC') | Thời điểm làm quiz UTC. |
| attempt_number | Int64 | Lần 1 hoặc 2 trong mỗi enrollment/quiz. |
| correct_count | Int64 | Số câu đúng từ 0 đến total_questions. |
| total_questions | Int64 | Số câu hỏi, hiện tại 20 mỗi quiz/attempt. |
| time_spent_seconds | Int64 | Thời gian học/làm quiz, giây dương; additive trên events. |
| is_passed | Int64 | 1 khi correct_count/total_questions ≥70%, ngược lại 0. |
