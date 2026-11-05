# ==============================================================================
# ĐẶC TẢ CONTAINER RUNNER THỰC THI PIPELINE (RUNNER DOCKERFILE)
# ==============================================================================

# 1. BASE IMAGE: Sử dụng bản Python 3.12 rút gọn trên nền Debian 12 (Bookworm)
# Bản 'slim' giúp giảm dung lượng image từ ~1GB xuống chỉ còn ~150MB, loại bỏ các gói
# thừa để tăng tính bảo mật và giảm thiểu lỗ hổng bảo mật tiềm ẩn.
FROM python:3.12.8-slim-bookworm

# 2. THƯ MỤC LÀM VIỆC MẶC ĐỊNH
# Toàn bộ mã nguồn dự án sẽ được ánh xạ hoặc copy vào thư mục /app trong container.
WORKDIR /app

# 3. CHIẾN LƯỢC TỐI ƯU HÓA CACHE CỦA DOCKER (DOCKER LAYER CACHING)
# Copy riêng 2 file requirements trước. Nhờ đó, khi bạn sửa code Python bên ngoài,
# Docker sẽ KHÔNG phải cài đặt lại thư viện từ đầu, giúp lệnh build chạy chỉ mất 1 giây!
COPY requirements.txt requirements.lock.txt ./

# 4. CÀI ĐẶT CÁC THƯ VIỆN ĐÃ ĐƯỢC KHÓA PHIÊN BẢN
# Cờ '--no-cache-dir' giúp tránh lưu file nén wheel của pip, tiết kiệm thêm ~80MB ổ đĩa.
RUN pip install --no-cache-dir -r requirements.lock.txt

# 5. COPY TOÀN BỘ MÃ NGUỒN VÀO IMAGE
COPY . .

# 6. BIẾN MÔI TRƯỜNG BẮT BUỘC KHI CHẠY PYTHON TRONG DOCKER
# Tắt chế độ đệm xuất dữ liệu (Buffer). Mọi câu lệnh print() hoặc log lỗi sẽ được
# đẩy lập tức ra màn hình Terminal theo thời gian thực mà không bị trễ hay nuốt log.
ENV PYTHONUNBUFFERED=1

# 7. LỆNH MẶC ĐỊNH KHI KHỞI CHẠY CONTAINER
# Mặc định in ra hướng dẫn sử dụng của CLI điều phối.
CMD ["python", "cli.py", "--help"]
