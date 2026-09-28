"""
Token repository.

Data access layer for the unified ``public.tokens`` table (Option 2).
Handles token creation, lookup by hash, status filtering, revocation,
and expiry checking for ALL token types (INVITATION, PASSWORD_RESET).

Token security model:
    - The caller generates a raw token (secrets.token_urlsafe(32)).
    - Only the SHA-256 hex digest is stored here.
    - Validation: hash incoming token → look up by (hash, token_type) → check invariants.

Token types:
    TOKEN_INVITATION     = 'INVITATION'
    TOKEN_PASSWORD_RESET = 'PASSWORD_RESET'
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.token import Tokens
from app.models.user import Users

logger = get_logger(__name__)

TOKEN_INVITATION = "INVITATION"
TOKEN_PASSWORD_RESET = "PASSWORD_RESET"


def _hash_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest of a raw token string."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def generate_raw_token() -> str:
    """Generate a cryptographically random URL-safe token (43 chars)."""
    return secrets.token_urlsafe(32)


class TokenRepository:
    """PostgreSQL data access for the unified tokens table."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Write operations ──────────────────────────────────────────────────

    async def create(
        self,
        user_id: uuid.UUID,
        raw_token: str,
        expires_in_hours: int,
        token_type: str = TOKEN_INVITATION,
        tenant_id: uuid.UUID | None = None,
        invited_by: uuid.UUID | None = None,
    ) -> Tokens:
        """
        Persist a new token record.

        Only the SHA-256 hash of ``raw_token`` is stored.
        ``invited_by`` holds the UUID of the user who issued the token (if applicable).

        Returns:
            The created ``Tokens`` ORM instance.
        """
        token_hash = _hash_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)

        record = Tokens(
            user_id=user_id,
            tenant_id=tenant_id,
            token_type=token_type,
            token_hash=token_hash,
            expires_at=expires_at,
            invited_by=invited_by,
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def create_reset_token(
        self,
        user_id: uuid.UUID,
        raw_token: str,
        expires_in_minutes: int,
    ) -> Tokens:
        """
        Persist a PASSWORD_RESET token (short-lived, no tenant scoping needed).

        Returns:
            The created ``Tokens`` ORM instance.
        """
        token_hash = _hash_token(raw_token)
        # Convert minutes to hours fraction for reuse of timedelta
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)

        record = Tokens(
            user_id=user_id,
            tenant_id=None,
            token_type=TOKEN_PASSWORD_RESET,
            token_hash=token_hash,
            expires_at=expires_at,
            invited_by=user_id,
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def revoke_pending_for_user(
        self,
        user_id: uuid.UUID,
        token_type: str = TOKEN_INVITATION,
    ) -> int:
        """
        Revoke all pending (non-accepted) tokens of a given type for a user.

        Called when resending an invite or issuing a fresh password reset —
        the old token is invalidated before a fresh one is issued.

        Returns:
            Number of tokens revoked.
        """
        result = await self.session.execute(
            select(Tokens).where(
                Tokens.user_id == user_id,
                Tokens.token_type == token_type,
                Tokens.accepted_at.is_(None),
                Tokens.is_revoked.is_(False),
            )
        )
        tokens = list(result.scalars().all())
        for token in tokens:
            token.is_revoked = True
        await self.session.flush()
        return len(tokens)

    async def accept(self, token_id: uuid.UUID) -> None:
        """
        Stamp the token as accepted (single-use invalidation).

        After calling this, the token is permanently invalid.
        """
        result = await self.session.execute(
            select(Tokens).where(Tokens.token_id == token_id)
        )
        record = result.scalar_one_or_none()
        if record:
            record.accepted_at = datetime.now(timezone.utc)
            await self.session.flush()

    async def revoke(self, token_id: uuid.UUID) -> bool:
        """
        Revoke a specific token by token_id.

        Returns:
            True if the token was found and revoked, False if not found.
        """
        result = await self.session.execute(
            select(Tokens).where(Tokens.token_id == token_id)
        )
        record = result.scalar_one_or_none()
        if not record:
            return False
        record.is_revoked = True
        await self.session.flush()
        return True

    # ── Read operations ───────────────────────────────────────────────────

    async def get_by_raw_token(
        self,
        raw_token: str,
        token_type: str = TOKEN_INVITATION,
    ) -> Tokens | None:
        """
        Look up a token record by the raw (un-hashed) token and its type.

        Hashes the token and queries by (hash, token_type).
        Loads the related ``user`` eagerly for validation context.

        Returns:
            The matching ``Tokens`` record, or ``None`` if not found.
        """
        token_hash = _hash_token(raw_token)
        result = await self.session.execute(
            select(Tokens)
            .options(selectinload(Tokens.user).selectinload(Users.role))
            .where(
                Tokens.token_hash == token_hash,
                Tokens.token_type == token_type,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(
        self, token_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Tokens | None:
        """
        Look up an invitation token by its UUID, scoped to a tenant.

        Used for revoke / resend to ensure tenant isolation.
        """
        result = await self.session.execute(
            select(Tokens)
            .options(selectinload(Tokens.user).selectinload(Users.role))
            .where(
                Tokens.token_id == token_id,
                Tokens.tenant_id == tenant_id,
                Tokens.token_type == TOKEN_INVITATION,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: uuid.UUID,
        status_filter: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Tokens], int]:
        """
        Return paginated INVITATION token records for a tenant.

        Args:
            tenant_id:     Filter to this tenant.
            status_filter: One of 'pending'|'accepted'|'expired'|'revoked', or None for all.
            page:          1-indexed page number.
            page_size:     Records per page.

        Returns:
            A tuple of (records, total_count).
        """
        now = datetime.now(timezone.utc)
        base_query = (
            select(Tokens)
            .options(selectinload(Tokens.user).selectinload(Users.role))
            .where(
                Tokens.tenant_id == tenant_id,
                Tokens.token_type == TOKEN_INVITATION,
            )
        )

        if status_filter == "pending":
            base_query = base_query.where(
                Tokens.accepted_at.is_(None),
                Tokens.is_revoked.is_(False),
                Tokens.expires_at > now,
            )
        elif status_filter == "accepted":
            base_query = base_query.where(Tokens.accepted_at.isnot(None))
        elif status_filter == "expired":
            base_query = base_query.where(
                Tokens.accepted_at.is_(None),
                Tokens.is_revoked.is_(False),
                Tokens.expires_at <= now,
            )
        elif status_filter == "revoked":
            base_query = base_query.where(Tokens.is_revoked.is_(True))

        count_result = await self.session.execute(base_query)
        all_records = list(count_result.scalars().all())
        total = len(all_records)

        offset = (page - 1) * page_size
        paginated = all_records[offset : offset + page_size]

        return paginated, total

    async def get_pending_for_user(
        self,
        user_id: uuid.UUID,
        token_type: str = TOKEN_INVITATION,
    ) -> Tokens | None:
        """
        Return the most recent active pending token of a given type for a user, or None.

        Used for resend flows to check the user still has a pending token.
        """
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(Tokens)
            .where(
                Tokens.user_id == user_id,
                Tokens.token_type == token_type,
                Tokens.accepted_at.is_(None),
                Tokens.is_revoked.is_(False),
                Tokens.expires_at > now,
            )
            .order_by(Tokens.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_tenant_admin_pending(self, tenant_id: uuid.UUID) -> Tokens | None:
        """
        Return the pending TENANT_ADMIN invite token for a given tenant, or None.

        Used by the resend-admin-invite endpoint.
        Filters by user.status == 'pending_invitation' (lazy-expiry model).
        """
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(Tokens)
            .options(selectinload(Tokens.user).selectinload(Users.role))
            .join(Users, Users.user_id == Tokens.user_id)
            .where(
                Tokens.tenant_id == tenant_id,
                Tokens.token_type == TOKEN_INVITATION,
                Tokens.accepted_at.is_(None),
                Tokens.is_revoked.is_(False),
                Users.status == "pending_invitation",  # Fixed: was Users.is_active
            )
            .order_by(Tokens.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()



