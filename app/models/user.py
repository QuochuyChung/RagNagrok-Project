import uuid
from datetime import datetime

from sqlalchemy import Boolean, Index, PrimaryKeyConstraint, String, Uuid, text, ForeignKeyConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class Users(Base):
    """
    Platform-wide user identity table.

    Lives in the ``public`` schema (``schema="public"`` in ``__table_args__``).
    This explicit declaration prevents ``schema_translate_map`` from ever
    redirecting user lookups to a tenant schema when a tenant session is active.

    Email is unique globally (platform-wide) — one email cannot belong to
    two tenants simultaneously (Option 1 — Shared Identity).
    Username is unique per-tenant (composite index on tenant_id + user_name).
    """
    __tablename__ = 'users'
    __table_args__ = (
        ForeignKeyConstraint(['role_id'], ['public.roles.role_id'], ondelete='RESTRICT', name='users_role_id_fkey'),
        ForeignKeyConstraint(['tenant_id'], ['public.tenants.tenant_id'], ondelete='RESTRICT', name='users_tenant_id_fkey'),
        PrimaryKeyConstraint('user_id', name='users_pkey'),
        Index('ix_users_role_id', 'role_id'),
        # username is unique within a tenant
        Index('ux_users_tenant_username', 'tenant_id', 'user_name', unique=True),
        # email is unique globally across the entire platform (not just per-tenant)
        Index('ux_users_email_global', 'email', unique=True),
        # Declare this table in the public schema so schema_translate_map
        # never redirects queries on this model to a tenant schema.
        {"schema": "public"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    user_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'active'"))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('NOW()'))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow)

    role: Mapped['Roles'] = relationship('Roles', back_populates='users')
    tenant: Mapped['Tenants'] = relationship('Tenants', back_populates='users')
    audit_logs: Mapped[list['AuditLogs']] = relationship('AuditLogs', back_populates='user')
    conversations: Mapped[list['Conversations']] = relationship('Conversations', back_populates='user')