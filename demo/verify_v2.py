"""
==================================================================================
KỊCH BẢN KIỂM THỬ NGHIỆM THU TỰ ĐỘNG TOÀN HỆ THỐNG (END-TO-END ACCEPTANCE VERIFIER)
==================================================================================
Mục tiêu:
  - Tự động hóa kiểm tra tính đúng đắn của toàn bộ chu trình xử lý dữ liệu trên môi trường thực:
      1. BẢO MẬT & PHÂN QUYỀN (RBAC):
         Xác minh tài khoản đọc ETL (`learning_reader`) bị giới hạn giao dịch CHỈ ĐỌC
         (transaction_read_only = 'on') và TUYỆT ĐỐI KHÔNG CÓ QUYỀN UPDATE/DELETE trên OLTP.
      2. XỬ LÝ SỰ KIỆN ĐẾN MUỘN (LATE-ARRIVING FACTS):
         Bơm 10.000 lượt thi giả lập, xác minh ClickHouse chỉ nạp phần delta tăng thêm
         (10.000 dòng) với hành động `appended`.
      3. BẢO VỆ CHẤT LƯỢNG & KHU CÁCH LY (QUARANTINE MECHANISM):
         Cố tình phá hoại dữ liệu (cập nhật email user_id=1 thành 'invalid-v2-fixture'),
         xác minh hệ thống không bị sập mà tự động cách ly vào bảng `quarantine_records`
         với mã lỗi `ERR_INVALID_EMAIL`.
      4. TIẾN HÓA DỮ LIỆU SCD TYPE 2 (SLOWLY CHANGING DIMENSIONS):
         Cập nhật trạng thái lượt ghi danh, xác minh bảng `fact_enrollments` phân loại
         hành động là `versioned` và thay thế phân vùng bị ảnh hưởng an toàn.
      5. TÍNH BẤT BIẾN & TÁI SỬ DỤNG PHÂN VÙNG (IDEMPOTENCY & GOLD REUSE):
         Khôi phục dữ liệu sạch và chạy lại 2 lần liên tiếp, xác minh lần chạy thứ 2
         đọc 0 dòng từ nguồn và tái sử dụng kho Gold 100% (`gold_reused = True`).
      6. LƯU BẰNG CHỨNG NGHIỆM THU:
         Xuất báo cáo nghiệm thu chi tiết ra file `artifacts/verification_v2.json`.
==================================================================================
"""

import json
import subprocess
import sys
from argparse import ArgumentParser
from contextlib import closing

from etl.common import (
    ARTIFACTS,
    pg_connect,
    source_connect,
    staging_connect,
    save_json,
)


def run_incremental_pipeline() -> dict:
    """Kích hoạt Pipeline ở chế độ nạp tăng dần qua CLI và đọc kết quả manifest."""
    subprocess.run(
        [sys.executable, "cli.py", "pipeline", "--mode", "incremental"],
        check=True,
    )
    manifest_file = ARTIFACTS / "pipeline.json"
    if not manifest_file.exists():
        raise FileNotFoundError(f"Không tìm thấy file manifest tại {manifest_file}")
    return json.loads(manifest_file.read_text(encoding="utf-8"))


def verify_system(attempt_number: int = 99):
    """Thực thi chuỗi 5 bài kiểm tra nghiệm thu tích hợp."""
    print("=" * 80)
    print("BẮT ĐẦU KIỂM THỬ NGHIỆM THU TOÀN DIỆN HỆ THỐNG (E2E VERIFICATION)")
    print("=" * 80)

    # --------------------------------------------------------------------------
    # BÀI THỬ 1: KIỂM TRA PHÂN QUYỀN BẢO MẬT TÀI KHOẢN ĐỌC ETL (RBAC ISOLATION)
    # --------------------------------------------------------------------------
    print("\n[BƯỚC 1/5] Kiểm tra quyền hạn tài khoản ETL trên CSDL nguồn OLTP...")
    with closing(source_connect()) as src, src.cursor() as cur:
        cur.execute(
            """
            SELECT
                current_setting('transaction_read_only'),
                has_table_privilege(current_user, 'oltp.users', 'UPDATE')
            """
        )
        readonly, writable = cur.fetchone()
        assert readonly == "on", (
            f"Lỗi bảo mật: transaction_read_only phải là 'on', thực tế: '{readonly}'"
        )
        assert not writable, (
            "Lỗi bảo mật: Tài khoản ETL tuyệt đối không được có quyền UPDATE trên oltp.users!"
        )
    print("  -> Đạt: Tài khoản ETL được cách ly ở chế độ READ-ONLY nghiêm ngặt.")

    # --------------------------------------------------------------------------
    # BÀI THỬ 2: ĐỌC MANIFEST TRƯỚC THỰC THI (BASELINE VERIFICATION)
    # --------------------------------------------------------------------------
    print("\n[BƯỚC 2/5] Đọc trạng thái đường cơ sở (Baseline Manifest)...")
    manifest_file = ARTIFACTS / "pipeline.json"
    if not manifest_file.exists():
        raise RuntimeError(
            "Cần chạy 'python cli.py pipeline --mode full' ít nhất một lần để tạo đường cơ sở!"
        )
    baseline = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert baseline.get("status") == "success", "Đường cơ sở trước đó không thành công!"
    print(f"  -> Trạng thái cơ sở Run ID: {baseline['run_id']} - Thành công.")

    # --------------------------------------------------------------------------
    # BÀI THỬ 3: BƠM DỮ LIỆU ĐẾN MUỘN & CỐ TÌNH GÂY LỖI DỮ LIỆU (FAULT INJECTION)
    # --------------------------------------------------------------------------
    print(f"\n[BƯỚC 3/5] Bơm 10.000 lượt thi giả lập và làm dơ dữ liệu user 1...")
    # 3.1 Bơm 10.000 lượt thi trắc nghiệm đến muộn
    subprocess.run(
        [
            sys.executable,
            "-m",
            "demo.seed_incremental",
            "--attempt-number",
            str(attempt_number),
        ],
        check=True,
    )

    # 3.2 Tác nghiệp sửa email user 1 thành sai định dạng và chạm vào enrollment 1
    with closing(pg_connect()) as pg, pg, pg.cursor() as cur:
        # Lưu lại email hợp lệ trước đó để khôi phục sau này
        cur.execute("SELECT email FROM oltp.users WHERE user_id = 1 FOR UPDATE")
        previous_email = cur.fetchone()[0]

        # Cố ý cập nhật email không hợp lệ (không chứa ký tự @ và domain hợp lệ)
        cur.execute(
            """
            UPDATE oltp.users
            SET email = 'invalid-v2-fixture'
            WHERE user_id = 1
            RETURNING updated_at
            """
        )
        invalid_stamp = cur.fetchone()[0]

        # Kích hoạt cập nhật mốc thời gian hoàn thành của lượt ghi danh 1 để kích hoạt SCD Type 2
        cur.execute(
            """
            UPDATE oltp.enrollments
            SET completed_at = completed_at
            WHERE enrollment_id = 1
            """
        )
    print("  -> Đã bơm 10.000 lượt thi, sửa email user 1 thành 'invalid-v2-fixture' và kích hoạt SCD2.")

    # --------------------------------------------------------------------------
    # BÀI THỬ 4: CHẠY PIPELINE TĂNG DẦN & XÁC MINH CÁC HÀNH ĐỘNG
    # --------------------------------------------------------------------------
    print("\n[BƯỚC 4/5] Kích hoạt nạp tăng dần (Incremental Pipeline) và kiểm tra đối soát...")
    try:
        changed = run_incremental_pipeline()

        # Xác minh hành động trên ClickHouse Gold
        assert changed["fact_actions"]["fact_quiz_attempts"] == "appended", (
            f"Kỳ vọng 'appended' cho quiz attempts, thực tế: {changed['fact_actions']}"
        )
        assert changed["fact_actions"]["fact_enrollments"] == "versioned", (
            f"Kỳ vọng 'versioned' cho enrollments, thực tế: {changed['fact_actions']}"
        )

        # Xác minh số lượng chèn thêm đúng 10.000 dòng
        delta = changed["tables"]["quiz_attempts"] - baseline["tables"]["quiz_attempts"]
        assert delta == 10000, f"Kỳ vọng delta = 10.000, thực tế nhận được: {delta}"
        print(f"  -> Đạt: fact_quiz_attempts được 'appended' chính xác +10.000 dòng mới.")

        # Xác minh bản ghi bẩn đã bị cách ly vào bảng quarantine
        with closing(staging_connect()) as pg, pg.cursor() as cur:
            cur.execute(
                """
                SELECT error_code, raw_payload->>'email'
                FROM quarantine.quarantine_records
                WHERE table_name = 'users'
                  AND source_id = 1
                  AND source_updated_at = %s
                """,
                (invalid_stamp,),
            )
            quarantine_row = cur.fetchone()
            assert quarantine_row == ("ERR_INVALID_EMAIL", "invalid-v2-fixture"), (
                f"Kỳ vọng bản ghi vào quarantine với ERR_INVALID_EMAIL, thực tế: {quarantine_row}"
            )
        print("  -> Đạt: Dữ liệu bẩn bị chặn đứng và cách ly với mã 'ERR_INVALID_EMAIL'.")

    finally:
        # Bắt buộc khôi phục lại email sạch ban đầu dù pipeline có lỗi hay không
        with closing(pg_connect()) as pg, pg, pg.cursor() as cur:
            cur.execute(
                """
                UPDATE oltp.users
                SET email = %s
                WHERE user_id = 1 AND email = 'invalid-v2-fixture'
                """,
                (previous_email,),
            )
        print("  -> Đã khôi phục lại email nguyên vẹn ban đầu cho user 1.")

    # --------------------------------------------------------------------------
    # BÀI THỬ 5: TÍNH TỰ ĐỒNG HÓA VÀ BẢO TOÀN DỮ LIỆU KHI CHẠY LẶP LẠI (IDEMPOTENCY)
    # --------------------------------------------------------------------------
    print("\n[BƯỚC 5/5] Kiểm tra tính bất biến (Idempotency) khi nạp lại không có thay đổi...")
    restored = run_incremental_pipeline()
    repeated = run_incremental_pipeline()

    # Kiểm tra mã băm toàn vẹn (Fingerprints) không bị biến đổi
    assert restored["fingerprints"] == repeated["fingerprints"] == changed["fingerprints"], (
        "Mã băm dữ liệu Gold bị lệch giữa các lần chạy liên tiếp!"
    )

    # Lần chạy lặp lại thứ 2 phải đọc 0 dòng và tái sử dụng kho Gold hiện tại
    assert not any(repeated["extracted"].values()), (
        f"Lần chạy lặp lại không được trích xuất dữ liệu thừa: {repeated['extracted']}"
    )
    assert repeated.get("gold_reused") is True, (
        "Lần chạy lặp lại bắt buộc phải tái sử dụng Gold (gold_reused = True) để tiết kiệm tài nguyên!"
    )
    print("  -> Đạt: Lần chạy lặp lại trích xuất 0 dòng và tái sử dụng Gold hoàn toàn.")

    # --------------------------------------------------------------------------
    # GHI NHẬN HỒ SƠ KẾT QUẢ NGHIỆM THU
    # --------------------------------------------------------------------------
    summary = {
        "source_readonly": True,
        "inserted_attempts": delta,
        "quarantine_error": "ERR_INVALID_EMAIL",
        "baseline_run": baseline["run_id"],
        "changed_run": changed["run_id"],
        "repeated_run": repeated["run_id"],
        "extracted": changed["extracted"],
        "fact_actions": changed["fact_actions"],
        "changed_seconds": changed["seconds"],
        "repeated_seconds": repeated["seconds"],
        "identical_gold": True,
    }
    save_json("verification_v2.json", summary)
    print("=" * 80)
    print("XÁC NHẬN: TẤT CẢ 5 BÀI THỬ NGHIỆM THU TÍCH HỢP ĐỀU ĐẠT CHUẨN XUẤT SẮC!")
    print(f"Hồ sơ nghiệm thu đã được lưu tại: artifacts/verification_v2.json")
    print("=" * 80)


if __name__ == "__main__":
    parser = ArgumentParser(description="Kịch bản nghiệm thu kiểm thử tự động trên hệ thống đang chạy.")
    parser.add_argument(
        "--attempt-number",
        type=int,
        default=99,
        help="Số thứ tự lần thi giả lập (mặc định: 99)",
    )
    args = parser.parse_args()
    verify_system(args.attempt_number)
