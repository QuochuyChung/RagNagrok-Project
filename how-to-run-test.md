# Hướng dẫn khởi động và kiểm thử Sprint 2

## Git workflow

Không làm việc trực tiếp trên `main`.

Quy trình tạo branch mới cho mỗi task:

```bash
# lấy code mới nhất từ develop 
git switch develop
git pull origin develop

# hoặc lấy code mới nhất từ nhánh mà mình cần

git switch <ten-branch>
git pull origin <ten-branch>

git switch -c feature/<ten-task>
```

Quy trình merge branch khác vào branch mình:

```bash
# Cập nhật code mới nhất từ nhánh cần merge (ví dụ: develop)
git switch develop
git pull origin develop

# Chuyển về nhánh của bạn và tiến hành merge
git switch feature/<ten-task>
git merge develop
```

Sau khi hoàn thành:

```bash
git status
git add .
git commit -m "feat: describe the change"
git push -u origin feature/<ten-task>
```

Sau đó tạo Pull Request:

```text
feature/<ten-task> → main
```

Một thành viên khác review và chạy thử trước khi merge.

Sau khi merge:

```bash
git switch main
git pull origin main
git branch -d feature/<ten-task>
```

Quy ước tên branch:

```bash
feature/...   chức năng mới
fix/...       sửa lỗi
test/...      kiểm thử
docs/...      tài liệu
chore/...     cấu hình hoặc bảo trì
```

Ví dụ commit message:

```bash
feat: add health endpoint
build: add Docker Compose stack
test: add Sprint 1 smoke test
docs: update setup instructions
fix: correct gateway port mapping
```

---

## Chuẩn bị môi trường

- Cần đặt repository trong filesystem của WSL2, ví dụ:

```bash
mkdir -p ~/projects
cd ~/projects
git clone <repository-url>
cd multi-tenant-rag-gateway
```

- Kiểm tra:

```bash
docker version
docker compose version
git --version
curl --version
```

## Các bước để khởi động cho dự án:

### 1. Check health:

- 1/ Tạo môi trường ảo:

```bash
python3 -m venv .venv
source .venv/bin/activate


# pip install -r requirements.txt

# Thoát venv
# deactivate

```

- 2/ Tạo file cấu hình môi trường:

```bash
cp .env.example .env
```

- 3/ Build và chạy toàn bộ stack:

```bash
docker compose up --build -d
```

- 4/ Kiểm tra container:

```bash
docker compose ps
```

- 5/ Initial data gồm tài khoảng và mật khẩu:
Có mặc định 3 tài khoản và 1 tenant:
    - user_name: user0, tenant0, platform0
    - Mật khẩu: 12345678
    - roles: USER, tenant_admin, platform_admin

```bash
# Xóa dữ liệu cũ và nạp lại dữ liệu mồi mặc định
docker compose exec gateway python scripts/reset_and_seed_db.py

# Nạp dữ liệu các lớp học mẫu (Hello World, Hội bàn tròn, Mushealy, Six Senses, RAGnarok)
# docker compose exec gateway python scripts/seed_Class.py
```

- 7/ Kiểm tra health check:

```bash
cd scripts/curl_examples

chmod +x 1_health_check.sh

# kiểm tra toàn bộ containers
./1_health_check.sh

./1_health_check.sh --debug

# kiểm tra login
chmod +x 2_1_login_check.sh

./2_1_login_check.sh

# Kiểm tra authentication for all API
chmod +x 2_2_auth_check.sh

./2_2_auth_check.sh  

# Kiểm tra CRUD User
chmod +x 3_crud_user_tenant_check.sh

./3_crud_user_tenant_check.sh

# Kiểm tra CRUD tenant
```
```bash
docker logs ragnarok-gateway-1 --tail 50 | jq -R 'fromjson? // .'

```
-----

- Swagger UI:

```bash
http://localhost:8000/docs
```

- Qdran UI:
```bash
http://localhost:6333/dashboard 
```

- UI frontend:

```bash
http://localhost:5173
```
- UI mailPit:

```bash
http://localhost:8025
```


### 2. Quản lý Database & Migration (Alembic)

#### 2.1. Quy trình thường ngày (Dành cho mọi thành viên)
Khi các thành viên khác đẩy code thay đổi cấu trúc Database (Migration mới) lên Git, bạn KHÔNG cần xóa DB làm lại. Chỉ cần chạy 2 lệnh sau để đồng bộ Database của bạn:

```bash
# 1. Kéo code và file migration mới về
git pull

# 2. Cập nhật Database của bạn (chỉ chạy những file migration còn thiếu)
docker compose exec gateway alembic upgrade head
```

#### 2.2. Onboarding — Lần đầu setup Database trên máy mới (Hoặc Xóa trắng làm lại)
Nếu bạn mới clone project hoặc muốn xóa sạch Database cũ để làm lại từ đầu cho "sạch sẽ":

*Lưu ý: Nhờ cấu hình tự động chạy migration tích hợp sẵn trong `compose.yaml`, các bảng và cột mới nhất sẽ tự động được đồng bộ và tạo lập khi khởi chạy container `gateway` mà không cần chạy các script SQL gốc hay stamp thủ công.*

```bash
# 1. (Tùy chọn) Xóa trắng toàn bộ Database hiện tại nếu muốn làm lại từ đầu
docker compose exec postgres psql -U ragnarok -d rag_db -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# 2. Khởi động lại container gateway để tự động áp dụng toàn bộ các file migration (Alembic)
docker compose restart gateway

# 3. Kiểm tra để đảm bảo Database đã đồng bộ 100% với Codebase
docker compose exec gateway alembic check
# Output mong đợi: "No new upgrade operations detected"
```

#### 2.3. Quy trình thay đổi Schema (Dành cho người sửa Model)
Khi bạn sửa code trong `app/models/` (thêm cột, đổi kiểu dữ liệu...) và muốn tạo Migration mới chia sẻ cho team:

```bash
# 1. Sinh migration tự động từ sự khác biệt giữa Model và Database
docker compose exec gateway alembic revision --autogenerate -m "mô tả thay đổi ngắn gọn"

# 2. MỞ FILE MIGRATION VỪA SINH TRONG migrations/versions/ VÀ KIỂM TRA LẠI
#    (Vì tính năng autogenerate không hoàn hảo, ví dụ rename cột sẽ bị hiểu là drop + add)

# 3. Apply thay đổi đó lên DB của chính bạn
docker compose exec gateway alembic upgrade head

# 4. Kiểm tra xem DB và Model đã khớp hoàn toàn chưa
docker compose exec gateway alembic check

# 5. Commit cả code model (.py) và file migration mới sinh ra đẩy lên Git
```

#### 2.4. Các lệnh tiện ích thường dùng khác
```bash
docker compose exec gateway alembic current            # Xem DB đang ở bản migration nào
docker compose exec gateway alembic history            # Xem danh sách toàn bộ migration từ trước đến nay
docker compose exec gateway alembic downgrade -1       # Lùi lại 1 phiên bản migration (cẩn thận mất dữ liệu)

# Dừng container nhưng GIỮ LẠI dữ liệu Database:
docker compose down

# Xóa cả container và XÓA HẲN dữ liệu Database (Volume):
docker compose down -v
```

#### 2.5. Test dữ liệu nhanh bằng pgAdmin + Swagger
```Bash
pgAdmin connection:
Host = 127.0.0.1 (Nếu Windows chiếm cổng, dùng IP WSL 172.x.x.x)
Port = 5432
Database = rag_db
Username = ragnarok
Password = ragnarok_secret
```

Trong pgAdmin Query Tool, bạn có thể insert thử tenant:
```sql
INSERT INTO tenants (tenant_name, collection_name, is_deleted)
VALUES ('Team Alpha', 'tenant_team_alpha', false)
ON CONFLICT (collection_name) DO NOTHING
RETURNING tenant_id, tenant_name, collection_name, is_deleted;
```

### 3. Chạy dữ liệu mồi (Seed Data) - User & Tenant

Dự án cung cấp script `scripts/seed_UserTenant.py` để tự động khởi tạo dữ liệu mẫu cho Database (PostgreSQL) và Vector DB (Qdrant). Tài liệu này đặc biệt hữu ích cho các **Developers** muốn có ngay một môi trường đầy đủ dữ liệu để test API `/users` và `/tenants`.

#### 3.1. Tổng quan (Overview)
Script này sẽ tự động khởi tạo:
- **3 Roles mặc định**: `PLATFORM_ADMIN`, `TENANT_ADMIN`, `USER`.
- **5 Tenants**: Từ Team Alpha đến Team Epsilon, mỗi Tenant đi kèm 1 Collection thực tế trên Qdrant.
- **250 Users**: 50 Users phân bổ cho mỗi Tenant với phân quyền tương ứng. Mật khẩu mặc định là `123456`.

#### 3.2. Cấu hình (Configuration Options)
Script tự động đọc thông tin kết nối từ Docker Network. Tuy nhiên bạn có thể thay đổi các biến môi trường sau nếu chạy script ở một môi trường tách biệt:
- `DATABASE_URL`: Chuỗi kết nối đến PostgreSQL. (Mặc định trỏ về `ragnarok@localhost:5432`).
- `QDRANT_URL`: Chuỗi kết nối HTTP API đến Qdrant. (Mặc định `http://localhost:6333`).

#### 3.3. Cách sử dụng (Usage Examples)
Cách tốt nhất và an toàn nhất là chạy script **bên trong Docker container** của Gateway, vì gói thư viện `qdrant-client` đã được cài đầy đủ bên trong Image của dự án.

**Yêu cầu (Prerequisites):**
- Toàn bộ hệ thống Docker Compose phải đang chạy (`docker compose up -d`).
- Đã chạy Alembic migration (`alembic upgrade head`) để Database có đủ các bảng và cột mới nhất.

**Lệnh thực thi:**
```bash
docker compose exec -e DATABASE_URL="postgresql+asyncpg://ragnarok:ragnarok_secret@postgres:5432/rag_db" -e QDRANT_URL="http://qdrant:6333" gateway python scripts/seed_Class.py
```

#### 3.4. FAQ
- **Tôi có bị duplicate (trùng lặp) dữ liệu hoặc lỗi Crash DB nếu lỡ chạy script 2 lần liên tiếp không?**
  **Không.** Script được thiết kế theo cơ chế **Idempotent** (có tích hợp cờ `ON CONFLICT DO NOTHING`). Do đó, chạy kịch bản này nhiều lần là cực kì an toàn. Hệ thống sẽ tự động bỏ qua những dữ liệu cũ và chỉ thêm vào dữ liệu nào còn thiếu.
- **Tôi nên làm gì nếu cấu trúc Database bị thay đổi quá nhiều so với lúc đầu?**
  Bạn nên chạy lệnh `docker compose down -v` (để xóa trắng Volume cũ), sau đó chạy lại `docker compose up -d`, áp dụng schema mới với `alembic upgrade head`, và cuối cùng chạy lại Seed Script này để làm mới lại toàn bộ hệ thống từ con số không.
