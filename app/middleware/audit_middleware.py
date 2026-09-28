import time
import uuid 
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.services.audit_logger import audit_logger

class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Bắt đầu bấm giờ
        start_time = time.time()
        
        # Tạo request_id mặc định nếu client không truyền lên qua header
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # 2. Cho phép Request đi tiếp vào bên trong các API Router xử lý
        response = await call_next(request)
        
        # 3. Request đã xử lý xong -> Dừng bấm giờ, tính Latency (ms)
        latency_ms = int((time.time() - start_time) * 1000)

        # 4. Lấy tenant_id từ request.state (Do hệ thống Auth của bạn đã set trước đó)
        # Nếu API nào không yêu cầu auth, ta để mặc định là "system" hoặc "anonymous"
        tenant_id = getattr(request.state, "tenant_id", None)
        if not tenant_id:
            tenant_id = request.headers.get("X-Tenant-ID", "system")

        user_id = getattr(request.state, "user_id", None)
        if not user_id and hasattr(request.state, "user"):
            user_id = getattr(request.state.user, "id", None)
        if not user_id:
            user_id = request.headers.get("X-User-ID")

        # 5. Đóng gói dữ liệu Log
        log_payload = {
            "tenant_id": str(tenant_id),
            "user_id": user_id if user_id else None,
            "request_id": request_id,
            "endpoint": str(request.url.path),
            "method": request.method,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
        }

        # 6. Đẩy vào Queue bất đồng bộ (CỰC KỲ NHANH, không block việc trả Response)
        await audit_logger.log_event(log_payload)

        return response