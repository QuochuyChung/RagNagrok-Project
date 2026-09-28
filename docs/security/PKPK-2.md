# TECHNICAL DOCUMENTATION & ARCHITECTURE DECISION RECORD (ADR)

## 📑 MỤC LỤC
1. [Bối cảnh & Bài toán Kỹ thuật (Context)](#1-bối-cảnh--bài-toán-kỹ-thuật-context)
2. [Khái niệm & Nguyên lý Cốt lõi (Core Concepts)](#2-khái-niệm--nguyên-lý-cốt-lõi-core-concepts)
3. [Thiết kế Kiến trúc Mã hóa (Architecture Design)](#3-thiết-kế-kiến-trúc-mã-hóa-architecture-design)
4. [Thay đổi về Cấu trúc Cơ sở Dữ liệu (Database Schema Changes)](#4-thay-đổi-về-cấu-trúc-cơ-sở-dữ-liệu-database-schema-changes)
5. [Sơ đồ Luồng Hoạt động (Sequence Diagrams)](#5-sơ-đồ-luồng-hoạt-động-sequence-diagrams)
6. [Đánh giá Ưu & Nhược điểm (Trade-offs)](#6-đánh-giá-ưu--nhược-điểm-trade-offs)
7. [Kế hoạch Thực thi & Actionable Sub-tasks](#7-kế-hoạch-thực-thi--actionable-sub-tasks)

---

## 1. BỐI CẢNH & BÀI TOÁN KỸ THUẬT (CONTEXT)

Hệ thống RAG API Gateway đang áp dụng mô hình kiến trúc **One Schema Per Tenant (SPT)**. Mô hình này đã giải quyết tốt việc cô lập dữ liệu về mặt logic giữa các Tenant qua cơ chế `SET search_path`. 

Tuy nhiên, hệ thống vẫn đối mặt với 2 rủi ro bảo mật nghiêm trọng:
1. **Rủi ro Quản trị viên (Platform Admin / DBA):** Cấp trên nắm quyền Root Database Server hoàn toàn có thể đọc trộm văn bản tri thức thô (raw text documents) của khách hàng.
2. **Rủi ro rò rỉ dữ liệu RAG:** Dữ liệu nhạy cảm nhồi vào LLM Prompt yêu cầu bảo vệ tuyệt đối ở mức "Chủ quyền khóa" (Bring Your Own Key - BYOK).

**Mục tiêu:** Thiết kế cơ chế mã hóa sao cho **khi Database bị đâm thủng hoặc Admin mở trực tiếp DB ra xem, họ chỉ thấy các chuỗi vô nghĩa (Ciphertext)**, trong khi tính năng Semantic Search của RAG vẫn hoạt động chính xác.

---

## 2. KHÁI NIỆM & NGUYÊN LÝ CỐT LÕI (CORE CONCEPTS)

Để đảm bảo hiệu năng và tính bảo mật cao nhất, giải pháp phối hợp **2 cơ chế mã hóa**:

### 2.1. Mã hóa bất đối xứng (Public / Private Keys - RSA/ECC)
* **Public Key (Khóa công khai):** Dùng để **MÃ HÓA**. Khóa này không cần bảo mật tuyệt đối, có thể lưu ở `public` schema. API Gateway dùng Public Key của Tenant nào thì chỉ mã hóa được cho Tenant đó.
* **Private Key (Khóa bí mật):** Dùng để **GIẢI MÃ**. Chỉ thuộc về chủ sở hữu Tenant. Không lưu trữ dưới dạng rõ (cleartext) ở bất kỳ bảng nào trong Database.

### 2.2. Mã hóa phong bì (Envelope Encryption)
Do thuật toán mã hóa bất đối xứng (RSA) xử lý dữ liệu lớn rất chậm, chúng ta kết hợp với mã hóa đối xứng (AES-256-GCM):
* **Data Encryption Key (DEK):** Một khóa đối xứng ngẫu nhiên sinh ra cho từng file/chunk dữ liệu để mã hóa cực nhanh văn bản thô.
* **Key Encryption Key (KEK / Public Key):** Dùng Public Key RSA của Tenant để mã hóa (bọc) khóa DEK đó lại.
* **Encrypted DEK:** Khóa DEK đã bị bọc, an toàn để lưu thẳng vào Database cùng với nội dung mã hóa.

---

## 3. THIẾT KẾ KIẾN TRÚC MÃ HÓA (ARCHITECTURE DESIGN)

### 3.1. Nguyên tắc vàng
> 🛑 **Mọi thao tác mã hóa và giải mã bắt buộc phải diễn ra tại RAM của RAG API Gateway.**  Không sử dụng các hàm mã hóa tầng DB (như `pgcrypto`) để tránh lộ khóa trên log truy vấn

### 3.2. Xử lý đặc thù cho RAG (Text vs. Embeddings)
* **Nội dung văn bản (`content`):** Áp dụng Envelope Encryption.
* **Tọa độ Vector (`embedding`):** Giữ ở **dạng rõ (Cleartext vector)**.
  * *Lý do:* Nếu mã hóa vector, các toán tử tính toán khoảng cách như Cosine Similarity (`<=>`) của `pgvector` sẽ bị hỏng. Tính cô lập của Vector được bảo vệ tuyệt đối bởi vách ngăn Schema.

---

## 4. THAY ĐỔI VỀ CẤU TRÚC CƠ SỞ DỮ LIỆU (DATABASE SCHEMA CHANGES)

### 4.1. Vùng Chung (`public.tenants`)
Thêm trường chứa Public Key dùng để mã hóa dữ liệu bất kỳ lúc nào mà không cần chờ Tenant truyền Private Key.

```sql
ALTER TABLE public.tenants 
ADD COLUMN public_key TEXT NULL; -- Lưu định dạng PEM của RSA Public Key
```
### 4.2. Vùng Riêng (`schema_<tenant_name>.chunks`)
Xóa các trường rõ cũ, thay bằng các trường nhị phân/chuỗi đã mã hóa.

```sql
-- Thực thi trên từng Schema Tenant
ALTER TABLE schema_tenant_x.chunks 
DROP COLUMN content; -- Xóa cột văn bản rõ cũ

ALTER TABLE schema_tenant_x.chunks 
ADD COLUMN content BYTEA NOT NULL,             -- Chứa Ciphertext (nội dung đã mã hóa AES-256)
ADD COLUMN encrypted_dek TEXT NOT NULL,         -- Chứa DEK đã mã hóa bằng RSA Public Key
ADD COLUMN embedding vector(1536) NULL;         -- Giữ dạng rõ để chạy Semantic Search
```

## 5. SƠ ĐỒ LUỒNG HOẠT ĐỘNG (SEQUENCE DIAGRAMS)
### 5.1. Luồng Tải tài liệu & Mã hóa (Ingestion Phase)
```text
[User Tenant A]         [RAG API Gateway]               [Public DB Schema]           [Tenant Private DB Schema]
       |                        |                                |                               |
       |--- 1. Upload Doc ----->|                                |                               |
       |                        |--- 2. Lấy Public_Key_A ------->|                               |
       |                        |<-- Trả về Public_Key_A --------|                               |
       |                        |                                                                |
       |                        |--- 3. Sinh ngẫu nhiên DEK_A                                    |
       |                        |--- 4. Ciphertext = AES_Encrypt(Doc_Content, DEK_A)             |
       |                        |--- 5. Encrypted_DEK = RSA_Encrypt(DEK_A, Public_Key_A)         |
       |                        |--- 6. Embeddings = OpenAI_Embedding(Doc_Content)               |
       |                        |                                                                |
       |                        |--- 7. INSERT Ciphertext, Encrypted_DEK, Embeddings ----------->|
       |                        |    (Lưu vào schema_tenant_a.chunks)                            |
       |<-- 8. Success Status --|                                                                |
```
### 5.2. Luồng Tra cứu & Giải mã khi Chat RAG (Retrieval Phase)
```text
[User Tenant A]         [RAG API Gateway]          [Tenant Private DB Schema]              [LLM Service]
       |                        |                              |                                 |
       |-- 1. Chat Request ---->|                              |                                 |
       |  (Kèm Private_Key_A)   |                              |                                 |
       |                        |-- 2. SET search_path ------->|                                 |
       |                        |-- 3. Top-K Vector Search --->|                                 |
       |                        |<-- Trả Encrypted_DEK & ------|                                 |
       |                             Ciphertext Chunks         |                                 |
       |                        |                                                                |
       |                        |-- 4. DEK_A = RSA_Decrypt(Encrypted_DEK, Private_Key_A)         |
       |                        |-- 5. Raw_Text = AES_Decrypt(Ciphertext, DEK_A)                 |
       |                        |                                                                |
       |                        |-- 6. Send Prompt (Kèm Raw_Text Context) ---------------------->|
       |                        |<-- 7. Response Stream -----------------------------------------|
       |<-- 8. Trả lời User ----|                                                                |
       |                        |-- 9. WIPE Raw_Text & DEK_A FROM GATEWAY RAM IMMEDIATELY        |
```
## 6. ĐÁNH GIÁ ƯU & NHƯỢC ĐIỂM (TRADE-OFFS)
### Ưu điểm (Pros)

- Tuyệt đối an toàn trước Admin/DBA: Admin mở DB chỉ thấy Ciphertext. Nếu không có Private Key do Tenant giữ, không bao giờ đọc được văn bản thô.
- Tốc độ xử lý tối ưu: Nhờ Envelope Encryption, việc mã hóa file lớn diễn ra cực nhanh bằng thuật toán AES đối xứng.
- Tuân thủ chuẩn Enterprise: Đáp ứng các chứng chỉ an toàn dữ liệu khắt khe (SOC2, HIPAA, GDPR - Right to be forgotten).

### Nhược điểm & Thách thức (Cons & Mitigations)
- Quản lý Private Key: Nếu Tenant làm mất Private Key, dữ liệu của họ vĩnh viễn không thể khôi phục (Zero-knowledge architecture).
- Không hỗ trợ Text Search truyền thống: Không thể chạy câu lệnh SQL kiểu WHERE content LIKE '%abc%' trên DB. Mọi thao tác tìm kiếm bắt buộc phải dựa vào embedding vector.

## 7. KẾ HOẠCH THỰC THI & ACTIONABLE SUB-TASKS
Dưới đây là danh sách các Jira Sub-tasks đề xuất chuyển giao cho Sprint tiếp theo:

[ ] TASK-01 (DB): Viết file Alembic Migration cập nhật cột public_key tại public.tenants và biến đổi cấu trúc bảng chunks ở các tenant schemas sang dạng BYTEA mã hóa.

[ ] TASK-02 (Backend): Xây dựng Module CryptoService trong Python (sử dụng thư viện cryptography) đóng gói các hàm: generate_key_pair(), encrypt_envelope(), decrypt_envelope().

[ ] TASK-03 (API Gateway): Cập nhật Pipeline Ingestion: Tích hợp bước gọi CryptoService.encrypt_envelope() trước khi ghi dữ liệu vào PostgreSQL.

[ ] TASK-04 (API Gateway): Cập nhật Pipeline Retrieval: Bổ sung bước giải mã Encrypted_DEK bằng Private_Key gửi từ Request Header, sau đó giải mã content thô trên RAM trước khi ghép Prompt gửi LLM.