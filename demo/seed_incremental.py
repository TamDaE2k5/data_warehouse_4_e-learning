"""
==================================================================================
KỊCH BẢN GIẢ LẬP SỰ KIỆN ĐẾN MUỘN (LATE-ARRIVING FACTS SEEDER)
==================================================================================
Mục tiêu:
  - Sinh 10.000 lượt làm bài thi trắc nghiệm (quiz attempts) đến muộn (Late-Arriving Facts)
    vào hệ thống tác nghiệp OLTP (PostgreSQL) bằng tài khoản tác nghiệp `learning`.
  - Giúp kiểm chứng khả năng nạp tăng dần (Incremental CDC / Watermark) của Pipeline:
      1. Pipeline chỉ quét và nạp đúng 10.000 bản ghi mới (delta).
      2. Không nạp lại hoặc làm trùng lặp các phân vùng dữ liệu cũ (Partition Idempotency).
      3. ClickHouse phân loại hành động là `appended` cho `fact_quiz_attempts`.

Nguyên lý thiết kế:
  - Sử dụng số thứ tự lần thử (attempt_number) đặc thù trong dải 99–119 để dễ dàng
    nhận diện và cô lập các bản ghi kiểm thử với dữ liệu nghiệp vụ thật (1–3 lần).
  - Tận dụng `ON CONFLICT DO NOTHING` trên khoá phức hợp (enrollment_id, quiz_id, attempt_number)
    đảm bảo tính bất biến và an toàn khi chạy lại nhiều lần.
==================================================================================
"""

from argparse import ArgumentParser
from contextlib import closing
from etl.common import pg_connect


def seed_incremental(attempt_number: int = 99) -> int:
    """Chèn 10.000 bản ghi thi trắc nghiệm giả lập đến muộn vào bảng oltp.quiz_attempts.

    Args:
        attempt_number: Số thứ tự lần thi giả lập (mặc định: 99, dải hợp lệ 99-119).

    Returns:
        Số lượng bản ghi thực tế được chèn vào cơ sở dữ liệu OLTP.
    """
    with closing(pg_connect()) as pg, pg, pg.cursor() as cur:
        # Sử dụng CTE:
        #   - sample: Lấy 10.000 lượt ghi danh phân biệt (DISTINCT ON enrollment_id)
        #     có số lần thi trước đó < 99.
        #   - max_id: Xác định attempt_id lớn nhất hiện tại để sinh khóa chính liên tục.
        cur.execute(
            """
            WITH sample AS (
                SELECT DISTINCT ON (enrollment_id) *
                FROM oltp.quiz_attempts
                WHERE attempt_number < 99
                ORDER BY enrollment_id, attempt_number
                LIMIT 10000
            ),
            max_id AS (
                SELECT COALESCE(MAX(attempt_id), 0) AS n FROM oltp.quiz_attempts
            )
            INSERT INTO oltp.quiz_attempts (
                attempt_id,
                enrollment_id,
                user_id,
                course_id,
                quiz_id,
                attempt_number,
                attempted_at,
                correct_count,
                total_questions,
                time_spent_seconds
            )
            SELECT
                n + ROW_NUMBER() OVER (ORDER BY enrollment_id),
                enrollment_id,
                user_id,
                course_id,
                quiz_id,
                %s,
                attempted_at,
                correct_count,
                total_questions,
                time_spent_seconds
            FROM sample
            CROSS JOIN max_id
            ON CONFLICT (enrollment_id, quiz_id, attempt_number) DO NOTHING
            """,
            (attempt_number,),
        )
        rowcount = cur.rowcount
        print(f"[SEED-INCREMENTAL] Đã chèn thành công {rowcount} lượt thi giả lập đến muộn (attempt_number={attempt_number}).")
        return rowcount


if __name__ == "__main__":
    parser = ArgumentParser(description="Tạo 10.000 lượt thi đến muộn trong OLTP phục vụ kiểm thử tăng dần.")
    parser.add_argument(
        "--attempt-number",
        type=int,
        choices=range(99, 120),
        default=99,
        help="Số thứ tự lần thi giả lập (mặc định: 99, dải: 99-119)",
    )
    args = parser.parse_args()
    seed_incremental(args.attempt_number)
