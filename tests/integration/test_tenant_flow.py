import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy import text

@pytest.mark.asyncio
async def test_tenant_lifecycle(http_client: AsyncClient, platform_admin_token: str, db_session, qdrant_client):
    """
    End-to-End Tenant Lifecycle:
    Create -> List -> Get -> Delete -> Get (NotFound)
    """
    headers = {"Authorization": f"Bearer {platform_admin_token}"}
    tenant_name = f"integration_lifecycle_tenant_{str(uuid.uuid4())[:8]}"

    # 1. Create Tenant
    create_resp = await http_client.post(
        "/v1/tenants",
        json={"name": tenant_name},
        headers=headers,
    )
    assert create_resp.status_code == 201
    tenant_data = create_resp.json()
    tenant_id = tenant_data["id"]
    collection_name = tenant_data["qdrant_collection"]

    # Verify Qdrant Collection was actually created
    assert await qdrant_client.collection_exists(collection_name) is True

    # 2. Get Tenant
    get_resp = await http_client.get(f"/v1/tenants/{tenant_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == tenant_name
    assert get_resp.json()["is_active"] is True

    # 3. List Tenants (Ensure it is in the list)
    list_resp = await http_client.get("/v1/tenants", headers=headers)
    assert list_resp.status_code == 200
    all_tenants = list_resp.json()["tenants"]
    assert any(t["id"] == tenant_id for t in all_tenants)

    # 4. Delete Tenant
    delete_resp = await http_client.delete(f"/v1/tenants/{tenant_id}", headers=headers)
    assert delete_resp.status_code == 204, delete_resp.text

    # DB soft delete sets is_deleted=True, so tenant should be 404
    get_deleted = await http_client.get(f"/v1/tenants/{tenant_id}", headers=headers)
    assert get_deleted.status_code == 404

    # The Qdrant Collection should be deleted
    assert await qdrant_client.collection_exists(collection_name) is False

    # Hard delete for cleanup
    await db_session.execute(text("DELETE FROM tenants WHERE tenant_id = :tid"), {"tid": tenant_id})
    await db_session.commit()

@pytest.mark.asyncio
async def test_tenant_validation_errors(http_client: AsyncClient, platform_admin_token: str):
    headers = {"Authorization": f"Bearer {platform_admin_token}"}
    
    # Empty name
    empty_name_resp = await http_client.post(
        "/v1/tenants",
        json={"name": ""},
        headers=headers,
    )
    assert empty_name_resp.status_code == 422, empty_name_resp.text
    
    # Missing field
    missing_field_resp = await http_client.post(
        "/v1/tenants",
        json={},
        headers=headers,
    )
    assert missing_field_resp.status_code == 422

@pytest.mark.asyncio
async def test_tenant_unauthorized_access(http_client: AsyncClient):
    # Missing token
    create_resp = await http_client.post(
        "/v1/tenants",
        json={"name": "unauthorized"}
    )
    assert create_resp.status_code == 401

    # Invalid token
    get_resp = await http_client.get(
        "/v1/tenants",
        headers={"Authorization": "Bearer invalid_token"}
    )
    assert get_resp.status_code == 401
