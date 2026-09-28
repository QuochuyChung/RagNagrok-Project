import pytest

def test_health_check_and_infrastructure(client):
    """
    Smoke Test 1: Kiểm tra hạ tầng cơ bản và mã vết (Correlation ID).
    """
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    
    body = response.json()
    assert isinstance(body, dict)


def test_rag_ingestion_smoke(client, tenant_admin_headers, mock_md_file):
    """
    Smoke Test 3: Upload thử 1 tài liệu nhỏ thành công (Happy Path).
    Xác nhận FastAPI kết nối được sang Qdrant Vector DB.
    """
    mock_md_file.seek(0)
    
    response = client.post(
        "/v1/documents",
        headers=tenant_admin_headers,
        files={"file": (mock_md_file.name, mock_md_file, "text/markdown")}
    )
    
    assert response.status_code in [200, 201], f"Upload Markdown thất bại: {response.text}"
    data = response.json()
    assert "doc_id" in data
    assert "X-Request-ID" in response.headers


def test_rag_chat_smoke(client, tenant_admin_headers):
    """
    Smoke Test 4: Thử gọi AI chat một câu đơn giản (Happy Path).
    Xác nhận API Gateway gọi được dịch vụ LLM (Ollama).
    """
    response = client.post(
        "/v1/chats",
        headers=tenant_admin_headers,
        json={"message": "Xin chào, đây là smoke test."}
    )
    assert response.status_code == 200
    data = response.json()
    assert "response" in data or "text" in data