# Release Notes: Sprint 4 - Email Invitations (feature/s4-invitation)

### ✨ New Features (Tính năng mới)
1. **Hệ thống Email Invitation Token-Based**: Đã loại bỏ luồng cấp mật khẩu plain-text kém bảo mật. Giờ đây, hệ thống sinh ra một secure token (mã hóa SHA-256 dưới database) và gửi qua Email dưới dạng "Magic Link". Người dùng click vào link để tự điền mật khẩu mới.
2. **Mời hàng loạt (Bulk Invite) bằng CSV**: Hỗ trợ endpoint mới `POST /v1/tenants/{tenant_id}/invitations/bulk` cho phép Tenant Admin mời cùng lúc hàng chục nhân viên dựa trên danh sách array JSON hoặc file CSV, giúp tiết kiệm thời gian onboarding.
3. **Quản lý Vòng đời Lời mời**: Tenant Admin có quyền Liệt kê (List), Thu hồi (Revoke), và Gửi lại (Resend) lời mời cho những nhân viên chưa accept thông qua bộ Endpoints CRUD dành riêng cho Invitations.

### 🚨 Breaking Changes & Action Required (Thay đổi ảnh hưởng luồng cũ)
1. **Trạng thái Kích hoạt (is_active)**: Những tài khoản user được tạo thông qua lời mời sẽ được khởi tạo mặc định dưới Database với `is_active=False` (Tài khoản vô hiệu hóa). Họ tuyệt đối **KHÔNG THỂ login** vào hệ thống cho tới khi gọi API `POST /v1/auth/invitations/accept` để xác nhận token và đặt password.
2. **Biến môi trường mới (ENV)**: File `.env.example` và `compose.yaml` đã được cập nhật. Bạn phải bổ sung thêm cấu hình liên quan đến SMTP Server (như Host, Port, TLS, Username, Password) vào file `.env` local của bạn để luồng gửi Email có thể hoạt động.
3. **Database Migrations Mới**: Branch này bổ sung thêm 2 file migration mới để tạo bảng `invitation_tokens` và đồng bộ schema. Sau khi kéo code về, các thành viên **bắt buộc** phải chạy lệnh sau:
   ```bash
   alembic upgrade head
   ```
4. **Cập nhật Dependency**: Hãy đảm bảo chạy lại lệnh `pip install -r requirements.txt` để cài đặt các thư viện mới phục vụ luồng gửi email và parsing CSV.
