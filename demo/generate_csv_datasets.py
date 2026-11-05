"""
==================================================================================
MODULE SINH 3 BỘ DATASET KIỂM THỬ KHẢ NĂNG CHỊU LỖI & NẠP TĂNG DẦN (CSV GENERATOR)
==================================================================================
Mục tiêu:
  - Tự động sinh ra 3 bộ Dataset chuẩn dạng CSV lưu trữ tại thư mục `data/`:
      1. `data/batch_1/`: Dữ liệu sạch ban đầu (Safe Baseline).
         Gồm 6 file CSV (users, user_history, enrollments, payments, lesson_completions, quiz_attempts)
         với đúng 100 bản ghi mỗi bảng (ID từ 50.001 - 50.100).
      2. `data/batch_2/`: Dữ liệu tăng dần & Trùng lặp (Incremental & Deduplication).
         Gồm 50 bản ghi thi cử mới + 50 bản ghi trùng lặp ID đợt 1 cập nhật điểm số;
         50 đơn hàng thanh toán trùng lặp cập nhật cờ hoàn tiền (refunded = 1).
      3. `data/batch_3/`: Dữ liệu hỗn loạn & Chịu lỗi (Chaos & Fault-Tolerance).
         Gồm 50 người dùng hợp lệ + 5 người dùng cố ý sai cấu trúc email (thiếu @, có khoảng trắng...)
         để kiểm thử năng lực bắt lỗi của Schema Guard và cách ly vào Quarantine.
  - Sau khi sinh, các file này sẽ được nạp vào PostgreSQL OLTP qua `demo/load_dataset_to_oltp.py`
    để chạy kiểm thử thực tế qua đường ống ETL Pipeline.
==================================================================================
"""

import csv
from pathlib import Path

# Thư mục đích lưu trữ các bộ Dataset: rebuild/data/
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def generate_all_datasets():
    """Hàm khởi tạo và ghi 3 bộ Dataset CSV vào thư mục data/batch_{1,2,3}."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # =========================================================================
    # BATCH 1: DỮ LIỆU SẠCH BAN ĐẦU (100 BẢN GHI CHO CÁC BẢNG)
    # =========================================================================
    b1_dir = DATA_DIR / "batch_1"
    b1_dir.mkdir(parents=True, exist_ok=True)

    # 1.1 users.csv (50001 - 50100)
    with (b1_dir / "users.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "full_name", "email", "city", "country", "created_at"])
        cities = ["Ha Noi", "Ho Chi Minh", "Da Nang", "Can Tho"]
        for i in range(1, 101):
            uid = 50000 + i
            w.writerow([
                uid,
                f"Học viên Mẫu {uid}",
                f"student_{uid}@example.com",
                cities[i % 4],
                "VN",
                "2024-01-01 08:00:00",
            ])

    # 1.2 user_history.csv (600001 - 600100)
    with (b1_dir / "user_history.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "history_id",
            "user_id",
            "full_name",
            "email",
            "city",
            "country",
            "valid_from",
            "valid_to",
        ])
        for i in range(1, 101):
            uid = 50000 + i
            hid = 600000 + i
            w.writerow([
                hid,
                uid,
                f"Học viên Mẫu {uid}",
                f"student_{uid}@example.com",
                cities[i % 4],
                "VN",
                "2024-01-01 08:00:00",
                "2100-01-01 00:00:00",
            ])

    # 1.3 enrollments.csv (500001 - 500100)
    with (b1_dir / "enrollments.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "enrollment_id",
            "user_id",
            "course_id",
            "enrolled_at",
            "completed_at",
            "lessons_completed",
        ])
        for i in range(1, 101):
            eid = 500000 + i
            uid = 50000 + i
            cid = (i % 100) + 1
            w.writerow([eid, uid, cid, "2024-01-10 09:00:00", "", 1])

    # 1.4 payments.csv (500001 - 500100)
    with (b1_dir / "payments.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "payment_id",
            "enrollment_id",
            "user_id",
            "course_id",
            "method_id",
            "transaction_id",
            "paid_at",
            "original_vnd",
            "discount_vnd",
            "charged_vnd",
            "refunded",
        ])
        for i in range(1, 101):
            pid = 500000 + i
            eid = 500000 + i
            uid = 50000 + i
            cid = (i % 100) + 1
            mid = (i % 3) + 1
            w.writerow([
                pid,
                eid,
                uid,
                cid,
                mid,
                f"TXN-BATCH1-{pid}",
                "2024-01-10 09:05:00",
                250000,
                50000,
                200000,
                0,
            ])

    # 1.5 lesson_completions.csv (3600001 - 3600100)
    with (b1_dir / "lesson_completions.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "completion_id",
            "enrollment_id",
            "user_id",
            "course_id",
            "lesson_id",
            "completed_at",
            "time_spent_seconds",
        ])
        for i in range(1, 101):
            cid_comp = 3600000 + i
            eid = 500000 + i
            uid = 50000 + i
            cid = (i % 100) + 1
            lid = (cid - 1) * 10 + 1
            w.writerow([cid_comp, eid, uid, cid, lid, "2024-01-15 14:00:00", 1200])

    # 1.6 quiz_attempts.csv (1010201 - 1010300)
    with (b1_dir / "quiz_attempts.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "attempt_id",
            "enrollment_id",
            "user_id",
            "course_id",
            "quiz_id",
            "attempt_number",
            "attempted_at",
            "correct_count",
            "total_questions",
            "time_spent_seconds",
        ])
        for i in range(1, 101):
            aid = 1010200 + i
            eid = 500000 + i
            uid = 50000 + i
            cid = (i % 100) + 1
            qid = cid
            w.writerow([
                aid,
                eid,
                uid,
                cid,
                qid,
                1,
                "2024-02-10 16:30:00",
                16,
                20,
                650,
            ])

    print("✓ Đã sinh xong Batch 1 (Safe Baseline): 6 bảng x 100 dòng CSV")

    # =========================================================================
    # BATCH 2: DỮ LIỆU TĂNG DẦN & TRÙNG LẶP (50 MỚI + 50 TRÙNG LẶP)
    # =========================================================================
    b2_dir = DATA_DIR / "batch_2"
    b2_dir.mkdir(parents=True, exist_ok=True)

    # 2.1 quiz_attempts.csv (50 dòng mới + 50 dòng trùng ID của Batch 1)
    with (b2_dir / "quiz_attempts.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "attempt_id",
            "enrollment_id",
            "user_id",
            "course_id",
            "quiz_id",
            "attempt_number",
            "attempted_at",
            "correct_count",
            "total_questions",
            "time_spent_seconds",
        ])
        # 50 bản ghi MỚI (lần thi thứ 2 của các enrollment 1..50)
        for i in range(1, 51):
            aid = 1010300 + i
            eid = 500000 + i
            uid = 50000 + i
            cid = (i % 100) + 1
            qid = cid
            w.writerow([
                aid,
                eid,
                uid,
                cid,
                qid,
                2,
                "2024-02-15 10:00:00",
                19,
                20,
                580,
            ])

        # 50 bản ghi TRÙNG LẶP ID của Batch 1 (cố ý gửi lại với điểm số cải thiện)
        for i in range(1, 51):
            aid = 1010200 + i  # TRÙNG ID ĐỢT 1
            eid = 500000 + i
            uid = 50000 + i
            cid = (i % 100) + 1
            qid = cid
            w.writerow([
                aid,
                eid,
                uid,
                cid,
                qid,
                1,
                "2024-02-20 18:00:00",
                20,
                20,
                999,
            ])

    # 2.2 payments.csv (50 dòng trùng lặp cập nhật trạng thái hoàn tiền)
    with (b2_dir / "payments.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "payment_id",
            "enrollment_id",
            "user_id",
            "course_id",
            "method_id",
            "transaction_id",
            "paid_at",
            "original_vnd",
            "discount_vnd",
            "charged_vnd",
            "refunded",
        ])
        for i in range(1, 51):
            pid = 500000 + i  # TRÙNG ID ĐỢT 1
            eid = 500000 + i
            uid = 50000 + i
            cid = (i % 100) + 1
            mid = (i % 3) + 1
            # Đổi trạng thái thành hoàn tiền (refunded = 1)
            w.writerow([
                pid,
                eid,
                uid,
                cid,
                mid,
                f"TXN-BATCH1-{pid}",
                "2024-01-10 09:05:00",
                250000,
                50000,
                200000,
                1,
            ])

    print(
        "✓ Đã sinh xong Batch 2 (Incremental + Duplicates): 50 attempts mới + 50 attempts trùng + 50 payments cập nhật trạng thái"
    )

    # =========================================================================
    # BATCH 3: DỮ LIỆU HỖN LOẠN (CHAOS / FAULT-TOLERANCE)
    # =========================================================================
    b3_dir = DATA_DIR / "batch_3"
    b3_dir.mkdir(parents=True, exist_ok=True)

    # 3.1 users.csv (50 users sạch + 5 users cố tình sai định dạng email)
    with (b3_dir / "users.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "full_name", "email", "city", "country", "created_at"])
        # 50 users SẠCH
        for i in range(1, 51):
            uid = 50100 + i
            w.writerow([
                uid,
                f"Học viên Batch 3 {uid}",
                f"student_{uid}@example.com",
                "Ha Noi",
                "VN",
                "2024-03-01 09:00:00",
            ])

        # 5 users CỐ TÌNH SAI ĐỊNH DẠNG EMAIL
        bad_users = [
            (50191, "User Thiếu @", "user_missing_at_symbol.com", "Ha Noi", "VN"),
            (50192, "User Có Khoảng Trắng", "user with space@domain.com", "Ho Chi Minh", "VN"),
            (50193, "User Thiếu Tên Miền", "bad_user_no_domain@", "Da Nang", "VN"),
            (50194, "User Hai Ký Tự @", "bad@@domain.com", "Can Tho", "VN"),
            (50195, "User Thiếu Phần Đầu", "@onlydomain.com", "Ha Noi", "VN"),
        ]
        for uid, name, email, city, country in bad_users:
            w.writerow([uid, name, email, city, country, "2024-03-01 09:00:00"])

    # 3.2 quiz_attempts.csv (50 attempts sạch đi kèm)
    with (b3_dir / "quiz_attempts.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "attempt_id",
            "enrollment_id",
            "user_id",
            "course_id",
            "quiz_id",
            "attempt_number",
            "attempted_at",
            "correct_count",
            "total_questions",
            "time_spent_seconds",
        ])
        for i in range(51, 101):
            aid = 1010350 + (i - 50)
            eid = 500000 + i
            uid = 50000 + i
            cid = (i % 100) + 1
            qid = cid
            w.writerow([
                aid,
                eid,
                uid,
                cid,
                qid,
                2,
                "2024-03-05 14:00:00",
                17,
                20,
                710,
            ])

    print(
        "✓ Đã sinh xong Batch 3 (Chaos Fault): 50 users sạch + 5 users lỗi email + 50 attempts sạch"
    )


if __name__ == "__main__":
    generate_all_datasets()
