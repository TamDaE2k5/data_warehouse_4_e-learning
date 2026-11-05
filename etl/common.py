"""
==================================================================================
MODULE TIỆN ÍCH DÙNG CHUNG HỆ THỐNG (COMMON UTILITIES & RUNTIME HELPERS)
==================================================================================
Mục tiêu:
  - Cung cấp tập hợp các hàm tiện ích lõi phục vụ xuyên suốt toàn bộ vòng đời ETL:
      1. Quản lý thư mục dự án và thư mục tạo tác phẩm (Artifacts Storage).
      2. Ghi file JSON nguyên tử (Atomic Write via .tmp file) chống hỏng dữ liệu.
      3. Cơ chế Khóa phân tán (PostgreSQL Advisory Lock) ngăn xung đột tiến trình đồng thời.
      4. Cơ chế Cổng kiểm soát (Gatekeeper) đảm bảo chỉ truy cập kho Gold khi pipeline thành công.
      5. Bộ truyền nhận dữ liệu siêu tốc bằng bộ đệm bộ nhớ (In-Memory Streaming Bulk Copy).
==================================================================================
"""

import io
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from etl.config import ch_connect, pg_connect, source_connect, staging_connect


# ==============================================================================
# 1. ĐỊNH TUYẾN ĐƯỜNG DẪN THƯ MỤC HỆ THỐNG (PATHS CONFIGURATION)
# ==============================================================================
# ROOT trỏ về thư mục gốc của dự án (cấp cha của thư mục etl)
ROOT = Path(__file__).resolve().parents[1]

# ARTIFACTS là nơi lưu trữ toàn bộ báo cáo kiểm toán, số liệu thống kê pipeline (JSON, Logs)
ARTIFACTS = ROOT / "artifacts"


# ==============================================================================
# 2. XỬ LÝ DỮ LIỆU JSON & THỜI GIAN CHUẨN QUỐC TẾ (JSON & UTC UTILITIES)
# ==============================================================================
def save_json(name: str, data: dict):
    """
    Ghi dữ liệu JSON an toàn theo nguyên lý nguyên tử (Atomic File Write Pattern).
    
    Nguyên lý hoạt động:
      - Nếu ghi trực tiếp vào file đích và tiến trình đột ngột bị tắt (ngắt điện, OOM-kill),
        file đích sẽ bị rỗng (0 bytes) hoặc đứt gãy JSON, làm hỏng toàn bộ pipeline downstream.
      - Giải pháp: Ghi nội dung hoàn chỉnh ra file tạm thời `.tmp`. Sau khi ghi thành công,
        gọi lệnh `temp.replace(path)` của hệ điều hành. Thao tác rename/replace là một lệnh
        nguyên tử (Atomic) ở cấp độ Kernel filesystem (POSIX/NTFS), đảm bảo file đích luôn ở
        trạng thái hợp lệ (hoặc là dữ liệu cũ, hoặc là dữ liệu mới hoàn chỉnh).
    """
    path = ARTIFACTS / name
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    temp.replace(path)


def utc_now() -> str:
    """Trả về mốc thời gian UTC hiện hành theo định dạng chuẩn ISO 8601 (ví dụ: '2026-11-05T08:30:00+00:00')."""
    return datetime.now(timezone.utc).isoformat()


# ==============================================================================
# 3. NẠP DỮ LIỆU SIÊU TỐC QUA GIAO THỨC COPY (HIGH-PERFORMANCE BULK LOAD)
# ==============================================================================
def copy_frame(conn, table: str, frame):
    """
    Nạp dữ liệu từ Pandas DataFrame trực tiếp vào bảng PostgreSQL bằng lệnh COPY FROM STDIN.

    Nguyên lý tối ưu hóa:
      - Các lệnh `INSERT INTO ... VALUES (...)` hoặc `to_sql()` truyền thống phải gửi từng câu
        lệnh SQL qua mạng, làm PostgreSQL phải phân tích cú pháp (SQL Parse) và lập kế hoạch
        thực thi cho từng dòng, tốc độ chỉ đạt vài nghìn dòng/giây.
      - Hàm `copy_frame` xuất DataFrame ra bộ đệm RAM (`io.StringIO`) dưới định dạng CSV,
        sau đó kích hoạt giao thức sao chép nhị phân trực tiếp (`copy_expert`) của PostgreSQL.
      - Bỏ qua toàn bộ giai đoạn Parse SQL, đạt hiệu năng nạp tới 100.000 - 200.000 dòng/giây.
      - Giá trị rỗng (NaN/None) được biểu diễn bằng ký tự `\\N` tương thích tuyệt đối với PostgreSQL.
    """
    buf = io.StringIO()
    frame.to_csv(
        buf,
        index=False,
        header=False,
        na_rep="\\N",
        date_format="%Y-%m-%d %H:%M:%S.%f",
    )
    buf.seek(0)
    with conn.cursor() as cur:
        cols = ",".join('"' + c + '"' for c in frame.columns)
        cur.copy_expert(
            f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT CSV, NULL '\\N')",
            buf,
        )


# ==============================================================================
# 4. KHÓA PHÂN TÁN CHỐNG XUNG ĐỘT TIẾN TRÌNH (DISTRIBUTED ADVISORY LOCK)
# ==============================================================================
@contextmanager
def project_lock():
    """
    Context Manager quản lý khóa phân tán ứng dụng (PostgreSQL Advisory Lock).

    Nguyên lý:
      - Ngăn chặn nguy cơ Race Condition khi có 2 tiến trình ETL hoặc 2 kỹ sư cùng chạy
        lệnh pipeline đồng thời, gây trùng lặp hoặc xung đột dữ liệu.
      - Sử dụng mã khóa định danh dự án duy nhất: `202210132024`.
      - Hàm `pg_try_advisory_lock` trả về `True` nếu chiếm khóa thành công, trả về `False`
        nếu đã có tiến trình khác giữ khóa (thay vì bị treo/block vô tận).
      - Khi tiến trình kết thúc (hoặc dù có bị crash), phiên kết nối đóng lại thì PostgreSQL
        sẽ tự động giải phóng khóa an toàn, không bao giờ bị Deadlock.
    """
    conn = staging_connect()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(202210132024)")
        if not cur.fetchone()[0]:
            conn.close()
            raise RuntimeError(
                "Another project command is running; retry after it finishes"
            )
    try:
        yield
    finally:
        conn.close()


# ==============================================================================
# 5. CỔNG KIỂM SOÁT TÍNH TOÀN VẸN DỮ LIỆU (DATA QUALITY GATEKEEPER)
# ==============================================================================
def require_success() -> dict:
    """
    Hàm kiểm soát cổng chất lượng (Quality Gatekeeper).
    
    Quy tắc nghiệp vụ:
      - Các lệnh phân tích nghiệp vụ, xuất báo cáo (Reports) và đo lường Benchmark
        tuyệt đối KHÔNG được phép đọc dữ liệu nếu mẻ ETL gần nhất bị lỗi hoặc chưa chạy.
      - Đọc manifest `artifacts/pipeline.json` để xác minh trạng thái `status == 'success'`.
      - Ngăn chặn triệt để tình trạng Business Analyst đưa ra quyết định sai lầm dựa trên
        dữ liệu dở dang hoặc chưa vượt qua 116 bài kiểm toán chất lượng.
    """
    path = ARTIFACTS / "pipeline.json"
    if not path.exists():
        raise RuntimeError("Run pipeline first")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("status") != "success":
        raise RuntimeError(
            "Gold is unavailable: last pipeline did not succeed. Rerun pipeline."
        )
    return manifest
