# Mô tả Script Kiểm thử Tenants & Users CRUD

Script `3_crud_user_tenant_check.sh` thực hiện kiểm thử tự động toàn diện các API liên quan đến quản lý Tenants, Users và xác thực (Authentication).


## Các Test Cases

### 0. Đăng nhập hệ thống (Auth)
* Sử dụng tài khoản Platform Admin (`platform0` / `123456`) để lấy JWT access token dùng cho tất cả các request phía sau.

### 1. Quản lý Tenant (Tenants CRUD Endpoints)
* **[1.1.1] Create a Tenant:** Tạo Tenant mới có tên `"Team Auto Test"` thành công.
* **[1.1.2] List All Active Tenants:** Lấy danh sách toàn bộ các Tenant đang hoạt động.
* **[1.1.3] Get Specific Tenant:** Truy vấn Tenant vừa tạo theo ID.
* **[1.2.1] List Tenants Including Inactive:** Lấy danh sách Tenant bao gồm cả những Tenant đã bị ẩn/xóa.
* **[1.3.1] Create Tenant Duplicate:** Kiểm tra lỗi trùng lặp khi cố tình tạo Tenant cùng tên.
* **[1.4.3] Invalid Tenant Name:** Kiểm tra validation lỗi khi truyền tên Tenant trống `""`.
* **[1.1.4] Soft-Delete a Tenant:** Xóa mềm Tenant vừa tạo.
* **[1.3.2] Get Deleted Tenant:** Truy vấn Tenant đã bị xóa mềm (kỳ vọng trả về mã lỗi `404`).

### 2. Quản lý User (Users CRUD Endpoints)
* **[2.1.1] Create a User:** Tạo mới User trong Tenant (gửi kèm header `X-Tenant-ID`).
* **[2.3.1] Create User Duplicate Username (Error Case):** Kiểm tra lỗi trùng username trong cùng một Tenant.
* **[2.4.1] Password Minimum Length Violation (Boundary Case):** Kiểm tra validation lỗi khi mật khẩu ngắn hơn 8 ký tự.
* **[2.4.2] Invalid Email/Username Format (Boundary Case):** Kiểm tra validation lỗi định dạng email hoặc tên chứa khoảng trắng.



