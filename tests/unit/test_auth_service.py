"""
Unit tests for app/services/auth_service.py

Tests cover AuthService.login in complete isolation:
 - UserRepository is replaced by AsyncMock.
 - Password verification (verify_password) is patched to avoid bcrypt overhead
   and to control pass/fail scenarios precisely.
 - JWT creation (create_access_token) is patched to return a predictable token.

Run with:
    pytest tests/unit/test_auth_service.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.auth_service import AuthService


# =============================================================================
# Shared fixtures & helpers
# =============================================================================

FAKE_TOKEN = "fake.jwt.token"


def _make_user_orm(
    user_name: str = "alice",
    password_hash: str = "hashed_password",
    is_active: bool = True,
    user_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    role_name: str = "USER",
) -> MagicMock:
    """Build a lightweight Users ORM-like mock that includes a role relationship."""
    role = MagicMock()
    role.role_name = role_name

    obj = MagicMock()
    obj.user_id = user_id or uuid.uuid4()
    obj.user_name = user_name
    obj.password_hash = password_hash
    obj.tenant_id = tenant_id or uuid.uuid4()
    obj.is_active = is_active
    obj.role = role
    obj.created_at = datetime.now(timezone.utc)
    obj.updated_at = None
    return obj


@pytest.fixture()
def user_repo() -> AsyncMock:
    """A fully-mocked UserRepository."""
    return AsyncMock()


@pytest.fixture()
def auth_service(user_repo: AsyncMock) -> AuthService:
    """AuthService wired with mock repo."""
    return AuthService(user_repository=user_repo)


# =============================================================================
# AuthService.login — Happy Path
# =============================================================================


class TestLoginHappyPath:
    """Happy-path scenarios for AuthService.login."""

    @pytest.mark.asyncio
    async def test_valid_credentials_return_jwt_token(
        self, auth_service: AuthService, user_repo: AsyncMock
    ) -> None:
        """[Happy Path] Correct username + password returns a non-empty JWT string."""
        orm_user = _make_user_orm(user_name="alice")
        user_repo.get_by_username.return_value = orm_user

        with (
            patch("app.services.auth_service.verify_password", return_value=True),
            patch("app.services.auth_service.create_access_token", return_value=FAKE_TOKEN),
        ):
            token = await auth_service.login("alice", "correct_password")

        assert token == FAKE_TOKEN

    @pytest.mark.asyncio
    async def test_correct_username_is_passed_to_repo(
        self, auth_service: AuthService, user_repo: AsyncMock
    ) -> None:
        """[Correctness] The exact username string is forwarded to UserRepository.get_by_username."""
        orm_user = _make_user_orm(user_name="bob")
        user_repo.get_by_username.return_value = orm_user

        with (
            patch("app.services.auth_service.verify_password", return_value=True),
            patch("app.services.auth_service.create_access_token", return_value=FAKE_TOKEN),
        ):
            await auth_service.login("bob", "password123")

        user_repo.get_by_username.assert_awaited_once_with(username="bob")

    @pytest.mark.asyncio
    async def test_password_hash_is_verified_not_compared_plaintext(
        self, auth_service: AuthService, user_repo: AsyncMock
    ) -> None:
        """[Security] verify_password is called with the stored hash, never the plain text."""
        orm_user = _make_user_orm(password_hash="bcrypt_hash_xyz")
        user_repo.get_by_username.return_value = orm_user

        with (
            patch("app.services.auth_service.verify_password", return_value=True) as mock_verify,
            patch("app.services.auth_service.create_access_token", return_value=FAKE_TOKEN),
        ):
            await auth_service.login("alice", "mypassword")

        # Second arg must be the stored hash, not the plain-text password
        mock_verify.assert_called_once_with("mypassword", "bcrypt_hash_xyz")

    @pytest.mark.asyncio
    async def test_access_token_created_with_user_object(
        self, auth_service: AuthService, user_repo: AsyncMock
    ) -> None:
        """[Correctness] create_access_token receives the full user ORM object."""
        orm_user = _make_user_orm()
        user_repo.get_by_username.return_value = orm_user

        with (
            patch("app.services.auth_service.verify_password", return_value=True),
            patch("app.services.auth_service.create_access_token", return_value=FAKE_TOKEN) as mock_create,
        ):
            await auth_service.login("alice", "password")

        mock_create.assert_called_once_with(user=orm_user)

    @pytest.mark.asyncio
    async def test_returned_token_is_a_string(
        self, auth_service: AuthService, user_repo: AsyncMock
    ) -> None:
        """[Type Contract] login() always returns a string (the raw JWT)."""
        orm_user = _make_user_orm()
        user_repo.get_by_username.return_value = orm_user

        with (
            patch("app.services.auth_service.verify_password", return_value=True),
            patch("app.services.auth_service.create_access_token", return_value="a.b.c"),
        ):
            result = await auth_service.login("alice", "password")

        assert isinstance(result, str)


# =============================================================================
# AuthService.login — Invalid Credentials
# =============================================================================


class TestLoginInvalidCredentials:
    """Error conditions triggered by wrong username or password."""

    @pytest.mark.asyncio
    async def test_unknown_username_raises_value_error(
        self, auth_service: AuthService, user_repo: AsyncMock
    ) -> None:
        """[Error Condition] A username that does not exist raises ValueError."""
        user_repo.get_by_username.return_value = None  # user not found

        with pytest.raises(ValueError, match="Invalid"):
            await auth_service.login("ghost_user", "anything")

    @pytest.mark.asyncio
    async def test_wrong_password_raises_value_error(
        self, auth_service: AuthService, user_repo: AsyncMock
    ) -> None:
        """[Error Condition] A valid username with the wrong password raises ValueError."""
        orm_user = _make_user_orm(user_name="alice")
        user_repo.get_by_username.return_value = orm_user

        with patch("app.services.auth_service.verify_password", return_value=False):
            with pytest.raises(ValueError, match="Invalid"):
                await auth_service.login("alice", "wrong_password")

    @pytest.mark.asyncio
    async def test_empty_username_returns_none_from_repo(
        self, auth_service: AuthService, user_repo: AsyncMock
    ) -> None:
        """[Edge Case] An empty username string causes user_repo to return None → ValueError."""
        user_repo.get_by_username.return_value = None

        with pytest.raises(ValueError):
            await auth_service.login("", "some_password")

    @pytest.mark.asyncio
    async def test_empty_password_fails_verification(
        self, auth_service: AuthService, user_repo: AsyncMock
    ) -> None:
        """[Edge Case] An empty password string fails bcrypt verification → ValueError."""
        orm_user = _make_user_orm()
        user_repo.get_by_username.return_value = orm_user

        with patch("app.services.auth_service.verify_password", return_value=False):
            with pytest.raises(ValueError):
                await auth_service.login("alice", "")

    @pytest.mark.asyncio
    async def test_correct_credentials_no_token_creation_on_failure(
        self, auth_service: AuthService, user_repo: AsyncMock
    ) -> None:
        """[Security] create_access_token must NOT be called when authentication fails."""
        user_repo.get_by_username.return_value = None

        with patch("app.services.auth_service.create_access_token") as mock_create:
            with pytest.raises(ValueError):
                await auth_service.login("no_one", "bad_pass")

        mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_sql_error_propagates_as_exception(
        self, auth_service: AuthService, user_repo: AsyncMock
    ) -> None:
        """[Error Condition] Unexpected DB errors are not swallowed — they propagate."""
        user_repo.get_by_username.side_effect = RuntimeError("DB connection lost")

        with pytest.raises(RuntimeError, match="DB connection lost"):
            await auth_service.login("alice", "password")


# =============================================================================
# AuthService.login — Edge / Boundary Cases
# =============================================================================


class TestLoginEdgeCases:
    """Boundary value and unusual input scenarios."""

    @pytest.mark.asyncio
    async def test_username_with_special_characters(
        self, auth_service: AuthService, user_repo: AsyncMock
    ) -> None:
        """[Edge Case] Usernames with special characters are passed through unchanged."""
        orm_user = _make_user_orm(user_name="alice@domain.com")
        user_repo.get_by_username.return_value = orm_user

        with (
            patch("app.services.auth_service.verify_password", return_value=True),
            patch("app.services.auth_service.create_access_token", return_value=FAKE_TOKEN),
        ):
            token = await auth_service.login("alice@domain.com", "password")

        assert token == FAKE_TOKEN
        user_repo.get_by_username.assert_awaited_once_with(username="alice@domain.com")

    @pytest.mark.asyncio
    async def test_very_long_password_is_handled(
        self, auth_service: AuthService, user_repo: AsyncMock
    ) -> None:
        """[Boundary] A very long password (512 chars) is passed to verify_password without truncation."""
        long_pass = "P" * 512
        orm_user = _make_user_orm()
        user_repo.get_by_username.return_value = orm_user

        with (
            patch("app.services.auth_service.verify_password", return_value=True) as mock_verify,
            patch("app.services.auth_service.create_access_token", return_value=FAKE_TOKEN),
        ):
            await auth_service.login("alice", long_pass)

        # Ensure full password length is passed — not truncated
        actual_password = mock_verify.call_args[0][0]
        assert actual_password == long_pass

    @pytest.mark.asyncio
    async def test_whitespace_only_username(
        self, auth_service: AuthService, user_repo: AsyncMock
    ) -> None:
        """[Edge Case] A whitespace-only username is treated as a lookup miss."""
        user_repo.get_by_username.return_value = None

        with pytest.raises(ValueError):
            await auth_service.login("   ", "password123")

    @pytest.mark.asyncio
    async def test_case_sensitive_username_lookup(
        self, auth_service: AuthService, user_repo: AsyncMock
    ) -> None:
        """[Edge Case] Username lookup is case-sensitive — 'Alice' ≠ 'alice'."""
        # repo returns None for 'Alice' (only 'alice' exists)
        user_repo.get_by_username.return_value = None

        with pytest.raises(ValueError):
            await auth_service.login("Alice", "password")

        user_repo.get_by_username.assert_awaited_once_with(username="Alice")
