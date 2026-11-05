"""
==================================================================================
MODULE TỔNG TƯ LỆNH ĐIỀU PHỐI PIPELINE (ETL ORCHESTRATOR & RESILIENCE ENGINE)
==================================================================================
Mục tiêu:
  - Giữ vai trò Tổng chỉ huy (Orchestrator) kết nối và điều phối nhịp nhàng toàn bộ
    vòng đời dữ liệu từ OLTP Nguồn $\rightarrow$ Staging/Quarantine $\rightarrow$ Gold ClickHouse.
  - Hỗ trợ linh hoạt 2 chế độ nạp dữ liệu:
      1. Full Load (`--mode full`): Nạp và tính toán lại toàn bộ lịch sử từ đầu.
      2. Incremental Load (`--mode incremental`): Chỉ trích xuất và nạp phần delta qua Watermark.
  - 5 Lớp phòng thủ hạ tầng và chịu lỗi cấp doanh nghiệp (Enterprise Fault-Tolerance):
      1. Thử lại với độ trễ tăng theo hàm mũ (Exponential Backoff): Tự động thử lại 3 lần
         (1s, 2s, 4s) khi gặp sự cố mạng chập chờn giữa các container Docker.
      2. Mẫu thiết kế Shadow Build / Blue-Green: Mọi thao tác tính toán và 116 bài kiểm toán
         được thực hiện trên database bóng `gold_build` trước khi người dùng nhìn thấy.
      3. Hoán đổi nguyên tử (Atomic Publish & Rollback): Tráo bảng tức thì trong vài mili-giây,
         tự động hoàn tác nếu gặp lỗi.
      4. Nạp tăng dần thông minh (Smart Incremental Short-Circuit): Nếu mẻ tăng dần không có
         dữ liệu mới, hệ thống phản hồi thành công ngay lập tức (< 1 giây).
      5. Ghi vết Manifest & Đo lường tài nguyên: Lưu trữ báo cáo `pipeline.json` và đo lường
         đỉnh tiêu thụ RAM (Peak RSS) của tiến trình.
==================================================================================
"""

import json
import resource
import time
import uuid
from contextlib import closing
import psycopg2

from etl.load_clickhouse import publish
from etl.watermark import commit_watermarks
from etl.bootstrap import TABLES
from etl.common import ARTIFACTS, ROOT, ch_connect, save_json, utc_now
from etl.stage import stage_source
from etl.transform_gold import load_gold_rows, silver_bridge


def statements(path):
    """
    Hàm tiện ích đọc file SQL và tách thành danh sách các câu lệnh riêng biệt
    dựa trên ký tự chấm phẩy (;), bỏ qua các câu lệnh rỗng hoặc chỉ có khoảng trắng.
    """
    return [
        sql.strip()
        for sql in path.read_text(encoding="utf-8").split(";")
        if sql.strip()
    ]


def clean_frame(df):
    """
    Hàm chuẩn hóa dữ liệu cho DataFrame (phục vụ bộ kiểm thử tích hợp Unit Test):
      - Cắt tỉa khoảng trắng ở hai đầu các trường chuỗi ký tự.
      - Chuyển đổi email về chữ thường (lowercase).
      - Chuyển đổi mã quốc gia về chữ in hoa (UPPERCASE).
    """
    result = df.copy()
    for col in (
        "full_name",
        "email",
        "city",
        "country",
        "title",
        "category",
        "difficulty",
        "method_name",
        "expertise",
    ):
        if col in result:
            result[col] = result[col].str.strip()
    if "email" in result:
        result["email"] = result["email"].str.lower()
    if "country" in result:
        result["country"] = result["country"].str.upper()
    return result


def pipeline(mode: str = "full"):
    """
    Hàm điều phối thực thi chính của luồng Data Warehouse Pipeline.

    Tham số:
      - mode (str): 'full' (nạp toàn bộ dữ liệu) hoặc 'incremental' (nạp tăng dần).
    """
    from etl.validate import validate

    started = time.perf_counter()
    run_id = uuid.uuid4().hex  # Sinh mã UUID định danh duy nhất cho phiên chạy hiện tại
    manifest = dict(run_id=run_id, status="running", mode=mode, started_at=utc_now())

    # Đọc kết quả của lượt chạy thành công trước đó (nếu có) từ artifacts/pipeline.json
    previous_path = ARTIFACTS / "pipeline.json"
    previous = (
        json.loads(previous_path.read_text(encoding="utf-8"))
        if previous_path.exists()
        else {}
    )
    save_json("pipeline.json", manifest)

    try:
        # ======================================================================
        # BƯỚC 1: TRÍCH XUẤT NGUỒN VÀO STAGING (KÈM CƠ CHẾ EXPONENTIAL BACKOFF)
        # ======================================================================
        # Nếu rớt mạng hoặc ngắt kết nối PostgreSQL, tự động thử lại 3 lần với thời gian chờ: 1s, 2s, 4s
        for attempt in range(3):
            try:
                counts, marks, extracted, previous_marks = stage_source(mode)
                break
            except (psycopg2.OperationalError, psycopg2.InterfaceError):
                if attempt == 2:
                    raise  # Sau 3 lần thử bất thành mới quăng lỗi ra ngoài
                time.sleep(2**attempt)

        # ======================================================================
        # BƯỚC 2: TỐI ƯU HÓA NẠP TĂNG DẦN RỖNG (EMPTY INCREMENTAL RUN SHORT-CIRCUIT)
        # ======================================================================
        # Nếu chạy chế độ tăng dần mà phía nguồn hoàn toàn không có dữ liệu mới phát sinh,
        # và phiên chạy trước đó đã thành công: Giữ nguyên kho Gold hiện tại và trả kết quả ngay (< 1s)
        if (
            mode == "incremental"
            and not any(extracted.values())
            and previous.get("status") == "success"
        ):
            manifest.update(
                status="success",
                tables=counts,
                extracted=extracted,
                fingerprints=previous["fingerprints"],
                quality_checks=previous["quality_checks"],
                gold_reused=True,
                seconds=round(time.perf_counter() - started, 3),
            )
            print(
                f"Nạp tăng dần hoàn tất tức thì trong {manifest['seconds']}s (Không có dữ liệu mới phát sinh)",
                flush=True,
            )
            return

        # ======================================================================
        # BƯỚC 3: DỰNG BẢN GOLD MỚI TRONG DATABASE BÓNG (SHADOW BUILD TRÊN 'gold_build')
        # ======================================================================
        with closing(ch_connect()) as ch:
            # Dọn dẹp sạch database bóng cũ (nếu còn sót lại từ lần chạy lỗi trước)
            ch.command("DROP DATABASE IF EXISTS gold_build SYNC")
            fact_actions = {}

            # Mở cầu nối bộ nhớ trực tiếp stage_bridge đọc từ PostgreSQL Staging (schema silver)
            with silver_bridge(ch):
                for file in (
                    "gold_schema.sql",
                    "load_gold.sql",
                    "materialized_views.sql",
                ):
                    for sql in statements(ROOT / "dw/ddl" / file):
                        # Định tuyến câu lệnh SQL sang database bóng: gold. -> gold_build. và silver. -> stage_bridge.
                        shadow_sql = (
                            sql.replace("gold.", "gold_build.")
                            .replace(
                                "CREATE DATABASE IF NOT EXISTS gold",
                                "CREATE DATABASE IF NOT EXISTS gold_build",
                            )
                            .replace("silver.", "stage_bridge.")
                        )

                        if file == "load_gold.sql":
                            # Nạp dữ liệu vào gold_build (tái sử dụng phân vùng ATTACH PARTITION nếu là incremental)
                            action = load_gold_rows(
                                ch,
                                shadow_sql,
                                mode,
                                extracted,
                                previous_marks,
                                previous.get("status") == "success",
                            )
                            if shadow_sql.startswith("INSERT INTO gold_build.fact_"):
                                fact_actions[
                                    shadow_sql.split()[2].split(".")[1]
                                ] = action
                        else:
                            ch.command(shadow_sql)

                # ==============================================================
                # BƯỚC 4: CỔNG KIỂM TOÁN CHẤT LƯỢNG (QUALITY GATEKEEPER)
                # ==============================================================
                # Chạy toàn bộ 116 bài kiểm toán trên database bóng gold_build trước khi cho phép công bố
                quality = validate(
                    ch=ch,
                    expected=counts,
                    require_ready=False,
                    database="gold_build",
                )

            # ==================================================================
            # BƯỚC 5: CÔNG BỐ BẢN GOLD NGUYÊN TỬ (ATOMIC PUBLISH)
            # ==================================================================
            tables = [
                row[0]
                for row in ch.query("SHOW TABLES FROM gold_build").result_rows
            ]

            # Xóa các Feed view cũ trước khi hoán đổi bảng
            for feed in ("feed_monthly_revenue", "feed_course_completion"):
                ch.command(f"DROP VIEW IF EXISTS gold.{feed}")

            # Hoán đổi nguyên tử toàn bộ bảng từ gold_build sang gold (Zero Downtime)
            publish(ch, tables)

            # Tạo lại các Materialized View feed tự động hứng sự kiện trên database gold chính thức
            for sql in statements(ROOT / "dw/ddl/aggregate_feeds.sql"):
                ch.command(sql)

            # Dọn dẹp sạch database bóng sau khi đã hoán đổi thành công
            ch.command("DROP DATABASE gold_build SYNC")

            # Dọn dẹp các database tàn dư cũ (nếu có) để kho ClickHouse luôn gọn gàng 100%
            for legacy in ("bronze", "silver"):
                ch.command(f"DROP DATABASE IF EXISTS {legacy} SYNC")

        # ======================================================================
        # BƯỚC 6: XÁC NHẬN MỐC PHÂN THỦY (DEFERRED WATERMARK COMMIT)
        # ======================================================================
        # Chỉ cập nhật mốc Watermark mới vào PostgreSQL Staging SAU KHI Gold đã được công bố an toàn!
        commit_watermarks(marks, run_id)

        # Cập nhật thông tin hoàn tất vào manifest
        manifest.update(
            status="success",
            tables=counts,
            extracted=extracted,
            fact_actions=fact_actions,
            fingerprints=quality["fingerprints"],
            quality_checks=len(quality["checks"]),
            seconds=round(time.perf_counter() - started, 3),
        )
        print(
            f"Pipeline THÀNH CÔNG trong {manifest['seconds']}s (Đạt {manifest['quality_checks']}/116 checks)",
            flush=True,
        )

    except Exception as exc:
        manifest.update(status="failed", error=str(exc))
        print(f"Pipeline THẤT BẠI: {exc}", flush=True)
        raise

    finally:
        # Ghi nhận thời gian kết thúc và đo lường đỉnh RAM tiêu thụ (Peak RSS) của tiến trình
        manifest["finished_at"] = utc_now()
        manifest["peak_rss_mib"] = round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2
        )
        save_json("pipeline.json", manifest)
        save_json(f"runs/{run_id}.json", manifest)
