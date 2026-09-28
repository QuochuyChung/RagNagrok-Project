"""
Retrieval Pydantic schemas.

Defines request/response models for the /retrieve endpoint.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SearchMode(str, Enum):
    """Search mode selector for retrieval strategy."""

    SEMANTIC_WITH_RERANK = "semantic_rerank"
    """Semantic search with lightweight reranking by heading/content presence."""

    SEMANTIC_ONLY = "semantic_only"
    """Pure semantic search without reranking."""

    HYBRID_BM25_SEMANTIC = "hybrid_bm25_semantic"
    """Hybrid search: BM25 keyword + semantic embedding, merged with weighted scores."""

    QDRANT_HYBRID = "qdrant_hybrid"
    """Hybrid search using Qdrant: BM25 keyword + semantic embedding, merged with weighted scores."""


class RetrieveBody(BaseModel):
    """HTTP request body for semantic/hybrid search query."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The search query string.",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum number of results to return.",
    )
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Optional Qdrant payload filters to narrow results.",
    )
    score_threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score threshold (0.0 – 1.0).",
    )
    hybrid_alpha: float | None = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Weight for semantic score in hybrid mode (0–1). Used only if mode=hybrid_bm25_semantic.",
    )
    hybrid_beta: float | None = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Weight for BM25 score in hybrid mode (0–1). Used only if mode=hybrid_bm25_semantic.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "query": "What is the refund policy?",
                    "top_k": 5,
                    "filters": None,
                    "score_threshold": 0.7,
                },
                {
                    "query": "refund",
                    "top_k": 10,
                    "score_threshold": 0.4,
                    "hybrid_alpha": 0.6,
                    "hybrid_beta": 0.4,
                },
            ]
        }
    }


class RetrieveRequest(RetrieveBody):
    """Internal retrieval request used by the service layer."""

    mode: SearchMode = Field(
        default=SearchMode.SEMANTIC_WITH_RERANK,
        description="Search strategy: semantic_rerank (default), semantic_only, or hybrid_bm25_semantic.",
    )


class ResultScore(BaseModel):
    """Score breakdown for a result across different scoring methods."""

    semantic: float | None = Field(
        default=None,
        description="Semantic embedding similarity score (0–1).",
    )
    bm25: float | None = Field(
        default=None,
        description="BM25 keyword match score (0–1, normalized).",
    )
    rerank_bonus: float | None = Field(
        default=None,
        description="Rerank bonus from heading/content match.",
    )
    final: float = Field(
        ...,
        description="Final combined score after all transformations (0–1).",
    )


class RetrievedChunk(BaseModel):
    """A single retrieved document chunk with multi-method scoring."""

    doc_id: str = Field(..., description="Parent document identifier.")
    chunk_index: int = Field(..., description="Zero-based chunk position in the document.")
    content: str = Field(..., description="Chunk text content.")
    scores: ResultScore = Field(..., description="Score breakdown across methods.")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional chunk metadata."
    )


class RetrieveResponse(BaseModel):
    """Response containing ranked retrieved chunks."""

    query: str = Field(..., description="The original query string.")
    mode: SearchMode = Field(..., description="Search mode used for this retrieval.")
    chunks: list[RetrievedChunk] = Field(
        ..., description="Ranked list of matching chunks, best first."
    )
    latency_ms: dict[str, float] | None = Field(
        default=None,
        description="Latency breakdown by stage (embed, search, rerank, total).",
    )
