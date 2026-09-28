"""
Document service.

Handles chunking, content hashing (idempotent ingestion), versioning,
and soft-delete of documents.

TODO (Sprint 3): Implement ingestion pipeline.
"""

from __future__ import annotations
###################################################
import asyncio
import uuid
import tempfile
import os
import mammoth
import io
from pathlib import Path
from typing import Literal

from qdrant_client.models import PointStruct
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession, AsyncEngine

from app.models import Tenants
from app.utils.s3_storage import save_file_to_s3, read_file_from_s3_by_key, unwrap_file_dek, decrypt_file_bytes, \
    encrypt_file_bytes, generate_file_dek
from app.core.custome_session import get_db_with_tenant_scope_session
from app.core.errors import DuplicateContentError, UnsupportedFileTypeError, EmptyFileError, DocumentNotFoundError
from app.core.config import get_settings
from app.repositories.document_repository import DocumentRepository
from app.repositories.qdrant_repository import QdrantRepository
from app.schemas.document import DocumentStatus
from app.utils.hashing import compute_sha256, zeroize
from app.services.chunker_service import ChunkerService
from app.core.tenant_dek_provider import get_plaintext_dek_from_blob
from app.profiling import LatencyTracker
from app.utils.field_cipher import encrypt_field, decrypt_field, compute_doc_name_lookup_hash
###########################################################

from app.core.logging import get_logger

logger = get_logger(__name__)

settings = get_settings()
ALLOWED_EXTENSIONS = set(settings.document_allowed_extensions)
STORAGE_ROOT = Path(settings.document_storage_root)

ChunkingMode = Literal["hybrid", "recursive_only"]

_doc_process_semaphore = asyncio.Semaphore(3)

# Retry configuration for background tasks
RETRY_CONFIG = {
    "max_attempts": 3,
    "base_delay": 2,  # seconds
    "max_delay": 30,  # seconds
    "exponential_base": 2,
}

CONTENT_TYPE_MAP = {
    "pdf": "application/pdf",
    "md": "text/markdown; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _calculate_retry_delay(attempt: int) -> float:
    """Calculate exponential backoff delay."""
    delay = RETRY_CONFIG["base_delay"] * (RETRY_CONFIG["exponential_base"] ** attempt)
    return min(delay, RETRY_CONFIG["max_delay"])


class DocumentService:
    """Business logic layer for document ingestion and management."""

    def __init__(self, repo: DocumentRepository, qdrant_repo: QdrantRepository) -> None:
        self.repo = repo
        self.qdrant_repo = qdrant_repo

    async def ingest_document(
        self, tenant_id: uuid.UUID, filename: str, content: bytes, tenant_name: str,
        encrypted_tenant_dek: bytes
    ) -> dict:
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise UnsupportedFileTypeError(ext)          # thay cho raise ValueError(...)
        if not content:
            raise EmptyFileError()                        # thay cho raise ValueError("File rộng")

        tracker = LatencyTracker(
            "document_ingest",
            tenant_id=str(tenant_id),
            file_size=len(content),
            doc_type=ext.lstrip("."),
        )

        # Resolve Tenant DEK once at the start of the pipeline
        async with tracker.astage("unwrap_tenant_dek"):
            tenant_dek = await get_plaintext_dek_from_blob(encrypted_tenant_dek, tenant_name)
        try:
            with tracker.stage("hash_and_lookup"):
                content_hash = compute_sha256(content)
                lookup_hash = compute_doc_name_lookup_hash(filename, tenant_dek)
            duplicate = await self.repo.get_active_by_content_hash(
                content_hash, exclude_lookup_hash=lookup_hash
            )
            if duplicate:
                duplicate_name = decrypt_field(duplicate.doc_name, tenant_dek)
                raise DuplicateContentError(duplicate_name)

            # doc_name comparison must use encrypted form since DB stores encrypted values

            latest = await self.repo.get_latest_version(lookup_hash)
            # Decrypt for plaintext comparison
            if latest:
                latest.doc_name = decrypt_field(latest.doc_name, tenant_dek)

            # Trùng nội dung với version mới nhất (và version đó chưa bị xóa) -> bỏ qua, không tạo version mới
            # Cùng tên cùng nội dung -> trùng không đánh dấu cái cũ
            if latest and not latest.is_deleted and latest.content_hash == content_hash:
                logger.info("document_duplicate_skip", doc_id=str(latest.doc_id))
                result = self._to_dict(latest, is_duplicate=True, chunk_count=None)
                result["old_doc_id"] = None
                return result

            next_version = latest.doc_version + 1 if latest else 1

            try:
                old_doc_id = None
                # Khác nội dung -> đá bản active cũ xuống false
                # Cùng tên khác nội dung -> đánh dấu cái hiện tại là cái cũ
                if latest and not latest.is_deleted:
                    old_doc_id = latest.doc_id
                    await self.repo.mark_superseded(latest)

                # Tạo version mới
                # Khác tên khác nội dung
                doc = await self.repo.create(
                    doc_name=filename,
                    doc_type=ext.lstrip("."),
                    doc_version=next_version,
                    content_hash=content_hash,
                    file_size=len(content),
                    status=DocumentStatus.PENDING,
                    storage_key="",
                    dek=tenant_dek,
                )
                async with tracker.astage("generate_file_dek_kms"):
                    plaintext_dek, encrypted_dek_b64 = await generate_file_dek(tenant_name, doc_id=str(doc.doc_id))
                with tracker.stage("encrypt_file_bytes", size_bytes=len(content)):
                    encrypted_content = encrypt_file_bytes(content, plaintext_dek)
                zeroize(plaintext_dek)
                plaintext_dek = None

                async with tracker.astage("upload_s3", size_bytes=len(encrypted_content)):
                    key = await save_file_to_s3(
                        tenant_name=tenant_name,
                        doc_type=ext.lstrip("."),
                        ingested_at=doc.ingested_at,     # có sẵn sau repo.create() + refresh
                        doc_id=str(doc.doc_id),
                        ext=ext.lstrip("."),
                        content=encrypted_content,
                    )
                async with tracker.astage("db_commit_metadata"):
                    await self.repo.update_storage_key(doc.doc_id, key)
                    await self.repo.update_encrypted_file_dek(doc.doc_id, encrypted_dek_b64)

                    await self.repo.commit()

                logger.info(
                    "document_ingested",
                    doc_id=str(doc.doc_id),
                    version=next_version,
                    chunk_count=None,
                )
                # Return with plaintext doc_name for the API response
                doc.doc_name = filename
                result = self._to_dict(doc, is_duplicate=False, chunk_count=None)
                # Khác tên khác nội dung thì không đánh dấu bản cũ
                result["old_doc_id"] = str(old_doc_id) if old_doc_id else None
                return result
            except Exception:
                await self.repo.rollback()
                logger.exception("document_ingest_pipeline_failed", tenant_id=str(tenant_id), filename=filename)
                raise
        finally:
            tracker.finish()
            zeroize(tenant_dek)
            tenant_dek = None

    async def process_document_async(
        self, *, chunking_mode: ChunkingMode = "hybrid" ,doc_id: uuid.UUID, tenant_id: uuid.UUID, tenant_name: str,
        collection_name: str, filename: str, doc_version: int,
        engine: AsyncEngine, session_maker: async_sessionmaker[AsyncSession],
        old_doc_id: uuid.UUID | None = None,
        encrypted_tenant_dek: bytes,
    ) -> None:
        async with _doc_process_semaphore:
            return await self._process_document_async_internal(
                chunking_mode=chunking_mode, doc_id=doc_id, tenant_id=tenant_id, tenant_name=tenant_name,
                collection_name=collection_name, filename=filename, doc_version=doc_version,
                engine=engine, session_maker=session_maker, old_doc_id=old_doc_id,
                encrypted_tenant_dek=encrypted_tenant_dek
            )

    async def _process_document_async_internal(
        self, *, chunking_mode: ChunkingMode = "hybrid" ,doc_id: uuid.UUID, tenant_id: uuid.UUID, tenant_name: str,
        collection_name: str, filename: str, doc_version: int,
        engine: AsyncEngine, session_maker: async_sessionmaker[AsyncSession],
        old_doc_id: uuid.UUID | None = None,
        encrypted_tenant_dek: bytes,
    ) -> None:
        ext = Path(filename).suffix
        tracker = LatencyTracker(
            "document_process",
            tenant_id=str(tenant_id),
            doc_id=str(doc_id),
            doc_version=doc_version,
            chunking_mode=chunking_mode,
        )

        # Resolve Tenant DEK once for this entire background job
        async with tracker.astage("unwrap_tenant_dek"):
            tenant_dek = await get_plaintext_dek_from_blob(encrypted_tenant_dek, tenant_name)
        try:
            async with get_db_with_tenant_scope_session(engine=engine, session_maker=session_maker, tenant_name=tenant_name) as session:
                document_repo = DocumentRepository(session)
                document = await document_repo.get_by_id_any_status(doc_id)

                if document is None:
                    logger.error("document_not_found_for_processing", doc_id=str(doc_id))
                    return

                async with tracker.astage("download_s3"):
                    if document.storage_key:
                        raw_content = await read_file_from_s3_by_key(document.storage_key)
                    else:
                        legacy_key = f"{tenant_id}/{document.doc_id}.{ext.lstrip('.')}"
                        raw_content = await read_file_from_s3_by_key(legacy_key)

                # Document cũ (ingest trước khi có tính năng encrypt) không có DEK -> chưa mã hóa,
                # dùng thẳng. Document mới -> bắt buộc decrypt trước khi chunk.
                if document.encrypted_file_dek:
                    async with tracker.astage("unwrap_file_dek_kms"):
                        plaintext_dek = await unwrap_file_dek(
                            document.encrypted_file_dek, tenant_name, doc_id=str(doc_id)
                        )
                    with tracker.stage("decrypt_file_bytes", size_bytes=len(raw_content)):
                        content = decrypt_file_bytes(raw_content, plaintext_dek)
                    zeroize(plaintext_dek)
                    plaintext_dek = None
                else:
                    content = raw_content

                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                    tmp.write(content)
                    temp_path = Path(tmp.name)

                try:
                    async with tracker.astage("chunking"):
                        chunks = await self._chunk_with_full_pipeline(temp_path)
                    tracker.add_context(chunk_count=len(chunks))

                    logger.info("chunking_completed", doc_id=str(doc_id), chunk_count=len(chunks))

                    # create_chunks mã hoá từng chunk bằng tenant DEK rồi ghi Postgres
                    async with tracker.astage("encrypt_and_save_chunks_db", chunk_count=len(chunks)):
                        await document_repo.create_chunks(doc_id=doc_id, chunks=chunks, dek=tenant_dek)
                    async with tracker.astage("embed_and_upsert_qdrant", chunk_count=len(chunks)):
                        await self._upsert_chunks_to_qdrant(
                            collection_name=collection_name,
                            tenant_id=tenant_id,
                            doc_id=doc_id,
                            doc_version=doc_version,
                            filename=filename,
                            chunks=chunks,
                            tenant_dek=tenant_dek,
                            tracker=tracker,
                        )

                    logger.info("qdrant_upsert_completed", doc_id=str(doc_id))

                    await document_repo.update_status(doc_id=doc_id, status=DocumentStatus.COMPLETED)

                    logger.info("document_processed", doc_id=str(doc_id), chunk_count=len(chunks))

                    # Race-condition guard: trong lúc job này đang chunk/embed, có thể
                    # đã bị 1 version mới hơn supersede (is_deleted=True) rồi. Nếu vậy,
                    # point mình vừa upsert đã lỗi thời ngay khi vừa xong -> tự dọn
                    # point của CHÍNH MÌNH, không chờ ai dọn hộ.
                    self_check = await document_repo.get_by_id_any_status(doc_id)
                    if self_check and self_check.is_deleted:
                        try:
                            await self.qdrant_repo.delete_by_doc_id(collection_name, str(doc_id))
                            logger.info("qdrant_self_cleanup_stale_version", doc_id=str(doc_id))
                        except Exception:
                            logger.exception("qdrant_self_cleanup_failed", doc_id=str(doc_id))

                    # Best-effort: dọn point Qdrant của version cũ, chỉ chạy SAU KHI
                    # version mới đã COMPLETED. Lỗi ở đây chỉ log, không đổi status
                    # của version mới — version mới vẫn READY dùng bình thường,
                    # chỉ là point cũ có thể còn sót lại (retrieve.py cần double-check
                    # doc_id active ở Postgres như đã note trước đó — chưa code phần này).
                    if old_doc_id:
                        try:
                            await self.qdrant_repo.delete_by_doc_id(collection_name, str(old_doc_id))
                        except Exception:
                            logger.exception(
                                "qdrant_cleanup_old_version_failed",
                                old_doc_id=str(old_doc_id),
                                new_doc_id=str(doc_id),
                            )

                except Exception as e:
                    await session.rollback()
                    logger.exception("document_process_failed", doc_id=str(doc_id), message=str(f"message: {e}"))
                    await document_repo.update_status(doc_id=doc_id, status=DocumentStatus.FAILED)

                finally:
                    os.unlink(temp_path)
        finally:
            tracker.finish()
            zeroize(tenant_dek)
            tenant_dek = None


    async def ingest_batch(self, tenant_id: uuid.UUID, tenant_name: str, files: list[tuple[str, bytes]],
                           encrypted_tenant_dek: bytes) -> dict:
        """
        files: list[(doc_name, content_bytes)]
        Two-tier check: so file_size trước, chỉ hash khi size trùng bản active.
        Commit riêng từng file — 1 file lỗi không ảnh hưởng các file khác trong batch.
        """
        # Resolve Tenant DEK once for the whole batch
        tenant_dek = await get_plaintext_dek_from_blob(encrypted_tenant_dek, tenant_name)

        results = {"new": [], "updated": [], "unchanged": [], "failed": []}
        max_bytes = settings.max_upload_size_mb * 1024 * 1024
        try:
            for doc_name, content in files:
                try:
                    ext = Path(doc_name).suffix.lower()
                    if ext not in ALLOWED_EXTENSIONS:
                        raise ValueError(f"Định dạng không hỗ trợ: {ext}")
                    if not content:
                        raise ValueError("File rỗng")
                    if len(content) > max_bytes:
                        raise ValueError(f"File vượt quá {settings.max_upload_size_mb}MB")

                    file_size = len(content)
                    # Lookup uses encrypted doc_name since DB stores encrypted values
                    lookup_hash = compute_doc_name_lookup_hash(doc_name, tenant_dek)
                    latest = await self.repo.get_latest_version(lookup_hash)
                    if latest:
                        latest.doc_name = decrypt_field(latest.doc_name, tenant_dek)
                    is_active_candidate = latest is not None and not latest.is_deleted

                    if is_active_candidate and latest.file_size == file_size:
                        # Size trùng -> nghi ngờ thật sự, mới cần hash để chắc chắn
                        content_hash = compute_sha256(content)
                        if content_hash == latest.content_hash:
                            results["unchanged"].append(doc_name)
                            continue
                    else:
                        # File mới hoàn toàn, hoặc size đã khác -> chắc chắn khác, khỏi so hash
                        # (vẫn tính hash để LƯU vào cột content_hash, không dùng để so sánh ở đây)
                        content_hash = compute_sha256(content)

                    # Unique index hiện tại là (content_hash, doc_version), KHÔNG có doc_name
                    # -> 2 file khác tên, cùng nội dung, cùng version sẽ vỡ IntegrityError ở DB
                    # -> phải tự chặn ở code trước khi insert.
                    duplicate = await self.repo.get_active_by_content_hash(
                        content_hash, exclude_lookup_hash=lookup_hash
                    )
                    if duplicate:
                        duplicate_name = decrypt_field(duplicate.doc_name, tenant_dek)
                        raise ValueError(
                            f"Nội dung trùng với document đang active '{duplicate_name}'"
                        )

                    next_version = latest.doc_version + 1 if latest else 1
                    is_new = latest is None
                    old_doc_id = None
                    if is_active_candidate:
                        old_doc_id = latest.doc_id
                        await self.repo.mark_superseded(latest)

                    doc = await self.repo.create(
                        doc_name=doc_name,
                        doc_type=ext.lstrip("."),
                        doc_version=next_version,
                        content_hash=content_hash,
                        file_size=len(content),
                        status=DocumentStatus.PENDING,
                        storage_key="",
                        dek=tenant_dek,
                    )

                    plaintext_dek, encrypted_dek_b64 = await generate_file_dek(tenant_name, doc_id=str(doc.doc_id))
                    encrypted_content = encrypt_file_bytes(content, plaintext_dek)
                    zeroize(plaintext_dek)
                    plaintext_dek = None
                    key = await save_file_to_s3(
                        tenant_name=tenant_name,
                        doc_type=ext.lstrip("."),
                        ingested_at=doc.ingested_at,
                        doc_id=str(doc.doc_id),
                        ext=ext.lstrip("."),
                        content=encrypted_content,
                    )
                    await self.repo.update_storage_key(doc.doc_id, key)
                    await self.repo.update_encrypted_file_dek(doc.doc_id, encrypted_dek_b64)
                    await self.repo.session.commit()

                    # Return plaintext doc_name for the batch result
                    item = {
                        "doc_name": doc_name,
                        "doc_id": str(doc.doc_id),
                        "doc_version": doc.doc_version,
                        "old_doc_id": str(old_doc_id) if old_doc_id else None,
                    }
                    results["updated" if not is_new else "new"].append(item)

                except Exception as e:
                    await self.repo.session.rollback()
                    results["failed"].append({"name": doc_name, "error": str(e)})
        finally:
            zeroize(tenant_dek)
            tenant_dek = None

        return results

    async def list_documents(self, tenant: Tenants | None = None) -> list[dict]:
        dek = None
        if tenant and tenant.encrypted_dek:
            dek = await get_plaintext_dek_from_blob(tenant.encrypted_dek, tenant.tenant_name)

        try:
            docs = await self.repo.list_by_tenant(dek=dek)
            return [self._to_dict(d) for d in docs]
        finally:
            if dek:
                zeroize(dek)
                dek = None

    async def list_all_tenant_documents(self, engine: AsyncEngine, session_maker: async_sessionmaker[AsyncSession]) -> list[dict]:
        async with session_maker() as session:
            result = await session.execute(
                text("SELECT tenant_name, encrypted_dek FROM public.tenants WHERE is_deleted = false")
            )
            tenants = result.fetchall()

        all_docs = []
        for row in tenants:
            tname = row[0]
            encrypted_dek = row[1]
            try:
                dek = await get_plaintext_dek_from_blob(encrypted_dek, tname) if encrypted_dek else None
            except Exception as e:
                logger.error("list_all_tenant_documents_dek_error", tenant_name=tname, error=str(e))
                dek = None

            try:
                async with get_db_with_tenant_scope_session(engine=engine, session_maker=session_maker, tenant_name=tname) as t_session:
                    t_repo = DocumentRepository(t_session)
                    try:
                        t_docs = await t_repo.list_by_tenant(dek=dek)
                        for d in t_docs:
                            doc_dict = self._to_dict(d)
                            doc_dict["tenant_name"] = tname
                            all_docs.append(doc_dict)
                    except Exception as e:
                        logger.error("list_all_tenant_documents_error", tenant_name=tname, error=str(e))
            finally:
                zeroize(tenant_dek)
                tenant_dek = None
        return all_docs

    async def delete_document(self, doc_id: uuid.UUID, collection_name: str):
        doc = await self.repo.get_by_id(doc_id)
        if not doc:
            return None
        deleted_doc = await self.repo.soft_delete(doc)

        try:
            await self.qdrant_repo.delete_by_doc_id(collection_name, str(deleted_doc.doc_id))
        except Exception:
            logger.exception("qdrant_cleanup_on_delete_failed", doc_id=str(deleted_doc.doc_id))

        return deleted_doc

    async def restore_document(
        self, doc_id: uuid.UUID, tenant_name: str, encrypted_tenant_dek: bytes
    ) -> dict | None:
        doc = await self.repo.get_by_id_any_status(doc_id)
        if doc is None:
            return None

        if not doc.is_deleted:
            result = self._to_dict(doc)
            result["old_doc_id"] = None
            return result

        tenant_dek = await get_plaintext_dek_from_blob(encrypted_tenant_dek, tenant_name)
        try:
            # doc.doc_name hiện là ciphertext -> decrypt để tính đúng lookup_hash
            plaintext_name = decrypt_field(doc.doc_name, tenant_dek)
            lookup_hash = compute_doc_name_lookup_hash(plaintext_name, tenant_dek)

            current_active = await self.repo.get_active_by_name(lookup_hash)   # SỬA
            old_doc_id = None
            if current_active is not None:
                old_doc_id = current_active.doc_id
                await self.repo.mark_superseded(current_active)

            restored = await self.repo.restore(doc)
            await self.repo.update_status(doc_id=restored.doc_id, status=DocumentStatus.PENDING)

            result = self._to_dict(restored)
            result["old_doc_id"] = str(old_doc_id) if old_doc_id else None
            return result
        finally:
            zeroize(tenant_dek)
            tenant_dek = None

    
    # @staticmethod
    # def _save_file(tenant_id: uuid.UUID, doc_id: uuid.UUID, filename: str, content: bytes) -> Path:
    #     dest = DocumentService._build_file_path(tenant_id=tenant_id, doc_id=doc_id, filename=filename)
    #     dest.parent.mkdir(parents=True, exist_ok=True)
    #     dest.write_bytes(content)
    #     return dest

    """
    Thư mục storage/documents/tenant_id
    + tenant_dir/ {doc_id}{.ext}
    trả về tên đường dẫn
    """
    # @staticmethod
    # def _build_file_path(tenant_id: uuid.UUID, doc_id: uuid.UUID ,filename: str):
    #     ext = Path(filename).suffix.lower()
    #     return STORAGE_ROOT / str(tenant_id) / f"{doc_id}{ext}"


    @staticmethod
    async def _chunk_with_full_pipeline(
        saved_path: Path,
        chunking_mode: ChunkingMode = "hybrid",
    ):
        """Use the concrete chunking and debug helpers."""
        try:
            from app.services.chunker_debug import ChunkerDebug
        except Exception as exc:
            logger.exception("chunk_pipeline_import_failed", path=str(saved_path))
            raise RuntimeError("Không thể nạp pipeline chunking cho document service") from exc

        try:
            chunks = await asyncio.to_thread(
                ChunkerService.chunking,
                str(saved_path),
                chunking_mode,
            )
            if getattr(settings, "debug", False):
                await asyncio.to_thread(ChunkerDebug.save_chunks_to_txt, chunks, str(saved_path))
            return chunks
        except Exception as exc:
            logger.exception("chunk_pipeline_failed", path=str(saved_path))
            raise RuntimeError("Chunking thất bại khi xử lý tài liệu") from exc

    async def _upsert_chunks_to_qdrant(
        self,
        *,
        collection_name: str,
        tenant_id: uuid.UUID,
        doc_id: uuid.UUID,
        doc_version: int,
        filename: str,
        chunks,
        tenant_dek: bytes,
        tracker: LatencyTracker | None = None,
    ) -> None:
        tracker = tracker or LatencyTracker("qdrant_upsert", doc_id=str(doc_id))
        try:
            from app.services.chunker_service import ChunkerService
        except Exception as exc:
            logger.exception("embedding_pipeline_import_failed", collection_name=collection_name)
            raise RuntimeError("Đục không thể nạp hàm embedding cho document service") from exc

        await self.qdrant_repo.ensure_collection_exists(collection_name)

        # Step 1: Prepare chunks and build corpus for BM25
        chunk_data = []
        corpus = []

        for i, chunk in enumerate(chunks):
            heading = ChunkerService.get_deepest_heading(chunk.metadata)
            searchable_text = "\n".join(part for part in [heading, chunk.page_content] if part).strip()
            corpus.append(searchable_text)
            chunk_data.append({
                "index": i,
                "heading": heading,
                "searchable_text": searchable_text,
                "page_content": chunk.page_content,
                "metadata": chunk.metadata,
            })

        if not corpus:
            raise RuntimeError("Đục không tạo được chunk nào để upsert vào Qdrant")

        # Biến chunk thành SparseVector
        async with tracker.astage("bm25_sparse_vectors", corpus_size=len(corpus)):
            sparse_vectors = await self.qdrant_repo.compute_bm25_sparse_vectors(corpus)

        # Biến toàn bộ corpus thành Dense vectors qua Async Mini-Batching (batch_size=32)
        async with tracker.astage("embed_dense_vectors", corpus_size=len(corpus)):
            dense_vectors = await ChunkerService.embed_batch_async(corpus, batch_size=32)

        # Step 2: Build PointStructs with dense & BM25 sparse vectors
        # Text fields to encrypt in Qdrant payload
        _TEXT_FIELDS = {"doc_name", "text", "searchable_text", "heading",
                        "source", "h1", "h2", "h3", "h4", "h5"}

        def _prepare_points() -> list[PointStruct]:
            pts: list[PointStruct] = []
            for chunk_info, sparse_vector, dense_vector in zip(chunk_data, sparse_vectors, dense_vectors, strict=False):
                raw_payload = {
                    "tenant_id": str(tenant_id),
                    "doc_id": str(doc_id),
                    "doc_name": filename,
                    "doc_version": doc_version,
                    "text": chunk_info["page_content"],
                    "searchable_text": chunk_info["searchable_text"],
                    **chunk_info["metadata"],
                    "heading": chunk_info["heading"],
                    "chunk_index": chunk_info["index"],
                }

                # Encrypt text fields; leave IDs and numeric metadata in plaintext
                payload = {
                    k: (encrypt_field(v, tenant_dek) if k in _TEXT_FIELDS and isinstance(v, str) else v)
                    for k, v in raw_payload.items()
                }

                point_id = str(uuid.uuid4())
                point = PointStruct(
                    id=point_id,
                    vector={
                        "": dense_vector,
                        self.qdrant_repo.sparse_vector_name: sparse_vector,
                    },
                    payload=payload,
                )
                pts.append(point)
            return pts

        with tracker.stage("encrypt_qdrant_payload", chunk_count=len(chunk_data)):
            points = await asyncio.to_thread(_prepare_points)

        # Step 3: Upsert points with dense + sparse vectors & payload
        async with tracker.astage("qdrant_upsert_call", point_count=len(points)):
            await self.qdrant_repo.client.upsert(
                collection_name=collection_name,
                points=points,
                wait=False,
            )

        logger.info(
            "qdrant_upsert_done",
            collection_name=collection_name,
            doc_id=str(doc_id),
            points=len(points),
        )

    @staticmethod
    def _to_dict(doc, is_duplicate: bool = False, chunk_count: int | None = None) -> dict:
        return {
            "doc_id": str(doc.doc_id),
            "doc_name": doc.doc_name,
            "doc_type": doc.doc_type,
            "doc_version": doc.doc_version,
            "version": doc.doc_version,
            "content_hash": doc.content_hash,
            "file_size": getattr(doc, "file_size", 0),
            "ingested_at": doc.ingested_at,
            "chunk_count": chunk_count,
            "is_duplicate": is_duplicate,
            "status": doc.status,
            "is_deleted": bool(getattr(doc, "is_deleted", False)),
        }

################################################################

    async def reindex_document_async(
        self, *, doc_id: uuid.UUID, tenant_id: uuid.UUID, tenant_name: str,
        collection_name: str, engine: AsyncEngine,
        session_maker: async_sessionmaker[AsyncSession],
        old_doc_id: uuid.UUID | None = None,
        encrypted_tenant_dek: bytes,
    ) -> None:
        """
        Dùng cho restore: chunk text đã có sẵn trong Postgres (không bị xóa
        lúc soft-delete), chỉ cần embed lại và upsert lại Qdrant — không cần
        đọc lại file gốc/chunk lại từ đầu.
        """
        # Resolve Tenant DEK
        tenant_dek = await get_plaintext_dek_from_blob(encrypted_tenant_dek, tenant_name)

        try:
            async with get_db_with_tenant_scope_session(engine=engine, session_maker=session_maker, tenant_name=tenant_name) as session:
                document_repo = DocumentRepository(session)
                try:
                    doc = await document_repo.get_by_id_any_status(doc_id)
                    chunk_rows = await document_repo.get_chunks_by_doc_id(doc_id, dek=tenant_dek)
                    if not chunk_rows:
                        logger.warning("reindex_no_chunks_found", doc_id=str(doc_id))
                        await document_repo.update_status(doc_id=doc_id, status=DocumentStatus.FAILED)
                        return

                    from qdrant_client.models import PointStruct
                    from app.services.chunker_service import ChunkerService

                    await self.qdrant_repo.ensure_collection_exists(collection_name)
                    chunk_contents = [row.content for row in chunk_rows]
                    dense_vectors = await ChunkerService.embed_batch_async(chunk_contents, batch_size=32)

                    points: list[PointStruct] = []
                    for row, vector in zip(chunk_rows, dense_vectors, strict=False):
                        payload = {
                            "tenant_id": str(tenant_id),
                            "doc_id": str(doc_id),
                            "doc_name": decrypt_field(doc.doc_name, tenant_dek),
                            "doc_version": doc.doc_version,
                            "text": row.content,
                            "chunk_index": row.chunk_index,
                            "section": row.section,
                        }
                        points.append(PointStruct(id=str(uuid.uuid4()), vector=vector, payload=payload))

                    # Note: the payload text fields will be encrypted inside _upsert_chunks_to_qdrant or we need to encrypt here.
                    # Actually, reindex_document_async doesn't call _upsert_chunks_to_qdrant, it upserts directly!
                    # So we must encrypt payload here.
                    for p in points:
                        for field in ["text", "doc_name", "section"]:
                            if field in p.payload and p.payload[field]:
                                p.payload[field] = encrypt_field(p.payload[field], tenant_dek)

                    await self.qdrant_repo.client.upsert(collection_name=collection_name, points=points, wait=True)
                    await document_repo.update_status(doc_id=doc_id, status=DocumentStatus.COMPLETED)
                    logger.info("document_reindexed", doc_id=str(doc_id), points=len(points))

                    # Bản active cũ bị đá xuống lúc restore (nếu có) cũng cần dọn Qdrant,
                    # giống hệt nguyên tắc supersede lúc ingest bình thường.
                    if old_doc_id:
                        try:
                            await self.qdrant_repo.delete_by_doc_id(collection_name, str(old_doc_id))
                        except Exception:
                            logger.exception("qdrant_cleanup_old_version_failed_on_restore", old_doc_id=str(old_doc_id))

                except Exception:
                    logger.exception("document_reindex_failed", doc_id=str(doc_id))
                    await document_repo.update_status(doc_id=doc_id, status=DocumentStatus.FAILED)
        finally:
            zeroize(tenant_dek)
            tenant_dek = None


    async def process_document_async_with_retry(
        self,
        *,
        chunking_mode: ChunkingMode = "hybrid",
        doc_id: uuid.UUID,
        tenant_id: uuid.UUID,
        tenant_name: str,
        collection_name: str,
        filename: str,
        doc_version: int,
        engine: AsyncEngine,
        session_maker: async_sessionmaker[AsyncSession],
        old_doc_id: uuid.UUID | None = None,
        encrypted_tenant_dek: bytes,
    ) -> None:
        """
        Wrapper cho process_document_async với retry mechanism.
        Tự động thử lại khi có lỗi tạm thời (network, timeout, etc.)
        """
        last_error = None

        for attempt in range(RETRY_CONFIG["max_attempts"]):
            try:
                await self.process_document_async(
                    chunking_mode=chunking_mode,
                    doc_id=doc_id,
                    tenant_id=tenant_id,
                    tenant_name=tenant_name,
                    collection_name=collection_name,
                    filename=filename,
                    doc_version=doc_version,
                    engine=engine,
                    session_maker=session_maker,
                    old_doc_id=old_doc_id,
                    encrypted_tenant_dek=encrypted_tenant_dek,
                )
                return  # Thành công, thoát
            except Exception as e:
                last_error = e
                is_retryable = _is_retryable_error(e)

                if is_retryable and attempt < RETRY_CONFIG["max_attempts"] - 1:
                    delay = _calculate_retry_delay(attempt)
                    logger.warning(
                        "document_process_retry",
                        doc_id=str(doc_id),
                        attempt=attempt + 1,
                        max_attempts=RETRY_CONFIG["max_attempts"],
                        delay_seconds=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)
                else:
                    # Không retryable hoặc đã hết số lần thử
                    logger.error(
                        "document_process_final_failure",
                        doc_id=str(doc_id),
                        attempts=attempt + 1,
                        error=str(e),
                    )
                    # Cập nhật status thành FAILED
                    await self._mark_document_failed(doc_id, tenant_id, tenant_name, engine, session_maker, str(e))
                    return

        # Nếu đến đây tức là đã thử hết và vẫn fail
        logger.error(
            "document_process_exhausted_retries",
            doc_id=str(doc_id),
            max_attempts=RETRY_CONFIG["max_attempts"],
            last_error=str(last_error),
        )
        await self._mark_document_failed(doc_id, tenant_id, tenant_name, engine, session_maker, str(last_error))

    async def reindex_document_async_with_retry(
        self,
        *,
        doc_id: uuid.UUID,
        tenant_id: uuid.UUID,
        tenant_name: str,
        collection_name: str,
        engine: AsyncEngine,
        session_maker: async_sessionmaker[AsyncSession],
        old_doc_id: uuid.UUID | None = None,
        encrypted_tenant_dek: bytes,
    ) -> None:
        """
        Wrapper cho reindex_document_async với retry mechanism.
        """
        last_error = None

        for attempt in range(RETRY_CONFIG["max_attempts"]):
            try:
                await self.reindex_document_async(
                    doc_id=doc_id,
                    tenant_id=tenant_id,
                    tenant_name=tenant_name,
                    collection_name=collection_name,
                    engine=engine,
                    session_maker=session_maker,
                    old_doc_id=old_doc_id,
                    encrypted_tenant_dek=encrypted_tenant_dek,
                )
                return
            except Exception as e:
                last_error = e
                is_retryable = _is_retryable_error(e)

                if is_retryable and attempt < RETRY_CONFIG["max_attempts"] - 1:
                    delay = _calculate_retry_delay(attempt)
                    logger.warning(
                        "document_reindex_retry",
                        doc_id=str(doc_id),
                        attempt=attempt + 1,
                        max_attempts=RETRY_CONFIG["max_attempts"],
                        delay_seconds=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "document_reindex_final_failure",
                        doc_id=str(doc_id),
                        attempts=attempt + 1,
                        error=str(e),
                    )
                    await self._mark_document_failed(doc_id, tenant_id, tenant_name, engine, session_maker, str(e))
                    return

        logger.error(
            "document_reindex_exhausted_retries",
            doc_id=str(doc_id),
            max_attempts=RETRY_CONFIG["max_attempts"],
            last_error=str(last_error),
        )
        await self._mark_document_failed(doc_id, tenant_id, tenant_name, engine, session_maker, str(last_error))

    async def _mark_document_failed(
        self,
        doc_id: uuid.UUID,
        tenant_id: uuid.UUID,
        tenant_name: str,
        engine: AsyncEngine,
        session_maker: async_sessionmaker[AsyncSession],
        error_message: str,
    ) -> None:
        """Đánh dấu document là FAILED trong database."""
        try:
            async with get_db_with_tenant_scope_session(
                engine=engine, session_maker=session_maker, tenant_name=tenant_name
            ) as session:
                document_repo = DocumentRepository(session)
                await document_repo.update_status(doc_id=doc_id, status=DocumentStatus.FAILED)
                await session.commit()
                logger.info("document_marked_failed", doc_id=str(doc_id), error=error_message)
        except Exception as e:
            logger.exception("failed_to_mark_document_failed", doc_id=str(doc_id), error=str(e))

    async def get_document_content(
        self, *, doc_id: uuid.UUID, tenant_id: uuid.UUID, tenant_name: str,
        encrypted_tenant_dek: bytes,
    ) -> tuple[bytes, str, str]:
        document = await self.repo.get_by_id_any_status(doc_id)
        if document is None:
            raise DocumentNotFoundError(str(doc_id))
        if document.is_deleted:
            raise DocumentNotFoundError(str(doc_id))

        tenant_dek = await get_plaintext_dek_from_blob(encrypted_tenant_dek, tenant_name)
        try:
            doc_name = decrypt_field(document.doc_name, tenant_dek)
            ext = Path(doc_name).suffix.lstrip(".").lower()

            if document.storage_key:
                raw_content = await read_file_from_s3_by_key(document.storage_key)
            else:
                legacy_key = f"{tenant_id}/{doc_id}.{ext}"
                raw_content = await read_file_from_s3_by_key(legacy_key)

            if document.encrypted_file_dek:
                plaintext_dek = await unwrap_file_dek(
                    document.encrypted_file_dek, tenant_name, doc_id=str(doc_id)
                )
                content = decrypt_file_bytes(raw_content, plaintext_dek)
                zeroize(plaintext_dek)
                plaintext_dek = None
            else:
                content = raw_content

            content_type = CONTENT_TYPE_MAP.get(ext, "application/octet-stream")
            return content, doc_name, content_type
        finally:
            zeroize(tenant_dek)
            tenant_dek = None

    async def convert_docx_to_html(self, content: bytes) -> str:
        """Hàm thuần — chỉ nhận bytes đã decrypt sẵn, không tự đi fetch/decrypt.
        Tách riêng để route tái dùng content đã có, không decrypt 2 lần.

        Normalize Unicode về NFC sau khi convert để tránh trường hợp mammoth
        trả về dạng NFD (ký tự base + combining marks tách rời) — một số
        browser/font sẽ render tách rời thành glyph lỗi, đặc biệt với tiếng
        Việt có nhiều dấu thanh phức tạp (ă, ơ, ư, đ, các dấu sắc/huyền/...).
        """
        import unicodedata

        def _convert(raw: bytes) -> str:
            result = mammoth.convert_to_html(io.BytesIO(raw))
            raw_html = result.value
            # NFC: gộp ký tự base + combining marks thành 1 codepoint duy nhất
            normalized = unicodedata.normalize("NFC", raw_html)
            return normalized
        return await asyncio.to_thread(_convert, content)


def _is_retryable_error(error: Exception) -> bool:
    """
    Kiểm tra xem lỗi có nên retry hay không.
    Retry các lỗi tạm thời (network, timeout, rate limit).
    Không retry các lỗi logic (validation, not found, etc.)
    """
    error_str = str(error).lower()

    # Các lỗi nên retry
    retryable_patterns = [
        "timeout",
        "timed out",
        "connection",
        "network",
        "temporarily unavailable",
        "service unavailable",
        "too many requests",
        "rate limit",
        "429",
        "503",
        "502",
        "504",
    ]

    for pattern in retryable_patterns:
        if pattern in error_str:
            return True

    # Các lỗi không nên retry - do logic/validation/pipeline
    non_retryable_patterns = [
        "not found",
        "does not exist",
        "invalid",
        "validation",
        "unauthorized",
        "forbidden",
        "permission denied",
        "access denied",
        "file not found",
        "no such file",
        "chunking failed",
        # Message tiếng Việt trong _chunk_with_full_pipeline: "Chunking thất bại khi xử lý tài liệu".
        # Mặc định retry trước đây match none trong 2 list -> True, làm job retry 3 lần
        # trong khi file hỏng thật — tốn resource, tăng tải Qdrant/S3 không cần thiết.
        "thất bại",
        "khi xử lý",
        "không thể nạp",
        "duplicate",
    ]

    for pattern in non_retryable_patterns:
        if pattern in error_str:
            return False

    # Mặc định: KHÔNG retry. Fail-fast an toàn hơn retry vô tội vạ vì:
    # 1. Retry 3 lần một lỗi không rõ nguyên nhân thường chỉ tốn resource,
    #    không tăng khả năng thành công.
    # 2. Status PENDING trong DB sẽ kẹt lâu hơn, block UI user.
    # 3. Có alert/log để oncall điều tra nguyên nhân.
    return False

