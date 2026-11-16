"""Fail-closed quality gate: counts, referential integrity, temporal SCD and money."""

import time
import os
from contextlib import closing
from etl.common import ch_connect, staging_connect, require_success, save_json, utc_now
from etl.integrity import fingerprints as content_fingerprints

FACTS = {
    "enrollments": ("enrollment_id", "enrolled_at", "enrolled_date_sk"),
    "payments": ("payment_id", "paid_at", "date_sk"),
    "lesson_completions": ("completion_id", "completed_at", "date_sk"),
    "quiz_attempts": ("attempt_id", "attempted_at", "date_sk"),
}


def validate(ch=None, expected=None, require_ready=True, database="gold"):
    if database not in ("gold", "gold_build"):
        raise ValueError("Validation database must be gold or gold_build")
    if ch is None:
        from etl.transform_gold import silver_bridge

        with closing(ch_connect()) as client, silver_bridge(client):
            return validate(client, expected, require_ready, database)

    def query(sql):
        return ch.query(sql.replace("gold.", database + ".").replace("silver.", "stage_bridge."))

    from etl.bootstrap import TABLES

    if require_ready:
        require_success()
    owned = ch is None
    ch = ch or ch_connect()
    started = time.perf_counter()
    checks = []

    def check(name, actual, wanted=0):
        passed = actual == wanted
        checks.append(dict(name=name, actual=actual, expected=wanted, passed=passed))
        if not passed:
            raise AssertionError(f"{name}: actual={actual}, expected={wanted}")

    def scalar(sql):
        return query(sql).first_row[0]

    try:
        if expected is None:
            with closing(staging_connect()) as pg, pg.cursor() as cur:
                expected = {}
                for t in TABLES:
                    cur.execute(f"SELECT count(*) FROM silver.{t}")
                    expected[t] = cur.fetchone()[0]
        for table in TABLES:
            key = query(f"DESCRIBE TABLE silver.{table}").first_row[0]
            for layer in ("silver",):
                check(
                    f"{layer}.{table}.count",
                    scalar(f"SELECT count() FROM {layer}.{table}"),
                    expected[table],
                )
                check(
                    f"{layer}.{table}.unique",
                    scalar(f"SELECT count()-uniqExact({key}) FROM {layer}.{table}"),
                )
            check(
                f"silver.{table}.positive_key",
                scalar(f"SELECT count() FROM silver.{table} WHERE {key} <= 0"),
            )
        minimum = int(os.environ.get("DW_MIN_SOURCE_ROWS", "5000000"))
        check("source.minimum_rows", sum(expected.values()) >= minimum, True)
        check(
            "silver.email_clean",
            scalar("SELECT count() FROM silver.users WHERE email != lowerUTF8(trimBoth(email))"),
        )
        check("silver.email_unique", scalar("SELECT count()-uniqExact(email) FROM silver.users"))
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
        fingerprints = {}
        for table, key in dimensions.items():
            check(table + ".unique", scalar(f"SELECT count()-uniqExact({key}) FROM gold.{table}"))
        check("date.1096_days_plus_unknown", scalar("SELECT count() FROM gold.dim_date"), 1097)
        check(
            "date.leap_day",
            scalar("SELECT count() FROM gold.dim_date WHERE full_date = '2024-02-29'"),
            1,
        )
        check(
            "scd.one_current",
            scalar("""SELECT count() FROM (SELECT user_id FROM gold.dim_user
                    GROUP BY user_id HAVING sum(is_current) != 1)"""),
        )
        check(
            "scd.no_overlap_or_gap",
            scalar("""SELECT count() FROM
          (SELECT user_id, valid_from, valid_to,
            leadInFrame(valid_from,1,toDateTime('2100-01-01 00:00:00','UTC')) OVER
            (PARTITION BY user_id ORDER BY valid_from ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS next_start
           FROM gold.dim_user) WHERE valid_to != next_start OR valid_from >= valid_to"""),
        )
        for table, (key, event_time, date_key) in FACTS.items():
            target = "gold.fact_" + table
            check(target + ".count", scalar(f"SELECT count() FROM {target}"), expected[table])
            check(target + ".unique", scalar(f"SELECT count()-uniqExact({key}) FROM {target}"))
            check(
                target + ".user_fk",
                scalar(
                    f"SELECT count() FROM {target} WHERE user_sk NOT IN (SELECT user_sk FROM gold.dim_user)"
                ),
            )
            check(
                target + ".course_fk",
                scalar(
                    f"SELECT count() FROM {target} WHERE course_sk NOT IN (SELECT course_sk FROM gold.dim_course)"
                ),
            )
            check(
                target + ".date_fk",
                scalar(
                    f"SELECT count() FROM {target} WHERE {date_key} NOT IN (SELECT date_sk FROM gold.dim_date)"
                ),
            )
            check(
                target + ".date_mapping",
                scalar(
                    f"SELECT count() FROM {target} WHERE {date_key} != toYYYYMMDD({event_time})"
                ),
            )
            check(
                target + ".scd_interval",
                scalar(f"""SELECT count() FROM {target} f INNER JOIN gold.dim_user u USING(user_sk)
              WHERE f.{event_time} < u.valid_from OR f.{event_time} >= u.valid_to"""),
            )
            check(
                target + ".source_key",
                scalar(
                    f"SELECT count() FROM {target} WHERE {key} NOT IN (SELECT {key} FROM silver.{table})"
                ),
            )
            check(
                target + ".source_identity",
                scalar(f"""SELECT count() FROM {target} f
              INNER JOIN silver.{table} s ON f.{key}=s.{key}
              INNER JOIN gold.dim_user u ON f.user_sk=u.user_sk
              INNER JOIN gold.dim_course c ON f.course_sk=c.course_sk
              WHERE u.user_id != s.user_id OR c.course_id != s.course_id OR f.{event_time} != s.{event_time}"""),
            )
            check(
                target + ".period",
                scalar(
                    f"SELECT count() FROM {target} WHERE {event_time} < '2022-01-01' OR {event_time} >= '2025-01-01'"
                ),
            )
            check(
                target + ".three_years",
                scalar(f"SELECT uniqExact(toYear({event_time})) FROM {target}"),
                3,
            )
            if table != "enrollments":
                check(
                    target + ".enrollment_identity_and_time",
                    scalar(f"""SELECT count() FROM silver.{table} f
                  INNER JOIN silver.enrollments e USING(enrollment_id)
                  WHERE f.user_id != e.user_id OR f.course_id != e.course_id OR f.{event_time} < e.enrolled_at"""),
                )
        for table in ("enrollments", "payments"):
            check(
                table + ".instructor_fk",
                scalar(f"""SELECT count() FROM gold.fact_{table}
                        WHERE instructor_sk NOT IN (SELECT instructor_sk FROM gold.dim_instructor)"""),
            )
        check(
            "payments.method_fk",
            scalar(
                "SELECT count() FROM gold.fact_payments WHERE method_sk NOT IN (SELECT method_sk FROM gold.dim_payment_method)"
            ),
        )
        check(
            "payments.transaction_unique",
            scalar("SELECT count()-uniqExact(transaction_id) FROM gold.fact_payments"),
        )
        check(
            "payments.money",
            scalar("""SELECT count() FROM gold.fact_payments WHERE charged_vnd != original_vnd-discount_vnd
                  OR net_vnd != charged_vnd*(1-refunded) OR net_vnd < 0"""),
        )
        check(
            "enrollments.completed_date_fk",
            scalar("""SELECT count() FROM gold.fact_enrollments
                   WHERE completed_date_sk NOT IN (SELECT date_sk FROM gold.dim_date)"""),
        )
        check(
            "enrollments.role_dates",
            scalar("""SELECT count() FROM gold.fact_enrollments WHERE
                 completed_date_sk != ifNull(toYYYYMMDD(completed_at),0)
                 OR is_completed != (completed_at IS NOT NULL) OR (completed_at < enrolled_at)"""),
        )
        check(
            "enrollments.lesson_totals",
            scalar("""SELECT count() FROM silver.enrollments e
                   LEFT JOIN (SELECT enrollment_id, count() AS n FROM silver.lesson_completions GROUP BY enrollment_id) l
                   USING(enrollment_id) WHERE e.lessons_completed != l.n"""),
        )
        for fact, dim, sk in [
            ("lesson_completions", "lesson", "lesson_sk"),
            ("quiz_attempts", "quiz", "quiz_sk"),
        ]:
            check(
                fact + ".dimension_fk",
                scalar(
                    f"SELECT count() FROM gold.fact_{fact} WHERE {sk} NOT IN (SELECT {sk} FROM gold.dim_{dim})"
                ),
            )
            check(
                fact + ".course_consistency",
                scalar(f"""SELECT count() FROM gold.fact_{fact} f
                       INNER JOIN gold.dim_{dim} d USING({sk}) INNER JOIN gold.dim_course c USING(course_sk)
                       WHERE d.course_id != c.course_id"""),
            )
        check(
            "quiz.score_and_pass",
            scalar("""SELECT count() FROM gold.fact_quiz_attempts WHERE correct_count > total_questions
                     OR correct_count < 0 OR total_questions <= 0 OR attempt_number <= 0
                     OR time_spent_seconds < 0 OR is_passed != (correct_count*100 >= total_questions*70)"""),
        )
        check(
            "lessons.duration_nonnegative",
            scalar("SELECT count() FROM gold.fact_lesson_completions WHERE time_spent_seconds < 0"),
        )
        check(
            "payments.refund_domain",
            scalar("SELECT count() FROM gold.fact_payments WHERE refunded NOT IN (0,1)"),
        )
        check(
            "dim_course.instructor_fk",
            scalar(
                "SELECT count() FROM gold.dim_course WHERE instructor_id NOT IN (SELECT instructor_id FROM gold.dim_instructor)"
            ),
        )
        for dimension in ("dim_lesson", "dim_quiz"):
            check(
                dimension + ".course_fk",
                scalar(
                    f"SELECT count() FROM gold.{dimension} WHERE course_id NOT IN (SELECT course_id FROM gold.dim_course)"
                ),
            )
        check(
            "scd.source_user_fk",
            scalar(
                "SELECT count() FROM gold.dim_user WHERE user_id NOT IN (SELECT user_id FROM silver.users)"
            ),
        )
        check(
            "scd.unique_effective_start",
            scalar("SELECT count()-uniqExact(tuple(user_id,valid_from)) FROM gold.dim_user"),
        )
        # Compare independently aggregated PostgreSQL source measures to Gold.
        with closing(staging_connect()) as pg, pg.cursor() as cur:
            cur.execute(
                "SELECT sum(charged_vnd*(1-refunded)), sum(charged_vnd), sum(discount_vnd) FROM silver.payments"
            )
            pg_money = tuple(int(v) for v in cur.fetchone())
            ch_money = query(
                "SELECT sum(net_vnd), sum(charged_vnd), sum(discount_vnd) FROM gold.fact_payments"
            ).first_row
            check("source.gold_money_reconciliation", tuple(ch_money), pg_money)
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
        # Order-independent fingerprints across every column, including NULLs.
        fingerprints = content_fingerprints(ch, database)
        result = dict(
            status="success",
            checked_at=utc_now(),
            checks=checks,
            fingerprints=fingerprints,
            seconds=round(time.perf_counter() - started, 3),
            source_rows=sum(expected.values()),
        )
        save_json("quality.json", result)
        print(f"Quality: {len(checks)} checks passed", flush=True)
        return result
    except Exception as exc:
        save_json(
            "quality.json",
            dict(status="failed", checked_at=utc_now(), checks=checks, error=str(exc)),
        )
        raise
    finally:
        if owned:
            ch.close()
