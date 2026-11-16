"""CPU quotas must remain usable by integer-valued ClickHouse query settings."""

import unittest
from unittest.mock import patch

from etl.config import ch_connect


class ConnectionConfigurationTests(unittest.TestCase):
    def test_fractional_cpu_quota_connects_with_a_bounded_worker_count(self):
        for quota, workers in [("1.5", 1), ("0.5", 1), ("2.9", 2), ("4.0", 4)]:
            with (
                self.subTest(quota=quota),
                patch.dict("os.environ", {"DW_CPUS": quota, "CH_PASSWORD": "test-only"}),
                patch("etl.config.clickhouse_connect.get_client") as client,
            ):
                ch_connect()
                self.assertEqual(client.call_args.kwargs["settings"]["max_threads"], workers)

    def test_nonfinite_nonpositive_and_invalid_cpu_values_fail_before_connection(self):
        for quota in ["nan", "inf", "-inf", "0", "-1", "not-a-number"]:
            with (
                self.subTest(quota=quota),
                patch.dict("os.environ", {"DW_CPUS": quota, "CH_PASSWORD": "test-only"}),
                patch("etl.config.clickhouse_connect.get_client") as client,
            ):
                with self.assertRaisesRegex(ValueError, "finite and positive"):
                    ch_connect()
                client.assert_not_called()

    def test_default_cpu_setting_remains_four_workers(self):
        with (
            patch.dict("os.environ", {"CH_PASSWORD": "test-only"}, clear=True),
            patch("etl.config.clickhouse_connect.get_client") as client,
        ):
            ch_connect()
            self.assertEqual(client.call_args.kwargs["settings"]["max_threads"], 4)
