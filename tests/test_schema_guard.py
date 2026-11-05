"""
==================================================================================
KIỂM THỬ ĐƠN VỊ TẤM KHIÊN BẢO VỆ SCHEMA (UNIT TEST: SCHEMA GUARD & VALIDATOR)
==================================================================================
Mục tiêu:
  - Kiểm thử độc lập (Isolated Unit Test) năng lực chuẩn hóa và phát hiện lỗi của
    hàm `normalize()` trong module `etl/schema_guard.py`.
  - Các ca kiểm thử bao phủ:
      1. Ép kiểu số nguyên hợp lệ ('120' -> 120).
      2. Chặn lỗi trôi dạt cấu trúc (Schema Drift): Cột số nguyên nhận chuỗi chữ cái ('invalid').
      3. Chặn vi phạm luật nghiệp vụ: Số tiền bị âm (-5).
      4. Chặn email sai cú pháp: Thiếu @ hoặc có khoảng trắng ('bad-email').
      5. Chặn giá trị NULL ở các cột thời gian bắt buộc (completed_at).
      6. Chặn mâu thuẫn trục thời gian: Ngày hoàn thành trước ngày ghi danh.
==================================================================================
"""

import unittest
from etl.schema_guard import normalize


class SchemaGuardTests(unittest.TestCase):
    def test_text_amount_and_invalid_amount(self):
        """Kiểm tra ép kiểu số nguyên lớn, bắt lỗi chữ cái và chặn số tiền âm."""
        # 1. Chuỗi số nguyên hợp lệ được tự động ép thành kiểu int (120)
        clean_vals, err_code, err_msg = normalize(["price_vnd"], ["bigint"], ["120"])
        self.assertEqual(clean_vals, (120,))
        self.assertIsNone(err_code)

        # 2. Chuỗi chữ cái không thể ép sang bigint -> Phải bắt mã lỗi ERR_SCHEMA_TYPE_MISMATCH
        clean_vals, err_code, err_msg = normalize(["price_vnd"], ["bigint"], ["invalid"])
        self.assertIsNone(clean_vals)
        self.assertEqual(err_code, "ERR_SCHEMA_TYPE_MISMATCH")

        # 3. Số tiền mang giá trị âm (< 0) -> Phải bắt mã lỗi vi phạm nghiệp vụ ERR_NEGATIVE_AMOUNT
        clean_vals, err_code, err_msg = normalize(["price_vnd"], ["bigint"], [-5])
        self.assertIsNone(clean_vals)
        self.assertEqual(err_code, "ERR_NEGATIVE_AMOUNT")

    def test_bad_email_and_missing_lesson_timestamp(self):
        """Kiểm tra cú pháp email bẩn và chặn giá trị NULL ở cột thời gian bắt buộc."""
        # 1. Email sai định dạng (thiếu @) -> Bắt lỗi ERR_INVALID_EMAIL
        clean_vals, err_code, err_msg = normalize(["email"], ["text"], ["bad-email"])
        self.assertIsNone(clean_vals)
        self.assertEqual(err_code, "ERR_INVALID_EMAIL")

        # 2. Cột thời gian bắt buộc không được phép mang giá trị NULL
        clean_vals, err_code, err_msg = normalize(
            ["completed_at"], ["timestamp without time zone"], [None]
        )
        self.assertIsNone(clean_vals)
        self.assertEqual(err_code, "ERR_SCHEMA_TYPE_MISMATCH")

    def test_enrollment_completion_before_enrollment(self):
        """Kiểm tra tính nhất quán trục thời gian: Không thể hoàn thành trước khi ghi danh."""
        cols = ["enrolled_at", "completed_at"]
        types = ["timestamp without time zone"] * 2
        # Cố ý truyền completed_at (2024-01-01) xảy ra trước enrolled_at (2024-01-02)
        clean_vals, err_code, err_msg = normalize(
            cols, types, ["2024-01-02", "2024-01-01"]
        )
        self.assertIsNone(clean_vals)
        self.assertEqual(err_code, "ERR_TIME_INCONSISTENCY")


if __name__ == "__main__":
    unittest.main()
