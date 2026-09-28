import datetime
import uuid

from sqlalchemy import Boolean, Index, PrimaryKeyConstraint, String, Uuid, Text, text, ForeignKeyConstraint, Integer, DateTime, BigInteger
from sqlalchemy import Boolean, CheckConstraint, Index, PrimaryKeyConstraint, String, Uuid, text, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class Documents(Base):
    """
    Tenant-scoped document metadata table.

    Lives inside the tenant's isolated schema (e.g. ``SCHEMA_FPTCORP``),
    NOT in ``public``.  Because every tenant has its own schema, there is no
    need for a ``tenant_id`` column — isolation is guaranteed at the
    PostgreSQL schema level by ``schema_translate_map`` in ``get_db_session``.

    Sprint 3 additions: status, minio_object_key, minio_version_id,
    content_hash_hmac for async Celery ingestion and duplicate detection.
    """
    __tablename__ = 'documents'
    __table_args__ = (
        PrimaryKeyConstraint('doc_id', name='documents_pkey'),
        # Uniqueness scoped to the schema (= tenant) — no tenant_id needed.
        Index('ux_documents_hash_version', 'content_hash', 'doc_version', unique=True),
    )

    doc_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    doc_name: Mapped[str] = mapped_column(Text, nullable=False)
    doc_type: Mapped[str] = mapped_column(String(255), nullable=False)
    doc_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('1'))
    ingested_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    content_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text('0'))
    status: Mapped[str] = mapped_column(String(200), nullable=False, server_default=text("'PENDING'"))
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))

    chunks: Mapped[list['Chunks']] = relationship('Chunks', back_populates='doc')
    storage_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    encrypted_file_dek: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    doc_name_lookup_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)