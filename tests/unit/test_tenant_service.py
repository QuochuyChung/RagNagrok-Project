"""
Unit tests for app/services/tenant_service.py

Tests cover TenantService business logic in complete isolation:
 - All external dependencies (TenantRepository, QdrantRepository) are replaced
   by AsyncMock objects so no database or Qdrant instance is needed.
 - Each test class focuses on a single method for clear organisation.

Run with:
    pytest tests/unit/test_tenant_service.py -v
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors import (
    QdrantCollectionCreationError,
    TenantAlreadyExistsError,
    TenantNotFoundError,
)
from app.schemas.tenant import TenantCreate, TenantListResponse, TenantResponse
from app.services.tenant_service import TenantService


# =============================================================================
# Shared fixtures
# =============================================================================


@pytest.fixture()
def tenant_repo() -> AsyncMock:
    """A fully-mocked TenantRepository with all async methods."""
    mock = AsyncMock()
    
    @contextlib.asynccontextmanager
    async def dummy_context_manager():
        yield AsyncMock()
        
    mock.session.begin = MagicMock(return_value=dummy_context_manager())
    mock.session.bind.begin = MagicMock(return_value=dummy_context_manager())
    mock.session.in_transaction.return_value = False
    mock.check_tenant_exists.return_value = False
    return mock


@pytest.fixture()
def qdrant_repo() -> AsyncMock:
    """A fully-mocked QdrantRepository with all async methods."""
    mock = AsyncMock()
    return mock


@pytest.fixture()
def service(tenant_repo: AsyncMock, qdrant_repo: AsyncMock) -> TenantService:
    """TenantService wired with mock repos."""
    return TenantService(tenant_repo=tenant_repo, qdrant_repo=qdrant_repo)


def _make_tenant_orm(
    tenant_id: uuid.UUID | None = None,
    tenant_name: str = "Test Tenant",
    collection_name: str | None = None,
    is_deleted: bool = False,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> MagicMock:
    """Build a lightweight ORM-like tenant object (MagicMock)."""
    tid = tenant_id or uuid.uuid4()
    obj = MagicMock()
    obj.tenant_id = tid
    obj.tenant_name = tenant_name
    obj.collection_name = collection_name or f"COL_{tenant_name.upper()}"
    obj.is_deleted = is_deleted
    obj.created_at = created_at or datetime.now(timezone.utc)
    obj.updated_at = updated_at
    return obj


# =============================================================================
# TenantService.create_tenant
# =============================================================================


class TestCreateTenant:
    """Tests for TenantService.create_tenant."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_tenant_response(
        self, service: TenantService, tenant_repo: AsyncMock, qdrant_repo: AsyncMock
    ) -> None:
        """[Happy Path] Creating a brand-new tenant returns a populated TenantResponse."""
        # Arrange: no existing tenant, repo.create returns ORM object
        tenant_repo.get_by_id.return_value = None
        orm_tenant = _make_tenant_orm(tenant_name="Acme Corp")
        tenant_repo.create.return_value = orm_tenant
        qdrant_repo.create_collection.return_value = None

        data = TenantCreate(name="Acme Corp")

        # Act
        result = await service.create_tenant(data)

        # Assert
        assert isinstance(result, TenantResponse)
        assert result.name == "Acme Corp"
        assert result.is_active is True  # is_deleted = False → is_active = True
        assert result.qdrant_collection.startswith("COL_")
        qdrant_repo.create_collection.assert_awaited_once()
        tenant_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_qdrant_failure_raises_qdrant_error(
        self, service: TenantService, tenant_repo: AsyncMock, qdrant_repo: AsyncMock
    ) -> None:
        """[Error Condition] A Qdrant outage during collection creation raises QdrantCollectionCreationError."""
        tenant_repo.get_by_id.return_value = None
        qdrant_repo.create_collection.side_effect = RuntimeError("Qdrant is down")

        with pytest.raises(QdrantCollectionCreationError):
            await service.create_tenant(TenantCreate(name="FailTenant"))

        # DB create IS called before Qdrant fails (but rolls back due to the exception)
        tenant_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_collection_name_format(
        self, service: TenantService, tenant_repo: AsyncMock, qdrant_repo: AsyncMock
    ) -> None:
        """[Business Rule] The Qdrant collection name is COL_<uuid-with-underscores>."""
        tenant_repo.get_by_id.return_value = None
        orm_tenant = _make_tenant_orm(tenant_name="Alpha")
        tenant_repo.create.return_value = orm_tenant

        await service.create_tenant(TenantCreate(name="Alpha"))

        call_args = qdrant_repo.create_collection.call_args
        collection_arg = call_args[0][0]  # positional arg
        assert collection_arg.startswith("COL_")
        assert "-" not in collection_arg  # hyphens replaced by underscores

    @pytest.mark.asyncio
    async def test_response_is_active_when_not_deleted(
        self, service: TenantService, tenant_repo: AsyncMock, qdrant_repo: AsyncMock
    ) -> None:
        """[Business Rule] is_active in the response is the inverse of is_deleted."""
        tenant_repo.get_by_id.return_value = None
        orm_tenant = _make_tenant_orm(is_deleted=False)
        tenant_repo.create.return_value = orm_tenant

        result = await service.create_tenant(TenantCreate(name="SomeTenant"))

        assert result.is_active is True

    @pytest.mark.asyncio
    async def test_boundary_name_min_length(
        self, service: TenantService, tenant_repo: AsyncMock, qdrant_repo: AsyncMock
    ) -> None:
        """[Boundary] A single-character tenant name is valid per TenantCreate schema (min_length=1)."""
        tenant_repo.get_by_id.return_value = None
        orm_tenant = _make_tenant_orm(tenant_name="A")
        tenant_repo.create.return_value = orm_tenant

        result = await service.create_tenant(TenantCreate(name="A"))
        assert result.name == "A"

    @pytest.mark.asyncio
    async def test_boundary_name_max_length(
        self, service: TenantService, tenant_repo: AsyncMock, qdrant_repo: AsyncMock
    ) -> None:
        """[Boundary] A 255-character name is valid (max_length=255)."""
        long_name = "T" * 255
        tenant_repo.get_by_id.return_value = None
        orm_tenant = _make_tenant_orm(tenant_name=long_name)
        tenant_repo.create.return_value = orm_tenant

        result = await service.create_tenant(TenantCreate(name=long_name))
        assert len(result.name) == 255

    @pytest.mark.asyncio
    async def test_name_exceeds_max_length_raises_validation_error(self) -> None:
        """[Boundary] A name longer than 255 chars is rejected by Pydantic."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TenantCreate(name="X" * 256)

    @pytest.mark.asyncio
    async def test_empty_name_raises_validation_error(self) -> None:
        """[Edge Case] An empty string name is rejected by TenantCreate (min_length=1)."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TenantCreate(name="")


# =============================================================================
# TenantService.get_tenant
# =============================================================================


class TestGetTenant:
    """Tests for TenantService.get_tenant."""

    @pytest.mark.asyncio
    async def test_happy_path_returns_tenant_response(
        self, service: TenantService, tenant_repo: AsyncMock
    ) -> None:
        """[Happy Path] A valid tenant ID returns the correct TenantResponse."""
        tid = str(uuid.uuid4())
        orm_tenant = _make_tenant_orm(tenant_id=uuid.UUID(tid), tenant_name="Beta Corp")
        tenant_repo.get_by_id.return_value = orm_tenant

        result = await service.get_tenant(tid)

        assert isinstance(result, TenantResponse)
        assert result.name == "Beta Corp"
        tenant_repo.get_by_id.assert_awaited_once_with(tid)

    @pytest.mark.asyncio
    async def test_not_found_raises_tenant_not_found_error(
        self, service: TenantService, tenant_repo: AsyncMock
    ) -> None:
        """[Error Condition] A non-existent tenant_id raises TenantNotFoundError."""
        tenant_repo.get_by_id.return_value = None

        with pytest.raises(TenantNotFoundError):
            await service.get_tenant("non-existent-id")

    @pytest.mark.asyncio
    async def test_inactive_tenant_is_reported_correctly(
        self, service: TenantService, tenant_repo: AsyncMock
    ) -> None:
        """[Edge Case] A soft-deleted tenant (is_deleted=True) has is_active=False in the response."""
        tid = str(uuid.uuid4())
        orm_tenant = _make_tenant_orm(tenant_id=uuid.UUID(tid), is_deleted=True)
        tenant_repo.get_by_id.return_value = orm_tenant

        result = await service.get_tenant(tid)

        assert result.is_active is False

    @pytest.mark.asyncio
    async def test_updated_at_can_be_none(
        self, service: TenantService, tenant_repo: AsyncMock
    ) -> None:
        """[Edge Case] updated_at may be None for a freshly created tenant."""
        tid = str(uuid.uuid4())
        orm_tenant = _make_tenant_orm(tenant_id=uuid.UUID(tid), updated_at=None)
        tenant_repo.get_by_id.return_value = orm_tenant

        result = await service.get_tenant(tid)

        assert result.updated_at is None


# =============================================================================
# TenantService.list_tenant
# =============================================================================


class TestListTenant:
    """Tests for TenantService.list_tenant."""

    @pytest.mark.asyncio
    async def test_happy_path_multiple_tenants(
        self, service: TenantService, tenant_repo: AsyncMock
    ) -> None:
        """[Happy Path] Returns all tenants with correct total count."""
        tenants = [_make_tenant_orm(tenant_name=f"Tenant {i}") for i in range(3)]
        tenant_repo.get_all.return_value = tenants

        result = await service.list_tenant()

        assert isinstance(result, TenantListResponse)
        assert result.total == 3
        assert len(result.tenants) == 3

    @pytest.mark.asyncio
    async def test_empty_list_returns_zero_total(
        self, service: TenantService, tenant_repo: AsyncMock
    ) -> None:
        """[Edge Case] When no tenants exist, total == 0 and list is empty."""
        tenant_repo.get_all.return_value = []

        result = await service.list_tenant()

        assert result.total == 0
        assert result.tenants == []

    @pytest.mark.asyncio
    async def test_total_matches_list_length(
        self, service: TenantService, tenant_repo: AsyncMock
    ) -> None:
        """[Invariant] total must always equal len(tenants)."""
        tenants = [_make_tenant_orm() for _ in range(5)]
        tenant_repo.get_all.return_value = tenants

        result = await service.list_tenant()

        assert result.total == len(result.tenants)

    @pytest.mark.asyncio
    async def test_single_tenant_returned(
        self, service: TenantService, tenant_repo: AsyncMock
    ) -> None:
        """[Happy Path] Single-item list is handled correctly."""
        tenant_repo.get_all.return_value = [_make_tenant_orm(tenant_name="Solo")]

        result = await service.list_tenant()

        assert result.total == 1
        assert result.tenants[0].name == "Solo"


# =============================================================================
# TenantService.delete_tenant
# =============================================================================


class TestDeleteTenant:
    """Tests for TenantService.delete_tenant."""

    @pytest.mark.asyncio
    async def test_happy_path_calls_soft_delete_and_qdrant(
        self, service: TenantService, tenant_repo: AsyncMock, qdrant_repo: AsyncMock
    ) -> None:
        """[Happy Path] Deleting an existing tenant soft-deletes in DB and removes Qdrant collection."""
        tid = uuid.uuid4()
        tid_str = str(tid)
        orm_tenant = _make_tenant_orm(tenant_id=tid)
        # get_tenant internally calls tenant_repo.get_by_id
        tenant_repo.get_by_id.return_value = orm_tenant
        tenant_repo.soft_delete.return_value = orm_tenant
        qdrant_repo.delete_collection.return_value = None

        await service.delete_tenant(tid_str)

        tenant_repo.soft_delete.assert_awaited_once_with(tid_str)
        qdrant_repo.delete_collection.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found_raises_error(
        self, service: TenantService, tenant_repo: AsyncMock, qdrant_repo: AsyncMock
    ) -> None:
        """[Error Condition] Deleting a non-existent tenant raises TenantNotFoundError."""
        tenant_repo.get_by_id.return_value = None

        with pytest.raises(TenantNotFoundError):
            await service.delete_tenant("ghost-tenant-id")

        tenant_repo.soft_delete.assert_not_awaited()
        qdrant_repo.delete_collection.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_qdrant_collection_name_is_correct(
        self, service: TenantService, tenant_repo: AsyncMock, qdrant_repo: AsyncMock
    ) -> None:
        """[Business Rule] The collection name passed to Qdrant uses underscores, not hyphens."""
        tid = uuid.UUID("12345678-1234-5678-1234-567812345678")
        tid_str = str(tid)
        orm_tenant = _make_tenant_orm(tenant_id=tid)
        tenant_repo.get_by_id.return_value = orm_tenant
        tenant_repo.soft_delete.return_value = orm_tenant

        await service.delete_tenant(tid_str)

        call_args = qdrant_repo.delete_collection.call_args[0][0]
        assert call_args == "COL_TEST TENANT"
        assert "-" not in call_args
