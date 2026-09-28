"""
Document repository.

Data access layer for document metadata stored in PostgreSQL.
Handles doc_id, version, content_hash, and soft-delete state.

Encryption:
    - Encrypted fields: Documents.doc_name, Chunks.section, Chunks.content
    - content_hash is intentionally NOT encrypted — it is used as a
      deduplication unique index and must be queryable in plaintext.
    - All write methods accept a plaintext ``dek`` (bytes) and encrypt before
      insert. Read methods accept an optional ``dek`` and decrypt after fetch.
"""

from __future__ import annotations
################################################################
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Documents, Chunks
##############################################################



from app.core.logging import get_logger
from app.schemas.document import DocumentStatus
from app.core.errors import DocumentNotFoundError
from app.utils.field_cipher import encrypt_field, decrypt_field, compute_doc_name_lookup_hash

logger = get_logger(__name__)


class DocumentRepository:
    """PostgreSQL data access for document metadata."""

    # TODO (Sprint 3): inject SQLAlchemy async session
##########################################################################
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_latest_version(
        self, doc_name_lookup_hash: str
    ) -> Documents | None:
        """
        Lấy version MỚI NHẤT theo doc_name_lookup_hash (blind index deterministic),
        KHÔNG lọc is_deleted -> số version luôn tăng liên tục kể cả sau khi bản
        trước bị xóa.

        NOTE: doc_name (ciphertext) là non-deterministic (AES-GCM random nonce),
        KHÔNG dùng để query bằng được. Phải dùng doc_name_lookup_hash (HMAC
        deterministic) — xem compute_doc_name_lookup_hash() trong field_cipher.py.
        """
        result = await self.session.execute(
            select(Documents)
            .where(
                Documents.doc_name_lookup_hash == doc_name_lookup_hash,
            )
            .order_by(Documents.doc_version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        doc_name: str,
        doc_type: str,
        doc_version: int,
        content_hash: str,
        file_size: int,
        status: str = DocumentStatus.PENDING,
        storage_key: str,
        dek: bytes,
    ) -> Documents:
        """Create a new document row with an encrypted doc_name + deterministic
        lookup hash for future WHERE queries.

        Args:
            dek: Plaintext Tenant DEK used to encrypt doc_name AND compute the
                lookup hash. content_hash is stored in plaintext (dedup index).
        """
        encrypted_name = encrypt_field(doc_name, dek)
        lookup_hash = compute_doc_name_lookup_hash(doc_name, dek)
        doc = Documents(
            doc_name=encrypted_name,
            doc_name_lookup_hash=lookup_hash,
            doc_type=doc_type,
            doc_version=doc_version,
            content_hash=content_hash,
            file_size=file_size,
            status=status,
            storage_key=storage_key,
        )
        self.session.add(doc)
        await self.session.flush()
        await self.session.refresh(doc)
        return doc

    async def update_storage_key(self, doc_id: uuid.UUID, storage_key: str) -> None:
        result = await self.session.execute(
            update(Documents).where(Documents.doc_id == doc_id).values(storage_key=storage_key)
        )
        if result.rowcount == 0:
            raise DocumentNotFoundError(str(doc_id))

    async def update_encrypted_file_dek(self, doc_id: uuid.UUID, encrypted_file_dek: str) -> None:
        stmt = (
            update(Documents)
            .where(Documents.doc_id == doc_id)
            .values(encrypted_file_dek=encrypted_file_dek)
        )
        result = await self.session.execute(stmt)
        if result.rowcount == 0:
            raise DocumentNotFoundError(str(doc_id))
        await self.session.commit()


    async def create_chunks(self, *, doc_id: uuid.UUID, chunks: list, dek: bytes) -> list[Chunks]:
        """Persist chunk rows for a document inside the current transaction.

        Args:
            dek: Plaintext Tenant DEK used to encrypt chunk section and content.
        """
        import asyncio
        document_is_deleted = await self.session.scalar(
            select(Documents.is_deleted).where(Documents.doc_id == doc_id)
        )

        def _prepare_chunk_rows() -> list[Chunks]:
            rows: list[Chunks] = []
            for idx, chunk in enumerate(chunks):
                metadata = chunk.metadata if isinstance(chunk.metadata, dict) else {}
                section = (
                    metadata.get("h5")
                    or metadata.get("h4")
                    or metadata.get("h3")
                    or metadata.get("h2")
                    or metadata.get("h1")
                )
                section=(section[:252] + "...") if section and len(section) > 255 else section
                content = chunk.page_content
                token_count = len(chunk.page_content.split())

                # Encrypt sensitive text fields before persisting
                encrypted_content = encrypt_field(content, dek)
                encrypted_section = encrypt_field(section, dek) if section else None

                row = Chunks(
                    doc_id=doc_id,
                    chunk_index=idx,
                    content=encrypted_content,
                    token_count=token_count,
                    # A document can be deleted while its background chunking job is
                    # still running. New rows must inherit that soft-delete state.
                    is_deleted=bool(document_is_deleted),
                    section=encrypted_section,
                    page_start=metadata.get("page_start"),
                    page_end=metadata.get("page_end"),
                )
                rows.append(row)
            return rows

        rows = await asyncio.to_thread(_prepare_chunk_rows)

        self.session.add_all(rows)
        await self.session.flush()
        return rows

    async def list_by_tenant(self, dek: bytes | None = None) -> list[Documents]:
        """List ALL documents (active + soft-deleted) so UI can dim deleted ones
        and offer restore. Soft-deleted docs still appear in the listing."""
        result = await self.session.execute(
            select(Documents)
            .order_by(
                # Active documents lên trước, soft-deleted xuống cuối.
                # Trong cùng 1 nhóm, version mới hơn lên trước.
                Documents.is_deleted.is_(False).desc(),
                Documents.doc_version.desc(),
            )
        )
        docs = list(result.scalars().all())
        if dek:
            for doc in docs:
                doc.doc_name = decrypt_field(doc.doc_name, dek)
        return docs

    async def get_by_id(
        self, doc_id: uuid.UUID, dek: bytes | None = None
    ) -> Documents | None:
        """Fetch an active document and optionally decrypt doc_name."""
        result = await self.session.execute(
            select(Documents).where(
                Documents.doc_id == doc_id,
                Documents.is_deleted.is_(False),
            )
        )
        doc = result.scalar_one_or_none()
        if doc and dek:
            doc.doc_name = decrypt_field(doc.doc_name, dek)
        return doc

    async def soft_delete(self, doc: Documents) -> Documents:
        doc.is_deleted = True
        await self._set_chunks_deleted(doc.doc_id, is_deleted=True)
        await self.session.commit()
        await self.session.refresh(doc)
        return doc

    async def update_status(self, doc_id: uuid.UUID, status: str) -> bool:
        exist_document = await self.get_by_id_any_status(doc_id=doc_id)
        if exist_document:
            exist_document.status = status
            await self.session.commit()
            return True
        return False

    async def mark_superseded(self, doc: Documents) -> Documents:
        doc.is_deleted = True
        await self._set_chunks_deleted(doc.doc_id, is_deleted=True)
        await self.session.flush()
        await self.session.refresh(doc)
        return doc

    async def get_by_id_any_status(self, doc_id) -> Documents | None:
        stmt = select(Documents).where(
            Documents.doc_id == doc_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_name(self, doc_name_lookup_hash: str) -> Documents | None:
        stmt = select(Documents).where(
            Documents.doc_name_lookup_hash == doc_name_lookup_hash,
            Documents.is_deleted.is_(False)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def restore(self, doc: Documents) -> Documents:
        doc.is_deleted = False
        await self._set_chunks_deleted(doc.doc_id, is_deleted=False)
        await self.session.commit()
        await self.session.refresh(doc)
        return doc

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def get_active_by_content_hash(
        self, content_hash: str, exclude_lookup_hash: str
    ) -> Documents | None:
        """
        Tìm document ĐANG ACTIVE nào trong tenant có cùng content_hash,
        KHÁC doc_name (so bằng lookup_hash deterministic, không so ciphertext
        trực tiếp vì AES-GCM random nonce sẽ luôn lệch dù cùng plaintext).
        """
        stmt = select(Documents).where(
            Documents.content_hash == content_hash,
            Documents.doc_name_lookup_hash != exclude_lookup_hash,
            Documents.is_deleted.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _set_chunks_deleted(self, doc_id: uuid.UUID, *, is_deleted: bool) -> None:
        """Keep a document's chunks in the same soft-delete state as the document."""
        await self.session.execute(
            update(Chunks)
            .where(Chunks.doc_id == doc_id)
            .values(is_deleted=is_deleted)
        )

    async def get_chunks_by_doc_id(self, doc_id: uuid.UUID, dek: bytes | None = None) -> list[Chunks]:
        """Fetch all chunks for a document, decrypting section/content if dek is provided."""
        result = await self.session.execute(
            select(Chunks)
            .where(Chunks.doc_id == doc_id)
            .order_by(Chunks.chunk_index)
        )
        chunks = list(result.scalars().all())
        if dek:
            for chunk in chunks:
                chunk.content = decrypt_field(chunk.content, dek)
                if chunk.section:
                    chunk.section = decrypt_field(chunk.section, dek)
        return chunks

    
