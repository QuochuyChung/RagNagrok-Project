"""
InvitationTokens ORM model.

Stores one-time invitation tokens for onboarding TENANT_ADMIN and USER accounts.
The raw token is NEVER persisted — only its SHA-256 hex digest is stored so that
a DB leak cannot expose valid tokens.

Token lifecycle:
    1. Admin sends invite → record created with accepted_at=NULL, is_revoked=FALSE
    2. Recipient clicks link → token validated, accepted_at stamped, is_active set TRUE on user
    3. Token becomes permanently invalidated (accepted_at IS NOT NULL)
    4. Admin may revoke a pending invite → is_revoked=TRUE before acceptance

A valid pending invite satisfies:
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


class InvitationTokens(Base):
    """
    Invitation token record in the public schema.

    One record is created per invitation attempt.  After acceptance or
    revocation the record is retained for audit purposes.
    """

    __tablename__ = "invitation_tokens"
    __table_args__ = (
        PrimaryKeyConstraint("token_id", name="invitation_tokens_pkey"),
        ForeignKeyConstraint(
            ["user_id"],
            ["public.users.user_id"],
            ondelete="CASCADE",
            name="invitation_tokens_user_id_fkey",
        ),
        ForeignKeyConstraint(
            ["tenant_id"],
            ["public.tenants.tenant_id"],
            ondelete="CASCADE",
            name="invitation_tokens_tenant_id_fkey",
        ),
        ForeignKeyConstraint(
            ["invited_by"],
            ["public.users.user_id"],
            ondelete="SET NULL",
            name="invitation_tokens_invited_by_fkey",
        ),
        # Token hash must be globally unique — each raw token produces exactly one record
        Index("ux_invitation_tokens_token_hash", "token_hash", unique=True),
        Index("ix_invitation_tokens_user_id", "user_id"),
        Index("ix_invitation_tokens_tenant_id", "tenant_id"),
        {"schema": "public"},
    )

    token_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # SHA-256 hex of the raw URL token — never store the raw token
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Stamped when the invite is accepted — NULL means still pending
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_revoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    # Relationships (read-only helpers — no back_populates needed for invitations)
    user: Mapped["Users"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Users",
        foreign_keys=[user_id],
        lazy="selectin",
    )
