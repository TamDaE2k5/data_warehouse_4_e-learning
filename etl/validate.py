"""
==================================================================================
MODULE CỔNG KIỂM TOÁN CHẤT LƯỢNG DỮ LIỆU TỰ ĐỘNG (QUALITY GATES ENGINE)
==================================================================================
Mục tiêu:
  - Thiết lập chốt chặn chất lượng dữ liệu tự động (Automated Quality Gatekeeper)
    trước khi dữ liệu được công bố chính thức cho người dùng cuối (Business Analyst/BI).
  - Thực thi toàn diện 116 chỉ tiêu kiểm toán nghiêm ngặt:
      1. Đối soát số lượng dòng (Row count parity): Khớp 100% giữa PostgreSQL Silver và ClickHouse Gold.
      2. Tính duy nhất của khóa (Uniqueness): Khóa chính và Surrogate Key không có bản ghi trùng lặp.
      3. Toàn vẹn tham chiếu (Referential Integrity): 100% khóa ngoại trong các bảng Fact phải tồn tại trong bảng Chiều.
      4. Kiểm toán chuỗi thời gian SCD Type 2:
         - Mỗi học viên tại một thời điểm chỉ có ĐÚNG 1 bản ghi hiện hành (`sum(is_current) == 1`).
         - Không có khoảng hở (No gaps) và không có khoảng đè chéo (No overlaps) giữa các khoảng hiệu lực.
      5. Đối soát số liệu tài chính chéo hệ thống (Cross-Database Financial Reconciliation):
         Tổng doanh thu, tổng tiền thực thu và tổng tiền giảm giá tính độc lập trên PostgreSQL Silver
         phải khớp chính xác từng đồng xu với ClickHouse Gold (`source.gold_money_reconciliation`).
      6. Tính đúng đắn của các bảng tổng hợp Materialized Views (SummingMergeTree).
      7. Dấu vân tay băm toàn phần (Order-independent Fingerprints): Băm `cityHash64` toàn bộ cột để
         phát hiện sai lệch dữ liệu ở mức độ từng bit.
  - Cơ chế Chặn lỗi nghiêm ngặt (Fail-Closed Architecture):
      + Chỉ cần 1 trong 116 chỉ tiêu bị vi phạm (dù chỉ lệch 1 dòng), hệ thống sẽ ném `AssertionError`
        và HỦY TOÀN BỘ quá trình công bố bản Gold.
==================================================================================
"""

import time
from etl.common import ch_connect, staging_connect, require_success, save_json, utc_now

# Cấu hình danh mục 4 bảng Fact và các trường sự kiện phục vụ kiểm toán:
# Cấu trúc: 'tên_fact': (khóa_chính, cột_thời_gian_sự_kiện, khóa_ngoại_ngày)
FACTS = {
    "enrollments": ("enrollment_id", "enrolled_at", "enrolled_date_sk"),
    "payments": ("payment_id", "paid_at", "date_sk"),
    "lesson_completions": ("completion_id", "completed_at", "date_sk"),
    "quiz_attempts": ("attempt_id", "attempted_at", "date_sk"),
}


def validate(ch=None, expected=None, require_ready=True, database="gold"):
    """
    Hàm thực thi 116 bài kiểm toán chất lượng dữ liệu.

    Tham số:
      - ch: Client kết nối ClickHouse (nếu None, tự tạo kết nối kèm cầu nối stage_bridge).
      - expected: Từ điển số lượng dòng kỳ vọng của từng bảng ở lớp Silver.
      - require_ready: Bắt buộc kiểm tra manifest pipeline thành công trước đó hay không.
      - database: Tên database cần kiểm toán ('gold' hoặc database bóng 'gold_build').
    """
    if ch is None:
        from contextlib import closing
        from etl.transform_gold import silver_bridge

        with closing(ch_connect()) as client, silver_bridge(client):
            return validate(client, expected, require_ready, database)

    def query(sql: str):
        """Hàm trợ giúp thực thi truy vấn trên ClickHouse, tự động định tuyến tên database."""
        return ch.query(
            sql.replace("gold.", database + ".").replace("silver.", "stage_bridge.")
        )

    from etl.bootstrap import TABLES

    if require_ready:
        require_success()

    owned = ch is None
    ch = ch or ch_connect()
    started = time.perf_counter()
    checks = []

    def check(name: str, actual, wanted=0):
        """
        Hàm xác nhận chỉ tiêu kiểm toán (Assertion Helper).
        Nếu giá trị thực tế khác giá trị kỳ vọng, ném ngay ngoại lệ AssertionError.
        """
        passed = actual == wanted
        checks.append(dict(name=name, actual=actual, expected=wanted, passed=passed))
        if not passed:
            raise AssertionError(f"{name}: actual={actual}, expected={wanted}")

    def scalar(sql: str):
        """Thực thi câu truy vấn SQL trả về một giá trị vô hướng đơn lẻ."""
        return query(sql).first_row[0]

    try:
        # Nếu chưa có số lượng dòng kỳ vọng, đọc trực tiếp từ PostgreSQL Staging (schema silver)
        if expected is None:
            with staging_connect() as pg, pg.cursor() as cur:
                expected = {}
                for t in TABLES:
                    cur.execute(f"SELECT count(*) FROM silver.{t}")
                    expected[t] = cur.fetchone()[0]

        # ----------------------------------------------------------------------
        # NHÓM 1: KIỂM TRA LỚP SILVER (TÍNH DUY NHẤT & KHÓA DƯƠNG)
        # ----------------------------------------------------------------------
        for table in TABLES:
            key = query(f"DESCRIBE TABLE silver.{table}").first_row[0]
            for layer in ("silver",):
                # 1.1 Khớp số lượng dòng với nguồn
                check(
                    f"{layer}.{table}.count",
                    scalar(f"SELECT count() FROM {layer}.{table}"),
                    expected[table],
                )
                # 1.2 Tính duy nhất tuyệt đối của khóa chính (count - uniqExact == 0)
                check(
                    f"{layer}.{table}.unique",
                    scalar(f"SELECT count() - uniqExact({key}) FROM {layer}.{table}"),
                )
            # 1.3 Khóa chính phải là số nguyên dương hợp lệ (> 0)
            check(
                f"silver.{table}.positive_key",
                scalar(f"SELECT count() FROM silver.{table} WHERE {key} <= 0"),
            )

        # 1.4 Kiểm tra quy mô tập dữ liệu sản xuất (> 5 triệu bản ghi tổng thể)
        check("production_source_5M", sum(expected.values()) >= 5000000, True)

        # 1.5 Kiểm tra dữ liệu dơ đã được làm sạch: Email đã cắt khoảng trắng và viết thường
        check(
            "silver.email_clean",
            scalar(
                "SELECT count() FROM silver.users WHERE email != lowerUTF8(trimBoth(email))"
            ),
        )
        check(
            "silver.email_unique",
            scalar("SELECT count() - uniqExact(email) FROM silver.users"),
        )

        # ----------------------------------------------------------------------
        # NHÓM 2: KIỂM TOÁN CÁC BẢNG CHIỀU GOLD (DIMENSIONS)
        # ----------------------------------------------------------------------
        dimensions = {
            "dim_date": "date_sk",
            "dim_user": "user_sk",
            "dim_course": "course_sk",
            "dim_instructor": "instructor_sk",
            "dim_lesson": "lesson_sk",
            "dim_quiz": "quiz_sk",
            "dim_payment_method": "method_sk",
        }
        dimension_sources = {
            "dim_user": "user_history",
            "dim_course": "courses",
            "dim_instructor": "instructors",
            "dim_lesson": "lessons",
            "dim_quiz": "quizzes",
            "dim_payment_method": "payment_methods",
        }
        for dimension, source in dimension_sources.items():
            check(
                f"{dimension}.source_count",
                scalar(f"SELECT count() FROM gold.{dimension}"),
                expected[source],
            )

        # 2.1 Tính duy nhất của Surrogate Key trên từng bảng chiều
        for table, key in dimensions.items():
            check(
                table + ".unique",
                scalar(f"SELECT count() - uniqExact({key}) FROM gold.{table}"),
            )

        # 2.2 Kiểm toán Chiều thời gian (dim_date): Đủ 1.096 ngày + 1 ngày dummy mốc 0
        check(
            "date.1096_days_plus_unknown",
            scalar("SELECT count() FROM gold.dim_date"),
            1097,
        )
        # Kiểm tra sự hiện diện chính xác của ngày nhuận 29/02/2024
        check(
            "date.leap_day",
            scalar(
                "SELECT count() FROM gold.dim_date WHERE full_date = '2024-02-29'"
            ),
            1,
        )

        # ----------------------------------------------------------------------
        # NHÓM 3: KIỂM TOÁN TÍNH TOÀN VẸN CHIỀU SCD TYPE 2 (DIM_USER)
        # ----------------------------------------------------------------------
        # 3.1 Mỗi học viên chỉ có đúng 1 bản ghi mang trạng thái hiện hành (is_current = 1)
        check(
            "scd.one_current",
            scalar(
                """
                SELECT count() FROM (
                    SELECT user_id FROM gold.dim_user
                    GROUP BY user_id HAVING sum(is_current) != 1
                )
                """
            ),
        )

        # 3.2 Chuỗi thời gian SCD Type 2 không có khoảng hở (No Gap) và không đè chéo (No Overlap)
        # Sử dụng Window Function leadInFrame để đối chiếu valid_to của bản ghi trước với valid_from của bản ghi sau
        check(
            "scd.no_overlap_or_gap",
            scalar(
                """
                SELECT count() FROM (
                    SELECT user_id, valid_from, valid_to,
                        leadInFrame(valid_from, 1, toDateTime('2100-01-01 00:00:00', 'UTC')) OVER (
                            PARTITION BY user_id ORDER BY valid_from 
                            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
                        ) AS next_start
                    FROM gold.dim_user
                ) 
                WHERE valid_to != next_start OR valid_from >= valid_to
                """
            ),
        )

        # ----------------------------------------------------------------------
        # NHÓM 4: KIỂM TOÁN CÁC BẢNG SỰ KIỆN FACT (GALAXY SCHEMA INTEGRITY)
        # ----------------------------------------------------------------------
        for table, (key, event_time, date_key) in FACTS.items():
            target = "gold.fact_" + table
            # 4.1 Khớp số lượng dòng với Silver
            check(target + ".count", scalar(f"SELECT count() FROM {target}"), expected[table])
            # 4.2 Tính duy nhất của khóa sự kiện
            check(target + ".unique", scalar(f"SELECT count() - uniqExact({key}) FROM {target}"))
            # 4.3 Khóa ngoại user_sk phải tồn tại trong dim_user (Toàn vẹn tham chiếu)
            check(
                target + ".user_fk",
                scalar(f"SELECT count() FROM {target} WHERE user_sk NOT IN (SELECT user_sk FROM gold.dim_user)"),
            )
            # 4.4 Khóa ngoại course_sk phải tồn tại trong dim_course
            check(
                target + ".course_fk",
                scalar(f"SELECT count() FROM {target} WHERE course_sk NOT IN (SELECT course_sk FROM gold.dim_course)"),
            )
            # 4.5 Khóa ngoại date_sk phải tồn tại trong dim_date
            check(
                target + ".date_fk",
                scalar(f"SELECT count() FROM {target} WHERE {date_key} NOT IN (SELECT date_sk FROM gold.dim_date)"),
            )
            # 4.6 Ánh xạ ngày chính xác: date_sk phải bằng toYYYYMMDD(thời điểm sự kiện)
            check(
                target + ".date_mapping",
                scalar(f"SELECT count() FROM {target} WHERE {date_key} != toYYYYMMDD({event_time})"),
            )
            # 4.7 RÀNG BUỘC THỜI GIAN SCD TYPE 2:
            # Thời điểm phát sinh sự kiện bắt buộc phải nằm trong khoảng hiệu lực [valid_from, valid_to) của user_sk tương ứng!
            check(
                target + ".scd_interval",
                scalar(
                    f"""
                    SELECT count() FROM {target} f 
                    INNER JOIN gold.dim_user u USING(user_sk)
                    WHERE f.{event_time} < u.valid_from OR f.{event_time} >= u.valid_to
                    """
                ),
            )
            # 4.8 Khóa sự kiện phải tồn tại ở bảng nguồn Silver
            check(
                target + ".source_key",
                scalar(f"SELECT count() FROM {target} WHERE {key} NOT IN (SELECT {key} FROM silver.{table})"),
            )
            # 4.9 Tính đồng nhất bản sắc (Identity Consistency): user_id, course_id và thời gian khớp 100% giữa Silver và Gold
            check(
                target + ".source_identity",
                scalar(
                    f"""
                    SELECT count() FROM {target} f
                    INNER JOIN silver.{table} s ON f.{key} = s.{key}
                    INNER JOIN gold.dim_user u ON f.user_sk = u.user_sk
                    INNER JOIN gold.dim_course c ON f.course_sk = c.course_sk
                    WHERE u.user_id != s.user_id OR c.course_id != s.course_id OR f.{event_time} != s.{event_time}
                    """
                ),
            )
            # 4.10 Kiểm tra ranh giới thời gian 3 năm (2022 - 2024)
            check(
                target + ".period",
                scalar(f"SELECT count() FROM {target} WHERE {event_time} < '2022-01-01' OR {event_time} >= '2025-01-01'"),
            )
            check(target + ".three_years", scalar(f"SELECT uniqExact(toYear({event_time})) FROM {target}"), 3)

            # 4.11 Các sự kiện con (payments, completions, attempts) không thể xảy ra trước ngày học viên ghi danh
            if table != "enrollments":
                check(
                    target + ".enrollment_identity_and_time",
                    scalar(
                        f"""
                        SELECT count() FROM silver.{table} f
                        INNER JOIN silver.enrollments e USING(enrollment_id)
                        WHERE f.user_id != e.user_id OR f.course_id != e.course_id OR f.{event_time} < e.enrolled_at
                        """
                    ),
                )

        # ----------------------------------------------------------------------
        # NHÓM 5: KIỂM TOÁN CÁC ĐỘ ĐO & LOGIC NGHIỆP VỤ ĐẶC THÙ
        # ----------------------------------------------------------------------
        # 5.1 Khóa ngoại giảng viên trên bảng enrollments và payments
        for table in ("enrollments", "payments"):
            check(
                table + ".instructor_fk",
                scalar(
                    f"""
                    SELECT count() FROM gold.fact_{table}
                    WHERE instructor_sk NOT IN (SELECT instructor_sk FROM gold.dim_instructor)
                    """
                ),
            )

        # 5.2 Kiểm toán bảng thanh toán (fact_payments)
        check(
            "payments.method_fk",
            scalar("SELECT count() FROM gold.fact_payments WHERE method_sk NOT IN (SELECT method_sk FROM gold.dim_payment_method)"),
        )
        check(
            "payments.transaction_unique",
            scalar("SELECT count() - uniqExact(transaction_id) FROM gold.fact_payments"),
        )
        check(
            "payments.money",
            scalar(
                """
                SELECT count() FROM gold.fact_payments 
                WHERE charged_vnd != original_vnd - discount_vnd
                   OR net_vnd != charged_vnd * (1 - refunded) 
                   OR net_vnd < 0
                """
            ),
        )

        # 5.3 Kiểm toán bảng ghi danh (fact_enrollments)
        check(
            "enrollments.completed_date_fk",
            scalar("SELECT count() FROM gold.fact_enrollments WHERE completed_date_sk NOT IN (SELECT date_sk FROM gold.dim_date)"),
        )
        check(
            "enrollments.role_dates",
            scalar(
                """
                SELECT count() FROM gold.fact_enrollments 
                WHERE completed_date_sk != ifNull(toYYYYMMDD(completed_at), 0)
                   OR is_completed != (completed_at IS NOT NULL) 
                   OR (completed_at < enrolled_at)
                """
            ),
        )
        # Tổng số bài học đã hoàn thành phải khớp chính xác với số dòng trong bảng chi tiết lesson_completions
        check(
            "enrollments.lesson_totals",
            scalar(
                """
                SELECT count() FROM silver.enrollments e
                LEFT JOIN (SELECT enrollment_id, count() AS n FROM silver.lesson_completions GROUP BY enrollment_id) l
                USING(enrollment_id) WHERE e.lessons_completed != l.n
                """
            ),
        )

        # 5.4 Kiểm toán bài học và bài kiểm tra
        for fact, dim, sk in [
            ("lesson_completions", "lesson", "lesson_sk"),
            ("quiz_attempts", "quiz", "quiz_sk"),
        ]:
            check(
                fact + ".dimension_fk",
                scalar(f"SELECT count() FROM gold.fact_{fact} WHERE {sk} NOT IN (SELECT {sk} FROM gold.dim_{dim})"),
            )
            check(
                fact + ".course_consistency",
                scalar(
                    f"""
                    SELECT count() FROM gold.fact_{fact} f
                    INNER JOIN gold.dim_{dim} d USING({sk}) 
                    INNER JOIN gold.dim_course c USING(course_sk)
                    WHERE d.course_id != c.course_id
                    """
                ),
            )

        # 5.5 Kiểm toán điểm thi trắc nghiệm (0 <= điểm <= tổng số câu và logic is_passed)
        check(
            "quiz.score_and_pass",
            scalar(
                """
                SELECT count() FROM gold.fact_quiz_attempts 
                WHERE correct_count > total_questions
                   OR correct_count < 0 
                   OR is_passed != (correct_count * 100 >= total_questions * 70)
                """
            ),
        )

        # ----------------------------------------------------------------------
        # NHÓM 6: ĐỐI SOÁT TÀI CHÍNH CHÉO HỆ THỐNG (POSTGRESQL VS CLICKHOUSE)
        # ----------------------------------------------------------------------
        # Tính toán độc lập trên PostgreSQL Silver rồi so sánh với ClickHouse Gold:
        with staging_connect() as pg, pg.cursor() as cur:
            cur.execute(
                "SELECT sum(charged_vnd * (1 - refunded)), sum(charged_vnd), sum(discount_vnd) FROM silver.payments"
            )
            pg_money = tuple(int(v) for v in cur.fetchone())
            ch_money = query(
                "SELECT sum(net_vnd), sum(charged_vnd), sum(discount_vnd) FROM gold.fact_payments"
            ).first_row
            check("source.gold_money_reconciliation", tuple(ch_money), pg_money)

        # Khớp tổng doanh thu trong bảng tổng hợp Materialized View với Fact
        check(
            "revenue_summary.reconciliation",
            scalar("SELECT sum(net_vnd) FROM gold.mv_monthly_revenue_summary"),
            ch_money[0],
        )
        check(
            "course_summary.reconciliation",
            scalar("SELECT sum(enrollments) FROM gold.mv_course_completion_stats"),
            expected["enrollments"],
        )

        # ----------------------------------------------------------------------
        # NHÓM 7: BĂM DẤU VÂN TAY DỮ LIỆU ĐỘC LẬP THỨ TỰ (DATA FINGERPRINTS)
        # ----------------------------------------------------------------------
        fingerprints = {}
        for table in list(dimensions) + ["fact_" + t for t in FACTS]:
            cols = [r[0] for r in query(f"DESCRIBE TABLE gold.{table}").result_rows]
            expr = "cityHash64(toJSONString(tuple(" + ",".join(cols) + ")))"
            row = query(
                f"SELECT count(), sum({expr}), groupBitXor({expr}) FROM gold.{table}"
            ).first_row
            fingerprints[table] = list(row)

        # Ghi nhận kết quả kiểm toán thành công ra file manifest quality.json
        result = dict(
            status="success",
            checked_at=utc_now(),
            checks=checks,
            fingerprints=fingerprints,
            seconds=round(time.perf_counter() - started, 3),
            source_rows=sum(expected.values()),
        )
        save_json("quality.json", result)
        print(f"Kiểm toán chất lượng: ĐẠT {len(checks)}/116 chỉ tiêu!", flush=True)
        return result

    except Exception as exc:
        # Nếu có bất kỳ kiểm toán nào thất bại, ghi nhận manifest lỗi và ném ngoại lệ
        save_json(
            "quality.json",
            dict(
                status="failed",
                checked_at=utc_now(),
                checks=checks,
                error=str(exc),
            ),
        )
        raise
    finally:
        if owned:
            ch.close()
