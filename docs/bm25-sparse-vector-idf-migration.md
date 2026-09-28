# BM25 Sparse Vector — Chuyển IDF từ tính tay sang Qdrant tự tính

## Tóm tắt

Hiện tại (`app/repositories/qdrant_repository.py`), IDF của BM25 được tính bằng tay ở client (`rank_bm25.BM25Okapi`) mỗi lần upload 1 tài liệu, chỉ dựa trên các chunk **của chính tài liệu đó**. Đề xuất: bỏ tính IDF ở client, chỉ lưu term-frequency (TF) đã saturate vào sparse vector, và bật `Modifier.IDF` để Qdrant tự tính IDF **dựa trên toàn bộ collection** tại thời điểm search.

---

## 1. IDF là gì

**IDF (Inverse Document Frequency)** đo độ hiếm của 1 token trên **cả tập tài liệu** (không phải trong 1 chunk riêng lẻ).

```
idf(token) = log( (N - df + 0.5) / (df + 0.5) + 1 )
```

- `N` = tổng số chunk (document) trong corpus đang xét
- `df` = số chunk có chứa token đó

Token xuất hiện ở hầu hết mọi chunk (từ phổ biến: "và", "là", "của") → `df` cao → `idf` **thấp** (ít giá trị phân biệt).
Token chỉ xuất hiện ở vài chunk (từ đặc trưng: "nghỉ phép", tên riêng) → `df` thấp → `idf` **cao** (giá trị phân biệt lớn, quan trọng khi search).

---

## 2. Cách làm cũ (tính tay, client-side)

```python
# corpus = TẤT CẢ chunk của 1 TÀI LIỆU ĐANG UPLOAD (không phải cả collection)
bm25 = BM25Okapi(tokenized_corpus)
idf = bm25.idf.get(token)              # N, df tính trong phạm vi tài liệu này thôi
weight = idf * tf                      # đóng gói cố định vào SparseVector, lưu vào Qdrant
```

**Vấn đề:**
- `N` và `df` chỉ tính trên chunk của **1 tài liệu đang upload**, không biết gì về các tài liệu khác đã có sẵn trong cùng collection (cùng tenant).
- `idf` tính xong bị **đóng băng vĩnh viễn** trong vector đã lưu — upload thêm bao nhiêu tài liệu sau đó cũng không cập nhật lại.
- IDF giữa các tài liệu khác nhau **không nhất quán / không so sánh được** với nhau.

---

## 3. Cách làm mới (Qdrant tự tính, server-side)

```python
# Lúc upload: chỉ lưu TF đã saturate, KHÔNG nhân idf
tf = freq * (k1 + 1) / (freq + k1 * (1 - b + b * doc_len / avg_len))
value = tf + ner_boost
# → SparseVector(indices=[...], values=[tf, ...])  — lưu vào Qdrant

# Config collection: bật modifier IDF
sparse_vectors_config={
    "bm25": SparseVectorParams(modifier=models.Modifier.IDF)
}
```

Lúc search, Qdrant tự nhân thêm `idf` vào `tf` đã lưu **ngay tại thời điểm tính điểm** (dot product query × document), dựa trên `N`, `df` **của toàn bộ collection hiện tại** — không sửa lại vector đã lưu, chỉ ảnh hưởng điểm số trả về.

---

## 4. So sánh N / df — ví dụ minh họa biến động

Giả sử tenant có 2 tài liệu, token `"hợp đồng"` xuất hiện rải rác:

| Bước | Cách cũ (client) | Cách mới (Qdrant) |
|---|---|---|
| Upload tài liệu A (20 chunk, "hợp đồng" xuất hiện ở 2/20 chunk) | `N=20`, `df=2` → idf **cao** (tưởng là từ hiếm) → đóng băng vào vector của A | Chưa tính idf, chỉ lưu TF |
| Upload tài liệu B (30 chunk, "hợp đồng" xuất hiện ở 23/30 chunk) | `N=30`, `df=23` → idf **thấp**, tính riêng, không ảnh hưởng vector của A | Chưa tính idf, chỉ lưu TF |
| Lúc search (sau khi có cả A+B) | Vector A vẫn dùng idf cũ (tính khi N=20) — **sai**, vì thực ra "hợp đồng" là từ phổ biến trong toàn tenant (25/50 chunk) | `N=50` (toàn collection), `df=25` → idf tính **đúng lúc search**, áp dụng nhất quán cho cả A lẫn B |
| Upload thêm tài liệu C sau đó | Vector A, B vẫn giữ idf cũ, không cập nhật trừ khi re-embed lại toàn bộ | `N`, `df` Qdrant tự cập nhật ngay, lần search kế tiếp dùng số liệu mới, không cần làm gì thêm |

→ Cách cũ: mỗi tài liệu "đóng băng" 1 phiên bản idf riêng, sai lệch dần khi tenant có nhiều tài liệu.
→ Cách mới: idf luôn phản ánh đúng trạng thái **hiện tại** của toàn bộ dữ liệu tenant đó.

---

## 5. Tại sao nên đổi

1. **Đúng bản chất thống kê BM25** — IDF vốn phải tính trên toàn corpus, không phải từng batch upload riêng lẻ.
2. **Tự động cập nhật** — thêm/xóa tài liệu không cần re-embed lại các tài liệu cũ để "làm mới" idf.
3. **Nhất quán giữa các tài liệu** — mọi chunk trong cùng collection dùng chung 1 phép tính idf tại thời điểm search, không lệch nhau theo thời điểm upload.
4. **Đơn giản hoá code** — bỏ được `rank_bm25`, bỏ bước build `BM25Okapi` cho cả corpus trước khi xử lý từng chunk.

---

## 6. Đánh đổi / lưu ý khi migrate

- Cần bật `Modifier.IDF` ở **cả 2 chỗ** tạo `SparseVectorParams()` trong `create_collection()` (nhánh tạo mới và nhánh migrate collection cũ).
- **Collection đã tồn tại** (đã upload dữ liệu trước đó) cần xóa và tạo lại — đổi code không tự cập nhật config field sparse vector đã có sẵn.
- `avgdl` (độ dài trung bình, trước tính động từ corpus qua `rank_bm25`) → thay bằng `avg_len`, 1 **hằng số cố định tự ước lượng**, không còn tính từ corpus thật nữa.
- Vẫn giữ `underthesea.word_tokenize` để tokenize — vì các sparse model có sẵn của `fastembed` (kể cả `Qdrant/bm25`) không hỗ trợ tiếng Việt, sẽ tách sai các từ ghép (vd: "Hà Nội" → "hà" + "nội").
- NER boost (`_apply_ner_boost`) vẫn giữ nguyên logic tự viết, cộng vào `value` trước khi đóng gói `SparseVector`.
