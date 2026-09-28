# Tìm Hiểu FastAPI & API Gateway Pattern
> Framework · Routing · Pydantic · Dependency Injection · Lifespan · Gateway Pattern

---

## 1. FastAPI là gì?

FastAPI là một **web framework hiện đại cho Python** để xây dựng REST API — nhanh, tự sinh tài liệu Swagger và hỗ trợ `async/await` native. Nó được xây dựng trên:

- **Starlette** — ASGI framework xử lý HTTP, middleware, routing
- **Pydantic** — validate và serialize dữ liệu tự động từ Python type hints

### Tại sao RAGnarok dùng FastAPI?

| Đặc điểm | Lý do chọn |
|----------|-----------|
| **Async native** | Gọi Qdrant, Ollama đều là I/O — `async/await` giúp xử lý concurrent mà không block |
| **Pydantic validation** | Request/response schema tự động validate, không cần viết if/else thủ công |
| **Tự sinh Swagger UI** | Mở `/docs` là test được ngay, không cần Postman |
| **Type hints = docs sống** | Code đồng thời là tài liệu, IDE hỗ trợ autocomplete đầy đủ |

---

## 2. Cài đặt

```bash
pip install fastapi uvicorn[standard] httpx pydantic
```

> **Uvicorn** là **ASGI server** — là thứ thật sự nhận HTTP request từ bên ngoài và chuyển vào ứng dụng FastAPI. FastAPI là framework, Uvicorn là server chạy nó.

### Kiểm tra đã cài chưa

```bash
python -c "import fastapi; print(fastapi.__version__)"
uvicorn --version
```

### Khởi động server

```bash
# Dev mode — tự reload khi code thay đổi
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

- `main` — tên file `main.py`
- `app` — tên biến `app = FastAPI()` bên trong file đó
- `--reload` — chỉ dùng khi dev, **không dùng production**

### Kiểm tra server đang chạy

```bash
curl http://localhost:8000/docs     # Swagger UI
curl http://localhost:8000/health   # Health endpoint
```

---

## 3. Ứng dụng FastAPI cơ bản

```python
from fastapi import FastAPI

app = FastAPI(
    title="RAGnarok Gateway",
    version="1.0.0",
    description="Multi-Tenant RAG API Gateway"
)

@app.get("/")
async def root():
    return {"message": "RAGnarok is running"}
```

### Truy cập tài liệu tự sinh

Sau khi chạy server, mở trình duyệt:

| URL | Mô tả |
|-----|-------|
| `http://localhost:8000/docs` | Swagger UI — tương tác được, có nút "Try it out" |
| `http://localhost:8000/redoc` | ReDoc — đẹp hơn, chỉ đọc |
| `http://localhost:8000/openapi.json` | Raw OpenAPI schema (JSON) |

---

## 4. Pydantic — Schema & Validation

Pydantic cho phép định nghĩa **cấu trúc dữ liệu bằng Python class**. FastAPI tự động validate request/response dựa trên class đó. Nếu client gửi sai kiểu, FastAPI trả về `422 Unprocessable Entity` với thông báo lỗi chi tiết — không cần viết thủ công.

### Định nghĩa schema

```python
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# Request schema — validate dữ liệu đầu vào
class ChatRequest(BaseModel):
    query: str                        # bắt buộc
    top_k: int = 5                    # optional, có default
    stream: bool = False
    session_id: Optional[str] = None  # hoàn toàn tùy chọn

# Response schema — định hình dữ liệu trả về
class HealthResponse(BaseModel):
    status: str          # "healthy" | "degraded" | "unhealthy"
    timestamp: datetime
    version: str
    services: Optional[dict] = None  # chỉ có khi debug=True
```

### Dùng trong endpoint

```python
@app.post("/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    # FastAPI tự parse body JSON → ChatRequest object
    # Nếu thiếu field 'query' hoặc top_k không phải int → 422 tự động
    print(request.query)   # đã validated, đúng kiểu str
    print(request.top_k)   # đã validated, đúng kiểu int
    ...
```

> **Lưu ý:** Khai báo `response_model=ChatResponse` giúp FastAPI tự sinh schema response trong Swagger UI và tự lọc các field không khai báo trước khi trả về client.

---

## 5. Router — Tách endpoint theo module

Khi dự án lớn, để tất cả endpoint trong `main.py` sẽ khó maintain. `APIRouter` cho phép tách thành các module riêng.

### Tạo Router trong module riêng

```python
# routes/health.py
from fastapi import APIRouter

# tags dùng để nhóm endpoint trong Swagger UI
router = APIRouter(tags=["Infrastructure"])

@router.get("/health")
async def health_check():
    return {"status": "healthy"}

@router.get("/version")
async def get_version():
    return {"version": "1.0.0"}
```

### Đăng ký Router vào app chính

```python
# main.py
from fastapi import FastAPI
from routes.health import router as health_router
from routes.chat import router as chat_router

app = FastAPI()

app.include_router(health_router)             # → /health, /version
app.include_router(chat_router, prefix="/v1") # → /v1/chat, /v1/retrieve
```

> **Tại sao `/health` không có prefix `/v1`?** Vì load balancer và Kubernetes probe cần gọi `/health` mà không cần token hay header — đặt ở root tách biệt khỏi các API có authentication.

---

## 6. Lifespan — Khởi tạo tài nguyên dùng chung

Một số tài nguyên như `httpx.AsyncClient`, database connection pool cần được **tạo một lần khi app khởi động** và **đóng khi app tắt**. Tạo mới trong mỗi request sẽ tốn tài nguyên và không tận dụng được connection pooling.

```python
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── STARTUP ──────────────────────────────────
    app.state.http_client = httpx.AsyncClient()

    yield  # app đang chạy bình thường

    # ── SHUTDOWN ─────────────────────────────────
    await app.state.http_client.aclose()

app = FastAPI(lifespan=lifespan)
```

### Lấy tài nguyên dùng chung trong endpoint

```python
from fastapi import Request

@app.get("/health")
async def health_check(request: Request):
    # Lấy client đã được tạo sẵn từ lifespan — không tạo mới
    http_client = request.app.state.http_client
    resp = await http_client.get("http://qdrant:6333/healthz")
    ...
```

---

## 7. Dependency Injection — `Depends()`

FastAPI có hệ thống DI built-in. Thay vì lặp lại logic trong từng endpoint (đọc settings, validate header, lấy DB connection...), ta viết một hàm dependency và FastAPI tự inject vào.

### Inject Settings

```python
from functools import lru_cache
from fastapi import Depends
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_version: str = "1.0.0"
    qdrant_url: str = "http://qdrant:6333"
    ollama_url: str = "http://ollama:11434"
    debug_mode: bool = False

    class Config:
        env_file = ".env"  # đọc từ file .env tự động

@lru_cache  # cache — chỉ tạo Settings object một lần
def get_settings() -> Settings:
    return Settings()

@app.get("/version")
async def get_version(settings: Settings = Depends(get_settings)):
    return {"version": settings.app_version}
```

### Validate header X-Tenant-ID (dùng từ Sprint 2)

```python
from fastapi import Header, HTTPException, Depends

async def require_tenant(x_tenant_id: str = Header(...)):
    # Header(...) — bắt buộc phải có, nếu thiếu → 422 tự động
    if len(x_tenant_id) < 3:
        raise HTTPException(status_code=400, detail="X-Tenant-ID không hợp lệ")
    return x_tenant_id

@app.post("/v1/chat")
async def chat(
    request: ChatRequest,
    tenant_id: str = Depends(require_tenant)
):
    # tenant_id đã được validate và inject, không cần xử lý thêm
    ...
```

---

## 8. API Gateway Pattern

### Là gì?

**API Gateway** là một điểm vào duy nhất (single entry point) cho toàn bộ request từ client. Thay vì client gọi trực tiếp vào Qdrant, Ollama, LangChain — client chỉ giao tiếp với FastAPI Gateway, và gateway điều phối phía sau.

```
Không có Gateway:
  Client ──► Qdrant :6333
  Client ──► Ollama :11434
  Client ──► LangChain

Có Gateway:
  Client ──► FastAPI :8000 ──► Qdrant
                           ──► Ollama
                           ──► LangChain
```

### Kiến trúc RAGnarok

```
┌──────────────────────────────────────────────────────────┐
│                      CLIENT                              │
│             (Open WebUI / curl / browser)                │
└─────────────────────────┬────────────────────────────────┘
                          │ HTTP :8000
                          ▼
┌──────────────────────────────────────────────────────────┐
│                  FastAPI GATEWAY                         │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  /health     │  │ /v1/ingest   │  │  /v1/chat     │  │
│  │  /version    │  │ /v1/docs     │  │  /v1/retrieve │  │
│  └──────────────┘  └──────────────┘  └───────────────┘  │
│                                                          │
│  Middleware: X-Tenant-ID · Logging · Error handling      │
└───────┬──────────────────┬──────────────────┬────────────┘
        │                  │                  │
        ▼                  ▼                  ▼
   ┌─────────┐       ┌──────────┐       ┌──────────┐
   │ Qdrant  │       │  Ollama  │       │LangChain │
   │  :6333  │       │  :11434  │       │ (in-proc)│
   └─────────┘       └──────────┘       └──────────┘
```

### Trách nhiệm của Gateway

| Trách nhiệm | Mô tả | Liên quan Sprint |
|-------------|-------|-----------------|
| **Routing** | Điều hướng request đến đúng service | Sprint 1 |
| **Authentication** | Kiểm tra `X-Tenant-ID` header | Sprint 2 |
| **Validation** | Validate request schema bằng Pydantic | Sprint 1 |
| **Aggregation** | Kết hợp kết quả từ Qdrant + Ollama | Sprint 3+ |
| **Error handling** | Chuẩn hóa lỗi trả về client | Sprint 4 |
| **Observability** | Logging có cấu trúc, health check, metrics | Sprint 4 |

### Tại sao không để client gọi thẳng vào service?

| Không có Gateway | Có Gateway |
|-----------------|------------|
| Client phải biết IP/port của từng service | Client chỉ cần một địa chỉ duy nhất |
| Logic tenant isolation nằm rải rác | Tập trung tại middleware một lần |
| Khó thêm logging, rate limiting cho tất cả | Thêm một chỗ, áp dụng toàn bộ |
| Service thay đổi → client phải cập nhật | Thay đổi trong gateway, client không biết |

---

## 9. Chạy thử với curl

Sau khi stack đang chạy:

```bash
# Kiểm tra health
curl http://localhost:8000/health

# Kiểm tra health + chi tiết từng service
curl "http://localhost:8000/health?debug=true"

# Kiểm tra version
curl http://localhost:8000/version

# Mở Swagger UI (trên browser)
# http://localhost:8000/docs
```

### Response mẫu `/health?debug=true`

```json
{
  "status": "healthy",
  "timestamp": "2026-06-25T10:00:00Z",
  "version": "1.0.0",
  "services": {
    "qdrant":    { "status": "up", "latency_ms": 4.21 },
    "ollama":    { "status": "up", "latency_ms": 12.5 },
    "open_webui":{ "status": "up", "latency_ms": 8.73 }
  }
}
```

### Response mẫu `/version`

```json
{
  "version": "1.0.0",
  "api_version": "v1",
  "python_version": "3.11.9",
  "build_date": "2026-06-25",
  "git_commit": "a3f91bc"
}
```

---

## 10. Tổng Hợp Nhanh

| Concept | Một câu mô tả |
|---------|--------------|
| **FastAPI** | Web framework Python, async-native, tự sinh Swagger UI từ type hints |
| **Uvicorn** | ASGI server nhận HTTP request và chuyển vào FastAPI để xử lý |
| **Pydantic** | Validate request/response tự động dựa trên Python class — sai kiểu → 422 |
| **APIRouter** | Tách nhóm endpoint thành module riêng, mount vào app chính bằng `include_router` |
| **Lifespan** | Khởi tạo tài nguyên dùng chung (HTTP client) khi start, giải phóng khi shutdown |
| **Depends()** | Dependency injection — inject settings, auth, DB connection vào endpoint |
| **Gateway Pattern** | Single entry point — tập trung routing, auth, logging, error handling |
| **asyncio.gather** | Chạy nhiều coroutine song song, tổng latency = service chậm nhất (thay vì cộng dồn) |
| **HTTP 503** | Trả về khi service unhealthy để load balancer biết ngừng route traffic |

---

## 11. Checklist Tự Kiểm Tra

| # | Câu hỏi |
|---|---------|
| 1 | Uvicorn và FastAPI khác nhau thế nào? Cái nào là server, cái nào là framework? |
| 2 | FastAPI khác Flask ở điểm gì cốt lõi? Kể 2 lý do RAGnarok chọn FastAPI. |
| 3 | Pydantic làm gì tự động khi client gửi request sai kiểu dữ liệu? |
| 4 | `APIRouter` giải quyết vấn đề gì? Tại sao `/health` không có prefix `/v1`? |
| 5 | Tại sao nên tạo `httpx.AsyncClient` trong `lifespan` thay vì trong từng request? |
| 6 | `Depends()` hoạt động thế nào? Kể một use case cụ thể trong RAGnarok. |
| 7 | Gateway Pattern là gì? Kể 3 trách nhiệm của FastAPI Gateway trong RAGnarok. |
| 8 | `asyncio.gather` tiết kiệm được gì so với `await` tuần tự trong `/health`? |
| 9 | Tại sao `/health` trả HTTP 503 thay vì 200 khi status là "unhealthy"? |
| 10 | `_get_git_commit()` dùng fallback strategy như thế nào? Tại sao không crash khi git không có? |

---

*Tài liệu tham khảo: [FastAPI Documentation](https://fastapi.tiangolo.com/) · [Pydantic Documentation](https://docs.pydantic.dev/)*
