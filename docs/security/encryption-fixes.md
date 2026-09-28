# Encryption Hardening — Sprint Review

Tài liệu này tổng hợp các thay đổi đã thực hiện sau buổi review logic mã hoá
(document / conversation / message / chunk dùng key của tenant). Mục đích:
khắc phục các lỗ hổng cấu hình + race-condition có thể khiến chuỗi mã hoá
bị vô hiệu hoá trong production, đồng thời bổ sung test coverage cho các
nhánh code nhạy cảm.

> **Lưu ý:** `SYSTEM_KEK` validator + default-zero guard trong `app/core/config.py`
> là mục **P0.1** đã được phát hiện nhưng **chưa sửa** trong sprint này — theo
> yêu cầu của chủ code sẽ tự xử lý sau. Mọi thay đổi khác đã hoàn tất + test pass.

---

## 1. Tổng quan các fix

| # | Mức | Vấn đề | File thay đổi |
|---|---|---|---|
| P0.2 | 🔴 | `tenant_name` đổi được → break KMS EncryptionContext | `app/models/tenant.py` |
| P0.3 | 🔴 | KMS fallback whitelist quá rộng + không counter | `app/core/encryption.py`, `app/utils/s3_storage.py` |
| P1.1 | 🟠 | Tenant DEK không `zeroize` trong chat/retrieval | `app/services/chat_service.py`, `app/services/retrieval_service.py` |
| P2.1 | 🟡 | File DEK EncryptionContext không bind `doc_id` | `app/utils/s3_storage.py`, `app/services/document_service.py` |
| P2.4 | 🟡 | Test coverage cho encrypt/fallback/zeroize còn yếu | `tests/unit/test_encryption_fixes.py` |

Kết quả test: **26/26 encryption tests mới pass**, các test cũ liên quan không bị break.

---

## 2. P0.2 — Rename guard cho `tenant_name`

### Vấn đề

- `app/core/encryption.py::_tenant_encryption_context` dùng `tenant_name` làm
  AWS KMS EncryptionContext / AAD. Khi wrap DEK, context được ghi vào ciphertext;
  lúc unwrap, KMS so sánh context — không khớp thì raise.
- Code cũ có comment nói "enforced ở tenant_service" nhưng `tenant_service.py`
  không có method update / rename guard nào.
- Hậu quả: nếu sau này thêm API đổi `tenant_name`, toàn bộ dữ liệu đã encrypt
  (field-level, Qdrant payload, file DEK) sẽ không decrypt được nữa.

### Sửa

Thêm `__setattr__` ở model `Tenants` (`app/models/tenant.py`):

```python
_IMMUTABLE_AFTER_LOAD = ("tenant_name",)

def __setattr__(self, key, value):
    if key in self._IMMUTABLE_AFTER_LOAD and getattr(self, "tenant_id", None) is not None:
        current = self.__dict__.get(key)
        if current is not None and current != value:
            raise AttributeError(
                "tenant_name is immutable — it is bound to the KMS "
                "EncryptionContext used to wrap the tenant DEK. Renaming "
                "would make all encrypted data undecryptable."
            )
    super().__setattr__(key, value)
```

- Cho phép gán `tenant_name` lần đầu (trước khi `tenant_id` được set).
- Sau khi load, gán `tenant_name` sang giá trị khác sẽ raise.
- Gán cùng giá trị OK (SQLAlchemy hydrate lại).

### Test

`tests/unit/test_encryption_fixes.py::TestTenantNameImmutability`:
- `test_rename_blocked_when_already_set` — đổi tên sau khi load → raise.
- `test_rename_allowed_during_init` — gán lần đầu trước `tenant_id` OK.

---

## 3. P0.3 — Thu hẹp KMS fallback whitelist + counter

### Vấn đề

- `_KMS_FALLBACK_ERRORS` cũ bao gồm 5 error code, trong đó có
  `InvalidCiphertextException` và `NotFoundException`. Hai error này có thể
  bị trigger bởi **bất kỳ blob nào** không phải do KMS wrap — cho phép attacker
  ép hệ thống rơi vào nhánh dùng local KEK (mà `SYSTEM_KEK` có thể đang là
  default zero — xem P0.1 chưa sửa).
- Fallback chỉ log `warning` — không có cảnh báo, không có counter để detect
  spike bất thường.

### Sửa

`app/core/encryption.py`:

```python
# Trước: 5 error (InvalidCiphertextException, InvalidKeyUsageException,
#          KeyUnavailableException, IncorrectKeyException, NotFoundException)
# Sau: chỉ 2 error tương ứng rotate KMS alias hợp lệ
_KMS_FALLBACK_ERRORS = (
    "IncorrectKeyException",
    "KeyUnavailableException",
)

_KMS_FALLBACK_COUNT = 0
_KMS_FALLBACK_THRESHOLD = 5

def _note_kms_fallback(operation: str, exc: Exception) -> None:
    """Log ERROR + tăng counter. Sau khi vượt ngưỡng -> raise."""
    global _KMS_FALLBACK_COUNT
    _KMS_FALLBACK_COUNT += 1
    logger.error("kms_fallback_to_local_kek", operation=operation, ...)
    if _KMS_FALLBACK_COUNT > _KMS_FALLBACK_THRESHOLD:
        logger.critical("kms_fallback_threshold_exceeded", ...)
```

- `generate_tenant_dek` và `unwrap_tenant_dek` gọi `_note_kms_fallback(...)`
  trước khi fallback.
- Sau khi vượt `_KMS_FALLBACK_THRESHOLD` (5 lần / process) → raise
  `KMSUnavailableError` thay vì tiếp tục dùng local KEK.

`app/utils/s3_storage.py`: áp dụng tương tự cho `generate_file_dek` và
`unwrap_file_dek`. Counter chia sẻ chung với `app.core.encryption` để có một
cảnh báo duy nhất cho cả process.

### Test

`tests/unit/test_encryption_fixes.py::TestKMSFallbackWhitelist`:
- `test_fallback_whitelist_is_narrow` — whitelist chỉ còn đúng 2 code.
- `test_invalid_ciphertext_not_in_whitelist` — không còn fallback cho error này.
- `test_not_found_not_in_whitelist`.
- `test_incorrect_key_in_whitelist`, `test_key_unavailable_in_whitelist`.

`tests/unit/test_encryption_fixes.py::TestKMSFallbackCounter`:
- `test_counter_increments_on_fallback` — fallback 1 lần → counter = 1.
- `test_raises_after_threshold` — fallback vượt ngưỡng → raise `KMSUnavailableError`.

---

## 4. P1.1 — Zeroize plaintext tenant DEK trong chat & retrieval

### Vấn đề

- `chat_service.chat`, `chat_service.chat_stream`, `retrieval_service.run_search`
  resolve `tenant_dek` plaintext 1 lần ở đầu request và giữ trong biến local.
- Không có `try/finally` để `zeroize` ở cuối request → plaintext key nằm trong
  heap cho đến khi garbage collector giải phóng.
- Nếu có heap dump trong lúc đang xử lý chat, attacker có thể lấy được
  plaintext DEK của mọi tenant đang chat.

### Sửa

Wrap toàn bộ thân hàm trong `try/finally` để gọi `zeroize(tenant_dek)`.

`app/services/chat_service.py::chat`:
```python
tenant_dek = await get_plaintext_dek(tenant)
try:
    # ... toàn bộ logic chat ...
finally:
    zeroize(tenant_dek)
    tenant_dek = None
```

Tương tự cho `chat_stream` (phải wrap cả generator vì nó là async generator).

`app/services/retrieval_service.py::run_search`:
```python
tenant_dek = await get_plaintext_dek(tenant)
try:
    if request.mode == SearchMode.SEMANTIC_WITH_RERANK:
        return await self._run_semantic_rerank(tenant, request, tenant_dek)
    # ...
    else:
        raise ValueError(...)
finally:
    zeroize(tenant_dek)
    tenant_dek = None
```

### Test

`tests/unit/test_encryption_fixes.py::TestChatServiceZeroize`:
- `test_chat_zeroizes_dek_on_success` — happy path → `zeroize` được gọi
  với đúng `tenant_dek` bytes.
- `test_chat_zeroizes_dek_on_error` — exception path → `zeroize` vẫn chạy.

`tests/unit/test_encryption_fixes.py::TestRetrievalServiceZeroize`:
- `test_run_search_zeroizes_dek` — happy path.
- `test_run_search_zeroizes_dek_on_error` — strategy raise → `zeroize` vẫn chạy.

---

## 5. P2.1 — Bind `doc_id` vào File DEK EncryptionContext

### Vấn đề

- `_encryption_context` của file DEK chỉ bind `tenant_name` + `purpose`.
- Lý thuyết: nếu attacker có quyền ghi DB, có thể swap `encrypted_file_dek`
  giữa 2 file cùng tenant → đọc nhầm file.
- Storage key khác nhau nhưng vẫn nên bind thêm 1 lớp phòng thủ.

### Sửa

`app/utils/s3_storage.py::_encryption_context`:
```python
def _encryption_context(tenant_name: str, doc_id: str | None = None) -> dict:
    ctx = {"tenant_name": tenant_name, "purpose": ENCRYPTION_PURPOSE}
    if doc_id:
        ctx["doc_id"] = doc_id
    return ctx
```

`generate_file_dek` và `unwrap_file_dek` thêm parameter `doc_id: str | None`
và truyền vào context. `doc_id` optional để backward-compat với blob cũ.

Cập nhật 4 caller trong `app/services/document_service.py`:
- `ingest_document` (line 134): `generate_file_dek(tenant_name, doc_id=str(doc.doc_id))`
- `process_document_async` (line 198): `unwrap_file_dek(..., doc_id=str(doc_id))`
- `ingest_batch` (line 341): `generate_file_dek(tenant_name, doc_id=str(doc.doc_id))`
- `get_document_content` (line 867): `unwrap_file_dek(..., doc_id=str(doc_id))`

### Test

`tests/unit/test_encryption_fixes.py::TestFileDEKContextBinding`:
- `test_context_with_doc_id` — context có `doc_id`.
- `test_context_without_doc_id` — backward-compat (không truyền).
- `test_generate_file_dek_passes_doc_id_to_context` — mock KMS client,
  verify `EncryptionContext` được truyền đúng cả 3 keys.

---

## 6. P2.4 — Bổ sung test coverage

File mới: `tests/unit/test_encryption_fixes.py` — 26 tests chia thành 6 nhóm:

| Nhóm | Test | Mục đích |
|---|---|---|
| `TestFieldCipherRoundtrip` | 5 | Roundtrip encrypt/decrypt, kể cả Unicode TV có dấu |
| `TestFieldCipherBackwardCompat` | 2 | Legacy plaintext rows trả về nguyên xi |
| `TestFieldCipherTampering` | 3 | Tampered ciphertext / sai DEK → raise |
| `TestKMSFallbackWhitelist` | 5 | Whitelist đúng + 2 error cũ bị loại |
| `TestKMSFallbackCounter` | 2 | Counter tăng + raise sau threshold |
| `TestFileDEKContextBinding` | 3 | `doc_id` được bind vào context |
| `TestTenantNameImmutability` | 2 | Rename block + init OK |
| `TestChatServiceZeroize` | 2 | Zeroize cả happy path + error path |
| `TestRetrievalServiceZeroize` | 2 | Zeroize cả happy path + error path |

Kết quả: **26 passed in 3.26s**.

---

## 7. Test cũ được sửa thêm

3 test trong `tests/unit/test_document_service.py::TestDocumentServiceIngest`
đã được thêm `encrypted_tenant_dek=b"\x00" * 32` vào call vì chữ ký hàm
đã có parameter này từ trước nhưng test cũ không truyền. Đây là sửa test,
không phải sửa logic.

---

## 8. Những thứ CHƯA sửa (theo yêu cầu)

### P0.1 — `SYSTEM_KEK` default zero + validator bị comment-out

- File: `app/core/config.py:430` (`DEFAULT_SYSTEM_KEK = "0" * 64`) và
  `:434-488` (3 validator đều bị comment-out bằng `#`).
- Hậu quả: nếu `.env` thiếu `SYSTEM_KEK`, app boot với KEK toàn 0; bất kỳ
  fallback xảy ra (xem P0.3) sẽ wrap DEK bằng key ai cũng biết.
- Theo yêu cầu của chủ code, mục này sẽ tự xử lý sau.

### P2.2 — Hard-coded KMS alias

- Người dùng đã chọn giữ hard-coded, không đưa vào Settings.

### P2.3 — `content_hash` plaintext (fingerprint leak)

- Chưa thay bằng HMAC. Có thể làm ở sprint sau.

### P2.5 — Không rotation path

- Chưa có cột `dek_version` hay script rotate. Migration sẽ cần thêm 1 cột
  + 1 admin command.

---

## 9. Cách chạy test

```bash
# Tạo venv lần đầu
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest pytest-asyncio

# Chạy riêng test mới
.venv/bin/pytest tests/unit/test_encryption_fixes.py -v

# Chạy tất cả test liên quan
.venv/bin/pytest tests/unit/test_encryption_fixes.py \
                   tests/unit/test_document_service.py \
                   tests/unit/test_hashing.py -v
```

---

## 10. Files đã thay đổi

```
app/core/encryption.py              ← thu hẹp whitelist + counter + helper
app/models/tenant.py                ← immutability guard cho tenant_name
app/services/chat_service.py        ← zeroize trong chat + chat_stream
app/services/retrieval_service.py   ← zeroize trong run_search
app/services/document_service.py    ← truyền doc_id vào file DEK ctx
app/utils/s3_storage.py             ← doc_id trong EncryptionContext + counter
tests/unit/test_encryption_fixes.py ← 26 tests mới
tests/unit/test_document_service.py ← sửa 3 test cũ (thêm encrypted_tenant_dek)
docs/security/encryption-fixes.md   ← file này
```