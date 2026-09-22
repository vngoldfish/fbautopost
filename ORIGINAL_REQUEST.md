# Original User Request

## 2026-09-22T19:08:16Z

Nâng cấp toàn diện hệ thống FB Auto Post thành Nền Tảng Quản Trị & Vận Hành Đa Tài Khoản Facebook (Production-Grade Facebook Account Farm & Automation System). Quản lý tập trung trên Server Admin Console và thực thi phân tán qua các Extension Worker Node trên từng trình duyệt/máy tính cá nhân.

Working directory: C:\Users\Admin\Desktop\project\autofb
Integrity mode: development

## Requirements

### R1. Giao Diện Quản Trị Admin Sản Phẩm (Production SaaS Admin Console)
Xây dựng giao diện Admin Dashboard chuẩn SaaS cao cấp:
- Quản lý danh sách các Máy / Trình duyệt (Worker Nodes) với trạng thái Thời gian thực (Online / Offline / Đang chạy nhiệm vụ / IP / Thời gian tương tác cuối).
- Quản lý Hồ sơ Tài khoản Facebook (Nick / Fanpage / Group), phân loại theo Project / Worker Node.
- Quản lý Lịch đăng bài, Trạng thái bài viết, và Báo cáo tổng quan KPI theo thời gian thực (Dashboard Analytics).

### R2. Hệ Thống Hàng Đợi Nhiệm Vụ Phân Tấn (Distributed Task Queue Engine)
Xây dựng cơ chế phát lệnh & phân phối nhiệm vụ 2 chiều giữa Server và các Extension Worker:
- Server phân bổ nhiệm vụ (Đăng bài, Seeding, Tương tác nuôi nick) tới đúng Worker Node được gán (`projectKey` / `workerId`).
- Extension Worker liên tục nhận nhiệm vụ từ Task Queue, thực thi tự động ngầm trên tab Facebook và trả kết quả/lỗi chi tiết về Server.

### R3. Bộ Kịch Bản Nuôi Nick & Tương Tác Tự Động (Automation Warm-up & Engagement Suite)
Bổ sung các kịch bản tương tác ngầm giúp duy trì độ tin cậy (trust) cho từng tài khoản:
- Tự động lướt Newsfeed, thả thả tim/like bài viết ngẫu nhiên theo cấu hình tần suất.
- Tự động seeding bình luận, thả cảm xúc bài viết chỉ định.
- Tự động xử lý và cảnh báo khi tài khoản gặp sự cố (checkpoint, hết hạn token, cần reload tab).

### R4. Chuẩn Hóa Mã Nguồn & Triển Khai Docker VPS (Production Architecture & Deployment)
Tối ưu hóa Backend Python FastAPI, bảo mật Token API (`X-Sync-Token`, `X-Project-Key`), cấu trúc thư mục sạch sẽ và cập nhật bộ file Docker Compose 1-click deploy hoàn chỉnh cho VPS.

## Acceptance Criteria

### Giao Diện Quản Trị Admin & Worker Node Monitor
- [ ] Giao diện Admin hiển thị bảng danh sách các Extension Worker Node (Tên máy/Browser ID, Trạng thái kết nối, Số tài khoản đang giữ, Nhiệm vụ vừa chạy).
- [ ] Cho phép gán / chuyển đổi tài khoản và nhiệm vụ cho từng Worker Node trực quan.

### Hàng Đợi & Phân Phối Nhiệm Vụ
- [ ] Nhiệm vụ đăng bài và nuôi nick được lưu trong Task Queue và phân phối chính xác cho từng Worker Node mà không bị lặp hoặc sót bài.
- [ ] Mọi Extension Worker chạy ngầm ổn định, thực thi bài đăng via Direct GraphQL / DOM Fallback và cập nhật tiến trình hiển thị realtime trên Dashboard.

### Kịch Bản Nuôi Nick & Chống Block
- [ ] Worker Extension có thể bật/tắt chế độ Nuôi Nick tự động (Newsfeed scroll, random react).
- [ ] Hệ thống bắt lỗi chính xác và tự động thử lại hoặc cảnh báo khi tài khoản bị đăng xuất.

### Triển Khai & Kiểm Thử
- [ ] Mã nguồn Python Backend và Extension JavaScript hoàn toàn sạch lỗi syntax (`node -c` và `py_compile` thành công 100%).
- [ ] File `docker-compose.yml` và `Dockerfile` sẵn sàng cho việc deploy VPS chỉ với 1 câu lệnh.
