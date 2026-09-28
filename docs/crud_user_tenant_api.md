# Tài Liệu Quản Lý Endpoints CRUD User / Tenant


## 1. Xác thực & Phân quyền chung (Authentication & Authorization)

Tất cả các endpoint CRUD dưới đây đều thuộc phiên bản API `/v1` và yêu cầu xác thực bằng Bearer Token.

*   **Header bắt buộc**: `Authorization: Bearer <JWT_TOKEN>`
*   **Cơ chế hoạt động**: Middleware [jwt_auth.py](file:///home/phucbuif/projects/ragnarok-multi-tenant-rag-api-gateway/app/middleware/jwt_auth.py) sẽ giải mã token để lấy thông tin `role`, `tenant_id` và gán vào request state.
*   **Các Role hợp lệ**:
    1.  `PLATFORM_ADMIN`: Quản trị viên toàn hệ thống. Có quyền quản lý tất cả các Tenants và Users trên mọi Tenants.
    2.  `TENANT_ADMIN`: Quản trị viên của một Tenant cụ thể. Chỉ được phép thao tác với dữ liệu và Users thuộc Tenant của mình.
    3.  `USER`: Người dùng thông thường trong Tenant. Chỉ có quyền truy cập thông tin hạn chế (ví dụ: xem thông tin tài khoản của chính mình).

---

## 2. Các Lỗi Chung Hệ Thống (Common API Errors)

Khi API gặp lỗi, phản hồi sẽ trả về mã trạng thái HTTP thích hợp kèm theo JSON body theo định dạng chuẩn dưới đây:

```json
{
  "error_code": "MA_LOI",
  "message": "Mô tả chi tiết nguyên nhân lỗi.",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "timestamp": "2026-07-08T10:26:08Z"
}
```

### Bảng danh sách lỗi xác thực & phân quyền:
| HTTP Status | Error Code | Nguyên nhân |
| :--- | :--- | :--- |
| **401 Unauthorized** | `UNAUTHORIZED` | Thiếu header `Authorization` hoặc không có tiền tố `Bearer `. |
| **401 Unauthorized** | `TOKEN_EXPIRED` | Token JWT đã hết hạn sử dụng. |
| **401 Unauthorized** | `INVALID_TOKEN` | Token JWT bị lỗi cấu trúc hoặc sai chữ ký bảo mật. |
| **403 Forbidden** | `FORBIDDEN` | Người dùng đã đăng nhập nhưng không có Role thích hợp để gọi API này. |
| **422 Unprocessable Entity** | `VALIDATION_ERROR` | Request body không khớp với Schema định nghĩa (ví dụ: thiếu thuộc tính bắt buộc, sai định dạng UUID, mật khẩu quá ngắn). |
| **500 Internal Server Error** | `INTERNAL_SERVER_ERROR` | Lỗi xảy ra không xác định trong hệ thống Backend. |

---

## 3. Endpoints CRUD Tenant (Quản lý Khách thuê)
*Định nghĩa tại: [tenants.py](file:///home/phucbuif/projects/ragnarok-multi-tenant-rag-api-gateway/app/api/routes/tenants.py)*

### 3.1. Tạo mới Tenant (`POST /v1/tenants`)
Tạo một tenant mới trong Postgres và đồng thời khởi tạo collection vector tương ứng trên Qdrant.

*   **Require Role?**: `PLATFORM_ADMIN`
*   **Input (JSON Body - [TenantCreate](file:///home/phucbuif/projects/ragnarok-multi-tenant-rag-api-gateway/app/schemas/tenant.py#L15-L40))**:
    ```json
    {
      "name": "Team Auto Test"
    }
    ```
    *   `name` (string, required): Tên hiển thị của tenant (độ dài từ 1 đến 255 ký tự).
*   **Output (JSON - [TenantResponse](file:///home/phucbuif/projects/ragnarok-multi-tenant-rag-api-gateway/app/schemas/tenant.py#L42-L70) - 201 Created)**:
    ```json
    {
      "id": "c8a41031-64d8-4f81-807e-3ca3733cc856",
      "name": "Team Auto Test",
      "qdrant_collection": "COL_c8a41031_64d8_4f81_807e_3ca3733cc856",
      "is_active": true,
      "created_at": "2026-07-08T10:26:08Z",
      "updated_at": "2026-07-08T10:26:08Z"
    }
    ```
*   **Raise Lỗi?**:
    *   `401 Unauthorized` (`UNAUTHORIZED` / `TOKEN_EXPIRED` / `INVALID_TOKEN`)
    *   `403 Forbidden` (`FORBIDDEN`): Nếu tài khoản không phải `PLATFORM_ADMIN`.
    *   `409 Conflict` (`TENANT_ALREADY_EXISTS`): Nếu ID của tenant bị trùng lắp trong DB.
    *   `422 Unprocessable Entity` (`VALIDATION_ERROR`): Nếu `name` trống hoặc vượt quá 255 ký tự.
    *   `500 Internal Server Error` (`QDRANT_CREATION_FAILED`): Gặp lỗi khi tạo collection trên Qdrant DB.

---

### 3.2. Lấy danh sách tất cả Tenants (`GET /v1/tenants`)
Lấy thông tin của toàn bộ các Tenants đang hoạt động.

*   **Require Role?**: `PLATFORM_ADMIN`
*   **Input**: Không yêu cầu dữ liệu gửi lên.
*   **Output (JSON - [TenantListResponse](file:///home/phucbuif/projects/ragnarok-multi-tenant-rag-api-gateway/app/schemas/tenant.py#L72-L97) - 200 OK)**:
    ```json
    {
      "tenants": [
        {
          "id": "c8a41031-64d8-4f81-807e-3ca3733cc856",
          "name": "Team Auto Test",
          "qdrant_collection": "COL_c8a41031_64d8_4f81_807e_3ca3733cc856",
          "is_active": true,
          "created_at": "2026-07-08T10:26:08Z",
          "updated_at": "2026-07-08T10:26:08Z"
        }
      ],
      "total": 1
    }
    ```
*   **Raise Lỗi?**:
    *   `401 Unauthorized` / `403 Forbidden`
    *   `500 Internal Server Error` (`INTERNAL_SERVER_ERROR`)

---

### 3.3. Xem chi tiết Tenant (`GET /v1/tenants/{tenant_id}`)
Truy vấn thông tin của một Tenant cụ thể thông qua ID của Tenant đó.

*   **Require Role?**: `PLATFORM_ADMIN` hoặc `TENANT_ADMIN`
*   **Input**:
    *   Path Parameter: `tenant_id` (UUID, required)
*   **Output (JSON - [TenantResponse](file:///home/phucbuif/projects/ragnarok-multi-tenant-rag-api-gateway/app/schemas/tenant.py#L42-L70) - 200 OK)**:
    ```json
    {
      "id": "c8a41031-64d8-4f81-807e-3ca3733cc856",
      "name": "Team Auto Test",
      "qdrant_collection": "COL_c8a41031_64d8_4f81_807e_3ca3733cc856",
      "is_active": true,
      "created_at": "2026-07-08T10:26:08Z",
      "updated_at": "2026-07-08T10:26:08Z"
    }
    ```
*   **Raise Lỗi?**:
    *   `401 Unauthorized` / `403 Forbidden`
    *   `404 Not Found` (`TENANT_NOT_FOUND`): Nếu không tìm thấy Tenant có ID tương ứng hoặc Tenant đó đã bị xóa mềm.

---

### 3.4. Xóa Tenant (`DELETE /v1/tenants/{tenant_id}`)
Thực hiện xóa mềm Tenant trong DB (chuyển trạng thái `is_active` thành false / `is_deleted = true`) và xóa collection tương ứng trên Qdrant.

*   **Require Role?**: `PLATFORM_ADMIN`
*   **Input**:
    *   Path Parameter: `tenant_id` (UUID, required)
*   **Output**: `204 No Content` (Trống)
*   **Raise Lỗi?**:
    *   `401 Unauthorized` / `403 Forbidden`
    *   `404 Not Found` (`TENANT_NOT_FOUND`): Nếu không tìm thấy Tenant để xóa.
    *   `500 Internal Server Error`: Nếu có lỗi xảy ra trong database Postgres hoặc kết nối Qdrant bị từ chối.

---

## 4. Endpoints CRUD User (Quản lý Người dùng)
*Định nghĩa tại: [users.py](file:///home/phucbuif/projects/ragnarok-multi-tenant-rag-api-gateway/app/api/routes/users.py)*

### 4.1. Tạo mới User (`POST /v1/users`)
Tạo một tài khoản người dùng mới thuộc một Tenant được chỉ định. Tên đăng nhập (`user_name`) phải là duy nhất trong toàn hệ thống.

*   **Require Role?**: `PLATFORM_ADMIN` hoặc `TENANT_ADMIN`
*   **Input (JSON Body - [UserCreate](file:///home/phucbuif/projects/ragnarok-multi-tenant-rag-api-gateway/app/schemas/user.py#L20-L69))**:
    ```json
    {
      "user_name": "john_doe",
      "email": "john.doe@example.com",
      "password": "s3cur3P@ssword",
      "tenant_id": "c8a41031-64d8-4f81-807e-3ca3733cc856",
      "role_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
    }
    ```
    *   `user_name` (string, required): Tên đăng nhập (3 - 255 ký tự, không được chứa khoảng trắng).
    *   `email` (string, optional): Địa chỉ email (tối đa 255 ký tự). Mặc định là `null`.
    *   `password` (string, required): Mật khẩu chưa băm (8 - 128 ký tự).
    *   `tenant_id` (UUID, required): ID của Tenant sở hữu người dùng này.
    *   `role_id` (UUID, required): ID của Role (Quyền) được gán cho người dùng này.
*   **Output (JSON - [UserResponse](file:///home/phucbuif/projects/ragnarok-multi-tenant-rag-api-gateway/app/schemas/user.py#L76-L105) - 201 Created)**:
    *Mật khẩu không bao giờ được trả về ở dữ liệu đầu ra.*
    ```json
    {
      "user_id": "a9a3b743-16a4-4a2b-8a88-294b0d061262",
      "user_name": "john_doe",
      "email": "john.doe@example.com",
      "tenant_id": "c8a41031-64d8-4f81-807e-3ca3733cc856",
      "role_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
      "is_active": true,
      "created_at": "2026-07-08T10:26:08Z",
      "updated_at": "2026-07-08T10:26:08Z"
    }
    ```
*   **Raise Lỗi?**:
    *   `401 Unauthorized` / `403 Forbidden`
    *   `409 Conflict` (`USER_ALREADY_EXISTS`): Nếu username đã tồn tại trên hệ thống.
    *   `422 Unprocessable Entity` (`VALIDATION_ERROR`):
        *   Mật khẩu ít hơn 8 ký tự.
        *   Tên đăng nhập chứa khoảng trắng.
        *   Thiếu các trường thông tin bắt buộc hoặc định dạng UUID không chuẩn.

---

### 4.2. Lấy danh sách Users (`GET /v1/users`)
Truy vấn toàn bộ danh sách tài khoản người dùng đang kích hoạt (`is_active = true`).

*   **Require Role?**: `PLATFORM_ADMIN` hoặc `TENANT_ADMIN`
*   **Phân quyền lọc dữ liệu tự động**:
    *   Nếu là **`PLATFORM_ADMIN`**: Trả về toàn bộ danh sách users của **tất cả** các Tenants trong hệ thống.
    *   Nếu là **`TENANT_ADMIN`**: Chỉ trả về danh sách users thuộc về **cùng một Tenant** với tài khoản admin đang đăng nhập.
*   **Input**: Không yêu cầu dữ liệu gửi lên.
*   **Output (JSON - [UserListResponse](file:///home/phucbuif/projects/ragnarok-multi-tenant-rag-api-gateway/app/schemas/user.py#L107-L134) - 200 OK)**:
    ```json
    {
      "users": [
        {
          "user_id": "a9a3b743-16a4-4a2b-8a88-294b0d061262",
          "user_name": "john_doe",
          "email": "john.doe@example.com",
          "tenant_id": "c8a41031-64d8-4f81-807e-3ca3733cc856",
          "role_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
          "is_active": true,
          "created_at": "2026-07-08T10:26:08Z",
          "updated_at": "2026-07-08T10:26:08Z"
        }
      ],
      "total": 1
    }
    ```
*   **Raise Lỗi?**:
    *   `401 Unauthorized` / `403 Forbidden`
    *   `500 Internal Server Error` (`INTERNAL_SERVER_ERROR`)

---

### 4.3. Xem chi tiết User (`GET /v1/users/{user_id}`)
Truy cập thông tin chi tiết của một người dùng theo mã định danh UUID.

*   **Require Role?**: `PLATFORM_ADMIN`, `TENANT_ADMIN`, hoặc `USER`
*   **Input**:
    *   Path Parameter: `user_id` (UUID, required)
*   **Output (JSON - [UserResponse](file:///home/phucbuif/projects/ragnarok-multi-tenant-rag-api-gateway/app/schemas/user.py#L76-L105) - 200 OK)**:
    ```json
    {
      "user_id": "a9a3b743-16a4-4a2b-8a88-294b0d061262",
      "user_name": "john_doe",
      "email": "john.doe@example.com",
      "tenant_id": "c8a41031-64d8-4f81-807e-3ca3733cc856",
      "role_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
      "is_active": true,
      "created_at": "2026-07-08T10:26:08Z",
      "updated_at": "2026-07-08T10:26:08Z"
    }
    ```
*   **Raise Lỗi?**:
    *   `401 Unauthorized` / `403 Forbidden`
    *   `404 Not Found` (`USER_NOT_FOUND`): Nếu không tồn tại user tương ứng hoặc tài khoản đó đã bị vô hiệu hóa (`is_active = false`).

---

### 4.4. Vô hiệu hóa User / Xóa mềm (`DELETE /v1/users/{user_id}`)
Khóa tài khoản của người dùng bằng cách gán `is_active = false`. Thông tin người dùng vẫn được lưu lại trong cơ sở dữ liệu để phục vụ mục đích đối soát/audit.

*   **Require Role?**: `PLATFORM_ADMIN` hoặc `TENANT_ADMIN`
*   **Input**:
    *   Path Parameter: `user_id` (UUID, required)
*   **Output**: `204 No Content` (Trống)
*   **Raise Lỗi?**:
    *   `401 Unauthorized` / `403 Forbidden`
    *   `404 Not Found` (`USER_NOT_FOUND`): Nếu không tìm thấy người dùng hoặc tài khoản đó đã ở trạng thái ngừng hoạt động sẵn từ trước.
    *   `500 Internal Server Error` (`INTERNAL_SERVER_ERROR`)

## 5. Endpoints Email Invitation (Quản lý Lời mời)
*Định nghĩa tại: [invitations.py](file:///home/phucbuif/projects/ragnarok-multi-tenant-rag-api-gateway/app/api/routes/invitations.py) và [auth.py](file:///home/phucbuif/projects/ragnarok-multi-tenant-rag-api-gateway/app/api/routes/auth.py)*

### 5.1. Mời người dùng hàng loạt (POST /v1/tenants/{tenant_id}/invitations/bulk)
Mời một hoặc nhiều người dùng gia nhập Tenant. Tài khoản người dùng sẽ được tạo sẵn ở trạng thái vô hiệu hóa (is_active = false) cùng một mật khẩu mã hóa ngẫu nhiên (không sử dụng được). Hệ thống sau đó sẽ gửi email chứa token một lần (single-use token) tới các user này.

*   **Require Role?**: PLATFORM_ADMIN hoặc TENANT_ADMIN (TENANT_ADMIN chỉ mời được vào Tenant của họ).
*   **Input**: Nhận vào danh sách email/tên người dùng, hoặc phân tích trực tiếp từ file CSV.
*   **Output**: 202 Accepted (Tiến trình gửi email chạy bất đồng bộ).

### 5.2. Chấp nhận lời mời & Đặt mật khẩu (POST /v1/auth/invitations/accept)
Hoàn tất quy trình giới thiệu (onboarding). Xác thực token một lần, cho phép người dùng đặt mật khẩu mới, và kích hoạt tài khoản (is_active = true). Sau khi thành công, token đó sẽ bị hủy vĩnh viễn.

*   **Require Role?**: Bất kỳ ai (Public)
*   **Input**: JSON chứa 	oken và 
ew_password.
*   **Output**: Thông báo thành công và người dùng có thể chuyển tới endpoint /v1/auth/login.
