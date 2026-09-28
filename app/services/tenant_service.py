"""
Tenant service.

Handles business logic for creating, listing, and deleting tenants.
Coordinates with TenantRepository (PostgreSQL) and Qdrant to create
the corresponding vector collection for each tenant.

TODO (Sprint 3): Implement full CRUD methods.
"""
from __future__ import annotations

import datetime
import uuid
from datetime import datetime
from typing import TYPE_CHECKING
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import Tenants
from app.repositories.tenant_repository import TenantRepository
from app.repositories.qdrant_repository import QdrantRepository
from app.schemas.tenant import TenantCreate, TenantResponse, TenantListResponse
from app.core.errors import *
from app.repositories.schema_repository import provision_tenant_schema
from app.core.encryption import generate_tenant_dek
from app.profiling import LatencyTracker

if TYPE_CHECKING:
    from app.repositories.user_repository import UserRepository


logger = get_logger(__name__)


class TenantService:
    """Business logic layer for tenant management."""

    # TODO (Sprint 3): inject TenantRepository and QdrantRepository
    def __init__(
        self, 
        tenant_repo: TenantRepository,
        qdrant_repo: QdrantRepository,
        user_repo: "UserRepository | None" = None,
    ):
        self.tenant_repo = tenant_repo
        self.qdrant_repo = qdrant_repo
        self.user_repo = user_repo


    async def create_tenant(self, data: TenantCreate):

        """
         tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
        tenant_name: Mapped[str] = mapped_column(String(255), nullable=False)
        collection_name: Mapped[str] = mapped_column(String(255), nullable=False)
        is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('NOW()'))
        updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow)

        """

        qdrant_created: bool = False
        collection_name: str = None
        new_tenant_id: uuid.UUID | None = None
        tenant_response = None
        tracker = LatencyTracker("tenant_provisioning", tenant_name=data.name)

        try:
            if data.tenant_admin is not None and self.user_repo is not None:
                existing_email = await self.user_repo.get_by_email(data.tenant_admin.email)
                if existing_email:
                    # Let the global exception handler pick this up or raise it cleanly
                    raise EmailAlreadyExistsError(email=data.tenant_admin.email)
                    
            in_tx = self.tenant_repo.session.in_transaction()
            if not in_tx:
                await self.tenant_repo.session.begin()

            existing = await self.tenant_repo.check_tenant_exists(data.name)
            if existing:
                raise TenantAlreadyExistsErrorWithName(tenant_name=data.name)

            # Collection name convention: COL_{TENANT_NAME_UPPER}
            collection_name = f"COL_{data.name.upper()}"

            # Generate and encrypt DEK for the new tenant
            async with tracker.astage("generate_tenant_dek_kms"):
                raw_dek, wrapped_dek = await generate_tenant_dek(data.name)

            async with tracker.astage("db_insert_tenant"):
                new_tenant = await self.tenant_repo.create(
                    tenant_id = uuid.uuid4(),
                    name = data.name,
                    collection_name=collection_name,
                    encrypted_dek=wrapped_dek,
                )
            raw_dek = None

            # Create collection in Qdrant
            try:
                async with tracker.astage("qdrant_create_collection"):
                    await self.qdrant_repo.create_collection(new_tenant.collection_name)
                qdrant_created = True
            except Exception as e:
                raise QdrantCollectionCreationError(tenant_id=str(new_tenant.tenant_id), detail=str(e))

            new_tenant_id = new_tenant.tenant_id
            tenant_response = TenantResponse(
                    id=new_tenant.tenant_id,
                    name=new_tenant.tenant_name,
                    is_active=not new_tenant.is_deleted,
                    qdrant_collection=new_tenant.collection_name,
                    created_at=new_tenant.created_at,
                    updated_at=new_tenant.updated_at,
                )
            
            await self.tenant_repo.session.commit()
            
        except Exception as e:
            await self.tenant_repo.session.rollback()
            if qdrant_created:
                try:
                    await self.qdrant_repo.delete_collection(collection_name)
                except Exception as e:
                    logger.error(f"delete collection {collection_name} failed with error {e}")
            raise
        
        # Provision isolated PostgreSQL schema
        tenant_name = data.name
        try:
            async with tracker.astage("provision_pg_schema"):
                raw_conn = await self.tenant_repo.session.connection()
                schema_name = await provision_tenant_schema(raw_conn, tenant_name)
                await self.tenant_repo.session.commit()
            logger.info("tenant_schema_created", tenant_name=tenant_name, schema=schema_name)
        except Exception as exc:
            logger.error("tenant_schema_provision_failed", tenant_name=tenant_name, error=str(exc))
            # Rollback compensating transactions
            if qdrant_created:
                try:
                    await self.qdrant_repo.delete_collection(collection_name)
                except Exception as cleanup_err:
                    logger.error(f"Failed to rollback Qdrant collection {collection_name}: {cleanup_err}")
            
            if new_tenant_id:
                try:
                    if not self.tenant_repo.session.in_transaction():
                        await self.tenant_repo.session.begin()
                    await self.tenant_repo.session.execute(
                        sa.delete(Tenants).where(Tenants.tenant_id == new_tenant_id)
                    )
                    await self.tenant_repo.session.commit()
                except Exception as cleanup_err:
                    logger.error(f"Failed to rollback Postgres tenant {new_tenant_id}: {cleanup_err}")
                    if self.tenant_repo.session.in_transaction():
                        await self.tenant_repo.session.rollback()
            raise
        finally:
            tracker.finish(tenant_id=str(new_tenant_id) if new_tenant_id else None)

        return tenant_response

    async def get_tenant(self, tenant_id: str | uuid.UUID) -> TenantResponse:
        if isinstance(tenant_id, uuid.UUID):
            tenant_uuid = tenant_id
        else:
            try:
                tenant_uuid = uuid.UUID(str(tenant_id).strip())
            except ValueError:
                raise TenantNotFoundError(tenant_id=str(tenant_id))

        tenant = await self.tenant_repo.get_by_id(tenant_uuid)
        if not tenant:
            raise TenantNotFoundError(tenant_id=str(tenant_id))

        return TenantResponse(
            id=tenant.tenant_id,
            name=tenant.tenant_name,
            qdrant_collection=tenant.collection_name,
            is_active=not tenant.is_deleted,
            created_at=tenant.created_at,
            updated_at=tenant.updated_at,
        )

    async def list_tenant(self) -> TenantListResponse:
        tenant_responses = []
        tenants = await self.tenant_repo.get_all()

        for tenant in tenants:
            tenant_response = TenantResponse(
                id=tenant.tenant_id,
                name=tenant.tenant_name,
                qdrant_collection=tenant.collection_name,
                is_active=not tenant.is_deleted,
                created_at=tenant.created_at,
                updated_at=tenant.updated_at
            )
            tenant_responses.append(tenant_response)

        return TenantListResponse(
            tenants=tenant_responses,
            total=len(tenant_responses)
        )

    async def delete_tenant(self, tenant_id: str | uuid.UUID):
        if isinstance(tenant_id, uuid.UUID):
            tenant_uuid = tenant_id
        else:
            try:
                tenant_uuid = uuid.UUID(str(tenant_id).strip())
            except ValueError:
                raise TenantNotFoundError(tenant_id=str(tenant_id))

        # Ensure tenant exists first
        tenant_response = await self.get_tenant(tenant_uuid)

        # Soft-delete in PostgreSQL
        success = await self.tenant_repo.soft_delete(tenant_uuid)

        # Deactivate all users belonging to this tenant so they can't log in
        if self.user_repo is not None:
            deactivated = await self.user_repo.deactivate_all_by_tenant(tenant_uuid)
            logger.info(
                "tenant_users_deactivated",
                tenant_id=str(tenant_uuid),
                deactivated_count=deactivated,
            )

        # Delete the Qdrant collection using the name stored in the tenant record
        try:
            await self.qdrant_repo.delete_collection(tenant_response.qdrant_collection)
        except Exception as e:
            logger.error(
                "qdrant_delete_collection_failed",
                tenant_id=str(tenant_uuid),
                collection=tenant_response.qdrant_collection,
                error=str(e),
            )

        return success

    # TODO: Fix logic with created_at
    async def get_tenant_by_id(self, tenant_id: uuid.UUID) -> TenantResponse | None:
        tenant = await self.tenant_repo.get_by_id(tenant_id)

        if tenant is not None:
            tenant_response = TenantResponse(
                id=tenant.tenant_id,
                name=tenant.tenant_name,
                created_at=tenant.created_at,
                is_active=not tenant.is_deleted,
                qdrant_collection=tenant.collection_name,
                updated_at=tenant.updated_at,
            )
            return tenant_response

        return None
    
