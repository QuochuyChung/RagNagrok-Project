"""
Tokens ORM model.

Unified token table for all token-based flows:
    - INVITATION: Onboarding tokens sent to new users (TENANT_ADMIN / USER).
    - PASSWORD_RESET: Password-reset tokens sent to existing users.

Design (Option 2):
    A single ``public.tokens`` table discriminated by ``token_type``.
    The ``invited_by`` column holds the user ID of the inviter.

Token security model:
    - The raw token is NEVER persisted — only its SHA-256 hex digest.
    - Validation: hash incoming token → look up by hash + token_type → check invariants.

Lifecycle:
    1. Admin/system creates record: accepted_at=NULL, is_revoked=FALSE.
    2. Recipient uses token → accepted_at stamped.
    3. Token is permanently invalidated (accepted_at IS NOT NULL).
    4. Admin may revoke a pending invite → is_revoked=TRUE before acceptance.

A valid pending token satisfies:
    accepted_at IS NULL AND is_revoked = FALSE AND expires_at > NOW()
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Tokens(Base):
    """
    Unified token record in the public schema.

    One record is created per token issuance. After acceptance or
    revocation the record is retained for audit purposes.

    token_type values:
        'INVITATION'     — email invitation to onboard a new user
        'PASSWORD_RESET' — password reset link for an existing user
    """

    __tablename__ = "tokens"
    __table_args__ = (
        PrimaryKeyConstraint("token_id", name="tokens_pkey"),
        ForeignKeyConstraint(
            ["user_id"],
            ["public.users.user_id"],
            ondelete="CASCADE",
            name="tokens_user_id_fkey",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["public.tenants.tenant_id"],
            ondelete="CASCADE",
            name="tokens_tenant_id_fkey",
        ),
        # Composite unique: one hash can't collide across types (belt + suspenders)
        Index("ux_tokens_token_hash_type", "token_hash", "token_type", unique=True),
        Index("ix_tokens_user_id", "user_id"),
        Index("ix_tokens_tenant_id", "tenant_id"),
        Index("ix_tokens_token_type", "token_type"),
        {"schema": "public"},
    )

    token_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # tenant_id is required for INVITATION tokens (data isolation + cascading deletes).
    # For PASSWORD_RESET on a PLATFORM_ADMIN (who has no tenant), this may be NULL.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # Discriminator: 'INVITATION' | 'PASSWORD_RESET'
    token_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # SHA-256 hex of the raw URL token — never store the raw token
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Stamped when the token is consumed — NULL means still pending
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_revoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    # The UUID of the user who sent the invite or reset token (if applicable).
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )

    # Relationship helper (read-only, for invitation context)
    user: Mapped["Users"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Users",
        foreign_keys=[user_id],
        lazy="selectin",
    )
