"""
Semantic/hybrid retrieval endpoint.

POST /v1/retrieve — Perform vector similarity search (semantic or hybrid)
                    against a tenant's Qdrant collection and return ranked
                    document chunks with configurable search strategy.
"""

from __future__ import annotations

from app.api.deps import get_retrieval_service, get_current_tenant
from fastapi import APIRouter, Depends, Query

from app.schemas.retrieve import RetrieveBody, RetrieveRequest, RetrieveResponse, SearchMode
from app.core.security import requires_roles, bearer_scheme
from app.services.retrieval_service import RetrievalService
from app.models import Tenants

router = APIRouter(
    prefix="/v1",
    tags=["Retrieval"],
    dependencies=[
        Depends(get_retrieval_service),
        Depends(get_current_tenant),
        Depends(bearer_scheme),
    ],
)


@router.post("/retrieve", response_model=RetrieveResponse)
@requires_roles("TENANT_ADMIN", "USER")
async def retrieve(
    request: RetrieveBody,
    mode: SearchMode = Query(
        default=SearchMode.SEMANTIC_WITH_RERANK,
        description="Search strategy: semantic_rerank, semantic_only, or hybrid_bm25_semantic.",
    ),
    tenant: Tenants = Depends(get_current_tenant),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
) -> dict:
    """
    Search across a tenant's document collection using configurable strategy.

    Args:
        request: Search parameters including query, mode (semantic_rerank | semantic_only | hybrid_bm25_semantic),
                thresholds, and hybrid weights.
        tenant: Current tenant (from JWT).
        retrieval_service: Retrieval service dependency.

    Returns:
        RetrieveResponse with ranked chunks, mode used, and latency breakdown.
    """
    service_request = RetrieveRequest(**request.model_dump(exclude={"mode"}), mode=mode)
    result = await retrieval_service.run_search(tenant, service_request)

    # Build response
    return {
        "query": service_request.query,
        "mode": result["mode"],
        "chunks": [
            {
                "doc_id": r["doc_id"],
                "chunk_index": r["chunk_index"],
                "content": r["content"],
                "scores": r["scores"],
                "metadata": r["metadata"],
            }
            for r in result["results"]
        ],
        "latency_ms": result["latency_ms"],
    }


@router.post("/retrieve/debug")
@requires_roles("TENANT_ADMIN", "USER")
async def retrieve_debug(
    request: RetrieveBody,
    mode: SearchMode = Query(
        default=SearchMode.QDRANT_HYBRID,
        description="Search strategy: semantic_rerank, semantic_only, hybrid_bm25_semantic, or qdrant_hybrid.",
    ),
    tenant: Tenants = Depends(get_current_tenant),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
) -> dict:
    """
    Debug endpoint for detailed trace of retrieval pipeline.

    Returns trace info with full latency breakdown, mode, and score details.
    """
    service_request = RetrieveRequest(**request.model_dump(), mode=mode)
    trace_info = await retrieval_service.get_trace(tenant, service_request)
    return {
        "query": service_request.query,
        "mode": service_request.mode,
        "trace": trace_info,
    }