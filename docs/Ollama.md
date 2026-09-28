# Ollama — Tổng Quan & Hướng Dẫn Sử Dụng

---

## 1. Ollama là gì?

Ollama là tool cho phép chạy Large Language Model (LLM) **offline trên máy local** — không cần internet, không cần API key. Ví dụ như CHATGPT, thay vì gửi request lên server OpenAI, Ollama kéo model AI về máy và expose một HTTP API tại `localhost:11434` để các ứng dụng gọi trực tiếp.

Cách dễ nhớ: **Ollama = Docker nhưng cho AI model** — pull, list, rm đều tương tự.

**Vì sao nên dùng Ollama thay vì OpenAI API?**
- Chạy offline, không phụ thuộc dịch vụ bên ngoài
- Không tốn tiền gọi API
- Dễ tích hợp vào Docker Compose stack — expose sẵn HTTP, FastAPI gọi thẳng không cần SDK
- Hỗ trợ đủ hai loại model cần thiết: **chat** (Mistral) và **embedding** (nomic-embed-text)

---

## 2. Cài đặt

### Trên WSL2 / Linux

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Kiểm tra

```bash
# Kiểm tra version
ollama --version
# → ollama version is 0.x.x

# Kiểm tra service đang chạy
curl http://localhost:11434
# → Ollama is running
```

### Khởi động thủ công (nếu service chưa chạy)

```bash
ollama serve
```

---

## 3. Quản lý Model

```bash
# Pull model về
ollama pull mistral            # Chat LLM — ~4.4 GB
ollama pull nomic-embed-text   # Embedding model — ~274 MB

# Xem danh sách model đã có
ollama list

# Xóa model
ollama rm mistral
```

> **Quan trọng:** Mistral và nomic-embed-text là hai model với **hai nhiệm vụ hoàn toàn khác nhau**. Mistral dùng để generate text; nomic-embed-text dùng để tạo vector. Gọi Embed API với Mistral sẽ báo lỗi.

---

## 4. Ba API Cốt Lõi

Ollama expose ba endpoint chính, tất cả đều là `POST` request với JSON body.

| API | Endpoint | Input | Output |
|-----|----------|-------|--------|
| **Generate** | `POST /api/generate` | `prompt` (string) | text |
| **Chat** | `POST /api/chat` | `messages` (array) | text |
| **Embed** | `POST /api/embed` | `input` (string/array) | vector[] |

---

### 4.1 Generate API

Nhận một **prompt** đơn, trả về text. Mỗi request là độc lập — không có memory, không có history.

```bash
curl http://localhost:11434/api/generate -d '{
  "model": "mistral",
  "prompt": "What is RAG in AI?",
  "stream": false
}'
```

```json
{
  "model": "mistral",
  "response": "RAG (Retrieval-Augmented Generation) is a technique...",
  "done": true
}
```

**Dùng khi:** các tác vụ one-shot không cần context — summarize, classify, translate,...

---

### 4.2 Chat API

Nhận một **messages array**, hỗ trợ multi-turn conversation. Đây là nền tảng cho **Conversation Memory** trong RAGnarok.

```bash
curl http://localhost:11434/api/chat -d '{
  "model": "mistral",
  "messages": [
    {"role": "user", "content": "What is RAG?"}
  ],
  "stream": false
}'
```

```json
{
  "model": "mistral",
  "message": {
    "role": "assistant",
    "content": "RAG, or Retrieval-Augmented Generation, is..."
  },
  "done": true
}
```

**Multi-turn:** gửi kèm history trong `messages` array, model sẽ đọc toàn bộ context:

```bash
curl http://localhost:11434/api/chat -d '{
  "model": "mistral",
  "messages": [
    {"role": "user",      "content": "What is RAG?"},
    {"role": "assistant", "content": "RAG is Retrieval-Augmented Generation..."},
    {"role": "user",      "content": "Can you give me an example?"}
  ],
  "stream": false
}'
```

**Các role hợp lệ:**

| Role | Ý nghĩa |
|------|---------|
| `user` | Tin nhắn từ người dùng |
| `assistant` | Tin nhắn từ model (lịch sử) |
| `system` | Instruction/persona cho model — dùng để prompt engineering |

**Dùng khi:** chat app, Q&A có context, conversation memory,...

---

### 4.3 Embed API

Chuyển text thành **vector** — mảng số thực biểu diễn "nghĩa" của đoạn text trong không gian toán học. Hai đoạn text có nghĩa tương đồng → vector nằm gần nhau trong không gian đó.

```bash
curl http://localhost:11434/api/embed -d '{
  "model": "nomic-embed-text",
  "input": "Hello world"
}'
```

```json
{
  "model": "nomic-embed-text",
  "embeddings": [[-0.006, -0.001, -0.171, 0.008, ...]]
}
```

Vector trả về có **~768 chiều** — đây là thứ được lưu vào Qdrant để thực hiện semantic search.

Có thể embed nhiều input cùng lúc:

```bash
curl http://localhost:11434/api/embed -d '{
  "model": "nomic-embed-text",
  "input": ["First document", "Second document", "Third document"]
}'
```

**Dùng khi:**

| Bước | Tác vụ | Input | Output |
|------|--------|-------|--------|
| Indexing | Embed từng chunk tài liệu | Nội dung chunk | Vector → lưu vào Qdrant |
| Querying | Embed câu hỏi của user | Câu hỏi | Vector → search trong Qdrant |

---

## 5. Tham số `stream`

Tất cả API đều hỗ trợ `stream: true/false`.

| | `stream: false` | `stream: true` |
|---|---|---|
| **Cách hoạt động** | Chờ model generate xong → trả 1 JSON duy nhất | Trả từng chunk ngay khi có, chunk cuối có `"done": true` |
| **Dùng khi** | Backend processing, cần full response trước khi xử lý tiếp | Frontend chat — chữ hiện dần như ChatGPT |

---

## 6. Ollama trong Docker

Trong RAGnarok, Ollama chạy như một service trong Docker Compose:

```yaml
ollama:
  image: ollama/ollama
  ports:
    - "11434:11434"
  volumes:
    - ollama_data:/root/.ollama  # persist model, tránh pull lại khi restart
  networks:
    - infra-network
```

### Lưu ý quan trọng

**Model trong WSL local và trong container là hoàn toàn tách biệt.** Phải pull riêng vào container:

```bash
docker exec -it fsa-ollama-1 ollama pull mistral
docker exec -it fsa-ollama-1 ollama pull nomic-embed-text
```

**FastAPI không được dùng `localhost` để gọi Ollama trong Docker.** Phải dùng hostname nội bộ (tên service trong docker-compose):

```python
# ❌ Sai — localhost trong container chỉ trỏ về chính container đó
OLLAMA_URL = "http://localhost:11434"

# ✅ Đúng — giao tiếp qua internal network bằng tên service
OLLAMA_URL = "http://ollama:11434"
```

---

## 7. RAG Flow với Ollama

```
── INDEXING ─────────────────────────────────────────────
[Tài liệu]
    → chunk thành đoạn nhỏ
    → POST /api/embed  (nomic-embed-text)  → vector[]
    → upsert vào Qdrant

── QUERYING ─────────────────────────────────────────────
[Câu hỏi của user]
    → POST /api/embed  (nomic-embed-text)  → vector
    → semantic search trong Qdrant          → top-k chunks
    → nhét chunks vào prompt
    → POST /api/chat   (mistral)           → câu trả lời
```

---

## 8. Model Đang Dùng Trong RAGnarok

| Model | Loại | Kích thước | Nhiệm vụ |
|-------|------|-----------|---------|
| `llama 3.2:1b` | Chat LLM | ~1.3 GB | Generate câu trả lời |
| `nomic-embed-text` | Embedding model | ~274 MB | Tạo vector cho Qdrant |

---

*Tham khảo: [Ollama API Documentation](https://github.com/ollama/ollama/blob/main/docs/api.md)*
