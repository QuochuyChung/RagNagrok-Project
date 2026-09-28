import io
import os
import pytest
import uuid
from fastapi.testclient import TestClient

# =========================================================================
# 3 DÒNG MA THUẬT: ÉP ĐÈ CẤU HÌNH TEST KHÔNG ĐỘNG VÀO CORE SYSTEM
# =========================================================================
os.environ["QDRANT_HOST"] = "127.0.0.1"  # Trỏ về localhost của máy test
os.environ["OLLAMA_HOST"] = "127.0.0.1"  # Trỏ về localhost của máy test

from app.core.config import get_settings
get_settings.cache_clear()  # <--- BẮT BUỘC: Xóa cache cũ để Pydantic nạp lại theo biến os.environ mới!
# =========================================================================

# Sau đó import app chạy bình thường
from app.main import app

@pytest.fixture(scope="session")
def client():
    with TestClient(app) as client:
        yield client

@pytest.fixture(scope="session")
def platform_admin_header(client):
    """
    Sử dụng tài khoản System Admin đã seed sẵn để lấy JWT Token.
    Sử dụng 'data=' thay vì 'json=' để gửi dưới dạng Form Data (x-www-form-urlencoded).
    """
    response = client.post(
        "/v1/auth/login",  # Sử dụng đúng endpoint v1 từ gateway
        json={
            "username": "platform0",
            "password": "Password@123"
        }
    )
    assert response.status_code == 200, f"Đăng nhập System Admin thất bại: {response.text}"
    token_data = response.json()
    access_token = token_data["access_token"]
    
    # Trả về header chuẩn chứa Bearer Token cùng mã vết Correlation ID
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }


# ---------------------------------------------------------
# Fixture 3: Lấy Token cho TENANT ADMIN (Doanh nghiệp A)
# ---------------------------------------------------------
@pytest.fixture(scope="session")
def tenant_admin_header(client):
    """
    Sử dụng tài khoản quản trị Tenant A đã seed sẵn.
    """
    response = client.post(
        "/v1/auth/login",
        json={
            "username": "tenant0",
            "password": "Password@123"
        }
    )
    assert response.status_code == 200, f"Đăng nhập Tenant Admin thất bại: {response.text}"
    token_data = response.json()
    access_token = token_data["access_token"]
    
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }


# ---------------------------------------------------------
# Fixture 4: Lấy Token cho TENANT USER (Nhân viên thường Doanh nghiệp A)
# ---------------------------------------------------------
@pytest.fixture(scope="session")
def user_header(client):
    """
    Sử dụng tài khoản nhân viên thường của Tenant A đã seed sẵn.
    """
    response = client.post(
        "/v1/auth/login",
        json={
            "username": "user0",
            "password": "Password@123"
        }
    )
    assert response.status_code == 200, f"Đăng nhập Tenant User thất bại: {response.text}"
    token_data = response.json()
    access_token = token_data["access_token"]
    
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

# ── 5. Fixture File Mẫu (Sẵn có của bạn) ───────────────────────────────────
@pytest.fixture
def sample_txt_file():
    content = b"This is a RAG test document"
    return {
        "file": (
            "sample.txt",
            io.BytesIO(content),
            "text/plain"
        )
    }

@pytest.fixture(scope="session")
def mock_md_file():
    """
    Fixture tạo file Markdown giả lập trong bộ nhớ RAM (BytesIO).
    Nội dung có cấu trúc phân tầng (H1, H2) để kiểm thử luồng Chunking/Splitter của RAG.
    """
    md_content = (
        "# Hướng dẫn Quy trình RAG Doanh nghiệp\n\n"
        "Đây là phần giới thiệu tổng quan về tài liệu.\n\n"
        "## 1. Cơ chế Bảo mật Tenant\n\n"
        "Dữ liệu của Tenant nào sẽ được cô lập hoàn toàn trong Collection của Tenant đó.\n\n"
        "## 2. Quy định Xóa mềm dữ liệu\n\n"
        "Mọi tài liệu khi xóa sẽ được cập nhật trường is_deleted=True thay vì xóa vật lý."
    )
    # Chuyển chuỗi string thành chuỗi bytes và bọc trong BytesIO để giả lập luồng stream file
    file_stream = io.BytesIO(md_content.encode("utf-8"))
    file_stream.name = "rag_document_hierarchy.md"
    return file_stream

@pytest.fixture(scope="session")
def sample_tenant(client, platform_admin_header):
    """
    Tự động sinh ra 1 Tenant mẫu sống trong suốt thời gian hàm test chạy,
    sau đó tự dọn dẹp (xóa) khi test xong.
    """
    # 1. SETUP: Tạo Tenant mẫu
    unique_code = f"tenant_{uuid.uuid4().hex[:8]}"
    payload = {
        "name": f"Sample {unique_code}",
        "code": unique_code,
        "description": "Tenant created for individual unit tests"
    }
    
    response = client.post("/v1/tenants", json=payload, headers=platform_admin_header)
    assert response.status_code == 201
    tenant_data = response.json()

    # 2. TRẢ DATA CHO HÀM TEST DÙNG
    yield tenant_data

    # 3. TEARDOWN: Xóa dọn dẹp sau khi hàm test chạy xong
    tenant_id = tenant_data["id"]
    client.delete(f"/v1/tenants/{tenant_id}", headers=platform_admin_header)