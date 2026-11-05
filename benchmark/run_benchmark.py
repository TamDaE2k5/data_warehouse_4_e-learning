"""
==================================================================================
MODULE THỰC THI BENCHMARK ĐỐI CHUẨN HIỆU NĂNG (BENCHMARK SUITE: CLICKHOUSE VS POSTGRESQL)
==================================================================================
Mục tiêu:
  - Thiết lập môi trường đo kiểm hiệu năng phân tích khách quan, khoa học và chặt chẽ
    giữa Hệ quản trị Cơ sở dữ liệu Cột ClickHouse và Cơ sở dữ liệu Hàng PostgreSQL 16.
  - Phương pháp luận đo kiểm cấp độ phòng thí nghiệm (Scientific Benchmarking Methodology):
      1. Bản sao dữ liệu đối ứng 1:1 (Identical Data Mirroring):
         Nhân bản 100% dữ liệu từ ClickHouse Gold sang schema `benchmark` trên PostgreSQL.
      2. Niêm phong dữ liệu bằng mật mã học (Full-Row SHA-256 Verification):
         Trước khi đo tốc độ, toàn bộ hàng triệu dòng dữ liệu ở cả 2 bên được băm và so khớp
         mã băm SHA-256 từng dòng; nếu lệch dù chỉ 1 byte sẽ dừng ngay lập tức.
      3. Loại bỏ hiện tượng ngẫu nhiên và thiên vị bộ nhớ đệm (Cache Bias Elimination):
         - Thực hiện 2 lần chạy làm nóng bộ nhớ đệm (Warm-up runs).
         - Thực hiện 5 lần chạy đo lặp lại (Measured runs).
         - Đảo ngược thứ tự thực thi xen kẽ (Lần lẻ: PG trước CH sau; Lần chẵn: CH trước PG sau).
         - Vô hiệu hóa bộ nhớ đệm câu lệnh ClickHouse (`use_query_cache: 0`).
      4. Đối soát kết quả truy vấn (Query Result Parity):
         Xác nhận kết quả trả về của 7 câu truy vấn Q1–Q7 từ ClickHouse và PostgreSQL
         phải trùng khớp 100% về số dòng và nội dung dữ liệu.
      5. Thống kê theo trung vị (Median / P50):
         Sử dụng giá trị Median để loại bỏ các điểm dị biệt (Outliers) do hệ điều hành ngắt nhịp.
==================================================================================
"""

import csv
import hashlib
import json
import platform
import statistics
import time
from datetime import date, datetime
from decimal import Decimal
import pandas as pd

from benchmark.queries import QUERIES
from etl.common import (
    ROOT,
    ARTIFACTS,
    ch_connect,
    staging_connect,
    copy_frame,
    require_success,
    save_json,
    utc_now,
)


def canonical(rows):
    """
    Chuẩn hóa kết quả truy vấn thành danh sách các chuỗi JSON đã sắp xếp để so sánh đối chiếu:
      - Chuyển đổi kiểu Decimal thành int hoặc chuỗi chuẩn hóa.
      - Chuyển đổi kiểu ngày tháng (Date/Datetime) sang chuỗi chuẩn ISO 8601.
      - Bỏ qua sự khác biệt về thứ tự sắp xếp giá trị NULL giữa hai hệ quản trị.
    """
    def norm(v):
        if isinstance(v, Decimal):
            return int(v) if v == v.to_integral_value() else str(v.normalize())
        if isinstance(v, (date, datetime)):
            return v.isoformat()
        return v

    return sorted(
        json.dumps([norm(v) for v in row], ensure_ascii=False, separators=(",", ":"))
        for row in rows
    )


def digest(rows):
    """Tính mã băm SHA-256 của tập kết quả đã được chuẩn hóa."""
    return hashlib.sha256("\n".join(canonical(rows)).encode()).hexdigest()


def row_bytes(row):
    """
    Chuyển đổi một dòng dữ liệu thành chuỗi byte JSON thống nhất để băm kiểm tra:
    - Loại bỏ thông tin tzinfo để đồng nhất giữa kiểu TIMESTAMP không múi giờ của PG
      và DateTime UTC của ClickHouse.
    """
    normalized = [
        v.replace(tzinfo=None).isoformat()
        if isinstance(v, datetime)
        else v.isoformat()
        if isinstance(v, date)
        else v
        for v in row
    ]
    return (
        json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode()
        + b"\n"
    )


def mirror(ch, pg, tables: list) -> dict:
    """
    Hàm nhân bản cấu trúc và toàn bộ dữ liệu từ ClickHouse Gold sang PostgreSQL Benchmark.

    Tham số:
      - ch: Client kết nối ClickHouse.
      - pg: Kết nối PostgreSQL dwh_staging.
      - tables: Danh sách các bảng cần nhân bản.

    Trả về:
      - counts (dict): Số dòng đã sao chép của từng bảng.
    """
    with pg.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS benchmark")

    counts = {}
    ddl = []

    for table in tables:
        # Đọc cấu trúc bảng từ ClickHouse để sinh câu lệnh DDL tương ứng cho PostgreSQL
        columns = ch.query(f"DESCRIBE TABLE gold.{table}").result_rows
        definitions = []
        for c, t, *_ in columns:
            sql_type = (
                "TIMESTAMP"
                if "DateTime" in t
                else "DATE"
                if t == "Date"
                else "TEXT"
                if "String" in t
                else "BIGINT"
            )
            definitions.append(
                f'"{c}" {sql_type}'
                + ("" if t.startswith("Nullable") else " NOT NULL")
            )

        key = columns[0][0]
        create = (
            f"CREATE TABLE benchmark.{table} ({','.join(definitions)}, PRIMARY KEY ({key}))"
        )
        with pg.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS benchmark.{table}")
            cur.execute(create)
        ddl.append(create + ";")

        # Truyền phát dữ liệu theo từng khối 50.000 dòng từ ClickHouse sang PostgreSQL qua lệnh COPY
        n = 0
        with ch.query_row_block_stream(
            f"SELECT * FROM gold.{table}", settings={"max_block_size": 50000}
        ) as stream:
            for rows in stream:
                copy_frame(
                    pg,
                    "benchmark." + table,
                    pd.DataFrame(rows, columns=[r[0] for r in columns]),
                )
                n += len(rows)

        # Tạo chỉ mục B-Tree trên các cột khóa ngoại cho các bảng Fact trong PostgreSQL
        # nhằm đảm bảo PostgreSQL đạt hiệu năng tối ưu nhất có thể cho các phép JOIN
        if table.startswith("fact_"):
            with pg.cursor() as cur:
                for col in ("date_sk", "enrolled_date_sk", "course_sk", "user_sk"):
                    if col in [r[0] for r in columns]:
                        cur.execute(f"CREATE INDEX ON benchmark.{table} ({col})")

        counts[table] = n
        print(f"Nhân bản bảng {table}: {n:,} dòng", flush=True)

    pg.commit()

    # Chạy lệnh ANALYZE để PostgreSQL cập nhật số liệu thống kê bảng cho bộ tối ưu truy vấn
    with pg.cursor() as cur:
        for table in tables:
            cur.execute(f"ANALYZE benchmark.{table}")
    pg.commit()

    # Ghi lại DDL nhân bản vào file benchmark/postgres_schema.sql
    (ROOT / "benchmark/postgres_schema.sql").write_text(
        "\n".join(ddl) + "\n", encoding="utf-8"
    )
    return counts


def benchmark(runs: int = 5, reuse_mirror: bool = False):
    """
    Hàm nhạc trưởng điều phối toàn bộ chu trình đo kiểm đối chuẩn hiệu năng.

    Tham số:
      - runs (int): Số lần đo lặp lại cho mỗi câu truy vấn (mặc định: 5 lần, tối thiểu 3).
      - reuse_mirror (bool): Có tái sử dụng bản sao PG có sẵn hay không (vẫn băm SHA-256 để xác minh).
    """
    if runs < 3:
        raise ValueError("Yêu cầu tối thiểu 3 lần đo lặp lại để tính trung vị")

    manifest = require_success()
    save_json(
        "benchmark/metadata.json",
        dict(
            status="running",
            pipeline_run=manifest["run_id"],
            started_at=utc_now(),
        ),
    )

    ch, pg = ch_connect(), staging_connect()
    warmups = 2  # Số lần chạy làm nóng bộ nhớ đệm

    try:
        tables = sorted(manifest["fingerprints"])
        begin = time.perf_counter()

        # BƯỚC 1: NHÂN BẢN DỮ LIỆU SANG POSTGRESQL (HOẶC ĐỐI SOÁT BẢN SAO SẴN CÓ)
        if reuse_mirror:
            with pg.cursor() as cur:
                counts = {}
                for table in tables:
                    cur.execute(f"SELECT count(*) FROM benchmark.{table}")
                    counts[table] = cur.fetchone()[0]
        else:
            counts = mirror(ch, pg, tables)

        mirror_seconds = round(time.perf_counter() - begin, 3)

        # Kiểm tra số lượng dòng phải khớp tuyệt đối
        for t, n in counts.items():
            if n != manifest["fingerprints"][t][0]:
                raise AssertionError(f"Lệch số dòng nhân bản ở bảng: {t}")

        # BƯỚC 2: NIÊM PHONG XÁC THỰC MÃ BĂM SHA-256 TỪNG DÒNG (FULL-ROW HASH EQUALITY)
        equality = {}
        for table in tables:
            key = ch.query(f"DESCRIBE TABLE gold.{table}").first_row[0]
            ch_hash, pg_hash = hashlib.sha256(), hashlib.sha256()

            # Quét toàn bộ ClickHouse sắp xếp theo khóa chính và băm SHA-256
            with ch.query_row_block_stream(
                f"SELECT * FROM gold.{table} ORDER BY {key}",
                settings={"max_block_size": 50000},
            ) as stream:
                for rows in stream:
                    for row in rows:
                        ch_hash.update(row_bytes(row))

            # Quét toàn bộ PostgreSQL sắp xếp theo khóa chính và băm SHA-256
            with pg.cursor(name="hash_" + table) as cur:
                cur.itersize = 50000
                cur.execute(f"SELECT * FROM benchmark.{table} ORDER BY {key}")
                while rows := cur.fetchmany(50000):
                    for row in rows:
                        pg_hash.update(row_bytes(row))

            equality[table] = dict(
                clickhouse=ch_hash.hexdigest(), postgres=pg_hash.hexdigest()
            )
            if ch_hash.digest() != pg_hash.digest():
                raise AssertionError(
                    f"Sai lệch mã băm dữ liệu gốc giữa ClickHouse và PG ở bảng: {table}"
                )
            print(f"Khớp mã băm SHA-256 toàn phần 100%: {table}", flush=True)

        pg.commit()

        # BƯỚC 3: XUẤT CÁC CÂU LỆNH SQL VÀO THƯ MỤC benchmark/sql/
        query_dir = ROOT / "benchmark/sql"
        query_dir.mkdir(parents=True, exist_ok=True)
        raw, summary, parity = [], [], {}

        def execute(engine: str, sql: str):
            """Hàm đo thời gian thực thi câu lệnh SQL tính bằng nano-giây ở máy khách."""
            start = time.perf_counter_ns()
            if engine == "clickhouse":
                rows = ch.query(
                    sql,
                    settings={"group_by_use_nulls": 1, "use_query_cache": 0},
                ).result_rows
            else:
                with pg.cursor() as cur:
                    cur.execute(sql)
                    rows = cur.fetchall()
            return (time.perf_counter_ns() - start) / 1e6, rows

        # BƯỚC 4: THỰC THI ĐO KIỂM 7 TRUY VẤN Q1–Q7
        for name, template in QUERIES.items():
            queries = {
                "postgres": template.format(db="benchmark"),
                "clickhouse": template.format(db="gold"),
            }
            # Ghi file SQL độc lập cho từng hệ quản trị
            for engine, sql in queries.items():
                (query_dir / f"{name}.{engine}.sql").write_text(
                    sql + ";\n", encoding="utf-8"
                )

            # 4.1 Làm nóng bộ nhớ đệm (Warm-up) và lấy kết quả chuẩn (Baseline)
            baseline = {}
            for engine in queries:
                for _ in range(warmups):
                    _, rows = execute(engine, queries[engine])
                baseline[engine] = canonical(rows)

            # Kiểm tra đối soát kết quả: Kết quả của ClickHouse và PG bắt buộc phải giống hệt nhau
            if baseline["postgres"] != baseline["clickhouse"]:
                save_json(
                    "benchmark/mismatch.json",
                    dict(query=name, results=baseline),
                )
                raise AssertionError(
                    f"Kết quả truy vấn không khớp giữa ClickHouse và PG ở câu: {name}"
                )

            parity[name] = dict(
                equal=True,
                rows=len(baseline["postgres"]),
                sha256=hashlib.sha256(
                    "\n".join(baseline["postgres"]).encode()
                ).hexdigest(),
            )

            # 4.2 Thực thi các lượt đo chính thức (5 lần lặp, đảo xen kẽ thứ tự)
            times = {"postgres": [], "clickhouse": []}
            for run in range(runs):
                order = (
                    ["postgres", "clickhouse"]
                    if run % 2 == 0
                    else ["clickhouse", "postgres"]
                )
                for engine in order:
                    elapsed, rows = execute(engine, queries[engine])
                    if canonical(rows) != baseline[engine]:
                        raise AssertionError(
                            f"Kết quả bị biến động bất thường trong khi đo ở câu: {name}"
                        )
                    times[engine].append(elapsed)
                    raw.append(
                        dict(
                            query=name,
                            engine=engine,
                            run=run + 1,
                            milliseconds=round(elapsed, 4),
                            rows=len(rows),
                        )
                    )

            # 4.3 Tính toán số liệu thống kê trung vị (Median / P50) và hệ số tăng tốc
            pg_ms = statistics.median(times["postgres"])
            ch_ms = statistics.median(times["clickhouse"])
            speedup = round(pg_ms / ch_ms, 3)

            summary.append(
                dict(
                    query=name,
                    postgres_median_ms=round(pg_ms, 3),
                    clickhouse_median_ms=round(ch_ms, 3),
                    speedup_pg_over_ch=speedup,
                    postgres_min_ms=round(min(times["postgres"]), 3),
                    postgres_max_ms=round(max(times["postgres"]), 3),
                    clickhouse_min_ms=round(min(times["clickhouse"]), 3),
                    clickhouse_max_ms=round(max(times["clickhouse"]), 3),
                    result_rows=parity[name]["rows"],
                )
            )
            print(
                f"{name}: PostgreSQL {pg_ms:.2f} ms / ClickHouse {ch_ms:.2f} ms => Nhanh gấp {speedup:.2f}x (Kết quả khớp 100%)",
                flush=True,
            )

        pg.commit()

        # BƯỚC 5: ĐO DUNG LƯỢNG LƯU TRỮ VÀ THÔNG SỐ CẤU HÌNH HỆ THỐNG
        with pg.cursor() as cur:
            cur.execute("SELECT version()")
            pg_version = cur.fetchone()[0]
            cur.execute(
                "SELECT name, setting, unit FROM pg_settings WHERE name IN ('work_mem', 'shared_buffers', 'max_parallel_workers_per_gather')"
            )
            pg_settings = cur.fetchall()
            cur.execute(
                "SELECT sum(pg_total_relation_size(quote_ident(schemaname)||'.'||quote_ident(tablename))) FROM pg_tables WHERE schemaname='benchmark'"
            )
            pg_bytes = int(cur.fetchone()[0])

        storage = ch.query(
            "SELECT sum(bytes_on_disk), sum(data_uncompressed_bytes) FROM system.parts WHERE database='gold' AND active"
        ).first_row

        metadata = dict(
            status="success",
            measured_at=utc_now(),
            pipeline_run=manifest["run_id"],
            warmup_runs=warmups,
            measured_runs=runs,
            timing="client wall-clock execute+fetch, serial, warm cache; CH query cache disabled",
            postgres_version=pg_version,
            clickhouse_version=ch.query("SELECT version()").first_row[0],
            python_version=platform.python_version(),
            postgres_settings=pg_settings,
            resources=dict(
                postgres_cpu=4,
                clickhouse_cpu=4,
                postgres_memory="2 GiB",
                clickhouse_memory="3 GiB",
                runner_memory="1500 MiB",
            ),
            limitations=[
                "Môi trường container Docker trên máy đơn lẻ (Single-host WSL/Linux)",
                "Cấu hình bộ nhớ cấp phát cho 2 hệ thống khác nhau (PG 2GB vs CH 3GB)",
                "Đo lường thời gian toàn phần từ máy khách (bao gồm độ trễ mạng socket)",
                "Dữ liệu sinh giả lập có cấu trúc đồng nhất cao",
            ],
            mirror_counts=counts,
            mirror_seconds=mirror_seconds,
            mirror_reused=reuse_mirror,
            mirror_hashes=equality,
            query_parity=parity,
            storage=dict(
                postgres_gold_with_indexes_bytes=pg_bytes,
                clickhouse_gold_bytes_on_disk=storage[0],
                clickhouse_gold_uncompressed_column_bytes=storage[1],
            ),
        )

        # Ghi nhận các file báo cáo kết quả
        benchmark_dir = ARTIFACTS / "benchmark"
        benchmark_dir.mkdir(parents=True, exist_ok=True)
        save_json("benchmark/metadata.json", metadata)
        save_json("benchmark/summary.json", summary)

        for filename, records in [("runs.csv", raw), ("summary.csv", summary)]:
            with (benchmark_dir / filename).open(
                "w", newline="", encoding="utf-8"
            ) as f:
                writer = csv.DictWriter(f, fieldnames=list(records[0]))
                writer.writeheader()
                writer.writerows(records)

        # Tạo file báo cáo định dạng Markdown trực quan
        lines = [
            "# Báo Cáo Đo Kiểm Đối Chuẩn Hiệu Năng (Benchmark Results)",
            "",
            f"Lượt chạy pipeline: `{manifest['run_id']}`. {warmups} lượt làm nóng (warm-ups) + {runs} lượt đo chính thức.",
            "",
            "**Đảm bảo tính khoa học:** Dữ liệu ở cả 2 hệ thống giống hệt nhau 100% (đối chiếu mã băm SHA-256 từng dòng và kết quả truy vấn).",
            "",
            "| Truy vấn | PostgreSQL P50 (ms) | ClickHouse P50 (ms) | Hệ số tăng tốc (PG / CH) | Số dòng kết quả |",
            "|:---|---:|---:|---:|---:|",
        ]
        lines += [
            f"| `{r['query']}` | {r['postgres_median_ms']:.2f} ms | {r['clickhouse_median_ms']:.2f} ms | **{r['speedup_pg_over_ch']:.2f}x** | {r['result_rows']:,} |"
            for r in summary
        ]
        lines += [
            "",
            "## So Sánh Dung Lượng Đĩa (Compression Efficiency)",
            f"- **PostgreSQL (kèm chỉ mục B-Tree):** `{pg_bytes / 1024 / 1024:.2f} MB`",
            f"- **ClickHouse (Đã nén cột LZ4/ZSTD):** `{storage[0] / 1024 / 1024:.2f} MB`",
            f"- **Tỷ lệ nén dữ liệu của ClickHouse:** `{storage[1] / storage[0]:.2f}x` (Dữ liệu gốc `{storage[1] / 1024 / 1024:.2f} MB`)",
            "",
            "## Giới Hạn Của Thử Nghiệm",
            "",
        ] + [f"- {v}" for v in metadata["limitations"]]

        (benchmark_dir / "results.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
        print("Đo kiểm Benchmark hoàn tất thành công!", flush=True)

    except Exception as exc:
        save_json(
            "benchmark/metadata.json",
            dict(
                status="failed",
                pipeline_run=manifest["run_id"],
                error=str(exc),
                finished_at=utc_now(),
            ),
        )
        raise
    finally:
        ch.close()
        pg.close()
