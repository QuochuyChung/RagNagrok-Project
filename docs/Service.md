# TỔNG QUAN KẾT NỐI FASTAPI, QDRANT, OLLAMA, LANGCHAIN VÀ OPEN WEBUI

## 1. Mục tiêu

Tài liệu này trình bày tổng quan về vai trò và cách kết nối các thành phần trong một hệ thống RAG chạy cục bộ, gồm:

* FastAPI;
* Qdrant;
* Ollama;
* LangChain;
* Open WebUI.

Nội dung tập trung vào kiến trúc kết nối và các API chính. Chi tiết triển khai và cơ chế hoạt động của từng thành phần được trình bày trong các tài liệu riêng.

---

## 2. Kiến trúc tổng quan

```text
Người dùng
    ↓
Open WebUI
    ↓ HTTP
FastAPI Gateway
    ↓
LangChain
    ├── Ollama Embedding API
    ├── Qdrant API
    └── Ollama LLM API
```

FastAPI là điểm tiếp nhận request chính. LangChain điều phối quá trình tạo embedding, truy xuất dữ liệu từ Qdrant và gọi mô hình ngôn ngữ trên Ollama. Open WebUI cung cấp giao diện để người dùng tương tác với hệ thống.

---

## 3. Vai trò của các thành phần

### 3.1. FastAPI

FastAPI đóng vai trò API Gateway của hệ thống.

Nhiệm vụ chính:

* Nhận request từ Open WebUI hoặc ứng dụng client;
* Cung cấp các endpoint nạp tài liệu, tìm kiếm và chat;
* Kiểm tra thông tin tenant;
* Gọi LangChain để xử lý pipeline RAG;
* Trả kết quả về dưới dạng JSON.

Một số endpoint tiêu biểu:

| Phương thức | Endpoint     | Chức năng                    |
| ----------- | ------------ | ---------------------------- |
| GET         | `/health`    | Kiểm tra trạng thái hệ thống |
| GET         | `/version`   | Kiểm tra phiên bản API       |
| POST        | `/documents` | Nạp tài liệu                 |
| POST        | `/retrieve`  | Tìm kiếm nội dung liên quan  |
| POST        | `/chat`      | Hỏi đáp theo ngữ cảnh        |

FastAPI mặc định chạy tại:

```text
http://localhost:8000
```

Tài liệu Swagger:

```text
http://localhost:8000/docs
```

---

### 3.2. Qdrant

Qdrant là nơi lưu trữ vector embedding và metadata của tài liệu.

Nhiệm vụ chính:

* Lưu vector của các đoạn tài liệu;
* Tìm kiếm các vector gần nhất với câu hỏi;
* Trả về nội dung và metadata liên quan;
* Phân tách dữ liệu giữa các tenant bằng collection hoặc metadata filter.

Qdrant hỗ trợ REST API, gRPC và Python client.

Địa chỉ mặc định:

```text
http://localhost:6333
```

Qdrant thường chỉ được gọi từ FastAPI hoặc LangChain, không được người dùng gọi trực tiếp.

---

### 3.3. Ollama

Ollama cung cấp hai nhóm chức năng chính:

1. Tạo embedding từ văn bản;
2. Sinh câu trả lời bằng mô hình ngôn ngữ lớn.

Địa chỉ mặc định:

```text
http://localhost:11434
```

API tạo embedding:

```text
POST /api/embed
```

Ví dụ:

```json
{
  "model": "nomic-embed-text",
  "input": "Nội dung cần chuyển thành vector"
}
```

API sinh văn bản:

```text
POST /api/generate
```

Ví dụ:

```json
{
  "model": "llama3.2",
  "prompt": "Câu hỏi và ngữ cảnh"
}
```

Các API trên do Ollama cung cấp sẵn, không phải endpoint do FastAPI định nghĩa.

---

### 3.4. LangChain

LangChain là lớp điều phối giữa FastAPI, Qdrant và Ollama.

Nhiệm vụ chính:

* Gọi Ollama để tạo embedding;
* Gửi vector đến Qdrant để tìm kiếm;
* Nhận các đoạn tài liệu liên quan;
* Xây dựng prompt từ câu hỏi và context;
* Gọi Ollama LLM để sinh câu trả lời;
* Trả kết quả và nguồn tham khảo cho FastAPI.

LangChain thường được sử dụng dưới dạng thư viện Python bên trong ứng dụng FastAPI, không chạy như một dịch vụ độc lập.

---

### 3.5. Open WebUI

Open WebUI là giao diện tương tác dành cho người dùng.

Nhiệm vụ chính:

* Nhận câu hỏi hoặc tài liệu từ người dùng;
* Gửi request đến FastAPI;
* Hiển thị câu trả lời và nguồn tham khảo.

Trong kiến trúc này, Open WebUI nên kết nối với FastAPI thay vì gọi trực tiếp Qdrant.

Việc gọi Ollama trực tiếp phù hợp với chat LLM thông thường. Tuy nhiên, với hệ thống RAG có kiểm soát tenant, retrieval và citation, request nên đi qua FastAPI.

---

## 4. Luồng kết nối chính

### 4.1. Nạp tài liệu

```text
Open WebUI
    ↓ POST /documents
FastAPI
    ↓
LangChain
    ↓
Ollama Embedding API
    ↓
Qdrant
```

Quy trình tổng quát:

1. Người dùng gửi tài liệu đến FastAPI.
2. FastAPI xử lý tài liệu và chia nội dung thành các đoạn.
3. LangChain gọi Ollama để tạo embedding.
4. FastAPI hoặc LangChain lưu embedding và metadata vào Qdrant.
5. FastAPI trả trạng thái xử lý cho người dùng.

---

### 4.2. Truy xuất dữ liệu

```text
Open WebUI
    ↓ POST /retrieve
FastAPI
    ↓
LangChain
    ↓
Ollama Embedding API
    ↓
Qdrant Search
```

Quy trình tổng quát:

1. Người dùng gửi câu truy vấn.
2. Ollama chuyển câu truy vấn thành vector.
3. Qdrant tìm các đoạn tài liệu có vector gần nhất.
4. FastAPI trả danh sách kết quả và metadata.

---

### 4.3. RAG Chat

```text
Open WebUI
    ↓ POST /chat
FastAPI
    ↓
LangChain
    ├── Ollama Embedding API
    ├── Qdrant Search
    └── Ollama LLM API
```

Quy trình tổng quát:

1. Người dùng gửi câu hỏi đến FastAPI.
2. LangChain tạo embedding cho câu hỏi.
3. Qdrant trả về các đoạn tài liệu liên quan.
4. LangChain kết hợp câu hỏi với context để tạo prompt.
5. Ollama sinh câu trả lời dựa trên prompt.
6. FastAPI trả câu trả lời và citation cho Open WebUI.

---

## 5. Giao tiếp giữa các thành phần

| Thành phần nguồn | Thành phần đích | Cách giao tiếp                |
| ---------------- | --------------- | ----------------------------- |
| Open WebUI       | FastAPI         | HTTP REST API                 |
| FastAPI          | LangChain       | Python API                    |
| LangChain        | Ollama          | HTTP API hoặc Python client   |
| LangChain        | Qdrant          | REST, gRPC hoặc Python client |
| FastAPI          | Qdrant          | Python client hoặc REST API   |
| FastAPI          | Open WebUI      | JSON response                 |

---

## 6. Ví dụ API Gateway

### Gửi câu hỏi

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: tenant_001" \
  -d '{
    "prompt": "FastAPI có vai trò gì trong hệ thống?"
  }'
```

Ví dụ phản hồi:

```json
{
  "answer": "FastAPI đóng vai trò API Gateway của hệ thống.",
  "citations": [
    {
      "document": "architecture.md",
      "chunk_id": 3
    }
  ]
}
```

### Kiểm tra trạng thái

```bash
curl "http://localhost:8000/health"
```

Ví dụ phản hồi:

```json
{
  "status": "healthy",
  "services": {
    "qdrant": "up",
    "ollama": "up"
  }
}
```

---

## 7. Cổng dịch vụ đề xuất

| Dịch vụ         | Cổng mặc định |
| --------------- | ------------: |
| FastAPI         |        `8000` |
| Qdrant REST API |        `6333` |
| Ollama API      |       `11434` |
| Open WebUI      |  Tùy cấu hình |

Các dịch vụ có thể được triển khai và kết nối trong cùng một Docker network. Khi đó, các container nên gọi nhau bằng tên service thay vì `localhost`.

Ví dụ:

```text
http://qdrant:6333
http://ollama:11434
http://api:8000
```

---

## 8. Kết luận

Trong hệ thống RAG:

* **Open WebUI** là giao diện người dùng;
* **FastAPI** là API Gateway và điểm kiểm soát request;
* **LangChain** điều phối pipeline RAG;
* **Ollama** cung cấp embedding model và LLM;
* **Qdrant** lưu trữ và tìm kiếm vector.

Luồng kết nối chính là:

```text
Open WebUI → FastAPI → LangChain → Qdrant và Ollama
```

Cách tổ chức này giúp tách biệt giao diện, API, xử lý RAG, mô hình AI và lưu trữ vector, đồng thời thuận tiện cho việc mở rộng, kiểm soát tenant và quản lý hệ thống.
