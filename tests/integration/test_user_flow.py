import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy import text

@pytest.mark.asyncio
async def test_user_lifecycle_and_rbac(http_client: AsyncClient, test_tenant_data: dict, platform_admin_token: str, db_session):
    """
    User Lifecycle and RBAC:
    - PLATFORM_ADMIN creates a TENANT_ADMIN.
    - TENANT_ADMIN logs in.
    - TENANT_ADMIN creates a USER in the same tenant.
    - TENANT_ADMIN tries to create a USER in another tenant (Fails).
    - USER logs in and tries to create a user (Fails).
    """
    tenant_id = test_tenant_data["id"]
    pa_headers = {"Authorization": f"Bearer {platform_admin_token}"}
    
    # 1. PLATFORM_ADMIN creates a TENANT_ADMIN in test_tenant
    tenant_admin_name = f"ta_{str(uuid.uuid4())[:8]}"
    create_ta_resp = await http_client.post(
        "/v1/users",
        json={
            "user_name": tenant_admin_name,
            "password": "Password@123",
            "role_name": "TENANT_ADMIN",
            "tenant_id": tenant_id
        },
        headers=pa_headers
    )
    assert create_ta_resp.status_code == 201
    ta_data = create_ta_resp.json()
    assert "user_id" in ta_data

    # 2. TENANT_ADMIN logs in
    login_resp = await http_client.post(
        "/v1/auth/login",
        json={"username": tenant_admin_name, "password": "Password@123"}
    )
    assert login_resp.status_code == 200
    ta_token = login_resp.json()["access_token"]
    ta_headers = {"Authorization": f"Bearer {ta_token}"}

    # 3. TENANT_ADMIN creates a USER in their own tenant
    user_name = f"user_{str(uuid.uuid4())[:8]}"
    create_user_resp = await http_client.post(
        "/v1/users",
        json={
            "user_name": user_name,
            "password": "Password@123",
            "role_name": "USER",
            "tenant_id": tenant_id
        },
        headers=ta_headers
    )
    assert create_user_resp.status_code == 201
    user_data = create_user_resp.json()
    user_id = user_data["user_id"]

    # 3b. TENANT_ADMIN creates another TENANT_ADMIN in their own tenant
    second_ta_name = f"ta2_{str(uuid.uuid4())[:8]}"
    create_second_ta_resp = await http_client.post(
        "/v1/users",
        json={
            "user_name": second_ta_name,
            "password": "Password@123",
            "role_name": "TENANT_ADMIN",
            "tenant_id": tenant_id
        },
        headers=ta_headers
    )
    assert create_second_ta_resp.status_code == 201
    second_ta_data = create_second_ta_resp.json()
    assert second_ta_data["role_name"] == "TENANT_ADMIN"

    # 4. TENANT_ADMIN attempts to create user in another tenant (e.g. some random UUID)
    other_tenant_id = str(uuid.uuid4())
    create_other_user_resp = await http_client.post(
        "/v1/users",
        json={
            "user_name": "hacker_user",
            "password": "Password@123",
            "role_name": "USER",
            "tenant_id": other_tenant_id
        },
        headers=ta_headers
    )
    assert create_other_user_resp.status_code == 403

    # 5. List users as TENANT_ADMIN (should see themselves and the user they created)
    list_resp = await http_client.get(f"/v1/users?tenant_id={tenant_id}", headers=ta_headers)
    assert list_resp.status_code == 200
    users_list = list_resp.json()["users"]
    assert any(u["user_id"] == user_id for u in users_list)
    assert any(u["user_id"] == ta_data["user_id"] for u in users_list)

    # 6. USER logs in
    user_login_resp = await http_client.post(
        "/v1/auth/login",
        json={"username": user_name, "password": "Password@123"}
    )
    assert user_login_resp.status_code == 200
    user_token = user_login_resp.json()["access_token"]
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # 7. USER tries to list users (Fails - lack of permission)
    user_list_resp = await http_client.get(f"/v1/users?tenant_id={tenant_id}", headers=user_headers)
    assert user_list_resp.status_code == 403

    # 8. Delete USER (Deactivate)
    delete_resp = await http_client.delete(f"/v1/users/{user_id}", headers=ta_headers)
    assert delete_resp.status_code == 204

    # 9. Verify soft deletion (try to login again)
    user_login_resp2 = await http_client.post(
        "/v1/auth/login",
        json={"username": user_name, "password": "Password@123"}
    )
    # The login might throw 401 Unauthorized for inactive users or 404
    assert user_login_resp2.status_code in [401, 404]

@pytest.mark.asyncio
async def test_auth_edge_cases(http_client: AsyncClient):
    # Invalid username
    resp = await http_client.post(
        "/v1/auth/login",
        json={"username": "does_not_exist", "password": "Password@123"}
    )
    assert resp.status_code == 401

    # Invalid password
    resp = await http_client.post(
        "/v1/auth/login",
        json={"username": "platform_admin", "password": "WrongPassword"}
    )
    assert resp.status_code == 401

    # Missing fields
    resp = await http_client.post(
        "/v1/auth/login",
        json={"username": "platform_admin"}
    )
    assert resp.status_code == 422
