"""
==================================================================================
MODULE CÔNG BỐ BẢN GOLD & HOÀN TÁC NGUYÊN TỬ (ATOMIC PUBLISH & SELF-HEALING ENGINE)
==================================================================================
Mục tiêu:
  - Triển khai mẫu thiết kế phát hành Shadow Build / Blue-Green Deployment ở cấp độ bảng:
      1. Toàn bộ quá trình tính toán và kiểm định chất lượng dữ liệu được thực hiện
         trên cơ sở dữ liệu bóng `gold_build`.
      2. Khi vượt qua 100% các bài kiểm toán, hàm `publish()` tiến hành hoán đổi nguyên tử
         (Atomic Table Swap) từ `gold_build` sang cơ sở dữ liệu chính thức `gold` đang phục vụ BI.
  - Đảm bảo tính khả dụng cao tuyệt đối (Zero-Downtime Guarantee):
      + Sử dụng lệnh chuyên dụng của ClickHouse: `EXCHANGE TABLES gold.{table} AND gold_build.{table}`.
      + Lệnh này hoán đổi con trỏ thư mục dữ liệu ở cấp độ metadata trong vòng vài mili-giây.
      + Người dùng cuối (Dashboard/Business Analyst) không bao giờ gặp tình trạng bảng bị khóa,
        bị rỗng hoặc đang nạp dở dang.
  - Cơ chế tự phục hồi và hoàn tác an toàn (Self-Healing Rollback Pattern):
      + Nếu trong chuỗi hoán đổi các bảng (ví dụ đang hoán đổi đến bảng thứ 5) mà phát sinh lỗi,
        hệ thống sẽ tự động duyệt ngược lại danh sách và hoán đổi các bảng đã tráo trở về vị trí cũ,
        đảm bảo kho Gold production không bao giờ rơi vào trạng thái chắp vá (Inconsistent State).
==================================================================================
"""


def publish(ch, tables: list):
    """
    Công bố danh sách các bảng từ database bóng 'gold_build' sang database chính thức 'gold'.

    Tham số:
      - ch: Client kết nối tới ClickHouse.
      - tables (list): Danh sách tên các bảng cần hoán đổi (ví dụ: ['dim_user', 'fact_payments', ...]).
    """
    # Đảm bảo cơ sở dữ liệu đích 'gold' luôn tồn tại
    ch.command("CREATE DATABASE IF NOT EXISTS gold")

    # Lấy danh sách các bảng hiện có trong database gold để quyết định dùng lệnh EXCHANGE hay RENAME
    existing = {r[0] for r in ch.query("SHOW TABLES FROM gold").result_rows}
    switched = []  # Danh sách theo dõi các bảng đã hoán đổi thành công để phục vụ rollback khi có sự cố

    try:
        for table in tables:
            if table in existing:
                # --------------------------------------------------------------
                # HOÁN ĐỔI NGUYÊN TỬ TỨC THÌ (ATOMIC SWAP):
                # --------------------------------------------------------------
                # Hoán đổi hai bảng cùng lúc trong 1 thao tác metadata duy nhất.
                # Bảng mới trong gold_build chuyển thành gold; bảng cũ trong gold chuyển thành gold_build.
                ch.command(f"EXCHANGE TABLES gold.{table} AND gold_build.{table}")
            else:
                # Nếu là bảng mới tinh chưa từng có trong database gold: Đổi tên từ gold_build sang gold
                ch.command(f"RENAME TABLE gold_build.{table} TO gold.{table}")

            # Đánh dấu bảng này đã hoán đổi thành công
            switched.append(table)

    except Exception:
        # ======================================================================
        # CƠ CHẾ ROLLBACK TỰ PHỤC HỒI (SELF-HEALING ROLLBACK):
        # ======================================================================
        # Khi xảy ra bất kỳ lỗi nào giữa chừng: Duyệt ngược danh sách các bảng đã hoán đổi
        # và thực hiện hoán đổi ngược lại để đưa toàn bộ hệ thống về nguyên trạng an toàn ban đầu.
        for table in reversed(switched):
            if table in existing:
                ch.command(f"EXCHANGE TABLES gold.{table} AND gold_build.{table}")
            else:
                ch.command(f"RENAME TABLE gold.{table} TO gold_build.{table}")

        # Ném lại ngoại lệ để tiến trình pipeline ghi nhận lỗi và dừng hoạt động
        raise
