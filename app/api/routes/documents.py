"""
Document management endpoints.

POST   /v1/documents              — Upload and ingest a document.
GET    /v1/documents              — List documents for a tenant.
DELETE /v1/documents/{doc_id}     — Soft-delete a document.
POST   /v1/documents/batch       — Batch upload documents.

TODO (Sprint 3): Wire up DocumentService and DocumentRepository.
"""

from __future__ import annotations
##############################################################
import uuid
import zipfile
from typing import Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile, Request, HTTPException, Response
from pathlib import Path
from starlette.background import BackgroundTasks
from starlette.responses import JSONResponse
from urllib.parse import quote

from app.api.deps import get_current_tenant, get_document_service
from app.core.config import get_settings
from app.core.errors import FileTooLargeError, UnsupportedFileTypeError
from app.core.errors import DocumentNotFoundError
from app.models import Tenants
from app.core.security import bearer_scheme, requires_roles
from app.schemas.document import DocumentListResponse, DocumentResponse
from app.services.document_service import DocumentService
from app.utils.zip_extract import extract_zip_safely, MAX_BATCH_FILES
from app.utils.mime_detection import validate_file_content
################################################################

router = APIRouter(prefix="/v1/documents", tags=["Documents"], dependencies=[Depends(bearer_scheme)])


@router.post("", response_model=DocumentResponse)
@requires_roles("TENANT_ADMIN")
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    chunking_mode: Literal["hybrid", "recursive_only"] = Query(
        default="hybrid",
        description="Chunking strategy: hybrid or recursive_only.",
    ),
    tenant: Tenants = Depends(get_current_tenant),
    service: DocumentService = Depends(get_document_service),
):
    settings = get_settings()
    content = await file.read()

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise FileTooLargeError(settings.max_upload_size_mb)

    # Validate file content using magic bytes
    is_valid, error_msg = validate_file_content(content, file.filename)
    if not is_valid:
        raise HTTPException(422, error_msg)

    tenant_id = tenant.tenant_id
    tenant_name = tenant.tenant_name
    collection_name = tenant.collection_name
    encrypted_tenant_dek = tenant.encrypted_dek

    result = await service.ingest_document(
        tenant_id=tenant.tenant_id,
        filename=file.filename,
        content=content,
        tenant_name=tenant_name,
        encrypted_tenant_dek=encrypted_tenant_dek,
    )

    # Nếu doc giống tên nhưng nội dung khác nhau
    # => ghi đè lại và trả ra version mới
    old_doc_id = None
    if result["old_doc_id"]:
        old_doc_id = uuid.UUID(result["old_doc_id"])

    if not result["is_duplicate"]:
        background_tasks.add_task(
            service.process_document_async,
            chunking_mode=chunking_mode,
            doc_id=uuid.UUID(result["doc_id"]),
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            collection_name=collection_name,
            filename=result["doc_name"],
            doc_version=result["doc_version"],
            old_doc_id=old_doc_id,
            engine=request.app.state.db_engine,
            session_maker=request.app.state.db_sessionmaker,
            encrypted_tenant_dek=encrypted_tenant_dek,
        )

    return result


@router.get("", response_model=DocumentListResponse)
@requires_roles("TENANT_ADMIN")
async def list_documents(
    tenant: Tenants = Depends(get_current_tenant),
    service: DocumentService = Depends(get_document_service),
):
    """Lấy danh sách documents của tenant hiện tại."""
    docs = await service.list_documents(tenant=tenant)
    return DocumentListResponse(documents=docs, total=len(docs))


@router.delete("/{doc_id}")
@requires_roles("TENANT_ADMIN")
async def delete_document(
    doc_id: uuid.UUID,
    tenant: Tenants = Depends(get_current_tenant),
    service: DocumentService = Depends(get_document_service),
):
    doc = await service.delete_document(doc_id, tenant.collection_name)
    if doc is None:
        raise DocumentNotFoundError(str(doc_id))
    return {"message": "Đã xóa document", "doc_id": str(doc_id), "doc_name": doc.doc_name}


@router.post("/{doc_id}/restore")
@requires_roles("TENANT_ADMIN")
async def restore_document(
    request: Request,
    background_tasks: BackgroundTasks,
    doc_id: uuid.UUID,
    tenant: Tenants = Depends(get_current_tenant),
    service: DocumentService = Depends(get_document_service),
):
    tenant_id = tenant.tenant_id
    tenant_name = tenant.tenant_name
    collection_name = tenant.collection_name
    encrypted_tenant_dek = tenant.encrypted_dek

    doc = await service.restore_document(
        doc_id, tenant_name=tenant_name, encrypted_tenant_dek=encrypted_tenant_dek
    )
    if doc is None:
        raise DocumentNotFoundError(str(doc_id))

    background_tasks.add_task(
        service.reindex_document_async_with_retry,
        doc_id=uuid.UUID(doc["doc_id"]),
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        collection_name=collection_name,
        old_doc_id=uuid.UUID(doc["old_doc_id"]) if doc["old_doc_id"] else None,
        engine=request.app.state.db_engine,
        session_maker=request.app.state.db_sessionmaker,
        encrypted_tenant_dek=encrypted_tenant_dek,
    )
    return doc


@router.post("/batch")
@requires_roles("TENANT_ADMIN")
async def upload_documents_batch(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    tenant: Tenants = Depends(get_current_tenant),
    service: DocumentService = Depends(get_document_service),
):
    settings = get_settings()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024

    # Chụp lại các field cần dùng SAU khi ingest_batch chạy xong (nhiều commit
    # bên trong sẽ expire object `tenant` -> truy cập lại field sau đó gây
    # MissingGreenlet). Lưu ra biến local NGAY BÂY GIỜ, trước khi gọi service.
    tenant_id = tenant.tenant_id
    tenant_name = tenant.tenant_name
    collection_name = tenant.collection_name
    encrypted_tenant_dek = tenant.encrypted_dek

    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(413, f"Batch quá {MAX_BATCH_FILES} file")

    # Xử lý zip: extract zip trước khi xử lý batch
    # Cho phép upload nhiều file có chứa zip bên trong
    raw_items = []
    zip_files = []
    other_files = []

    for f in files:
        if Path(f.filename).suffix.lower() == ".zip":
            zip_files.append(f)
        else:
            other_files.append(f)

    # Extract tất cả zip
    for zf in zip_files:
        content = await zf.read()
        try:
            extracted = extract_zip_safely(content)

            # 🔒 VALIDATE SIZE CỦA TỪNG FILE TRONG ZIP
            for filename, file_content in extracted:
                if len(file_content) > max_bytes:
                    raise HTTPException(
                        422,
                        f"File '{filename}' trong {zf.filename} vượt quá {settings.max_upload_size_mb}MB"
                    )
                # 🔒 VALIDATE MIME TYPE CỦA TỪNG FILE
                is_valid, error_msg = validate_file_content(file_content, filename)
                if not is_valid:
                    raise HTTPException(422, f"File '{filename}' trong {zf.filename}: {error_msg}")

            raw_items.extend(extracted)
        except (zipfile.BadZipFile, ValueError) as e:
            raise HTTPException(422, f"File {zf.filename}: {str(e)}")

    # Thêm các file không phải zip
    for f in other_files:
        content = await f.read()
        # 🔒 VALIDATE SIZE
        if len(content) > max_bytes:
            raise HTTPException(
                422,
                f"File '{f.filename}' vượt quá {settings.max_upload_size_mb}MB"
            )
        # 🔒 VALIDATE MIME TYPE
        is_valid, error_msg = validate_file_content(content, f.filename)
        if not is_valid:
            raise HTTPException(422, f"File '{f.filename}': {error_msg}")

        raw_items.append((f.filename, content))

    if len(raw_items) > MAX_BATCH_FILES:
        raise HTTPException(413, f"Batch quá {MAX_BATCH_FILES} file")

    result = await service.ingest_batch(
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        files=raw_items,
        encrypted_tenant_dek=encrypted_tenant_dek,
    )

    for status in ("new", "updated"):
        for item in result[status]:
            background_tasks.add_task(
                service.process_document_async,
                chunking_mode="hybrid",
                doc_id=uuid.UUID(item["doc_id"]),
                tenant_id=tenant_id,
                tenant_name=tenant_name,
                collection_name=collection_name,
                filename=item["doc_name"],
                doc_version=item["doc_version"],
                old_doc_id=uuid.UUID(item["old_doc_id"]) if item["old_doc_id"] else None,
                engine=request.app.state.db_engine,
                session_maker=request.app.state.db_sessionmaker,
                encrypted_tenant_dek=encrypted_tenant_dek,
            )

    return result

@router.get("/{doc_id}/content")
@requires_roles("TENANT_ADMIN")
async def get_document_content_route(
    doc_id: uuid.UUID,
    disposition: Literal["inline", "attachment"] = Query(default="inline"),
    tenant: Tenants = Depends(get_current_tenant),
    service: DocumentService = Depends(get_document_service),
):
    tenant_id = tenant.tenant_id
    tenant_name = tenant.tenant_name
    encrypted_tenant_dek = tenant.encrypted_dek

    try:
        content, filename, content_type = await service.get_document_content(
            doc_id=doc_id, tenant_id=tenant_id, tenant_name=tenant_name, encrypted_tenant_dek=encrypted_tenant_dek,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))

    ext = Path(filename).suffix.lower()

    # Nhánh riêng: preview docx -> HTML thay vì raw bytes
    if disposition == "inline" and ext == ".docx":
        html = await service.convert_docx_to_html(content)
        return JSONResponse({"html": html})

    # Mọi trường hợp còn lại (pdf/md/txt inline, hoặc download bất kỳ ext nào) -> raw bytes
    safe_filename = quote(filename)
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": (
                f'{disposition}; filename="{filename}"; '
                f"filename*=UTF-8''{safe_filename}"
            )
        },
    )
