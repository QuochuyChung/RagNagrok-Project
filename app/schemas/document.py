"""
Document Pydantic schemas.

Defines request/response models for the /documents endpoints.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    """Full document metadata returned by the API."""

    doc_id: str = Field(..., description="Unique document identifier (UUID).")
    doc_name: str = Field(..., description="Original uploaded filename.")
    doc_type: str = Field(..., description="")
    content_hash: str = Field(
        ..., description="SHA-256 hash of the document content (for idempotency)."
    )
    chunk_count: int | None = Field(
        default=None, description="Number of chunks produced after ingestion."
    )

    doc_version: int = Field(..., description="Document version counter.")

    file_size: int | None = Field(default=None, description="Document file size in bytes.")

    ingested_at: datetime = Field(..., description="UTC upload timestamp.")

    status: str = Field(..., description="Document status (PENDING, COMPLETED, FAILED).")

    is_deleted: bool = Field(
        default=False,
        description="True if document was soft-deleted and is awaiting restore.",
    )

    model_config = {"from_attributes": True}



class DocumentListResponse(BaseModel):
    """Paginated list of documents for a tenant."""

    documents: list[DocumentResponse] = Field(..., description="List of documents.")
    total: int = Field(..., description="Total number of documents for this tenant.")

class DocumentStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"