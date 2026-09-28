# Đề Xuất Kiến Trúc Lưu Audit Log Cho Hệ Thống RAG API Gateway (Đa Tenant)

## 1. Các Mô Hình Ghi Audit Log & Đánh Giá Latency

### Mô hình 1: Asynchronous / Non-blocking In-Memory (Ghi bất đồng bộ qua Bộ nhớ tạm)
* Cách hoạt động: Khi request hoàn tất, ứng dụng **đẩy log object vào một Queue trong bộ nhớ** (ví dụ: `asyncio.Queue` trong Python / `Channel` trong Go) và lập tức trả kết quả cho client. Một worker chạy nền (background task) sẽ lấy log từ Queue và ghi vào db.
* Tác động Latency: **Rất thấp** (~0ms bổ sung). Response được trả về ngay lập tức cho client mà không chờ I/O ghi log.
* Lợi ích: Tối ưu hiệu năng tối đa cho API.
* Rủi ro: Mất dữ liệu khi crash. Nếu service bị sập bất ngờ (OOM, restart container, mất điện), toàn bộ log còn nằm trong memory queue chưa kịp flush ra storage sẽ bị mất.

### Mô hình 2: Log-to-stdout + External Log Collector (Kiến trúc Cloud-Native)
* Cách hoạt động: Ứng dụng chỉ cần ghi Structured Log (JSON) ra chuẩn đầu ra `stdout` (sử dụng thư viện ghi log bất đồng bộ). Một Agent bên ngoài chạy song song (ví dụ: Fluentbit, Logstash, Vector) đóng vai trò làm Daemon/Sidecar sẽ "tail" đọc stdout từ container và chuyển về Log Storage/Database (Elasticsearch, Loki, OpenSearch,...).
* Tác động Latency:** **Gần như bằng 0** (< 1ms). Việc ghi vào `stdout` của container OS được xử lý rất nhanh qua bộ đệm của hệ điều hành (OS buffer).
* Ưu điểm:
  * Giải phóng hoàn toàn logic I/O ghi log ra khỏi mã nguồn ứng dụng.
  * Chuẩn hóa theo nguyên tắc 12-Factor App, dễ scaling.
  * Tận dụng khả năng retry, buffering mạnh mẽ của các log agent chuyên dụng (Fluentbit/Vector).
* Nhược điểm: Phụ thuộc vào hạ tầng Docker/Kubernetes và đòi hỏi thiết lập thêm Sidecar/DaemonSet.

### Mô hình 3: Distributed Message Queue (MQ-based Auditing)
* Cách hoạt động: Luồng xử lý chính kết nối với một Message Broker tầm trung/lớn (như Kafka, RabbitMQ, Amazon SQS, Redis Stream) thông qua một Producer bất đồng bộ và đẩy sự kiện audit log vào Queue. Các Log Consumer sẽ pull dữ liệu từ Queue này để lưu trữ lâu dài.
* Tác động Latency: **Thấp** (1 - 5ms). Độ trễ chính là thời gian gửi mạng (network round-trip) từ Gateway tới Message Broker.
* Ưu điểm:
  * Độ bền cao: Nếu Storage đích (Elasticsearch, PostgreSQL...) bị nghẽn hoặc sập, Message Broker vẫn giữ vai trò đệm (buffer/backpressure) và không làm trôi log.
  * Có khả năng scale độc lập luồng ghi và luồng đọc.
* Nhược điểm: Tăng chi phí vận hành và tính phức tạp của kiến trúc hệ thống.

---

### Mô hình 4: Synchronous Direct Database Insert (Ghi trực tiếp đồng bộ)
* Cách hoạt động: Ứng dụng thực hiện truy vấn `INSERT` trực tiếp thông tin audit log vào Database (PostgreSQL, MongoDB, ClickHouse...) trước khi trả kết quả response cho client.
* Tác động Latency: **Rất cao** (10ms - 100ms+). Mọi request API đều phải gánh thêm độ trễ của Network I/O + Database Write I/O + Transaction Locking.
* Đánh giá: **KHÔNG KHUYẾN NGHỊ** cho API Gateway hoặc các hệ thống có lưu lượng tải lớn. Chỉ dùng cho các giao dịch tài chính/ngân hàng khắt khe cực kỳ ưu tiên tính toàn vẹn đồng bộ hơn là tốc độ.

---

## 2. Bảng So Sánh Tổng Quan Các Phương Án

| Phương án Kiến trúc | Latency ảnh hưởng API | Mức độ an toàn dữ liệu | Băng thông / Tải chịu được | Chi phí triển khai | Phù hợp cho |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Async In-Memory** | **Rất thấp (~0ms)** | Thấp (Dễ mất log) | Trung bình | Rất dễ | Project nhỏ, Lab, MVP |
| **2. Stdout + Sidecar Agent** | **Rất thấp (<1ms)** | Cao | Rất cao | Trung bình | **Microservices, Docker, K8s (Khuyên dùng)** |
| **3. External Message Queue** | **Thấp (1-5ms)** | Rất cao | Cực cao | Khá cao | Hệ thống Enterprise, Tải cực lớn |
| **4. Sync DB Write** | **Rất cao (>10ms)** | Tuyệt đối | Thấp | Dễ | API ít traffic, yêu cầu transaction đồng bộ |

---

## 3. Lựa Chọn Storage Lưu Trừ (Database Level)

Tùy thuộc vào bản chất tính chất tra cứu của Audit Log để chọn lưu trữ phù hợp:

1. **ClickHouse / TimescaleDB (Time-series / OLAP DB):** 
   * *Ưu điểm:* Tốc độ ghi nén cực khủng, tối ưu cho việc ghi liên tục (Append-only) và truy vấn thống kê log theo thời gian. Tốn rất ít dung lượng đĩa.
2. **Elasticsearch / OpenSearch:**
   * *Ưu điểm:* Mạnh nhất về khả năng tìm kiếm full-text, hỗ trợ dashboard trực quan (Kibana).
3. **PostgreSQL / MySQL (Relational DB):**
   * *Ưu điểm:* Dễ dùng, sẵn có.
   * *Nhược điểm:* Khi bảng log lên đến hàng chục/trăm triệu bản ghi sẽ gây chậm hệ thống. Cần phân vùng dữ liệu (Partitioning) theo ngày/tháng nếu sử dụng.

---

## 4. Khuyến Nghị & Mẹo Tối Ưu Cho RAG API Gateway

### 💡 Khuyến nghị Kiến trúc:
1. **Ứng dụng Gateway (FastAPI):**
   * Sử dụng Middleware để log thông tin dạng **Structured JSON** bao gồm đầy đủ context (`tenant_id`, `request_id`, `latency_ms`, `status_code`...).
   * Ghi log dạng bất đồng bộ xuất thẳng ra `stdout`.
2. **Hạ tầng Log Collector:**
   * Sử dụng **Fluentbit** hoặc **Vector** làm daemon để thu gom log từ `stdout`.
   * Cấu hình **Buffer (Disk Buffer)** trong Fluentbit để đề phòng trường hợp Storage đích bị ngắt kết nối thì log vẫn lưu an toàn trên đĩa cục bộ.
3. **Nơi lưu trữ (Storage Destination):**
   * Đẩy log về **OpenSearch / Elasticsearch** (phục vụ search log UI) hoặc **ClickHouse** (phục vụ phân tích / đếm token / billing cho từng Tenant).

### ⚡ Các kỹ thuật giảm độ trễ (Latency Mitigation):
* **Batching:** Luôn gom các bản ghi log thành từng batch (ví dụ: gom 100 logs hoặc 1 giây/lần) trước khi thực hiện hành động I/O (ghi DB / đẩy MQ).
* **Sampling (Lấy mẫu):** Với các log truy vết thông thường (Debug/Info), chỉ ghi mẫu $10-20\%$ lượng request. Tuy nhiên đối với **Audit Log** (Security, Auth, Mutation, Error status codes), bắt buộc phải đảm bảo ghi đủ $100\%$.
