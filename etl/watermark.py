"""
==================================================================================
MODULE QUẢN LÝ MỐC PHÂN THỦY NẠP TĂNG DẦN (WATERMARK ENGINE & CDC STATE)
==================================================================================
Mục tiêu:
  - Quản lý trạng thái tiến độ nạp dữ liệu (ETL Watermark State) của từng bảng trong
    hệ thống, được lưu trữ tại bảng `staging.etl_watermarks` trong PostgreSQL `dwh_staging`.
  - Hỗ trợ cơ chế trích xuất tăng dần (Incremental Change Data Capture - CDC), chỉ kéo
    những bản ghi mới phát sinh hoặc có sửa đổi kể từ lần nạp thành công gần nhất.
  - Sử dụng cặp mốc kép (Composite High-Water Mark): `(last_processed_time, last_processed_id)`.
      + Tại sao cần cả 2 trường? Nếu chỉ dùng `updated_at`, khi có nhiều bản ghi phát sinh
        trong cùng 1 microsecond, hệ thống có thể bị sót dữ liệu hoặc lặp bản ghi.
        Cặp `(timestamp, id)` tạo ra thứ tự sắp xếp toàn phần (Strict Total Order) tuyệt đối.
  - Nguyên tắc cam kết an toàn (Transactional Safety / Exactly-Once Semantics):
      + Mốc phân thủy CHỈ ĐƯỢC PHÉP CẬP NHẬT (Commit) sau khi toàn bộ chuỗi pipeline hoàn tất,
        vượt qua 116 bài kiểm toán chất lượng và kho Gold đã được hoán đổi an toàn trên ClickHouse.
      + Nếu pipeline gặp sự cố giữa chừng, mốc cũ được giữ nguyên 100%, lần chạy tiếp theo
        sẽ tự động xử lý lại từ vị trí an toàn trước đó mà không làm mất mát dữ liệu.
==================================================================================
"""

from contextlib import closing
from psycopg2.extras import execute_values
from etl.config import staging_connect


def read_watermark(cursor, table: str):
    """
    Đọc mốc phân thủy gần nhất của một bảng từ bảng `staging.etl_watermarks`.

    Tham số:
      - cursor: Con trỏ cơ sở dữ liệu kết nối tới PostgreSQL `dwh_staging`.
      - table (str): Tên bảng cần lấy mốc (ví dụ: 'payments', 'enrollments').

    Trả về:
      - Tuple `(last_processed_time, last_processed_id)` nếu bảng đã từng được nạp trước đó.
      - `None` nếu đây là lần nạp đầu tiên (Cold Start / Initial Full Load).
    """
    cursor.execute(
        "SELECT last_processed_time, last_processed_id "
        "FROM staging.etl_watermarks "
        "WHERE table_name = %s",
        (table,),
    )
    return cursor.fetchone()


def commit_watermarks(marks: list, run_id: str):
    """
    Ghi nhận và xác nhận (Commit) các mốc phân thủy mới sau khi mẻ pipeline hoàn tất thành công.

    Tham số:
      - marks (list): Danh sách các bộ ba `[(table_name, last_processed_time, last_processed_id), ...]`.
      - run_id (str): Mã định danh duy nhất của lượt chạy ETL hiện tại (UUID) để phục vụ kiểm toán (Auditing).

    Nguyên lý hoạt động:
      - Sử dụng cú pháp `INSERT ... ON CONFLICT (table_name) DO UPDATE` (UPSERT)
        của PostgreSQL thông qua hàm tối ưu `execute_values` của psycopg2.extras.
      - Toàn bộ danh sách mốc được cập nhật trong 1 Transaction duy nhất trên cơ sở dữ liệu `dwh_staging`.
    """
    if not marks:
        return

    # Kết nối tới dwh_staging bằng tài khoản công nhân learning_stage
    with closing(staging_connect()) as pg, pg, pg.cursor() as cur:
        sql = """
            INSERT INTO staging.etl_watermarks
                (table_name, last_processed_time, last_processed_id, last_run_id)
            VALUES %s
            ON CONFLICT (table_name) DO UPDATE SET
                last_processed_time = EXCLUDED.last_processed_time,
                last_processed_id = EXCLUDED.last_processed_id,
                last_run_id = EXCLUDED.last_run_id
        """
        # Chuẩn bị danh sách bản ghi chứa thêm mã run_id của phiên chạy
        data = [(table, stamp, key, run_id) for table, stamp, key in marks]
        execute_values(cur, sql, data)
