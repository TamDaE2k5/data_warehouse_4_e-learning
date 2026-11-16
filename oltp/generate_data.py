"""Deterministic Faker master data + vectorized events; COPY in one transaction."""

import time
import numpy as np
import pandas as pd
from faker import Faker
from etl.common import ROOT, copy_frame, pg_connect, save_json, utc_now


def generate(enrollments=500000, seed=2024):
    if enrollments < 100 or enrollments % 100:
        raise ValueError("enrollments must be a positive multiple of 100 (production: 500000)")
    start = time.perf_counter()
    fake = Faker("vi_VN")
    fake.seed_instance(seed)
    rng = np.random.default_rng(seed)
    users_n = min(50000, enrollments // 10)
    courses_n, instructors_n = 1000, 100
    counts = {}
    conn = pg_connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL dw.bulk_seed='on'")
            cur.execute((ROOT / "oltp/schema.sql").read_text())
            cur.execute("SELECT count(*) FROM oltp.enrollments")
            if cur.fetchone()[0]:
                raise RuntimeError(
                    "Source already populated; generation is create-once. Use pipeline to reload DW."
                )

        def load(table, data):
            frame = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
            copy_frame(conn, "oltp." + table, frame)
            counts[table] = counts.get(table, 0) + len(frame)

        ids = np.arange(1, users_n + 1)
        cities = np.array(["Ha Noi", "Da Nang", "Ho Chi Minh", "Can Tho"])
        names = [fake.name() for _ in ids]
        emails = [
            f"  STUDENT{i}@example.invalid  " if i % 17 == 0 else f"student{i}@example.invalid"
            for i in ids
        ]
        original_city = cities[ids % 4]
        changed = ids % 5 == 0
        current_city = np.where(changed, cities[(ids + 1) % 4], original_city)
        load(
            "users",
            dict(
                user_id=ids,
                full_name=names,
                email=emails,
                city=current_city,
                country="VN",
                created_at=pd.Timestamp("2022-01-01"),
            ),
        )
        hist = pd.DataFrame(
            dict(
                history_id=ids * 10 + 1,
                user_id=ids,
                full_name=names,
                email=emails,
                city=original_city,
                country="VN",
                valid_from=pd.Timestamp("2022-01-01"),
                valid_to=pd.to_datetime(np.where(changed, "2023-07-01", "2100-01-01")),
            )
        )
        load("user_history", hist)
        second = hist.loc[changed].copy()
        second["history_id"] += 1
        second["city"] = current_city[changed]
        second["valid_from"] = pd.Timestamp("2023-07-01")
        second["valid_to"] = pd.Timestamp("2100-01-01")
        load("user_history", second)
        load(
            "instructors",
            dict(
                instructor_id=np.arange(1, instructors_n + 1),
                full_name=[fake.name() for _ in range(instructors_n)],
                expertise=["Technology"] * instructors_n,
            ),
        )
        course_ids = np.arange(1, courses_n + 1)
        prices = np.clip(
            rng.lognormal(12.7, 0.6, courses_n).astype("int64") // 1000 * 1000, 50000, 3000000
        )
        prices[course_ids % 10 == 0] = 0
        load(
            "courses",
            dict(
                course_id=course_ids,
                instructor_id=(course_ids - 1) % instructors_n + 1,
                title=[f"{fake.catch_phrase()} {i}" for i in course_ids],
                category=np.array(["Data", "Programming", "Business", "Design", "Language"])[
                    course_ids % 5
                ],
                difficulty=np.array(["beginner", "intermediate", "advanced"])[course_ids % 3],
                price_vnd=prices,
            ),
        )
        lesson_ids = np.arange(1, courses_n * 10 + 1)
        load(
            "lessons",
            dict(
                lesson_id=lesson_ids,
                course_id=(lesson_ids - 1) // 10 + 1,
                title=[f"Lesson {(i - 1) % 10 + 1}" for i in lesson_ids],
                position=(lesson_ids - 1) % 10 + 1,
            ),
        )
        load(
            "quizzes",
            dict(
                quiz_id=course_ids,
                course_id=course_ids,
                title=[f"Course assessment {i}" for i in course_ids],
                total_questions=20,
            ),
        )
        load(
            "payment_methods",
            dict(method_id=[1, 2, 3], method_name=["bank_transfer", "card", "wallet"]),
        )
        completion_id = 1
        for lo in range(1, enrollments + 1, 25000):
            eid = np.arange(lo, min(lo + 25000, enrollments + 1))
            n = len(eid)
            uid = (eid - 1) % users_n + 1
            cid = (((eid - 1) // users_n) * 73 + uid) % courses_n + 1
            enrolled = pd.Timestamp("2022-01-01") + pd.to_timedelta(
                rng.integers(
                    0, (pd.Timestamp("2024-12-01") - pd.Timestamp("2022-01-01")).days * 86400, n
                ),
                unit="s",
            )
            done = (eid - 1 + (eid - 1) // users_n) % 10 < 3
            lesson_count = np.where(done, 10, 6)
            completed = pd.Series(enrolled + pd.Timedelta(days=31)).where(done)
            load(
                "enrollments",
                dict(
                    enrollment_id=eid,
                    user_id=uid,
                    course_id=cid,
                    enrolled_at=enrolled,
                    completed_at=completed,
                    lessons_completed=lesson_count,
                ),
            )
            original = prices[cid - 1]
            discount = original * rng.choice([0, 10, 20, 30], n) // 100
            load(
                "payments",
                dict(
                    payment_id=eid,
                    enrollment_id=eid,
                    user_id=uid,
                    course_id=cid,
                    method_id=rng.integers(1, 4, n),
                    transaction_id=[f"TXN-{i:012d}" for i in eid],
                    paid_at=enrolled + pd.Timedelta(seconds=60),
                    original_vnd=original,
                    discount_vnd=discount,
                    charged_vnd=original - discount,
                    refunded=(rng.random(n) < 0.05).astype(int),
                ),
            )
            idx = np.repeat(np.arange(n), lesson_count)
            positions = np.concatenate([np.arange(1, k + 1) for k in lesson_count])
            m = len(idx)
            load(
                "lesson_completions",
                dict(
                    completion_id=np.arange(completion_id, completion_id + m),
                    enrollment_id=eid[idx],
                    user_id=uid[idx],
                    course_id=cid[idx],
                    lesson_id=(cid[idx] - 1) * 10 + positions,
                    completed_at=enrolled[idx] + pd.to_timedelta(positions * 3, unit="D"),
                    time_spent_seconds=rng.integers(180, 3601, m),
                ),
            )
            completion_id += m
            idx = np.repeat(np.arange(n), 2)
            attempt = np.tile([1, 2], n)
            correct = np.clip(np.rint(rng.normal(13.5, 3.5, n * 2) + (attempt - 1)), 0, 20).astype(
                int
            )
            load(
                "quiz_attempts",
                dict(
                    attempt_id=(np.repeat(eid, 2) - 1) * 2 + attempt,
                    enrollment_id=eid[idx],
                    user_id=uid[idx],
                    course_id=cid[idx],
                    quiz_id=cid[idx],
                    attempt_number=attempt,
                    attempted_at=enrolled[idx] + pd.to_timedelta(attempt * 14, unit="D"),
                    correct_count=correct,
                    total_questions=20,
                    time_spent_seconds=rng.integers(180, 1801, n * 2),
                ),
            )
            print(f"Generated {eid[-1]:,}/{enrollments:,} enrollments", flush=True)
        conn.commit()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("ANALYZE")
        result = dict(
            status="success",
            seed=seed,
            counts=counts,
            total_rows=sum(counts.values()),
            seconds=round(time.perf_counter() - start, 3),
            finished_at=utc_now(),
            synthetic=True,
            period=["2022-01-01", "2024-12-31"],
        )
        save_json("generation.json", result)
        print(result, flush=True)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
