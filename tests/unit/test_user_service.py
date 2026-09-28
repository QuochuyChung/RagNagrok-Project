"""
Unit tests for app/services/user_service.py

Tests cover UserService business logic in complete isolation.
All external dependencies (UserRepository) are replaced by AsyncMock objects.

RBAC matrix under test:
  PLATFORM_ADMIN → can create TENANT_ADMIN or USER in any tenant
  TENANT_ADMIN   → can create TENANT_ADMIN or USER in their own tenant
  USER           → cannot call create_user (router-level guard, not tested here)

Run with:
    pytest tests/unit/test_user_service.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core.errors import UserNotFoundError
from app.schemas.user import UserCreate, UserListResponse, UserResponse
from app.services.user_service import UserService


# =============================================================================
# Shared fixtures & helpers
# =============================================================================

PLATFORM_ADMIN_ROLE = "PLATFORM_ADMIN"
TENANT_ADMIN_ROLE = "TENANT_ADMIN"
USER_ROLE = "USER"

FIXED_TENANT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OTHER_TENANT_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture()
def user_repo() -> AsyncMock:
    """A fully-mocked UserRepository with all async methods."""
    return AsyncMock()


@pytest.fixture()
def service(user_repo: AsyncMock) -> UserService:
    """UserService wired with mock repo."""
    return UserService(user_repo=user_repo)


def _make_role_orm(role_name: str, role_id: uuid.UUID | None = None) -> MagicMock:
    """Build a lightweight Roles ORM-like mock."""
    obj = MagicMock()
    obj.role_id = role_id or uuid.uuid4()
    obj.role_name = role_name
    return obj


def _make_user_orm(
    user_id: uuid.UUID | None = None,
    user_name: str = "john_doe",
    tenant_id: uuid.UUID | None = None,
    role_id: uuid.UUID | None = None,
    is_active: bool = True,
    email: str | None = "john@example.com",
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> MagicMock:
    """Build a lightweight Users ORM-like mock."""
    obj = MagicMock()
    obj.user_id = user_id or uuid.uuid4()
    obj.user_name = user_name
    obj.tenant_id = tenant_id or FIXED_TENANT_ID
    obj.role_id = role_id or uuid.uuid4()
    obj.is_active = is_active
    obj.email = email
    obj.password_hash = "hashed"
    obj.created_at = created_at or datetime.now(timezone.utc)
    obj.updated_at = updated_at
    return obj


def _make_user_create(
    user_name: str = "john_doe",
    password: str = "Secur3Pass",
    tenant_id: uuid.UUID | None = None,
    role_name: str = "USER",
    email: str | None = "john@example.com",
) -> UserCreate:
    return UserCreate(
        user_name=user_name,
        password=password,
        tenant_id=tenant_id or FIXED_TENANT_ID,
        role_name=role_name,
        email=email,
    )


# =============================================================================
# UserService.create_user — RBAC & Happy Paths
# =============================================================================


class TestCreateUser:
    """Tests for UserService.create_user."""

    # ── Happy paths ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_platform_admin_creates_tenant_admin(
        self, service: UserService, user_repo: AsyncMock
    ) -> None:
        """[Happy Path] PLATFORM_ADMIN can create a TENANT_ADMIN in any tenant."""
        role_obj = _make_role_orm("TENANT_ADMIN")
        user_repo.get_role_by_name.return_value = role_obj
        orm_user = _make_user_orm(user_name="ta_user", role_id=role_obj.role_id)
        user_repo.create.return_value = orm_user

        with patch.object(UserService, "_to_response", return_value=MagicMock(spec=UserResponse)):
            result = await service.create_user(
                _make_user_create(user_name="ta_user", role_name="TENANT_ADMIN"),
                caller_role=PLATFORM_ADMIN_ROLE,
                caller_tenant_id=str(OTHER_TENANT_ID),
            )

        user_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_platform_admin_creates_user_in_any_tenant(
        self, service: UserService, user_repo: AsyncMock
    ) -> None:
        """[Happy Path] PLATFORM_ADMIN can create a USER in any tenant."""
        role_obj = _make_role_orm("USER")
        user_repo.get_role_by_name.return_value = role_obj
        orm_user = _make_user_orm(user_name="reg_user", role_id=role_obj.role_id)
        user_repo.create.return_value = orm_user

        with patch.object(UserService, "_to_response", return_value=MagicMock(spec=UserResponse)):
            await service.create_user(
                _make_user_create(role_name="USER"),
                caller_role=PLATFORM_ADMIN_ROLE,
                caller_tenant_id=str(OTHER_TENANT_ID),  # different tenant — still OK
            )

        user_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_tenant_admin_creates_user_in_own_tenant(
        self, service: UserService, user_repo: AsyncMock
    ) -> None:
        """[Happy Path] TENANT_ADMIN can create a USER in their own tenant."""
        role_obj = _make_role_orm("USER")
        user_repo.get_role_by_name.return_value = role_obj
        orm_user = _make_user_orm(role_id=role_obj.role_id)
        user_repo.create.return_value = orm_user

        with patch.object(UserService, "_to_response", return_value=MagicMock(spec=UserResponse)):
            await service.create_user(
                _make_user_create(tenant_id=FIXED_TENANT_ID, role_name="USER"),
                caller_role=TENANT_ADMIN_ROLE,
                caller_tenant_id=str(FIXED_TENANT_ID),
            )

        user_repo.create.assert_awaited_once()

    # ── RBAC violations ──────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_tenant_admin_cannot_create_user_in_other_tenant(
        self, service: UserService, user_repo: AsyncMock
    ) -> None:
        """[RBAC Error] TENANT_ADMIN creating a user in a different tenant raises 403."""
        role_obj = _make_role_orm("USER")
        user_repo.get_role_by_name.return_value = role_obj

        with pytest.raises(HTTPException) as exc_info:
            await service.create_user(
                _make_user_create(tenant_id=FIXED_TENANT_ID, role_name="USER"),
                caller_role=TENANT_ADMIN_ROLE,
                caller_tenant_id=str(OTHER_TENANT_ID),  # caller is in OTHER tenant
            )

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_tenant_admin_can_create_tenant_admin_in_own_tenant(
        self, service: UserService, user_repo: AsyncMock
    ) -> None:
        """[Happy Path] TENANT_ADMIN can create a TENANT_ADMIN in their own tenant."""
        role_obj = _make_role_orm("TENANT_ADMIN")
        user_repo.get_role_by_name.return_value = role_obj
        orm_user = _make_user_orm(role_id=role_obj.role_id)
        user_repo.create.return_value = orm_user

        with patch.object(UserService, "_to_response", return_value=MagicMock(spec=UserResponse)):
            await service.create_user(
                _make_user_create(tenant_id=FIXED_TENANT_ID, role_name="TENANT_ADMIN"),
                caller_role=TENANT_ADMIN_ROLE,
                caller_tenant_id=str(FIXED_TENANT_ID),
            )

        user_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_platform_admin_cannot_create_platform_admin(
        self, service: UserService, user_repo: AsyncMock
    ) -> None:
        """[RBAC Error] PLATFORM_ADMIN cannot create another PLATFORM_ADMIN (escalation prevention)."""
        role_obj = _make_role_orm("PLATFORM_ADMIN")
        user_repo.get_role_by_name.return_value = role_obj

        with pytest.raises(HTTPException) as exc_info:
            await service.create_user(
                _make_user_create(role_name="PLATFORM_ADMIN"),
                caller_role=PLATFORM_ADMIN_ROLE,
                caller_tenant_id=str(FIXED_TENANT_ID),
            )

        assert exc_info.value.status_code == 403

    # ── Invalid role name ─────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_invalid_role_name_raises_400(
        self, service: UserService, user_repo: AsyncMock
    ) -> None:
        """[Error Condition] An unrecognised role_name raises HTTP 400."""
        user_repo.get_role_by_name.return_value = None  # role not found

        with pytest.raises(HTTPException) as exc_info:
            await service.create_user(
                _make_user_create(role_name="SUPER_GOD"),
                caller_role=PLATFORM_ADMIN_ROLE,
                caller_tenant_id=str(FIXED_TENANT_ID),
            )

        assert exc_info.value.status_code == 400

    # ── Schema boundary / validation ─────────────────────────────────────────

    def test_user_name_with_spaces_is_rejected(self) -> None:
        """[Boundary] user_name containing spaces fails Pydantic validation."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserCreate(
                user_name="john doe",
                password="Secur3Pass",
                tenant_id=FIXED_TENANT_ID,
                role_name="USER",
            )

    def test_user_name_min_length_boundary(self) -> None:
        """[Boundary] user_name of exactly 3 characters is valid (min_length=3)."""
        data = UserCreate(
            user_name="abc",
            password="Secur3Pass",
            tenant_id=FIXED_TENANT_ID,
            role_name="USER",
        )
        assert data.user_name == "abc"

    def test_user_name_below_min_length_rejected(self) -> None:
        """[Boundary] user_name shorter than 3 characters is rejected."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserCreate(
                user_name="ab",
                password="Secur3Pass",
                tenant_id=FIXED_TENANT_ID,
                role_name="USER",
            )

    def test_password_min_length_boundary(self) -> None:
        """[Boundary] password of exactly 8 characters is valid (min_length=8)."""
        data = UserCreate(
            user_name="validuser",
            password="12345678",
            tenant_id=FIXED_TENANT_ID,
            role_name="USER",
        )
        assert len(data.password) == 8

    def test_password_below_min_length_rejected(self) -> None:
        """[Boundary] password shorter than 8 characters is rejected."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserCreate(
                user_name="validuser",
                password="short",
                tenant_id=FIXED_TENANT_ID,
                role_name="USER",
            )

    def test_password_max_length_boundary(self) -> None:
        """[Boundary] password of exactly 128 characters is valid."""
        data = UserCreate(
            user_name="validuser",
            password="A" * 128,
            tenant_id=FIXED_TENANT_ID,
            role_name="USER",
        )
        assert len(data.password) == 128

    def test_password_exceeds_max_length_rejected(self) -> None:
        """[Boundary] password longer than 128 characters is rejected."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            UserCreate(
                user_name="validuser",
                password="A" * 129,
                tenant_id=FIXED_TENANT_ID,
                role_name="USER",
            )

    def test_optional_email_defaults_to_none(self) -> None:
        """[Edge Case] email is optional and defaults to None."""
        data = UserCreate(
            user_name="nomail",
            password="Secur3Pass",
            tenant_id=FIXED_TENANT_ID,
            role_name="USER",
        )
        assert data.email is None


# =============================================================================
# UserService.get_user
# =============================================================================


class TestGetUser:
    """Tests for UserService.get_user."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_user_response(
        self, service: UserService, user_repo: AsyncMock
    ) -> None:
        """[Happy Path] A valid UUID returns a UserResponse."""
        uid = uuid.uuid4()
        orm_user = _make_user_orm(user_id=uid)
        user_repo.get_by_id.return_value = orm_user

        with patch.object(UserService, "_to_response", return_value=MagicMock(spec=UserResponse)) as mock_resp:
            result = await service.get_user(uid)
            mock_resp.assert_called_once_with(orm_user)

    @pytest.mark.asyncio
    async def test_not_found_raises_user_not_found_error(
        self, service: UserService, user_repo: AsyncMock
    ) -> None:
        """[Error Condition] A non-existent user_id raises UserNotFoundError."""
        user_repo.get_by_id.return_value = None

        with pytest.raises(UserNotFoundError):
            await service.get_user(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_repo_called_with_correct_uuid(
        self, service: UserService, user_repo: AsyncMock
    ) -> None:
        """[Correctness] get_user passes the exact UUID to the repository."""
        uid = uuid.uuid4()
        orm_user = _make_user_orm(user_id=uid)
        user_repo.get_by_id.return_value = orm_user

        with patch.object(UserService, "_to_response", return_value=MagicMock(spec=UserResponse)):
            await service.get_user(uid)

        user_repo.get_by_id.assert_awaited_once_with(uid)


# =============================================================================
# UserService.list_users
# =============================================================================


class TestListUsers:
    """Tests for UserService.list_users (PLATFORM_ADMIN path)."""

    @pytest.mark.asyncio
    async def test_happy_path_multiple_users(
        self, service: UserService, user_repo: AsyncMock
    ) -> None:
        """[Happy Path] Returns all users with the correct total."""
        users = [_make_user_orm(user_name=f"user{i}") for i in range(4)]
        user_repo.get_all.return_value = users

        with patch.object(UserService, "_to_response", side_effect=lambda u: MagicMock(spec=UserResponse)):
            result = await service.list_users()

        assert result.total == 4

    @pytest.mark.asyncio
    async def test_empty_list(
        self, service: UserService, user_repo: AsyncMock
    ) -> None:
        """[Edge Case] When no users exist, total == 0."""
        user_repo.get_all.return_value = []

        result = await service.list_users()

        assert result.total == 0
        assert result.users == []

    @pytest.mark.asyncio
    async def test_total_matches_user_count(
        self, service: UserService, user_repo: AsyncMock
    ) -> None:
        """[Invariant] total must always equal len(users)."""
        users = [_make_user_orm() for _ in range(7)]
        user_repo.get_all.return_value = users

        with patch.object(UserService, "_to_response", side_effect=lambda u: MagicMock(spec=UserResponse)):
            result = await service.list_users()

        assert result.total == len(result.users)


# =============================================================================
# UserService.list_users_by_tenant
# =============================================================================


class TestListUsersByTenant:
    """Tests for UserService.list_users_by_tenant (TENANT_ADMIN path)."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_only_tenant_users(
        self, service: UserService, user_repo: AsyncMock
    ) -> None:
        """[Happy Path] Returns only users belonging to the specified tenant."""
        users = [_make_user_orm(tenant_id=FIXED_TENANT_ID) for _ in range(2)]
        user_repo.get_all_by_tenant.return_value = users

        with patch.object(UserService, "_to_response", side_effect=lambda u: MagicMock(spec=UserResponse)):
            result = await service.list_users_by_tenant(FIXED_TENANT_ID)

        assert result.total == 2
        user_repo.get_all_by_tenant.assert_awaited_once_with(FIXED_TENANT_ID)

    @pytest.mark.asyncio
    async def test_empty_tenant_returns_zero(
        self, service: UserService, user_repo: AsyncMock
    ) -> None:
        """[Edge Case] A tenant with no users returns an empty list."""
        user_repo.get_all_by_tenant.return_value = []

        result = await service.list_users_by_tenant(FIXED_TENANT_ID)

        assert result.total == 0
        assert result.users == []


# =============================================================================
# UserService.delete_user
# =============================================================================


class TestDeleteUser:
    """Tests for UserService.delete_user (hard delete per spec)."""

    @pytest.mark.asyncio
    async def test_happy_path_calls_hard_delete(
        self, service: UserService, user_repo: AsyncMock
    ) -> None:
        """[Happy Path] Deleting an existing user calls user_repo.hard_delete."""
        uid = uuid.uuid4()
        # Simulate get_by_id returning a user in the correct tenant
        orm_user = _make_user_orm(user_id=uid, tenant_id=FIXED_TENANT_ID)
        user_repo.get_by_id.return_value = orm_user
        user_repo.hard_delete.return_value = None

        await service.delete_user(
            uid,
            caller_role=PLATFORM_ADMIN_ROLE,
            caller_tenant_id=str(FIXED_TENANT_ID),
        )

        user_repo.hard_delete.assert_awaited_once_with(uid)

    @pytest.mark.asyncio
    async def test_not_found_propagates_user_not_found_error(
        self, service: UserService, user_repo: AsyncMock
    ) -> None:
        """[Error Condition] If user not found, UserNotFoundError propagates."""
        uid = uuid.uuid4()
        user_repo.get_by_id.return_value = None

        with pytest.raises(UserNotFoundError):
            await service.delete_user(
                uid,
                caller_role=PLATFORM_ADMIN_ROLE,
                caller_tenant_id=str(FIXED_TENANT_ID),
            )

    @pytest.mark.asyncio
    async def test_tenant_admin_cannot_delete_user_in_other_tenant(
        self, service: UserService, user_repo: AsyncMock
    ) -> None:
        """[RBAC] TENANT_ADMIN cannot delete a user belonging to another tenant."""
        uid = uuid.uuid4()
        # user is in FIXED_TENANT_ID, but caller is OTHER_TENANT_ID
        orm_user = _make_user_orm(user_id=uid, tenant_id=FIXED_TENANT_ID)
        user_repo.get_by_id.return_value = orm_user

        with pytest.raises(HTTPException) as exc_info:
            await service.delete_user(
                uid,
                caller_role=TENANT_ADMIN_ROLE,
                caller_tenant_id=str(OTHER_TENANT_ID),
            )

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_does_not_return_body(
        self, service: UserService, user_repo: AsyncMock
    ) -> None:
        """[HTTP Contract] delete_user returns None (maps to 204 No Content)."""
        uid = uuid.uuid4()
        orm_user = _make_user_orm(user_id=uid, tenant_id=FIXED_TENANT_ID)
        user_repo.get_by_id.return_value = orm_user
        user_repo.hard_delete.return_value = None

        result = await service.delete_user(
            uid,
            caller_role=PLATFORM_ADMIN_ROLE,
            caller_tenant_id=str(FIXED_TENANT_ID),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_correct_user_id_passed_to_repo(
        self, service: UserService, user_repo: AsyncMock
    ) -> None:
        """[Correctness] The exact UUID is forwarded to the repository hard_delete call."""
        uid = uuid.UUID("12345678-1234-5678-1234-567812345678")
        orm_user = _make_user_orm(user_id=uid, tenant_id=FIXED_TENANT_ID)
        user_repo.get_by_id.return_value = orm_user
        user_repo.hard_delete.return_value = None

        await service.delete_user(
            uid,
            caller_role=PLATFORM_ADMIN_ROLE,
            caller_tenant_id=str(FIXED_TENANT_ID),
        )

        user_repo.hard_delete.assert_awaited_once_with(uid)
