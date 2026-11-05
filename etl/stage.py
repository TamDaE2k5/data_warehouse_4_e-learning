"""
==================================================================================
MODULE ĐIỀU PHỐI VÙNG STAGING & CÁCH LY DỮ LIỆU LỖI (STAGE ENGINE & PIPELINE FORK)
==================================================================================
Mục tiêu:
  - Điều phối toàn bộ quy trình trích xuất từ `learning_oltp` sang kho trung chuyển `dwh_staging`.
  - Kiểm tra Hợp đồng Cấu trúc Tiền kiểm (Pre-Flight Schema Contract Check):
      + Xác minh bảng nguồn và bảng đích khớp nhau về danh mục cột và kiểu dữ liệu trước khi chạy.
  - Kiến trúc phân luồng 2 ngả (Forking Pipeline):
      1. Nhánh dữ liệu sạch: Chuẩn hóa, khử trùng lặp và nạp vào các bảng `silver.*`.
      2. Nhánh dữ liệu lỗi: Gắn mã lỗi định danh, bắt các dòng mồ côi (Orphans) hoặc sai schema
         và cách ly an toàn vào bảng `quarantine.quarantine_records` (Dead-Letter Pattern).
  - Tối ưu hóa hiệu năng cao cấp (High-Performance Engineering):
      + Sử dụng mức cô lập giao dịch `REPEATABLE READ` trên nguồn để đảm bảo tính nhất quán của bản chụp (Snapshot Consistency).
      + Sử dụng bảng tạm trong phiên kết nối (`CREATE TEMP TABLE ... ON COMMIT DROP`).
      + Nạp theo lô lớn bằng lệnh `COPY FROM STDIN` nhị phân, sau đó thực hiện `UPSERT`
        (`ON CONFLICT DO UPDATE`) từ bảng tạm vào bảng Silver chính thức.
==================================================================================
"""

import io
import json
from contextlib import closing
from psycopg2.extras import execute_values
from etl.bootstrap import TABLES
from etl.common import source_connect, staging_connect
from etl.schema_guard import normalize
from etl.extract import batches
from etl.watermark import read_watermark

# Bản đồ các mối quan hệ khóa ngoại (Foreign Keys) giữa các bảng:
# Dùng để phát hiện các bản ghi mồ côi (ví dụ: hóa đơn thanh toán trỏ vào khóa học không tồn tại).
# Cấu trúc mỗi tuple: (cột_khóa_ngoại, bảng_cha_ở_silver, cột_khóa_chính_cha)
REFERENCES = {
    "user_history": [("user_id", "users", "user_id")],
    "courses": [("instructor_id", "instructors", "instructor_id")],
    "lessons": [("course_id", "courses", "course_id")],
    "quizzes": [("course_id", "courses", "course_id")],
    "enrollments": [
        ("user_id", "users", "user_id"),
        ("course_id", "courses", "course_id"),
    ],
    "payments": [
        ("course_id", "courses", "course_id"),
        ("user_id", "users", "user_id"),
        ("enrollment_id", "enrollments", "enrollment_id"),
        ("method_id", "payment_methods", "method_id"),
    ],
    "lesson_completions": [
        ("course_id", "courses", "course_id"),
        ("user_id", "users", "user_id"),
        ("enrollment_id", "enrollments", "enrollment_id"),
        ("lesson_id", "lessons", "lesson_id"),
    ],
    "quiz_attempts": [
        ("course_id", "courses", "course_id"),
        ("user_id", "users", "user_id"),
        ("enrollment_id", "enrollments", "enrollment_id"),
        ("quiz_id", "quizzes", "quiz_id"),
    ],
}


def reject_orphans(writer, table: str, key: str) -> dict:
    """
    Phát hiện và xóa các bản ghi bị mồ côi khóa ngoại (Orphan Records) trong bảng tạm.

    Nguyên lý:
      - Trong hệ thống phân tán hoặc nạp dữ liệu không theo thứ tự, có thể có trường hợp
        giao dịch con (payment) trỏ tới một khóa học (course_id) chưa hề tồn tại trong Silver.
      - Hàm này thực thi câu lệnh SQL DELETE có mệnh đề WHERE NOT EXISTS đối chiếu sang
        bảng cha tương ứng trong schema `silver.*`.
      - Mệnh đề RETURNING thu hồi danh sách khóa chính của các dòng bị loại bỏ để ghi vào Quarantine.

    Trả về:
      - rejected (dict): Ánh xạ `{source_id: (mã_lỗi, lý_do_từ_chối)}`.
    """
    rejected = {}
    for column, parent, parent_key in REFERENCES.get(table, ()):
        # Phân biệt mã lỗi đặc thù: mồ côi khóa học hay mồ côi tham chiếu khác
        code = "ERR_ORPHAN_COURSE" if column == "course_id" else "ERR_ORPHAN_REFERENCE"

        # Xóa các dòng vi phạm khỏi bảng tạm và trả về ID bị xóa
        sql = f"""
            DELETE FROM batch_{table} b
            WHERE NOT EXISTS (
                SELECT 1 FROM silver.{parent} p WHERE p.{parent_key} = b.{column}
            )
            RETURNING b.{key}
        """
        writer.execute(sql)
        for (source_id,) in writer.fetchall():
            rejected[source_id] = (
                code,
                f"Thiếu tham chiếu khóa ngoại: {parent}.{parent_key}",
            )

    return rejected


def csv_field(value) -> str:
    """
    Định dạng một giá trị Python sang trường tương thích với cú pháp CSV của PostgreSQL COPY:
      - Giá trị rỗng (None) chuyển thành ký hiệu '\\N'.
      - Chuỗi ký tự được bọc dấu nháy kép và escape các dấu nháy kép nội tại.
    """
    return "\\N" if value is None else '"' + str(value).replace('"', '""') + '"'


def stage_source(mode: str = "incremental"):
    """
    Hàm nhạc trưởng điều phối toàn bộ chu trình trích xuất và nạp vào tầng Staging/Silver.

    Tham số:
      - mode (str): 'full' (nạp lại toàn bộ từ đầu) hoặc 'incremental' (nạp tăng dần theo Watermark).

    Trả về:
      - counts (dict): Số dòng hiện tại của từng bảng trong schema `silver.*`.
      - marks (list): Danh sách các mốc phân thủy mới của từng bảng.
      - extracted (dict): Số lượng dòng thực tế đã trích xuất từ nguồn trong mẻ này.
      - previous_marks (dict): Mốc phân thủy trước đó của từng bảng.
    """
    counts, marks, extracted, previous_marks = {}, [], {}, {}

    # Mở đồng thời 2 kết nối:
    # 1. src: Kết nối chỉ đọc tới PostgreSQL 'learning_oltp' (tài khoản learning_reader).
    # 2. dst: Kết nối ghi tới PostgreSQL 'dwh_staging' (tài khoản learning_stage).
    with closing(source_connect()) as src, closing(staging_connect()) as dst:
        # Cấu hình mức cô lập REPEATABLE READ: Đảm bảo toàn bộ 11 bảng được đọc từ cùng
        # một bản chụp thời gian nhất quán (Consistent Snapshot), ngăn hiện tượng đọc bóng ma (Phantom Reads).
        src.set_session(readonly=True, isolation_level="REPEATABLE READ")

        # Quản lý giao dịch ghi trên dwh_staging: Tự động commit nếu hoàn tất, rollback nếu lỗi
        with dst, dst.cursor() as writer, src.cursor() as catalog:
            for table in TABLES:
                # --------------------------------------------------------------
                # BƯỚC 1: ĐỌC CẤU TRÚC SCHEMA ĐÍCH TRÊN SILVER
                # --------------------------------------------------------------
                writer.execute(
                    """
                    SELECT column_name, data_type FROM information_schema.columns
                    WHERE table_schema = 'silver' AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (table,),
                )
                cols, types = map(list, zip(*writer.fetchall()))
                key = cols[0]  # Quy ước kiến trúc: Khóa chính luôn là cột đầu tiên của bảng

                # --------------------------------------------------------------
                # BƯỚC 2: KIỂM TRA HỢP ĐỒNG SCHEMA TIỀN KHỞI ĐỘNG (PRE-FLIGHT CONTRACT)
                # --------------------------------------------------------------
                # Đảm bảo bảng nguồn OLTP phải có đủ các cột của Silver, cột updated_at và kiểu khóa chính bigint
                catalog.execute(
                    """
                    SELECT column_name, data_type FROM information_schema.columns
                    WHERE table_schema = 'oltp' AND table_name = %s
                    """,
                    (table,),
                )
                actual = dict(catalog.fetchall())
                if (
                    not set(cols) <= actual.keys()
                    or actual.get("updated_at") != "timestamp with time zone"
                    or actual.get(key) != "bigint"
                ):
                    raise RuntimeError(
                        f"Vi phạm hợp đồng cấu trúc dữ liệu cho bảng oltp.{table}"
                    )

                # --------------------------------------------------------------
                # BƯỚC 3: XỬ LÝ MỐC PHÂN THỦY & CHẾ ĐỘ NẠP (FULL HOẶC INCREMENTAL)
                # --------------------------------------------------------------
                mark = read_watermark(writer, table)
                previous_marks[table] = mark

                if mode == "incremental" and not mark:
                    raise RuntimeError(
                        f"Bảng {table} chưa có mốc Watermark. Hãy chạy chế độ full load trước!"
                    )

                if mode == "full":
                    # Nếu là nạp Full: Xóa sạch dữ liệu cũ trong bảng Silver tương ứng
                    writer.execute(f"TRUNCATE silver.{table}")
                    mark = None

                # --------------------------------------------------------------
                # BƯỚC 4: TẠO BẢNG TẠM TRONG PHIÊN (SESSION TEMP TABLE)
                # --------------------------------------------------------------
                # Bảng tạm batch_{table} có cấu trúc cột giống hệt bảng silver tương ứng,
                # tự động giải phóng khi transaction kết thúc (ON COMMIT DROP).
                names = ",".join(cols)
                writer.execute(
                    f"CREATE TEMP TABLE batch_{table} (LIKE silver.{table}) ON COMMIT DROP"
                )
                extracted[table] = 0

                # --------------------------------------------------------------
                # BƯỚC 5: ĐỌC VÀ LỌC RỬA DỮ LIỆU THEO TỪNG LÔ 50.000 DÒNG
                # --------------------------------------------------------------
                for batch in batches(src, table, cols, key, mark):
                    errors = []
                    buffer = io.StringIO()

                    # Duyệt qua từng dòng dữ liệu thô trong mẻ trích xuất
                    for raw in batch:
                        # Ghi nhận mốc phân thủy tiềm năng mới nhất (cột cuối là updated_at, cột đầu là PK)
                        mark = (raw[-1], raw[0])

                        # Kiểm tra kiểu và quy tắc nghiệp vụ qua Module Schema Guard
                        clean, code, reason = normalize(cols, types, raw)

                        if code:
                            # Nếu phát hiện lỗi: Đưa vào danh sách chờ chuyển sang Quarantine
                            errors.append(
                                (
                                    table,
                                    raw[0],
                                    raw[-1],
                                    code,
                                    reason,
                                    json.dumps(dict(zip(cols, raw)), default=str),
                                )
                            )
                        else:
                            # Nếu bản ghi sạch: Ghi vào bộ đệm RAM CSV chuẩn bị bulk load
                            buffer.write(
                                ",".join(csv_field(value) for value in clean) + "\n"
                            )

                    # ----------------------------------------------------------
                    # BƯỚC 6: BULK LOAD DỮ LIỆU SẠCH VÀO BẢNG TẠM QUA LỆNH COPY
                    # ----------------------------------------------------------
                    buffer.seek(0)
                    writer.copy_expert(
                        f"COPY batch_{table} ({names}) FROM STDIN WITH (FORMAT CSV, NULL '\\N')",
                        buffer,
                    )

                    # ----------------------------------------------------------
                    # BƯỚC 7: KIỂM SOÁT BẢN GHI MỒ CÔI KHÓA NGOẠI
                    # ----------------------------------------------------------
                    rejected = reject_orphans(writer, table, key)
                    if rejected:
                        for raw in batch:
                            if raw[0] in rejected:
                                code, reason = rejected[raw[0]]
                                errors.append(
                                    (
                                        table,
                                        raw[0],
                                        raw[-1],
                                        code,
                                        reason,
                                        json.dumps(dict(zip(cols, raw)), default=str),
                                    )
                                )

                    # ----------------------------------------------------------
                    # BƯỚC 8: NẠP DỮ LIỆU LỖI VÀO BẢNG CÁCH LY QUARANTINE
                    # ----------------------------------------------------------
                    if errors:
                        execute_values(
                            writer,
                            """
                            INSERT INTO quarantine.quarantine_records
                                (table_name, source_id, source_updated_at, error_code, rejection_reason, raw_payload)
                            VALUES %s
                            ON CONFLICT DO NOTHING
                            """,
                            errors,
                        )

                    # ----------------------------------------------------------
                    # BƯỚC 9: HỢP NHẤT DỮ LIỆU SẠCH TỪ BẢNG TẠM VÀO SILVER QUA UPSERT
                    # ----------------------------------------------------------
                    # Kỹ thuật UPSERT: Nếu bản ghi chưa có thì INSERT; nếu đã có thì UPDATE các trường mới
                    updates = ",".join(f"{c} = EXCLUDED.{c}" for c in cols[1:])
                    writer.execute(
                        f"""
                        INSERT INTO silver.{table} SELECT * FROM batch_{table}
                        ON CONFLICT ({key}) DO UPDATE SET {updates}
                        """
                    )

                    # Xóa bảng tạm để chuẩn bị cho lô 50.000 dòng tiếp theo
                    writer.execute(f"TRUNCATE batch_{table}")
                    extracted[table] += len(batch)

                # Cập nhật danh sách mốc phân thủy mới của bảng sau khi xử lý xong toàn bộ các lô
                if mark:
                    marks.append((table, *mark))

                # Đếm tổng số bản ghi sạch hiện có trong bảng Silver
                writer.execute(f"SELECT count(*) FROM silver.{table}")
                counts[table] = writer.fetchone()[0]
                print(
                    f"{table}: Đã trích xuất {extracted[table]:,} dòng / Tổng sạch {counts[table]:,} dòng",
                    flush=True,
                )

    return counts, marks, extracted, previous_marks
