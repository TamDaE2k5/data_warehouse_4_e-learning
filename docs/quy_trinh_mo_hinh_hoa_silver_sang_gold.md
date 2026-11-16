# QUY TRÌNH MÔ HÌNH HÓA VÀ BIẾN ĐỔI DỮ LIỆU TỪ SILVER SANG GOLD
## (Chi Tiết Từng Luồng Bằng Sơ Đồ Mermaid Phân Đoạn)

> **Mục tiêu tài liệu:**  
> Thay vì dùng một sơ đồ tổng thể khổng lồ gây rối mắt, tài liệu này **chia nhỏ luồng biến đổi dữ liệu từ PostgreSQL Silver sang ClickHouse Gold thành 8 sơ đồ trực quan độc lập**.  
> Mỗi sơ đồ tập trung giải quyết đúng một câu hỏi: **Bảng này lấy từ đâu ở Silver? Biến đổi công thức gì? Nối khóa nào? Và nạp vào đâu ở Gold?**

---

## 📑 MỤC LỤC CÁC SƠ ĐỒ LUỒNG

1. [Sơ đồ 0: Kiến Trúc Cầu Nối Bộ Nhớ (Zero-Copy Stage Bridge)](#1-sơ-đồ-0-kiến-trúc-cầu-nối-bộ-nhớ-zero-copy-stage-bridge)
2. [Sơ đồ 1: Luồng Các Chiều Danh Mục Độc Lập (`dim_date`, `dim_payment_method`, `dim_instructor`)](#2-sơ-đồ-1-luồng-các-chiều-danh-mục-độc-lập)
3. [Sơ đồ 2: Luồng Chiều Học Viên Bảo Toàn Lịch Sử SCD Type 2 (`dim_user`)](#3-sơ-đồ-2-luồng-chiều-học-viên-bảo-toàn-lịch-sử-scd-type-2)
4. [Sơ đồ 3: Luồng Nhóm Chiều Cấu Trúc Khóa Học (`dim_course`, `dim_lesson`, `dim_quiz`)](#4-sơ-đồ-3-luồng-nhóm-chiều-cấu-trúc-khóa-học)
5. [Sơ đồ 4: Luồng Bảng Fact Doanh Thu & Thanh Toán (`fact_payments`)](#5-sơ-đồ-4-luồng-bảng-fact-doanh-thu--thanh-toán-fact_payments)
6. [Sơ đồ 5: Luồng Bảng Fact Tiến Độ Ghi Danh & Tốt Nghiệp (`fact_enrollments`)](#6-sơ-đồ-5-luồng-bảng-fact-tiến-độ-ghi-danh--tốt-nghiệp-fact_enrollments)
7. [Sơ đồ 6: Luồng Bảng Fact Hoàn Thành Bài Giảng (`fact_lesson_completions`)](#7-sơ-đồ-6-luồng-bảng-fact-hoàn-thành-bài-giảng-fact_lesson_completions)
8. [Sơ đồ 7: Luồng Bảng Fact Kết Quả Thi Trắc Nghiệm (`fact_quiz_attempts`)](#8-sơ-đồ-7-luồng-bảng-fact-kết-quả-thi-trắc-nghiệm-fact_quiz_attempts)
9. [Sơ đồ 8: Luồng Tự Động Tổng Hợp Báo Cáo Siêu Tốc (Aggregate Feeds)](#9-sơ-đồ-8-luồng-tự-động-tổng-hợp-báo-cáo-siêu-tốc-aggregate-feeds)
10. [Bảng Ma Trận Tổng Hợp Đối Chiếu Nguồn - Đích](#10-bảng-ma-trận-tổng-hợp-đối-chiếu-nguồn---đích)

---

## 1. SƠ ĐỒ 0: KIẾN TRÚC CẦU NỐI BỘ NHỚ (ZERO-COPY STAGE BRIDGE)

Trước khi đi vào từng bảng, đây là cơ chế vật lý giúp ClickHouse đọc được dữ liệu sạch từ PostgreSQL Silver mà **không cần ghi file trung gian ra ổ đĩa**:

```mermaid
flowchart LR
    subgraph PG["PostgreSQL (Container: postgres)"]
        S_DATA[("Database: dwh_staging<br/>Schema: silver<br/>• 11 bảng sạch đã chuẩn hóa")]
    end

    subgraph CH["ClickHouse (Container: clickhouse)"]
        BRIDGE["Database ảo: stage_bridge<br/>• ENGINE = PostgreSQL(...)<br/>• Đọc trực tiếp qua mạng nội bộ"]
        GOLD_BUILD[("Database bóng: gold_build<br/>• Nạp và tính toán mô hình hóa<br/>• Kiểm toán 116 Checks PASS<br/>• Hoán đổi nguyên tử sang gold")]
    end

    S_DATA ===|"Truyền dữ liệu thẳng qua RAM (Socket mạng)"| BRIDGE
    BRIDGE -->|"Thực thi INSERT INTO gold_build.* SELECT ..."| GOLD_BUILD
```

* **Nguyên lý:** ClickHouse tạo database ảo `stage_bridge` kết nối thẳng vào PostgreSQL. Dữ liệu từ schema `silver` được nạp thẳng vào RAM của ClickHouse với tốc độ hàng trăm nghìn dòng mỗi giây. Sau khi nạp xong, database `stage_bridge` tự động bị hủy (`DROP DATABASE`).

---

## 2. SƠ ĐỒ 1: LUỒNG CÁC CHIỀU DANH MỤC ĐỘC LẬP

Đây là nhóm 3 bảng chiều đầu tiên được nạp vì chúng **hoàn toàn độc lập**, không phụ thuộc vào bất kỳ bảng nào khác:

```mermaid
flowchart TD
    subgraph SRC["DỮ LIỆU NGUỒN"]
        GEN["ClickHouse Engine:<br/>numbers(1096)<br/>(Dãy số 0 .. 1095)"]
        S_METH["silver.payment_methods<br/>• method_id<br/>• method_name"]
        S_INST["silver.instructors<br/>• instructor_id<br/>• full_name<br/>• expertise"]
    end

    subgraph TRANS["BIẾN ĐỔI & TẠO SURROGATE KEY (SK)"]
        T_DATE["• toDate('2022-01-01') + interval<br/>• date_sk = toYYYYMMDD(d)<br/>• Thêm dòng date_sk = 0 (Unknown)"]
        T_METH["• method_sk = method_id + 5,000,000<br/>• method_name = LowCardinality"]
        T_INST["• instructor_sk = instructor_id + 2,000,000<br/>• expertise = LowCardinality"]
    end

    subgraph GOLD["BẢNG CHIỀU ĐÍCH (GOLD)"]
        G_DATE[("gold.dim_date<br/>• date_sk (PK)<br/>• full_date, year, quarter, month, day")]
        G_METH[("gold.dim_payment_method<br/>• method_sk (PK)<br/>• method_id, method_name")]
        G_INST[("gold.dim_instructor<br/>• instructor_sk (PK)<br/>• instructor_id, full_name, expertise")]
    end

    GEN --> T_DATE --> G_DATE
    S_METH --> T_METH --> G_METH
    S_INST --> T_INST --> G_INST
```

### 💡 Điểm cốt lõi cần nhớ:
1. **`dim_date` không lấy từ Silver:** Bảng lịch được sinh trước bằng thuật toán 1.096 ngày liên tục (2022–2024). Dòng `date_sk = 0` (`1970-01-01`) dành riêng cho các sự kiện chưa kết thúc (như khóa học chưa tốt nghiệp).
2. **Khóa thay thế (SK):**
   * Phương thức thanh toán: `method_sk = method_id + 5.000.000`.
   * Giảng viên: `instructor_sk = instructor_id + 2.000.000`.

---

## 3. SƠ ĐỒ 2: LUỒNG CHIỀU HỌC VIÊN BẢO TOÀN LỊCH SỬ SCD TYPE 2

Nhiều người hay nhầm lẫn giữa `silver.users` và `silver.user_history`. Sơ đồ này làm rõ tại sao phải lấy từ `silver.user_history`:

```mermaid
flowchart TD
    subgraph WRONG["NGUỒN BỊ LOẠI BỎ (KHÔNG DÙNG)"]
        S_USER["silver.users<br/>❌ Chỉ lưu thành phố hiện tại<br/>❌ Mất sạch lịch sử khi học viên đổi chỗ ở"]
    end

    subgraph SRC["NGUỒN CHÍNH XÁC"]
        S_HIST["silver.user_history<br/>• history_id (PK nguồn)<br/>• user_id<br/>• full_name, email, city, country<br/>• valid_from (mốc bắt đầu)<br/>• valid_to (mốc kết thúc)"]
    end

    subgraph TRANS["LOGIC BIẾN ĐỔI SCD TYPE 2"]
        T_USER["• user_sk = history_id + 10,000,000<br/>• Cờ is_current = 1 (nếu valid_to = 2100-01-01)<br/>• Cờ is_current = 0 (nếu phiên bản lịch sử cũ)<br/>• Nén city, country sang LowCardinality"]
    end

    subgraph GOLD["BẢNG CHIỀU ĐÍCH (GOLD)"]
        G_USER[("gold.dim_user<br/>(Slowly Changing Dimension Type 2)<br/>• user_sk (Surrogate Key duy nhất từng phiên bản)<br/>• user_id (Khóa tự nhiên để COUNT DISTINCT)<br/>• full_name, email, city, country<br/>• valid_from, valid_to, is_current")]
    end

    S_HIST --> T_USER --> G_USER
    S_USER -.->|"Bị loại bỏ"| WRONG
```

### 💡 Ví dụ thực tế:
Học viên 5 (Nhật Phạm) chuyển từ Đà Nẵng vào TP.HCM ngày 01/07/2023:
* **Phiên bản 1 (Đà Nẵng):** `history_id = 51` $\rightarrow$ `user_sk = 10000051`, `valid_from = 2022-01-01`, `valid_to = 2023-07-01`, `is_current = 0`.
* **Phiên bản 2 (TP.HCM):** `history_id = 52` $\rightarrow$ `user_sk = 10000052`, `valid_from = 2023-07-01`, `valid_to = 2100-01-01`, `is_current = 1`.

---

## 4. SƠ ĐỒ 3: LUỒNG NHÓM CHIỀU CẤU TRÚC KHÓA HỌC

Nhóm chiều này biểu diễn cây cấu trúc đào tạo: **Khóa học $\rightarrow$ Bài học $\rightarrow$ Đề thi trắc nghiệm**:

```mermaid
flowchart TD
    subgraph SRC["DỮ LIỆU NGUỒN SILVER"]
        S_COURSE["silver.courses<br/>• course_id, instructor_id<br/>• title, category, difficulty, price_vnd"]
        S_LESS["silver.lessons<br/>• lesson_id, course_id<br/>• title, position"]
        S_QUIZ["silver.quizzes<br/>• quiz_id, course_id<br/>• title, total_questions"]
    end

    subgraph TRANS["BIẾN ĐỔI & TẠO SURROGATE KEY"]
        T_C["• course_sk = course_id + 1,000,000<br/>• Nén category, difficulty: LowCardinality"]
        T_L["• lesson_sk = lesson_id + 3,000,000<br/>• Giữ nguyên position (thứ tự bài 1..10)"]
        T_Q["• quiz_sk = quiz_id + 4,000,000<br/>• Giữ nguyên total_questions (20 câu)"]
    end

    subgraph GOLD["CÁC BẢNG CHIỀU ĐÍCH (GOLD)"]
        G_COURSE[("gold.dim_course<br/>• course_sk (PK)<br/>• course_id, instructor_id<br/>• title, category, difficulty, price_vnd")]
        G_LESS[("gold.dim_lesson<br/>• lesson_sk (PK)<br/>• lesson_id, course_id, title, position")]
        G_QUIZ[("gold.dim_quiz<br/>• quiz_sk (PK)<br/>• quiz_id, course_id, title, total_questions")]
    end

    S_COURSE --> T_C --> G_COURSE
    S_LESS --> T_L --> G_LESS
    S_QUIZ --> T_Q --> G_QUIZ
```

### 💡 Quy tắc khóa thay thế:
* Khóa học: `course_sk = course_id + 1.000.000`
* Bài học: `lesson_sk = lesson_id + 3.000.000`
* Đề thi: `quiz_sk = quiz_id + 4.000.000`

---

## 5. SƠ ĐỒ 4: LUỒNG BẢNG FACT DOANH THU & THANH TOÁN (`fact_payments`)

Đây là trung tâm tài chính của hệ thống. Bảng này đọc từng giao dịch từ `silver.payments` và **JOIN vào 4 bảng Dimension** để thay thế toàn bộ khóa nguồn thành Surrogate Keys:

```mermaid
flowchart TD
    subgraph SRC["NGUỒN SỰ KIỆN GIAO DỊCH"]
        S_PAY["silver.payments<br/>• payment_id, transaction_id<br/>• enrollment_id, user_id, course_id, method_id<br/>• paid_at, original_vnd, discount_vnd, charged_vnd, refunded"]
    end

    subgraph LOOKUP["LOOKUP SURROGATE KEYS TỪ CÁC CHIỀU ĐÃ NẠP"]
        D_COUR["gold.dim_course<br/>(Lookup c.course_sk theo course_id)"]
        D_INST["gold.dim_instructor<br/>(Lookup i.instructor_sk theo instructor_id)"]
        D_METH["gold.dim_payment_method<br/>(Lookup m.method_sk theo method_id)"]
        D_DATE["gold.dim_date<br/>(Tạo date_sk = toYYYYMMDD(paid_at))"]
        D_USER["gold.dim_user (SCD2)<br/>⚡ ASOF JOIN: paid_at >= u.valid_from<br/>(Lấy đúng user_sk tại thời điểm trả tiền)"]
    end

    subgraph CALC["TÍNH TOÁN ĐỘ ĐO PHÁI SINH"]
        FORMULA["net_vnd = charged_vnd * (1 - refunded)<br/>• Nếu refunded = 1: net_vnd = 0 đ<br/>• Nếu refunded = 0: net_vnd = charged_vnd"]
    end

    subgraph TARGET["BẢNG FACT ĐÍCH (GOLD)"]
        F_PAY[("gold.fact_payments<br/>(Transaction Fact - 500k dòng)<br/>• payment_id, transaction_id, enrollment_id<br/>• user_sk, course_sk, instructor_sk, method_sk, date_sk<br/>• paid_at, original_vnd, discount_vnd, charged_vnd, refunded<br/>• net_vnd (Doanh thu thuần)")]
    end

    S_PAY --> LOOKUP
    D_COUR --> F_PAY
    D_INST --> F_PAY
    D_METH --> F_PAY
    D_DATE --> F_PAY
    D_USER --> F_PAY
    S_PAY --> FORMULA --> F_PAY
```

---

## 6. SƠ ĐỒ 5: LUỒNG BẢNG FACT TIẾN ĐỘ GHI DANH & TỐT NGHIỆP (`fact_enrollments`)

Khác với thanh toán, ghi danh là **Accumulating Snapshot Fact** (theo dõi tiến độ tích lũy từ lúc nhập học đến khi tốt nghiệp). Bảng này sử dụng **Role-Playing Dimension** cho chiều thời gian:

```mermaid
flowchart TD
    subgraph SRC["NGUỒN SỰ KIỆN GHI DANH"]
        S_ENR["silver.enrollments<br/>• enrollment_id<br/>• user_id, course_id<br/>• enrolled_at (ngày bắt đầu)<br/>• completed_at (ngày tốt nghiệp, có thể NULL)<br/>• lessons_completed (số bài xong)<br/>• updated_at"]
    end

    subgraph LOOKUP["LOOKUP SURROGATE KEYS & ROLE-PLAYING DATE"]
        D_COUR["gold.dim_course<br/>(Lookup course_sk, instructor_sk)"]
        D_USER["gold.dim_user (SCD2)<br/>⚡ ASOF JOIN: enrolled_at >= u.valid_from<br/>(Lấy user_sk tại thời điểm ghi danh)"]
        D_DATE1["dim_date (Role 1: Ngày ghi danh)<br/>• enrolled_date_sk = toYYYYMMDD(enrolled_at)"]
        D_DATE2["dim_date (Role 2: Ngày tốt nghiệp)<br/>• completed_date_sk = toYYYYMMDD(completed_at)<br/>• Nếu NULL: gán = 0 (Unknown Date)"]
    end

    subgraph CALC["TÍNH TOÁN CỜ HOÀN THÀNH"]
        FLAG["is_completed = 1 (nếu completed_at IS NOT NULL)<br/>is_completed = 0 (nếu đang học dở)"]
    end

    subgraph TARGET["BẢNG FACT ĐÍCH (GOLD)"]
        F_ENR[("gold.fact_enrollments<br/>(Accumulating Snapshot Fact - 500k dòng)<br/>• enrollment_id<br/>• user_sk, course_sk, instructor_sk<br/>• enrolled_date_sk, completed_date_sk<br/>• enrolled_at, completed_at<br/>• lessons_completed, is_completed, updated_at")]
    end

    S_ENR --> LOOKUP
    D_COUR --> F_ENR
    D_USER --> F_ENR
    D_DATE1 --> F_ENR
    D_DATE2 --> F_ENR
    S_ENR --> FLAG --> F_ENR
```

---

## 7. SƠ ĐỒ 6: LUỒNG BẢNG FACT HOÀN THÀNH BÀI GIẢNG (`fact_lesson_completions`)

Đây là bảng sự kiện có quy mô lớn nhất hệ thống (**khoảng 4.2 triệu dòng**), ghi lại hành vi xem video bài học của học viên:

```mermaid
flowchart TD
    subgraph SRC["NGUỒN SỰ KIỆN HỌC BÀI"]
        S_LESS["silver.lesson_completions<br/>• completion_id, enrollment_id<br/>• user_id, course_id, lesson_id<br/>• completed_at, time_spent_seconds"]
    end

    subgraph LOOKUP["LOOKUP SURROGATE KEYS"]
        D_COUR["gold.dim_course<br/>(Lookup course_sk)"]
        D_LESS["gold.dim_lesson<br/>(Lookup lesson_sk)"]
        D_DATE["gold.dim_date<br/>(date_sk = toYYYYMMDD(completed_at))"]
        D_USER["gold.dim_user (SCD2)<br/>⚡ ASOF JOIN: completed_at >= u.valid_from<br/>(Lấy user_sk lúc học xong bài)"]
    end

    subgraph TARGET["BẢNG FACT ĐÍCH (GOLD)"]
        F_LCOMP[("gold.fact_lesson_completions<br/>(Transaction Fact - 4.19M dòng)<br/>• completion_id, enrollment_id<br/>• user_sk, course_sk, lesson_sk, date_sk<br/>• completed_at<br/>• time_spent_seconds (Thời gian học thực tế)")]
    end

    S_LESS --> LOOKUP
    D_COUR --> F_LCOMP
    D_LESS --> F_LCOMP
    D_DATE --> F_LCOMP
    D_USER --> F_LCOMP
    LOOKUP --> TARGET
```

---

## 8. SƠ ĐỒ 7: LUỒNG BẢNG FACT KẾT QUẢ THI TRẮC NGHIỆM (`fact_quiz_attempts`)

Ghi nhận kết quả làm bài thi trắc nghiệm đánh giá năng lực (**khoảng 1.03 triệu dòng**):

```mermaid
flowchart TD
    subgraph SRC["NGUỒN SỰ KIỆN THI THỬ"]
        S_QUIZ["silver.quiz_attempts<br/>• attempt_id, enrollment_id<br/>• user_id, course_id, quiz_id<br/>• attempt_number, attempted_at<br/>• correct_count, total_questions, time_spent_seconds"]
    end

    subgraph LOOKUP["LOOKUP SURROGATE KEYS"]
        D_COUR["gold.dim_course<br/>(Lookup course_sk)"]
        D_QUIZ["gold.dim_quiz<br/>(Lookup quiz_sk)"]
        D_DATE["gold.dim_date<br/>(date_sk = toYYYYMMDD(attempted_at))"]
        D_USER["gold.dim_user (SCD2)<br/>⚡ ASOF JOIN: attempted_at >= u.valid_from<br/>(Lấy user_sk lúc nộp bài)"]
    end

    subgraph CALC["TÍNH TOÁN CỜ ĐỖ KỲ THI"]
        FLAG["is_passed = 1 (nếu correct_count * 100 >= total_questions * 70)<br/>is_passed = 0 (nếu làm đúng dưới 70%)"]
    end

    subgraph TARGET["BẢNG FACT ĐÍCH (GOLD)"]
        F_QATT[("gold.fact_quiz_attempts<br/>(Transaction Fact - 1.03M dòng)<br/>• attempt_id, enrollment_id<br/>• user_sk, course_sk, quiz_sk, date_sk<br/>• attempted_at, attempt_number<br/>• correct_count, total_questions, time_spent_seconds<br/>• is_passed (1: Đạt, 0: Trượt)")]
    end

    S_QUIZ --> LOOKUP
    D_COUR --> F_QATT
    D_QUIZ --> F_QATT
    D_DATE --> F_QATT
    D_USER --> F_QATT
    S_QUIZ --> FLAG --> F_QATT
```

---

## 9. SƠ ĐỒ 8: LUỒNG TỰ ĐỘNG TỔNG HỢP BÁO CÁO SIÊU TỐC (AGGREGATE FEEDS)

Sau khi 4 bảng Fact nạp xong, hệ thống nạp tiếp 2 bảng tổng hợp tính toán sẵn (**Aggregate Feeds**) để phục vụ báo cáo với tốc độ dưới **4 mili-giây**:

```mermaid
flowchart LR
    subgraph FACTS["BẢNG FACT ĐÃ NẠP"]
        F_PAY["gold.fact_payments<br/>(500k dòng giao dịch)"]
        F_ENR["gold.fact_enrollments<br/>(500k dòng tiến độ)"]
    end

    subgraph AGG["BẢNG TỔNG HỢP TÍNH SẴN (AGGREGATE FEEDS)"]
        AGG_REV[("gold.agg_monthly_revenue<br/>• Engine: SummingMergeTree ORDER BY month<br/>• Chỉ số: gmv, discount_vnd, refund_vnd, net_vnd<br/>• Phản hồi truy vấn: 3.9 ms")]
        AGG_ENR[("gold.agg_course_completion<br/>• Engine: SummingMergeTree ORDER BY course_sk<br/>• Chỉ số: enrollments, completions, completion_days<br/>• Phản hồi truy vấn: 1.2 ms")]
    end

    F_PAY -->|"GROUP BY month = toYYYYMM(paid_at)"| AGG_REV
    F_ENR -->|"GROUP BY course_sk"| AGG_ENR
```

---

## 10. BẢNG MA TRẬN TỔNG HỢP ĐỐI CHIẾU NGUỒN - ĐÍCH

| STT | Đối tượng Gold | Loại bảng | Nguồn Silver chính | Các Dimension được JOIN để lấy SK | Công thức / Quy tắc biến đổi cốt lõi |
| :-: | :--- | :--- | :--- | :--- | :--- |
| **1** | `dim_date` | Chiều | *ClickHouse `numbers(1096)`* | *Không có* | Sinh 1.096 ngày lịch (2022–2024) + dòng `date_sk = 0` (Unknown). |
| **2** | `dim_user` | Chiều (SCD2)| `silver.user_history` | *Không có* | `user_sk = history_id + 10M`, gán `is_current = (valid_to = 2100-01-01)`. |
| **3** | `dim_course` | Chiều | `silver.courses` | *Không có* | `course_sk = course_id + 1M`, nén `category` & `difficulty`. |
| **4** | `dim_instructor` | Chiều | `silver.instructors` | *Không có* | `instructor_sk = instructor_id + 2M`, nén `expertise`. |
| **5** | `dim_lesson` | Chiều | `silver.lessons` | *Không có* | `lesson_sk = lesson_id + 3M`, lưu thứ tự bài `position` (1..10). |
| **6** | `dim_quiz` | Chiều | `silver.quizzes` | *Không có* | `quiz_sk = quiz_id + 4M`, lưu `total_questions` (20 câu). |
| **7** | `dim_payment_method`| Chiều | `silver.payment_methods`| *Không có* | `method_sk = method_id + 5M` (`bank_transfer`, `card`, `wallet`). |
| **8** | `fact_payments` | Sự kiện | `silver.payments` | `dim_course`, `dim_instructor`, `dim_payment_method`, `dim_user` (ASOF), `dim_date` | $\text{net\_vnd} = \text{charged\_vnd} \times (1 - \text{refunded})$. |
| **9** | `fact_enrollments` | Sự kiện | `silver.enrollments` | `dim_course`, `dim_instructor`, `dim_user` (ASOF), `dim_date` (Role 1 & 2) | Role-playing date (`completed_date_sk = 0` nếu chưa xong); cờ `is_completed`. |
| **10**| `fact_lesson_completions`| Sự kiện | `silver.lesson_completions`| `dim_course`, `dim_lesson`, `dim_user` (ASOF), `dim_date` | Lưu `time_spent_seconds` thời lượng học thực tế. |
| **11**| `fact_quiz_attempts` | Sự kiện | `silver.quiz_attempts` | `dim_course`, `dim_quiz`, `dim_user` (ASOF), `dim_date` | Gán `is_passed = 1` nếu điểm $\ge 70\%$ ($\ge 14/20$ câu đúng). |
| **12**| `agg_monthly_revenue`| Tổng hợp | `gold.fact_payments` | *Không có* | `SummingMergeTree` gom nhóm theo tháng phát sinh doanh thu. |
| **13**| `agg_course_completion`| Tổng hợp | `gold.fact_enrollments` | *Không có* | `SummingMergeTree` gom nhóm theo khóa học để tính tỷ lệ hoàn thành. |
