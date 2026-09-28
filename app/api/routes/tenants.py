"""
Tenant management endpoints.

POST   /v1/tenants           — Create a new tenant (+ optional TENANT_ADMIN invite).
GET    /v1/tenants           — List all tenants.
GET    /v1/tenants/{id}      — Get a specific tenant.
DELETE /v1/tenants/{id}      — Delete a tenant (soft delete).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import get_token_service, get_tenant_service
from app.core.security import bearer_scheme, requires_roles, public
from app.schemas.invitation import TenantWithAdminResponse
from app.schemas.tenant import TenantCreate, TenantResponse, TenantListResponse
from app.services.token_service import TokenService
from app.services.tenant_service import TenantService

router = APIRouter(prefix="/v1/tenants", tags=["Tenants"], dependencies=[Depends(bearer_scheme)])


# =============================================================================
# POST /tenants
# =============================================================================


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new tenant",
    description=(
        "Create a new tenant and its Qdrant collection. "
        "If ``tenant_admin`` is provided, a TENANT_ADMIN account is pre-created "
        "(inactive) and an invitation email is dispatched asynchronously. "
        "Returns a ``TenantWithAdminResponse`` when admin details are included, "
        "or a plain ``TenantResponse`` otherwise."
    ),
)
@requires_roles("PLATFORM_ADMIN")
async def create_tenant(
    request: Request,
    data: TenantCreate,
    tenant_service: TenantService = Depends(get_tenant_service),
    token_service: TokenService = Depends(get_token_service),
):
    """Create a new tenant and (optionally) its first TENANT_ADMIN account."""
    tenant_response = await tenant_service.create_tenant(data)

    if data.tenant_admin is not None:
        caller_user_id_str: str | None = getattr(request.state, "user_id", None)
        caller_user_id = uuid.UUID(caller_user_id_str) if caller_user_id_str else None
        inviter_name: str = getattr(request.state, "username", "PLATFORM_ADMIN")

        admin_created = await token_service.create_tenant_admin_invite(
            tenant_id=tenant_response.id,
            tenant_name=tenant_response.name,
            admin_input=data.tenant_admin,
            invited_by_id=caller_user_id,
            inviter_name=inviter_name,
        )
        return TenantWithAdminResponse(
            tenant=tenant_response.model_dump(),
            tenant_admin=admin_created,
        )

    return tenant_response


# =============================================================================
# GET /tenants
# =============================================================================


@router.get(
    "", 
    response_model=TenantListResponse
)
@requires_roles("PLATFORM_ADMIN")
async def list_tenant(
    tenant_service: TenantService = Depends(get_tenant_service)
):
    """Get details of all tenants."""
    return await tenant_service.list_tenant()


# =============================================================================
# GET /tenants/{tenant_id}
# =============================================================================


@router.get(
    "/{tenant_id}", 
    response_model=TenantResponse
)
@requires_roles("PLATFORM_ADMIN", "TENANT_ADMIN")
async def get_tenant(
    request: Request,
    tenant_id: str,
    tenant_service: TenantService = Depends(get_tenant_service)
):
    """Get details of a specific tenant. Enforces tenant isolation for TENANT_ADMIN."""
    caller_role: str = getattr(request.state, "role", "")
    caller_tenant_id: str | None = getattr(request.state, "tenant_id", None)

    if caller_role == "TENANT_ADMIN":
        if not caller_tenant_id or str(caller_tenant_id).strip() != str(tenant_id).strip():
            from app.core.errors import PermissionDeniedError
            raise PermissionDeniedError("TENANT_ADMIN can only view details of their own tenant.")

    return await tenant_service.get_tenant(tenant_id)


# =============================================================================
# DELETE /tenants/{tenant_id}
# =============================================================================


@router.delete(
    "/{tenant_id}", 
    status_code=status.HTTP_204_NO_CONTENT
)
@requires_roles("PLATFORM_ADMIN")
async def delete_tenant(
    tenant_id: str,
    tenant_service: TenantService = Depends(get_tenant_service)
):
    """Safe-delete a tenant (sets is_deleted=True) and deactivates all its users."""
    await tenant_service.delete_tenant(tenant_id)
    return None