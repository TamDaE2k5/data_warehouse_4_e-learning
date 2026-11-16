"""Consistent dashboard snapshots protected by a shared publication lock."""

from contextlib import closing
from datetime import date, datetime
import calendar
import pandas as pd
from etl.common import ch_connect, staging_connect, project_lock, require_success

FRAME_COLUMNS = {
    "finance": [
        "month",
        "net_vnd",
        "gross_vnd",
        "discount_vnd",
        "refund_vnd",
        "payments",
        "refunds",
    ],
    "funnel": ["enrolled", "started", "completed", "avg_days"],
    "courses": ["category", "enrollments", "completions", "completion_pct"],
    "enrollment_trend": ["month", "enrollments", "completions"],
    "revenue_categories": ["category", "net_vnd", "payments"],
    "methods": ["method_name", "net_vnd", "payments"],
    "quiz": [
        "quiz_id",
        "quiz_title",
        "category",
        "attempts",
        "pass_pct",
        "avg_score_pct",
        "passed",
        "correct_answers",
        "question_count",
        "duration_score_corr",
    ],
    "instructors": ["instructor_id", "full_name", "net_vnd", "payments"],
    "cities": ["city", "net_vnd", "payments"],
    "prior_money": ["net_vnd", "payments"],
    "prior_learning": ["enrolled", "completed"],
}


def validate_scope(start, end, categories):
    """Reject invalid scopes before opening a database connection."""
    if any(not isinstance(value, date) or isinstance(value, datetime) for value in (start, end)):
        raise ValueError("Reporting boundaries must be calendar dates")
    if not date(2022, 1, 1) <= start <= end <= date(2024, 12, 31):
        raise ValueError("Choose an ordered date range inside the 2022–2024 calendar")
    if isinstance(categories, (str, bytes)) or not categories:
        raise ValueError("Select at least one course category")
    if any(not isinstance(value, str) or not value.strip() for value in categories):
        raise ValueError("Course categories must be nonempty strings")
    return tuple(dict.fromkeys(categories))


def comparison_period(start, end):
    """Same calendar dates one year earlier, only inside the supported calendar."""
    if start.year != end.year or start.year <= 2022:
        return None

    def previous(value):
        return date(
            value.year - 1,
            value.month,
            min(value.day, calendar.monthrange(value.year - 1, value.month)[1]),
        )

    return previous(start), previous(end)


def snapshot(run_id, start, end, categories):
    categories = validate_scope(start, end, categories)
    with project_lock(shared=True):
        manifest = require_success()
        if manifest["run_id"] != run_id:
            raise RuntimeError("The published snapshot changed. Refresh to read the new version.")
        parameters = dict(start=str(start), end=str(end), categories=tuple(categories))
        with closing(ch_connect()) as ch:

            def query(name, sql):
                result = ch.query(sql, parameters=parameters)
                # Native ClickHouse responses can omit column headers for zero rows.
                return pd.DataFrame(result.result_rows, columns=FRAME_COLUMNS[name])

            def scope(event):
                return f"""toDate({event}) BETWEEN toDate(%(start)s) AND toDate(%(end)s)
                    AND c.category IN %(categories)s"""

            finance = query(
                "finance",
                f"""SELECT toStartOfMonth(p.paid_at) AS month,
                sum(p.net_vnd) AS net_vnd,sum(p.original_vnd) AS gross_vnd,
                sum(p.discount_vnd) AS discount_vnd,sum(p.charged_vnd*p.refunded) AS refund_vnd,
                count() AS payments,sum(p.refunded) AS refunds
                FROM gold.fact_payments p JOIN gold.dim_course c USING(course_sk)
                WHERE {scope("p.paid_at")} GROUP BY month ORDER BY month""",
            )
            funnel = query(
                "funnel",
                f"""SELECT count() AS enrolled,countIf(e.lessons_completed>0) AS started,
                sum(e.is_completed) AS completed,avgIf(dateDiff('day',e.enrolled_at,e.completed_at),e.is_completed=1) AS avg_days
                FROM gold.fact_enrollments e JOIN gold.dim_course c USING(course_sk)
                WHERE {scope("e.enrolled_at")}""",
            )
            courses = query(
                "courses",
                f"""SELECT c.category,count() AS enrollments,sum(e.is_completed) AS completions,
                round(100*completions/nullIf(enrollments,0),2) AS completion_pct
                FROM gold.fact_enrollments e JOIN gold.dim_course c USING(course_sk)
                WHERE {scope("e.enrolled_at")} GROUP BY c.category ORDER BY enrollments DESC""",
            )
            enrollment_trend = query(
                "enrollment_trend",
                f"""SELECT toStartOfMonth(e.enrolled_at) AS month,
                count() AS enrollments,sum(e.is_completed) AS completions
                FROM gold.fact_enrollments e JOIN gold.dim_course c USING(course_sk)
                WHERE {scope("e.enrolled_at")} GROUP BY month ORDER BY month""",
            )
            revenue_categories = query(
                "revenue_categories",
                f"""SELECT c.category,sum(p.net_vnd) AS net_vnd,count() AS payments
                FROM gold.fact_payments p JOIN gold.dim_course c USING(course_sk)
                WHERE {scope("p.paid_at")} GROUP BY c.category ORDER BY net_vnd DESC,c.category""",
            )
            methods = query(
                "methods",
                f"""SELECT m.method_name,sum(p.net_vnd) AS net_vnd,count() AS payments
                FROM gold.fact_payments p JOIN gold.dim_course c USING(course_sk)
                JOIN gold.dim_payment_method m USING(method_sk)
                WHERE {scope("p.paid_at")} GROUP BY m.method_name ORDER BY net_vnd DESC,m.method_name""",
            )
            quiz = query(
                "quiz",
                f"""SELECT d.quiz_id,d.title AS quiz_title,c.category,count() AS attempts,
                round(100*avg(q.is_passed),2) AS pass_pct,
                round(100*avg(q.correct_count/q.total_questions),2) AS avg_score_pct,
                sum(q.is_passed) AS passed,sum(q.correct_count) AS correct_answers,
                sum(q.total_questions) AS question_count,
                corr(toFloat64(q.time_spent_seconds),q.correct_count/q.total_questions) AS duration_score_corr
                FROM gold.fact_quiz_attempts q JOIN gold.dim_course c USING(course_sk)
                JOIN gold.dim_quiz d USING(quiz_sk) WHERE {scope("q.attempted_at")}
                GROUP BY d.quiz_id,d.title,c.category ORDER BY attempts DESC,d.quiz_id""",
            )
            instructors = query(
                "instructors",
                f"""SELECT i.instructor_id,i.full_name,sum(p.net_vnd) AS net_vnd,count() AS payments
                FROM gold.fact_payments p JOIN gold.dim_course c USING(course_sk)
                JOIN gold.dim_instructor i USING(instructor_sk) WHERE {scope("p.paid_at")}
                GROUP BY i.instructor_id,i.instructor_sk,i.full_name ORDER BY net_vnd DESC,i.instructor_sk LIMIT 15""",
            )
            cities = query(
                "cities",
                f"""SELECT u.city,sum(p.net_vnd) AS net_vnd,count() AS payments
                FROM gold.fact_payments p JOIN gold.dim_course c USING(course_sk)
                JOIN gold.dim_user u USING(user_sk) WHERE {scope("p.paid_at")}
                GROUP BY u.city ORDER BY net_vnd DESC,u.city""",
            )
            baseline = None
            if previous := comparison_period(start, end):
                parameters.update(start=str(previous[0]), end=str(previous[1]))
                prior_money = query(
                    "prior_money",
                    f"""SELECT sum(p.net_vnd) AS net_vnd,count() AS payments
                    FROM gold.fact_payments p JOIN gold.dim_course c USING(course_sk)
                    WHERE {scope("p.paid_at")}""",
                ).iloc[0]
                prior_learning = query(
                    "prior_learning",
                    f"""SELECT count() AS enrolled,sum(e.is_completed) AS completed
                    FROM gold.fact_enrollments e JOIN gold.dim_course c USING(course_sk)
                    WHERE {scope("e.enrolled_at")}""",
                ).iloc[0]
                baseline = dict(
                    start=previous[0],
                    end=previous[1],
                    net_vnd=int(prior_money.net_vnd),
                    payments=int(prior_money.payments),
                    enrolled=int(prior_learning.enrolled),
                    completed=int(prior_learning.completed),
                )
        return dict(
            manifest=manifest,
            finance=finance,
            funnel=funnel,
            courses=courses,
            enrollment_trend=enrollment_trend,
            revenue_categories=revenue_categories,
            methods=methods,
            baseline=baseline,
            quiz=quiz,
            instructors=instructors,
            cities=cities,
        )


def operations_snapshot(run_id):
    """Read control-plane status without scanning analytical fact tables."""
    with project_lock(shared=True):
        manifest = require_success()
        if manifest["run_id"] != run_id:
            raise RuntimeError("The published snapshot changed. Refresh to read the new version.")
        with closing(staging_connect()) as pg, pg.cursor() as cursor:
            cursor.execute("""SELECT table_name,error_code,count(*) AS records,
                count(*) FILTER(WHERE resolved_at IS NULL) AS open_records
                FROM quarantine.quarantine_records GROUP BY 1,2 ORDER BY 3 DESC,1,2""")
            quarantine = pd.DataFrame(
                cursor.fetchall(), columns=["Table", "Error code", "Total", "Open"]
            )
            cursor.execute("""SELECT table_name,source_id,error_code,rejection_reason,detected_at,resolved_at
                FROM quarantine.quarantine_records ORDER BY detected_at DESC,table_name,source_id LIMIT 50""")
            recent_errors = pd.DataFrame(
                cursor.fetchall(),
                columns=[
                    "Table",
                    "Source ID",
                    "Error code",
                    "Reason",
                    "Detected at",
                    "Resolved at",
                ],
            )
            cursor.execute("""SELECT run_id,phase,started_at,finished_at,
                manifest->>'mode' AS mode,manifest->>'seconds' AS seconds
                FROM staging.pipeline_runs ORDER BY started_at DESC,run_id LIMIT 10""")
            runs = pd.DataFrame(
                cursor.fetchall(),
                columns=["Run ID", "Phase", "Started at", "Finished at", "Mode", "Seconds"],
            )
        return dict(
            manifest=manifest, quarantine=quarantine, recent_errors=recent_errors, runs=runs
        )


def options():
    with project_lock(shared=True):
        manifest = require_success()
        with closing(ch_connect()) as ch:
            categories = [
                row[0]
                for row in ch.query(
                    "SELECT DISTINCT category FROM gold.dim_course ORDER BY category"
                ).result_rows
            ]
            bounds = ch.query(
                "SELECT min(toDate(enrolled_at)),max(toDate(enrolled_at)) FROM gold.fact_enrollments"
            ).first_row
        return manifest, categories, bounds


def detail(run_id, kind, start, end, categories):
    """Optional drilldowns, retaining the same publication and filter contract."""
    categories = validate_scope(start, end, categories)
    if kind not in {"study", "movers"}:
        raise ValueError("Unknown drilldown")
    with project_lock(shared=True):
        if require_success()["run_id"] != run_id:
            raise RuntimeError("Snapshot changed; refresh the portal")
        with closing(ch_connect()) as ch:
            params = dict(start=str(start), end=str(end), categories=tuple(categories))
            if kind == "study":
                sql = """WITH study AS (
                    SELECT l.enrollment_id,l.course_sk,sum(l.time_spent_seconds) AS study_seconds
                    FROM gold.fact_lesson_completions l JOIN gold.dim_course c USING(course_sk)
                    WHERE toDate(l.completed_at) BETWEEN toDate(%(start)s) AND toDate(%(end)s)
                      AND c.category IN %(categories)s GROUP BY l.enrollment_id,l.course_sk
                ), scores AS (
                    SELECT q.enrollment_id,q.course_sk,avg(q.correct_count/q.total_questions) AS score
                    FROM gold.fact_quiz_attempts q JOIN gold.dim_course c USING(course_sk)
                    WHERE toDate(q.attempted_at) BETWEEN toDate(%(start)s) AND toDate(%(end)s)
                      AND c.category IN %(categories)s GROUP BY q.enrollment_id,q.course_sk
                ) SELECT c.course_id,c.title,count() AS enrollments,
                    corr(toFloat64(study_seconds),score) AS correlation
                  FROM scores JOIN study USING(enrollment_id,course_sk)
                  JOIN gold.dim_course c USING(course_sk)
                  GROUP BY c.course_id,c.title HAVING enrollments>1 ORDER BY enrollments DESC,c.course_id"""
            elif kind == "movers":
                sql = """SELECT u.city,toYear(p.paid_at) AS year,sum(p.net_vnd) AS net_vnd
                    FROM gold.fact_payments p JOIN gold.dim_course c USING(course_sk)
                    JOIN gold.dim_user u USING(user_sk)
                    WHERE toDate(p.paid_at) BETWEEN toDate(%(start)s) AND toDate(%(end)s)
                      AND c.category IN %(categories)s AND u.user_id IN (
                        SELECT user_id FROM gold.dim_user GROUP BY user_id HAVING uniqExact(city)>1)
                    GROUP BY u.city,year ORDER BY u.city,year"""
            else:
                raise ValueError("Unknown drilldown")
            result = ch.query(sql, parameters=params)
            columns = (
                ["course_id", "title", "enrollments", "correlation"]
                if kind == "study"
                else ["city", "year", "net_vnd"]
            )
            return pd.DataFrame(result.result_rows, columns=columns)
