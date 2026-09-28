"""
Retrieval service.

Builds and executes semantic search queries against Qdrant.
Provides debug trace and latency breakdown for monitoring.

TODO (Sprint 3): Implement retrieval pipeline.
"""

from __future__ import annotations

import asyncio
from time import perf_counter
import unicodedata
from typing import Any

from app.models.tenant import Tenants
from app.repositories.qdrant_repository import QdrantRepository
from app.services.chunker_service import ChunkerService
from app.schemas.retrieve import RetrieveRequest, SearchMode
from app.core.logging import get_logger
from app.core.tenant_dek_provider import get_plaintext_dek
from app.utils.field_cipher import decrypt_field
from app.utils.hashing import zeroize

logger = get_logger(__name__)


class RetrievalService:
    """Business logic layer for semantic retrieval."""
    
    def __init__(self, qdrant_repository: QdrantRepository, embedding_client: ChunkerService) -> None:
        self.qdrant_repository = qdrant_repository
        self.embedding_client = embedding_client

    @staticmethod
    def _normalize_query_text(query: str) -> str:
        """Normalize query text to match ingestion Unicode canonical form."""
        return unicodedata.normalize("NFC", query)
    
    # Hàm embedding query text
    async def embed_query(self, query: str) -> list[float]:
        """Embed the query text using the embedding client."""
        normalized_query = self._normalize_query_text(query)
        embedding = await self.embedding_client.embed_text_async(normalized_query)
        return embedding
    
    # Hàm truy vấn Qdrant với embedding theo semantic search, top_k = 3
    async def search(self, tenant: Tenants, query: str, top_k: int = 3) -> list[dict]:
        """Perform semantic search in Qdrant using the embedded query."""
        embedding = await self.embed_query(query)
        results = await self.qdrant_repository.search(tenant.tenant_id, tenant.collection_name, embedding, top_k)
        return results

    # --- Public Dispatcher Method ---
    async def run_search(
        self,
        tenant: Tenants,
        request: RetrieveRequest,
    ) -> dict[str, Any]:
        """
        Main search dispatcher — routes to appropriate strategy based on request.mode.

        Resolves the Tenant DEK once here before delegating to strategy methods,
        so that each strategy can decrypt Qdrant payload fields transparently.

        The plaintext DEK is always zeroized in the finally block (including
        error paths) so the key does not linger in memory after the request.
        """
        # Resolve Tenant DEK for Qdrant payload decryption
        tenant_dek = await get_plaintext_dek(tenant)
        try:
            if request.mode == SearchMode.SEMANTIC_WITH_RERANK:
                return await self._run_semantic_rerank(tenant, request, tenant_dek)
            elif request.mode == SearchMode.SEMANTIC_ONLY:
                return await self._run_semantic_only(tenant, request, tenant_dek)
            elif request.mode == SearchMode.HYBRID_BM25_SEMANTIC:
                return await self._run_hybrid_bm25_semantic(tenant, request, tenant_dek)
            elif request.mode == SearchMode.QDRANT_HYBRID:
                return await self._run_qdrant_hybrid(tenant, request, tenant_dek)
            else:
                raise ValueError(f"Unknown search mode: {request.mode}")
        finally:
            zeroize(tenant_dek)
            tenant_dek = None

    # --- Strategy Methods ---
    async def _run_semantic_rerank(
        self,
        tenant: Tenants,
        request: RetrieveRequest,
        tenant_dek: bytes,
    ) -> dict[str, Any]:
        """Semantic search with rerank strategy."""
        total_start = perf_counter()

        embed_start = perf_counter()
        embedding = await self.embed_query(request.query)
        embed_latency_ms = (perf_counter() - embed_start) * 1000

        search_start = perf_counter()
        candidate_limit = max(request.top_k * 3, request.top_k)
        results = await self.qdrant_repository.search(
            tenant.tenant_id,
            tenant.collection_name,
            embedding,
            candidate_limit,
        )

        reranked_results = self._rerank_results(request.query, results)
        filtered_results = self._filter_by_final_score(
            request.query, reranked_results, request.score_threshold
        )
        top_results = filtered_results[: request.top_k]
        search_latency_ms = (perf_counter() - search_start) * 1000

        return {
            "mode": SearchMode.SEMANTIC_WITH_RERANK,
            "results": [self._serialize_result_point(r, request.query, tenant_dek) for r in top_results],
            "result_count": len(top_results),
            "latency_ms": {
                "embed": round(embed_latency_ms, 3),
                "search": round(search_latency_ms, 3),
                "total": round((perf_counter() - total_start) * 1000, 3),
            },
        }

    async def _run_semantic_only(
        self,
        tenant: Tenants,
        request: RetrieveRequest,
        tenant_dek: bytes,
    ) -> dict[str, Any]:
        """Pure semantic search without reranking."""
        total_start = perf_counter()

        embed_start = perf_counter()
        embedding = await self.embed_query(request.query)
        embed_latency_ms = (perf_counter() - embed_start) * 1000

        search_start = perf_counter()
        results = await self.qdrant_repository.search(
            tenant.tenant_id,
            tenant.collection_name,
            embedding,
            request.top_k,
        )

        filtered_results = self._apply_score_threshold(results, request.score_threshold)
        top_results = filtered_results[: request.top_k]
        search_latency_ms = (perf_counter() - search_start) * 1000

        return {
            "mode": SearchMode.SEMANTIC_ONLY,
            "results": [self._serialize_result_point_simple(r, tenant_dek) for r in top_results],
            "result_count": len(top_results),
            "latency_ms": {
                "embed": round(embed_latency_ms, 3),
                "search": round(search_latency_ms, 3),
                "total": round((perf_counter() - total_start) * 1000, 3),
            },
        }

    async def _run_hybrid_bm25_semantic(
        self,
        tenant: Tenants,
        request: RetrieveRequest,
        tenant_dek: bytes,
    ) -> dict[str, Any]:
        """Hybrid BM25 + semantic search with score fusion."""
        total_start = perf_counter()

        embed_start = perf_counter()
        embedding = await self.embed_query(request.query)
        embed_latency_ms = (perf_counter() - embed_start) * 1000

        search_start = perf_counter()
        candidate_limit = max(request.top_k * 2, request.top_k)

        semantic_results, bm25_results = await asyncio.gather(
            self.qdrant_repository.search(
                tenant.tenant_id,
                tenant.collection_name,
                embedding,
                candidate_limit,
            ),
            self.qdrant_repository.search_bm25(
                tenant.tenant_id,
                tenant.collection_name,
                request.query,
                candidate_limit,
            ),
        )

        merged = self._merge_hybrid_results(
            semantic_results,
            bm25_results,
            alpha=request.hybrid_alpha or 0.7,
            beta=request.hybrid_beta or 0.3,
        )

        filtered_results = self._apply_score_threshold(merged, request.score_threshold)
        top_results = filtered_results[: request.top_k]
        search_latency_ms = (perf_counter() - search_start) * 1000

        return {
            "mode": SearchMode.HYBRID_BM25_SEMANTIC,
            "results": [self._serialize_result_point_hybrid(r, tenant_dek) for r in top_results],
            "result_count": len(top_results),
            "latency_ms": {
                "embed": round(embed_latency_ms, 3),
                "search": round(search_latency_ms, 3),
                "total": round((perf_counter() - total_start) * 1000, 3),
            },
        }

    async def _run_qdrant_hybrid(
        self,
        tenant: Tenants,
        request: RetrieveRequest,
        tenant_dek: bytes,
    ) -> dict[str, Any]:
        """Hybrid search using Qdrant's built-in hybrid capabilities."""
        total_start = perf_counter()

        embed_start = perf_counter()
        embedding = await self.embed_query(request.query)
        sparse_vector = self.qdrant_repository.build_bm25_query_sparse_vector(request.query)
        embed_latency_ms = (perf_counter() - embed_start) * 1000

        search_start = perf_counter()
        candidate_limit = max(request.top_k * 2, request.top_k)

        hybrid_results = await self.qdrant_repository.qdrant_hybrid_search(
            tenant.tenant_id,
            tenant.collection_name,
            embedding,
            sparse_vector,
            top_k=candidate_limit
        )

        filtered_results = self._apply_score_threshold(hybrid_results, request.score_threshold)
        top_results = filtered_results[: request.top_k]
        search_latency_ms = (perf_counter() - search_start) * 1000

        return {
            "mode": SearchMode.QDRANT_HYBRID,
            "results": [self._serialize_result_point_qdrant_hybrid(r, tenant_dek) for r in top_results],
            "result_count": len(top_results),
            "latency_ms": {
                "embed": round(embed_latency_ms, 3),
                "search": round(search_latency_ms, 3),
                "total": round((perf_counter() - total_start) * 1000, 3),
            },
        }

    @staticmethod
    def _apply_score_threshold(results: list[Any], score_threshold: float | None) -> list[Any]:
        """Filter out results below the configured similarity threshold."""
        if score_threshold is None:
            return results
        return [result for result in results if getattr(result, "score", None) is not None and result.score >= score_threshold]

    @staticmethod
    def _tokenize_query(query: str) -> list[str]:
        """Tokenize the query into light-weight matching terms for reranking."""
        tokens = []
        for token in query.lower().split():
            cleaned = "".join(char for char in token if char.isalnum() or char in {"_", "-"})
            if len(cleaned) >= 3:
                tokens.append(cleaned)
        return tokens

    @staticmethod
    def _calculate_rerank_bonus(query: str, payload: dict[str, Any]) -> float:
        """Assign a small bonus when query terms appear in heading or content."""
        normalized_query = query.lower().strip()
        heading = str(payload.get("heading", "")).lower()
        content = str(payload.get("text", "")).lower()
        searchable_text = str(payload.get("searchable_text", "")).lower()
        tokens = RetrievalService._tokenize_query(normalized_query)

        bonus = 0.0
        if normalized_query and normalized_query in heading:
            bonus += 0.08
        if normalized_query and normalized_query in content:
            bonus += 0.06
        if normalized_query and normalized_query in searchable_text:
            bonus += 0.03

        heading_hits = sum(1 for token in tokens if token in heading)
        content_hits = sum(1 for token in tokens if token in content)
        searchable_hits = sum(1 for token in tokens if token in searchable_text)

        # Keep rerank lightweight so semantic score stays dominant.
        bonus += min(0.06, heading_hits * 0.006)
        bonus += min(0.04, content_hits * 0.004)
        bonus += min(0.03, searchable_hits * 0.002)
        return bonus

    @staticmethod
    def _compute_final_score(original_score: float, rerank_bonus: float) -> float:
        """Compute final score after rerank and clamp to [0, 1]."""
        return max(0.0, min(1.0, original_score + rerank_bonus))

    @classmethod
    def _rerank_results(cls, query: str, results: list[Any]) -> list[Any]:
        """Rerank results slightly by heading/content presence while preserving semantic score."""
        scored_results = []
        for result in results:
            payload = getattr(result, "payload", {}) or {}
            bonus = cls._calculate_rerank_bonus(query, payload)
            original_score = getattr(result, "score", 0.0) or 0.0
            final_score = cls._compute_final_score(original_score, bonus)
            scored_results.append((final_score, bonus, result))

        scored_results.sort(key=lambda item: (item[0], item[1], getattr(item[2], "score", 0.0) or 0.0), reverse=True)
        return [item[2] for item in scored_results]

    @classmethod
    def _filter_by_final_score(
        cls,
        query: str,
        results: list[Any],
        score_threshold: float | None,
    ) -> list[Any]:
        """Filter reranked results by threshold against final_score (not raw score)."""
        if score_threshold is None:
            return results

        kept: list[Any] = []
        for result in results:
            payload = getattr(result, "payload", {}) or {}
            bonus = cls._calculate_rerank_bonus(query, payload)
            original_score = getattr(result, "score", 0.0) or 0.0
            final_score = cls._compute_final_score(original_score, bonus)
            if final_score >= score_threshold:
                kept.append(result)
        return kept

    async def search_with_threshold(
        self,
        tenant: Tenants,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.4,
    ) -> list[Any]:
        """Perform search then apply rerank/final-score threshold, and keep top_k by final_score."""
        embedding = await self.embed_query(query)
        # Pull a wider candidate pool so rerank can reorder before final top_k cut.
        candidate_limit = max(top_k * 3, top_k)
        results = await self.qdrant_repository.search(
            tenant.tenant_id,
            tenant.collection_name,
            embedding,
            candidate_limit,
        )
        reranked_results = self._rerank_results(query, results)
        filtered_results = self._filter_by_final_score(query, reranked_results, score_threshold)
        return filtered_results[:top_k]

    # --- Hybrid Search Helpers ---
    @staticmethod
    def _normalize_score(score: float) -> float:
        """Normalize score to [0, 1] range."""
        return max(0.0, min(1.0, score))

    @staticmethod
    def _merge_hybrid_results(
        semantic_results: list[Any],
        bm25_results: list[Any],
        alpha: float = 0.7,
        beta: float = 0.3,
    ) -> list[Any]:
        """
        Merge semantic and BM25 results using weighted score fusion.

        Args:
            semantic_results: Dense vector search results with `.score` attr.
            bm25_results: Sparse BM25 keyword search results with `.score` attr.
            alpha: Weight for semantic score (default 0.7).
            beta: Weight for BM25 score (default 0.3).

        Returns:
            Merged and deduplicated results, sorted by final score.
        """
        # Build score maps
        semantic_map = {
            getattr(r, "id", None): RetrievalService._normalize_score(getattr(r, "score", 0.0) or 0.0)
            for r in semantic_results
        }
        bm25_map = {
            getattr(r, "id", None): RetrievalService._normalize_score(getattr(r, "score", 0.0) or 0.0)
            for r in bm25_results
        }

        # Merge with fusion
        merged_map = {}
        all_ids = set(semantic_map.keys()) | set(bm25_map.keys())

        for result_id in all_ids:
            semantic_score = semantic_map.get(result_id, 0.0)
            bm25_score = bm25_map.get(result_id, 0.0)
            fused_score = alpha * semantic_score + beta * bm25_score
            merged_map[result_id] = {
                "id": result_id,
                "semantic": semantic_score,
                "bm25": bm25_score,
                "fused": RetrievalService._normalize_score(fused_score),
            }

        # Rebuild result objects with fused scores
        merged_results = []
        for result_id in sorted(merged_map.keys(), key=lambda rid: merged_map[rid]["fused"], reverse=True):
            # Get original result object and override score
            orig_result = next(
                (r for r in semantic_results if getattr(r, "id", None) == result_id),
                next((r for r in bm25_results if getattr(r, "id", None) == result_id), None),
            )
            if orig_result:
                # Store scores in payload for serialization
                orig_result._hybrid_scores = merged_map[result_id]
                orig_result.score = merged_map[result_id]["fused"]
                merged_results.append(orig_result)

        return merged_results

    @staticmethod
    def _serialize_result_point(result: Any, query: str | None = None, tenant_dek: bytes | None = None) -> dict[str, Any]:
        """Serialize Qdrant scored point, decrypting payload text fields if dek is provided."""
        payload = getattr(result, "payload", {}) or {}

        # Decrypt encrypted text fields before serialization
        if tenant_dek:
            for field in ("text", "doc_name", "heading", "searchable_text", "source",
                          "h1", "h2", "h3", "h4", "h5"):
                if field in payload and isinstance(payload[field], str):
                    payload[field] = decrypt_field(payload[field], tenant_dek)

        system_keys = {"doc_id", "chunk_index", "text"}
        metadata = {k: v for k, v in payload.items() if k not in system_keys}
        rerank_bonus = RetrievalService._calculate_rerank_bonus(query or "", payload) if query else 0.0
        original_score = getattr(result, "score", None)
        final_score = RetrievalService._compute_final_score((original_score or 0.0), rerank_bonus)
        return {
            "id": str(getattr(result, "id", "")),
            "scores":{
                "semantic": round(original_score, 4) if original_score else 0.0,
                "bm25": None,
                "rerank_bonus": round(rerank_bonus, 4),
                "final": round(final_score, 4) if final_score else 0.0,
            },
            "doc_id": payload.get("doc_id", ""),
            "chunk_index": payload.get("chunk_index", -1),
            "content": payload.get("text", ""),
            "metadata": metadata,
        }

    @staticmethod
    def _serialize_result_point_simple(result: Any, tenant_dek: bytes | None = None) -> dict[str, Any]:
        """Serialize Qdrant point for semantic_only mode, decrypting text fields."""
        payload = getattr(result, "payload", {}) or {}

        if tenant_dek:
            for field in ("text", "doc_name", "heading", "searchable_text", "source",
                          "h1", "h2", "h3", "h4", "h5"):
                if field in payload and isinstance(payload[field], str):
                    payload[field] = decrypt_field(payload[field], tenant_dek)

        system_keys = {"doc_id", "chunk_index", "text"}
        metadata = {k: v for k, v in payload.items() if k not in system_keys}
        original_score = getattr(result, "score", None)
        return {
            "id": str(getattr(result, "id", "")),
            "scores": {
                "semantic": round(original_score, 4) if original_score else 0.0,
                "bm25": None,
                "rerank_bonus": None,
                "final": round(original_score, 4) if original_score else 0.0,
            },
            "doc_id": payload.get("doc_id", ""),
            "chunk_index": payload.get("chunk_index", -1),
            "content": payload.get("text", ""),
            "metadata": metadata,
        }

    @staticmethod
    def _serialize_result_point_hybrid(result: Any, tenant_dek: bytes | None = None) -> dict[str, Any]:
        """Serialize Qdrant point for hybrid_bm25_semantic mode, decrypting text fields."""
        payload = getattr(result, "payload", {}) or {}

        if tenant_dek:
            for field in ("text", "doc_name", "heading", "searchable_text", "source",
                          "h1", "h2", "h3", "h4", "h5"):
                if field in payload and isinstance(payload[field], str):
                    payload[field] = decrypt_field(payload[field], tenant_dek)

        system_keys = {"doc_id", "chunk_index", "text"}
        metadata = {k: v for k, v in payload.items() if k not in system_keys}
        hybrid_scores = getattr(result, "_hybrid_scores", None)

        if hybrid_scores:
            scores = {
                "semantic": round(hybrid_scores["semantic"], 4),
                "bm25": round(hybrid_scores["bm25"], 4),
                "rerank_bonus": None,
                "final": round(hybrid_scores["fused"], 4),
            }
        else:
            final_score = getattr(result, "score", 0.0) or 0.0
            scores = {
                "semantic": None,
                "bm25": None,
                "rerank_bonus": None,
                "final": round(final_score, 4),
            }

        return {
            "id": str(getattr(result, "id", "")),
            "scores": scores,
            "doc_id": payload.get("doc_id", ""),
            "chunk_index": payload.get("chunk_index", -1),
            "content": payload.get("text", ""),
            "metadata": metadata,
        }
    @staticmethod
    def _serialize_result_point_qdrant_hybrid(result: Any, tenant_dek: bytes | None = None) -> dict[str, Any]:
        """Serialize Qdrant point for qdrant_hybrid mode, decrypting text fields."""
        payload = getattr(result, "payload", {}) or {}

        if tenant_dek:
            for field in ("text", "doc_name", "heading", "searchable_text", "source",
                          "h1", "h2", "h3", "h4", "h5"):
                if field in payload and isinstance(payload[field], str):
                    payload[field] = decrypt_field(payload[field], tenant_dek)

        system_keys = {"doc_id", "chunk_index", "text"}
        metadata = {k: v for k, v in payload.items() if k not in system_keys}
        original_score = getattr(result, "score", None)
        return {
            "id": str(getattr(result, "id", "")),
            "scores": {
                "semantic": None,
                "bm25": None,
                "rerank_bonus": None,
                "final": round(original_score, 4) if original_score else 0.0,
            },
            "doc_id": payload.get("doc_id", ""),
            "chunk_index": payload.get("chunk_index", -1),
            "content": payload.get("text", ""),
            "metadata": metadata,
        }
    
    # Hàm trả về trace và latency breakdown cho việc truy vấn
    async def get_trace(
        self,
        tenant: Tenants,
        request: RetrieveRequest,
    ) -> dict[str, Any]:
        """Get debug trace and latency breakdown for the search query."""
        normalized_query = self._normalize_query_text(request.query)

        total_start = perf_counter()

        embed_start = perf_counter()
        embedding = await self.embedding_client.embed_text_async(normalized_query)
        embed_latency_ms = (perf_counter() - embed_start) * 1000

        search_start = perf_counter()
        trace_data: dict[str, Any]

        if request.mode == SearchMode.SEMANTIC_WITH_RERANK:
            candidate_limit = max(request.top_k * 3, request.top_k)
            results = await self.qdrant_repository.search(
                tenant.tenant_id,
                tenant.collection_name,
                embedding,
                candidate_limit,
            )
            reranked_results = self._rerank_results(request.query, results)
            filtered_results = self._filter_by_final_score(
                request.query,
                reranked_results,
                request.score_threshold,
            )
            top_results = filtered_results[: request.top_k]
            trace_data = {
                "result_count": len(results),
                "filtered_result_count": len(filtered_results),
                "reranked_result_count": len(reranked_results),
                "top_result_count": len(top_results),
                "results": [self._serialize_result_point(result, request.query) for result in results],
                "filtered_results": [self._serialize_result_point(result, request.query) for result in filtered_results],
                "reranked_results": [self._serialize_result_point(result, request.query) for result in reranked_results],
                "top_results": [self._serialize_result_point(result, request.query) for result in top_results],
            }
        elif request.mode == SearchMode.SEMANTIC_ONLY:
            results = await self.qdrant_repository.search(
                tenant.tenant_id,
                tenant.collection_name,
                embedding,
                request.top_k,
            )
            filtered_results = self._apply_score_threshold(results, request.score_threshold)
            top_results = filtered_results[: request.top_k]
            trace_data = {
                "result_count": len(results),
                "filtered_result_count": len(filtered_results),
                "reranked_result_count": len(filtered_results),
                "top_result_count": len(top_results),
                "results": [self._serialize_result_point_simple(result) for result in results],
                "filtered_results": [self._serialize_result_point_simple(result) for result in filtered_results],
                "reranked_results": [self._serialize_result_point_simple(result) for result in filtered_results],
                "top_results": [self._serialize_result_point_simple(result) for result in top_results],
            }
        elif request.mode == SearchMode.HYBRID_BM25_SEMANTIC:
            candidate_limit = max(request.top_k * 2, request.top_k)
            semantic_results, bm25_results = await asyncio.gather(
                self.qdrant_repository.search(
                    tenant.tenant_id,
                    tenant.collection_name,
                    embedding,
                    candidate_limit,
                ),
                self.qdrant_repository.search_bm25(
                    tenant.tenant_id,
                    tenant.collection_name,
                    request.query,
                    candidate_limit,
                ),
            )
            merged_results = self._merge_hybrid_results(
                semantic_results,
                bm25_results,
                alpha=request.hybrid_alpha or 0.7,
                beta=request.hybrid_beta or 0.3,
            )
            filtered_results = self._apply_score_threshold(merged_results, request.score_threshold)
            top_results = filtered_results[: request.top_k]
            trace_data = {
                "result_count": len(merged_results),
                "filtered_result_count": len(filtered_results),
                "reranked_result_count": len(merged_results),
                "top_result_count": len(top_results),
                "semantic_results": [self._serialize_result_point_simple(result) for result in semantic_results],
                "bm25_results": [self._serialize_result_point_simple(result) for result in bm25_results],
                "results": [self._serialize_result_point_hybrid(result) for result in merged_results],
                "filtered_results": [self._serialize_result_point_hybrid(result) for result in filtered_results],
                "reranked_results": [self._serialize_result_point_hybrid(result) for result in merged_results],
                "top_results": [self._serialize_result_point_hybrid(result) for result in top_results],
            }

        elif request.mode == SearchMode.QDRANT_HYBRID:
            candidate_limit = max(request.top_k * 2, request.top_k)
            sparse_vector = self.qdrant_repository.build_bm25_query_sparse_vector(request.query)
            hybrid_results = await self.qdrant_repository.qdrant_hybrid_search(
                tenant.tenant_id,
                tenant.collection_name,
                embedding,
                sparse_vector,
                top_k=candidate_limit
            )
            filtered_results = self._apply_score_threshold(hybrid_results, request.score_threshold)
            top_results = filtered_results[: request.top_k]
            trace_data = {
                "result_count": len(hybrid_results),
                "filtered_result_count": len(filtered_results),
                "reranked_result_count": len(hybrid_results),
                "top_result_count": len(top_results),
                "results": [self._serialize_result_point_qdrant_hybrid(result) for result in hybrid_results],
                "filtered_results": [self._serialize_result_point_qdrant_hybrid(result) for result in filtered_results],
                "reranked_results": [self._serialize_result_point_qdrant_hybrid(result) for result in hybrid_results],
                "top_results": [self._serialize_result_point_qdrant_hybrid(result) for result in top_results],
            }

        else:
            raise ValueError(f"Unknown search mode: {request.mode}")

        search_latency_ms = (perf_counter() - search_start) * 1000
        total_latency_ms = (perf_counter() - total_start) * 1000

        return {
            "mode": request.mode,
            "tenant_id": str(tenant.tenant_id),
            "collection_name": tenant.collection_name,
            "query": request.query,
            "normalized_query": normalized_query,
            "top_k": request.top_k,
            "filters": request.filters,
            "score_threshold": request.score_threshold,
            "embedding_dimension": len(embedding),
            "embedding_preview": embedding[:8],
            "latency_ms": {
                "embed": round(embed_latency_ms, 3),
                "search": round(search_latency_ms, 3),
                "total": round(total_latency_ms, 3),
            },
            **trace_data,
        }