import unittest
from datetime import datetime, timezone
import pandas as pd
from etl.pipeline import clean_frame
from benchmark.run_benchmark import row_bytes, canonical
from etl.common import ch_connect


class TransformTests(unittest.TestCase):
    def test_cleaning_preserves_raw_and_identity(self):
        raw = pd.DataFrame(
            {
                "user_id": [7],
                "email": ["  STUDENT7@EXAMPLE.INVALID  "],
                "country": [" vn "],
                "city": [" Ha Noi "],
            }
        )
        clean = clean_frame(raw)
        self.assertEqual(
            clean.iloc[0].to_dict(),
            dict(user_id=7, email="student7@example.invalid", country="VN", city="Ha Noi"),
        )
        self.assertEqual(raw.email.iloc[0], "  STUDENT7@EXAMPLE.INVALID  ")

    def test_hash_utc_and_null(self):
        self.assertEqual(
            row_bytes((datetime(2024, 2, 29), None)),
            row_bytes((datetime(2024, 2, 29, tzinfo=timezone.utc), None)),
        )
        self.assertNotEqual(row_bytes((None,)), row_bytes(("",)))

    def test_parity_preserves_duplicates(self):
        self.assertNotEqual(canonical([(1,), (1,)]), canonical([(1,)]))
        self.assertEqual(canonical([(None,), (1,)]), canonical([(1,), (None,)]))


class WarehouseIntegrationTests(unittest.TestCase):
    integration = True

    @classmethod
    def setUpClass(cls):
        cls.ch = ch_connect()

    @classmethod
    def tearDownClass(cls):
        cls.ch.close()

    def test_scd_exact_boundary(self):
        # Three probes around the effective-time boundary, independent of generated event times.
        rows = self.ch.query("""SELECT e.t,u.user_sk FROM
        (SELECT toInt64(5) AS user_id,arrayJoin([
          toDateTime('2023-06-30 23:59:59','UTC'),toDateTime('2023-07-01 00:00:00','UTC'),
          toDateTime('2023-07-01 00:00:01','UTC')]) AS t) e
        ASOF LEFT JOIN gold.dim_user u ON e.user_id=u.user_id AND e.t>=u.valid_from ORDER BY e.t""").result_rows
        self.assertEqual([r[1] for r in rows], [10000051, 10000052, 10000052])

    def test_unknown_date_only_uncompleted(self):
        n = self.ch.query("""SELECT count() FROM gold.fact_enrollments
                WHERE (completed_date_sk=0) != (completed_at IS NULL)""").first_row[0]
        self.assertEqual(n, 0)

    def test_cube_subtotal_null_labels(self):
        from benchmark.queries import QUERIES

        rows = self.ch.query(
            QUERIES["Q5_cube"].format(db="gold"), settings={"group_by_use_nulls": 1}
        ).result_rows
        self.assertEqual(sum(r[0] is None and r[1] is None for r in rows), 1)
        self.assertEqual(sum(r[1] is None for r in rows), 4)
        self.assertFalse(any(r[1] == "" for r in rows))

    def test_drill_across_preserves_totals(self):
        import re
        from etl.common import ROOT

        text = (ROOT / "analytics/queries.sql").read_text()
        query = re.search(
            r"-- name: R07_revenue_enrollment_drill_across\n(.*?);", text, re.S
        ).group(1)
        rows = self.ch.query(query).result_rows
        actual = (sum(r[3] for r in rows), sum(r[4] for r in rows))
        expected = (
            self.ch.query("SELECT sum(net_vnd) FROM gold.fact_payments").first_row[0],
            self.ch.query("SELECT count() FROM gold.fact_enrollments").first_row[0],
        )
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
