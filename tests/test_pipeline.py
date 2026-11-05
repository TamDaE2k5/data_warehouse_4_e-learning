"""
==================================================================================
KIỂM THỬ TÍCH HỢP TOÀN DIỆN KHO DỮ LIỆU (INTEGRATION TESTS: WAREHOUSE PIPELINE)
==================================================================================
Mục tiêu:
  - Kiểm thử tích hợp toàn diện (End-to-End Integration Tests) giữa Python và ClickHouse Gold:
      1. Kiểm thử hàm làm sạch DataFrame `clean_frame` bảo toàn tính bất biến (Immutability).
      2. Kiểm thử cơ chế băm dữ liệu `row_bytes`: Đồng nhất múi giờ UTC và phân biệt NULL vs chuỗi rỗng.
      3. Ranh giới chính xác đến từng giây của chiều SCD Type 2 (Exact Time Boundary):
         Xác minh 3 mốc kiểm tra cực biên xung quanh thời điểm học viên chuyển nhà (2023-07-01):
           - 2023-06-30 23:59:59 -> Trả về user_sk cũ (10000051)
           - 2023-07-01 00:00:00 -> Trả về user_sk mới (10000052)
           - 2023-07-01 00:00:01 -> Trả về user_sk mới (10000052)
      4. Tính toàn vẹn của mốc thời gian chưa hoàn thành (completed_date_sk = 0).
      5. Nhãn NULL chuẩn của phép toán gom nhóm đa chiều CUBE.
      6. Bảo toàn tổng số đo khi thực hiện kỹ thuật Fact-to-Fact Drill Across (R07).
==================================================================================
"""

import unittest
from datetime import datetime, timezone
import pandas as pd
from etl.pipeline import clean_frame
from benchmark.run_benchmark import row_bytes, canonical
from etl.common import ch_connect


class TransformTests(unittest.TestCase):
    def test_cleaning_preserves_raw_and_identity(self):
        """Kiểm tra việc làm sạch chuỗi không làm thay đổi DataFrame nguồn ban đầu."""
        raw = pd.DataFrame({
            "user_id": [7],
            "email": ["  STUDENT7@EXAMPLE.INVALID  "],
            "country": [" vn "],
            "city": [" Ha Noi "],
        })
        clean = clean_frame(raw)

        # Kết quả sau làm sạch phải chuẩn hóa đúng
        self.assertEqual(
            clean.iloc[0].to_dict(),
            dict(
                user_id=7,
                email="student7@example.invalid",
                country="VN",
                city="Ha Noi",
            ),
        )
        # DataFrame gốc phải giữ nguyên giá trị dơ ban đầu (Immutability)
        self.assertEqual(raw.email.iloc[0], "  STUDENT7@EXAMPLE.INVALID  ")

    def test_hash_utc_and_null(self):
        """Kiểm tra cơ chế băm byte: Đồng nhất UTC có/không tzinfo và phân biệt NULL với chuỗi rỗng."""
        # Hai mốc thời gian giống nhau dù một bên có tzinfo UTC thì băm ra vẫn phải trùng nhau
        self.assertEqual(
            row_bytes((datetime(2024, 2, 29), None)),
            row_bytes((datetime(2024, 2, 29, tzinfo=timezone.utc), None)),
        )
        # Tuyệt đối không được đánh đồng giá trị NULL với chuỗi rỗng ''
        self.assertNotEqual(row_bytes((None,)), row_bytes(("",)))

    def test_parity_preserves_duplicates(self):
        """Kiểm tra việc chuẩn hóa tập đa tập (Multiset): Bảo toàn số lượng bản ghi trùng lặp."""
        self.assertNotEqual(canonical([(1,), (1,)]), canonical([(1,)]))
        # Bỏ qua sự khác biệt về vị trí sắp xếp của NULL
        self.assertEqual(
            canonical([(None,), (1,)]), canonical([(1,), (None,)])
        )


class WarehouseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Khởi tạo kết nối ClickHouse trước khi chạy các bài test tích hợp."""
        cls.ch = ch_connect()

    @classmethod
    def tearDownClass(cls):
        """Đóng kết nối ClickHouse sau khi hoàn tất kiểm thử."""
        cls.ch.close()

    def test_scd_exact_boundary(self):
        """
        Kiểm tra ranh giới chính xác đến từng giây của SCD Type 2 bằng phép ASOF JOIN.
        Kiểm tra 3 mốc thời gian sát nút chuyển nhà của User 5 vào ngày 2023-07-01:
          - 23:59:59 ngày 30/06/2023: Thuộc phiên bản cũ (user_sk = 10000051)
          - 00:00:00 ngày 01/07/2023: Đã chuyển sang phiên bản mới (user_sk = 10000052)
          - 00:00:01 ngày 01/07/2023: Thuộc phiên bản mới (user_sk = 10000052)
        """
        rows = self.ch.query(
            """
            SELECT e.t, u.user_sk FROM (
                SELECT toInt64(5) AS user_id, arrayJoin([
                    toDateTime('2023-06-30 23:59:59', 'UTC'),
                    toDateTime('2023-07-01 00:00:00', 'UTC'),
                    toDateTime('2023-07-01 00:00:01', 'UTC')
                ]) AS t
            ) e
            ASOF LEFT JOIN gold.dim_user u ON e.user_id = u.user_id AND e.t >= u.valid_from 
            ORDER BY e.t
            """
        ).result_rows
        self.assertEqual([r[1] for r in rows], [10000051, 10000052, 10000052])

    def test_unknown_date_only_uncompleted(self):
        """Khóa ngày completed_date_sk = 0 khi và chỉ khi completed_at mang giá trị NULL."""
        n = self.ch.query(
            """
            SELECT count() FROM gold.fact_enrollments
            WHERE (completed_date_sk = 0) != (completed_at IS NULL)
            """
        ).first_row[0]
        self.assertEqual(n, 0)

    def test_cube_subtotal_null_labels(self):
        """Kiểm tra các nhãn tổng con trong truy vấn CUBE hiển thị giá trị NULL chuẩn."""
        from benchmark.queries import QUERIES

        rows = self.ch.query(
            QUERIES["Q5_cube"].format(db="gold"),
            settings={"group_by_use_nulls": 1},
        ).result_rows

        # Có đúng 1 dòng tổng toàn cục (cả year và category đều NULL)
        self.assertEqual(sum(r[0] is None and r[1] is None for r in rows), 1)
        # Có đúng 4 dòng tổng con theo từng năm (category là NULL)
        self.assertEqual(sum(r[1] is None for r in rows), 4)
        # Không bao giờ có nhãn mang chuỗi rỗng ''
        self.assertFalse(any(r[1] == "" for r in rows))

    def test_drill_across_preserves_totals(self):
        """
        Kiểm tra kỹ thuật Fact-to-Fact Drill Across (R07):
        Tổng doanh thu và tổng lượt ghi danh sau khi Drill Across phải khớp chính xác
        với tổng độc lập tính trực tiếp từ từng bảng Fact.
        """
        import re
        from etl.common import ROOT

        text = (ROOT / "analytics/queries.sql").read_text()
        query = re.search(
            r"-- name: R07_revenue_enrollment_drill_across\n(.*?);", text, re.S
        ).group(1)
        rows = self.ch.query(query).result_rows

        # Tổng hợp số đo từ kết quả Drill Across
        actual = (sum(r[3] for r in rows), sum(r[4] for r in rows))

        # Tính toán đối ứng độc lập trực tiếp từ 2 bảng Fact gốc
        expected = (
            self.ch.query(
                "SELECT sum(net_vnd) FROM gold.fact_payments"
            ).first_row[0],
            self.ch.query(
                "SELECT count() FROM gold.fact_enrollments"
            ).first_row[0],
        )
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
