"""Content fingerprints used by publication validation and safe Gold reuse."""

CORE_TABLES = (
    "dim_date",
    "dim_user",
    "dim_course",
    "dim_instructor",
    "dim_lesson",
    "dim_quiz",
    "dim_payment_method",
    "fact_enrollments",
    "fact_payments",
    "fact_lesson_completions",
    "fact_quiz_attempts",
)


def fingerprints(ch, database="gold"):
    if database not in ("gold", "gold_build"):
        raise ValueError("Fingerprint database must be gold or gold_build")
    result = {}
    for table in CORE_TABLES:
        columns = [row[0] for row in ch.query(f"DESCRIBE TABLE {database}.{table}").result_rows]
        expression = "cityHash64(toJSONString(tuple(" + ",".join(columns) + ")))"
        row = ch.query(
            f"SELECT count(), sum({expression}), groupBitXor({expression}) FROM {database}.{table}"
        ).first_row
        result[table] = list(row)
    return result
