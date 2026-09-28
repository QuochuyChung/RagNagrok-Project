# 📋 Tài liệu về tìm Hiểu Qdrant
> Collection · Point · Vector · Payload · Filter · Upsert · Search

---

## 1. Collection

Collection là **không gian lưu trữ độc lập** cho một tập hợp các Points (gồm id + vector + payload). Tương tự Table trong SQL, nhưng được tối ưu cho vector similarity search.

- Mỗi collection có cấu hình **cố định ngay từ khi tạo**:  
    - vector size 
    - distance metric
- Không thể thay đổi `vector size` sau khi tạo — phải xóa và tạo lại
- Các collection **độc lập hoàn toàn** với nhau

**Tạo Collection:**
```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

client = QdrantClient(host="localhost", port=6333)

client.create_collection(
    collection_name="my_collection",
    vectors_config=VectorParams(
        size=384,              # số chiều (dimension) của vector
        distance=Distance.COSINE
    )
)
```
**Giải thích:**
- QdrantClient: là class từ thư viện qdrant-client, dùng để giao tiếp với Qdrant Server qua HTTP REST API qua port 6333

- create_collection: câu lệnh tạo 1 collection

- VectorParams: các params quy định thuộc tính của vector

    - 'size': **độ dài** mảng số thực của vector

        ```python
        dense_vector=[0.95, 0.85, 0.92, ...] # độ dài: 384 số
        ```

    -  'distance': phương pháp tính độ tương đồng giữa 2 vector.Có 3 thuật toán thường được sử dụng :
        + **Cosine Similarity**: thường được dùng nhất
            ```python
            # cú pháp khai báo
            distance=Distance.CONSINE
            # score = (A · B) / (|A| × |B|)
            ```

        
        + **Dot Product (Tích vô hướng)**: dùng khi **độ dài** của 2 vector **đã được chuẩn hóa**. Ví dụ có 2 câu muốn so sánh: áo polo và áo thun. Độ dài đã được chuẩn hóa với nhau, đều có 2 từ
            ```python
            # cú pháp khai báo
            distance=Distance.DOT
            score = A · B = Σ(Aᵢ × Bᵢ)
            ```

        + **EUCLID**:Euclidean đo khoảng cách đường thẳng giữa hai vector trong không gian nhiều chiều.
            ```python
            # cú pháp khai báo
            distance=Distance.EUCLID
            score = √Σ(Aᵢ - Bᵢ)²
            ```


### Các thao tác cơ bản
```python
# Xem danh sách collections
client.get_collections()

# Xem thông tin một collection
client.get_collection("my_collection")

# Xóa collection
client.delete_collection("my_collection")

# Kiểm tra collection tồn tại chưa
client.collection_exists("my_collection")
```

---

## 2. Point

### Là gì?
Point là **đơn vị dữ liệu cơ bản** trong Qdrant. Mỗi point gồm đúng 3 thành phần:

```
Point = {
    id:      định danh duy nhất (UUID hoặc unsigned integer)
    vector:  mảng float đại diện cho nội dung
    payload: metadata tùy chọn (JSON object)
}
```

### Ví dụ một Point
```python
from qdrant_client.models import PointStruct

point = PointStruct(
    id=1,                              # hoặc "550e8400-e29b-41d4-a716-..."
    vector=[0.23, -0.87, 0.41, 0.15], # embedding vector
    payload={
        "title": "Introduction to ML",
        "category": "education",
        "year": 2024
    }
)
```
**Note**
- **Payload:** là bao gồm về thông tin của **chunk** gốc và những metadata thuộc về chunk đó. Ví dụ có thể là: 
    + **doc_type**: chunk đó thuộc về document nào
    + **section**: tiêu đề của chunk đó
    ...



### Lưu ý về ID
```python
# Qdrant chấp nhận 2 loại ID:
id = 1                                    # unsigned integer
id = "550e8400-e29b-41d4-a716-446655440000"  # UUID string
```

---

## 3. Vector

### Là gì?
Vector là **mảng số thực (float32)** đại diện cho nội dung trong không gian nhiều chiều. Hai nội dung "giống nhau về ngữ nghĩa" → hai vector **gần nhau** trong không gian đó.

### Distance Metrics — 3 cách đo độ tương đồng

| Metric | Công thức | Khi dùng |
|--------|-----------|----------|
| **Cosine** | cos(θ) = A·B / (\|A\|×\|B\|) | Text, NLP (phổ biến nhất) |
| **Dot Product** | A · B = Σ aᵢbᵢ | Khi vectors đã normalized |
| **Euclidean** | √Σ(aᵢ-bᵢ)² | Image, spatial data |

### Cosine vs Euclidean — Tại sao Cosine phổ biến hơn cho text?
```
Cosine đo GÓC giữa 2 vector → không quan tâm độ dài
→ Câu ngắn và câu dài cùng nội dung vẫn cho score cao

Euclidean đo KHOẢNG CÁCH trực tiếp
→ Câu dài có vector lớn hơn → distance lớn hơn dù cùng nội dung
```

### Sparse Vector (Hybrid Search)
Ngoài dense vector (mảng float đặc), Qdrant hỗ trợ **sparse vector** cho keyword matching:
```python
from qdrant_client.models import SparseVector

sparse = SparseVector(
    indices=[12, 45, 892],     # index của từ trong vocabulary
    values=[0.73, 0.21, 0.95]  # weight của từ đó
)
```

---

## 4. Payload

### Là gì?
Payload là **JSON object tự do** gắn kèm với mỗi point. Dùng để:
- Lưu nội dung gốc để trả về cho user
- Làm điều kiện lọc (filter) khi search
- Lưu metadata phục vụ business logic

### Ví dụ Payload
```python
payload = {
    # Dạng string
    "title": "Introduction to Machine Learning",
    "category": "education",
    "author": "John Doe",

    # Dạng số
    "year": 2024,
    "rating": 4.5,
    "page_count": 320,

    # Dạng boolean
    "is_published": True,

    # Dạng array
    "tags": ["machine learning", "AI", "beginner"],

    # Dạng datetime
    "created_at": "2024-01-15T08:00:00Z"
}
```

### Tạo Payload Index — BẮT BUỘC trước khi Filter

> **Không có index → filter phải full scan toàn bộ collection → rất chậm O(n)**  
> **Có index → lookup O(log n)**

```python
# Phải tạo index trên field sẽ dùng để filter
client.create_payload_index(
    collection_name="my_collection",
    field_name="category",
    field_schema="keyword"   # keyword = exact match string
)

client.create_payload_index(
    collection_name="my_collection",
    field_name="year",
    field_schema="integer"
)

client.create_payload_index(
    collection_name="my_collection",
    field_name="rating",
    field_schema="float"
)

client.create_payload_index(
    collection_name="my_collection",
    field_name="created_at",
    field_schema="datetime"
)
```

### Các loại field_schema
| Schema | Dùng cho |
|--------|----------|
| `keyword` | String, exact match |
| `integer` | Số nguyên, range query |
| `float` | Số thực, range query |
| `bool` | True/False |
| `datetime` | Ngày giờ, range query |
| `geo` | Toạ độ địa lý |
| `text` | Full-text search |

---

## 5. Filter

### Là gì?
Filter cho phép **kết hợp vector search với điều kiện metadata** — tìm vector gần nhất trong tập con thỏa mãn điều kiện.

### 3 Toán tử chính
| Toán tử | Ý nghĩa |
|---------|---------|
| `must` | AND — tất cả điều kiện phải đúng |
| `should` | OR — ít nhất 1 điều kiện đúng |
| `must_not` | NOT — điều kiện không được thỏa |

### Filter cơ bản
```python
from qdrant_client.models import Filter, FieldCondition, MatchValue

# Lọc đúng 1 giá trị
f = Filter(
    must=[
        FieldCondition(
            key="category",
            match=MatchValue(value="education")
        )
    ]
)
```

### Kết hợp nhiều điều kiện
```python
from qdrant_client.models import (
    Filter, FieldCondition, MatchValue,
    MatchAny, Range
)

f = Filter(
    must=[
        # category phải là "education" hoặc "science"
        FieldCondition(
            key="category",
            match=MatchAny(any=["education", "science"])
        ),
        # year phải từ 2020 trở lên
        FieldCondition(
            key="year",
            range=Range(gte=2020)
        )
    ],
    must_not=[
        # loại trừ draft
        FieldCondition(
            key="is_published",
            match=MatchValue(value=False)
        )
    ]
)
```

### Range operators
```python
Range(gt=5)    # greater than
Range(gte=5)   # greater than or equal
Range(lt=10)   # less than
Range(lte=10)  # less than or equal
Range(gte=5, lte=10)  # between 5 and 10
```

---

## 6. Upsert

### Là gì?
**Upsert = Update + Insert**
- Point ID **đã tồn tại** → overwrite (update)
- Point ID **chưa tồn tại** → tạo mới (insert)
- Luôn **idempotent** — gọi nhiều lần với cùng data cho kết quả giống nhau

### Upsert cơ bản
```python
from qdrant_client.models import PointStruct

client.upsert(
    collection_name="my_collection",
    points=[
        PointStruct(
            id=1,
            vector=[0.23, -0.87, 0.41, 0.15],
            payload={"title": "Doc A", "category": "education"}
        ),
        PointStruct(
            id=2,
            vector=[0.55, 0.12, -0.33, 0.88],
            payload={"title": "Doc B", "category": "science"}
        )
    ]
)
```

### Upsert nhiều points (batch)
```python
# Build danh sách points
points = [
    PointStruct(
        id=i,
        vector=vectors[i].tolist(),
        payload={"title": docs[i]["title"]}
    )
    for i in range(len(docs))
]

# Upsert theo batch để tránh timeout
batch_size = 100
for i in range(0, len(points), batch_size):
    client.upsert(
        collection_name="my_collection",
        points=points[i:i + batch_size]
    )
```

### Cập nhật chỉ Payload (không đổi vector)
```python
# Update payload của point đã có
client.set_payload(
    collection_name="my_collection",
    payload={"rating": 4.8, "updated_at": "2024-02-01"},
    points=[1, 2, 3]  # list point IDs cần update
)

# Xóa 1 field trong payload
client.delete_payload(
    collection_name="my_collection",
    keys=["old_field"],
    points=[1]
)
```

### Xóa Points
```python
from qdrant_client.models import PointIdsList

client.delete(
    collection_name="my_collection",
    points_selector=PointIdsList(points=[1, 2, 3])
)
```

---

## 7. Search

### Dense Search — Tìm theo ngữ nghĩa
```python
results = client.search(
    collection_name="my_collection",
    query_vector=[0.23, -0.87, 0.41, 0.15],  # vector của câu hỏi
    limit=5,            # lấy top 5 kết quả
    with_payload=True,  # trả về payload
    with_vectors=False  # không cần trả về vector gốc
)

for hit in results:
    print(f"Score: {hit.score:.4f} | ID: {hit.id}")
    print(f"Title: {hit.payload['title']}")
```

### Search kết hợp Filter
```python
from qdrant_client.models import Filter, FieldCondition, MatchValue

results = client.search(
    collection_name="my_collection",
    query_vector=[0.23, -0.87, 0.41, 0.15],
    query_filter=Filter(
        must=[
            FieldCondition(key="category", match=MatchValue(value="education"))
        ]
    ),
    limit=5,
    score_threshold=0.7  # chỉ lấy kết quả có score >= 0.7
)
```

### Search theo ID (lấy bằng ID thay vì vector)
```python
# Lấy point bằng ID
results = client.retrieve(
    collection_name="my_collection",
    ids=[1, 2, 3],
    with_payload=True
)
```

### Scroll — Lấy tất cả points (không cần query vector)
```python
# Lấy toàn bộ points trong collection (có thể kết hợp filter)
results, next_offset = client.scroll(
    collection_name="my_collection",
    scroll_filter=Filter(
        must=[FieldCondition(key="category", match=MatchValue(value="education"))]
    ),
    limit=100,
    with_payload=True
)
```

### Count — Đếm số points
```python
count = client.count(
    collection_name="my_collection",
    count_filter=Filter(
        must=[FieldCondition(key="category", match=MatchValue(value="education"))]
    )
)
print(count.count)
```

---

## 8. Tổng Hợp Nhanh

| Concept | Một câu mô tả |
|---------|--------------|
| **Collection** | Không gian lưu trữ, khai báo vector size + distance metric một lần cố định |
| **Point** | Đơn vị dữ liệu = id + vector + payload |
| **Vector** | Mảng float biểu diễn nội dung trong không gian nhiều chiều |
| **Payload** | JSON metadata gắn kèm point, dùng để filter và trả kết quả |
| **Filter** | Lọc must/should/must_not trên payload, cần index trước |
| **Upsert** | Insert nếu ID mới, Update nếu ID cũ — idempotent |
| **Search** | Tìm k vectors gần nhất với query vector, có thể kết hợp filter |

---

## 9. Checklist Tự Kiểm Tra

| # | Câu hỏi |
|---|---------|
| 1 | Sau khi tạo collection, có thể đổi `vector size` không? Tại sao? |
| 2 | Point bắt buộc phải có payload không? |
| 3 | Cosine và Euclidean khác nhau ở điểm gì? Khi nào dùng cái nào? |
| 4 | Tại sao phải tạo payload index trước khi filter? |
| 5 | `must` vs `should` khác nhau thế nào? |
| 6 | Upsert với ID đã tồn tại thì chuyện gì xảy ra? |
| 7 | `score_threshold` trong search có tác dụng gì? |
| 8 | Khác gì giữa `search` và `scroll`? |
| 9 | Sparse vector dùng trong trường hợp nào? |
| 10 | `set_payload` vs upsert toàn bộ point — khi nào dùng cái nào? |

---

*Tài liệu tham khảo: [Qdrant Documentation](https://qdrant.tech/documentation/)*
