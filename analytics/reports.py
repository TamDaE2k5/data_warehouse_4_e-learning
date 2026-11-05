"""
==================================================================================
MODULE XUẤT BÁO CÁO PHÂN TÍCH QUẢN TRỊ (EXECUTIVE REPORTS EXPORT ENGINE)
==================================================================================
Mục tiêu:
  - Đóng vai trò là tầng phân phát dữ liệu (Data Serving Layer) phục vụ các cấp quản lý,
    Ban Giám đốc và các chuyên viên phân tích dữ liệu (Business Analysts).
  - Đọc và thực thi tự động 10 câu truy vấn phân tích nghiệp vụ trong `analytics/queries.sql`.
  - Xuất kết quả phân tích ra các file định dạng CSV chuẩn doanh nghiệp tại `artifacts/reports/`:
      + Sử dụng bảng mã `utf-8-sig` (tự động đính kèm Byte Order Mark - BOM) giúp Microsoft Excel
        hiển thị chuẩn xác tiếng Việt có dấu mà không bao giờ bị lỗi font (Mojibake).
      + Áp dụng cài đặt ClickHouse `settings={'group_by_use_nulls': 1}`: Đảm bảo các dòng tổng con
        (Subtotals) của mệnh đề ROLLUP và CUBE hiển thị giá trị chuẩn `NULL` (thay vì số 0 hoặc chuỗi rỗng).
  - Tích hợp kiểm toán toàn vẹn báo cáo: Tự động tính toán mã băm mật mã học **SHA-256** cho từng file CSV,
    ghi nhận thời gian thực thi và lưu trữ manifest tại `artifacts/reports/manifest.json`.
==================================================================================
"""

import csv
import hashlib
import re
import time
from etl.common import (
    ROOT,
    ARTIFACTS,
    require_success,
    ch_connect,
    save_json,
    utc_now,
)


def reports():
    """
    Hàm điều phối thực thi và xuất 10 báo cáo phân tích quản trị R01–R10.
    Được triệu gọi thông qua lệnh CLI: `python cli.py reports`.
    """
    # --------------------------------------------------------------------------
    # 1. KIỂM SOÁT CỔNG CHẤT LƯỢNG (GATEKEEPER CHECK)
    # --------------------------------------------------------------------------
    # Bắt buộc phiên chạy pipeline gần nhất phải ở trạng thái 'success' (đạt 116 bài kiểm toán).
    # Ngăn chặn tuyệt đối việc xuất báo cáo trên dữ liệu dở dang hoặc chưa kiểm định.
    manifest = require_success()

    out = ARTIFACTS / "reports"
    out.mkdir(parents=True, exist_ok=True)

    # Đọc nội dung file SQL và phân tách thành từng truy vấn độc lập qua thẻ '-- name: Rxx...'
    sql = (ROOT / "analytics/queries.sql").read_text(encoding="utf-8")
    parts = re.split(r"-- name: (\w+)\s*\n", sql)

    metadata = dict(
        pipeline_run=manifest["run_id"],
        generated_at=utc_now(),
        synthetic=True,
        reports={},
    )

    ch = ch_connect()
    try:
        # Vòng lặp duyệt qua từng cặp (tên_báo_cáo, câu_lệnh_sql)
        for i in range(1, len(parts), 2):
            name, query = parts[i], parts[i + 1].strip().rstrip(";")
            tick = time.perf_counter()

            # THIẾT LẬP CLICKHOUSE QUAN TRỌNG:
            # 'group_by_use_nulls': 1 buộc ClickHouse trả về giá trị NULL ở các cấp tổng con của ROLLUP/CUBE
            # theo đúng tiêu chuẩn ANSI SQL, giúp người dùng Excel dễ dàng lọc các dòng tổng hợp.
            result = ch.query(query, settings={"group_by_use_nulls": 1})

            path = out / (name + ".csv")
            # Ghi file với mã hóa utf-8-sig để hỗ trợ hiển thị tiếng Việt hoàn hảo trên Excel
            with path.open("w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(result.column_names)
                writer.writerows(result.result_rows)

            # Tính toán mã băm SHA-256 để niêm phong và đối chiếu toàn vẹn dữ liệu
            sha256_hash = hashlib.sha256(path.read_bytes()).hexdigest()

            metadata["reports"][name] = dict(
                rows=len(result.result_rows),
                seconds=round(time.perf_counter() - tick, 4),
                sha256=sha256_hash,
                source_sql="analytics/queries.sql",
                null_representation="empty CSV cell; subtotal dimensions are NULL for ROLLUP/CUBE",
            )
            print(f"{name}: Đã xuất {len(result.result_rows):,} dòng", flush=True)

        # Lưu trữ manifest báo cáo tổng thể
        save_json("reports/manifest.json", metadata)
        print("Toàn bộ 10 báo cáo phân tích quản trị đã được xuất thành công!", flush=True)

    finally:
        ch.close()
