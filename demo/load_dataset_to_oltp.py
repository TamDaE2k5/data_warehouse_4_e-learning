"""
==================================================================================
MODULE NẠP BỘ DỮ LIỆU CSV VÀO SCHEMA OLTP POSTGRESQL (DATASET OLTP LOADER)
==================================================================================
Mục tiêu:
  - Cung cấp công cụ nạp dữ liệu thủ công từ các file CSV (`data/batch_{1,2,3}/`)
    trực tiếp vào cơ sở dữ liệu tác nghiệp `learning_oltp` (schema `oltp`).
  - Đóng vai trò là nguồn phát sinh dữ liệu nghiệp vụ thực tế phục vụ các kịch bản kiểm thử:
      + Batch 1: Nạp 100 bản ghi an toàn thiết lập mốc ban đầu (Initial Baseline).
      + Batch 2: Nạp 50 bản ghi mới + 50 bản ghi trùng lặp ID (để kiểm tra khử trùng lặp).
      + Batch 3: Nạp 50 bản ghi sạch + 5 bản ghi cố ý sai email (để kiểm tra Schema Guard).
  - Tự động kích hoạt cơ chế CDC Watermark:
      + Câu lệnh SQL sử dụng kỹ thuật UPSERT: `ON CONFLICT (pk) DO UPDATE SET ..., updated_at = clock_timestamp()`.
      + Mốc thời gian `updated_at` được nhảy lên thời gian hiện tại, giúp tiến trình ETL
        nhận diện chính xác các bản ghi này để kéo sang Gold ở mẻ nạp tăng dần.

Cách sử dụng dòng lệnh:
  python demo/load_dataset_to_oltp.py --batch 1
  python demo/load_dataset_to_oltp.py --batch 2
  python demo/load_dataset_to_oltp.py --batch 3
==================================================================================
"""

import argparse
import csv
from pathlib import Path
from contextlib import closing
from etl.common import pg_connect

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Thứ tự nạp các bảng để đảm bảo không vi phạm ràng buộc khóa ngoại (Foreign Keys)
TABLE_ORDER = [
    "users",
    "user_history",
    "enrollments",
    "payments",
    "lesson_completions",
    "quiz_attempts",
]

# Danh mục định nghĩa Khóa chính và các cột dữ liệu tương ứng của từng bảng
TABLE_KEYS = {
    "users": (
        "user_id",
        ["full_name", "email", "city", "country", "created_at"],
    ),
    "user_history": (
        "history_id",
        [
            "user_id",
            "full_name",
            "email",
            "city",
            "country",
            "valid_from",
            "valid_to",
        ],
    ),
    "enrollments": (
        "enrollment_id",
        ["user_id", "course_id", "enrolled_at", "completed_at", "lessons_completed"],
    ),
    "payments": (
        "payment_id",
        [
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
        ],
    ),
    "lesson_completions": (
        "completion_id",
        [
            "enrollment_id",
            "user_id",
            "course_id",
            "lesson_id",
            "completed_at",
            "time_spent_seconds",
        ],
    ),
    "quiz_attempts": (
        "attempt_id",
        [
            "enrollment_id",
            "user_id",
            "course_id",
            "quiz_id",
            "attempt_number",
            "attempted_at",
            "correct_count",
            "total_questions",
            "time_spent_seconds",
        ],
    ),
}


def load_batch(batch_num: int):
    """
    Đọc toàn bộ file CSV trong thư mục data/batch_{batch_num} và nạp vào schema oltp.

    Tham số:
      - batch_num (int): Số thứ tự đợt cần nạp (1, 2, hoặc 3).
    """
    batch_dir = DATA_DIR / f"batch_{batch_num}"
    if not batch_dir.exists():
        raise FileNotFoundError(f"Thư mục {batch_dir} không tồn tại!")

    print("\n" + "=" * 80)
    print(
        f"📥 BẮT ĐẦU NẠP DỮ LIỆU TỪ '{batch_dir.name}' VÀO POSTGRESQL (SCHEMA OLTP)"
    )
    print("=" * 80)

    total_loaded = 0
    with closing(pg_connect()) as pg, pg, pg.cursor() as cur:
        for table in TABLE_ORDER:
            csv_path = batch_dir / f"{table}.csv"
            if not csv_path.exists():
                continue

            with csv_path.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            if not rows:
                continue

            pk_col, other_cols = TABLE_KEYS[table]
            all_cols = [pk_col] + other_cols
            cols_str = ", ".join(all_cols)
            placeholders = ", ".join(["%s"] * len(all_cols))
            update_clauses = [f"{c} = EXCLUDED.{c}" for c in other_cols]
            update_str = ", ".join(update_clauses)

            # Cú pháp UPSERT thần thánh:
            # - Nếu ID chưa có: INSERT mới.
            # - Nếu ID đã tồn tại: UPDATE các cột dữ liệu và ép updated_at = clock_timestamp().
            sql = f"""
                INSERT INTO oltp.{table} ({cols_str})
                VALUES ({placeholders})
                ON CONFLICT ({pk_col}) 
                DO UPDATE SET {update_str}, updated_at = clock_timestamp()
            """

            for row in rows:
                # Chuyển đổi chuỗi rỗng thành giá trị NULL trong SQL
                vals = [row[c] if row[c] != "" else None for c in all_cols]
                cur.execute(sql, vals)

            print(
                f"  ✓ [{table}]: Đã nạp thành công {len(rows):>3} dòng từ {csv_path.name}"
            )
            total_loaded += len(rows)

    print("-" * 80)
    print(
        f"🎉 TỔNG KẾT: Đã nạp xong {total_loaded} bản ghi của Batch {batch_num} vào PostgreSQL 'learning_oltp'!"
    )
    print(
        f"👉 Bước tiếp theo: Hãy chạy lệnh ETL Pipeline để xử lý dữ liệu từ PostgreSQL sang Gold:"
    )
    mode = "full" if batch_num == 1 else "incremental"
    print(f"   docker compose run --rm runner python cli.py pipeline --mode {mode}")
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Nạp Dataset CSV vào PostgreSQL OLTP (learning_oltp)"
    )
    parser.add_argument(
        "--batch",
        type=int,
        choices=[1, 2, 3],
        required=True,
        help="Số thứ tự đợt cần nạp (1, 2, hoặc 3)",
    )
    args = parser.parse_args()
    load_batch(args.batch)


if __name__ == "__main__":
    main()
