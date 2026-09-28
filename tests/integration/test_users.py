import pytest
import test
import uuid

# --------------------------------------------
# POST /v1/users
# --------------------------------------------
@pytest.mark.parametrize("headers_fixture", ["tenant_admin_header", "platform_admin_header"])
def test_create_user_allowed_roles(client, request, headers_fixture):
    """Tenant Admin và Platform admin cấp User mới -> 201 Created"""
    headers = request.getfixturevalue(headers_fixture)
    payload = {"name": "unauthorized"}