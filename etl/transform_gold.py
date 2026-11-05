"""
==================================================================================
MODULE MÔ HÌNH HÓA ĐA CHIỀU & NẠP VÀO GOLD (TRANSFORM GOLD ENGINE)
==================================================================================
Mục tiêu:
  - Thiết lập Cầu nối bộ nhớ trực tiếp (Zero-Copy Bridge) giữa ClickHouse và PostgreSQL:
      + Sử dụng ClickHouse PostgreSQL Table Engine (`stage_bridge.*`) để đọc trực tiếp
        dữ liệu sạch từ schema `silver` trên PostgreSQL qua mạng Docker nội bộ.
      + Loại bỏ hoàn toàn bước xuất/nhập file trung gian (CSV/Parquet ra ổ cứng),
        tiết kiệm hàng chục GB dung lượng đĩa và đẩy tốc độ truyền nhận lên tối đa.
  - Tối ưu hóa nạp tăng dần siêu tốc (High-Performance Partition Attachment):
      + Thay vì tính toán lại toàn bộ dữ liệu lịch sử nhiều năm, hệ thống sử dụng lệnh:
        `ALTER TABLE gold_build.fact_* ATTACH PARTITION ID ... FROM gold.fact_*`.
      + Thao tác này chỉ hoán đổi con trỏ metadata của các phân vùng tháng cũ (< 50ms),
        sau đó chỉ chạy tính toán mô hình hóa trên tập dữ liệu mới phát sinh (Delta).
  - Tự động khử trùng lặp và gộp phiên bản mới nhất:
      + Đối với bảng `fact_enrollments` (ReplacingMergeTree), tự động kích hoạt
        `OPTIMIZE TABLE ... FINAL` trên các phân vùng bị ảnh hưởng để gộp trạng thái mới.
==================================================================================
"""

import os
from contextlib import closing, contextmanager
from etl.config import staging_connect
from etl.bootstrap import TABLES


@contextmanager
def silver_bridge(ch):
    """
    Context Manager tạo cơ sở dữ liệu cầu nối tạm thời 'stage_bridge' trong ClickHouse.

    Nguyên lý hoạt động:
      - Tận dụng tính năng PostgreSQL Engine của ClickHouse: ClickHouse có thể đọc dữ liệu
        từ PostgreSQL như thể đó là một bảng cục bộ.
      - Toàn bộ 11 bảng trong schema `silver.*` của PostgreSQL `dwh_staging` được ánh xạ
        sang `stage_bridge.{table}`.
      - Dữ liệu được truyền thẳng từ RAM của PostgreSQL sang RAM của ClickHouse qua Socket mạng.
      - Sau khi quá trình biến đổi dữ liệu hoàn tất, khối `finally` tự động xóa sạch database
        cầu nối `stage_bridge` để không để lại tài nguyên rác.
    """
    ch.command("DROP DATABASE IF EXISTS stage_bridge SYNC")
    ch.command("CREATE DATABASE stage_bridge")
    try:
        # Ánh xạ từng bảng trong danh mục sang ClickHouse qua PostgreSQL Engine
        for table in TABLES:
            ch.command(
                f"""
                CREATE TABLE stage_bridge.{table}
                ENGINE = PostgreSQL(%(host)s, 'dwh_staging', %(table)s, %(user)s, %(password)s, 'silver')
                """,
                parameters=dict(
                    host=os.environ["PGHOST"] + ":5432",
                    table=table,
                    user="learning_stage",
                    password=os.environ["PG_STAGE_PASSWORD"],
                ),
            )
        yield
    finally:
        # Dọn dẹp sạch sẽ cơ sở dữ liệu cầu nối sau khi nạp xong dữ liệu vào Gold
        ch.command("DROP DATABASE IF EXISTS stage_bridge SYNC")


def prepare_delta(ch, fact: str, key: str, watermark: tuple) -> str:
    """
    Trích xuất riêng tập dữ liệu mới phát sinh (Delta) của một bảng Fact từ PostgreSQL Staging.

    Tham số:
      - ch: Client kết nối ClickHouse.
      - fact (str): Tên bảng Fact nguồn (ví dụ: 'payments', 'quiz_attempts').
      - key (str): Khóa chính của bảng (ví dụ: 'payment_id').
      - watermark (tuple): Mốc phân thủy `(last_processed_time, last_processed_id)` từ lần nạp trước.

    Trả về:
      - target (str): Tên bảng tạm thời trong ClickHouse chứa riêng các dòng mới.
    """
    target = f"stage_bridge.delta_{fact}"

    # Tạo bảng đệm dạng MergeTree trong ClickHouse có cấu trúc khớp với bảng nguồn
    ch.command(
        f"CREATE TABLE {target} AS stage_bridge.{fact} ENGINE = MergeTree ORDER BY {key}"
    )

    # Đọc từ PostgreSQL chỉ các bản ghi có (updated_at, key) lớn hơn mốc watermark
    with closing(staging_connect()) as pg, pg.cursor(name=f"delta_{fact}") as cursor:
        cursor.execute(
            f"SELECT * FROM silver.{fact} WHERE (updated_at, {key}) > (%s, %s)",
            watermark,
        )
        while rows := cursor.fetchmany(50000):
            ch.insert(target, rows)

    return target


# Bản đồ ánh xạ tên bảng sự kiện Fact và khóa chính tương ứng
EVENT_FACTS = {
    "payments": "payment_id",
    "lesson_completions": "completion_id",
    "quiz_attempts": "attempt_id",
    "enrollments": "enrollment_id",
}


def load_gold_rows(
    ch,
    sql: str,
    mode: str,
    extracted: dict,
    previous_marks: dict,
    reuse_safe: bool,
) -> str:
    """
    Hàm điều phối thông minh việc nạp một bảng vào cơ sở dữ liệu bóng 'gold_build'.

    Chiến lược tối ưu hóa:
      1. Trường hợp Full Rebuild:
         - Khi chạy chế độ `full`, hoặc khi các bảng Chiều danh mục (Dimensions) có sự thay đổi:
           Bắt buộc phải thực thi toàn bộ câu lệnh SQL mô hình hóa để tính toán lại từ đầu.
      2. Trường hợp Incremental Load (Chỉ có sự kiện Fact mới phát sinh):
         - Sử dụng kỹ thuật **Partition Attachment**: Tái sử dụng nguyên vẹn các phân vùng tháng cũ
           từ bảng `gold` chính thức sang `gold_build` mà không tốn 1 chu kỳ CPU tính toán nào.
         - Chỉ chạy câu lệnh SQL mô hình hóa đối với tập dữ liệu mới (Delta) và nạp vào phân vùng mới.
         - Đối với bảng ghi danh (`fact_enrollments`): Kích hoạt `OPTIMIZE FINAL` để gộp phiên bản mới nhất.

    Trả về trạng thái xử lý:
      - 'rebuilt': Tính toán xây dựng mới hoàn toàn.
      - 'reused': Tái sử dụng 100% phân vùng cũ (không có dữ liệu mới).
      - 'appended': Thêm các bản ghi mới vào phân vùng tương ứng (Append-only).
      - 'versioned': Gộp và cập nhật phiên bản mới (SCD/Accumulating Snapshot).
    """
    # Nhận diện xem câu lệnh SQL hiện tại có phải là câu lệnh nạp vào một bảng Fact hay không
    fact = next(
        (
            name
            for name in EVENT_FACTS
            if sql.startswith(f"INSERT INTO gold_build.fact_{name}\n")
        ),
        None,
    )

    # Nếu không phải bảng Fact, hoặc đang chạy chế độ full, hoặc các bảng Dimension master có thay đổi:
    # Bắt buộc phải tính toán lại toàn bộ câu lệnh SQL
    if (
        not fact
        or mode != "incremental"
        or not reuse_safe
        or any(extracted[name] for name in TABLES[1:7])
    ):
        ch.command(sql)
        return "rebuilt"

    table = f"fact_{fact}"
    delta = None
    changed_partitions = []

    # Nếu bảng Fact này có dữ liệu mới phát sinh trong lần chạy này:
    if extracted[fact]:
        key = EVENT_FACTS[fact]
        # Chuẩn bị bảng delta chỉ chứa các dòng mới
        delta = prepare_delta(ch, fact, key, previous_marks[fact])

        # Đối với Fact ghi danh (Accumulating Snapshot Fact):
        if fact == "enrollments":
            # Kiểm tra xem có bản ghi nào bị thay đổi tháng ghi danh hay không
            must_rebuild = ch.query(
                f"""
                SELECT count() FROM gold.{table} g 
                INNER JOIN {delta} s USING(enrollment_id) 
                WHERE toYYYYMM(g.enrolled_at) != toYYYYMM(s.enrolled_at)
                """
            ).first_row[0]
            # Lấy danh sách các phân vùng tháng chịu ảnh hưởng bởi sự thay đổi
            changed_partitions = ch.query(
                f"SELECT DISTINCT toYYYYMM(enrolled_at) FROM {delta}"
            ).result_rows
        else:
            # Đối với Fact giao dịch (Append-only): nếu trùng ID đã có trong Gold thì phải rebuild lại
            must_rebuild = ch.query(
                f"""
                SELECT count() FROM {delta} 
                WHERE {key} IN (SELECT {key} FROM gold.{table})
                """
            ).first_row[0]

        if must_rebuild:
            ch.command(sql)
            return "rebuilt"

    # --------------------------------------------------------------------------
    # KỸ THUẬT GẮN PHÂN VÙNG SIÊU TỐC (PARTITION ATTACHMENT)
    # --------------------------------------------------------------------------
    # Gắn toàn bộ các phân vùng dữ liệu cũ từ bảng gold đang chạy sang gold_build
    # bằng cách sao chép con trỏ metadata (tốc độ < 50ms, không tốn I/O đĩa)
    partitions = ch.query(
        """
        SELECT DISTINCT partition_id FROM system.parts
        WHERE active AND database = 'gold' AND table = %(table)s
        """,
        parameters={"table": table},
    ).result_rows

    for (partition,) in partitions:
        if not partition.isdecimal():
            raise ValueError(f"Phân vùng không hợp lệ: {partition}")
        ch.command(
            f"ALTER TABLE gold_build.{table} ATTACH PARTITION ID '{partition}' FROM gold.{table}"
        )

    # Nếu có dữ liệu mới phát sinh: chèn phần delta vào phân vùng tương ứng
    if delta:
        # Thay thế nguồn đọc từ bảng đầy đủ sang bảng delta
        ch.command(sql.replace(f"FROM stage_bridge.{fact} ", f"FROM {delta} "))

        # Nếu là fact_enrollments: kích hoạt OPTIMIZE FINAL để gộp bản ghi theo ReplacingMergeTree
        for (partition,) in changed_partitions:
            ch.command(
                f"OPTIMIZE TABLE gold_build.{table} PARTITION ID '{int(partition)}' FINAL"
            )

        return "versioned" if fact == "enrollments" else "appended"

    # Nếu không có dòng mới nào phát sinh: tái sử dụng 100% dữ liệu cũ
    return "reused"
