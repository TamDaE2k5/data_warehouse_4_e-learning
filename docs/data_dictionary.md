# Data dictionary

Physical types are read from running schemas. Timestamps use UTC and money uses integer VND.
Gold event timestamps have second precision. The quality gate verifies Gold foreign keys.
See [architecture](architecture.md) for grain and history, and [mapping](mapping.md) for formulas.
Regenerate with `docker compose run --rm runner python -m docs.generate_dictionary`.

## PostgreSQL learning_oltp.oltp.change_journal

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| revision | bigint | NO | Per-change revision used to reject stale replay. |
| source_xid | bigint | NO | Full transaction ID of the source transaction recorded in the journal. |
| table_name | text | NO | Source table name from the warehouse contract. |
| source_id | bigint | NO | Business key of the source row. |
| operation | text | NO | INSERT, UPDATE, DELETE or a durable staged-delta operation. |
| raw_payload | jsonb | NO | Original JSON payload retained for replay or investigation. |
| changed_at | timestamp with time zone | NO | UTC time at which the source trigger recorded the change. |
## PostgreSQL learning_oltp.oltp.courses

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| course_id | bigint | NO | Course business key. |
| instructor_id | bigint | NO | Instructor business key. |
| title | text | NO | Course, lesson or quiz title, depending on the table. |
| category | text | NO | Course category: Data, Programming, Business, Design or Language. |
| difficulty | text | NO | beginner, intermediate or advanced. |
| price_vnd | bigint | NO | Current course list price, nonnegative integer VND; not historical payment revenue. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
| dw_revision | bigint | NO | Monotonic source revision; zero identifies the baseline seed or migrated data. |
## PostgreSQL learning_oltp.oltp.enrollments

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| enrollment_id | bigint | NO | Enrollment business key; retained as a reference on activity facts. |
| user_id | bigint | NO | Learner business key. Use it to count distinct people across SCD versions. |
| course_id | bigint | NO | Course business key. |
| enrolled_at | timestamp without time zone | NO | UTC enrollment time; learner history is selected at this instant. |
| completed_at | timestamp without time zone | YES | UTC completion; nullable for incomplete enrollments, required for lesson completions. |
| lessons_completed | smallint | NO | Current enrollment progress; not a daily historical progress series. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
| dw_revision | bigint | NO | Monotonic source revision; zero identifies the baseline seed or migrated data. |
## PostgreSQL learning_oltp.oltp.instructors

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| instructor_id | bigint | NO | Instructor business key. |
| full_name | text | NO | Synthetic Faker name; surrounding whitespace is trimmed in Silver. |
| expertise | text | NO | Synthetic instructor specialization. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
| dw_revision | bigint | NO | Monotonic source revision; zero identifies the baseline seed or migrated data. |
## PostgreSQL learning_oltp.oltp.lesson_completions

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| completion_id | bigint | NO | Lesson completion event key; enrollment and lesson identify one completion. |
| enrollment_id | bigint | NO | Enrollment business key; retained as a reference on activity facts. |
| user_id | bigint | NO | Learner business key. Use it to count distinct people across SCD versions. |
| course_id | bigint | NO | Course business key. |
| lesson_id | bigint | NO | Lesson business key; the generator creates ten lessons per course. |
| completed_at | timestamp without time zone | NO | UTC completion; nullable for incomplete enrollments, required for lesson completions. |
| time_spent_seconds | integer | NO | Positive time spent on a lesson completion or quiz attempt, in seconds. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
| dw_revision | bigint | NO | Monotonic source revision; zero identifies the baseline seed or migrated data. |
## PostgreSQL learning_oltp.oltp.lessons

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| lesson_id | bigint | NO | Lesson business key; the generator creates ten lessons per course. |
| course_id | bigint | NO | Course business key. |
| title | text | NO | Course, lesson or quiz title, depending on the table. |
| position | smallint | NO | Lesson order inside its course, 1 through 10 in the generator. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
| dw_revision | bigint | NO | Monotonic source revision; zero identifies the baseline seed or migrated data. |
## PostgreSQL learning_oltp.oltp.payment_methods

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| method_id | bigint | NO | Payment method business key. |
| method_name | text | NO | bank_transfer, card or wallet. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
| dw_revision | bigint | NO | Monotonic source revision; zero identifies the baseline seed or migrated data. |
## PostgreSQL learning_oltp.oltp.payments

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| payment_id | bigint | NO | Payment business key; the generator creates one payment per enrollment. |
| enrollment_id | bigint | NO | Enrollment business key; retained as a reference on activity facts. |
| user_id | bigint | NO | Learner business key. Use it to count distinct people across SCD versions. |
| course_id | bigint | NO | Course business key. |
| method_id | bigint | NO | Payment method business key. |
| transaction_id | text | NO | Unique transaction reference retained on the payment fact. |
| paid_at | timestamp without time zone | NO | UTC payment time; generated as enrollment time plus 60 seconds. |
| original_vnd | bigint | NO | Original amount recorded on the transaction, integer VND. |
| discount_vnd | bigint | NO | Discount in integer VND, between zero and the original amount. |
| charged_vnd | bigint | NO | Charged amount before refunds: original_vnd minus discount_vnd. |
| refunded | smallint | NO | Full-refund flag, 0 or 1. No separate refund event timestamp exists. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
| dw_revision | bigint | NO | Monotonic source revision; zero identifies the baseline seed or migrated data. |
## PostgreSQL learning_oltp.oltp.quiz_attempts

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| attempt_id | bigint | NO | Quiz attempt event key. |
| enrollment_id | bigint | NO | Enrollment business key; retained as a reference on activity facts. |
| user_id | bigint | NO | Learner business key. Use it to count distinct people across SCD versions. |
| course_id | bigint | NO | Course business key. |
| quiz_id | bigint | NO | Quiz business key; the generator creates one quiz per course. |
| attempt_number | smallint | NO | Attempt sequence within an enrollment and quiz. |
| attempted_at | timestamp without time zone | NO | UTC quiz attempt time. |
| correct_count | smallint | NO | Correct answers, from zero through total_questions. |
| total_questions | smallint | NO | Number of questions; generated quizzes and attempts contain 20. |
| time_spent_seconds | integer | NO | Positive time spent on a lesson completion or quiz attempt, in seconds. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
| dw_revision | bigint | NO | Monotonic source revision; zero identifies the baseline seed or migrated data. |
## PostgreSQL learning_oltp.oltp.quizzes

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| quiz_id | bigint | NO | Quiz business key; the generator creates one quiz per course. |
| course_id | bigint | NO | Course business key. |
| title | text | NO | Course, lesson or quiz title, depending on the table. |
| total_questions | smallint | NO | Number of questions; generated quizzes and attempts contain 20. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
| dw_revision | bigint | NO | Monotonic source revision; zero identifies the baseline seed or migrated data. |
## PostgreSQL learning_oltp.oltp.user_history

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| history_id | bigint | NO | Source history version key; one learner can have several versions. |
| user_id | bigint | NO | Learner business key. Use it to count distinct people across SCD versions. |
| full_name | text | NO | Synthetic Faker name; surrounding whitespace is trimmed in Silver. |
| email | text | NO | Synthetic example.invalid address; Silver trims and lowercases it. |
| city | text | NO | City at the applicable history version; see user_history and dim_user. |
| country | character | NO | Country code; the generator uses VN. Silver uppercases the value. |
| valid_from | timestamp without time zone | NO | Inclusive start of the SCD2 effective interval, in UTC. |
| valid_to | timestamp without time zone | NO | Exclusive end of the SCD2 interval; 2100-01-01 denotes the current version. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
| dw_revision | bigint | NO | Monotonic source revision; zero identifies the baseline seed or migrated data. |
## PostgreSQL learning_oltp.oltp.users

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| user_id | bigint | NO | Learner business key. Use it to count distinct people across SCD versions. |
| full_name | text | NO | Synthetic Faker name; surrounding whitespace is trimmed in Silver. |
| email | text | NO | Synthetic example.invalid address; Silver trims and lowercases it. |
| city | text | NO | City at the applicable history version; see user_history and dim_user. |
| country | character | NO | Country code; the generator uses VN. Silver uppercases the value. |
| created_at | timestamp without time zone | NO | UTC creation time; generated learners start in 2022. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
| dw_revision | bigint | NO | Monotonic source revision; zero identifies the baseline seed or migrated data. |
## PostgreSQL dwh_staging.quarantine.quarantine_records

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| table_name | text | NO | Source table name from the warehouse contract. |
| source_id | bigint | NO | Business key of the source row. |
| source_updated_at | timestamp with time zone | NO | Source updated_at value of the rejected version. |
| error_code | text | NO | Machine-readable schema, domain or reference error code. |
| rejection_reason | text | NO | Human-readable explanation of the rejected change. |
| detected_at | timestamp with time zone | YES | UTC time at which staging detected the invalid change. |
| raw_payload | jsonb | NO | Original JSON payload retained for replay or investigation. |
| resolved_at | timestamp with time zone | YES | UTC resolution time; NULL while the rejection remains unresolved. |
## PostgreSQL dwh_staging.silver.courses

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| course_id | bigint | NO | Course business key. |
| instructor_id | bigint | NO | Instructor business key. |
| title | text | NO | Course, lesson or quiz title, depending on the table. |
| category | text | NO | Course category: Data, Programming, Business, Design or Language. |
| difficulty | text | NO | beginner, intermediate or advanced. |
| price_vnd | bigint | NO | Current course list price, nonnegative integer VND; not historical payment revenue. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
## PostgreSQL dwh_staging.silver.enrollments

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| enrollment_id | bigint | NO | Enrollment business key; retained as a reference on activity facts. |
| user_id | bigint | NO | Learner business key. Use it to count distinct people across SCD versions. |
| course_id | bigint | NO | Course business key. |
| enrolled_at | timestamp without time zone | NO | UTC enrollment time; learner history is selected at this instant. |
| completed_at | timestamp without time zone | YES | UTC completion; nullable for incomplete enrollments, required for lesson completions. |
| lessons_completed | bigint | NO | Current enrollment progress; not a daily historical progress series. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
## PostgreSQL dwh_staging.silver.instructors

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| instructor_id | bigint | NO | Instructor business key. |
| full_name | text | NO | Synthetic Faker name; surrounding whitespace is trimmed in Silver. |
| expertise | text | NO | Synthetic instructor specialization. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
## PostgreSQL dwh_staging.silver.lesson_completions

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| completion_id | bigint | NO | Lesson completion event key; enrollment and lesson identify one completion. |
| enrollment_id | bigint | NO | Enrollment business key; retained as a reference on activity facts. |
| user_id | bigint | NO | Learner business key. Use it to count distinct people across SCD versions. |
| course_id | bigint | NO | Course business key. |
| lesson_id | bigint | NO | Lesson business key; the generator creates ten lessons per course. |
| completed_at | timestamp without time zone | NO | UTC completion; nullable for incomplete enrollments, required for lesson completions. |
| time_spent_seconds | bigint | NO | Positive time spent on a lesson completion or quiz attempt, in seconds. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
## PostgreSQL dwh_staging.silver.lessons

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| lesson_id | bigint | NO | Lesson business key; the generator creates ten lessons per course. |
| course_id | bigint | NO | Course business key. |
| title | text | NO | Course, lesson or quiz title, depending on the table. |
| position | bigint | NO | Lesson order inside its course, 1 through 10 in the generator. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
## PostgreSQL dwh_staging.silver.payment_methods

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| method_id | bigint | NO | Payment method business key. |
| method_name | text | NO | bank_transfer, card or wallet. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
## PostgreSQL dwh_staging.silver.payments

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| payment_id | bigint | NO | Payment business key; the generator creates one payment per enrollment. |
| enrollment_id | bigint | NO | Enrollment business key; retained as a reference on activity facts. |
| user_id | bigint | NO | Learner business key. Use it to count distinct people across SCD versions. |
| course_id | bigint | NO | Course business key. |
| method_id | bigint | NO | Payment method business key. |
| transaction_id | text | NO | Unique transaction reference retained on the payment fact. |
| paid_at | timestamp without time zone | NO | UTC payment time; generated as enrollment time plus 60 seconds. |
| original_vnd | bigint | NO | Original amount recorded on the transaction, integer VND. |
| discount_vnd | bigint | NO | Discount in integer VND, between zero and the original amount. |
| charged_vnd | bigint | NO | Charged amount before refunds: original_vnd minus discount_vnd. |
| refunded | bigint | NO | Full-refund flag, 0 or 1. No separate refund event timestamp exists. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
## PostgreSQL dwh_staging.silver.quiz_attempts

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| attempt_id | bigint | NO | Quiz attempt event key. |
| enrollment_id | bigint | NO | Enrollment business key; retained as a reference on activity facts. |
| user_id | bigint | NO | Learner business key. Use it to count distinct people across SCD versions. |
| course_id | bigint | NO | Course business key. |
| quiz_id | bigint | NO | Quiz business key; the generator creates one quiz per course. |
| attempt_number | bigint | NO | Attempt sequence within an enrollment and quiz. |
| attempted_at | timestamp without time zone | NO | UTC quiz attempt time. |
| correct_count | bigint | NO | Correct answers, from zero through total_questions. |
| total_questions | bigint | NO | Number of questions; generated quizzes and attempts contain 20. |
| time_spent_seconds | bigint | NO | Positive time spent on a lesson completion or quiz attempt, in seconds. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
## PostgreSQL dwh_staging.silver.quizzes

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| quiz_id | bigint | NO | Quiz business key; the generator creates one quiz per course. |
| course_id | bigint | NO | Course business key. |
| title | text | NO | Course, lesson or quiz title, depending on the table. |
| total_questions | bigint | NO | Number of questions; generated quizzes and attempts contain 20. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
## PostgreSQL dwh_staging.silver.user_history

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| history_id | bigint | NO | Source history version key; one learner can have several versions. |
| user_id | bigint | NO | Learner business key. Use it to count distinct people across SCD versions. |
| full_name | text | NO | Synthetic Faker name; surrounding whitespace is trimmed in Silver. |
| email | text | NO | Synthetic example.invalid address; Silver trims and lowercases it. |
| city | text | NO | City at the applicable history version; see user_history and dim_user. |
| country | text | NO | Country code; the generator uses VN. Silver uppercases the value. |
| valid_from | timestamp without time zone | NO | Inclusive start of the SCD2 effective interval, in UTC. |
| valid_to | timestamp without time zone | NO | Exclusive end of the SCD2 interval; 2100-01-01 denotes the current version. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
## PostgreSQL dwh_staging.silver.users

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| user_id | bigint | NO | Learner business key. Use it to count distinct people across SCD versions. |
| full_name | text | NO | Synthetic Faker name; surrounding whitespace is trimmed in Silver. |
| email | text | NO | Synthetic example.invalid address; Silver trims and lowercases it. |
| city | text | NO | City at the applicable history version; see user_history and dim_user. |
| country | text | NO | Country code; the generator uses VN. Silver uppercases the value. |
| created_at | timestamp without time zone | NO | UTC creation time; generated learners start in 2022. |
| updated_at | timestamp with time zone | NO | UTC source-version timestamp, updated by the source trigger. |
## PostgreSQL dwh_staging.staging.etl_watermarks

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| table_name | text | NO | Source table name from the warehouse contract. |
| last_processed_time | timestamp with time zone | NO | Informational timestamp, not the authoritative journal checkpoint. |
| last_processed_id | bigint | NO | Business key accompanying the informational timestamp. |
| last_run_id | text | NO | Publication run that confirmed the informational watermark. |
## PostgreSQL dwh_staging.staging.pending_changes

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| table_name | text | NO | Source table name from the warehouse contract. |
| source_id | bigint | NO | Business key of the source row. |
| operation | text | NO | INSERT, UPDATE, DELETE or a durable staged-delta operation. |
| revision | bigint | NO | Per-change revision used to reject stale replay. |
## PostgreSQL dwh_staging.staging.pipeline_runs

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| run_id | text | NO | Pipeline run UUID. |
| phase | text | NO | extracting, building, publishing, completed, failed or recovered. |
| manifest | jsonb | NO | Run metadata with counts, fingerprints, checks and measurements. |
| publication | jsonb | YES | Durable per-table old/new UUID plan used for recovery. |
| started_at | timestamp with time zone | NO | UTC run start time. |
| finished_at | timestamp with time zone | YES | UTC completion or failure time. |
## PostgreSQL dwh_staging.staging.published_state

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| singleton | boolean | NO | Single-row boolean key; always true. |
| manifest | jsonb | NO | Run metadata with counts, fingerprints, checks and measurements. |
| safe_xid | bigint | YES | Source transaction checkpoint for the next journal read. |
| published_at | timestamp with time zone | NO | UTC time authoritative publication state was committed. |
## PostgreSQL dwh_staging.staging.source_versions

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| table_name | text | NO | Source table name from the warehouse contract. |
| source_id | bigint | NO | Business key of the source row. |
| revision | bigint | NO | Per-change revision used to reject stale replay. |
## PostgreSQL dwh_staging.staging.stage_state

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| singleton | boolean | NO | Single-row boolean key; always true. |
| needs_full | boolean | NO | A committed full stage still requires a complete Gold rebuild. |

## ClickHouse gold.dim_course

| Column | Type | Meaning |
|---|---|---|
| course_sk | Int64 | Course surrogate key: course_id plus 1000000. |
| course_id | Int64 | Course business key. |
| title | String | Course, lesson or quiz title, depending on the table. |
| category | LowCardinality(String) | Course category: Data, Programming, Business, Design or Language. |
| difficulty | LowCardinality(String) | beginner, intermediate or advanced. |
| instructor_id | Int64 | Instructor business key. |
| price_vnd | Int64 | Current course list price, nonnegative integer VND; not historical payment revenue. |

## ClickHouse gold.dim_date

| Column | Type | Meaning |
|---|---|---|
| date_sk | Int64 | Calendar key YYYYMMDD; zero is the unknown date row. |
| full_date | Date | Calendar day. 1970-01-01 is used only for the unknown row. |
| year | Int64 | Calendar year; zero for the unknown date. |
| quarter | Int64 | Quarter 1 through 4; zero for the unknown date. |
| month | Int64 | Calendar month in dim_date; YYYYMM in the monthly revenue aggregate. |
| day | Int64 | Day of month; zero for the unknown date. |

## ClickHouse gold.dim_instructor

| Column | Type | Meaning |
|---|---|---|
| instructor_sk | Int64 | Instructor surrogate key: instructor_id plus 2000000. |
| instructor_id | Int64 | Instructor business key. |
| full_name | String | Synthetic Faker name; surrounding whitespace is trimmed in Silver. |
| expertise | LowCardinality(String) | Synthetic instructor specialization. |

## ClickHouse gold.dim_lesson

| Column | Type | Meaning |
|---|---|---|
| lesson_sk | Int64 | Lesson surrogate key: lesson_id plus 3000000. |
| lesson_id | Int64 | Lesson business key; the generator creates ten lessons per course. |
| course_id | Int64 | Course business key. |
| title | String | Course, lesson or quiz title, depending on the table. |
| position | Int64 | Lesson order inside its course, 1 through 10 in the generator. |

## ClickHouse gold.dim_payment_method

| Column | Type | Meaning |
|---|---|---|
| method_sk | Int64 | Payment method surrogate key: method_id plus 5000000. |
| method_id | Int64 | Payment method business key. |
| method_name | LowCardinality(String) | bank_transfer, card or wallet. |

## ClickHouse gold.dim_quiz

| Column | Type | Meaning |
|---|---|---|
| quiz_sk | Int64 | Quiz surrogate key: quiz_id plus 4000000. |
| quiz_id | Int64 | Quiz business key; the generator creates one quiz per course. |
| course_id | Int64 | Course business key. |
| title | String | Course, lesson or quiz title, depending on the table. |
| total_questions | Int64 | Number of questions; generated quizzes and attempts contain 20. |

## ClickHouse gold.dim_user

| Column | Type | Meaning |
|---|---|---|
| user_sk | Int64 | SCD2 version surrogate key: history_id plus 10000000. |
| user_id | Int64 | Learner business key. Use it to count distinct people across SCD versions. |
| full_name | String | Synthetic Faker name; surrounding whitespace is trimmed in Silver. |
| email | String | Synthetic example.invalid address; Silver trims and lowercases it. |
| city | LowCardinality(String) | City at the applicable history version; see user_history and dim_user. |
| country | LowCardinality(String) | Country code; the generator uses VN. Silver uppercases the value. |
| valid_from | DateTime('UTC') | Inclusive start of the SCD2 effective interval, in UTC. |
| valid_to | DateTime('UTC') | Exclusive end of the SCD2 interval; 2100-01-01 denotes the current version. |
| is_current | Int64 | 1 for the current history version, otherwise 0. |

## ClickHouse gold.fact_enrollments

| Column | Type | Meaning |
|---|---|---|
| enrollment_id | Int64 | Enrollment business key; retained as a reference on activity facts. |
| user_sk | Int64 | SCD2 version surrogate key: history_id plus 10000000. |
| course_sk | Int64 | Course surrogate key: course_id plus 1000000. |
| instructor_sk | Int64 | Instructor surrogate key: instructor_id plus 2000000. |
| enrolled_date_sk | Int64 | Enrollment-date role of dim_date, derived from enrolled_at. |
| completed_date_sk | Int64 | Completion-date role of dim_date; zero for incomplete enrollments. |
| enrolled_at | DateTime('UTC') | UTC enrollment time; learner history is selected at this instant. |
| completed_at | Nullable(DateTime('UTC')) | UTC completion; nullable for incomplete enrollments, required for lesson completions. |
| lessons_completed | Int64 | Current enrollment progress; not a daily historical progress series. |
| is_completed | Int64 | 1 when the enrollment has completed_at; completion-rate numerator. |
| updated_at | DateTime64(6, 'UTC') | UTC source-version timestamp, updated by the source trigger. |

## ClickHouse gold.fact_lesson_completions

| Column | Type | Meaning |
|---|---|---|
| completion_id | Int64 | Lesson completion event key; enrollment and lesson identify one completion. |
| enrollment_id | Int64 | Enrollment business key; retained as a reference on activity facts. |
| user_sk | Int64 | SCD2 version surrogate key: history_id plus 10000000. |
| course_sk | Int64 | Course surrogate key: course_id plus 1000000. |
| lesson_sk | Int64 | Lesson surrogate key: lesson_id plus 3000000. |
| date_sk | Int64 | Calendar key YYYYMMDD; zero is the unknown date row. |
| completed_at | DateTime('UTC') | UTC completion; nullable for incomplete enrollments, required for lesson completions. |
| time_spent_seconds | Int64 | Positive time spent on a lesson completion or quiz attempt, in seconds. |

## ClickHouse gold.fact_payments

| Column | Type | Meaning |
|---|---|---|
| payment_id | Int64 | Payment business key; the generator creates one payment per enrollment. |
| enrollment_id | Int64 | Enrollment business key; retained as a reference on activity facts. |
| transaction_id | String | Unique transaction reference retained on the payment fact. |
| user_sk | Int64 | SCD2 version surrogate key: history_id plus 10000000. |
| course_sk | Int64 | Course surrogate key: course_id plus 1000000. |
| instructor_sk | Int64 | Instructor surrogate key: instructor_id plus 2000000. |
| method_sk | Int64 | Payment method surrogate key: method_id plus 5000000. |
| date_sk | Int64 | Calendar key YYYYMMDD; zero is the unknown date row. |
| paid_at | DateTime('UTC') | UTC payment time; generated as enrollment time plus 60 seconds. |
| original_vnd | Int64 | Original amount recorded on the transaction, integer VND. |
| discount_vnd | Int64 | Discount in integer VND, between zero and the original amount. |
| charged_vnd | Int64 | Charged amount before refunds: original_vnd minus discount_vnd. |
| refunded | Int64 | Full-refund flag, 0 or 1. No separate refund event timestamp exists. |
| net_vnd | Int64 | Retained revenue: charged_vnd times (1-refunded), on the original payment date. |

## ClickHouse gold.fact_quiz_attempts

| Column | Type | Meaning |
|---|---|---|
| attempt_id | Int64 | Quiz attempt event key. |
| enrollment_id | Int64 | Enrollment business key; retained as a reference on activity facts. |
| user_sk | Int64 | SCD2 version surrogate key: history_id plus 10000000. |
| course_sk | Int64 | Course surrogate key: course_id plus 1000000. |
| quiz_sk | Int64 | Quiz surrogate key: quiz_id plus 4000000. |
| date_sk | Int64 | Calendar key YYYYMMDD; zero is the unknown date row. |
| attempted_at | DateTime('UTC') | UTC quiz attempt time. |
| attempt_number | Int64 | Attempt sequence within an enrollment and quiz. |
| correct_count | Int64 | Correct answers, from zero through total_questions. |
| total_questions | Int64 | Number of questions; generated quizzes and attempts contain 20. |
| time_spent_seconds | Int64 | Positive time spent on a lesson completion or quiz attempt, in seconds. |
| is_passed | Int64 | 1 when correct answers divided by questions is at least 70 percent. |

## ClickHouse gold.feed_course_completion

| Column | Type | Meaning |
|---|---|---|
| course_sk | Int64 | Course surrogate key: course_id plus 1000000. |
| enrollments | UInt64 | Number of enrollments in the aggregate group. |
| completions | Int64 | Number of enrollments with completed_at in the group. |
| completion_days | Int64 | Sum of completed enrollment durations, in days. |

## ClickHouse gold.feed_monthly_revenue

| Column | Type | Meaning |
|---|---|---|
| month | UInt32 | Calendar month in dim_date; YYYYMM in the monthly revenue aggregate. |
| net_vnd | Int64 | Retained revenue: charged_vnd times (1-refunded), on the original payment date. |
| gmv | Int64 | Sum of original amounts before discounts and refunds, in VND. |
| discount_vnd | Int64 | Discount in integer VND, between zero and the original amount. |
| refund_vnd | Int64 | Sum of fully refunded charged amounts, in VND. |
| refunds | Int64 | Number of fully refunded transactions in the aggregate group. |
| payments | UInt64 | Number of payment transactions in the aggregate group. |

## ClickHouse gold.mv_course_completion_stats

| Column | Type | Meaning |
|---|---|---|
| course_sk | Int64 | Course surrogate key: course_id plus 1000000. |
| enrollments | UInt64 | Number of enrollments in the aggregate group. |
| completions | Int64 | Number of enrollments with completed_at in the group. |
| completion_days | Int64 | Sum of completed enrollment durations, in days. |

## ClickHouse gold.mv_monthly_revenue_summary

| Column | Type | Meaning |
|---|---|---|
| month | UInt32 | Calendar month in dim_date; YYYYMM in the monthly revenue aggregate. |
| net_vnd | Int64 | Retained revenue: charged_vnd times (1-refunded), on the original payment date. |
| gmv | Int64 | Sum of original amounts before discounts and refunds, in VND. |
| discount_vnd | Int64 | Discount in integer VND, between zero and the original amount. |
| refund_vnd | Int64 | Sum of fully refunded charged amounts, in VND. |
| refunds | Int64 | Number of fully refunded transactions in the aggregate group. |
| payments | UInt64 | Number of payment transactions in the aggregate group. |
