# Git Workflow cho dự án

## 1. Mục tiêu

Git workflow giúp nhóm:

- Không sửa trực tiếp trên nhánh `main`.
- Mỗi công việc được thực hiện trên một nhánh riêng.
- Mọi thay đổi được review trước khi merge.
- Giữ cho `main` luôn ở trạng thái có thể chạy và demo.

---

## 2. Cấu trúc branch

```bash
main
├── feature/s1-fastapi
├── feature/s1-compose
├── test/s1-smoke-test
└── docs/s1-readme
```

Quy ước đặt tên:

- `feature/...`: phát triển chức năng mới.
- `fix/...`: sửa lỗi.
- `test/...`: thêm hoặc sửa kiểm thử.
- `docs/...`: cập nhật tài liệu.
- `chore/...`: cấu hình hoặc công việc bảo trì.

---

## 3. Quy trình làm một task

### Bước 1: Cập nhật `main`

```bash
git switch main
git pull origin main
```

### Bước 2: Tạo branch mới

```bash
git switch -c feature/s1-fastapi
```

### Bước 3: Viết code và kiểm tra thay đổi

```bash
git status
git diff
```

### Bước 4: Stage và commit

```bash
git add .
git commit -m "feat: add health and version endpoints"
```

### Bước 5: Push branch lên remote

Lần đầu:

```bash
git push -u origin feature/s1-fastapi
```

Các lần sau:

```bash
git push
```

### Bước 6: Tạo Pull Request

Tạo Pull Request:

```text
feature/s1-fastapi → main
```

Pull Request nên mô tả:

- Đã thay đổi những gì.
- Cách chạy thử.
- Kết quả mong đợi.
- Vấn đề còn tồn tại, nếu có.

### Bước 7: Review và merge

Một thành viên khác kiểm tra code, chạy thử và approve.

Sau khi merge:

```bash
git switch main
git pull origin main
git branch -d feature/s1-fastapi
```

---

## 4. Commit message

Cấu trúc:

```bash
loại: mô tả ngắn
```

Ví dụ:

```bash
feat: add health endpoint
fix: correct gateway port mapping
build: add Qdrant Compose service
test: add Sprint 1 smoke test
docs: add local setup instructions
chore: update gitignore
```

Không nên dùng các commit message không rõ nghĩa như:

```bash
update
fix
done
code mới
```

---

## 5. Khi branch cần cập nhật từ `main`

```bash
git switch main
git pull origin main

git switch feature/s1-compose
git merge main
```

Với nhóm mới, nên dùng `merge` thay vì `rebase` để quy trình dễ hiểu hơn.

---

## 6. Xử lý conflict

Conflict thường xảy ra khi nhiều người sửa cùng một phần của một file.

Cách xử lý:

1. Mở file bị conflict.
2. Chọn nội dung đúng.
3. Xóa các dấu `<<<<<<<`, `=======`, `>>>>>>>`.
4. Kiểm tra lại chương trình.
5. Commit phần đã xử lý.

```bash
git add <ten-file>
git commit -m "fix: resolve merge conflict"
```

Để hạn chế conflict:

- Chia công việc theo file hoặc module.
- Cập nhật `main` thường xuyên.
- Giữ Pull Request nhỏ.
- Không để branch tồn tại quá lâu.
- Trao đổi trước khi sửa file dùng chung.

---

## 7. Nguyên tắc làm việc của nhóm

1. Không push trực tiếp vào `develop`.
2. Mỗi task sử dụng một branch riêng.
3. Mỗi Pull Request tập trung vào một nhóm thay đổi.
4. Ít nhất một thành viên khác phải review.
5. Chỉ merge khi code đã được chạy thử.
6. Không commit `.env`, mật khẩu hoặc secret.
7. Luôn cập nhật `develop` trước khi tạo branch mới.
8. Xóa branch sau khi đã merge.
9. `develop` phải luôn có khả năng chạy và demo.
10. Trước khi kết thúc sprint, kiểm tra toàn bộ hệ thống từ `develop`.

---

## 8. Workflow tổng quát

```text
Cập nhật develop
    ↓
Tạo branch mới
    ↓
Viết code
    ↓
Commit
    ↓
Push branch
    ↓
Tạo Pull Request
    ↓
Review và sửa nếu cần
    ↓
Merge vào develop
    ↓
Xóa branch cũ
```
