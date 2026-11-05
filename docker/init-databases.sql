-- ==============================================================================
-- SCRIPT KHỞI TẠO CƠ SỞ DỮ LIỆU BAN ĐẦU CỦA POSTGRESQL (DOCKER ENTRYPOINT)
-- ==============================================================================
-- Mục đích:
-- Khi container PostgreSQL khởi động lần đầu tiên, biến môi trường POSTGRES_DB đã tạo
-- sẵn database tác nghiệp chính là 'learning_oltp'.
-- Script này được Docker tự động mount vào thư mục '/docker-entrypoint-initdb.d/'
-- để tạo thêm database thứ hai: 'dwh_staging'.
--
-- Ý nghĩa kiến trúc:
-- Phân tách ranh giới vật lý giữa:
--   1. 'learning_oltp': Cơ sở dữ liệu tác nghiệp (nguồn phát sinh giao dịch).
--   2. 'dwh_staging': Cơ sở dữ liệu trung chuyển dành riêng cho Data Warehouse
--      (chứa các schema: silver, staging, quarantine và benchmark).
-- ==============================================================================

CREATE DATABASE dwh_staging;
