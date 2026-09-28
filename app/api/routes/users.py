"""
User management endpoints.

POST   /v1/users                    — Create a new user.
GET    /v1/users                    — List users (PLATFORM_ADMIN: all or filter by ?tenant_id,
                                      TENANT_ADMIN: own tenant only, ignores query param).
GET    /v1/users/{user_id}          — Get a specific user (with tenant isolation for TENANT_ADMIN).
DELETE /v1/users/{user_id}          — Soft-delete a user (with tenant isolation for TENANT_ADMIN).
PATCH  /v1/users/{user_id}/restore  — Restore a soft-deleted user.

RBAC summary:
  PLATFORM_ADMIN → full access across all tenants
  TENANT_ADMIN   → scoped to their own tenant; can create USER or TENANT_ADMIN in their own tenant
  USER           → read-only access to their own record (GET /v1/users/{user_id})
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import get_user_service
from app.core.security import bearer_scheme, requires_roles
from app.schemas.user import UserCreate, UserListResponse, UserResponse
from app.services.user_service import UserService

router = APIRouter(prefix="/v1/users", tags=["Users"], dependencies=[Depends(bearer_scheme)])


# =============================================================================
# POST /users — Create user
# =============================================================================


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user",
    description=(
        "Create a new user account within a tenant. "
        "**PLATFORM_ADMIN**: can create USER or TENANT_ADMIN in any tenant — "
        "must supply ``tenant_id`` in the request body. "
        "**TENANT_ADMIN**: can create USER or TENANT_ADMIN in their own tenant — "
        "``tenant_id`` in the body is ignored (or must match their own)."
    ),
)
@requires_roles("PLATFORM_ADMIN", "TENANT_ADMIN")
async def create_user(
    request: Request,
    data: UserCreate,
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Create a new user, enforcing RBAC rules from the JWT token."""
    caller_role: str = getattr(request.state, "role", "")
    caller_tenant_id: str | None = getattr(request.state, "tenant_id", None)
    return await user_service.create_user(data, caller_role=caller_role, caller_tenant_id=caller_tenant_id)


# =============================================================================
# GET /users — List users
# =============================================================================


@router.get(
    "",
    response_model=UserListResponse,
    summary="List users",
    description=(
        "**PLATFORM_ADMIN**: returns all active users platform-wide. "
        "Optionally filter by ``?tenant_id=<uuid>`` to get users of a specific tenant. "
        "**TENANT_ADMIN**: always returns users in their own tenant, "
        "the ``tenant_id`` query parameter is **ignored**."
    ),
)
@requires_roles("PLATFORM_ADMIN", "TENANT_ADMIN")
async def list_users(
    request: Request,
    tenant_id: uuid.UUID | None = Query(
        default=None,
        description="(PLATFORM_ADMIN only) Filter users by tenant UUID.",
    ),
    user_service: UserService = Depends(get_user_service),
) -> UserListResponse:
    """List users. Behavior is role-dependent."""
    caller_role: str = getattr(request.state, "role", "")
    caller_tenant_id: str | None = getattr(request.state, "tenant_id", None)

    if caller_role == "TENANT_ADMIN":
        if not caller_tenant_id:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "TENANT_REQUIRED",
                    "message": "TENANT_ADMIN user must be associated with a valid tenant.",
                },
            )
        return await user_service.list_users_by_tenant(uuid.UUID(caller_tenant_id))

    # PLATFORM_ADMIN
    if tenant_id is not None:
        return await user_service.list_users_by_tenant(tenant_id)
    return await user_service.list_users()


# =============================================================================
# GET /users/{user_id} — Get single user
# =============================================================================


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get a user by ID",
    description=(
        "Return the details of a single active user. "
        "**TENANT_ADMIN** can only retrieve users within their own tenant."
    ),
)
@requires_roles("PLATFORM_ADMIN", "TENANT_ADMIN", "USER")
async def get_user(
    request: Request,
    user_id: uuid.UUID,
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Retrieve a single active user by UUID. Enforces tenant isolation for TENANT_ADMIN."""
    caller_role: str = getattr(request.state, "role", "")
    caller_tenant_id: str | None = getattr(request.state, "tenant_id", None)

    if caller_role == "TENANT_ADMIN":
        if not caller_tenant_id:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "TENANT_REQUIRED",
                    "message": "TENANT_ADMIN user must be associated with a valid tenant.",
                },
            )
        return await user_service.get_user_in_tenant(user_id, uuid.UUID(caller_tenant_id))

    # PLATFORM_ADMIN or USER (own record — no extra isolation at service level)
    return await user_service.get_user(user_id)


# =============================================================================
# DELETE /users/{user_id} — Soft-delete user
# =============================================================================


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a user",
    description=(
        "Deactivate a user account (soft delete). "
        "**TENANT_ADMIN** can only deactivate users within their own tenant. "
        "**PLATFORM_ADMIN** can deactivate any user."
    ),
)
@requires_roles("PLATFORM_ADMIN", "TENANT_ADMIN")
async def delete_user(
    request: Request,
    user_id: uuid.UUID,
    user_service: UserService = Depends(get_user_service),
) -> None:
    """Soft-delete a user. Returns 204 No Content on success."""
    caller_role: str = getattr(request.state, "role", "")
    caller_tenant_id: str | None = getattr(request.state, "tenant_id", None)
    caller_user_id: str | None = getattr(request.state, "user_id", None)

    await user_service.delete_user(
        user_id,
        caller_role=caller_role,
        caller_tenant_id=caller_tenant_id,
        caller_user_id=caller_user_id,
    )
    return None


# =============================================================================
# PATCH /users/{user_id}/restore — Restore user
# =============================================================================


@router.patch(
    "/{user_id}/restore",
    status_code=status.HTTP_200_OK,
    summary="Restore a user",
    description=(
        "Restore a deactivated user account. "
        "**TENANT_ADMIN** can only restore users within their own tenant. "
        "**PLATFORM_ADMIN** can restore any user."
    ),
)
@requires_roles("PLATFORM_ADMIN", "TENANT_ADMIN")
async def restore_user(
    request: Request,
    user_id: uuid.UUID,
    user_service: UserService = Depends(get_user_service),
) -> dict:
    """Restore a soft-deleted user."""
    caller_role: str = getattr(request.state, "role", "")
    caller_tenant_id: str | None = getattr(request.state, "tenant_id", None)

    await user_service.restore_user(
        user_id,
        caller_role=caller_role,
        caller_tenant_id=caller_tenant_id,
    )
    return {"message": "User restored successfully."}