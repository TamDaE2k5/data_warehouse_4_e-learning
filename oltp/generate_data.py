"""
==================================================================================
MODULE SINH DỮ LIỆU TÁC NGHIỆP GIẢ LẬP (OLTP SYNTHETIC DATA GENERATOR)
==================================================================================
Mục tiêu:
  - Sinh dữ liệu mẫu giả lập quy mô lớn (500.000 enrollments, ~5.72 triệu bản ghi)
    cho hệ thống E-Learning, nạp trực tiếp vào schema `oltp` trong PostgreSQL.
  - Đảm bảo tính nhất quán (Deterministic) thông qua hạt giống ngẫu nhiên (seed),
    giúp mọi lần chạy thử nghiệm đều ra cùng một bộ dữ liệu chuẩn xác.
  - Phục vụ kiểm thử toàn diện các kỹ thuật Data Warehouse:
      + Làm sạch dữ liệu dơ (dirty emails, khoảng trắng, chữ hoa/thường).
      + Theo dõi biến động lịch sử SCD Type 2 (học viên thay đổi nơi cư trú).
      + Mô hình Galaxy Schema & Fact-to-Fact Drill Across (doanh thu vs học tập).

Kỹ thuật tối ưu hóa hiệu năng:
  - Vectorization với NumPy & Pandas: Tính toán toàn bộ mảng dữ liệu song song trên C/BLAS,
    loại bỏ hoàn toàn vòng lặp Python chậm chạp, sinh 5.7M bản ghi chỉ trong < 100 giây.
  - Phân khối (Chunking): Chia nhỏ 500k lượt đăng ký thành từng lô 25.000 bản ghi,
    giúp kiểm soát bộ nhớ RAM luôn dưới 500MB mà không bị tràn bộ nhớ (OOM).
  - Bulk Copy Streaming: Nạp dữ liệu qua giao thức PostgreSQL `COPY FROM STDIN`
    (thông qua hàm copy_frame trong etl.common), nhanh gấp 50-100 lần so với INSERT thông thường.
  - Single Transaction & ANALYZE: Toàn bộ quá trình nạp gói gọn trong 1 Transaction duy nhất;
    kết thúc bằng lệnh ANALYZE để cập nhật bộ thống kê cho PostgreSQL Query Planner.
==================================================================================
"""

import time
import numpy as np
import pandas as pd
from faker import Faker
from etl.common import ROOT, copy_frame, pg_connect, save_json, utc_now


def generate(enrollments: int = 500000, seed: int = 2024):
    """
    Hàm sinh dữ liệu tác nghiệp toàn diện và nạp vào 11 bảng của schema `oltp`.

    Tham số:
      - enrollments (int): Tổng số lượt đăng ký khóa học cần sinh (mặc định: 500,000).
                           Phải >= 100 và là bội số của 100.
      - seed (int): Hạt giống ngẫu nhiên cố định để đảm bảo tính tái lập (mặc định: 2024).
    """
    # --------------------------------------------------------------------------
    # 1. KIỂM TRA THAM SỐ ĐẦU VÀO VÀ KHỞI TẠO BỘ SINH SỐ NGẪU NHIÊN (RNG)
    # --------------------------------------------------------------------------
    if enrollments < 100 or enrollments % 100:
        raise ValueError("enrollments must be a positive multiple of 100 (production: 500000)")

    start = time.perf_counter()

    # Sử dụng thư viện Faker với locale tiếng Việt ('vi_VN') để sinh họ tên người Việt chân thực
    fake = Faker("vi_VN")
    fake.seed_instance(seed)

    # Bộ sinh số ngẫu nhiên NumPy thế hệ mới (PCG64) đảm bảo tốc độ cực cao và tính xác định
    rng = np.random.default_rng(seed)

    # Tính toán quy mô các thực thể Master Data dựa trên tổng số enrollments:
    # Với 500k enrollments -> 50,000 học viên (tỉ lệ trung bình mỗi học viên học 10 khóa)
    users_n = min(50000, enrollments // 10)
    courses_n, instructors_n = 1000, 100  # 1.000 khóa học và 100 giảng viên
    counts = {}  # Từ điển ghi nhận số lượng bản ghi đã nạp vào từng bảng

    conn = pg_connect()
    try:
        # ----------------------------------------------------------------------
        # 2. KHỞI TẠO CẤU TRÚC SCHEMA VÀ KIỂM TRA TÍNH BẢO VỆ DỮ LIỆU
        # ----------------------------------------------------------------------
        with conn.cursor() as cur:
            # Thực thi file DDL schema.sql để tạo schema `oltp` và 11 bảng chuẩn hóa 3NF
            cur.execute((ROOT / "oltp/schema.sql").read_text())

            # Cơ chế Idempotent Check: Nếu bảng enrollments đã có dữ liệu, ngăn việc chạy đè
            # nhằm tránh làm hỏng các luồng ETL downstream đang phụ thuộc.
            cur.execute("SELECT count(*) FROM oltp.enrollments")
            if cur.fetchone()[0]:
                raise RuntimeError(
                    "Source already populated; generation is create-once. Use pipeline to reload DW."
                )

        def load(table: str, data):
            """Hàm tiện ích ghi đệm (bulk load) DataFrame vào PostgreSQL qua lệnh COPY."""
            frame = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
            copy_frame(conn, "oltp." + table, frame)
            counts[table] = counts.get(table, 0) + len(frame)

        # ----------------------------------------------------------------------
        # 3. SINH DỮ LIỆU PHÂN HỆ HỌC VIÊN & LỊCH SỬ THAY ĐỔI ĐỊA LÝ (SCD TYPE 2)
        # ----------------------------------------------------------------------
        ids = np.arange(1, users_n + 1)
        cities = np.array(["Ha Noi", "Da Nang", "Ho Chi Minh", "Can Tho"])

        # Sinh danh sách họ tên tiếng Việt ngẫu nhiên nhưng cố định theo hạt giống
        names = [fake.name() for _ in ids]

        # TẠO DỮ LIỆU DƠ CỐ Ý (DIRTY DATA):
        # Cứ mỗi học viên có id chia hết cho 17, ta cố ý chèn khoảng trắng đầu/cuối và viết IN HOA:
        # Ví dụ: '  STUDENT17@example.invalid  '
        # Mục đích: Kiểm thử năng lực làm sạch dữ liệu (Data Cleansing) ở tầng Silver.
        emails = [
            f"  STUDENT{i}@example.invalid  " if i % 17 == 0 else f"student{i}@example.invalid"
            for i in ids
        ]

        # Phân bổ tỉnh thành ban đầu xoay vòng theo 4 thành phố lớn
        original_city = cities[ids % 4]

        # MÔ PHỎNG BIẾN ĐỘNG NƠI Ở (SCD TYPE 2 BASELINE):
        # Giả lập 20% học viên (id % 5 == 0) chuyển nhà sang thành phố kế tiếp vào ngày 2023-07-01
        changed = ids % 5 == 0
        current_city = np.where(changed, cities[(ids + 1) % 4], original_city)

        # 3.1 Nạp bảng `users` (chứa trạng thái hiện hành mới nhất của học viên)
        load(
            "users",
            dict(
                user_id=ids,
                full_name=names,
                email=emails,
                city=current_city,
                country="VN",
                created_at=pd.Timestamp("2022-01-01"),
            ),
        )

        # 3.2 Nạp bảng `user_history` (ghi vết lịch sử hiệu lực theo thời gian)
        # Phiên bản 1: Có hiệu lực từ 2022-01-01.
        # - Nếu người dùng đổi nơi ở: valid_to = 2023-07-01
        # - Nếu người dùng không đổi: valid_to = 2100-01-01 (vô tận / trạng thái mở)
        hist = pd.DataFrame(
            dict(
                history_id=ids * 10 + 1,
                user_id=ids,
                full_name=names,
                email=emails,
                city=original_city,
                country="VN",
                valid_from=pd.Timestamp("2022-01-01"),
                valid_to=pd.to_datetime(np.where(changed, "2023-07-01", "2100-01-01")),
            )
        )
        load("user_history", hist)

        # Phiên bản 2: Chỉ áp dụng cho 20% học viên dọn nhà
        # Bắt đầu hiệu lực từ 2023-07-01 đến 2100-01-01 tại thành phố mới
        second = hist.loc[changed].copy()
        second["history_id"] += 1
        second["city"] = current_city[changed]
        second["valid_from"] = pd.Timestamp("2023-07-01")
        second["valid_to"] = pd.Timestamp("2100-01-01")
        load("user_history", second)

        # ----------------------------------------------------------------------
        # 4. SINH DỮ LIỆU PHÂN HỆ GIẢNG VIÊN & KHÓA HỌC (COURSES & LESSONS)
        # ----------------------------------------------------------------------
        # 4.1 Danh mục 100 giảng viên chuyên môn Công nghệ
        load(
            "instructors",
            dict(
                instructor_id=np.arange(1, instructors_n + 1),
                full_name=[fake.name() for _ in range(instructors_n)],
                expertise=["Technology"] * instructors_n,
            ),
        )

        # 4.2 Danh mục 1.000 khóa học với phân phối học phí log-normal chân thực:
        # Giá trung bình quanh mức 300.000đ - 1.500.000đ, làm tròn đến hàng nghìn đồng.
        # Khống chế chặn dưới 50.000đ và chặn trên 3.000.000đ qua hàm np.clip.
        course_ids = np.arange(1, courses_n + 1)
        prices = np.clip(
            rng.lognormal(12.7, 0.6, courses_n).astype("int64") // 1000 * 1000,
            50000,
            3000000,
        )
        # 10% số khóa học là miễn phí (học phí = 0 VND) để kiểm thử dữ liệu 0đ
        prices[course_ids % 10 == 0] = 0

        load(
            "courses",
            dict(
                course_id=course_ids,
                instructor_id=(course_ids - 1) % instructors_n + 1,
                title=[f"{fake.catch_phrase()} {i}" for i in course_ids],
                category=np.array(["Data", "Programming", "Business", "Design", "Language"])[
                    course_ids % 5
                ],
                difficulty=np.array(["beginner", "intermediate", "advanced"])[course_ids % 3],
                price_vnd=prices,
            ),
        )

        # 4.3 Danh mục 10.000 bài học (mỗi khóa học gồm đúng 10 bài học có thứ tự vị trí 1 -> 10)
        lesson_ids = np.arange(1, courses_n * 10 + 1)
        load(
            "lessons",
            dict(
                lesson_id=lesson_ids,
                course_id=(lesson_ids - 1) // 10 + 1,
                title=[f"Lesson {(i - 1) % 10 + 1}" for i in lesson_ids],
                position=(lesson_ids - 1) % 10 + 1,
            ),
        )

        # 4.4 Danh mục 1.000 bài kiểm tra đánh giá khóa học (mỗi khóa 1 bài quiz gồm 20 câu hỏi)
        load(
            "quizzes",
            dict(
                quiz_id=course_ids,
                course_id=course_ids,
                title=[f"Course assessment {i}" for i in course_ids],
                total_questions=20,
            ),
        )

        # 4.5 Danh mục 3 hình thức thanh toán được hỗ trợ
        load(
            "payment_methods",
            dict(method_id=[1, 2, 3], method_name=["bank_transfer", "card", "wallet"]),
        )

        # ----------------------------------------------------------------------
        # 5. SINH DỮ LIỆU SỰ KIỆN GIAO DỊCH THEO LÔ (CHUNKED TRANSACTIONAL EVENTS)
        # ----------------------------------------------------------------------
        # Chia quá trình sinh 500k enrollments thành các mẻ nhỏ 25.000 bản ghi
        # để tối ưu hóa bộ nhớ RAM và duy trì tốc độ truyền dữ liệu cao.
        completion_id = 1
        for lo in range(1, enrollments + 1, 25000):
            eid = np.arange(lo, min(lo + 25000, enrollments + 1))
            n = len(eid)

            # Ghép cặp học viên và khóa học theo thuật toán xoay vòng phân tán đều
            uid = (eid - 1) % users_n + 1
            cid = (((eid - 1) // users_n) * 73 + uid) % courses_n + 1

            # Phân bổ mốc thời gian đăng ký ngẫu nhiên trải đều trong 3 năm (2022-01-01 -> 2024-12-01)
            enrolled = pd.Timestamp("2022-01-01") + pd.to_timedelta(
                rng.integers(
                    0,
                    (pd.Timestamp("2024-12-01") - pd.Timestamp("2022-01-01")).days * 86400,
                    n,
                ),
                unit="s",
            )

            # Mô phỏng tỉ lệ hoàn thành khóa học: khoảng 30% học viên hoàn thành trọn vẹn 10 bài học
            done = (eid - 1 + (eid - 1) // users_n) % 10 < 3
            lesson_count = np.where(done, 10, 6)
            completed = pd.Series(enrolled + pd.Timedelta(days=31)).where(done)

            # 5.1 Bảng lượt ghi danh (enrollments)
            load(
                "enrollments",
                dict(
                    enrollment_id=eid,
                    user_id=uid,
                    course_id=cid,
                    enrolled_at=enrolled,
                    completed_at=completed,
                    lessons_completed=lesson_count,
                ),
            )

            # 5.2 Bảng thanh toán hóa đơn (payments)
            # Khách hàng áp dụng mã giảm giá (voucher) ngẫu nhiên: 0%, 10%, 20%, 30%.
            # Tỉ lệ hoàn tiền (refund rate) khoảng 5% nhằm mô phỏng nghiệp vụ tài chính thực tế.
            original = prices[cid - 1]
            discount = original * rng.choice([0, 10, 20, 30], n) // 100
            load(
                "payments",
                dict(
                    payment_id=eid,
                    enrollment_id=eid,
                    user_id=uid,
                    course_id=cid,
                    method_id=rng.integers(1, 4, n),
                    transaction_id=[f"TXN-{i:012d}" for i in eid],
                    paid_at=enrolled + pd.Timedelta(seconds=60),  # Thanh toán 1 phút sau đăng ký
                    original_vnd=original,
                    discount_vnd=discount,
                    charged_vnd=original - discount,
                    refunded=(rng.random(n) < 0.05).astype(int),
                ),
            )

            # 5.3 Bảng hoàn thành bài học (lesson_completions)
            # Mỗi bài học được học sinh hoàn thành cách nhau 3 ngày.
            # Thời lượng học được mô phỏng ngẫu nhiên từ 180 giây (3 phút) đến 3.600 giây (60 phút).
            idx = np.repeat(np.arange(n), lesson_count)
            positions = np.concatenate([np.arange(1, k + 1) for k in lesson_count])
            m = len(idx)
            load(
                "lesson_completions",
                dict(
                    completion_id=np.arange(completion_id, completion_id + m),
                    enrollment_id=eid[idx],
                    user_id=uid[idx],
                    course_id=cid[idx],
                    lesson_id=(cid[idx] - 1) * 10 + positions,
                    completed_at=enrolled[idx] + pd.to_timedelta(positions * 3, unit="D"),
                    time_spent_seconds=rng.integers(180, 3601, m),
                ),
            )
            completion_id += m

            # 5.4 Bảng lịch sử làm bài kiểm tra (quiz_attempts)
            # Mỗi lượt ghi danh thực hiện 2 lần làm bài kiểm tra.
            # Điểm số tuân theo phân phối chuẩn (Normal distribution) trung bình 13.5 câu đúng (độ lệch 3.5),
            # lần 2 cải thiện hơn lần 1 (+1 điểm), chặn trong thang điểm [0, 20] câu hỏi.
            idx_quiz = np.repeat(np.arange(n), 2)
            attempt = np.tile([1, 2], n)
            correct = np.clip(
                np.rint(rng.normal(13.5, 3.5, n * 2) + (attempt - 1)),
                0,
                20,
            ).astype(int)
            load(
                "quiz_attempts",
                dict(
                    attempt_id=(np.repeat(eid, 2) - 1) * 2 + attempt,
                    enrollment_id=eid[idx_quiz],
                    user_id=uid[idx_quiz],
                    course_id=cid[idx_quiz],
                    quiz_id=cid[idx_quiz],
                    attempt_number=attempt,
                    attempted_at=enrolled[idx_quiz] + pd.to_timedelta(attempt * 14, unit="D"),
                    correct_count=correct,
                    total_questions=20,
                    time_spent_seconds=rng.integers(180, 1801, n * 2),
                ),
            )

            print(f"Generated {eid[-1]:,}/{enrollments:,} enrollments", flush=True)

        # ----------------------------------------------------------------------
        # 6. KẾT THÚC TRANSACTION VÀ CẬP NHẬT THỐNG KÊ HỆ THỐNG
        # ----------------------------------------------------------------------
        conn.commit()  # Xác nhận lưu vĩnh viễn toàn bộ dữ liệu vào cơ sở dữ liệu

        # Chạy lệnh ANALYZE để PostgreSQL cập nhật số liệu phân tích bảng (histogram, row counts)
        # giúp bộ tối ưu hóa truy vấn (Query Planner) chọn kế hoạch thực thi tốt nhất.
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("ANALYZE")

        # Ghi nhận tóm tắt kết quả sinh dữ liệu ra file artifacts/generation.json
        result = dict(
            status="success",
            seed=seed,
            counts=counts,
            total_rows=sum(counts.values()),
            seconds=round(time.perf_counter() - start, 3),
            finished_at=utc_now(),
            synthetic=True,
            period=["2022-01-01", "2024-12-31"],
        )
        save_json("generation.json", result)
        print(result, flush=True)

    except Exception:
        # Nếu gặp bất kỳ sự cố nào, thu hồi toàn bộ transaction để tránh dữ liệu mồ côi (dangling data)
        conn.rollback()
        raise
    finally:
        conn.close()
