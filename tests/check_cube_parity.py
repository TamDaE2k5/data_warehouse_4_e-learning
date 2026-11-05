"""
==================================================================================
KIỂM TRA HỒI QUY: TÍNH TƯƠNG ĐỒNG CỦA MỆNH ĐỀ CUBE (CUBE PARITY CHECK)
==================================================================================
Mục tiêu:
  - Kiểm tra đối chuẩn chuyên sâu (Targeted Regression Check):
    Ngữ nghĩa của giá trị NULL ở các cấp tổng con (Subtotals) trong mệnh đề CUBE
    bắt buộc phải trùng khớp hoàn hảo giữa PostgreSQL 16 và ClickHouse Server.
  - Sử dụng hàm chuẩn hóa `canonical()` để so sánh đối ứng hai tập dữ liệu trả về.
  - Xác nhận sự hiện diện của dòng Tổng toàn cục (Grand Total) với cả hai nhãn đều là NULL.
==================================================================================
"""

from benchmark.queries import QUERIES
from benchmark.run_benchmark import canonical
from etl.common import ch_connect, pg_connect


def check_cube():
    """Thực thi kiểm tra tính tương đương của truy vấn CUBE trên ClickHouse và PostgreSQL."""
    ch = ch_connect()
    try:
        with pg_connect() as pg, pg.cursor() as cur:
            sql = QUERIES["Q5_cube"]

            # Thực thi trên PostgreSQL Mirror
            cur.execute(sql.format(db="benchmark"))
            pg_rows = cur.fetchall()

            # Thực thi trên ClickHouse Gold với thiết lập group_by_use_nulls=1
            ch_rows = ch.query(
                sql.format(db="gold"),
                settings={"group_by_use_nulls": 1},
            ).result_rows

            # 1. So sánh đối ứng hai tập kết quả (phải trùng khớp 100%)
            assert canonical(pg_rows) == canonical(ch_rows), (
                f"Lệch kết quả CUBE:\nPG: {canonical(pg_rows)}\nCH: {canonical(ch_rows)}"
            )

            # 2. Phải có đúng 1 dòng Tổng toàn cục (Grand Total) với Year và Category đều là NULL
            grand_totals = sum(r[0] is None and r[1] is None for r in ch_rows)
            assert grand_totals == 1, f"Kỳ vọng 1 dòng Grand Total nhưng thấy {grand_totals}"

            print(
                f"✓ Kiểm tra CUBE Parity THÀNH CÔNG: {len(ch_rows)} dòng (Bao gồm đầy đủ các nhãn NULL tổng con)!",
                flush=True,
            )
    finally:
        ch.close()


if __name__ == "__main__":
    check_cube()
