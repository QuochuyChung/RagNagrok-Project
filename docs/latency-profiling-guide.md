# Hướng dẫn chạy đo Latency

Tài liệu này hướng dẫn bật, thu thập và phân tích số liệu latency của 3 luồng chính.
Phần phân tích lỗi/bottleneck xem ở [backend-audit-report.md](backend-audit-report.md).

---

## 1. Chuẩn bị

### Bật profiling

Thêm vào `.env` (mặc định đã là `true`, chỉ cần khai báo khi muốn tắt):

```bash
ENABLE_LATENCY_PROFILING=true
LATENCY_PROFILING_DIR=profiling_results
```

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `ENABLE_LATENCY_PROFILING` | `true` | `false` sẽ tắt hoàn toàn, không tốn chi phí ghi file |
| `LATENCY_PROFILING_DIR` | `profiling_results` | Thư mục chứa file kết quả |

### Khởi động hệ thống

```bash
docker compose up -d
```

Kiểm tra gateway sống chưa:

```bash
curl http://localhost:8000/health
```

> **Lưu ý:** đổi biến trong `.env` cần restart lại gateway thì mới có hiệu lực, vì settings chỉ đọc một lần lúc khởi động.

---

## 2. Chạy từng luồng để thu số liệu

Thư mục `profiling_results/` sẽ tự được tạo. Mỗi flow ghi ra một file riêng theo ngày:
`latency_<flow>_<YYYYMMDD>.jsonl`

### Luồng 1 — Tạo tenant → Email → Verify

Đăng nhập bằng `PLATFORM_ADMIN` rồi tạo tenant qua Swagger (`http://localhost:8000/docs`) hoặc:

```bash
curl -X POST http://localhost:8000/v1/tenants -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" -d '{"name":"test_latency","tenant_admin":{"email":"admin@test.local","full_name":"Test Admin"}}'
```

Sinh ra 2 file:
- `latency_tenant_provisioning_*.jsonl` — sinh DEK qua KMS, insert DB, tạo collection Qdrant, provision schema
- `latency_email_invitation_*.jsonl` — thời gian gửi SMTP

Xem email đã gửi tại **Mailpit**: `http://localhost:8025` (service `mailpit` trong `compose.yaml`).

### Luồng 2 — Upload → Chunking → Mã hóa → Lưu DB

Đăng nhập bằng `TENANT_ADMIN`, rồi upload:

```bash
curl -X POST http://localhost:8000/v1/documents -H "Authorization: Bearer <TOKEN>" -F "file=@benchmark/other/mekong/docs/01_so_tay_nhan_vien.md"
```

Sinh ra 2 file:
- `latency_document_ingest_*.jsonl` — phần **đồng bộ** (hash, sinh DEK file, mã hóa, upload S3, ghi metadata). Đây là thời gian người dùng phải chờ.
- `latency_document_process_*.jsonl` — phần **nền** (chunking, embedding, upsert Qdrant). Chạy sau khi API đã trả response.

> File `document_process` chỉ xuất hiện **sau khi** job nền chạy xong. Tài liệu lớn có thể mất vài chục giây — chờ status document chuyển sang `COMPLETED` rồi hãy phân tích.

Muốn so sánh 2 chiến lược chunking:

```bash
curl -X POST "http://localhost:8000/v1/documents?chunking_mode=recursive_only" ...
```

### Luồng 3 — Chat → Rewrite → Retrieval → Generate

Cách dễ nhất là chat qua UI (`http://localhost:5173`). Hoặc gọi API:

```bash
curl -N -X POST http://localhost:8000/v1/chat/stream -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" -d '{"message":"Số ngày nghỉ phép của tôi là bao nhiêu?","top_k":5,"llm_provider":"ollama"}'
```

Sinh ra `latency_chat_*.jsonl`.

Nên chạy **ít nhất 10–20 lượt** với câu hỏi khác nhau — lượt đầu luôn chậm bất thường (model chưa nạp, cache lạnh) nên một mẫu đơn lẻ không nói lên gì.

Nhớ đo cả 2 nhánh:
- **Câu hỏi thường** (`"Chào bạn"`) → đi luồng `CHAT_NORMAL`, bỏ qua retrieval
- **Câu hỏi tra cứu** (`"Chính sách nghỉ phép?"`) → đi luồng đầy đủ có retrieval + rerank

---

## 3. Phân tích kết quả

### Dùng script có sẵn

```bash
python scripts/analyze_latency.py
```

Lọc theo nhu cầu:

```bash
python scripts/analyze_latency.py --flow chat
python scripts/analyze_latency.py --flow document_process --top 5
python scripts/analyze_latency.py --date 20260806
```

Kết quả mẫu:

```
========================================================================================
FLOW: chat   (12 lượt chạy)
========================================================================================
  Tổng thời gian:  p50=   3821.2ms  p95=   5247.2ms  max=   6102.4ms
  Chưa được đo:    p50=     42.0ms (1.1% tổng thời gian)

  STAGE                                             N        p50        p95        max
  --------------------------------------------- ----- ---------- ---------- ----------
  generate_stream_total                            12    3072.1ms    3943.3ms    3943.3ms
  generate_ttft                                    12     599.7ms     883.9ms     883.9ms
  intent_classify_rewrite                          12      92.6ms     123.5ms     123.5ms
  retrieval                                        12      47.7ms      61.9ms      61.9ms
  rerank                                           12      46.1ms      61.9ms      61.9ms
  unwrap_tenant_dek                                12      29.5ms      32.8ms      32.8ms
    embed_query                                    12      22.1ms      33.1ms      33.1ms
    qdrant_search                                  12      16.0ms      20.9ms      20.9ms
```

Stage thụt lề là stage con nằm trong stage cha ngay phía trên.

### Đọc số liệu thế nào

| Chỉ số | Ý nghĩa |
|---|---|
| **p50** | Trung vị — trải nghiệm của người dùng điển hình. Đây là con số nên dùng để so sánh trước/sau khi tối ưu. |
| **p95** | 5% lượt chậm nhất. Nếu p95 lệch xa p50 nghĩa là hệ thống không ổn định. |
| **max** | Trường hợp xấu nhất ghi nhận được. |
| **Chưa được đo** | Thời gian không nằm trong stage nào. **Trên 20% là có điểm mù** — còn chặng tốn thời gian chưa gắn đo. |

Riêng luồng chat, để ý 2 chỉ số tách biệt:
- **`generate_ttft`** — thời gian tới token đầu tiên. Đây mới là thứ người dùng cảm nhận là "nhanh/chậm".
- **`generate_stream_total`** — tổng thời gian sinh hết câu trả lời. Số này phụ thuộc độ dài câu trả lời nên **không so sánh trực tiếp giữa các lượt** được.

### Đọc file thô

Mỗi dòng là một JSON độc lập:

```bash
python -c "import json; [print(json.dumps(json.loads(l), ensure_ascii=False, indent=2)) for l in open('profiling_results/latency_chat_20260806.jsonl', encoding='utf-8')]"
```

Cấu trúc:

```json
{
  "flow": "chat",
  "timestamp": "2026-08-06T03:11:56+00:00",
  "total_ms": 8421.3,
  "unattributed_ms": 132.6,
  "slowest_stage": "generate_stream_total",
  "tenant_id": "...",
  "llm_provider": "ollama",
  "stages": [
    {"stage": "intent_classify_rewrite", "duration_ms": 1502.8, "offset_ms": 215.0},
    {"stage": "retrieval", "duration_ms": 921.5, "offset_ms": 1720.0},
    {"stage": "rerank", "duration_ms": 640.2, "metadata": {"provider": "local"}}
  ]
}
```

`offset_ms` = stage bắt đầu ở giây thứ mấy tính từ đầu pipeline. Dùng để dựng biểu đồ timeline hoặc phát hiện khoảng trống giữa 2 stage.

Stage bị lỗi sẽ có thêm `"failed": true` và `"error"` — nhờ vậy vẫn đo được cả những lượt hỏng, thường lại là những lượt cần điều tra nhất.

---

## 4. Quy trình so sánh trước/sau khi tối ưu

```bash
# 1. Thu số liệu nền
python scripts/analyze_latency.py --flow chat > /tmp/before.txt

# 2. Dọn dữ liệu cũ để không lẫn
mkdir -p profiling_results/archive
mv profiling_results/latency_chat_*.jsonl profiling_results/archive/

# 3. Áp dụng thay đổi, restart, chạy lại cùng bộ câu hỏi (cùng số lượt)
docker compose restart gateway

# 4. So sánh
python scripts/analyze_latency.py --flow chat > /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt
```

Nguyên tắc để so sánh có ý nghĩa:
- **Cùng bộ câu hỏi, cùng số lượt** — khác input thì số liệu không so được.
- **Bỏ vài lượt đầu** — cache lạnh làm sai lệch.
- **So p50, không so max** — max dễ bị nhiễu bởi một lượt bất thường.
- Máy không chạy việc nặng khác song song.

---

## 5. Xử lý sự cố

| Hiện tượng | Nguyên nhân & cách xử lý |
|---|---|
| Không có file nào trong `profiling_results/` | `ENABLE_LATENCY_PROFILING=false`, hoặc chưa restart gateway sau khi sửa `.env`. Kiểm tra bằng cách tìm dòng log `latency_profile`. |
| Thiếu file `latency_document_process_*` | Job nền chưa xong hoặc đã lỗi. Kiểm tra status document — nếu là `FAILED` thì xem log `document_process_failed`. |
| `unattributed_ms` chiếm phần lớn | Còn chặng nặng chưa gắn đo. Thêm `async with tracker.astage("ten_stage"):` quanh đoạn nghi ngờ. |
| `UnicodeEncodeError` khi chạy script | Đã xử lý sẵn trong script (ép stdout UTF-8). Nếu vẫn gặp, chạy `chcp 65001` trước trong PowerShell. |
| Số liệu chênh lệch lớn giữa các lượt | Bình thường ở vài lượt đầu. Nếu kéo dài, xem mục **B1** trong báo cáo audit — model rerank đang được load lại mỗi request. |

---

## 6. Thêm stage đo mới

Khi cần đo một đoạn code chưa được gắn:

```python
from app.profiling import LatencyTracker

tracker = LatencyTracker("ten_flow", tenant_id=str(tenant_id))

# Đoạn async
async with tracker.astage("goi_api_ngoai"):
    await client.post(...)

# Đoạn đồng bộ
with tracker.stage("ma_hoa", size_bytes=len(data)):
    encrypted = encrypt(data)

# Ghi thẳng số đo đã có sẵn từ nơi khác
tracker.mark("latency_tu_service_khac", 125.4)

# Bổ sung context phát sinh giữa chừng
tracker.add_context(doc_id=str(doc_id))

# Chốt — nên đặt trong finally để nhánh lỗi cũng có số liệu
tracker.finish()
```

Lưu ý khi gắn thêm:
- Đặt `tracker.finish()` trong `finally`, không đặt ở cuối `try` — nếu không thì đúng lúc pipeline lỗi (lúc cần số liệu nhất) lại không có gì được ghi.
- Stage lồng nhau tự động ghép tên thành `cha.con`, không cần tự đặt tiền tố.
- Tracker nuốt mọi lỗi nội bộ của chính nó, nên không sợ việc gắn đo làm hỏng luồng nghiệp vụ.

---

## 7. Lưu ý khi chạy production

- `profiling_results/` **không nên** commit vào git — dữ liệu có thể chứa `tenant_id`. Kiểm tra `.gitignore` trước khi commit.
- Mỗi request ghi 1 dòng vào file, dùng lock để không xen kẽ. Với lưu lượng lớn nên tắt (`ENABLE_LATENCY_PROFILING=false`) hoặc chuyển sang đẩy metric qua Prometheus/OpenTelemetry thay vì ghi file.
- File JSONL tăng theo ngày và **không tự xóa** — nên dọn định kỳ.
