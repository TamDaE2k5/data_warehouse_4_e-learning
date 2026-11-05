"""
==================================================================================
MODULE TRÍCH XUẤT DỮ LIỆU NGUỒN THEO LUỒNG (EXTRACT ENGINE & SERVER-SIDE STREAMING)
==================================================================================
Mục tiêu:
  - Trích xuất dữ liệu từ cơ sở dữ liệu tác nghiệp (`learning_oltp`) sang môi trường ETL
    với hiệu năng cao nhất và tiêu thụ bộ nhớ RAM thấp nhất.
  - Sử dụng con trỏ máy chủ có tên (Server-Side Named Cursor):
      + Thay vì kéo toàn bộ hàng triệu dòng về bộ nhớ đệm Python gây tràn RAM (OOM Crash),
        con trỏ có tên yêu cầu PostgreSQL duy trì cổng truyền phát (Portal) trên server
        và chỉ gửi về máy khách từng khối 50.000 dòng (`fetchmany(50000)`).
      + Nhờ đó, lượng RAM tiêu thụ của Python luôn được khống chế ổn định < 200MB.
  - Hỗ trợ cơ chế trích xuất tăng dần (Incremental Extraction) thông qua toán tử so sánh
    bộ đôi (Row Constructor): `WHERE (updated_at, key) > (%s, %s)`.
  - Tuyệt đối tuân thủ nguyên tắc chọn cột tường minh (`SELECT col1, col2...`),
    không dùng `SELECT *` để phòng tránh lỗi ngầm khi schema nguồn thay đổi thứ tự cột.
==================================================================================
"""


def batches(source, table: str, columns: list, key: str, watermark: tuple):
    """
    Generator trích xuất dữ liệu từ một bảng nguồn theo từng lô 50.000 dòng.

    Tham số:
      - source: Kết nối chỉ đọc (Read-Only) tới cơ sở dữ liệu tác nghiệp `learning_oltp`.
      - table (str): Tên bảng cần trích xuất (ví dụ: 'payments', 'enrollments').
      - columns (list): Danh sách tên các cột cần đọc theo thứ tự tường minh.
      - key (str): Tên cột khóa chính của bảng (ví dụ: 'payment_id', 'user_id').
      - watermark (tuple | None): Mốc phân thủy `(last_processed_time, last_processed_id)`
                                  của lần nạp trước. Nếu là `None`, trích xuất toàn bộ (Full Load).

    Trả về:
      - Generator sinh ra từng khối dữ liệu (`list of tuples`) với kích thước tối đa 50.000 dòng/lô.
    """
    # Khởi tạo Server-Side Named Cursor bằng cách truyền tham số `name`:
    # Tên con trỏ là duy nhất cho mỗi bảng: `extract_{table}`
    with source.cursor(name=f"extract_{table}") as reader:
        # Nếu có mốc phân thủy (chế độ tăng dần), áp dụng mệnh đề WHERE lọc bộ đôi.
        # Cú pháp so sánh Row Constructor của SQL: (a, b) > (val_a, val_b)
        # tương đương logic: (a > val_a) OR (a = val_a AND b > val_b).
        condition = f"WHERE (updated_at, {key}) > (%s, %s)" if watermark else ""

        # Câu lệnh SQL chọn đích danh danh sách cột và sắp xếp toàn phần đơn điệu
        sql = (
            f"SELECT {','.join(columns)} FROM oltp.{table} "
            f"{condition} "
            f"ORDER BY updated_at, {key}"
        )

        # Thực thi truy vấn trên server PostgreSQL
        reader.execute(sql, watermark or ())

        # Đọc dữ liệu theo từng khối kích thước 50.000 dòng truyền qua mạng
        while rows := reader.fetchmany(50000):
            # Trả về từng khối dữ liệu cho tiến trình xử lý tiếp theo (Generator Pattern)
            yield rows
