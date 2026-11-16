import unittest
from etl.schema_guard import normalize


class DomainTests(unittest.TestCase):
    def test_blank_required_text_and_nonpositive_identifiers_are_quarantined(self):
        for column in ["full_name", "title", "city", "transaction_id"]:
            with self.subTest(column=column):
                self.assertEqual(normalize([column], ["text"], ["   "])[1], "ERR_EMPTY_VALUE")
        for value in [0, -1]:
            self.assertEqual(normalize(["user_id"], ["bigint"], [value])[1], "ERR_INVALID_DOMAIN")

    def test_incomplete_cross_field_contracts_are_rejected_without_crashing(self):
        for column, kind, value in [
            ("charged_vnd", "bigint", 100),
            ("valid_from", "timestamp without time zone", "2024-01-01"),
        ]:
            with self.subTest(column=column):
                self.assertEqual(
                    normalize([column], [kind], [value])[1], "ERR_SCHEMA_TYPE_MISMATCH"
                )

    def test_invalid_numeric_domains_are_quarantined(self):
        for column, value in [
            ("total_questions", 0),
            ("attempt_number", 0),
            ("position", 0),
            ("time_spent_seconds", -1),
            ("lessons_completed", -1),
            ("refunded", 2),
        ]:
            with self.subTest(column=column):
                self.assertEqual(normalize([column], ["bigint"], [value])[1], "ERR_INVALID_DOMAIN")

    def test_score_above_denominator_and_empty_history_are_rejected(self):
        self.assertEqual(
            normalize(["correct_count", "total_questions"], ["bigint"] * 2, [21, 20])[1],
            "ERR_INVALID_SCORE",
        )
        self.assertEqual(
            normalize(
                ["valid_from", "valid_to"],
                ["timestamp without time zone"] * 2,
                ["2024-01-01", "2024-01-01"],
            )[1],
            "ERR_TIME_INCONSISTENCY",
        )
