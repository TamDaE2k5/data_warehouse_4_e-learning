"""Offline dashboard contracts; install demo requirements to run these tests."""

import csv
import io
import os
import unittest
from contextlib import nullcontext
from datetime import date, datetime
from unittest.mock import patch, MagicMock
from uuid import uuid4

try:
    import pandas as pd
    from streamlit.testing.v1 import AppTest
    from demo.charts import (
        short_number,
        tick_indices,
        ranked_chart,
        revenue_chart,
        enrollment_chart,
    )
    from demo.presentation import csv_bytes, ratio, change, percent
    from demo.data import validate_scope, snapshot, detail, operations_snapshot, comparison_period
except ModuleNotFoundError as error:
    raise unittest.SkipTest("Dashboard dependencies are not installed in this image") from error


class PresentationContracts(unittest.TestCase):
    def test_empty_and_nonfinite_metrics_are_not_displayed_as_real_rates(self):
        self.assertIsNone(ratio(2, 0))
        self.assertIsNone(ratio(1, float("nan")))
        self.assertIsNone(ratio(float("inf"), 2))
        self.assertEqual(ratio(0, 5), 0)
        self.assertEqual(percent(None), "—")
        self.assertEqual(short_number(float("nan")), "—")
        self.assertEqual(short_number(1234567890, 2), "1.23 B")
        self.assertEqual(change(45, 40, points=True), "+5.0 pp")
        self.assertIsNone(change(45, 0))

    def test_csv_neutralizes_formulas_without_changing_numeric_amounts(self):
        values = ["=1+1", "+SUM(A1)", "-formula", "@command", "\t=hidden", "Normal title"]
        frame = pd.DataFrame({"title": values, "amount": [-12, 0, 1, 2, 3, 4]})
        output = csv_bytes(frame)
        self.assertTrue(output.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.DictReader(io.StringIO(output.decode("utf-8-sig"))))
        self.assertEqual(rows[0]["title"], "'=1+1")
        self.assertEqual(rows[4]["title"], "'\t=hidden")
        self.assertEqual(rows[5]["title"], "Normal title")
        self.assertEqual(rows[0]["amount"], "-12")
        self.assertEqual(frame.title.iloc[0], "=1+1")

    def test_truncated_ranking_labels_do_not_merge_distinct_categories(self):
        prefix = "A course with the same very long prefix "
        figure = ranked_chart(
            pd.DataFrame({"name": [prefix + "one", prefix + "two"], "count": [4, 3]}),
            "count",
            "name",
            "count",
        )
        self.assertEqual(len(set(figure.data[0].y)), 2)
        self.assertEqual(figure.data[0].customdata[0][0], prefix + "one")
        self.assertEqual(figure.data[0].customdata[1][0], prefix + "two")

    def test_empty_and_signed_figures_remain_usable(self):
        self.assertEqual(tick_indices(0), [])
        self.assertEqual(len(revenue_chart(pd.DataFrame()).data), 0)
        self.assertEqual(len(enrollment_chart(pd.DataFrame()).data), 0)
        self.assertEqual(len(ranked_chart(pd.DataFrame(), "x", "label").data), 0)
        figure = ranked_chart(
            pd.DataFrame({"label": ["loss", "gain"], "amount": [-4, 2]}), "amount", "label", "count"
        )
        self.assertLess(figure.layout.xaxis.range[0], -4)
        self.assertGreater(figure.layout.xaxis.range[1], 2)

    def test_quarterly_chart_aggregates_values_in_calendar_order(self):
        rows = pd.DataFrame(
            {
                "month": ["2024-04-01", "2024-02-01", "2024-01-01"],
                "gross_vnd": [30, 20, 10],
                "net_vnd": [27, 18, 9],
            }
        )
        figure = revenue_chart(rows, "Quarter")
        self.assertEqual(list(figure.data[0].y), [30 / 1e6, 30 / 1e6])
        self.assertEqual(list(figure.data[1].y), [27 / 1e6, 27 / 1e6])
        self.assertEqual(tick_indices(12), [0, 4, 7, 11])


class QueryContracts(unittest.TestCase):
    def test_invalid_scope_is_rejected_before_database_access(self):
        cases = [
            (date(2024, 2, 1), date(2024, 1, 1), ["Data"]),
            (date(2021, 1, 1), date(2024, 1, 1), ["Data"]),
            (date(2024, 1, 1), date(2024, 1, 2), []),
            (date(2024, 1, 1), date(2024, 1, 2), "Data"),
            (datetime(2024, 1, 1), date(2024, 1, 2), ["Data"]),
        ]
        with patch("demo.data.project_lock") as lock:
            for start, end, categories in cases:
                with self.subTest(start=start, categories=categories):
                    with self.assertRaises(ValueError):
                        snapshot("run", start, end, categories)
            lock.assert_not_called()
        self.assertEqual(
            validate_scope(date(2024, 1, 1), date(2024, 1, 2), ["Data", "Data"]), ("Data",)
        )

    def test_unknown_drilldown_is_rejected_before_database_access(self):
        with patch("demo.data.project_lock") as lock:
            with self.assertRaises(ValueError):
                detail("run", "unknown", date(2024, 1, 1), date(2024, 1, 2), ["Data"])
            lock.assert_not_called()

    def test_operations_reads_control_tables_without_analytical_connection(self):
        pg = MagicMock()
        cursor = pg.cursor.return_value.__enter__.return_value
        cursor.fetchall.side_effect = [[], [], []]
        with (
            patch("demo.data.project_lock", return_value=nullcontext()),
            patch("demo.data.require_success", return_value={"run_id": "run"}),
            patch("demo.data.staging_connect", return_value=pg),
            patch("demo.data.ch_connect") as ch,
        ):
            result = operations_snapshot("run")
            ch.assert_not_called()
        self.assertEqual(set(result), {"manifest", "quarantine", "recent_errors", "runs"})
        self.assertEqual(
            list(result["quarantine"].columns), ["Table", "Error code", "Total", "Open"]
        )
        self.assertEqual(cursor.execute.call_count, 3)

    def test_stale_operation_snapshot_is_rejected(self):
        with (
            patch("demo.data.project_lock", return_value=nullcontext()),
            patch("demo.data.require_success", return_value={"run_id": "new"}),
            patch("demo.data.staging_connect") as connect,
        ):
            with self.assertRaisesRegex(RuntimeError, "snapshot changed"):
                operations_snapshot("old")
            connect.assert_not_called()

    def test_calendar_comparison_respects_coverage_and_leap_day(self):
        self.assertIsNone(comparison_period(date(2022, 1, 1), date(2022, 12, 31)))
        self.assertIsNone(comparison_period(date(2023, 1, 1), date(2024, 12, 31)))
        self.assertEqual(
            comparison_period(date(2024, 2, 29), date(2024, 2, 29)),
            (date(2023, 2, 28), date(2023, 2, 28)),
        )


class OfflinePageContracts(unittest.TestCase):
    def setUp(self):
        from demo.data import FRAME_COLUMNS

        self.manifest = {
            "run_id": "fixture-" + uuid4().hex,
            "tables": {"enrollments": 10},
            "quality_checks": 123,
            "finished_at": "2026-11-14T00:00:00+00:00",
            "quality_checked_at": "2026-11-14T00:00:00+00:00",
            "seconds": 0.5,
            "gold_reused": True,
            "mode": "incremental",
        }
        self.data = {key: pd.DataFrame(columns=columns) for key, columns in FRAME_COLUMNS.items()}
        self.data["funnel"] = pd.DataFrame(
            [[0, 0, 0, float("nan")]], columns=FRAME_COLUMNS["funnel"]
        )
        self.data["baseline"] = None
        self.ops = {
            "manifest": self.manifest,
            "quarantine": pd.DataFrame(columns=["Table", "Error code", "Total", "Open"]),
            "recent_errors": pd.DataFrame(),
            "runs": pd.DataFrame(),
        }
        self.patches = [
            patch.dict(os.environ, {"DW_DASHBOARD_ALLOW_PIPELINE": "0"}),
            patch(
                "demo.data.options",
                return_value=(
                    self.manifest,
                    ["Data", "Business"],
                    (date(2022, 1, 1), date(2024, 11, 30)),
                ),
            ),
            patch("demo.data.snapshot", return_value=self.data),
            patch("demo.data.operations_snapshot", return_value=self.ops),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

    def test_all_pages_render_empty_without_query_errors(self):
        app = AppTest.from_file("demo/app.py", default_timeout=15).run()
        self.assertFalse(app.exception)
        for page in app.radio[0].options:
            app.radio[0].set_value(page).run()
            self.assertFalse(app.exception, page)
            self.assertFalse(app.error, page)
        self.assertFalse(any(item.label == "Run incremental load" for item in app.button))
        self.assertTrue(any("Read-only dashboard" in item.value for item in app.caption))

    def test_operations_page_works_with_incomplete_custom_date_selection(self):
        app = AppTest.from_file("demo/app.py", default_timeout=15).run()
        next(item for item in app.selectbox if item.key == "period").set_value("Custom dates").run()
        next(item for item in app.date_input if item.key == "custom_dates").set_value(
            (date(2024, 1, 1),)
        ).run()
        app.radio[0].set_value("Quality & operations").run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Read-only dashboard" in item.value for item in app.caption))

    def test_quiz_minimum_remains_valid_after_a_scope_change(self):
        from demo.data import FRAME_COLUMNS

        self.data["quiz"] = pd.DataFrame(
            [[1, "Quiz one", "Data", 100, 50, 60, 50, 600, 1000, 0.2]],
            columns=FRAME_COLUMNS["quiz"],
        )
        # Streamlit only emits the duplicate-default warning once per process.
        # Reset its latch so earlier page tests cannot hide a first-visit warning.
        with patch("streamlit.elements.lib.policies._shown_default_value_warning", False):
            app = AppTest.from_file("demo/app.py", default_timeout=15).run()
            app.radio[0].set_value("Quizzes").run()
            self.assertFalse(app.warning, [item.value for item in app.warning])
            next(item for item in app.number_input if item.key == "quiz_min").set_value(90).run()
            self.assertFalse(app.warning, [item.value for item in app.warning])
            self.data["quiz"].loc[0, "attempts"] = 2
            app.multiselect[0].set_value(["Data"]).run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            self.assertFalse(app.warning, [item.value for item in app.warning])
            self.assertLessEqual(
                next(item for item in app.number_input if item.key == "quiz_min").value, 2
            )

    def test_local_pipeline_control_requires_explicit_opt_in(self):
        with (
            patch.dict(os.environ, {"DW_DASHBOARD_ALLOW_PIPELINE": "1"}),
            patch("subprocess.run") as execute,
        ):
            app = AppTest.from_file("demo/app.py", default_timeout=15).run()
            app.radio[0].set_value("Quality & operations").run()
            self.assertFalse(app.exception)
            self.assertTrue(any(item.label == "Run incremental load" for item in app.button))
            execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
