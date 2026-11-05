"""
==================================================================================
MODULE KHỞI TẠO HẠ TẦNG VÀ PHÂN QUYỀN HỆ THỐNG (BOOTSTRAP & RBAC SECURITY SETUP)
==================================================================================
Mục tiêu:
  - Thiết lập ranh giới cơ sở dữ liệu vật lý độc lập trên máy chủ PostgreSQL:
      1. Cơ sở dữ liệu tác nghiệp: `learning_oltp` (chứa dữ liệu nghiệp vụ gốc).
      2. Cơ sở dữ liệu kho trung chuyển: `dwh_staging` (chứa staging, silver, quarantine).
  - Triển khai mô hình kiểm soát truy cập dựa trên vai trò (Role-Based Access Control - RBAC)
    theo chuẩn an ninh thông tin công nghiệp:
      + `learning_reader`: Tài khoản chỉ đọc cho tiến trình trích xuất ETL, áp dụng cờ
        `default_transaction_read_only = on` để bảo vệ 100% dữ liệu gốc.
      + `learning_stage`: Tài khoản công nhân ETL, sở hữu các schema staging/silver/quarantine,
        nhưng BỊ TƯỚC QUYỀN KẾT NỐI (REVOKE CONNECT) vào `learning_oltp`.
  - Cài đặt hệ thống kích hoạt (Triggers) và cột theo dõi mốc phân thủy (`updated_at` + index)
    trên toàn bộ 11 bảng tác nghiệp, làm nền móng cho cơ chế trích xuất tăng dần (Incremental CDC).
==================================================================================
"""

import os
from contextlib import closing
import psycopg2
from etl.common import ROOT

# Danh mục 11 bảng tác nghiệp của hệ thống đào tạo trực tuyến E-Learning
TABLES = (
    "users",
    "user_history",
    "instructors",
    "courses",
    "lessons",
    "quizzes",
    "payment_methods",
    "enrollments",
    "payments",
    "lesson_completions",
    "quiz_attempts",
)


def setup():
    """
    Hàm thực thi khởi tạo hạ tầng cơ sở dữ liệu và thiết lập bảo mật phân quyền.
    Được triệu gọi thông qua lệnh CLI: `python cli.py setup`.
    """
    # ==============================================================================
    # BƯỚC 1: KHỞI TẠO CƠ SỞ DỮ LIỆU VÀ CÁC ROLE BẢO MẬT BẰNG QUYỀN ADMIN (POSTGRES)
    # ==============================================================================
    with closing(psycopg2.connect(dbname="postgres")) as admin:
        admin.autocommit = True
        with admin.cursor() as cur:
            # Lấy danh sách các cơ sở dữ liệu hiện có trên máy chủ PostgreSQL
            cur.execute("SELECT datname FROM pg_database")
            names = {row[0] for row in cur}

            # 1.1 Tạo cơ sở dữ liệu tác nghiệp 'learning_oltp' nếu chưa tồn tại
            if "learning_oltp" not in names:
                cur.execute(
                    "ALTER DATABASE learning RENAME TO learning_oltp"
                    if "learning" in names
                    else "CREATE DATABASE learning_oltp"
                )

            # 1.2 Tạo cơ sở dữ liệu trung chuyển 'dwh_staging' nếu chưa tồn tại
            if "dwh_staging" not in names:
                cur.execute("CREATE DATABASE dwh_staging")

            # 1.3 Tạo Role trích xuất 'learning_reader' (chỉ đọc) cho database tác nghiệp
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'learning_reader'")
            if not cur.fetchone():
                cur.execute("CREATE ROLE learning_reader LOGIN")
            cur.execute(
                "ALTER ROLE learning_reader PASSWORD %s",
                (os.environ["PG_READER_PASSWORD"],),
            )
            # Ràng buộc an toàn: Mặc định mọi Transaction của learning_reader đều ở chế độ READ-ONLY
            cur.execute("ALTER ROLE learning_reader SET default_transaction_read_only = on")

            # 1.4 Tạo Role công nhân 'learning_stage' chuyên trách kho Staging & Silver
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'learning_stage'")
            if not cur.fetchone():
                cur.execute("CREATE ROLE learning_stage LOGIN")
            cur.execute(
                "ALTER ROLE learning_stage PASSWORD %s",
                (os.environ["PG_STAGE_PASSWORD"],),
            )

            # 1.5 Phân quyền ranh giới: Thu hồi quyền kết nối công cộng và cô lập hai môi trường
            # Ngăn chặn tài khoản ETL 'learning_stage' vô tình hoặc cố ý kết nối vào OLTP
            cur.execute("REVOKE CONNECT ON DATABASE learning_oltp FROM PUBLIC")
            cur.execute("GRANT CONNECT ON DATABASE learning_oltp TO learning_reader")
            cur.execute(
                "GRANT CONNECT, CREATE, TEMPORARY ON DATABASE dwh_staging TO learning_stage"
            )

    # ==============================================================================
    # BƯỚC 2: CẤU HÌNH SCHEMA TÁC NGHIỆP, TRIGGER CDC & CHỈ MỤC MỐC PHÂN THỦY TRÊN 'learning_oltp'
    # ==============================================================================
    with closing(psycopg2.connect(dbname="learning_oltp")) as source, source, source.cursor() as cur:
        # Thực thi tạo cấu trúc 11 bảng 3NF nguồn ban đầu
        cur.execute((ROOT / "oltp/schema.sql").read_text(encoding="utf-8"))

        # Tạo hàm Trigger ghi vết thời gian `clock_timestamp()`:
        # Điểm khác biệt quan trọng: `clock_timestamp()` trả về thời gian thực tại thời điểm
        # câu lệnh thực thi, trong khi `now()` chỉ trả về thời điểm bắt đầu Transaction.
        # Sử dụng `clock_timestamp()` đảm bảo thứ tự thời gian luôn tăng đơn điệu (Monotonic Order),
        # loại bỏ hiện tượng sót bản ghi khi thực hiện trích xuất tăng dần (Incremental Extraction).
        cur.execute("""
            CREATE OR REPLACE FUNCTION oltp.touch_row() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                NEW.updated_at := clock_timestamp();
                RETURN NEW;
            END $$;
        """)

        # Bổ sung cột mốc phân thủy `updated_at`, tạo Index B-Tree và gắn Trigger cho toàn bộ 11 bảng
        for table in TABLES:
            cur.execute(f"""
                ALTER TABLE oltp.{table} ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
                CREATE INDEX IF NOT EXISTS {table}_updated_idx ON oltp.{table}(updated_at);
                CREATE OR REPLACE TRIGGER set_updated_at BEFORE INSERT OR UPDATE ON oltp.{table}
                FOR EACH ROW EXECUTE FUNCTION oltp.touch_row();
            """)

        # Cấp quyền đọc tối thiểu trên schema `oltp` cho role `learning_reader`
        cur.execute("""
            GRANT CONNECT ON DATABASE learning_oltp TO learning_reader;
            GRANT USAGE ON SCHEMA oltp TO learning_reader;
            GRANT SELECT ON ALL TABLES IN SCHEMA oltp TO learning_reader;
        """)

    # ==============================================================================
    # BƯỚC 3: KHỞI TẠO CÁC SCHEMA VÀ PHÂN QUYỀN TRÊN KHO TRUNG CHUYỂN 'dwh_staging'
    # ==============================================================================
    with closing(psycopg2.connect(dbname="dwh_staging")) as stage, stage, stage.cursor() as cur:
        # Nếu file DDL staging_schema.sql đã sẵn sàng, thực thi để tạo cấu trúc silver, staging, quarantine
        staging_ddl = ROOT / "dw/ddl/staging_schema.sql"
        if staging_ddl.exists():
            cur.execute(staging_ddl.read_text(encoding="utf-8"))

            # Trao toàn quyền quản lý bảng cho role `learning_stage`
            cur.execute("GRANT USAGE ON SCHEMA silver, staging, quarantine TO learning_stage")
            cur.execute(
                "GRANT ALL ON ALL TABLES IN SCHEMA silver, staging, quarantine TO learning_stage"
            )

        # Khởi tạo schema `benchmark` thuộc quyền sở hữu của learning_stage phục vụ việc đo hiệu năng
        cur.execute("CREATE SCHEMA IF NOT EXISTS benchmark AUTHORIZATION learning_stage")
        cur.execute("ALTER SCHEMA benchmark OWNER TO learning_stage")

    print(
        "Thiết lập hạ tầng 2 cơ sở dữ liệu và phân quyền RBAC an toàn THÀNH CÔNG!",
        flush=True,
    )
