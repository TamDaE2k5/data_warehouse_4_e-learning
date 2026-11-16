"""Source-backed analytics workspace for the local learning warehouse."""

import json
import logging
import os
import subprocess
import sys
from datetime import date
from html import escape
from itertools import count
from contextlib import contextmanager

import pandas as pd
import streamlit as st
from demo.charts import (
    short_number,
    revenue_chart,
    ranked_chart,
    enrollment_chart,
    payment_mix,
    revenue_bridge,
    METHOD_LABELS,
)
from demo.data import options, snapshot, operations_snapshot, detail
from demo.presentation import (
    metrics,
    card_title,
    empty,
    progress,
    ratio,
    percent,
    change,
    icon,
    csv_bytes,
)
from etl.common import ROOT

PAGES = ["Overview", "Finance", "Learning", "Quizzes", "Markets", "Quality & operations"]
PAGE_DESCRIPTIONS = {
    "Overview": "Follow revenue, enrollment, and completion in one published snapshot.",
    "Finance": "Understand the path from original transaction value to net revenue.",
    "Learning": "Track enrollment cohorts and their current completion outcomes.",
    "Quizzes": "Compare assessment outcomes with attempt volume and study context.",
    "Markets": "Explore instructors and learner locations at payment time.",
    "Quality & operations": "Inspect publication health, quarantined records, and pipeline history.",
}
_cards = count()


@contextmanager
def card():
    with st.container(border=True, key=f"card_{next(_cards)}"):
        st.markdown('<span class="card-anchor"></span>', unsafe_allow_html=True)
        yield


st.set_page_config(
    page_title="Learning Warehouse · Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="auto",
)
st.markdown(
    "<style>" + (ROOT / "demo/styles.css").read_text(encoding="utf-8") + "</style>",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=60, show_spinner="Loading analytics…")
def load_data(run_id, start, end, categories):
    return snapshot(run_id, start, end, categories)


@st.cache_data(ttl=60, show_spinner="Loading detailed analysis…")
def load_detail(run_id, kind, start, end, categories):
    return detail(run_id, kind, start, end, categories)


@st.cache_data(ttl=10, show_spinner="Loading warehouse status…")
def load_operations(run_id):
    return operations_snapshot(run_id)


def plot(figure, key):
    st.plotly_chart(
        figure,
        use_container_width=True,
        key=key,
        config={
            "displaylogo": False,
            "responsive": True,
            "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
        },
    )


def table(frame, key, renames=None):
    display = frame.rename(columns=renames or {})
    st.dataframe(
        display.style.format(precision=2, na_rep="—"),
        use_container_width=True,
        hide_index=True,
        height=min(380, 38 + len(display) * 35),
    )
    filename = f"{key}_{start.isoformat()}_{end.isoformat()}.csv"
    st.download_button(
        "Download CSV",
        csv_bytes(display),
        file_name=filename,
        mime="text/csv",
        key="export_" + key,
    )


def reset_filters():
    st.session_state["period"] = str(bounds[1].year)
    st.session_state["categories"] = categories
    st.session_state["custom_dates"] = (date(2022, 1, 1), date(2024, 12, 31))


with st.sidebar:
    st.markdown(
        '<div class="brand"><div class="brand-mark">'
        + icon("chart")
        + '</div><div><div class="brand-name">Learning Warehouse</div><div class="brand-sub">ANALYTICS WORKSPACE</div></div></div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="nav-caption">EXPLORE</div>', unsafe_allow_html=True)
    page = st.radio("Navigation", PAGES, key="nav", label_visibility="collapsed")
    st.divider()
    st.markdown('<div class="nav-caption">DATA</div>', unsafe_allow_html=True)
    if st.button("↻  Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

try:
    manifest, categories, bounds = options()
except Exception:
    logging.exception("Dashboard publication discovery failed")
    st.title("The warehouse is not ready yet")
    st.info(
        "No published snapshot is available, or a pipeline is publishing. Refresh after the pipeline finishes."
    )
    st.stop()

with st.sidebar:
    published_at = pd.to_datetime(manifest["finished_at"], utc=True).strftime(
        "%d %b %Y · %H:%M UTC"
    )
    st.markdown(
        '<div class="sidebar-meta">Published snapshot<br><strong>'
        + published_at
        + "</strong><br><br>"
        + f"{sum(manifest['tables'].values()):,}"
        + " source rows in snapshot<br>Event calendar <strong>2022 – 2024</strong></div>",
        unsafe_allow_html=True,
    )
    st.divider()
    st.markdown(
        '<div class="sidebar-meta">Synthetic source data<br>Currency VND · Time zone UTC</div>',
        unsafe_allow_html=True,
    )

st.markdown(
    '<div class="page-top"><div class="breadcrumb">Analytics <span style="padding:0 7px">/</span><b>'
    + escape(page)
    + '</b></div><div class="publish-tag"><span class="status-dot"></span>Validated · '
    + str(manifest["quality_checks"])
    + " checks</div></div>",
    unsafe_allow_html=True,
)
st.title(page)
st.caption(PAGE_DESCRIPTIONS[page])

if "period" not in st.session_state:
    st.session_state["period"] = str(bounds[1].year)
if "categories" not in st.session_state:
    st.session_state["categories"] = categories
with st.container(key="filterbar"):
    st.markdown('<span class="filter-anchor"></span>', unsafe_allow_html=True)
    first, second, third = st.columns([1.25, 1.45, 0.65])
    with first:
        periods = [str(year) for year in range(bounds[1].year, 2021, -1)] + [
            "All time · 2022–2024",
            "Custom dates",
        ]
        period = st.selectbox(
            "Reporting period", periods, key="period", disabled=page == "Quality & operations"
        )
    with second:
        selected = st.session_state["categories"]
        label = (
            "All categories"
            if len(selected) == len(categories)
            else (selected[0] if len(selected) == 1 else f"{len(selected)} categories")
        )
        st.caption("Course categories")
        with st.popover(label, use_container_width=True, disabled=page == "Quality & operations"):
            st.multiselect("Course categories", categories, key="categories")
    with third:
        st.button("Reset", on_click=reset_filters, use_container_width=True)
    if period == "Custom dates" and page != "Quality & operations":
        chosen = st.date_input(
            "Start date – end date",
            min_value=date(2022, 1, 1),
            max_value=date(2024, 12, 31),
            value=(date(2022, 1, 1), date(2024, 12, 31)),
            key="custom_dates",
        )
        if len(chosen) != 2:
            st.info("Select both a start date and an end date.")
            st.stop()
        start, end = chosen
    elif period.startswith("All time") or page == "Quality & operations":
        start, end = date(2022, 1, 1), date(2024, 12, 31)
    else:
        start, end = date(int(period), 1, 1), date(int(period), 12, 31)
        if int(period) == bounds[1].year:
            end = min(end, bounds[1])
selected_categories = st.session_state["categories"]
if page == "Quality & operations":
    start, end, selected_categories = date(2022, 1, 1), date(2024, 12, 31), categories
if not selected_categories:
    empty("Select at least one course category to start exploring.")
    st.stop()
if page == "Quality & operations":
    st.markdown(
        '<div class="scope-caption">Warehouse-wide status · Analytical filters do not apply to this page</div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        '<div class="scope-caption">'
        + f"{start:%d %b %Y} — {end:%d %b %Y} · {len(selected_categories)} categories"
        + "</div>",
        unsafe_allow_html=True,
    )

try:
    data = (
        load_operations(manifest["run_id"])
        if page == "Quality & operations"
        else load_data(manifest["run_id"], start, end, selected_categories)
    )
except Exception:
    logging.exception("Dashboard snapshot failed")
    st.error(
        "This snapshot could not be loaded. Refresh after the pipeline finishes, or check service health."
    )
    st.stop()

prior = None
if page != "Quality & operations":
    monthly = data["finance"].copy()
    funnel = data["funnel"].iloc[0]
    net = int(monthly.net_vnd.sum())
    gross = int(monthly.gross_vnd.sum())
    payments = int(monthly.payments.sum())
    completion = ratio(funnel.completed, funnel.enrolled)
    prior = data["baseline"]
    prior_rate = ratio(prior["completed"], prior["enrolled"]) if prior else None
    comparison_note = (
        "vs. same period in " + str(prior["start"].year) if prior else "Selected period"
    )


def headline():
    metrics(
        [
            dict(
                label="Net revenue",
                value=short_number(net, 2) + " VND",
                icon="money",
                delta=change(net, prior["net_vnd"]) if prior else None,
                note=comparison_note,
            ),
            dict(
                label="Payments",
                value=f"{payments:,}",
                icon="chart",
                delta=change(payments, prior["payments"]) if prior else None,
                note=comparison_note,
            ),
            dict(
                label="Enrollments",
                value=f"{int(funnel.enrolled):,}",
                icon="users",
                delta=change(funnel.enrolled, prior["enrolled"]) if prior else None,
                note=comparison_note,
            ),
            dict(
                label="Completion rate",
                value=percent(completion),
                icon="check",
                delta=change(completion, prior_rate, points=True)
                if completion is not None and prior_rate is not None
                else None,
                note="Enrollment cohort",
            ),
        ]
    )


if page == "Overview":
    headline()
    left, right = st.columns([1.65, 1], gap="medium")
    with left, card():
        title, control = st.columns([2.5, 1])
        with title:
            card_title("Revenue trend", "Net revenue and original transaction value")
        with control:
            grain = st.selectbox(
                "Time grouping",
                ["Month", "Quarter"],
                key="revenue_grain",
                label_visibility="collapsed",
            )
        if monthly.empty:
            empty()
        else:
            plot(revenue_chart(monthly, grain), "overview_revenue")
    with right, card():
        card_title(
            "Revenue by category",
            "Net revenue · VND",
            tag=f"{len(data['revenue_categories'])} categories",
        )
        if data["revenue_categories"].empty:
            empty()
        else:
            plot(
                ranked_chart(data["revenue_categories"], "net_vnd", "category", height=310),
                "overview_categories",
            )
    left, right = st.columns([1.65, 1], gap="medium")
    with left, card():
        card_title("Monthly enrollments", "Enrollments started in the selected period")
        if data["enrollment_trend"].empty:
            empty()
        else:
            plot(enrollment_chart(data["enrollment_trend"]), "overview_enrollments")
    with right, card():
        card_title("Payment methods", "Share of transaction count")
        if data["methods"].empty:
            empty()
        else:
            plot(payment_mix(data["methods"]), "overview_methods")

elif page == "Finance":
    metrics(
        [
            dict(
                label="Net revenue",
                value=short_number(net, 2) + " VND",
                icon="money",
                delta=change(net, prior["net_vnd"]) if prior else None,
                note=comparison_note,
            ),
            dict(
                label="Original transaction value",
                value=short_number(gross, 2) + " VND",
                icon="chart",
            ),
            dict(
                label="Discount rate",
                value=percent(ratio(monthly.discount_vnd.sum(), gross)),
                icon="money",
                note="Discounts / original value",
            ),
            dict(
                label="Refund rate",
                value=percent(ratio(monthly.refunds.sum(), payments)),
                icon="check",
                note="Refunded transactions / payments",
            ),
        ]
    )
    with card():
        card_title("Revenue over time", "VND · By payment date")
        if monthly.empty:
            empty()
        else:
            plot(revenue_chart(monthly), "finance_revenue")
    left, right = st.columns([1.55, 1], gap="medium")
    with left, card():
        card_title(
            "From original value to net revenue",
            "Refunds are attributed to the original payment date",
        )
        if monthly.empty:
            empty()
        else:
            plot(revenue_bridge(monthly), "finance_bridge")
    with right, card():
        card_title("Revenue by payment method", "Net revenue · VND")
        methods = data["methods"].copy()
        methods["method"] = methods.method_name.map(lambda name: METHOD_LABELS.get(name, name))
        if methods.empty:
            empty()
        else:
            plot(ranked_chart(methods, "net_vnd", "method", height=280), "finance_methods")
    with st.expander("Revenue details and export"):
        table(
            monthly,
            "revenue",
            {
                "month": "Month",
                "net_vnd": "Net revenue (VND)",
                "gross_vnd": "Original value (VND)",
                "discount_vnd": "Discounts (VND)",
                "refund_vnd": "Refunds (VND)",
                "payments": "Transactions",
                "refunds": "Refunded payments",
            },
        )

elif page == "Learning":
    metrics(
        [
            dict(
                label="Enrollments",
                value=f"{int(funnel.enrolled):,}",
                icon="users",
            ),
            dict(
                label="Started learning",
                value=percent(ratio(funnel.started, funnel.enrolled)),
                icon="book",
                note="At least one completed lesson",
            ),
            dict(
                label="Course completion",
                value=percent(completion),
                icon="check",
                note=f"{int(funnel.completed):,} completed enrollments",
            ),
            dict(
                label="Time to complete",
                value=f"{funnel.avg_days:.1f}" + " days" if pd.notna(funnel.avg_days) else "—",
                icon="clock",
                note="Average among completed enrollments",
            ),
        ]
    )
    st.caption(
        "The cohort includes enrollments started in the selected period. Completion reflects the current published snapshot, including completions after that period."
    )
    left, right = st.columns([1, 1], gap="medium")
    with left, card():
        card_title("Learning progression", "Enrollments at each stage")
        progress(
            [
                ("Enrollments", int(funnel.enrolled)),
                ("Started learning", int(funnel.started)),
                ("Completed", int(funnel.completed)),
            ]
        )
    with right, card():
        card_title("Completion by category", "Completed / enrolled · %")
        if data["courses"].empty:
            empty()
        else:
            plot(
                ranked_chart(
                    data["courses"].sort_values("completion_pct", ascending=False),
                    "completion_pct",
                    "category",
                    "percent",
                    height=255,
                ),
                "learning_completion",
            )
    with card():
        card_title("Enrollments by monthly cohort", "Bars show enrollment count")
        if data["enrollment_trend"].empty:
            empty()
        else:
            plot(enrollment_chart(data["enrollment_trend"]), "learning_trend")
    with st.expander("Learning outcomes"):
        table(
            data["courses"],
            "completions",
            {
                "category": "Category",
                "enrollments": "Enrollments",
                "completions": "Completed",
                "completion_pct": "Completed (%)",
            },
        )

elif page == "Quizzes":
    quiz = data["quiz"].copy()
    attempts = int(quiz.attempts.sum())
    metrics(
        [
            dict(label="Quiz attempts", value=f"{attempts:,}", icon="book"),
            dict(
                label="Pass rate",
                value=percent(ratio(quiz.passed.sum(), attempts)),
                icon="check",
                note="At least 70% correct",
            ),
            dict(
                label="Correct answer rate",
                value=percent(ratio(quiz.correct_answers.sum(), quiz.question_count.sum())),
                icon="chart",
                note="Total correct answers / total questions",
            ),
            dict(label="Quizzes with attempts", value=f"{len(quiz):,}", icon="users"),
        ]
    )
    with card():
        card_title(
            "Quizzes with the highest failure rate", "Ranked by failure rate, then attempt volume"
        )
        first, second, third = st.columns([1, 1, 1.5])
        with first:
            top = st.selectbox("Quizzes to show", [5, 10, 15], index=1, key="quiz_top")
        with second:
            maximum = max(1, int(quiz.attempts.max())) if not quiz.empty else 1
            st.session_state["quiz_min"] = min(
                max(1, int(st.session_state.get("quiz_min", 1))), maximum
            )
            minimum = st.number_input(
                "Minimum attempts",
                min_value=1,
                max_value=maximum,
                key="quiz_min",
            )
        with third:
            search = st.text_input(
                "Search quizzes", placeholder="Quiz ID or title", key="quiz_search"
            )
        filtered = quiz.loc[quiz.attempts >= minimum].copy()
        if search:
            filtered = filtered.loc[
                filtered.quiz_id.astype(str).str.contains(search, regex=False)
                | filtered.quiz_title.str.contains(search, case=False, regex=False)
            ]
        filtered["fail_pct"] = 100 - filtered.pass_pct
        difficult = (
            filtered.sort_values(
                ["fail_pct", "attempts", "quiz_id"], ascending=[False, False, True]
            )
            .head(top)
            .copy()
        )
        difficult["label"] = difficult.quiz_id.map(lambda value: f"Quiz {value}")
        if difficult.empty:
            empty("No quizzes match these filters.")
        else:
            plot(ranked_chart(difficult, "fail_pct", "label", "percent"), "exam_ranking")
    with st.expander("Quiz details and export"):
        table(
            filtered,
            "quizzes",
            {
                "quiz_id": "Quiz ID",
                "quiz_title": "Quiz title",
                "category": "Category",
                "attempts": "Attempts",
                "pass_pct": "Pass (%)",
                "fail_pct": "Fail (%)",
                "avg_score_pct": "Average score (%)",
                "duration_score_corr": "Duration–score correlation",
                "passed": "Passed attempts",
                "correct_answers": "Correct answers",
                "question_count": "Questions",
            },
        )
    with st.expander("Study time and quiz scores"):
        st.caption(
            "Includes enrollments with both completed lessons and quiz attempts in this period. Correlation does not establish causation; it is undefined when scores or durations do not vary."
        )
        if st.checkbox("Load correlation analysis", key="study_detail"):
            try:
                study = load_detail(manifest["run_id"], "study", start, end, selected_categories)
                table(
                    study,
                    "study_score_correlation",
                    {
                        "course_id": "Course ID",
                        "title": "Course",
                        "enrollments": "Enrollments",
                        "correlation": "Correlation",
                    },
                )
            except Exception:
                logging.exception("Study drilldown failed")
                st.error(
                    "The detailed analysis could not be loaded. Refresh the snapshot and try again."
                )

elif page == "Markets":
    cities = data["cities"]
    metrics(
        [
            dict(label="Net revenue", value=short_number(net, 2) + " VND", icon="money"),
            dict(label="Payments", value=f"{payments:,}", icon="chart"),
            dict(label="Cities with payments", value=str(len(cities)), icon="users"),
            dict(
                label="Leading city share",
                value=percent(ratio(cities.net_vnd.iloc[0], net)) if not cities.empty else "—",
                icon="chart",
                note=str(cities.city.iloc[0]) if not cities.empty else "No payments",
            ),
        ]
    )
    left, right = st.columns([1.3, 1], gap="medium")
    with left, card():
        card_title("Instructors by revenue", "Net revenue · VND")
        limit = st.selectbox("Instructors to show", [5, 10, 15], index=1, key="instructor_limit")
        instructors = data["instructors"].head(limit).copy()
        instructors["label"] = (
            instructors.apply(
                lambda row: f"{row.full_name} · #{row.instructor_id}"
                if instructors.full_name.duplicated(keep=False).loc[row.name]
                else row.full_name,
                axis=1,
            )
            if not instructors.empty
            else pd.Series(dtype=str)
        )
        if instructors.empty:
            empty()
        else:
            plot(ranked_chart(instructors, "net_vnd", "label"), "market_instructors")
    with right, card():
        card_title("Revenue by location", "Learner city at payment time")
        if cities.empty:
            empty()
        else:
            plot(ranked_chart(cities, "net_vnd", "city", height=365), "market_cities")
    with st.expander("Instructor and location details"):
        table(
            data["instructors"],
            "instructors",
            {
                "instructor_id": "Instructor ID",
                "full_name": "Instructor",
                "net_vnd": "Net revenue (VND)",
                "payments": "Transactions",
            },
        )
        table(
            cities,
            "locations",
            {"city": "City", "net_vnd": "Net revenue (VND)", "payments": "Transactions"},
        )
    with st.expander("Learner relocation and annual revenue"):
        st.caption(
            "Location follows learner history at payment time. Year-over-year change requires two complete consecutive calendar years and nonzero prior-year revenue."
        )
        if st.checkbox("Load relocation history", key="mover_detail"):
            try:
                movers = load_detail(
                    manifest["run_id"], "movers", start, end, selected_categories
                ).copy()
                previous_year = movers.groupby("city")["year"].shift()
                previous_revenue = movers.groupby("city")["net_vnd"].shift()
                movers["yoy_pct"] = [
                    (row.net_vnd / previous_revenue[index] - 1) * 100
                    if previous_year[index] == int(row.year) - 1
                    and previous_revenue[index] != 0
                    and start <= date(int(row.year) - 1, 1, 1)
                    and end >= date(int(row.year), 12, 31)
                    else None
                    for index, row in movers.iterrows()
                ]
                table(
                    movers,
                    "learner_relocations",
                    {
                        "city": "City",
                        "year": "Year",
                        "net_vnd": "Net revenue (VND)",
                        "yoy_pct": "YoY (%)",
                    },
                )
            except Exception:
                logging.exception("Mover drilldown failed")
                st.error(
                    "The location history could not be loaded. Refresh the snapshot and try again."
                )

else:
    errors = data["quarantine"]
    total_errors = int(errors["Total"].sum()) if not errors.empty else 0
    open_errors = int(errors["Open"].sum()) if not errors.empty else 0
    metrics(
        [
            dict(
                label="Quality checks",
                value=str(manifest["quality_checks"]),
                icon="check",
                note="Published Gold snapshot",
            ),
            dict(
                label="Open issues",
                value=str(open_errors),
                icon="book",
                note="Quarantined records",
            ),
            dict(
                label="Resolved issues",
                value=str(total_errors - open_errors),
                icon="check",
                note="Replaced by valid source data",
            ),
            dict(
                label="Latest published load",
                value=f"{manifest['seconds']:.2f}" + " s",
                icon="clock",
                note="No-change incremental" if manifest.get("gold_reused") else manifest["mode"],
            ),
        ]
    )
    quality_tab, ops_tab = st.tabs(["Data quality", "Run history"])
    with quality_tab, card():
        card_title("Snapshot status", tag="Validated")
        st.markdown(
            '<div class="quality-summary"><b>'
            + (
                "No open data issues"
                if not open_errors
                else str(open_errors) + " records require attention"
            )
            + "</b><p>Data types, references, learner history, amounts, and aggregate totals are checked before publication.</p></div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "Last validated "
            + pd.to_datetime(manifest["quality_checked_at"], utc=True).strftime(
                "%d %b %Y %H:%M UTC"
            )
            + ". No-change runs retain the quality results of the previous Gold snapshot."
        )
        if not errors.empty:
            table(errors, "quarantine_summary")
            with st.expander("Recently detected issues"):
                table(data["recent_errors"], "recent_issues")
    with ops_tab, card():
        card_title("Pipeline runs", "10 most recent runs")
        table(data["runs"], "pipeline_runs")
        with st.expander("Publication details"):
            st.json(
                {
                    key: manifest.get(key)
                    for key in [
                        "run_id",
                        "mode",
                        "started_at",
                        "finished_at",
                        "seconds",
                        "peak_rss_mib",
                        "fact_actions",
                        "extracted",
                        "rejected",
                    ]
                }
            )
        st.caption(
            "Incremental loading processes changes across the entire source, independently of analytical filters."
        )
        if os.getenv("DW_DASHBOARD_ALLOW_PIPELINE", "0") != "1":
            st.caption(
                "Read-only dashboard. Run pipeline commands from the CLI, or explicitly enable "
                "the local operator control with DW_DASHBOARD_ALLOW_PIPELINE=1."
            )
        elif st.button("Run incremental load", type="primary"):
            try:
                with st.spinner("Loading, validating, and publishing…"):
                    result = subprocess.run(
                        [sys.executable, "cli.py", "pipeline", "--mode", "incremental"],
                        cwd=ROOT,
                        capture_output=True,
                        text=True,
                        timeout=1200,
                    )
                if result.returncode:
                    st.error(
                        "The pipeline did not complete. Review the run history and service logs before retrying."
                    )
                else:
                    st.cache_data.clear()
                    st.rerun()
            except subprocess.TimeoutExpired:
                st.error(
                    "The pipeline exceeded the waiting time. Check its recorded status before starting another run."
                )

with st.expander("Data sources and metric definitions"):
    st.caption(
        "Source: ClickHouse Gold. Synthetic data for learning and demonstration. Analytical queries share the same published snapshot and filters."
    )
    st.markdown(
        "**Net revenue** = original amount − discounts − refunds, attributed to the original payment date. **Completion rate** = completed / enrolled in the selected enrollment cohort. **Passing score** = at least 70% of questions."
    )
    st.caption(
        "The latest year ends on the last source enrollment date. Choose All time or Custom dates to include learning events after that date."
    )
    if prior:
        st.caption(
            f"Comparison period: {prior['start']:%d %b %Y} — {prior['end']:%d %b %Y}. Rate changes use percentage points. Leap years can have different day counts."
        )
    else:
        st.caption(
            "Comparisons are unavailable when the selected range has no matching prior period in the 2022–2024 calendar."
        )
    source = dict(
        run_id=manifest["run_id"],
        published_at=manifest["finished_at"],
        start=str(start),
        end=str(end),
        categories=selected_categories,
        comparison=prior,
        synthetic=True,
        timezone="UTC",
        currency="VND",
    )
    st.download_button(
        "Download source metadata",
        json.dumps(source, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
        file_name="source_metadata.json",
        mime="application/json",
    )
st.markdown(
    '<div class="footer"><span>Learning Warehouse · Synthetic data</span><span>Snapshot '
    + escape(manifest["run_id"][:8])
    + " · VND / UTC</span></div>",
    unsafe_allow_html=True,
)
