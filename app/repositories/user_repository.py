"""
User repository.

Data access layer for user records stored in PostgreSQL.
Handles password hashing, user lookups by ID, username (per-tenant), or
email (globally unique), and both soft-deactivation and hard-delete.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import UserNotFoundError, UserAlreadyExistsError, EmailAlreadyExistsError
from app.core.logging import get_logger
from app.models import Users
from app.models.role import Roles
from app.utils.hashing import hash_password

logger = get_logger(__name__)


# =============================================================================
# Repository
# =============================================================================


class UserRepository:
    """PostgreSQL data access for users."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Helpers ───────────────────────────────────────────────────────────

    async def _get_active(self, user_id: uuid.UUID) -> Users | None:
        """Return a user by PK if they are active, else None."""
        result = await self.session.execute(
            select(Users)
            .options(selectinload(Users.role))
            .where(
                Users.user_id == user_id,
                Users.status == 'active',
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id_include_inactive(self, user_id: uuid.UUID) -> Users | None:
        """Return a user by PK regardless of status."""
        result = await self.session.execute(
            select(Users)
            .options(selectinload(Users.role))
            .where(
                Users.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def _get_by_username_in_tenant(
        self, user_name: str, tenant_id: uuid.UUID
    ) -> Users | None:
        """Return a user matching (tenant_id, user_name) regardless of active status."""
        result = await self.session.execute(
            select(Users).where(
                Users.user_name == user_name,
                Users.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    # ── Public API ────────────────────────────────────────────────────────

    async def get_role_by_name(self, role_name: str) -> Roles | None:
        """Look up a Role record by its name string (e.g. 'USER', 'TENANT_ADMIN')."""
        result = await self.session.execute(
            select(Roles).where(
                Roles.role_name == role_name,
                Roles.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_name: str,
        plain_password: str,
        tenant_id: uuid.UUID,
        role_id: uuid.UUID,
        email: str | None = None,
        full_name: str | None = None,
    ) -> Users:
        """
        Persist a new user.

        Raises:
            UserAlreadyExistsError: if (tenant_id, user_name) already exists.
            EmailAlreadyExistsError: if email is provided and already exists platform-wide.
        """
        existing_username = await self._get_by_username_in_tenant(user_name, tenant_id)
        if existing_username:
            raise UserAlreadyExistsError(user_name=user_name)

        if email:
            existing_email = await self.get_by_email(email)
            if existing_email:
                raise EmailAlreadyExistsError(email=email)

        new_user = Users(
            user_name=user_name,
            password_hash=hash_password(plain_password),
            tenant_id=tenant_id,
            role_id=role_id,
            email=email,
            full_name=full_name,
            status='active',
        )
        self.session.add(new_user)
        await self.session.commit()
        await self.session.refresh(new_user)
        return new_user

    async def create_inactive(
        self,
        user_name: str,
        tenant_id: uuid.UUID,
        role_id: uuid.UUID,
        email: str,
        full_name: str | None = None,
    ) -> Users:
        """
        Pre-create an invited user with ``is_active=False``.

        The account is locked until the invitation is accepted.  A placeholder
        password hash is stored so the column constraint is satisfied — it cannot
        be used to authenticate because ``is_active=False`` blocks login.

        Raises:
            EmailAlreadyExistsError: if the email already exists platform-wide.
            UserAlreadyExistsError:  if (tenant_id, user_name) already exists.
        """
        if email:
            existing_email = await self.get_by_email(email)
            if existing_email:
                raise EmailAlreadyExistsError(email=email)

        existing_username = await self._get_by_username_in_tenant(user_name, tenant_id)
        if existing_username:
            raise UserAlreadyExistsError(user_name=user_name)

        # Locked placeholder — bcrypt hash of a random UUID; can never be guessed
        locked_hash = hash_password(f"LOCKED_INVITE_{uuid.uuid4()}")

        new_user = Users(
            user_name=user_name,
            password_hash=locked_hash,
            tenant_id=tenant_id,
            role_id=role_id,
            email=email,
            full_name=full_name,
            status='pending_invitation',
        )
        self.session.add(new_user)
        await self.session.flush()
        await self.session.refresh(new_user)
        return new_user

    async def activate_and_set_password(
        self,
        user_id: uuid.UUID,
        plain_password: str,
    ) -> Users:
        """
        Activate an invited user and set their chosen password.

        Called when an invite is accepted.  Loads without the ``is_active``
        filter because the user is still inactive at this point.

        Raises:
            UserNotFoundError: if the user record does not exist.
        """
        result = await self.session.execute(
            select(Users)
            .options(selectinload(Users.role))
            .where(Users.user_id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise UserNotFoundError(user_id=user_id)

        user.password_hash = hash_password(plain_password)
        user.status = 'active'
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def get_by_id(self, user_id: uuid.UUID) -> Users | None:
        """Return an active user by primary key, or ``None``."""
        return await self._get_active(user_id)

    async def get_by_username(self, username: str) -> Users | None:
        """Return an active user by username (global search), including their role."""
        result = await self.session.execute(
            select(Users)
            .options(selectinload(Users.role))
            .where(Users.user_name == username, Users.status == 'active')
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Users | None:
        """
        Return a user matching the given email, regardless of active status.

        Email is unique platform-wide, so no tenant filter is needed.
        Includes the ``role`` relationship for login token generation.
        """
        result = await self.session.execute(
            select(Users)
            .options(selectinload(Users.role))
            .where(Users.email == email)
        )
        return result.scalar_one_or_none()

    async def get_active_by_email(self, email: str) -> Users | None:
        """Return an active user by email, including their role."""
        result = await self.session.execute(
            select(Users)
            .options(selectinload(Users.role))
            .where(Users.email == email, Users.status == 'active')
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[Users]:
        """Return all users across all tenants."""
        result = await self.session.execute(
            select(Users).options(selectinload(Users.role))
        )
        return list(result.scalars().all())

    async def get_all_by_tenant(self, tenant_id: uuid.UUID) -> list[Users]:
        """Return all users belonging to a specific tenant."""
        result = await self.session.execute(
            select(Users)
            .options(selectinload(Users.role))
            .where(
                Users.tenant_id == tenant_id,
            )
        )
        return list(result.scalars().all())

    async def deactivate(self, user_id: uuid.UUID) -> Users:
        """
        Soft-delete a user by setting ``status = 'disabled'``.

        Raises:
            UserNotFoundError: if the user does not exist or is already inactive.
        """
        user = await self._get_active(user_id)
        if not user:
            raise UserNotFoundError(user_id=user_id)

        user.status = 'disabled'
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def restore(self, user_id: uuid.UUID) -> Users:
        """
        Restore a soft-deleted user by setting ``status = 'active'``.
        """
        user = await self.get_by_id_include_inactive(user_id)
        if not user:
            raise UserNotFoundError(user_id=user_id)

        user.status = 'active'
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def hard_delete(self, user_id: uuid.UUID) -> None:
        """
        Permanently remove a user record from the database.

        Raises:
            UserNotFoundError: if the user does not exist (active or inactive).
        """
        result = await self.session.execute(
            select(Users).where(Users.user_id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise UserNotFoundError(user_id=user_id)

        await self.session.execute(
            delete(Users).where(Users.user_id == user_id)
        )
        await self.session.commit()

    async def deactivate_all_by_tenant(self, tenant_id: uuid.UUID) -> int:
        """
        Soft-delete all active users belonging to a tenant.

        Called when a tenant is soft-deleted so its users can no longer log in.

        Returns:
            Number of users deactivated.
        """
        result = await self.session.execute(
            select(Users).where(
                Users.tenant_id == tenant_id,
                Users.status == 'active',
            )
        )
        users = list(result.scalars().all())
        for user in users:
            user.status = 'disabled'
        await self.session.commit()
        return len(users)
