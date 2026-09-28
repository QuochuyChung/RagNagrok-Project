"""
Tenant repository.

Data access layer for tenant records stored in PostgreSQL.
Maps tenant_id ↔ Qdrant collection name and validates tenant existence.

TODO (Sprint 3): Implement full CRUD operations with SQLAlchemy.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.logging import get_logger
from app.models import Tenants
from app.core.errors import *

logger = get_logger(__name__)


class TenantRepository:
    """PostgreSQL data access for tenants."""

    # TODO (Sprint 3): inject SQLAlchemy async session
    def __init__(self, session: AsyncSession) -> None:
           self.session = session

    async def create(self, tenant_id: uuid.UUID, name: str, collection_name: str, encrypted_dek: bytes):
        new_tenant = Tenants(
            tenant_id = tenant_id,
            tenant_name=name,
            collection_name=collection_name,
            encrypted_dek=encrypted_dek
        )
        self.session.add(new_tenant)
        await self.session.flush()
        await self.session.refresh(new_tenant)
        return new_tenant

    async def get_by_id(self, tenant_id: uuid.UUID) -> Tenants | None:
        result = await self.session.execute(
            select(Tenants).where(
                Tenants.tenant_id == tenant_id,
                Tenants.is_deleted.is_(False),
            )
        )
        tenant_result = result.scalar_one_or_none()

        return tenant_result

    async def check_tenant_exists(self, tenant_name: str) -> Tenants | None:
        result = await self.session.execute(
            select(Tenants).where(
                Tenants.tenant_name == tenant_name,
            )
        )

        tenant_result = result.scalar_one_or_none()
        return tenant_result

    async def get_all(self) -> list[Tenants]:
        result = await self.session.execute(
            select(Tenants).where(
                Tenants.is_deleted.is_(False),
            )
        )
        tenants = result.scalars().all()
        return tenants

    async def soft_delete(self, tenant_id: uuid.UUID):
        tenant = await self.get_by_id(tenant_id)
        if not tenant:
            raise TenantNotFoundError(tenant_id=tenant_id)

        tenant.is_deleted = True
        await self.session.commit()
        await self.session.refresh(tenant)
        return tenant

