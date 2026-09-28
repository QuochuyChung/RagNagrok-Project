import datetime
import uuid
from typing import Optional, Any

from sqlalchemy import Index, PrimaryKeyConstraint, String, Uuid, text, ForeignKeyConstraint, BigInteger, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB, INET
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class AuditLogs(Base):
    """
    Platform-wide audit log table.

    Lives in the ``public`` schema (``schema="public"`` in ``__table_args__``).
    This explicit declaration prevents ``schema_translate_map`` from ever
    redirecting audit log writes to a tenant schema when a tenant session
    is active.

    ``user_id`` references ``public.users`` explicitly so the FK resolves
    correctly regardless of which schema_translate_map is in effect.
    """
    __tablename__ = 'audit_logs'
    __table_args__ = (
        # Explicit public. prefix so this FK resolves correctly even when
        # a schema_translate_map is active for a tenant session.
        ForeignKeyConstraint(['user_id'], ['public.users.user_id'], ondelete='SET NULL', name='audit_logs_user_id_fkey'),
        PrimaryKeyConstraint('id', name='audit_logs_pkey'),
        Index('ix_audit_logs_action_time', 'action_time'),
        Index('ix_audit_logs_user_id', 'user_id'),
        # Declare this table in the public schema so schema_translate_map
        # never redirects queries on this model to a tenant schema.
        {"schema": "public"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    action_time: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    ip_address: Mapped[Optional[Any]] = mapped_column(INET, nullable=True)

    endpoint: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # action_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # additional_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    # source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    user: Mapped[Optional['Users']] = relationship('Users', back_populates='audit_logs')

