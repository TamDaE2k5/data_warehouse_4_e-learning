# Source-to-target mapping

## Operational records to Silver

Full extraction reads the explicit business-column contract within one repeatable-read source snapshot. Incremental extraction reads safely committed journal payloads by transaction ID and per-key revision, rather than relying only on `updated_at`. Silver retains source identifiers and corresponding PostgreSQL business types. Technical `dw_revision` is recorded in control state rather than copied into every Silver business table.

Text is trimmed, emails lowercased and country codes uppercased. Validation checks row shape, required labels, positive identifiers, Int64 bounds, UTC timestamps, value domains, amount formulas and references. Rejected payloads retain a machine-readable code and reason in quarantine. Valid corrections resolve previous rejections; invalid updates preserve the preceding clean version.

Source deletes remove the Silver row and create a pending Gold deletion. Silver and pending state commit together, so a Gold failure does not lose the change. `needs_full` remains set after a committed full stage until a complete Gold rebuild is successfully published. Publication confirms the checkpoint only after the serving tables and aggregate feeds are ready.

## Dimensions

| Source | Target | Mapping |
|---|---|---|
| Generated calendar | `dim_date` | 2022-01-01 through 2024-12-31; YYYYMMDD key and calendar fields; unknown key 0 |
| `silver.user_history` | `dim_user` | `history_id + 10000000`; keep natural user ID, cleaned attributes and effective interval |
| `silver.courses` | `dim_course` | `course_id + 1000000`; current title/category/difficulty/instructor/list price |
| `silver.instructors` | `dim_instructor` | `instructor_id + 2000000`; name and expertise |
| `silver.lessons` | `dim_lesson` | `lesson_id + 3000000`; course, title and lesson position |
| `silver.quizzes` | `dim_quiz` | `quiz_id + 4000000`; course, title and number of questions |
| `silver.payment_methods` | `dim_payment_method` | `method_id + 5000000`; method name |

`silver.users` holds the current source learner snapshot and supports auditing. `dim_user` derives from actual `user_history` versions; it is not created by copying the latest learner row into invented historical periods.

## Facts

Every fact retains its source event identifier and the enrollment reference where applicable. Course keys come from `dim_course`. Learner-version keys come from the event-time history lookup, with effective-interval checks. Count and reference reconciliation catches missing rows that an inner join could otherwise hide.

| Target | History lookup time | Additional keys | Measures and retained references |
|---|---|---|---|
| `fact_enrollments` | `enrolled_at` | Instructor through course; enrolled date; completed date or 0 | enrollment ID, event times, lessons completed, completed flag |
| `fact_payments` | `paid_at` | Instructor through course, payment method, payment date | payment/enrollment/transaction ID; original, discount, charged, refunded, net amounts |
| `fact_lesson_completions` | `completed_at` | Lesson and completion date | completion/enrollment ID and time spent |
| `fact_quiz_attempts` | `attempted_at` | Quiz and attempt date | attempt/enrollment ID, attempt number, correct/questions, duration and pass flag |

Revenue is `charged_vnd * (1-refunded)`; the source supports full refunds only. Passing means `correct_count * 100 >= total_questions * 70`. Completion means an enrollment has a non-null completion timestamp. Rates are recomputed from their numerators and denominators, not added across groups.

Enrollment history attribution stays at enrollment time. The same learner can have another `user_sk` on a later payment or learning event. Use natural `user_id` to count people across these versions.

## Reports and lineage

Reports query Gold directly; CSV is an output, not an analytical input. A complete CSV set is published with a manifest containing the pipeline run ID, row count, source SQL and SHA-256 for each file. Drill-across aggregates the facts separately at a common grain before joining.

Benchmark copies the same eleven Gold tables into PostgreSQL, verifies full-row SHA-256 and result multisets, then measures seven equivalent query pairs. Executed SQL and generated mirror DDL are runtime evidence under `artifacts/benchmark`, keeping verification from modifying tracked source files. Follow `artifacts/benchmark/latest.json` to a complete immutable result bundle.
