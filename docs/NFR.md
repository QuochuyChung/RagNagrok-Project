# Yêu Cầu Phi Chức Năng (Non-Functional Requirements - NFR)

## 1. Môi Trường & Luồng Phát Triển (Environment & Dev Workflow)
* Môi trường lab chính: Sử dụng Windows + WSL2 (Windows Subsystem for Linux 2).
* Quy trình quản lý mã nguồn (Git Workflow):
  * Chia nhánh tính năng rõ ràng (branches).
  * Sử dụng Pull Requests (PRs) / Merge Requests (MRs) trước khi hợp nhất mã nguồn.
  * Lịch sử commit tuân thủ quy chuẩn, truyền tải thông điệp rõ ràng (meaningful commits).
* Tài liệu hướng dẫn: Cung cấp tệp `README.md` với các hướng dẫn từng bước chi tiết (step-by-step) để cài đặt, cấu hình và khởi chạy ứng dụng.

---

## 2. Docker & Triển Khai (Docker & Deployment)
* Khởi chạy bằng Docker Compose: Đảm bảo khởi động toàn bộ hạ tầng (full stack) chỉ với một lệnh Compose duy nhất:
  * FastAPI gateway: Service Gateway tiếp nhận và xử lý yêu cầu API.
  * PostgreSQL: Relational Database phục vụ truy vấn CRUD, đảm bảo tính toàn vẹn dữ liệu
  * Qdrant: Vector Database phục vụ việc lưu trữ và truy vấn vector embedding.
  * Ollama: Service chạy mô hình ngôn ngữ lớn (LLM) và Embedding model cục bộ.
  * React UI: Giao diện người dùng phục vụ thử nghiệm và tương tác.
* Lưu trữ dữ liệu bền vững (Persistence):
  * Sử dụng Docker Volumes để duy trì dữ liệu của Qdrant không bị mất khi khởi động lại container (`persisted across restarts`).
* Kiểm tra trạng thái (Health checks):
  * Endpoint `GET /health` tại Gateway để kiểm tra tính sẵn sàng của ứng dụng.
  * Khai báo `healthcheck` trong container Docker nếu có thể.

---

## 3. Cấu Hình & Quản Lý Bí Mật (Configuration & Secrets Hygiene)
* Cấu hình qua biến môi trường (.env): Tất cả các tham số hệ thống phải được đọc từ biến môi trường hoặc tệp `.env`:
  * Các tham số bắt buộc: `QDRANT_URL`, `OLLAMA_URL`, tên mô hình (`MODEL names`), kích thước đoạn văn bản (`chunk sizes`), giới hạn tài nguyên (`limits`), v.v.
* Tuyệt đối không mã hóa cứng (No hardcoding):Không lưu URL, API Keys hay secret keys trực tiếp trong mã nguồn.
* Tệp mẫu: Cung cấp tệp mẫu `.env.example` chứa toàn bộ cấu hình mặc định và hướng dẫn thiết lập.

---

## 4. Khả Năng Giám Sát (Observability)
* Structured JSON Logs: Xuất nhật ký hệ thống dưới định dạng JSON chuẩn hóa, bao gồm đầy đủ các trường:
  * `tenant_id`: Mã định danh tenant.
  * `endpoint`: Đường dẫn API được gọi.
  * `latency_ms`: Thời gian xử lý yêu cầu (ms).
  * `status_code`: Mã trạng thái HTTP trả về.
  * `error_code`: Mã lỗi chi tiết (nếu có).
* Mã định danh truy vết (Correlation ID):
  * Chấp nhận header `X-Request-ID` từ request client hoặc tự động sinh mới nếu thiếu.
  * Trả lại `X-Request-ID` trong header của Response.
  * Đính kèm `X-Request-ID` vào toàn bộ log phát sinh trong cùng một luồng xử lý.
* Chế độ gỡ lỗi (Debug mode): Bật chế độ debug cho khâu truy xuất (retrieval) để hiển thị chi tiết thời gian phản hồi từng công đoạn (latency breakdown).

---

## 5. Giới Hạn, Kiểm Soát Tải & Xử Lý Lỗi (Limits, Backpressure & Error Handling)
* Áp dụng giới hạn yêu cầu (Enforce request limits):
  * Dung lượng tệp tải lên tối đa (`max upload size`).
  * Số lượng chunk tối đa cho mỗi tài liệu (`max chunks per doc`).
  * Thời gian chờ tối đa cho các lời gọi dịch vụ phía sau (`timeouts for downstream calls`).
* Phản hồi lỗi rõ ràng (Clear error responses):
  * Trả về đúng mã HTTP Status Code phù hợp (ví dụ: `413 Payload Too Large`, `422 Unprocessable Entity`, `500 Internal Server Error`, `503 Service Unavailable`).
  * Định dạng lỗi nhất quán theo cấu trúc JSON quy chuẩn (consistent JSON error schema).

---

## 6. Đảm Bảo Chất Lượng & Kiểm Thử (Quality Assurance - Tests)
* Độ bao phủ Pytest tối thiểu (Minimum pytest coverage):
  * `tenant required`: Kiểm tra bắt buộc phải truyền mã tenant.
  * `idempotent ingest`: Kiểm tra tính lặp lại an toàn khi nạp cùng một tài liệu nhiều lần.
  * `tenant isolation retrieval negative case`: Kiểm tra tính cách ly dữ liệu giữa các tenant (không thể truy vấn dữ liệu của tenant khác).
  * `chat returns citations`: Kiểm tra phản hồi trò chuyện có bao gồm trích dẫn nguồn (basic check).
* Kịch bản kiểm thử (Test scripts): Cung cấp các script để thực thi bộ kiểm thử dễ dàng tại Swagger hoặc UI

---

## 7. Khả Năng Chịu Lỗi & Kiểm Thử Tải Cơ Bản (Resilience & Basic Load Testing)
* Công cụ / Script kiểm thử tải nhẹ:
  * Thực hiện gửi từ 20 đến 50 yêu cầu đồng thời (`20-50 requests`).
  * Tổng hợp và báo cáo độ trễ (latency) và tỷ lệ lỗi (error rate).
* Kịch bản kiểm thử khắc phục sự cố (Failure test):
  * Khởi động lại hoặc dừng dịch vụ Qdrant → Gateway phải trả về lỗi `503 Service Unavailable` kèm thông điệp rõ ràng.
  * Khi Qdrant hoạt động trở lại → Gateway tự động khôi phục xử lý yêu cầu bình thường.
