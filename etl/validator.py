"""
==================================================================================
MODULE KIỂM ĐỊNH QUY TẮC NGHIỆP VỤ BẢN GHI (BUSINESS RULE VALIDATOR)
==================================================================================
Mục tiêu:
  - Đóng vai trò là tầng phòng vệ thứ hai (Second Line of Defense) sau khi bản ghi
    đã vượt qua bước chuẩn hóa cấu trúc & ép kiểu trong `etl/schema_guard.py`.
  - Kiểm tra tính hợp lệ về mặt logic kinh doanh (Business Domain Constraints):
      1. Định dạng Email: Chuẩn hóa chữ thường, kiểm tra cấu trúc qua Regex (`user@domain.ext`).
      2. Mã quốc gia: Chuẩn hóa in hoa theo chuẩn ISO (`'vn'` -> `'VN'`).
      3. Ràng buộc số tiền không âm: `price_vnd`, `original_vnd`, `discount_vnd`, `charged_vnd` >= 0.
      4. Phương trình cân đối tài chính: Tiền thực thu phải đúng bằng Giá gốc trừ Tiền giảm giá
         (`charged_vnd == original_vnd - discount_vnd`).
      5. Tính nhất quán trục thời gian: Ngày hoàn thành không được xảy ra trước ngày đăng ký
         (`completed_at >= enrolled_at`).
  - Khi phát hiện vi phạm: Trả về mã lỗi định danh chuẩn (`ERR_INVALID_EMAIL`, `ERR_NEGATIVE_AMOUNT`,
    `ERR_INVALID_AMOUNT`, `ERR_TIME_INCONSISTENCY`) để chuyển bản ghi vào bảng cách ly Quarantine.
==================================================================================
"""

import re

# Biểu thức chính quy (Regex) kiểm định cấu trúc địa chỉ email:
# Yêu cầu có tiền tố tài khoản, ký tự '@', tên miền và phần mở rộng hợp lệ, không chứa khoảng trắng.
EMAIL_REGEX = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def validate_row(row: dict):
    """
    Kiểm tra toàn diện các quy tắc logic nghiệp vụ trên một dòng bản ghi nguồn.

    Tham số:
      - row (dict): Từ điển chứa tên các cột và giá trị tương ứng của một bản ghi đã được ép kiểu.

    Trả về bộ ba (tuple):
      - (clean_values, error_code, rejection_reason):
          + Nếu bản ghi hợp lệ 100%: Trả về `(tuple(row.values()), None, None)`.
          + Nếu vi phạm quy tắc: Trả về `(None, mã_lỗi, lý_do_từ_chối)`.
    """
    # --------------------------------------------------------------------------
    # 1. KIỂM ĐỊNH & CHUẨN HÓA ĐỊA CHỈ EMAIL
    # --------------------------------------------------------------------------
    if "email" in row:
        # Chuẩn hóa toàn bộ email về chữ thường (lowercase)
        row["email"] = row["email"].lower()
        if not EMAIL_REGEX.fullmatch(row["email"]):
            return (
                None,
                "ERR_INVALID_EMAIL",
                "Email sai định dạng (thiếu @ hoặc có khoảng trắng)",
            )

    # --------------------------------------------------------------------------
    # 2. CHUẨN HÓA MÃ QUỐC GIA (ISO COUNTRY CODE)
    # --------------------------------------------------------------------------
    if "country" in row:
        # Chuyển đổi mã quốc gia sang chữ in hoa (ví dụ: 'vn' -> 'VN')
        row["country"] = row["country"].upper()

    # --------------------------------------------------------------------------
    # 3. RÀNG BUỘC SỐ TIỀN & HỌC PHÍ PHẢI KHÔNG ÂM (NON-NEGATIVE AMOUNTS)
    # --------------------------------------------------------------------------
    if any(
        row.get(col, 0) < 0
        for col in ("price_vnd", "original_vnd", "discount_vnd", "charged_vnd")
    ):
        return (
            None,
            "ERR_NEGATIVE_AMOUNT",
            "Số tiền (giá/học phí/giảm giá) không được phép âm",
        )

    # --------------------------------------------------------------------------
    # 4. PHƯƠNG TRÌNH ĐỐI SOÁT TÀI CHÍNH (FINANCIAL RECONCILIATION EQUATION)
    # --------------------------------------------------------------------------
    # Ràng buộc kế toán: Thực thu = Giá gốc niêm yết - Giá trị phiếu giảm giá
    if "charged_vnd" in row and row["charged_vnd"] != (
        row["original_vnd"] - row["discount_vnd"]
    ):
        return (
            None,
            "ERR_INVALID_AMOUNT",
            "Tiền thực thu không khớp với công thức: charged = original - discount",
        )

    # --------------------------------------------------------------------------
    # 5. TÍNH NHẤT QUÁN TRỤC THỜI GIAN (TEMPORAL CONSISTENCY)
    # --------------------------------------------------------------------------
    # Quy tắc logic: Học viên không thể hoàn thành khóa học trước thời điểm ghi danh
    if (
        row.get("completed_at")
        and row.get("enrolled_at")
        and row["completed_at"] < row["enrolled_at"]
    ):
        return (
            None,
            "ERR_TIME_INCONSISTENCY",
            "Thời điểm hoàn thành trước thời điểm ghi danh khóa học",
        )

    # Nếu vượt qua tất cả các chốt chặn kiểm định: Bản ghi hoàn toàn sạch sẽ!
    return tuple(row.values()), None, None
