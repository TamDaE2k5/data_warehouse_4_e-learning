"""
==================================================================================
MODULE TẤM KHIÊN BẢO VỆ SCHEMA & ÉP KIỂU AN TOÀN (SCHEMA GUARD & DEFENSIVE TYPING)
==================================================================================
Mục tiêu:
  - Đóng vai trò là hàng rào phòng ngự đầu tiên (First Line of Defense) của hệ thống ETL,
    ngăn chặn mọi biến dạng dữ liệu hoặc trôi dạt cấu trúc (Schema Drift) từ phía nguồn.
  - Kiểm tra và ép kiểu an toàn (Defensive Type Casting) cho từng bản ghi trước khi nạp:
      + Kiểu số nguyên lớn `bigint`: Ngăn cạm bẫy kiểu boolean trong Python (`bool` là con của `int`),
        kiểm tra biểu thức chính quy (Regex `[+-]?\\d+`), và chặn tràn số nguyên 64-bit có dấu.
      + Kiểu thời gian `timestamp`: Chuyển đổi định dạng ISO 8601, chuẩn hóa múi giờ về UTC.
      + Kiểu chuỗi `str`: Cắt bỏ khoảng trắng thừa ở đầu và cuối (Whitespace Trimming).
  - Phân loại lỗi và cách ly (Fault-Tolerant Segregation):
      + Khi gặp dữ liệu sai kiểu (ví dụ: cột số tiền nhận chuỗi chữ cái hoặc vượt ngưỡng Int64),
        hệ thống không làm sập pipeline (Crash-Proof), mà gắn mã lỗi `ERR_SCHEMA_TYPE_MISMATCH`
        để chuyển dòng đó vào bảng cách ly `quarantine.quarantine_records`.
      + Các dòng dữ liệu chuẩn mực khác trong cùng mẻ vẫn tiếp tục được nạp bình thường vào Silver.
==================================================================================
"""

import re
from datetime import datetime, timezone
from etl.validator import validate_row


def normalize(columns: list, types: list, values: list):
    """
    Chuẩn hóa và kiểm tra tính hợp lệ về kiểu dữ liệu cho một dòng bản ghi nguồn.

    Tham số:
      - columns (list): Danh sách tên các cột (ví dụ: ['payment_id', 'charged_vnd', 'paid_at']).
      - types (list): Danh sách kiểu dữ liệu kỳ vọng từ schema Staging (ví dụ: ['bigint', 'bigint', 'timestamp']).
      - values (list): Danh sách giá trị thực tế trích xuất từ cơ sở dữ liệu nguồn.

    Trả về bộ ba (tuple):
      - clean_values (dict | None): Từ điển dữ liệu đã được chuẩn hóa và làm sạch (None nếu có lỗi).
      - error_code (str | None): Mã lỗi định danh (ví dụ: 'ERR_SCHEMA_TYPE_MISMATCH', None nếu hợp lệ).
      - error_message (str | None): Mô tả chi tiết nguyên nhân gây lỗi (None nếu hợp lệ).
    """
    # Ghép cặp tên cột và giá trị tương ứng thành từ điển để thao tác an toàn theo tên trường
    row = dict(zip(columns, values))

    try:
        for col, kind in zip(columns, types):
            value = row[col]

            # ------------------------------------------------------------------
            # 1. XỬ LÝ ĐẶC THÙ CHO GIÁ TRỊ RỖNG (NULLABLE FIELDS)
            # ------------------------------------------------------------------
            # Cột completed_at được phép mang giá trị NULL đối với học viên chưa học xong khóa
            if value is None and col == "completed_at" and "enrolled_at" in columns:
                continue

            # ------------------------------------------------------------------
            # 2. KIỂM SOÁT KIỂU SỐ NGUYÊN LỚN 64-BIT (BIGINT)
            # ------------------------------------------------------------------
            if kind == "bigint":
                # CẠM BẪY PYTHON: Trong Python, `bool` là lớp con kế thừa từ `int` (True == 1, False == 0).
                # Nếu không chặn `isinstance(value, bool)`, giá trị True/False sẽ bị âm thầm ép thành 1/0.
                if isinstance(value, bool) or (
                    not isinstance(value, int) and not re.fullmatch(r"[+-]?\d+", str(value))
                ):
                    raise ValueError(f"Cột '{col}' không phải số nguyên hợp lệ: {value}")

                row[col] = int(value)

                # Kiểm tra chặn trên và chặn dưới của kiểu số nguyên có dấu 64-bit (-2^63 đến 2^63 - 1)
                if not -(2**63) <= row[col] < 2**63:
                    raise OverflowError(f"Cột '{col}' vượt quá giới hạn Int64: {value}")

            # ------------------------------------------------------------------
            # 3. KIỂM SOÁT KIỂU THỜI GIAN (TIMESTAMP)
            # ------------------------------------------------------------------
            elif kind.startswith("timestamp"):
                # Chuyển đổi chuỗi ISO 8601 sang đối tượng datetime nếu chưa phải kiểu datetime
                parsed = (
                    value
                    if isinstance(value, datetime)
                    else datetime.fromisoformat(str(value))
                )

                # Quy đổi về múi giờ chuẩn quốc tế UTC nếu đối tượng có thông tin timezone
                if parsed.tzinfo is not None:
                    parsed = parsed.astimezone(timezone.utc)

                # Nếu cột trong PostgreSQL là "timestamp without time zone", loại bỏ thông tin tzinfo
                if kind == "timestamp without time zone":
                    parsed = parsed.replace(tzinfo=None)

                row[col] = parsed

            # ------------------------------------------------------------------
            # 4. KIỂM SOÁT VÀ CHUẨN HÓA KIỂU CHUỖI KÝ TỰ (STRING / TEXT)
            # ------------------------------------------------------------------
            elif isinstance(value, str):
                # Loại bỏ khoảng trắng thừa ở hai đầu chuỗi để làm sạch dữ liệu dơ
                row[col] = value.strip()

            else:
                raise ValueError(
                    f"Kiểu dữ liệu không được hỗ trợ hoặc sai định dạng ở cột '{col}': {value}"
                )

    except (ValueError, TypeError, OverflowError) as exc:
        # Khi xảy ra lỗi ép kiểu cấu trúc: Đánh dấu mã lỗi và chuyển dữ liệu sang phân loại lỗi schema
        return None, "ERR_SCHEMA_TYPE_MISMATCH", str(exc)

    # Nếu toàn bộ các trường vượt qua kiểm tra cấu trúc schema,
    # tiếp tục chuyển dữ liệu sang tầng kiểm tra ràng buộc luật nghiệp vụ (Business Rules Validation)
    return validate_row(row)
