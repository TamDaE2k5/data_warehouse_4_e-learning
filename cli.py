"""
==================================================================================
GIAO DIỆN DÒNG LỆNH ĐIỀU HÀNH HỆ THỐNG KHO DỮ LIỆU (DATA WAREHOUSE CLI ENTRYPOINT)
==================================================================================
Mục tiêu:
  - Cung cấp cổng giao tiếp dòng lệnh duy nhất (Unified CLI) để quản trị, vận hành
    và giám sát toàn bộ hệ thống Data Warehouse E-Learning 2022–2024.
  - Danh mục các lệnh được hỗ trợ:
      1. `setup`:     Khởi tạo 2 cơ sở dữ liệu (learning_oltp, dwh_staging) và phân quyền 3 roles.
      2. `generate`:  Sinh tập dữ liệu tác nghiệp mẫu quy mô lớn (500k enrollments, ~5.72M bản ghi).
      3. `pipeline`:  Điều phối luồng nạp ETL (hỗ trợ cờ `--mode full` hoặc `--mode incremental`).
      4. `validate`:  Kích hoạt cổng kiểm toán 116 chỉ tiêu chất lượng dữ liệu tự động.
      5. `reports`:   Thực thi 10 câu truy vấn phân tích nghiệp vụ (R01–R10) và xuất file CSV.
      6. `benchmark`: Đo kiểm hiệu năng truy vấn phân tích đối chuẩn giữa ClickHouse và PostgreSQL.
      7. `all`:       Chạy toàn diện chu trình khép kín: generate $\rightarrow$ pipeline $\rightarrow$ reports $\rightarrow$ benchmark.
  - Cơ chế an toàn: Toàn bộ các tác vụ xử lý đều được bọc trong Khóa phân tán
    (PostgreSQL Advisory Lock qua `project_lock()`) để chống xung đột tiến trình đồng thời.
==================================================================================
"""

import argparse
from etl.common import project_lock


def main():
    parser = argparse.ArgumentParser(
        description="Online Learning DW — Kho dữ liệu học trực tuyến 2022–2024"
    )
    parser.add_argument(
        "command",
        choices=[
            "setup",
            "generate",
            "pipeline",
            "validate",
            "reports",
            "benchmark",
            "all",
        ],
        help="Lệnh cần thực thi trong hệ thống",
    )
    parser.add_argument(
        "--enrollments",
        type=int,
        default=500000,
        help="Số lượng lượt ghi danh cần sinh (mặc định 500.000 dòng sự kiện)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=2024,
        help="Hạt giống sinh ngẫu nhiên tái lập (mặc định: 2024)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Số lần đo lặp lại cho benchmark (mặc định: 5 lần)",
    )
    parser.add_argument(
        "--reuse-mirror",
        action="store_true",
        help="Tái sử dụng bản sao PG Gold nếu đã có sẵn; vẫn đối chiếu toàn vẹn mã băm SHA256",
    )
    parser.add_argument(
        "--mode",
        choices=["full", "incremental"],
        default="full",
        help="Chế độ chạy pipeline: nạp toàn bộ (full) hoặc nạp tăng dần (incremental)",
    )

    args = parser.parse_args()

    # --------------------------------------------------------------------------
    # 1. LỆNH KHỞI TẠO HẠ TẦNG (SETUP)
    # --------------------------------------------------------------------------
    # Lệnh setup chạy bằng quyền quản trị postgres để tạo DB và phân quyền bảo mật,
    # không phụ thuộc vào khóa phân tán trên dwh_staging vì DB có thể chưa tồn tại.
    if args.command == "setup":
        from etl.bootstrap import setup

        setup()
        return

    # --------------------------------------------------------------------------
    # 2. CÁC TÁC VỤ VẬN HÀNH & PHÂN TÍCH (BỌC TRONG ADVISORY LOCK)
    # --------------------------------------------------------------------------
    # Ngăn ngừa tình trạng 2 tiến trình ETL hoặc 2 kỹ sư cùng kích hoạt lệnh song song
    with project_lock():
        # 2.1 Sinh dữ liệu nguồn giả lập
        if args.command in ("generate", "all"):
            from oltp.generate_data import generate

            generate(args.enrollments, args.seed)

        # 2.2 Điều phối luồng ETL nạp dữ liệu (Full hoặc Incremental)
        if args.command in ("pipeline", "all"):
            from etl.pipeline import pipeline

            pipeline(args.mode)

        # 2.3 Cổng kiểm toán chất lượng 116 chỉ tiêu toàn vẹn
        if args.command == "validate":
            from etl.validate import validate

            validate()

        # 2.4 Xuất 10 báo cáo phân tích nghiệp vụ SQL sang CSV
        if args.command in ("reports", "all"):
            from analytics.reports import reports

            reports()

        # 2.5 Chạy benchmark đối chuẩn hiệu năng ClickHouse vs PostgreSQL
        if args.command in ("benchmark", "all"):
            from benchmark.run_benchmark import benchmark

            benchmark(args.runs, reuse_mirror=args.reuse_mirror)


if __name__ == "__main__":
    main()
