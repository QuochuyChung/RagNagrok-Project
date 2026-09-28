import pytest
import test
import uuid

# --------------------------------------------
# POST /v1/tenants
# --------------------------------------------

def test_create_tenant_success_platform_admin(client, platform_admin_header):
    """Platform Admin tạo mới Tenant thành công."""
    unique_code = f"tenant_{uuid.uuid4().hex[:8]}"
    payload = {
        "name": f"Team {unique_code}"
    }
    response = client.post("/v1/tenants", json=payload, headers=platform_admin_header)

    assert response.status_code == 201
    data = response.json()
    
    assert data["is_active"]
    assert data["qdrant_collection"] == "COL_" + payload["name"].upper()
    assert "id" in data
    print(data["id"])

    assert data["name"] == payload["name"]

@pytest.mark.parametrize("headers_fixture", ["tenant_admin_header", "user_header"])
def test_create_tenant_forbidden_non_super_admin(client, request, headers_fixture):
    """Tenant Admin và Normal User không có quyền tạo Tenant -> 403 Forbidden."""
    headers = request.getfixturevalue(headers_fixture)
    payload = {"name": "unauthorized"}

    response = client.post("/v1/tenants", json=payload, headers=headers)
    assert response.status_code == 403

def test_create_tenant_validation_missing_name(client, platform_admin_header):
    """Test thiếu tên trong payload"""
    payload = {}

    response = client.post("/v1/tenants", json=payload, headers = platform_admin_header)
    assert response.status_code == 422

def test_create_tenant_duplicate_name(client, platform_admin_header):
    """Test trùng tên trong payload"""
    payload = {"name": "dev_team"}

    response = client.post("/v1/tenants", json=payload, headers = platform_admin_header)
    assert response.status_code in [400, 409]

# --------------------------------------------
# GET /v1/tenants
# --------------------------------------------

def test_get_tenants_list_success_platform_admin(client, platform_admin_header):
    """Platform Admin lấy danh sách toàn bộ các Tenant -> 200 OK."""
    response = client.get("/v1/tenants", headers=platform_admin_header)
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["tenants"], list)
    assert data["total"] >= 1

@pytest.mark.parametrize("headers_fixture", ["tenant_admin_header", "user_header"])
def test_get_tenant_list_forbidden_non_super_admin(client, request, headers_fixture):
    """Tenant Admin và Normal User không có quyền xem danh sách Tenant -> 403 Forbidden."""
    headers = request.getfixturevalue(headers_fixture)

    response = client.get("/v1/tenants", headers=headers)
    assert response.status_code == 403

# --------------------------------------------
# GET /v1/tenants/{tenant_id}
# --------------------------------------------

def test_get_tenant_by_id_success_platform_admin(client, platform_admin_header, sample_tenant):
    """Super Admin xem thông tin bất kỳ Tenant nào qua tenant_id -> 200 OK."""
    tenant_id = sample_tenant["id"]
    response = client.get(f"/v1/tenants/{tenant_id}", headers=platform_admin_header)
    
    assert response.status_code == 200
    assert response.json()["id"] == tenant_id

def test_get_tenant_by_id_success_own_tenant_admin(client, tenant_admin_header):
    """Tenant Admin xem thông tin CHÍNH TENANT CỦA MÌNH (name = dev_team) -> 200 OK."""
    tenant_id = "7378aa3d-f907-4866-9cfa-99acaf10b43c"
    response = client.get(f"/v1/tenants/{tenant_id}", headers=tenant_admin_header)
    
    assert response.status_code == 200
    assert response.json()["id"] == tenant_id

def test_get_tenant_by_id_403_cross_tenant_admin(client, tenant_admin_header, sample_tenant):
    """Tenant Admin xem thông tin của tenant khác (name != dev_team) -> 403 Forbidden."""
    tenant_id = sample_tenant["id"]
    response = client.get(f"/v1/tenants/{tenant_id}", headers=tenant_admin_header)
    
    assert response.status_code == 403

def test_get_tenant_by_id_404_not_found(client, platform_admin_header):
    """Platform Admin tra cứu tenant_id không tồn tại -> 404 Not Found."""
    invalid_id = "e56911c5-5432-4dee-b616-555ff38b4f18"
    response = client.get(f"/v1/tenants/{invalid_id}", headers=platform_admin_header)
    
    assert response.status_code == 404

# ==============================================================================
# 4. \DELETE /v1/tenants/{tenant_id} (Sửa/Xóa Tenant - Super Admin Only)
# ==============================================================================

def test_delete_tenant_by_id_successful_platform_admin(client, platform_admin_header, sample_tenant):
    """Platform admin xoá tenant_id (xoá mềm) -> 204 Query Successful."""
    id_to_delete = sample_tenant["id"]
    response = client.delete(f"/v1/tenants/{id_to_delete}", headers=platform_admin_header)

    assert response.status_code == 204

@pytest.mark.parametrize("headers_fixture", ["tenant_admin_header", "user_header"])
def test_delete_tenant_forbidden_non_super_admin(client, request, headers_fixture):
    """Tenant Admin & User thường không được xóa Tenant -> 403 Forbidden."""
    headers = request.getfixturevalue(headers_fixture)
    tenant_id = "b99396b7-560c-4af3-9b54-01c48151a0e7"
    
    response = client.delete(f"/v1/tenants/{tenant_id}", headers=headers)
    assert response.status_code == 403

# ------- FLOW OF CREATE & DELETE TENANT (PLATFORM_ADMIN) ----------------

def test_create_delete_tenant_flow_platform_admin(client, platform_admin_header):
    """Platform admin thực hiện các bước tạo rồi xoá (mềm) tenant, kiểm tra bằng đọc tenant trước và sau khi xoá"""

    # Tạo tenant (201)
    unique_code = f"tenant_{uuid.uuid4().hex[:8]}"
    payload = {
        "name": f"Team {unique_code}"
    }
    response_post = client.post(f"/v1/tenants", json=payload, headers=platform_admin_header)
    assert response_post.status_code == 201

    data = response_post.json()
    assert data["is_active"]
    assert data["qdrant_collection"] == "COL_" + payload["name"].upper()
    assert "id" in data
    assert data["name"] == payload["name"]
    print(data["id"])
    tenant_id = data["id"]

    # Đọc Tenant (200)
    response_get_appear = client.get(f"/v1/tenants/{tenant_id}", headers=platform_admin_header)
    assert response_get_appear.status_code == 200

    # Xoá Tenant (204)
    response_delete = client.delete(f"/v1/tenants/{tenant_id}", headers=platform_admin_header)
    assert response_delete.status_code == 204

    # Đọc Tenant (404)
    response_get_not_appear = client.get(f"/v1/tenants/{tenant_id}", headers=platform_admin_header)
    assert response_get_not_appear.status_code == 404

