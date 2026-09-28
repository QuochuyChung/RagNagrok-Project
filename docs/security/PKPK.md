# Mã hóa bất đối xứng (Public Key / Private Key)

## 1. Giới thiệu

### 1.1 Mã hóa dữ liệu là gì?

- Khái niệm mã hóa dữ liệu.
- Vì sao cần mã hóa.
- Các vấn đề cần giải quyết:
  - Bảo mật.
  - Xác thực.
  - Toàn vẹn dữ liệu.
  - Chống giả mạo.

---

## 2. Hai loại mã hóa phổ biến

### 2.1 Mã hóa đối xứng (Symmetric Encryption)

| Đặc điểm | Mô tả |
|----------|--------|
| Số khóa | 1 |
| Ví dụ | AES |
| Tốc độ | Nhanh |
| Nhược điểm | Khó trao đổi khóa |

Ví dụ:

Alice ↔ Bob dùng chung một khóa bí mật.

---

### 2.2 Mã hóa bất đối xứng (Asymmetric Encryption)

| Đặc điểm | Mô tả |
|----------|--------|
| Số khóa | 2 |
| Public key | Công khai |
| Private key | Bí mật |
| Ví dụ | RSA, ECC, Ed25519 |

---

## 3. Khái niệm Public Key và Private Key

### 3.1 Public Key

- Có thể chia sẻ cho mọi người.
- Dùng để mã hóa hoặc xác minh chữ ký.

### 3.2 Private Key

- Chỉ chủ sở hữu được giữ.
- Dùng để giải mã hoặc ký dữ liệu.

---

## 4. Nguyên lý hoạt động

### 4.1 Quy trình mã hóa

```text
Alice
    |
    | Encrypt bằng Public Key của Bob
    ↓

Ciphertext

    ↓

Bob dùng Private Key để giải mã
```

### 4.2 Quy trình giải mã

```text
Plaintext
    +
Public Key
    ↓

Ciphertext
    +
Private Key
    ↓

Plaintext
```

---

## 5. Chữ ký số (Digital Signature)

### 5.1 Mục đích

- Xác minh người gửi.
- Đảm bảo dữ liệu chưa bị chỉnh sửa.
- Chống chối bỏ.

### 5.2 Cơ chế

```text
Document
     +
Private Key
     ↓

Signature

     ↓

Người nhận dùng Public Key kiểm tra
```

---

## 6. Nền tảng toán học

### 6.1 RSA hoạt động như thế nào?

- Sinh hai số nguyên tố lớn:

```text
p, q
```

- Tính:

```text
n = p × q
```

- Sinh public key và private key.

### 6.2 Tại sao không thể suy ngược?

- Bài toán phân tích số nguyên lớn.
- Độ khó tính toán.

---

## 7. Ví dụ thực tế

### 7.1 HTTPS

```text
Browser
    ↓
Nhận Public Key
    ↓
Sinh Session Key
    ↓
Mã hóa Session Key
    ↓
Server giải mã
```

### 7.2 SSH

- Đăng nhập máy chủ bằng cặp khóa.

### 7.3 JWT

- Ký token bằng private key.
- Xác thực bằng public key.

### 7.4 GitHub SSH Key

- Push/Pull mà không cần nhập mật khẩu.

---

## 8. So sánh các thuật toán

| Thuật toán | Loại | Tốc độ | Độ phổ biến |
|------------|--------|--------|--------|
| AES | Đối xứng | Rất nhanh | Rất cao |
| RSA | Bất đối xứng | Chậm | Cao |
| ECC | Bất đối xứng | Nhanh hơn RSA | Rất cao |
| Ed25519 | Chữ ký số | Rất nhanh | Ngày càng phổ biến |

---

## 9. Tại sao HTTPS không dùng RSA để mã hóa toàn bộ dữ liệu?

- RSA chậm.
- Chỉ dùng để trao đổi khóa.
- Sau đó chuyển sang AES.

```text
RSA/ECC
     ↓

Trao đổi khóa

     ↓

AES

     ↓

Mã hóa dữ liệu
```

---

## 10. Các lỗi bảo mật phổ biến

- Commit private key lên GitHub.
- Lưu private key dưới dạng plaintext.
- Dùng khóa quá ngắn.
- Chia sẻ private key.
- Không xoay vòng khóa (key rotation).

---

## 11. Tổng kết

| Thành phần | Vai trò |
|------------|----------|
| Public Key | Mã hóa / xác minh |
| Private Key | Giải mã / ký |
| RSA | Trao đổi khóa |
| AES | Mã hóa dữ liệu |
| Digital Signature | Xác thực |

---

## 12. Tài liệu tham khảo

- RFC 8017 (RSA)
- RFC 8446 (TLS 1.3)
- OpenSSL Documentation
- OWASP Cryptographic Storage Cheat Sheet

## 13. Ứng dụng trong hệ thống Multi-tenant RAG Gateway

### JWT Authentication

Gateway ký JWT bằng private key:

```text
Gateway (Private Key)
        ↓
     JWT Token
```

Service khác dùng public key để xác thực:

```text
JWT
   +
Public Key
   ↓
Verified
```

### Mã hóa API Key

- API Key được mã hóa trước khi lưu database.
- Private key được giữ trên server.

### Giao tiếp HTTPS

Frontend ↔ Gateway ↔ Service sử dụng TLS.