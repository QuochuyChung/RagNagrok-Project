import uuid

from sqlalchemy import Boolean, Index, PrimaryKeyConstraint, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

class Roles(Base):
    """
    Platform-level role definitions.

    Lives in the ``public`` schema (``schema="public"`` in ``__table_args__``).
    This explicit declaration prevents ``schema_translate_map`` from ever
    redirecting role lookups to a tenant schema when a tenant session is active.
    """
    __tablename__ = 'roles'
    __table_args__ = (
        PrimaryKeyConstraint('role_id', name='roles_pkey'),
        Index('ux_roles_role_name', 'role_name', postgresql_where='(is_deleted = false)', unique=True),
        # Declare this table in the public schema so schema_translate_map
        # never redirects queries on this model to a tenant schema.
        {"schema": "public"},
    )

    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    role_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))

    users: Mapped[list['Users']] = relationship('Users', back_populates='role')