# Document Endpoints — Luồng hoạt động

> Module: Document Ingestion — RAGnarok Multi-Tenant RAG API Gateway
> Kiến trúc: `routes → services → repositories → database`
> Tất cả endpoint đều yêu cầu header `X-Tenant-ID` (qua dependency `get_current_tenant`), validate tenant tồn tại trong DB trước khi vào logic chính.

---

## 1. `POST /documents` — Upload document

**Mục đích:** Nạp tài liệu mới, xử lý idempotency (trùng nội dung) và versioning (khác nội dung, cùng tên).

### Luồng xử lý

```
Client
  │  multipart/form-data: file, header X-Tenant-ID
  ▼
Route (upload_document)
  │  đọc file.read() -> content (bytes)
  │  check size -> quá lớn -> 413
  ▼
Service (ingest_document)
  │  1. Validate extension (.pdf/.txt/.md) -> sai -> ValueError -> route bắt -> 422
  │  2. content rỗng -> ValueError -> 422
  │  3. Tính content_hash = SHA-256(content)
  │  4. Repository.get_latest_version(tenant_id, doc_name)
  │     -> lấy bản có doc_version CAO NHẤT, bất kể is_deleted
  ▼
  ┌─── latest tồn tại, đang active (is_deleted=False), hash TRÙNG ───┐
  │   -> Idempotent: KHÔNG tạo row mới, trả nguyên latest            │
  └────────────────────────────────────────────────────────────────┘
  ┌─── latest tồn tại, đang active, hash KHÁC ───────────────────────┐
  │   -> mark_superseded(latest): set is_deleted=True cho bản cũ     │
  │   -> next_version = latest.doc_version + 1                      │
  │   -> Repository.create(...) -> INSERT row mới                   │
  │   -> Lưu file vật lý: storage/documents/{tenant_id}/{doc_id}.ext │
  └────────────────────────────────────────────────────────────────┘
  ┌─── latest KHÔNG tồn tại (lần đầu upload tên này) ────────────────┐
  │   -> next_version = 1                                            │
  │   -> Repository.create(...) -> INSERT row mới                   │
  │   -> Lưu file vật lý                                             │
  └────────────────────────────────────────────────────────────────┘
  ▼
Response: DocumentResponse (200)
```

### Business rules quan trọng
- **Idempotency chỉ so với bản active mới nhất**, không so toàn bộ lịch sử — file trùng hash với version đã bị superseded vẫn tạo version mới.
- **Insert DB trước, ghi file sau** — vì `doc_id` do DB tự sinh, cần biết `doc_id` mới đặt được tên file. Rủi ro: ghi file fail sau khi DB đã commit → row mồ côi (chưa xử lý, thuộc scope Module 6 Reliability).
- Không có field `is_duplicate` trong response — trùng thì âm thầm giữ nguyên `doc_id`/`doc_version`.

### Lỗi có thể gặp
| Status | Nguyên nhân |
|---|---|
| 400 | Thiếu header `X-Tenant-ID` |
| 404 | Tenant không tồn tại trong DB |
| 413 | File vượt kích thước cho phép |
| 422 | Sai extension, file rỗng |

---

## 2. `GET /documents` — List documents

**Mục đích:** Trả danh sách document đang active (bản mới nhất của mỗi `doc_name`) thuộc tenant.

### Luồng xử lý

```
Client
  │  header X-Tenant-ID
  ▼
Route (list_documents)
  ▼
Service (list_documents)
  ▼
Repository (list_by_tenant)
  │  SELECT * FROM documents
  │  WHERE tenant_id = ? AND is_deleted = FALSE
  ▼
Response: DocumentListResponse { documents: [...], total: N }
```

### Business rules
- Chỉ trả bản `is_deleted = False` — đúng spec "deleted documents are excluded from retrieval/chat".
- Vì mỗi `(tenant_id, doc_name)` tại một thời điểm chỉ có tối đa 1 bản active (nhờ `mark_superseded` tự động), list này tự nhiên chỉ hiện version mới nhất của từng tên file — không cần thêm logic dedupe ở tầng query.

### Giới hạn hiện tại
- **Không có cách xem lịch sử version cũ** (các bản `is_deleted=True`) qua endpoint này — muốn xem phải query DB tay. Đây là gap cần bổ sung nếu làm UI kiểu "xem version cũ để restore" (endpoint riêng `/documents/{doc_id}/versions` hoặc query param `?include_deleted=true` — chưa quyết, chưa làm).

---

## 3. `DELETE /documents/{doc_id}` — Soft-delete document

**Mục đích:** Đánh dấu 1 document đang active thành không active (không xóa vật lý).

### Luồng xử lý

```
Client
  │  path param doc_id, header X-Tenant-ID
  ▼
Route (delete_document)
  ▼
Service (delete_document)
  ▼
Repository.get_by_id(tenant_id, doc_id)
  │  filter is_deleted = False -> không tìm thấy doc đã xóa rồi
  ▼
  ┌─── tìm thấy ────────────────────┐   ┌─── không tìm thấy ─────────┐
  │  soft_delete(doc):              │   │  return None               │
  │  set is_deleted = True          │   │  -> route raise             │
  │                                  │   │     DocumentNotFoundError   │
  │  return doc                     │   │     -> 404                  │
  └─────────────────────────────────┘   └────────────────────────────┘
  ▼
Response: { "message": "Đã xóa document", "doc_id": "..." } (200)
```

### Business rules
- `is_deleted` dùng chung cho cả 2 lý do: xóa thủ công (`soft_delete`) và bị thay thế tự động (`mark_superseded`) — không tách field `status` riêng, chấp nhận đơn giản hóa.
- Xóa 1 doc đã xóa rồi (hoặc `doc_id` không tồn tại) → 404, vì `get_by_id` filter `is_deleted=False`.

### ⚠️ Bug đang mở
- **`307 Temporary Redirect`** khi gọi endpoint này — chưa xác định nguyên nhân chính xác (nghi trailing-slash hoặc route ordering). Đang chờ output `curl -i -X DELETE ...` để xem header `Location` và đối chiếu cách khai báo `@router.delete("/{doc_id}")`.

---

## 4. `POST /documents/{doc_id}/restore` — Restore document

**Mục đích:** Khôi phục lại 1 document đã bị soft-delete, đưa nó trở thành bản active thay cho bản đang active hiện tại.

### Luồng xử lý

```
Client
  │  path param doc_id (của bản ĐÃ soft-delete), header X-Tenant-ID
  ▼
Route (restore_document)
  ▼
Service (restore_document)
  │
  │  1. Repository.get_by_id_any_status(tenant_id, doc_id)
  │     -> KHÔNG filter is_deleted, tìm ra doc bất kể trạng thái
  ▼
  ┌─── doc không tồn tại ────────────────────────────────────────┐
  │   -> return None -> route raise DocumentNotFoundError -> 404 │
  └───────────────────────────────────────────────────────────┘
  ┌─── doc tồn tại, is_deleted = False (đã active sẵn) ──────────┐
  │   -> Idempotent: KHÔNG làm gì thêm, trả nguyên trạng thái    │
  │      (tránh tự supersede rồi tự restore chính nó)            │
  └───────────────────────────────────────────────────────────┘
  ┌─── doc tồn tại, is_deleted = True (case restore thật) ───────┐
  │   2. Repository.get_active_by_name(tenant_id, doc.doc_name)  │
  │      -> tìm bản đang active hiện tại của cùng doc_name       │
  │   3. Nếu có current_active -> mark_superseded(current_active)│
  │      (set is_deleted = True cho bản đang active)             │
  │   4. Repository.restore(doc) -> set is_deleted = False        │
  │      (GIỮ NGUYÊN doc_version gốc, không +1)                  │
  └───────────────────────────────────────────────────────────┘
  ▼
Response: DocumentResponse (200)
```

### Business rules quan trọng
- **Reactivate tại chỗ (Approach A)** — không tạo row mới, không copy file vật lý, không đổi `doc_version` của bản được restore. Bản đang active trước đó bị chuyển sang `is_deleted=True` (supersede), còn bản restore lấy lại đúng `doc_version` cũ của nó.
- **`doc_version` không đại diện cho "mới nhất theo thời gian active"** mà là số định danh nội dung cố định — sau restore, số active có thể **nhỏ hơn** số bị supersede (vd `v1` active, `v2` bị đá xuống deleted). Đây là điểm khác biệt so với trực giác thông thường, cần lưu ý khi đọc `GET /documents`.
- **Version tương lai không bị ảnh hưởng bởi restore** — `get_latest_version` luôn lấy `MAX(doc_version)` toàn bộ lịch sử (không filter `is_deleted`), nên upload mới tiếp theo vẫn tính đúng từ số cao nhất từng tồn tại, không quan tâm bản nào đang active.

### Cách lấy `doc_id` để test (hiện tại)
Chưa có endpoint list version cũ trên UI, phải query DB tay:
```sql
SELECT doc_id, doc_name, doc_version, is_deleted
FROM documents
WHERE tenant_id = '<TENANT_ID>'
ORDER BY doc_name, doc_version;
```
Chọn row có `is_deleted = t` để lấy `doc_id` paste vào Swagger.

### Lỗi có thể gặp
| Status | Nguyên nhân |
|---|---|
| 404 | `doc_id` không tồn tại trong DB (kể cả đã xóa hay chưa từng tồn tại) |
| 200 (idempotent) | `doc_id` tồn tại nhưng đang active sẵn — không phải lỗi, trả nguyên trạng |

---

## Tổng hợp trạng thái `is_deleted` qua 4 endpoint

| Endpoint | Điều kiện input | Ảnh hưởng lên `is_deleted` |
|---|---|---|
| `POST /documents` | Nội dung khác bản active | Bản cũ: `False → True` (supersede) |
| `GET /documents` | — | Chỉ đọc, filter `is_deleted=False` |
| `DELETE /documents/{doc_id}` | Doc đang active | `False → True` (soft-delete) |
| `POST /documents/{doc_id}/restore` | Doc đang deleted | Doc restore: `True → False`; bản active hiện tại (nếu có): `False → True` |

---

## Việc còn thiếu / cần làm tiếp (liên quan trực tiếp 4 endpoint này)

1. Endpoint list lịch sử version (bao gồm bản `is_deleted=True`) — cần cho UI "..." menu chọn bản để restore, và để tự QA không phải query DB tay.
2. Fix bug `307 Temporary Redirect` trên `DELETE /documents/{doc_id}` (đang chờ curl -i output).
3. Đồng bộ format lỗi 413/422 (`HTTPException` thô) với `ErrorResponse` chuẩn dùng cho lỗi nghiệp vụ khác.
4. Rollback/compensation khi ghi file vật lý fail sau khi DB đã commit (row mồ côi) — cả cho `POST /documents`.
