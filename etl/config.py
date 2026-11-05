"""
==================================================================================
MODULE CẤU HÌNH KẾT NỐI & AN TOÀN TÀI NGUYÊN (CONNECTION CONFIG & RESOURCE BOUNDS)
==================================================================================
Mục tiêu:
  - Quản lý tập trung thông tin kết nối và định tuyến truy cập cho toàn bộ hệ thống
    Data Warehouse (PostgreSQL OLTP, PostgreSQL Staging, ClickHouse Gold).
  - Triển khai nguyên tắc đặc quyền tối thiểu (Principle of Least Privilege):
      + Role `learning_reader`: Chỉ có quyền SELECT trên OLTP, tuyệt đối không được ghi.
      + Role `learning_stage`: Toàn quyền trên Staging/Silver, bị chặn kết nối vào OLTP.
      + Role `admin` (postgres): Dùng khi khởi tạo hệ thống (bootstrap) hoặc sinh dữ liệu.
  - Thiết lập ranh giới an toàn bộ nhớ (Memory Safety Bounds) cho ClickHouse,
    chống tràn RAM (OOM - Out Of Memory) khi tính toán các truy vấn OLAP hàng triệu dòng.
==================================================================================
"""

import os
import clickhouse_connect
import psycopg2


def pg_connect():
    """
    Kết nối quản trị PostgreSQL mặc định (Admin Connection).
    - Sử dụng: Dùng khi chạy lệnh bootstrap hệ thống hoặc script sinh dữ liệu OLTP.
    - Cấu hình: Đọc từ các biến môi trường chuẩn của PostgreSQL
      (PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD) hoặc cấu hình trong docker-compose.
    - Application Name: 'online_learning_dw_admin' giúp DBA dễ dàng nhận diện phiên trong pg_stat_activity.
    """
    return psycopg2.connect(application_name="online_learning_dw_admin")


def staging_connect():
    """
    Kết nối chuyên trách tới cơ sở dữ liệu trung chuyển 'dwh_staging' trên PostgreSQL.
    - Tài khoản: 'learning_stage' (kỹ sư dữ liệu / worker ETL).
    - Phạm vi quản lý: Các schema `staging` (dữ liệu thô vừa extract),
      `silver` (dữ liệu đã làm sạch & khử trùng lặp), và `quarantine` (cách ly bản ghi lỗi).
    - Bảo mật: Role này bị tước quyền kết nối (REVOKE CONNECT) vào cơ sở dữ liệu 'learning_oltp'
      để đảm bảo không bao giờ vô tình ghi đè hoặc can thiệp dữ liệu nghiệp vụ sống.
    """
    return psycopg2.connect(
        dbname="dwh_staging",
        user="learning_stage",
        password=os.environ["PG_STAGE_PASSWORD"],
        application_name="online_learning_dw_staging",
    )


def source_connect():
    """
    Kết nối tới cơ sở dữ liệu tác nghiệp 'learning_oltp' trên PostgreSQL.
    - Tài khoản: 'learning_reader' (chỉ đọc).
    - Quyền hạn: Chỉ được cấp quyền SELECT trên schema `oltp`.
      Đặc biệt được gán cờ `default_transaction_read_only = on` ở cấp độ Role.
    - Mục tiêu kiến trúc: Đảm bảo tiến trình ETL trích xuất dữ liệu (Extract)
      tuyệt đối không gây khóa độc quyền (Exclusive Lock) hoặc làm thay đổi trạng thái của nguồn.
    """
    return psycopg2.connect(
        dbname="learning_oltp",
        user="learning_reader",
        password=os.environ["PG_READER_PASSWORD"],
        application_name="dw_readonly_extractor",
    )


def ch_connect():
    """
    Kết nối tới máy chủ phân tích ClickHouse (Gold Layer - Dimensional Data Warehouse).
    - Áp dụng các tham số giới hạn an toàn tài nguyên (Memory Safety Bounds):
        + max_threads = 4: Khống chế tối đa 4 luồng tính toán song song, tránh ngốn kiệt CPU máy chủ.
        + max_memory_usage = 1.8GB: Giới hạn lượng RAM tối đa cho 1 truy vấn đơn lẻ; nếu vượt ngưỡng
          truy vấn sẽ bị hủy an toàn thay vì làm sập toàn bộ tiến trình ClickHouse (OOM Panic).
        + max_bytes_before_external_group_by = 500MB: Khi phép toán gom nhóm (GROUP BY) tiêu thụ
          vượt 500MB RAM, tự động kích hoạt cơ chế tràn đĩa (Spill-to-Disk) để tiếp tục xử lý.
        + max_bytes_before_external_sort = 500MB: Tương tự, sắp xếp (ORDER BY) lớn sẽ tự động dùng đĩa tạm.
    """
    return clickhouse_connect.get_client(
        host=os.getenv("CH_HOST", "localhost"),
        port=int(os.getenv("CH_PORT", "8123")),
        username=os.getenv("CH_USER", "learning"),
        password=os.environ["CH_PASSWORD"],
        connect_timeout=30,
        send_receive_timeout=600,
        settings={
            "max_threads": 4,
            "max_memory_usage": 1800000000,
            "max_bytes_before_external_group_by": 500000000,
            "max_bytes_before_external_sort": 500000000,
        },
    )
