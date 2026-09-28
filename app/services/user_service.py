"""
User service.

Handles business logic for creating, listing, retrieving, and deleting users.
Enforces RBAC rules:
  - PLATFORM_ADMIN: can create TENANT_ADMIN or USER in any tenant
  - TENANT_ADMIN:   can create TENANT_ADMIN or USER in their own tenant
  - Neither can create PLATFORM_ADMIN (privilege escalation prevention)
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException

from app.core.errors import UserNotFoundError, PermissionDeniedError
from app.core.logging import get_logger
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserListResponse, UserResponse

logger = get_logger(__name__)

# Roles that can be assigned by each caller role
_ALLOWED_TARGET_ROLES: dict[str, set[str]] = {
    "PLATFORM_ADMIN": {"TENANT_ADMIN", "USER"},
    "TENANT_ADMIN": {"TENANT_ADMIN", "USER"},
}


class UserService:
    """Business logic layer for user management."""

    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _to_response(user: object) -> UserResponse:
        """Convert a ``Users`` ORM instance to ``UserResponse``."""
        resp = UserResponse.model_validate(user)
        if hasattr(user, "role") and user.role and hasattr(user.role, "role_name"):
            resp.role_name = user.role.role_name
        return resp

    # ── Public API ────────────────────────────────────────────────────────

    async def create_user(
        self,
        data: UserCreate,
        caller_role: str,
        caller_tenant_id: str | None,
    ) -> UserResponse:
        """
        Create a new user, enforcing RBAC rules.

        RBAC matrix:
        - PLATFORM_ADMIN: can create TENANT_ADMIN or USER in any tenant.
          ``data.tenant_id`` is required.
        - TENANT_ADMIN: can create TENANT_ADMIN or USER in their own tenant.
          ``data.tenant_id`` is forced to ``caller_tenant_id`` regardless
          of what the caller sends.


        Raises:
            HTTPException 400: Role name not found in the database.
            HTTPException 403: Caller tries to assign a role above their level,
                               or TENANT_ADMIN tries to create in another tenant.
        """
        # ── Resolve role name → Role ORM ─────────────────────────────────
        role_obj = await self.user_repo.get_role_by_name(data.role_name)
        if role_obj is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "INVALID_ROLE",
                    "message": f"Role '{data.role_name}' does not exist.",
                },
            )

        # ── RBAC guard: check target role is allowed ──────────────────────
        allowed_roles = _ALLOWED_TARGET_ROLES.get(caller_role, set())
        if data.role_name not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "PERMISSION_DENIED",
                    "message": (
                        f"Role '{caller_role}' cannot assign role '{data.role_name}'."
                    ),
                },
            )

        # ── Resolve target tenant ─────────────────────────────────────────
        if caller_role == "TENANT_ADMIN":
            if not caller_tenant_id:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error_code": "TENANT_REQUIRED",
                        "message": "TENANT_ADMIN must be associated with a valid tenant.",
                    },
                )
            # TENANT_ADMIN can only create users in their own tenant, ignore body value
            effective_tenant_id = uuid.UUID(caller_tenant_id)
            if data.tenant_id is not None and data.tenant_id != effective_tenant_id:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error_code": "PERMISSION_DENIED",
                        "message": "TENANT_ADMIN can only create users within their own tenant.",
                    },
                )
        else:
            # PLATFORM_ADMIN must provide tenant_id in the body
            if data.tenant_id is None:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error_code": "TENANT_REQUIRED",
                        "message": "PLATFORM_ADMIN must specify 'tenant_id' in the request body.",
                    },
                )
            effective_tenant_id = data.tenant_id

        logger.info(
            "user_create_requested",
            user_name=data.user_name,
            tenant_id=str(effective_tenant_id),
            role=data.role_name,
            caller_role=caller_role,
        )

        new_user = await self.user_repo.create(
            user_name=data.user_name,
            plain_password=data.password,
            tenant_id=effective_tenant_id,
            role_id=role_obj.role_id,
            email=data.email,
            full_name=data.full_name,
        )

        logger.info(
            "user_created",
            user_id=str(new_user.user_id),
            user_name=new_user.user_name,
            tenant_id=str(new_user.tenant_id),
        )
        return self._to_response(new_user)

    async def get_user(self, user_id: uuid.UUID) -> UserResponse:
        """
        Retrieve a single active user by UUID.

        Raises:
            UserNotFoundError: if the user does not exist or is inactive.
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id=user_id)
        return self._to_response(user)

    async def get_user_in_tenant(
        self, user_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> UserResponse:
        """
        Retrieve a user, ensuring they belong to the specified tenant.

        Used by TENANT_ADMIN to enforce isolation — they can only view
        users within their own tenant.

        Raises:
            UserNotFoundError: if the user doesn't exist or isn't in the tenant.
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user or user.tenant_id != tenant_id:
            raise UserNotFoundError(user_id=user_id)
        return self._to_response(user)

    async def list_users(self) -> UserListResponse:
        """Return all active users across all tenants (PLATFORM_ADMIN only)."""
        users = await self.user_repo.get_all()
        responses = [self._to_response(u) for u in users]
        return UserListResponse(users=responses, total=len(responses))

    async def list_users_by_tenant(self, tenant_id: uuid.UUID) -> UserListResponse:
        """Return all active users belonging to the given tenant."""
        users = await self.user_repo.get_all_by_tenant(tenant_id)
        responses = [self._to_response(u) for u in users]
        return UserListResponse(users=responses, total=len(responses))

    async def delete_user(
        self,
        user_id: uuid.UUID,
        caller_role: str,
        caller_tenant_id: str | None,
        caller_user_id: str | None = None,
    ) -> None:
        """
        Soft-delete a user (permanent removal is no longer done here).

        RBAC:
        - PLATFORM_ADMIN: can delete any user.
        - TENANT_ADMIN: can only delete users within their own tenant.
        - Cannot delete self or PLATFORM_ADMIN.

        Raises:
            UserNotFoundError: if the user does not exist.
            HTTPException 400: if caller attempts to delete self.
            HTTPException 403: if TENANT_ADMIN attempts to delete a user outside their tenant or PLATFORM_ADMIN.
        """
        if caller_user_id and str(user_id) == str(caller_user_id):
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "CANNOT_DELETE_SELF",
                    "message": "You cannot delete your own account.",
                },
            )

        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id=user_id)

        if user.role.role_name == "PLATFORM_ADMIN":
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "PERMISSION_DENIED",
                    "message": "Cannot delete PLATFORM_ADMIN.",
                },
            )

        if caller_role == "TENANT_ADMIN":
            if not caller_tenant_id or str(user.tenant_id) != caller_tenant_id:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error_code": "PERMISSION_DENIED",
                        "message": "TENANT_ADMIN can only delete users within their own tenant.",
                    },
                )

        logger.info("user_soft_delete_requested", user_id=str(user_id), caller_role=caller_role)
        await self.user_repo.deactivate(user_id)
        logger.info("user_soft_deleted", user_id=str(user_id))

    async def restore_user(
        self,
        user_id: uuid.UUID,
        caller_role: str,
        caller_tenant_id: str | None,
    ) -> None:
        """
        Restore a soft-deleted user.

        RBAC:
        - PLATFORM_ADMIN: can restore any user.
        - TENANT_ADMIN: can only restore users within their own tenant.
        """
        user = await self.user_repo.get_by_id_include_inactive(user_id)
        if not user:
            raise UserNotFoundError(user_id=user_id)

        if caller_role == "TENANT_ADMIN":
            if not caller_tenant_id or str(user.tenant_id) != caller_tenant_id:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error_code": "PERMISSION_DENIED",
                        "message": "TENANT_ADMIN can only restore users within their own tenant.",
                    },
                )

        logger.info("user_restore_requested", user_id=str(user_id), caller_role=caller_role)
        await self.user_repo.restore(user_id)
        logger.info("user_restored", user_id=str(user_id))
