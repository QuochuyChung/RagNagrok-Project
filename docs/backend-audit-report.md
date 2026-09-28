# Báo cáo rà soát Backend — Lỗi, Bug & Bottleneck

**Ngày:** 2026-08-06
**Phạm vi:** 3 luồng nghiệp vụ chính của `app/`
1. Tạo tenant/user → gửi email → verify
2. Upload tài liệu → chunking → mã hóa → lưu DB
3. Chat → rewrite → retrieval → generate

**Phương pháp:** đọc code tĩnh + đo trực tiếp trên máy dev (có ghi rõ số liệu đo được ở từng mục).

---

## 0. Tóm tắt điều hành

| # | Mức | Vấn đề | Ảnh hưởng | File |
|---|-----|--------|-----------|------|
| B1 | 🔴 P0 | Model rerank được load lại **mỗi request chat** | **+2.9s/request**, chặn event loop | `app/api/deps.py:251` |
| B2 | 🔴 P0 | Raw invitation token bị `print()` ra stdout | Rò rỉ token vào log | `app/services/token_service.py:333` |
| B3 | 🔴 P0 | `SYSTEM_KEK` mặc định toàn số 0 | Fallback wrap DEK bằng key ai cũng biết | `app/core/config.py` |
| B4 | 🟠 P1 | `asyncio.create_task` gửi email không giữ reference | Task bị GC giữa chừng, email mất im lặng | `app/services/token_service.py:170,237,357` |
| B5 | 🟠 P1 | Engine DB thiếu `pool_pre_ping` | `InterfaceError: connection is closed` (**đã sửa**) | `app/main.py:85` |
| B6 | 🟠 P1 | Toàn bộ lượt chat nằm trong 1 transaction, commit ở cuối | Ngắt giữa chừng → mất sạch hội thoại (**đã sửa**) | `app/services/chat_service.py` |
| B7 | 🟠 P1 | Bulk invite: N+1 query + N kết nối SMTP | 100 lời mời = 100 lần bắt tay SMTP | `app/services/token_service.py:310` |
| B8 | 🟡 P2 | `build_bm25_query_sparse_vector` gọi đồng bộ trong async | Chặn event loop theo độ dài query | `app/services/retrieval_service.py:228` |
| B9 | 🟡 P2 | `BackgroundTasks` của Starlette xử lý document | Mất job khi restart, không retry | `app/api/routes/documents.py:84` |
| B10 | 🟡 P2 | Log prompt đầy đủ ở mức INFO | Phình log, lộ nội dung tài liệu | `app/services/chat_service.py` |
| B11 | 🟡 P2 | `_rerank_chunks` sửa dict tại chỗ (mutate) | Điểm số gốc bị ghi đè, khó debug | `app/services/chat_service.py` |
| B12 | 🟢 P3 | `import` thừa, biến chết | Nhiễu code | nhiều file |

---

## 1. Luồng 1 — Tạo tenant/user → Email → Verify

### B2 🔴 Raw token bị in ra stdout

`app/services/token_service.py:333`

```python
raw_token = generate_raw_token()
print(f"🚀 [LOCAL TEST] RAW TOKEN FOR {invitee.email}: {raw_token}")
```

Token lời mời ở dạng **thô** (chưa hash) bị in thẳng ra stdout. Trong container, stdout đi vào log driver → bất kỳ ai đọc được log đều chiếm được tài khoản của người được mời. Đây là chuỗi bí mật tương đương mật khẩu dùng một lần.

**Sửa:** xóa hẳn dòng `print`. Nếu cần debug local, dùng `logger.debug` và chỉ log `raw_token[:6] + "..."`.

### B4 🟠 Fire-and-forget task gửi email không an toàn

`app/services/token_service.py:170, 237, 357`

```python
asyncio.create_task(
    send_invitation_email(...)
)
```

Ba vấn đề:
1. **Không giữ reference** — tài liệu Python cảnh báo rõ: event loop chỉ giữ *weak reference* tới task, task có thể bị garbage-collect giữa chừng và biến mất không dấu vết.
2. **Không bắt exception** — SMTP lỗi thì exception nằm im trong task, chỉ hiện `Task exception was never retrieved` lúc GC. Người dùng thấy API trả 200 nhưng email không bao giờ tới.
3. **Không retry** — SMTP timeout một lần là mất lời mời vĩnh viễn.

**Sửa:**
```python
_background_tasks: set[asyncio.Task] = set()

task = asyncio.create_task(send_invitation_email(...))
_background_tasks.add(task)                      # giữ reference
task.add_done_callback(_background_tasks.discard)
task.add_done_callback(_log_email_failure)       # bắt exception
```
Dài hạn nên đẩy sang hàng đợi thật (Celery/ARQ/RQ) để có retry và dead-letter queue.

### B7 🟠 Bulk invite: N+1 query và N kết nối SMTP

`app/services/token_service.py:310-360`

Vòng lặp `for invitee in request.invitees:` mỗi vòng gọi:
- `user_repo.create_inactive(...)` → 1 round-trip DB
- `token_repo.create(...)` → 1 round-trip DB nữa

Mời 100 người = **200 round-trip DB tuần tự**. Sau đó tạo 100 task email, **mỗi task mở một kết nối SMTP riêng** (`smtplib.SMTP(...)` trong `_send_email_sync`) — không tái sử dụng kết nối, và 100 kết nối đồng thời tới SMTP server rất dễ bị rate-limit hoặc chặn.

**Sửa:**
- Gom insert bằng `session.add_all()` / `bulk_insert_mappings` thay vì insert từng dòng.
- Gộp email: mở **1 kết nối SMTP** rồi `sendmail` nhiều lần trong cùng phiên, hoặc giới hạn đồng thời bằng `asyncio.Semaphore(5)`.

### B3 🔴 SYSTEM_KEK mặc định toàn số 0

Đã được ghi nhận trong `docs/security/encryption-fixes.md` mục P0.1 là "chưa sửa". **Đo thực tế trên máy dev cho thấy KEK hiện tại đúng là 64 ký tự `0`.**

Hệ quả: mọi DEK được wrap qua nhánh fallback local đều bị mã hóa bằng một khóa ai cũng đoán được → coi như không mã hóa.

**Sửa:** bật lại validator trong `app/core/config.py` và đặt `SYSTEM_KEK` ngẫu nhiên thật:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Nhận xét về SMTP đồng bộ

`_send_email_sync` dùng `smtplib` (blocking) nhưng **đã** được bọc bằng `asyncio.to_thread` — cách xử lý này đúng, không chặn event loop. Điểm cần lưu ý là `timeout=10` áp cho *kết nối*, còn `starttls()` + `login()` + `sendmail()` mỗi bước đều có thể treo thêm; tổng thời gian xấu nhất vượt xa 10s.

---

## 2. Luồng 2 — Upload → Chunking → Mã hóa → Lưu DB

### B9 🟠 Dùng `BackgroundTasks` cho job nặng

`app/api/routes/documents.py:84`

```python
background_tasks.add_task(service.process_document_async, ...)
```

`BackgroundTasks` của Starlette chạy **trong chính tiến trình web**, sau khi response đã trả. Hệ quả:
- **Restart/deploy giữa chừng = mất job vĩnh viễn**, document kẹt mãi ở trạng thái `PENDING`.
- Không có retry (dù đã khai báo sẵn `RETRY_CONFIG` ở `document_service.py:51` nhưng **không chỗ nào dùng** — code chết).
- Job nặng (chunk + embed) ăn CPU/RAM của tiến trình đang phục vụ request.

**Sửa:** chuyển sang worker riêng (Celery/ARQ/Dramatiq). Trước mắt, tối thiểu nên có job quét lại các document `PENDING` quá lâu để xử lý lại.

### Bottleneck: embedding là chặng chậm nhất

`app/services/document_service.py:601` → `ChunkerService.embed_batch_async(corpus, batch_size=32)`

Các batch được gửi **tuần tự** (`for i in range(0, len(texts), batch_size)`), mỗi batch chờ Ollama xong mới gửi batch kế. Tài liệu 500 chunk = 16 batch nối đuôi nhau.

**Sửa:** chạy song song có giới hạn:
```python
sem = asyncio.Semaphore(4)
results = await asyncio.gather(*[_embed_one_batch(b) for b in batches])
```
Cần đo trước để không làm Ollama quá tải (xem phần 4).

### Điểm tốt cần giữ

- `compute_bm25_sparse_vectors` được bọc `asyncio.to_thread` — đúng, vì đây là tính toán CPU nặng.
- `ChunkerService.chunking` cũng đã bọc `asyncio.to_thread`.
- Mỗi file trong batch commit riêng — 1 file lỗi không kéo đổ cả lô.

---

## 3. Luồng 3 — Chat → Rewrite → Retrieval → Generate

### B1 🔴 BOTTLENECK LỚN NHẤT: model rerank load lại mỗi request

`app/api/deps.py:251`
```python
async def get_chat_service(...) -> ChatService:
    return ChatService(retrieval_service, client_factory, conversation_repo)
```

`get_chat_service` là **FastAPI dependency** → chạy lại **mỗi request**. Mà `ChatService.__init__` (`chat_service.py:116`) làm:
```python
self.reranker = TextCrossEncoder(model_name=self.settings.local_model_reranker)
self._cohere_rerank_client = cohere.ClientV2(...) if ... else None
```

**Số liệu đo thực tế trên máy dev** (model `jinaai/jina-reranker-v2-base-multilingual`):

```
lần 1: khởi tạo TextCrossEncoder = 2777.8 ms
lần 2: khởi tạo TextCrossEncoder = 2944.7 ms
lần 3: khởi tạo TextCrossEncoder = 2950.3 ms
```

**~2.9 giây mỗi lần, và KHÔNG nhanh hơn ở lần sau** — nghĩa là không có cache nội bộ nào cứu được.

Nghiêm trọng hơn: đây là lời gọi **đồng bộ nằm trong hàm `async`** → nó **chặn toàn bộ event loop ~3 giây**. Trong 3 giây đó, *mọi* request khác của *mọi* tenant đều đứng im, kể cả `/health`.

**Sửa (ưu tiên cao nhất):** khởi tạo model **một lần** lúc app startup rồi tái sử dụng:

```python
# app/main.py — trong lifespan
app.state.reranker = TextCrossEncoder(model_name=settings.local_model_reranker)
app.state.cohere_client = cohere.ClientV2(...) if ... else None

# app/api/deps.py
async def get_chat_service(request: Request, ...) -> ChatService:
    return ChatService(..., reranker=request.app.state.reranker,
                       cohere_client=request.app.state.cohere_client)
```

Ước tính: **giảm ~2.9s khỏi mọi request chat** và loại bỏ hoàn toàn hiện tượng nghẽn toàn cục.

### B8 🟡 BM25 query vector tính đồng bộ trong async

`app/services/retrieval_service.py:228`
```python
sparse_vector = self.qdrant_repository.build_bm25_query_sparse_vector(request.query)
```

Khác với đường ingest (đã bọc `to_thread`), đường query gọi thẳng. Với query ngắn thì không đáng kể, nhưng đây là chặng nằm trên đường đi của *mọi* lượt chat nên vẫn nên bọc `asyncio.to_thread` cho nhất quán.

### B10 🟡 Log toàn bộ prompt ở mức INFO

`app/services/chat_service.py` — 2 chỗ:
```python
logger.info(f"prompt: {prompt} và system prompt: {system_prompt} sau khi intent")
logger.info(f"Đã chat xong với câu trả lời {full_content}")
```

`prompt` chứa **toàn bộ nội dung các chunk tài liệu** đã giải mã. Vậy là dữ liệu vừa được mã hóa cẩn thận ở DB/Qdrant/S3 lại nằm phơi dưới dạng plaintext trong log. Ngoài rủi ro lộ dữ liệu, mỗi dòng log có thể vài chục KB → phình đĩa rất nhanh.

**Sửa:** hạ xuống `logger.debug` và chỉ log độ dài + số chunk, không log nội dung.

### B11 🟡 `_rerank_chunks` sửa dict tại chỗ

`app/services/chat_service.py`
```python
chunk["scores"]["final"] = 1 / (1 + math.exp(-score))
```

Ghi đè trực tiếp lên dict do `retrieval_service` trả về, xóa mất điểm gốc (`final` cũ từ Qdrant). Khi cần điều tra "vì sao chunk này lọt top", không còn dữ liệu để so sánh trước/sau rerank.

**Sửa:** ghi vào khóa mới `chunk["scores"]["rerank"]` và giữ nguyên `final` gốc, hoặc copy dict trước khi sửa.

### B6 🟠 Toàn bộ lượt chat trong 1 transaction — ĐÃ SỬA

Trước đây `conversation` + cả 2 message chỉ commit ở **cuối** `chat_stream`. Client ngắt giữa chừng → `GeneratorExit`/`CancelledError` (kế thừa `BaseException`, **không** rơi vào `except Exception`) → commit không chạy → transaction rollback → **mất sạch cả hội thoại**.

Đã sửa: thêm nhánh `except (GeneratorExit, asyncio.CancelledError)` lưu lại câu hỏi + phần trả lời dở dang với `message_type="interrupted"`, và nhánh `except Exception` lưu với `message_type="error"` thay vì rollback.

### B5 🟠 Thiếu `pool_pre_ping` — ĐÃ SỬA

Engine tạo ở `app/main.py:85` không có `pool_pre_ping` → pool phát ra connection đã bị server đóng (idle timeout / mất mạng) → `InterfaceError: connection is closed` ném tới tận client. Đã thêm `pool_pre_ping=True` và `pool_recycle=1800`.

---

## 4. Code đo latency đã triển khai

### Module mới: `app/profiling/latency_tracker.py`

Đo thời gian từng chặng, xuất ra structured log + file JSONL để phân tích offline.

**Nguyên tắc thiết kế:**
- **An toàn khi chạy song song** — mỗi request một instance, không dùng biến global giữ số đo.
- **Không bao giờ làm hỏng nghiệp vụ** — mọi lỗi bên trong tracker bị nuốt, chỉ log mức `debug`.
- **Tắt được hoàn toàn** — qua `ENABLE_LATENCY_PROFILING=false`.
- Dùng `perf_counter` (monotonic), không lệch khi đồng hồ hệ thống bị chỉnh.
- Hỗ trợ stage lồng nhau (`cha.con`).

**API:**
```python
tracker = LatencyTracker("chat", tenant_id=..., llm_provider=...)

async with tracker.astage("retrieval"):      # đo đoạn async
    ...
with tracker.stage("encrypt_payload"):        # đo đoạn sync
    ...
tracker.mark("generate_ttft", 812.5)          # ghi số đo có sẵn
tracker.finish()                              # log + ghi file
```

**Output** — `profiling_results/latency_chat_20260806.jsonl`, mỗi dòng 1 JSON:
```json
{
  "flow": "chat",
  "total_ms": 8421.3,
  "unattributed_ms": 132.6,
  "slowest_stage": "generate_stream_total",
  "tenant_id": "...",
  "stages": [
    {"stage": "unwrap_tenant_dek", "duration_ms": 210.4, "offset_ms": 0.1},
    {"stage": "intent_classify_rewrite", "duration_ms": 1502.8, "offset_ms": 215.0},
    {"stage": "retrieval", "duration_ms": 921.5, "offset_ms": 1720.0},
    {"stage": "retrieval.embed_query", "duration_ms": 402.1},
    {"stage": "retrieval.qdrant_search", "duration_ms": 515.2},
    {"stage": "rerank", "duration_ms": 640.2, "metadata": {"provider": "local"}},
    {"stage": "generate_ttft", "duration_ms": 812.5},
    {"stage": "generate_stream_total", "duration_ms": 4980.1}
  ]
}
```

Trường `unattributed_ms` = phần thời gian **không** nằm trong stage nào. Nếu số này lớn nghĩa là còn chặng tốn thời gian chưa được đo — dùng để phát hiện điểm mù.

### Các chặng đã gắn đo

**Luồng 1 — tenant (`tenant_service.py`) và email (`email.py`):**
| Stage | Ý nghĩa |
|---|---|
| `generate_tenant_dek_kms` | Gọi AWS KMS sinh DEK |
| `db_insert_tenant` | Insert bảng tenants |
| `qdrant_create_collection` | Tạo collection Qdrant |
| `provision_pg_schema` | Tạo schema riêng + bảng cho tenant |
| `smtp_send` | Gửi email (flow riêng `email_invitation`) |

**Luồng 2 — upload (`document_service.py`):**
| Stage | Ý nghĩa |
|---|---|
| `unwrap_tenant_dek` | Giải mã DEK qua KMS |
| `hash_and_lookup` | SHA-256 + hash tra cứu tên |
| `generate_file_dek_kms` | Sinh DEK riêng cho file |
| `encrypt_file_bytes` | Mã hóa nội dung file |
| `upload_s3` | Đẩy lên S3 |
| `db_commit_metadata` | Ghi metadata |

Background job (flow `document_process`):
| Stage | Ý nghĩa |
|---|---|
| `download_s3` / `unwrap_file_dek_kms` / `decrypt_file_bytes` | Tải + giải mã |
| `chunking` | Cắt chunk |
| `encrypt_and_save_chunks_db` | Mã hóa + lưu Postgres |
| `embed_and_upsert_qdrant.bm25_sparse_vectors` | Tính BM25 |
| `embed_and_upsert_qdrant.embed_dense_vectors` | **Gọi Ollama embedding** |
| `embed_and_upsert_qdrant.encrypt_qdrant_payload` | Mã hóa payload |
| `embed_and_upsert_qdrant.qdrant_upsert_call` | Upsert Qdrant |

**Luồng 3 — chat (`chat_service.py`):**
| Stage | Ý nghĩa |
|---|---|
| `unwrap_tenant_dek` | Giải mã DEK |
| `intent_classify_rewrite` | LLM phân loại ý định + viết lại câu hỏi |
| `retrieval` (+ `.embed_query`, `.qdrant_search`) | Truy xuất |
| `rerank` | Rerank chunk |
| `generate_ttft` | **Thời gian tới token đầu tiên** — thứ người dùng thực sự cảm nhận |
| `generate_stream_total` | Tổng thời gian sinh hết câu trả lời |

`generate_ttft` được tách riêng vì đây mới là chỉ số phản ánh cảm nhận "nhanh/chậm" của người dùng; tổng thời gian stream phụ thuộc độ dài câu trả lời nên không so sánh được giữa các lượt.

### Bật/tắt

```bash
ENABLE_LATENCY_PROFILING=true          # mặc định true
LATENCY_PROFILING_DIR=profiling_results
```

### Cách phân tích nhanh

```bash
python -c "
import json,collections,statistics
rows=[json.loads(l) for l in open('profiling_results/latency_chat_20260806.jsonl',encoding='utf-8')]
agg=collections.defaultdict(list)
for r in rows:
    for s in r['stages']: agg[s['stage']].append(s['duration_ms'])
for k,v in sorted(agg.items(), key=lambda x:-statistics.median(x[1])):
    print(f'{k:45s} n={len(v):4d} p50={statistics.median(v):9.1f}ms max={max(v):9.1f}ms')
"
```

---

## 5. Thứ tự ưu tiên đề xuất

| Ưu tiên | Việc | Công sức | Lợi ích |
|---|---|---|---|
| 1 | **B1** — đưa reranker + cohere client lên `app.state` | Thấp | **-2.9s/request chat**, hết nghẽn toàn cục |
| 2 | **B2** — xóa `print` raw token | Rất thấp | Bịt lỗ rò rỉ token |
| 3 | **B3** — đặt `SYSTEM_KEK` thật + bật validator | Thấp | Mã hóa mới thực sự có tác dụng |
| 4 | **B10** — hạ log prompt xuống `debug` | Rất thấp | Hết lộ nội dung tài liệu qua log |
| 5 | **B4** — giữ reference + bắt lỗi task email | Thấp | Hết mất email im lặng |
| 6 | **B8** — bọc `to_thread` cho BM25 query | Rất thấp | Bớt chặn event loop |
| 7 | **B7** — gom batch insert + tái dùng kết nối SMTP | Trung bình | Bulk invite nhanh hơn nhiều |
| 8 | Embedding chạy song song có giới hạn | Trung bình | Rút ngắn thời gian xử lý tài liệu |
| 9 | **B9** — chuyển sang worker thật | Cao | Không mất job khi restart |

**Khuyến nghị:** chạy hệ thống với profiling bật khoảng 1–2 ngày để thu số liệu thật, rồi dùng script ở mục 4 xác nhận lại thứ tự ưu tiên trước khi tối ưu sâu — tránh tối ưu nhầm chỗ.

---

## 6. Ghi chú

- Các mục **B5** và **B6** đã được sửa trong phiên làm việc này; phần còn lại là đề xuất, **chưa** áp dụng vào code.
- Số liệu 2.9s ở **B1** đo trên máy dev Windows, CPU-only. Máy có GPU hoặc model nhỏ hơn sẽ khác, nhưng bản chất "load lại mỗi request" thì không đổi.
- Không thay đổi nào ở mục 4 (code đo latency) làm đổi logic nghiệp vụ; toàn bộ chỉ bọc thêm context manager quanh code sẵn có.
