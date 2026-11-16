"""Business rules applied after strict type normalization."""

import re

EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def validate_row(row):
    for column, value in row.items():
        if isinstance(value, str) and not value:
            return None, "ERR_EMPTY_VALUE", f"Required text is empty: {column}"
        if column.endswith("_id") and isinstance(value, int) and value <= 0:
            return None, "ERR_INVALID_DOMAIN", f"Source identifiers must be positive: {column}"
    if "email" in row:
        row["email"] = row["email"].lower()
        if not EMAIL.fullmatch(row["email"]):
            return None, "ERR_INVALID_EMAIL", "Invalid email format"
    if "country" in row:
        row["country"] = row["country"].upper()
    if any(
        row.get(col, 0) < 0 for col in ("price_vnd", "original_vnd", "discount_vnd", "charged_vnd")
    ):
        return None, "ERR_NEGATIVE_AMOUNT", "Amounts must not be negative"
    if "charged_vnd" in row and not {"original_vnd", "discount_vnd"} <= row.keys():
        return None, "ERR_SCHEMA_TYPE_MISMATCH", "Payment amount fields are incomplete"
    if "charged_vnd" in row and row["charged_vnd"] != row["original_vnd"] - row["discount_vnd"]:
        return None, "ERR_INVALID_AMOUNT", "Charged amount does not match price minus discount"
    if (
        row.get("completed_at")
        and row.get("enrolled_at")
        and row["completed_at"] < row["enrolled_at"]
    ):
        return None, "ERR_TIME_INCONSISTENCY", "Completion precedes enrollment"
    if any(row.get(col, 1) <= 0 for col in ("total_questions", "attempt_number", "position")):
        return (
            None,
            "ERR_INVALID_DOMAIN",
            "Question counts, attempt numbers and positions must be positive",
        )
    if any(
        row.get(col, 0) < 0 for col in ("correct_count", "time_spent_seconds", "lessons_completed")
    ):
        return (
            None,
            "ERR_INVALID_DOMAIN",
            "Scores, durations and lesson counts must not be negative",
        )
    if row.get("correct_count", 0) > row.get("total_questions", 2**63 - 1):
        return None, "ERR_INVALID_SCORE", "Correct answers exceed the question count"
    if row.get("refunded", 0) not in (0, 1):
        return None, "ERR_INVALID_DOMAIN", "Refund flag must be 0 or 1"
    if ("valid_from" in row or "valid_to" in row) and not {"valid_from", "valid_to"} <= row.keys():
        return None, "ERR_SCHEMA_TYPE_MISMATCH", "History interval fields are incomplete"
    if "valid_from" in row and row["valid_from"] >= row["valid_to"]:
        return None, "ERR_TIME_INCONSISTENCY", "History intervals must have positive duration"
    return tuple(row.values()), None, None
