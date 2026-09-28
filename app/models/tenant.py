import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, PrimaryKeyConstraint, String, Text, Uuid, text, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

class Tenants(Base):
    """
    Platform-level tenant registry.

    Lives in the ``public`` schema (``schema="public"`` in ``__table_args__``).
    This explicit schema declaration ensures the table is NEVER redirected by
    ``schema_translate_map`` when a tenant-scoped session is active.

    ``tenant_name`` is UNIQUE and immutable — it is used to derive the
    PostgreSQL schema name: ``SCHEMA_{tenant_name.upper()}``.
    """
    __tablename__ = 'tenants'
    __table_args__ = (
        PrimaryKeyConstraint('tenant_id', name='tenants_pkey'),
        Index('ux_tenants_collection_name', 'collection_name', unique=True),
        # UNIQUE on tenant_name guarantees no two tenants map to the same schema.
        # Enforced upstream by API validation (no spaces / hyphens allowed).
        Index('ux_tenants_tenant_name', 'tenant_name', unique=True),
        # Declare this table in the public schema so schema_translate_map
        # never redirects queries on this model to a tenant schema.
        {"schema": "public"},
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    tenant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    collection_name: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_dek: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text('NOW()'))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=datetime.utcnow)

    # NOTE: ``tenant_name`` is part of the AWS KMS EncryptionContext used to wrap
    # the tenant DEK (see ``app.core.encryption._tenant_encryption_context``).
    # Renaming a tenant would invalidate that context and make every blob already
    # stored (fields, Qdrant payload, file DEKs) undecryptable. We therefore
    # forbid assignments to ``tenant_name`` after the row is loaded.
    _IMMUTABLE_AFTER_LOAD = ("tenant_name",)

    def __setattr__(self, key, value):
        if key in self._IMMUTABLE_AFTER_LOAD and getattr(self, "tenant_id", None) is not None:
            # Allow Pydantic / SQLAlchemy internal hydration during flush, but
            # block updates that change the value once it has been set.
            current = self.__dict__.get(key)
            if current is not None and current != value:
                raise AttributeError(
                    "tenant_name is immutable — it is bound to the KMS "
                    "EncryptionContext used to wrap the tenant DEK. Renaming "
                    "would make all encrypted data undecryptable."
                )
        super().__setattr__(key, value)



    # documents and conversations are NOT listed here — those tables live in
    # tenant schemas and no longer have a FK back to public.tenants.
    users: Mapped[list['Users']] = relationship('Users', back_populates='tenant')