"""Add up to 10,000 late-arriving synthetic quiz attempts using the source writer."""

from argparse import ArgumentParser
from contextlib import closing
from etl.common import pg_connect

parser = ArgumentParser()
parser.add_argument("--attempt-number", type=int, choices=range(99, 120), default=99)
args = parser.parse_args()

with closing(pg_connect()) as pg, pg, pg.cursor() as cur:
    cur.execute(
        """WITH sample AS (
        SELECT DISTINCT ON (enrollment_id) * FROM oltp.quiz_attempts
        WHERE attempt_number < 99 ORDER BY enrollment_id,attempt_number
        LIMIT 10000
    ), max_id AS (SELECT max(attempt_id) AS n FROM oltp.quiz_attempts)
    INSERT INTO oltp.quiz_attempts (attempt_id,enrollment_id,user_id,course_id,quiz_id,
        attempt_number,attempted_at,correct_count,total_questions,time_spent_seconds)
    SELECT n+row_number() OVER (ORDER BY enrollment_id),enrollment_id,user_id,course_id,quiz_id,
        %s,attempted_at,correct_count,total_questions,time_spent_seconds
    FROM sample CROSS JOIN max_id ON CONFLICT (enrollment_id,quiz_id,attempt_number) DO NOTHING""",
        (args.attempt_number,),
    )
    print(f"Inserted {cur.rowcount} synthetic attempts")
