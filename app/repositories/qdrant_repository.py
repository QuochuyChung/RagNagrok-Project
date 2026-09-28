"""
Qdrant repository.

Data access layer for Qdrant vector database operations.
Builds and executes queries specific to Qdrant (upsert, search, filter).
Has no knowledge of business domain beyond what is needed to formulate queries.

TODO (Sprint 3): Implement Qdrant client integration.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import re
from qdrant_client import models
from app.core.logging import get_logger

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams, Filter, FieldCondition, MatchValue, SparseVector, SparseVectorParams, FusionQuery
from qdrant_client.http.exceptions import UnexpectedResponse
from underthesea import word_tokenize, ner

logger = get_logger(__name__)


class QdrantRepository:
    """Qdrant data access — upsert, search, and filter operations."""

    # TODO (Sprint 3): inject qdrant_client
    def __init__(self, client: AsyncQdrantClient, vector_size: int = 1024):
        self.client = client
        self.vector_size = vector_size # Lấy từ file config/environment
        # Khuyên dùng Cosine cho các bài toán Text Search
        self.distance_metric = Distance.COSINE
        # BM25 sparse vector index name
        self.sparse_vector_name = "bm25"
        self.bm25_k1 = 1.5
        self.bm25_b = 0.75
        self.bm25_avg_len = 256

    # --- BM25 Sparse Vector Helpers ---
    @staticmethod
    def _tokenize_bm25(text: str) -> list[str]:
        """
            Hàm này xài lúc upload
            Mục đích: để cắt các chunks ra thành list từ

            Input:
                chunk 0: "docker compose setup"
                chunk 1: "docker network config"
                chunk 2: "python api gateway"
            Output:
                ["docker","compose","setup"]  ["docker","network","config"]  ["python","api","gateway"]
        """
        """Tokenize text for BM25: lowercase and word tokenize."""
        tokens = word_tokenize(text.lower())
        return tokens

    @staticmethod
    def _token_to_sparse_index(token: str) -> int:
        """Map a token to a stable sparse-vector dimension."""
        """
            Helper dùng để chuyển token từ chữ sang số
              "docker"  → blake2b hash → 1823                                                                                                                                     
              "compose" → blake2b hash → 4521
              "setup"   → blake2b hash → 7102 
        """
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
        return int.from_bytes(digest, byteorder="big", signed=False)

    @staticmethod
    def _weights_to_sparse_vector(weights: dict[int, float]) -> SparseVector:
        """Convert weighted token dimensions to Qdrant sparse-vector format."""
        """
            Helper chuyển dict weights → SparseVector theo format Qdrant yêu cầu.
            
            # Input                                                                                                                                                             
            weights = {
                4521: 1.09, 
                1823: 0.28, 
                7102: 1.09
            }
                                                                                                                                                                                  
            # sorted theo index tăng dần
            sorted_pairs = [(1823, 0.28), (4521, 1.09), (7102, 1.09)]
            
            # Output
            SparseVector(
                  indices=[1823, 4521, 7102],
                  values=[0.28, 1.09, 1.09]
            )
        """
        if not weights:
            return SparseVector(indices=[], values=[])

        sorted_pairs = sorted(weights.items(), key=lambda item: item[0])
        return SparseVector(
            indices=[index for index, _ in sorted_pairs],
            values=[value for _, value in sorted_pairs],
        )

    @staticmethod
    def _apply_ner_boost(tokens: list[str]) -> dict[str, float]:
        try:
            entities = ner(" ".join(tokens))
            boost = {}
            for entity in entities:
                if len(entity) >= 2:
                    word = entity[0]
                    label = entity[-1]  # NER tag is typically the last element
                    if any(target in label for target in ["PER", "LOC", "ORG"]):
                        boost[word] = 1.5
            return boost
        except Exception as exc:
            logger.error("[qdrant-repository - ner] ner boost error ")
            raise Exception("ner boost error with error") from exc
    """
        Đã xóa hàm _build_bm25_index hàm này chủ yếu để lấy idf thống kê nhưng hiện tại bây giờ đã chuyển qua cho qdrant làm
    """

    def _build_document_sparse_vector(
        self,
        *,
        tokens: list[str],
    ) -> SparseVector:
        """
            Hàm này dùng lúc upload
            => Dùng để trả ra SparseVector, nhận vào từng chunk lẻ để biến chunk thành SparseVector
            Input:
                bm25 {
                    bm25.corpus_size = 3          # tổng số chunk
                    bm25.avgdl = 3.0              # độ dài trung bình mỗi chunk (3 token/chunk)
                    bm25.idf = {
                          "docker": 0.28,           # xuất hiện 2/3 chunk → IDF thấp
                          "compose": 1.09,          # xuất hiện 1/3 chunk → IDF cao hơn
                          "setup": 1.09,
                          "network": 1.09,
                          "config": 1.09,
                          "python": 1.09,
                          "api": 1.09,
                          "gateway": 1.09
                    }
                }


                tokens: ["docker", "compose", "setup"],    # chunk lẻ

            Output:
                  SparseVector(
                      indices=[1823, 4521, 7102],   # index của "docker", "compose", "setup"
                      values=[0.28, 1.09, 1.09]    # weight BM25 tương ứng
                  )

        """
        """Build one document sparse vector using BM25 term weights."""
        if not tokens:
            return SparseVector(indices=[], values=[])


        """
            Counter đếm số lần xuất hiện của từng token trong chunk:                                                                                                            
                                                                                                                                                                      
            tokens = ["docker", "docker", "setup"]                                                                                                                              
            Counter(tokens)
            # → {"docker": 2, "setup": 1}                                                                                                                                       
                
            term_freq = số lần token đó xuất hiện trong chunk. Ví dụ "docker" xuất hiện 2 lần → term_freq = 2.
        """
        term_counts = Counter(tokens)
        doc_len = max(len(tokens), 1)
        weights: dict[int, float] = {}
        ner_boost_map = self._apply_ner_boost(tokens)

        # for qua từng chữ
        for token, term_freq in term_counts.items():
            """
             Tính điểm BM25 cho từng token:    

            - idf — token này hiếm hay phổ biến trong toàn corpus                                                                                                               
            - numerator/denominator — token này xuất hiện bao nhiêu lần trong chunk, normalize theo độ dài chunk
            - weight = idf × TF_normalized — điểm cuối cùng                                                                                                                     
                              
            Ví dụ chunk 0 ["docker", "compose", "setup"]:
            + "docker"  → idf=0.28 (xuất hiện 2/3 chunk) → weight thấp
            + "compose" → idf=1.09 (xuất hiện 1/3 chunk) → weight cao
            + "setup"   → idf=1.09 (xuất hiện 1/3 chunk) → weight cao
            
            Token càng hiếm trong corpus → weight càng cao → quan trọng hơn khi search.
            """

            """
                idf không tính nữa mà sẽ để cho qdrant tính
            """
            # idf = float(bm25.idf.get(token, 0.0))
            # if idf <= 0:
            #     continue

            """
             k1 và b là hyperparameter của BM25, không phải thống kê từ corpus — chúng được set cố định khi khởi tạo:                                                            
                                                                                                                                                                      
              bm25 = BM25Okapi(tokenized_corpus, k1=self.bm25_k1, b=self.bm25_b)                                                                                                  
               
              - k1 — điều chỉnh mức độ ảnh hưởng của term frequency (thường = 1.5)                                                                                                
              - b — điều chỉnh mức độ normalize theo độ dài doc (thường = 0.75)
            
              Nên bm25.k1, bm25.b lấy từ object bm25 vẫn được, nhưng chúng là config chứ không phải số liệu thống kê từ data.
            """
            numerator = term_freq * (self.bm25_k1 + 1)
            denominator = term_freq + self.bm25_k1 * (
                    1 - self.bm25_b + self.bm25_b * doc_len / self.bm25_avg_len
            )
            weight = (numerator / denominator)

            """
              weights = {                                                                                                                                                         
                  1823: 0.28,   # "docker" → index 1823, weight 0.28
                  4521: 1.09,   # "compose" → index 4521, weight 1.09                                                                                                             
                  7102: 1.09,   # "setup" → index 7102, weight 1.09
              }
            
              - Key = index số nguyên của token (từ _token_to_sparse_index)
              - Value = điểm BM25 của token đó
            """

            # gọi ngoài vòng lặp rồi thì chỗ này lấy để tra cứu thôi
            weight += ner_boost_map.get(token, 0.0) # tăng trọng số nếu token là NER

            weights[self._token_to_sparse_index(token)] = float(weight)

        return self._weights_to_sparse_vector(weights)

    async def compute_bm25_sparse_vectors(self, corpus: list[str]) -> list[SparseVector]:
        """Build sparse BM25 document vectors for a corpus concurrently."""
        """
            Hàm này  dùng lúc upload:
          - Nhận toàn bộ corpus (list chunk), đưa vào các chunks
          - Trả ra list SparseVector cho từng chunk → lưu vào Qdrant      
        """
        import asyncio
        if not corpus:
            return []

        def process_chunk_sync(chunk: str) -> SparseVector:
            tokens = self._tokenize_bm25(chunk)
            return self._build_document_sparse_vector(tokens=tokens)

        tasks = [asyncio.to_thread(process_chunk_sync, chunk) for chunk in corpus]
        return await asyncio.gather(*tasks)

    def build_bm25_query_sparse_vector(self, query_text: str) -> SparseVector:
        """Build a sparse query vector that aligns with stored BM25 token dimensions."""
        """
            Hàm này  dùng lúc search:                                                                                                                   
          - Nhận 1 câu query   
          - Trả ra 1 SparseVector cho query đó → dùng để so sánh với vector đã lưu
        """
        query_tokens = self._tokenize_bm25(query_text)
        if not query_tokens:
            return SparseVector(indices=[], values=[])

        weights: dict[int, float] = {}
        for token, term_freq in Counter(query_tokens).items():
            weights[self._token_to_sparse_index(token)] = float(term_freq)

        return self._weights_to_sparse_vector(weights)


    #     # --- NEW METHOD FOR SPRINT 2: Upsert ---
    # async def upsert_documents(
    #     self, 
    #     collection_name: str, 
    #     documents: List[UploadDocumentRequest]
    # ) -> int:
    #     """
    #     Upsert (Insert/Update) a list of documents into the specified collection.
        
    #     In a real scenario, this would:
    #     1. Transform raw PDF/DOCX into chunks.
    #     2. Generate embeddings for each chunk using an LLM.
    #     3. Create Qdrant Points with vector, payload, and unique ID.
        
    #     For now, this is a placeholder implementation.
    #     """
    #     try:
    #         # TODO (Sprint 3): Implement full vector upsert logic
    #         # Placeholders:
    #         # - Generate embeddings
    #         # - Create Qdrant points
    #         # - Call self.client.upsert(...)
            
    #         logger.info(f"Upserting {len(documents)} documents into collection: {collection_name}")
    #         # Mock implementation: Simply log the action
    #         # In Sprint 3, replace this with actual Qdrant client calls
    #         return len(documents)
            
    #     except Exception as e:
    #         logger.error(f"Failed to upsert documents into {collection_name}: {str(e)}")
    #         raise e


    async def ensure_collection_exists(self, collection_name: str) -> None:
        """
        Kiểm tra collection xem có tồn tại không.
        Nếu KHÔNG tồn tại -> Báo lỗi RuntimeError chứ không tự ý tạo mới.
        """
        exists = await self.client.collection_exists(collection_name)
        if not exists:
            logger.error(f"Qdrant collection '{collection_name}' does not exist.")
            raise RuntimeError(f"Qdrant collection '{collection_name}' not found for tenant.")

    async def create_collection(self, collection_name: str) -> None:
        """
        Tạo hoặc nâng cấp collection để support dense mặc định + sparse BM25.
        """
        try:
            exists = await self.client.collection_exists(collection_name)
            
            if exists:
                collection_info = await self.client.get_collection(collection_name)
                sparse_vectors = getattr(collection_info.config.params, "sparse_vectors", None) or {}
                if self.sparse_vector_name not in sparse_vectors:
                    logger.info(
                        f"Adding sparse vector schema '{self.sparse_vector_name}' "
                        f"to existing collection: {collection_name}"
                    )
                    # IDF lúc này sẽ do qdrant tính lúc search
                    # Search xong bỏ chứ không có lưu hay update SparseVector đang có values bị chênh
                    await self.client.update_collection(
                        collection_name=collection_name,
                        sparse_vectors_config={
                            self.sparse_vector_name: SparseVectorParams()
                        },
                    )
                logger.info(f"Qdrant collection '{collection_name}' already exists. Skipping creation.")
                return

            logger.info(f"Creating new Qdrant collection: {collection_name}")
            await self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=self.distance_metric,
                ),
                sparse_vectors_config={
                    self.sparse_vector_name: SparseVectorParams()
                }
            )
            logger.info(
                f"Successfully created Qdrant collection: {collection_name} "
                f"(dense + sparse vectors)"
            )
            
        except UnexpectedResponse as e:
            # Bắt lỗi từ phía server Qdrant (ví dụ: mất kết nối, lỗi auth)
            logger.error(f"Unexpected Qdrant error while creating collection '{collection_name}': {str(e)}")
            raise e
        except Exception as e:
            logger.error(f"Failed to create Qdrant collection '{collection_name}': {str(e)}")
            raise e


    """
    Soft Delete bên Qdrant
    + Khi retrive thì lấy cái collection name đi kèm với tenant name nào mà isActive = True
    + Nếu mà isActive = False thì không lấy ra được collection name luôn -> đồng nghĩa là 
    không chỉ định được collection name trong qdrant để retrive 
    => Đã bị chặn ở tầng postgres nên hàm này là dư thừa không cần dùng nữa
    """
    async def delete_collection(self, collection_name: str) -> None:
        """Xóa luôn (Hard Delete) cho collections của tenant"""
        try:
            exists = await self.client.collection_exists(collection_name)
            if not exists:
                logger.info(f"Qdrant collection '{collection_name}' doesn't exist. Skipping deletion.")
                return
            
            logger.info(f"Deleting Qdrant collection: {collection_name}")
            await self.client.delete_collection(
                collection_name=collection_name
            )
            logger.info(f"Successfully deleted Qdrant collection: {collection_name}")

        except UnexpectedResponse as e:
            logger.error(f"Unexpected Qdrant error while deleting collection '{collection_name}': {str(e)}")
            raise e
        except Exception as e:
            logger.error(f"Failed to delete Qdrant collection '{collection_name}': {str(e)}")
            raise e

    async def search(self, tenant_id: str, collection_name: str, query: list[float], top_k: int = 5) -> list[dict]:
        """
        Thực hiện truy vấn semantic search trong Qdrant dựa trên embedding.
        Trả về danh sách các kết quả (top_k) gần nhất.
        """
        try:
            logger.info(f"Searching in collection '{collection_name}' for tenant '{tenant_id}' with top_k={top_k}")
            search_result = await self.client.query_points(
                collection_name=collection_name,
                query=query,
                limit=top_k
            )
            logger.info(f"Search completed. Found {len(search_result.points)} results.")
            return search_result.points

        except UnexpectedResponse as e:
            logger.error(f"Unexpected Qdrant error during search in collection '{collection_name}': {str(e)}")
            raise e
        except Exception as e:
            logger.error(f"Failed to perform search in collection '{collection_name}': {str(e)}")
            raise e

    async def search_bm25(
        self, tenant_id: str, collection_name: str, query: str, top_k: int = 5
    ) -> list[dict]:
        """
        Perform BM25 keyword search in Qdrant using sparse vectors.

        Args:
            tenant_id: Tenant identifier.
            collection_name: Qdrant collection name for this tenant.
            query: Search query text.
            top_k: Maximum results to return.

        Returns:
            List of ScoredPoint objects with BM25 relevance scores.
        """
        try:
            logger.info(
                f"Performing BM25 search in collection '{collection_name}' "
                f"for tenant '{tenant_id}' with query='{query}', top_k={top_k}"
            )
            sparse_query = self.build_bm25_query_sparse_vector(query)
            if not sparse_query.indices:
                return []

            search_result = await self.client.query_points(
                collection_name=collection_name,
                query=sparse_query,
                using=self.sparse_vector_name,
                limit=top_k,
            )
            logger.info(f"BM25 search completed. Found {len(search_result.points)} results.")
            return search_result.points
        except Exception as e:
            logger.error(f"Failed to perform BM25 search in collection '{collection_name}': {str(e)}")
            raise e

    # Hàm sử dụng cho mode=QDRANT_HYBRID. Nhân chính là hàm QueryPoints của Qdrant.
    # Đầu vào nhận vào embedding dense vector, sparse vector của query, alpha, beta, top_k, collection_name. Trả về danh sách các kết quả (top_k) gần nhất.
    # Đi kèm với hàm fusion_score để tính toán điểm số cuối cùng dựa trên alpha và beta.
    async def qdrant_hybrid_search(
        self,
        tenant_id: str,
        collection_name: str,
        query: list[float],
        sparse_query: list[float],
        top_k: int = 5
    ) -> list[dict]:
        """
        Perform hybrid search in Qdrant combining semantic embedding and BM25 keyword search.
        Args:
            tenant_id: Tenant identifier.
            collection_name: Qdrant collection name for this tenant.
            query: Semantic embedding vector for the query.
            sparse_query: Sparse vector for BM25 query.
            top_k: Maximum results to return.

        Returns:
            List of search results with fused scores.
        """
        try:
            logger.info(
                f"Performing hybrid search in collection '{collection_name}' "
                f"for tenant '{tenant_id}' with top_k={top_k}"
            )
            search_result = await self.client.query_points(
                collection_name=collection_name,
                prefetch=[
                    {
                        "query": query,
                        "using": "",
                        "limit": top_k
                    },
                    {
                        "query": sparse_query,
                        "using": "bm25",
                        "limit": top_k
                    },
                ],
                query=models.RrfQuery(rrf=models.Rrf(k=60)),
                limit=top_k
            )
            logger.info(f"Hybrid search completed. Found {len(search_result.points)} results.")
            return search_result.points
        except Exception as e:
            logger.error(f"Failed to perform hybrid search in collection '{collection_name}': {str(e)}")
            raise e

    async def get_trace(self, tenant_id: str, collection_name: str, query: list[float], top_k: int = 5) -> dict:
        """
        Lấy trace và latency breakdown cho truy vấn
        """
        try:
            logger.info(f"Getting trace for search in collection '{collection_name}' for tenant '{tenant_id}' with top_k={top_k}")
            trace_info = await self.client.query_points(
                collection_name=collection_name,
                query=query,
                limit=top_k
            )
            logger.info(f"Trace retrieved successfully.")
            return trace_info

        except UnexpectedResponse as e:
            logger.error(f"Unexpected Qdrant error while getting trace for collection '{collection_name}': {str(e)}")
            raise e
        except Exception as e:
            logger.error(f"Failed to get trace for collection '{collection_name}': {str(e)}")
            raise e

    async def delete_by_doc_id(self, collection_name: str, doc_id: str) -> None:
        """
        Xóa tất cả point thuộc về 1 doc_id cụ thể trong collection.
        Dùng khi 1 version bị supersede — dọn point vector của bản cũ,
        tránh retrieve.py trả nhầm chunk đã lỗi thời.
        Gọi là best-effort ở nơi dùng (process_document_async): lỗi ở đây
        chỉ log, không fail job vì version mới đã READY rồi.
        """
        try:
            exists = await self.client.collection_exists(collection_name)
            if not exists:
                logger.info(f"Qdrant collection '{collection_name}' doesn't exist. Skipping cleanup for doc_id={doc_id}.")
                return

            await self.client.delete(
                collection_name=collection_name,
                points_selector=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                ),
            )
            logger.info(f"Deleted Qdrant points for doc_id={doc_id} in collection '{collection_name}'")

        except UnexpectedResponse as e:
            logger.error(f"Unexpected Qdrant error while deleting points for doc_id={doc_id}: {str(e)}")
            raise e
        except Exception as e:
            logger.error(f"Failed to delete points for doc_id={doc_id} in '{collection_name}': {str(e)}")
            raise e