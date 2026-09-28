import test
import jwt
import pytest
from app.core.config import get_settings

settings = get_settings()


def test_login_successful_with_email(client, user_fixture):
    response = client.post("/v1/auth/login", json={
        "email": user_fixture["email"],
        "password": user_fixture["password"]
    })
    assert response.status_code == 200
    assert "access_token" in response.json()

def test_login_successful_with_username(client, user_fixture):
    response = client.post("/v1/auth/login", json={
        "username": user_fixture["username"],
        "password": user_fixture["password"]
    })
    assert response.status_code == 200
    assert "access_token" in response.json()

@pytest.mark.parametrize(
    "user_fixture_name",
    [
        "platform_admin_fixture",
        "tenant_admin_fixture",
        "user_fixture",
    ]
)
def test_login_successful_claimed_by_role(client, request, user_fixture_name):
    user = request.getfixturevalue(user_fixture_name)
    payload = {
        "username": user["username"], # Hoặc user_data["email"] tùy spec
        "password": user["password"]
    }

    response = client.post("/v1/auth/login", json=payload)

    assert response.status_code == 200
    res_json = response.json()
    assert "access_token" in res_json
    assert res_json["token_type"].lower() == "bearer"

    decoded_token = jwt.decode(
        res_json["access_token"],
        settings.jwt_secret_key,
        algorithms=["HS256"]
    )

    assert decoded_token.get("role") == user["role"]

@pytest.mark.parametrize(
    "payload, expected_status",
    [
        ({"username": "user0"}, 422),
        ({"username": "user0", "password": ""}, 401),
        ({"username": "user0", "password":"saimatkhau"}, 401),
        ({"email": "not-an-email", "password": "123456"}, 401),
        ({"email": "user0@devteam.local"}, 422),
        ({}, 422),
    ]
)
def test_login_invalid_credentials(client, payload, expected_status):
    response = client.post("/v1/auth/login", json=payload)
    assert response.status_code == expected_status

""" def test_login_nonexistent_user(client, test_user_credential):
    response = client.post("/v1/auth/login", json={
        "username": test_user_credential["username"],
        "email": test_user_credential["email"],
        "password": "123457"
    })
    assert response.status_code == 401 """