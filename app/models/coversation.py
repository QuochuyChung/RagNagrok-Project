import datetime
import uuid

from sqlalchemy import ForeignKeyConstraint, PrimaryKeyConstraint, Index, Uuid, String, DateTime, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Conversations(Base):
    """
    Tenant-scoped conversation table.

    Lives inside the tenant's isolated schema (e.g. ``SCHEMA_FPTCORP``).
    No ``tenant_id`` column is needed — isolation is guaranteed by the
    PostgreSQL schema itself.

    Cross-schema FK: ``user_id`` references ``public.users(user_id)`` because
    the Users table lives in the shared ``public`` schema (Option 1 —
    Shared Identity).  PostgreSQL fully supports cross-schema foreign keys.
    """
    __tablename__ = 'conversations'
    __table_args__ = (
        # Cross-schema FK → public.users (Users live in the shared public schema)
        ForeignKeyConstraint(
            ['user_id'],
            ['public.users.user_id'],
            ondelete='RESTRICT',
            name='conversations_user_id_fkey',
        ),
        PrimaryKeyConstraint('conversation_id', name='conversations_pkey'),
        Index('ix_conversations_user_id', 'user_id'),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    turn_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    token_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))

    user: Mapped['Users'] = relationship('Users', back_populates='conversations')
    messages: Mapped[list['Messages']] = relationship('Messages', back_populates='conversation', cascade="all, delete-orphan")
