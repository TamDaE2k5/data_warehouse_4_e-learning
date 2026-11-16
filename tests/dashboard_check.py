"""Dashboard regression checks against rendered Streamlit pages and Silver totals."""

import json
import os
from datetime import date
from contextlib import closing
from streamlit.testing.v1 import AppTest
from demo.data import options, snapshot, comparison_period
from etl.common import save_json, utc_now, staging_connect

checks = []


def check(name, condition=True):
    assert condition, name
    checks.append(name)
    print("PASS " + name, flush=True)


def clean(app):
    assert not app.exception, app.exception
    assert not app.error, app.error


def widget(items, key):
    return next(item for item in items if item.key == key)


app = AppTest.from_file("demo/app.py", default_timeout=90).run()
clean(app)
check("overview renders four interactive charts", len(app.get("plotly_chart")) == 4)
for page in app.radio[0].options:
    app.radio[0].set_value(page).run()
    clean(app)
    if page == "Quality & operations":
        check("operations view contains no analytical plots", len(app.get("plotly_chart")) == 0)
        if os.getenv("DW_DASHBOARD_ALLOW_PIPELINE", "0") != "1":
            check(
                "dashboard pipeline control is disabled without explicit opt-in",
                not any(item.label == "Run incremental load" for item in app.button),
            )
check("all six navigation pages render")
app.radio[0].set_value("Overview").run()
app.multiselect[0].set_value(["Data"]).run()
clean(app)
check("category filter preserves a working overview", len(app.get("plotly_chart")) == 4)
widget(app.selectbox, "revenue_grain").set_value("Quarter").run()
clean(app)
spec = json.loads(app.get("plotly_chart")[0].proto.spec)
check(
    "quarterly view groups the latest year into four calendar quarters",
    len(spec["data"][0]["x"]) == 4,
)
app.radio[0].set_value("Quizzes").run()
clean(app)
spec = json.loads(app.get("plotly_chart")[0].proto.spec)
check(
    "quiz IDs use readable categorical bars",
    spec["layout"]["yaxis"]["type"] == "category" and spec["data"][0]["orientation"] == "h",
)
widget(app.text_input, "quiz_search").set_value("no matching quiz xyz").run()
clean(app)
check("quiz search has an honest empty state", len(app.get("plotly_chart")) == 0)
widget(app.text_input, "quiz_search").set_value("").run()
widget(app.checkbox, "study_detail").check().run()
clean(app)
check("study score drilldown loads without hidden query errors")
app.radio[0].set_value("Markets").run()
widget(app.checkbox, "mover_detail").check().run()
clean(app)
check("historical mover drilldown loads")
app.multiselect[0].set_value([]).run()
clean(app)
check(
    "empty category selection does not imply zero observations",
    any("Select at least one course category" in item.value for item in app.markdown),
)
next(item for item in app.button if item.label == "Reset").click().run()
clean(app)
check(
    "reset restores latest year and all categories",
    widget(app.selectbox, "period").value == "2024" and len(app.multiselect[0].value) == 5,
)
widget(app.selectbox, "period").set_value("Custom dates").run()
widget(app.date_input, "custom_dates").set_value((date(2024, 12, 31), date(2024, 12, 31))).run()
for page in ["Overview", "Finance", "Learning", "Quizzes", "Markets"]:
    app.radio[0].set_value(page).run()
    clean(app)
check("empty custom day renders safely on all analytical pages")
manifest, categories, _ = options()
for selected, start, end in [
    (categories, date(2022, 1, 1), date(2024, 12, 31)),
    (["Data"], date(2024, 1, 1), date(2024, 12, 31)),
]:
    data = snapshot(manifest["run_id"], start, end, selected)
    net = int(data["finance"].net_vnd.sum())
    assert (
        net
        == int(data["revenue_categories"].net_vnd.sum())
        == int(data["methods"].net_vnd.sum())
        == int(data["cities"].net_vnd.sum())
    )
    with closing(staging_connect()) as pg, pg.cursor() as cursor:
        cursor.execute(
            """SELECT coalesce(sum(p.charged_vnd*(1-p.refunded)),0),count(*)
            FROM silver.payments p JOIN silver.courses c USING(course_id)
            WHERE p.paid_at >= %s::date AND p.paid_at < %s::date+interval '1 day'
            AND c.category=ANY(%s)""",
            (start, end, selected),
        )
        pg_net, pg_payments = cursor.fetchone()
        assert net == pg_net and int(data["finance"].payments.sum()) == pg_payments
        cursor.execute(
            """SELECT count(*),count(*) FILTER(WHERE e.completed_at IS NOT NULL)
            FROM silver.enrollments e JOIN silver.courses c USING(course_id)
            WHERE e.enrolled_at >= %s::date AND e.enrolled_at < %s::date+interval '1 day'
            AND c.category=ANY(%s)""",
            (start, end, selected),
        )
        enrolled, completed = cursor.fetchone()
        assert (
            int(data["funnel"].iloc[0].enrolled) == enrolled
            and int(data["funnel"].iloc[0].completed) == completed
        )
        assert int(data["enrollment_trend"].enrollments.sum()) == enrolled
        if data["baseline"]:
            prior = data["baseline"]
            cursor.execute(
                """SELECT coalesce(sum(p.charged_vnd*(1-p.refunded)),0),count(*)
                FROM silver.payments p JOIN silver.courses c USING(course_id)
                WHERE p.paid_at >= %s::date AND p.paid_at < %s::date+interval '1 day'
                AND c.category=ANY(%s)""",
                (prior["start"], prior["end"], selected),
            )
            previous_net, previous_payments = cursor.fetchone()
            assert prior["net_vnd"] == previous_net and prior["payments"] == previous_payments
check("filtered totals reconcile independently to PostgreSQL Silver")
check(
    "calendar comparisons stay inside coverage and preserve leap days",
    comparison_period(date(2022, 1, 1), date(2022, 12, 31)) is None
    and comparison_period(date(2022, 1, 1), date(2024, 12, 31)) is None
    and comparison_period(date(2024, 2, 29), date(2024, 2, 29))
    == (date(2023, 2, 28), date(2023, 2, 28)),
)
result = dict(
    status="success",
    checked_at=utc_now(),
    count=len(checks),
    checks=checks,
    pipeline_run=manifest["run_id"],
    scope="dashboard redesign, live synthetic Gold and independent Silver reconciliation",
)
save_json("dashboard-tests.json", result)
print(result)
