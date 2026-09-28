# gateway-ui

Giao diện web cho **Multi-Tenant RAG Gateway**. Repo này tách biệt khỏi `gateway-api` — xem phần [Liên kết với gateway-api](#liên-kết-với-gateway-api) bên dưới để hiểu cách hai repo giao tiếp.

---

## Mục lục

- [Yêu cầu môi trường](#yêu-cầu-môi-trường)
- [Bắt đầu nhanh](#bắt-đầu-nhanh)
- [Chạy bằng Docker](#chạy-bằng-docker)
- [Cấu trúc thư mục](#cấu-trúc-thư-mục)
- [Nguyên tắc tổ chức code](#nguyên-tắc-tổ-chức-code)
- [Quy tắc ranh giới giữa các feature](#quy-tắc-ranh-giới-giữa-các-feature)
- [Liên kết với gateway-api](#liên-kết-với-gateway-api)
- [Quy ước đặt tên & convention](#quy-ước-đặt-tên--convention)
- [Câu hỏi thường gặp](#câu-hỏi-thường-gặp)

---

## Yêu cầu môi trường

- Node.js 20.19+ hoặc Node.js 22 LTS nếu chạy local
- Docker Desktop nếu chạy bằng Docker Compose
- `gateway-api` đang chạy (local qua `docker compose up -d` hoặc trỏ tới môi trường dev chung)

## Bắt đầu nhanh

```bash
git clone <repo-url> gateway-ui
cd gateway-ui
cp .env.example .env.local     # chỉnh VITE_API_BASE_URL trỏ về gateway-api
npm install
npm run dev
```

## Chạy bằng Docker

Chạy riêng UI từ `compose.yaml` ở thư mục gốc:

```bash
docker compose up --build ui
```

UI mặc định mở ở `http://localhost:5173` và gọi gateway-api qua `VITE_API_BASE_URL=http://localhost:8000`.

Chạy cả backend stack kèm UI:

```bash
docker compose up --build
```

---

## Cấu trúc thư mục

```

gateway-ui/
├── node_modules/
├── public/
│   ├── favicon.svg
├── src/
│   ├── features/                         # Dành cho user thường, luôn trong phạm vi 1 tenant
│   │   ├── documents/
│   │   ├── chat/
│   │   └── health/                       # Bản health cơ bản, user thường xem được
│   │
│   ├── admin/                            # [MỚI] Dành riêng cho admin, cross-tenant
│   │   ├── features/
│   │   │   ├── tenant-management/        # Tạo/xóa/sửa tenant — khác hẳn TenantSwitcher của user thường
│   │   │   │   ├── components/
│   │   │   │   │   ├── TenantTable.jsx
│   │   │   │   │   ├── CreateTenantForm.jsx
│   │   │   │   │   └── TenantUsageStats.jsx   # Số document, số request/tenant
│   │   │   │   ├── hooks/
│   │   │   │   │   └── useTenantAdmin.js       # gọi POST/DELETE /v1/tenants — quyền admin mới có
│   │   │   │   └── pages/
│   │   │   │       └── TenantManagementPage.jsx
│   │   │   │
│   │   │   ├── system-health/            # Bản mở rộng của health/ — chi tiết hơn, admin-only
│   │   │   │   ├── components/
│   │   │   │   │   ├── ServiceStatusGrid.jsx    # Giống health/ nhưng thêm latency history
│   │   │   │   │   └── ErrorLogViewer.jsx
│   │   │   │   └── pages/
│   │   │   │       └── SystemHealthPage.jsx
│   │   │   │
│   │   │   └── audit-log/                # Xem log truy vấn, ai làm gì (nếu backend hỗ trợ)
│   │   │       └── pages/
│   │   │           └── AuditLogPage.jsx
│   │   │
│   │   ├── components/                   # UI dùng riêng trong admin, VD: AdminSidebar khác Sidebar thường
│   │   └── layout/
│   │       └── AdminLayout.jsx           # Layout riêng, có thể có nav khác hẳn user thường
│   │
│   ├── shared/                           # Vẫn dùng chung cho cả admin lẫn user thường
│   │
│   ├── router/
│   │   └── routes.jsx                    # Định nghĩa route /admin/* riêng, có guard
│   │
│   └── context/
│       └── AuthContext.jsx               # [MỚI] biết user hiện tại có role admin hay không
│
├── tests/
│   ├── unit/
│   └── e2e/
│
└── scripts/
```

Mỗi feature bên trong `features/` đều theo cùng một khuôn 3 lớp:

```
features/<tên-feature>/
├── components/     # UI thuần túy — nhận props, render, KHÔNG tự gọi API
├── hooks/          # Logic trạng thái + gọi api/endpoints/ — cầu nối UI ↔ API
└── pages/          # Ráp components + hooks thành 1 trang hoàn chỉnh, được router import
```

---

## Nguyên tắc tổ chức code

**1. Tổ chức theo domain nghiệp vụ (feature), không theo loại file.**
Khi cần sửa tính năng "upload document", bạn chỉ mở một folder duy nhất: `features/documents/`. Không cần lục tìm trong `components/`, `hooks/`, `pages/` nằm rải rác khắp nơi.

**2. `components/` không được tự gọi API.**
Component chỉ nhận dữ liệu và callback qua `props`. Toàn bộ việc gọi `gateway-api` nằm trong `hooks/`. Điều này giúp component dễ test (chỉ cần mock data, không cần mock `fetch`) và dễ tái sử dụng.

```jsx
// ✅ Đúng — component chỉ render
export function DocumentList({ documents, onDelete }) {
  return documents.map((doc) => (
    <li key={doc.doc_id}>
      {doc.filename}
      <button onClick={() => onDelete(doc.doc_id)}>Xóa</button>
    </li>
  ));
}
```

```js
// ✅ Đúng — hook lo gọi API và quản lý state
export function useDocuments() {
  const { tenantId } = useTenantContext();
  const { data } = useQuery(["documents", tenantId], () =>
    listDocuments(tenantId),
  );
  return { documents: data };
}
```

**3. `pages/` là điểm vào duy nhất được `router/` import.**
`components/` và `hooks/` bên trong một feature không nên bị import trực tiếp từ `router/` hay từ feature khác.

**4. Chỉ đưa lên `shared/` khi thật sự dùng ở ≥ 2 feature.**
Đừng chuyển lên `shared/` "phòng khi sau này cần" — điều đó tạo abstraction sớm không cần thiết. Cứ để trong feature đến khi có nhu cầu dùng chung thật sự.

---

## Quy tắc ranh giới giữa các feature

> **Một feature không được import trực tiếp từ `components/` hoặc `hooks/` của feature khác.**

```js
// ❌ SAI — chat import thẳng vào nội bộ của documents
import { DocumentUploader } from "../../documents/components/DocumentUploader";

// ✅ ĐÚNG — nếu cần dùng chung, chuyển lên shared/ trước
import { FileUploadWidget } from "../../../shared/components/ui/FileUploadWidget";
```

**Vì sao quy tắc này quan trọng:** nếu không giữ ranh giới, các feature sẽ dần phụ thuộc chéo vào nhau (coupling), và ta mất đi lợi ích chính của việc tách feature — khả năng sửa hoặc xóa một feature mà không ảnh hưởng domain khác.

Nếu bạn thấy mình cần import chéo giữa 2 feature → dấu hiệu cho thấy đoạn code đó nên chuyển lên `shared/`, không phải lý do để phá vỡ quy tắc.

---

## Liên kết với gateway-api

`features/` trong repo này ánh xạ 1-1 có chủ đích với `app/api/routes/` bên `gateway-api`:

| `gateway-api`                 | `gateway-ui`              |
| ----------------------------- | ------------------------- |
| `app/api/routes/tenants.py`   | `src/features/tenants/`   |
| `app/api/routes/documents.py` | `src/features/documents/` |
| `app/api/routes/chat.py`      | `src/features/chat/`      |
| `app/api/routes/health.py`    | `src/features/health/`    |

Khi backend đổi route hoặc schema, tra đúng feature tương ứng bên UI để cập nhật — không cần hỏi ai định vị ở đâu.

**Mọi request tới API phải đi qua `src/api/client.js`**, không gọi `fetch()` trực tiếp trong component hay hook. `client.js` tự động:

- Gắn header `X-Tenant-ID` từ `TenantContext`
- Sinh và gắn `X-Request-ID` để đối chiếu log với backend khi debug
- Parse error theo đúng envelope chuẩn trong `api_contract.md`:

```json
{
  "error_code": "TENANT_NOT_FOUND",
  "message": "No tenant exists with the given ID.",
  "request_id": "...",
  "timestamp": "..."
}
```

**Trước khi code một tính năng mới liên quan tới API**, luôn kiểm tra `api_contract.md` bên `gateway-api` trước — nếu endpoint/schema chưa được định nghĩa đầy đủ, trao đổi với người phụ trách backend để chốt schema trước, tránh code lại nhiều lần khi contract thay đổi.

---

## Quy ước đặt tên & convention

| Loại           | Convention                  | Ví dụ                                 |
| -------------- | --------------------------- | ------------------------------------- |
| Component      | PascalCase                  | `DocumentUploader.jsx`                |
| Hook           | camelCase, tiền tố `use`    | `useDocuments.js`                     |
| Hàm gọi API    | camelCase, động từ rõ nghĩa | `listDocuments()`, `deleteDocument()` |
| Folder feature | chữ thường, số nhiều        | `documents/`, `tenants/`              |

- Component không viết logic gọi API trực tiếp — luôn qua hook.
- Không hard-code base URL — luôn dùng biến môi trường `VITE_API_BASE_URL`.
- Không commit `.env.local` — chỉ commit `.env.example`.

---

## Câu hỏi thường gặp

**Tôi cần thêm 1 tính năng mới hoàn toàn (VD: "analytics"), bắt đầu từ đâu?**
Tạo `features/analytics/` với đủ 3 folder con `components/`, `hooks/`, `pages/`. Nếu backend chưa có route tương ứng, phối hợp với team backend để thêm vào `app/api/routes/` và `api_contract.md` trước.

**Tôi cần một component dùng ở 2 feature, để ở đâu?**
Chuyển vào `shared/components/ui/`. Không giữ 2 bản trùng lặp ở 2 feature.

**Vì sao `api/endpoints/` không trùng với `routes/` bên gateway-api?**
`routes/` bên backend là nơi **cung cấp** endpoint. `api/endpoints/` bên UI là nơi **gọi tới** endpoint đó. Hai lớp riêng biệt của hai phía client/server, không phải trùng lặp.

**Dự án dùng JS hay TS?**
Xem `package.json` / có `tsconfig.json` hay không trong repo. Cấu trúc thư mục giữ nguyên ở cả hai phiên bản, chỉ khác đuôi file (`.jsx` vs `.tsx`) và có/không có `api/types/`.
