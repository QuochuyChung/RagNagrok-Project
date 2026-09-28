# Multi-Tenant RAG API Gateway

Dự án xây dựng API Gateway cho hệ thống Multi-Tenant RAG.  
Trong Sprint 1, mục tiêu là tạo nền tảng gồm FastAPI, Qdrant, Ollama và Docker Compose.

## 1. Vị trí đặt source code

Nên đặt repository trong filesystem của WSL2, ví dụ:

```bash
mkdir -p ~/projects
cd ~/projects
git clone <repository-url>
cd multi-tenant-rag-gateway
```

Đường dẫn đề xuất:

```text
/home/<username>/projects/multi-tenant-rag-gateway
```

Không nên đặt source code tại:

```text
/mnt/c/Users/...
```

Việc đặt source code trực tiếp trong WSL2 thường giúp Docker, Git và các công cụ Linux hoạt động ổn định hơn.

Mở thư mục bằng VS Code:

```bash
code .
```

## 2. Cấu trúc thư mục

```bash
multi-tenant-rag-gateway/
├── DBScript.sql
├── Makefile
├── README.md
├── alembic.ini
├── app
│   ├── __init__.py
│   ├── __pycache__
│   │   ├── __init__.cpython-314.pyc
│   │   └── main.cpython-314.pyc
│   ├── api
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   │   ├── __init__.cpython-314.pyc
│   │   │   └── deps.cpython-314.pyc
│   │   ├── deps.py
│   │   └── routes
│   │       ├── __init__.py
│   │       ├── __pycache__
│   │       │   ├── __init__.cpython-314.pyc
│   │       │   ├── chat.cpython-314.pyc
│   │       │   ├── documents.cpython-314.pyc
│   │       │   ├── health.cpython-314.pyc
│   │       │   ├── retrieve.cpython-314.pyc
│   │       │   └── tenants.cpython-314.pyc
│   │       ├── chat.py
│   │       ├── documents.py
│   │       ├── health.py
│   │       ├── retrieve.py
│   │       └── tenants.py
│   ├── clients
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   │   ├── __init__.cpython-314.pyc
│   │   │   └── ollama_client.cpython-314.pyc
│   │   └── ollama_client.py
│   ├── core
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   │   ├── __init__.cpython-314.pyc
│   │   │   ├── config.cpython-314.pyc
│   │   │   ├── errors.cpython-314.pyc
│   │   │   └── logging.cpython-314.pyc
│   │   ├── config.py
│   │   ├── errors.py
│   │   └── logging.py
│   ├── main.py
│   ├── middleware
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   │   ├── __init__.cpython-314.pyc
│   │   │   └── request_id.cpython-314.pyc
│   │   └── request_id.py
│   ├── models
│   │   ├── __init__.py
│   │   ├── auditlog.py
│   │   ├── base.py
│   │   ├── chunk.py
│   │   ├── coversation.py
│   │   ├── document.py
│   │   ├── message.py
│   │   ├── role.py
│   │   ├── tenant.py
│   │   └── user.py
│   ├── repositories
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   │   ├── __init__.cpython-314.pyc
│   │   │   ├── document_repository.cpython-314.pyc
│   │   │   ├── qdrant_repository.cpython-314.pyc
│   │   │   └── tenant_repository.cpython-314.pyc
│   │   ├── document_repository.py
│   │   ├── qdrant_repository.py
│   │   └── tenant_repository.py
│   ├── schemas
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   │   ├── __init__.cpython-314.pyc
│   │   │   ├── chat.cpython-314.pyc
│   │   │   ├── common.cpython-314.pyc
│   │   │   ├── document.cpython-314.pyc
│   │   │   ├── health.cpython-314.pyc
│   │   │   ├── retrieve.cpython-314.pyc
│   │   │   └── tenant.cpython-314.pyc
│   │   ├── chat.py
│   │   ├── common.py
│   │   ├── document.py
│   │   ├── health.py
│   │   ├── retrieve.py
│   │   └── tenant.py
│   ├── services
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   │   ├── __init__.cpython-314.pyc
│   │   │   ├── auth_service.cpython-314.pyc
│   │   │   ├── chat_service.cpython-314.pyc
│   │   │   ├── document_service.cpython-314.pyc
│   │   │   ├── retrieval_service.cpython-314.pyc
│   │   │   └── tenant_service.cpython-314.pyc
│   │   ├── auth_service.py
│   │   ├── chat_service.py
│   │   ├── document_service.py
│   │   ├── retrieval_service.py
│   │   └── tenant_service.py
│   └── utils
│       ├── __init__.py
│       ├── __pycache__
│       │   ├── __init__.cpython-314.pyc
│       │   ├── hashing.cpython-314.pyc
│       │   └── time.cpython-314.pyc
│       ├── hashing.py
│       ├── parsers
│       │   ├── __init__.py
│       │   └── __pycache__
│       │       └── __init__.cpython-314.pyc
│       └── time.py
├── compose.yaml
├── docker
│   └── Dockerfile.gateway
├── docs
│   ├── Docker-WSL-v2.md
│   ├── FastAPI.md
│   ├── HTTP.txt
│   ├── Ollama.md
│   ├── Qdrant.md
│   ├── RAG-Basics.md
│   ├── Service.md
│   ├── api_contract.md
│   ├── git-workflow.md
│   ├── repo-x.txt
│   └── sprint_reports
│       └── sprint_2.md
├── first.md
├── migrations
│   ├── README
│   ├── env.py
│   ├── script.py.mako
│   └── versions
│       └── 8517dd8e0f39_first_migration_for_db.py
├── requirements.txt
├── scripts
│   ├── curl_examples
│   │   └── health_check.sh
│   ├── load_test.sh
│   └── smoke_test.sh
└── tests
    ├── __init__.py
    ├── integration
    │   └── __init__.py
    └── unit
        ├── __init__.py
        ├── test_hashing.py
        └── test_time.py
```

Ý nghĩa chính:

- `app/`: source code FastAPI.
- `docs/`: tài liệu dự án và báo cáo sprint.
- `scripts/`: script kiểm tra hoặc hỗ trợ chạy dự án.
- `compose.yaml`: khai báo các service Docker.
- `Dockerfile`: đóng gói FastAPI Gateway.
- `.env.example`: mẫu cấu hình môi trường.
- `requirements.txt`: thư viện Python.

## 3. Yêu cầu môi trường

- Windows với WSL2.
- Ubuntu chạy trên WSL2.
- Docker Desktop đã bật WSL Integration.
- Git và curl.

Kiểm tra:

```bash
docker version
docker compose version
git --version
curl --version
```

## 4. Khởi động dự án

Tạo môi trường ảo:

```bash
python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

# Thoát venv
# deactivate

```

Tạo file cấu hình môi trường:

```bash
cp .env.example .env
```

Build và chạy toàn bộ stack:

```bash
docker compose up --build -d
```

Kiểm tra container:

```bash
docker compose ps
```
Kiểm tra health check:

```bash
cd scripts/curl_examples

chmod +x health_check.sh

./health_check.sh

./health_check.sh --debug
```

Tiếp theo chuyển qua phần 9 Postgres

other detail:
Gateway:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/version
```

Qdrant:

```bash
curl http://localhost:6333/readyz
```

Ollama:

```bash
curl http://localhost:11434/api/version
```

Swagger UI:

```text
http://localhost:8000/docs
```

Hoặc chạy smoke test:

```bash
bash scripts/smoke_test.sh
```

## 6. Git workflow

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

## 7. Nguyên tắc làm việc nhóm

- Không push trực tiếp vào `main`.
- Mỗi task dùng một branch riêng.
- Pull Request nên nhỏ và tập trung vào một thay đổi.
- Ít nhất một thành viên khác review trước khi merge.
- Không commit `.env`, mật khẩu hoặc secret.
- `main` phải luôn ở trạng thái có thể chạy và demo.

## 8. Dừng hệ thống

Dừng container nhưng giữ dữ liệu:

```bash
docker compose down
```

Xóa cả container và volume:

```bash
docker compose down -v
```

Lưu ý: lệnh có `-v` sẽ xóa dữ liệu Qdrant và model Ollama đã lưu.

## 9. Database migration (Alembic)

Dự án dùng SQLAlchemy ORM (`app/models/`) + Alembic để quản lý schema PostgreSQL, áp dụng kiến trúc **Schema-per-tenant**.

Trong kiến trúc mới này, toàn bộ quá trình khởi tạo database được gom gọn vào **một migration duy nhất** (`8517dd8e0f39_first_migration_for_db.py`). Migration này sẽ chịu trách nhiệm:
1. Khởi tạo các bảng dùng chung (Users, Tenants, Roles, AuditLogs) trên schema `public`.
2. Định nghĩa hàm helper để tạo tự động các bảng riêng tư (Documents, Conversations) trên các schema của từng tenant.

Vì vậy, `DBScript.sql` đã trở nên lỗi thời và **KHÔNG CÒN ĐƯỢC SỬ DỤNG** để bootstrap database nữa. Mọi thao tác đều phải đi qua lệnh `alembic upgrade head`.

Alembic đọc connection string từ `.env` (qua `app/core/config.py`), nên cần cấu hình `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` trỏ đúng tới PostgreSQL của bạn.

### 9.1. Onboarding — Setup Database lần đầu (Kể cả máy mới)

```bash
cd ragnarok-multi-tenant-rag-api-gateway
pip install -r requirements.txt
```

Nếu Database của bạn **trống hoàn toàn** hoặc bạn muốn chạy lại từ đầu (nhớ drop database cũ), bạn chỉ cần gõ lệnh sau để tạo toàn bộ bảng trong schema `public`:

```bash
alembic upgrade head
```

Sau khi chạy xong, lệnh `alembic current` phải trả về `8517dd8e0f39 (head)`. Tới đây Database của bạn đã sẵn sàng. Không cần chạy lệnh stamp hay script SQL thủ công nào khác.

### 9.2. Quy trình thay đổi schema (người tạo thay đổi)

> [!WARNING]
> Do kiến trúc Schema-per-tenant, Alembic `autogenerate` chỉ được cấu hình để quét schema `public` nhằm tránh sinh ra code trùng lặp cho mỗi schema của các tenant khác nhau. Mọi thay đổi đối với các model của tenant (ví dụ `documents`, `conversations`) thì **không thể sử dụng autogenerate** mà phải tự viết tay script migration DDL.

```bash
# 1. Sửa ORM model trong app/models/
# 2. Sinh migration từ diff (CHỈ HIỆU QUẢ VỚI BẢNG PUBLIC)
alembic revision --autogenerate -m "mô tả thay đổi"
# 3. MỞ FILE MIGRATION VỪA SINH TRONG migrations/versions/ VÀ REVIEW
# 4. Apply lên DB của mình
alembic upgrade head
# 5. Test nhanh sau khi apply
alembic current            # phải ra revision mới nhất (head)
# 6. Commit cả model + file migration trong cùng 1 PR
```

Test dữ liệu nhanh bằng pgAdmin + Swagger:

```text
pgAdmin connection:
Host = 127.0.0.1
Port = 5432
Database = rag_db
Username = ragnarok
Password = ragnarok_secret
```

Nếu Windows đang có `postgres.exe` chiếm `127.0.0.1:5432`, dùng IP WSL
`172.x.x.x` thay cho `127.0.0.1`.

Trong pgAdmin Query Tool, insert tenant test:

```sql
INSERT INTO tenants (tenant_name, collection_name, is_deleted)
VALUES ('Team Alpha', 'tenant_team_alpha', false)
ON CONFLICT (collection_name) DO NOTHING
RETURNING tenant_id, tenant_name, collection_name, is_deleted;
```

Copy `tenant_id` trả về, mở Swagger tại `http://localhost:8000/docs`, rồi gọi
`GET /v1/tenants/{tenant_id}` để kiểm tra API đọc đúng dữ liệu từ PostgreSQL.

### 9.3. Quy trình khi pull code có migration mới (mọi người còn lại)

```bash
git pull
alembic upgrade head
```

### 9.4. Lệnh thường dùng

```bash
alembic current            # DB đang ở revision nào
alembic history            # danh sách toàn bộ migration
alembic check              # phát hiện model và DB lệch nhau (drift)
alembic downgrade -1       # lùi 1 migration (cẩn thận với dữ liệu)
```

### 9.5. Luật làm việc nhóm với migration

- **Chỉ có duy nhất một file migration khởi tạo (`8517dd8e0f39`)**: Không chỉnh sửa các lệnh DDL khởi tạo của file migration này nếu hệ thống đã chạy trên Production. Nếu ở dev/local, khi schema lỗi, tốt nhất drop database rồi chạy lại.
- Không sửa DB bằng tay (psql/pgAdmin). 
- Hai branch cùng tạo migration → sau khi merge, Alembic báo "multiple heads":
  người merge chạy `alembic merge heads -m "merge"` rồi `upgrade head`.
- File migration đã push lên `main` thì không sửa/xóa — muốn đổi thì tạo migration mới.

## 10. Chạy dữ liệu mồi (Seed Data)

Dự án cung cấp script `scripts/seed_UserTenant.py` để tự động tạo dữ liệu mẫu cho Database (PostgreSQL) và Vector DB (Qdrant).

### 10.1. Cấu trúc dữ liệu mồi

- **Roles**: 3 roles mặc định (PLATFORM_ADMIN, TENANT_ADMIN, USER).
- **Tenants**: 5 tenants (Team Alpha đến Team Epsilon), mỗi tenant có một Collection riêng trên Qdrant.
- **Users**: 250 users (50 users mỗi tenant).
- **Mật khẩu mặc định**: `Password@123`

### 10.2. Cách chạy script qua Docker (Khuyên dùng)

Vì script cần kết nối đồng thời với PostgreSQL và Qdrant, đồng thời thư viện `qdrant-client` đã được cài sẵn bên trong Docker container của Gateway, cách tốt nhất và an toàn nhất là chạy lệnh trực tiếp bên trong container thông qua Docker Compose.

**Yêu cầu (Prerequisites):** 
- Hệ thống Docker Compose phải đang chạy (`docker compose up -d`).
- Đã chạy Alembic migration để DB có đầy đủ các cột mới nhất (`alembic upgrade head`).

**Lệnh thực thi:**
```bash
docker compose exec -e DATABASE_URL="postgresql+asyncpg://ragnarok:ragnarok_secret@postgres:5432/rag_db" -e QDRANT_URL="http://qdrant:6333" gateway python scripts/seed_UserTenant.py
```

### 10.3. Xử lý sự cố (Troubleshooting)

- **Lỗi `No module named 'qdrant_client'`**: 
  - *Nguyên nhân:* Xảy ra khi bạn chạy bằng lệnh `python` trực tiếp trên máy host (Windows/Mac) mà chưa cài thư viện này vào Virtual Env. 
  - *Cách xử lý:* Script đã tự động bắt lỗi và bỏ qua bước tạo Qdrant (Database vẫn được lưu bình thường). Tuy nhiên, để đồng bộ trọn vẹn cả hai hệ thống, hãy dùng lệnh `docker compose exec...` ở mục 10.2.
- **Lỗi Unicode / hiển thị ký tự lạ trên Windows**: 
  - *Nguyên nhân:* Console của Windows đôi khi không hỗ trợ các ký tự Unicode.
  - *Cách xử lý:* Bản script hiện tại đã được loại bỏ ký tự Unicode và chuẩn hóa về ASCII.

### 10.4. Best Practices

- **Idempotent**: Script đã được thiết kế đi kèm cờ `ON CONFLICT DO NOTHING`, do đó bạn có thể chạy script nhiều lần hoàn toàn an toàn mà không sợ trùng lặp dữ liệu hay crash hệ thống.
- **Môi trường**: Chỉ chạy script này trên môi trường **Local** hoặc **Development**. Tuyệt đối không chạy trên môi trường Production.
- **Reset Database**: Nếu Database thay đổi cấu trúc quá nhiều hoặc bạn muốn làm lại từ đầu, hãy chạy `docker compose down -v` để xóa trắng dữ liệu cũ, chạy lại `docker compose up -d`, `alembic upgrade head`, và chạy lệnh Seed này để có một hệ thống sạch sẽ hoàn toàn.
