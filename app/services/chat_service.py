"""
Chat service.

Implements the full RAG pipeline: retrieve relevant chunks → build prompt →
call LLM → assemble response with citations. Manages conversation memory.

Luồng 1 lượt chat:
    1. Xác định conversation (tạo mới hoặc load theo conversation_id)
    2. Lấy lịch sử hội thoại (nếu là hội thoại cũ)
    3. Retrieval — tái dùng RetrievalService (mode semantic_rerank)
    4. Ghép prompt (lịch sử + tài liệu + câu hỏi) rồi gọi LLM
    5. Lưu message user + assistant, cập nhật turn_count/token_total
    6. Trả ChatResponse kèm citations
"""

from __future__ import annotations

import json
import math
import uuid
import asyncio
from http.client import responses

import cohere
from datetime import datetime, timezone
from time import perf_counter
from typing import Any


from app.clients.client_factory import ClientFactory
from app.clients.ollama_client import OllamaClient
from app.core.config import get_settings
from app.core.errors import ConversationNotFoundError
from app.core.logging import get_logger
from app.models import Tenants
from app.repositories.conversation_repository import ConversationRepository
from app.schemas.chat import ChatRequest, ChatResponse, Citation, IntentClassification, IntentType
from app.schemas.retrieve import RetrieveRequest, SearchMode
from app.services.retrieval_service import RetrievalService
from app.core.tenant_dek_provider import get_plaintext_dek
from app.profiling import LatencyTracker
from app.utils.hashing import zeroize

logger = get_logger(__name__)

# Độ dài trích dẫn trả về client (không ảnh hưởng nội dung gửi cho LLM)
CITATION_SNIPPET_LENGTH = 500

SYSTEM_PROMPT = """Bạn là trợ lý AI hỗ trợ nhân viên tra cứu thông tin từ tài liệu nội bộ của công ty.

## NGUYÊN TẮC BẮT BUỘC

1. Chỉ trả lời dựa trên ngữ cảnh được cung cấp (context/tài liệu truy xuất bên dưới). Không được bịa đặt thông tin không có trong tài liệu, không được đưa thêm quy định/chính sách không được đề cập. Nếu ngữ cảnh không đủ thông tin để trả lời, hãy nói rõ: "Tôi không tìm thấy thông tin này trong tài liệu hiện có.".

2. ĐƯỢC PHÉP suy luận và tính toán khi tài liệu đã nêu rõ công thức/quy tắc. Khi suy luận/tính toán, phải trình bày ngắn gọn cách tính (để người dùng kiểm tra lại được), sau đó chốt kết quả cuối cùng rõ ràng.

3. Luôn trích dẫn nguồn khi trả lời - nêu rõ tên tài liệu, heading nếu có.

## PHONG CÁCH TRẢ LỜI
- Trả lời bằng tiếng Việt, rõ ràng, súc tích, đúng trọng tâm câu hỏi.
- Với câu hỏi về quy trình/thủ tục: trình bày theo bước (numbered list) nếu tài liệu có cấu trúc từng bước.
- Xóa định dạng kí tự Markdown trong câu trả lời.

## XỬ LÝ CÂU HỎI NGOÀI PHẠM VI

- Nếu câu hỏi không liên quan đến tài liệu nội bộ (ví dụ: hỏi kiến thức chung, hỏi cá nhân AI), trả lời: "Tôi được thiết kế để hỗ trợ tra cứu tài liệu nội bộ công ty. Bạn có câu hỏi nào liên quan đến quy trình, chính sách, hoặc tài liệu công ty không?"
"""


INTENT_SYSTEM_PROMPT = """Bạn là bộ phân loại câu hỏi cho hệ thống tra cứu tài liệu nội bộ công ty.

Nhiệm vụ: đọc LỊCH SỬ HỘI THOẠI và CÂU HỎI MỚI, trả về:
1. "intent":
   - "CHAT_NORMAL": chào hỏi, cảm ơn, hỏi ngoài phạm vi tài liệu công ty (kiến thức chung, hỏi về bản thân AI).
   - "CHAT_RETRIEVE": hỏi về chính sách, quy trình, quy định, tài liệu nội bộ công ty.
2. "rewritten_query":
   - Nếu câu hỏi mới phụ thuộc ngữ cảnh trước đó (vd "còn... thì sao", "cái đó là gì"), viết lại thành câu hỏi độc lập, đầy đủ nghĩa, dựa vào lịch sử.
   - Nếu câu hỏi đã đầy đủ nghĩa hoặc là CHAT_N0RMAL, giữ nguyên câu gốc.

Ví dụ:
- Lịch sử: (trống). Câu hỏi: "Chào bạn" → {"intent": "CHAT_NORMAL", "rewritten_query": "Chào bạn"}
- Lịch sử: (trống). Câu hỏi: "Số ngày nghỉ phép 1 năm?" → {"intent": "RAG_QUERY", "rewritten_query": "Số ngày nghỉ phép 1 năm?"}
- Lịch sử: "Người dùng: Chính sách nghỉ phép? / Trợ lý: 14 ngày/năm...". Câu hỏi: "còn thâm niên thì sao?"
  → {"intent": "RAG_QUERY", "rewritten_query": "Chính sách cộng thêm ngày phép theo thâm niên như thế nào?"}
"""

SSE_EVENT_CITATIONS = "citations" # phần này là dùng để stream citations theo nguồn
SSE_EVENT_TOKEN = "token" # phần này stream câu trả lời theo event token
SSE_EVENT_DONE = "done" # phần này là event done
SSE_EVENT_ERROR= "error"

class ChatService:
    """
        Trong Chat Service bao gồm các hàm
        + chat(): hàm chat bình thường chưa có streaming và intent classify
        + chat_stream(): hàm chat stream đã có streaming và intent classify
        + _build_prompt(): ghép lịch sử + tài liệu (chunks) + câu hỏi thành 1 chuỗi prompt duy nhất gửi cho LLM
        + _format_history(): làm phẳng list message lịch sử hội thoại thành text (Người dùng:/Trợ lý:)
        + _format_context(): ghép nội dung các chunk retrieve được thành khối văn bản TÀI LIỆU trong prompt
        + _build_citations(): đổi chunks retrieve được thành list Citation trả về cho client
        + _classify_intent(): gọi LLM phân loại intent (CHAT_NORMAL/CHAT_RETRIEVE) và rewrite câu hỏi dựa vào lịch sử
        + _rerank_chunks(): truyền chunks vào trong hàm rồi rerank từng chunk
    """

    def __init__(
        self,
        retrieval_service: RetrievalService,
        client_factory: ClientFactory,
        conversation_repo: ConversationRepository,
    ) -> None:
        self.retrieval_service = retrieval_service
        self._client_factory = client_factory
        self.conversation_repo = conversation_repo
        self.settings = get_settings()
        self._cohere_rerank_client = (
            cohere.ClientV2(api_key=self.settings.cohere_trial_key)
            if self.settings.cohere_trial_key
            else None
        )
        self._cohere_model = self.settings.cohere_rerank_model

    async def chat(
        self,
        *,
        tenant: Tenants,
        user_id: uuid.UUID,
        request: ChatRequest,
    ) -> ChatResponse:
        """Chạy trọn 1 lượt hỏi-đáp RAG và lưu lại vào hội thoại."""
        total_start = perf_counter()

        # Resolve Tenant DEK once for the entire request
        tenant_dek = await get_plaintext_dek(tenant)
        try:
            # ── 1. Xác định conversation ──────────────────────────────────────
            if request.conversation_id:
                try:
                    conv_uuid = uuid.UUID(str(request.conversation_id).strip())
                except ValueError:
                    raise ConversationNotFoundError(request.conversation_id)

                conversation = await self.conversation_repo.get_by_id(conv_uuid)
                if conversation is None:
                    raise ConversationNotFoundError(request.conversation_id)
                is_new_conversation = False
            else:
                conversation = await self.conversation_repo.create_conversation(
                    user_id=user_id,
                    title=self.conversation_repo.build_title(request.message),
                    dek=tenant_dek,
                )
                is_new_conversation = True

            try:
                # ── 2. Lấy lịch sử (chỉ khi là hội thoại cũ) ──────────────────
                history: list[Any] = []
                if not is_new_conversation:
                    # x2 vì mỗi lượt sinh ra 2 message (user + assistant)
                    history = await self.conversation_repo.get_recent_messages(
                        conversation.conversation_id,
                        limit=self.settings.max_conversation_turns * 2,
                        dek=tenant_dek,
                    )

                # ── 3. Retrieval — tái dùng RetrievalService ──────────────────
                # Dùng semantic_rerank: BM25 hiện chưa xử lý được tiếng Việt có dấu
                # nên hybrid sẽ cho context kém chính xác hơn.
                search_result = await self.retrieval_service.run_search(
                    tenant,
                    RetrieveRequest(
                        query=request.message,
                        top_k=request.top_k,
                        mode=SearchMode.SEMANTIC_WITH_RERANK,
                    ),
                )
                chunks: list[dict[str, Any]] = search_result["results"]

                logger.info(
                    "chat_retrieval_done",
                    conversation_id=str(conversation.conversation_id),
                    chunk_count=len(chunks),
                )

                # ── 4. Ghép prompt + gọi LLM ─────────────────────────────────
                prompt = self._build_prompt(
                    history=history,
                    chunks=chunks,
                    question=request.message,
                )
                llm_result = await self._client_factory.build_llm_client(request=request).generate(
                    prompt=prompt,
                    system=SYSTEM_PROMPT,
                )

                # ── 5. Lưu lại — tới đây mới bắt đầu ghi ─────────────────────
                citations = self._build_citations(chunks)

                user_index = await self.conversation_repo.get_next_message_index(
                    conversation.conversation_id
                )
                await self.conversation_repo.add_message(
                    conversation_id=conversation.conversation_id,
                    content=request.message,
                    role_chat="user",
                    message_index=user_index,
                    dek=tenant_dek,
                )
                await self.conversation_repo.add_message(
                    conversation_id=conversation.conversation_id,
                    content=llm_result.content,
                    role_chat="assistant",
                    message_index=user_index + 1,  # cùng 1 request, không ai chen vào
                    citation_content=json.dumps(
                        [c.model_dump() for c in citations], ensure_ascii=False
                    ),
                    dek=tenant_dek,
                )
                await self.conversation_repo.bump_conversation(
                    conversation,
                    added_tokens=llm_result.prompt_tokens + llm_result.output_tokens,
                )
                await self.conversation_repo.commit()

            except Exception:
                # Lỗi ở bất kỳ bước nào -> huỷ hết, không để sót conversation rỗng
                # hay message user không có câu trả lời đi kèm.
                await self.conversation_repo.rollback()
                logger.exception(
                    "chat_pipeline_failed",
                    conversation_id=str(conversation.conversation_id),
                    is_new_conversation=is_new_conversation,
                )
                raise

            latency_ms = round((perf_counter() - total_start) * 1000, 3)
            logger.info(
                "chat_completed",
                conversation_id=str(conversation.conversation_id),
                turn_count=conversation.turn_count,
                token_total=conversation.token_total,
                latency_ms=latency_ms,
            )

            return ChatResponse(
                conversation_id=str(conversation.conversation_id),
                message=llm_result.content,
                citations=citations,
                latency_ms=latency_ms,
                timestamp=datetime.now(timezone.utc),
            )
        finally:
            # Always zeroize plaintext tenant DEK once request finishes, including
            # error paths — otherwise the plaintext key lingers in the heap for
            # the lifetime of the request and would survive in memory dumps.
            zeroize(tenant_dek)
            tenant_dek = None

    async def chat_stream(self, *, tenant: Tenants, user_id: uuid.UUID, request: ChatRequest):
        total_start = perf_counter()
        tracker = LatencyTracker(
            "chat",
            tenant_id=str(tenant.tenant_id),
            llm_provider=request.llm_provider,
            is_new_conversation=request.conversation_id is None,
        )

        """
            Xác định đây có phải conversation mới không
        """

        # Resolve Tenant DEK once for the entire stream
        async with tracker.astage("unwrap_tenant_dek"):
            tenant_dek = await get_plaintext_dek(tenant)
        try:
            if request.conversation_id:
                conversation = await self.conversation_repo.get_by_id(conversation_id=uuid.UUID(request.conversation_id))
                if conversation is None:
                    raise ConversationNotFoundError(request.conversation_id)
                is_new_conversation = False
            else:
                conversation = await self.conversation_repo.create_conversation(
                    user_id=user_id,
                    title=self.conversation_repo.build_title(request.message),
                    dek=tenant_dek,
                )
                is_new_conversation = True

            try:
                """
                    Lấy lịch sử chat
                """
                history: list[Any] = []
                if not is_new_conversation:
                    history = await self.conversation_repo.get_recent_messages(
                        conversation_id=conversation.conversation_id,
                        limit=self.settings.max_conversation_turns * 2,
                        dek=tenant_dek,
                    )

                # Khai báo trước để 2 khối except bên dưới luôn đọc được, kể cả
                # khi lỗi xảy ra trước lúc luồng bình thường gán giá trị thật
                # (vd lỗi ngay trong lúc classify intent hoặc retrieval).
                list_tokens: list[str] = []
                citations_out_for_client: list[dict] = []

                """
                    Intent classify loại câu hỏi, xong rồi rewrite query luôn
                    Gọi đến helper dùng để intent-classify

                    Intent Classify:
                    Dựa vào biến môi trường sẽ quyết định LLM nào sẽ intent-classify
                    + Routing: Xác định sẽ đi theo luồng chat dựa vào câu hỏi theo hướng NORMAL_CHAT hay là RETRIEVE_CHAT
                    + Trả lời: Nếu Normal Chat thì trả lời luôn
                    + Rewrite Query: Dựa trên chat history, sẽ ghi lại câu hỏi cho rõ ràng hơn
                """
                async with tracker.astage("intent_classify_rewrite"):
                    intent_result = await self._classify_intent(history=history, question=request.message)
                tracker.add_context(intent=str(intent_result.intent))

                """
                    Khúc này dựa theo intent result mà soạn lại prompt, system prompt và context
                """
                citations_out_for_client = []
                if intent_result.intent == IntentType.CHAT_NORMAL:
                    logger.info("[chat_service] process theo luồng normal chat")
                    """
                        Chat không có retrieval thì không có chunk với retrieval
                    """
                    yield {"event": SSE_EVENT_CITATIONS, "data": []}
                    prompt = f"CÂU HỎI: {request.message}"
                    system_prompt: str = ("Bạn là trợ lý AI của công ty."
                                          "Trả lời ngắn gọn, tự nhiên bằng tiếng Việt."
                                          "Trả lời dựa theo kiến thức mà bạn có.")
                    logger.info(f"prompt: {prompt} và system prompt: {system_prompt} sau khi intent")
                else:
                    """
                        Retrieval
                    """
                    logger.info(f"[chat_service] câu query đã được rewrite từ {request.message} thành {intent_result.rewritten_query}")
                    logger.info("[chat_service] process theo luồng retrieve chat")

                    retrieve_request = RetrieveRequest(
                        query=intent_result.rewritten_query,
                        top_k=max(request.top_k * 2, 10),
                        mode=SearchMode.QDRANT_HYBRID
                    )

                    async with tracker.astage("retrieval"):
                        search_result = await self.retrieval_service.run_search(
                            tenant=tenant,
                            request=retrieve_request
                        )
                    # RetrievalService tự đo sẵn embed/search bên trong -> lấy
                    # lại để có breakdown chi tiết thay vì chỉ 1 con số tổng.
                    _lat = search_result.get("latency_ms") or {}
                    if _lat.get("embed") is not None:
                        tracker.mark("retrieval.embed_query", _lat["embed"])
                    if _lat.get("search") is not None:
                        tracker.mark("retrieval.qdrant_search", _lat["search"])

                    """
                        Object do search trả ra, tự định nghĩa
                        "mode": SearchMode.QDRANT_HYBRID,
                        "results": [self._serialize_result_point_qdrant_hybrid(r) for r in top_results] -> 1 list result,
                        "result_count": len(top_results),
                        "latency_ms": {
                            "embed": round(embed_latency_ms, 3),
                            "search": round(search_latency_ms, 3),
                            "total": round((perf_counter() - total_start) * 1000, 3),
                        },

                        =====
                        Chunks là results
                        Khúc này là tương đương với 1 chunk
                        Result:
                        {
                            "id": str(getattr(result, "id", "")),
                            "scores": {
                                "semantic": None,
                                "bm25": None,
                                "rerank_bonus": None,
                                "rerank_bonus": None,
                                "final": round(original_score, 4) if original_score else 0.0,
                            },
                            "doc_id": payload.get("doc_id", ""),
                            "chunk_index": payload.get("chunk_index", -1),
                            "content": payload.get("text", ""),
                            "metadata": metadata,
                        }
                    """

                    chunks: list[dict[str, Any]] = search_result["results"]
                    logger.info("chat_retrieval_done", conversation_id=str(conversation.conversation_id), chunk_count=len(chunks))

                    async with tracker.astage("rerank", provider="cohere", chunk_count=len(chunks)):
                        chunks_reranking = await asyncio.to_thread(
                            self._rerank_chunks, intent_result.rewritten_query, chunks, self._cohere_rerank_client, self._cohere_model
                        )
                    
                    # Cắt lại đúng số lượng top_k user yêu cầu (vd: 5)
                    chunks_reranking = chunks_reranking[:request.top_k]

                    logger.info("reranking_done", conversation_id=str(conversation.conversation_id), chunk_count=len(chunks_reranking), rerank_provider=self.settings.rerank_provider)
                    """
                        Lấy Citations xong trả nguyên 1 list citations ra cho người dùng rồi mới bắt đầu thực
                        hiện streaming chat
                    """
                    citations = self._build_citations(chunks=chunks_reranking)

                    for c in citations:
                        citations_out_for_client.append(c.model_dump())

                    yield {
                        "event": SSE_EVENT_CITATIONS,
                        "data": citations_out_for_client
                    }
                    """
                        Build 1 prompt gửi đến LLM
                    """
                    prompt = self._build_prompt(
                        history=history,
                        chunks=chunks_reranking,
                        question=intent_result.rewritten_query
                    )
                    # System prompt là system prompt của truy vấn tài liệu
                    system_prompt = SYSTEM_PROMPT
                    logger.info(f"prompt: {prompt} và system prompt: {system_prompt} sau khi intent")

                """
                Chỗ này sẽ append list string thay vì +=
                Khúc này là trả lời/luồng chat
                """
                token_count: int = 0
                list_tokens: list[str] = []
                full_content: str = ""
                _generate_start = perf_counter()
                _first_token_at: float | None = None
                async for piece_dict in self._client_factory.build_llm_client(request=request).generate_stream(prompt=prompt, system=system_prompt):
                    if piece_dict["content"]:
                        token = piece_dict["content"]
                        if _first_token_at is None:
                            # TTFT — thứ người dùng thực sự cảm nhận là "chậm",
                            # tách riêng khỏi tổng thời gian sinh hết câu trả lời.
                            _first_token_at = perf_counter()
                            tracker.mark(
                                "generate_ttft",
                                (_first_token_at - _generate_start) * 1000,
                                provider=request.llm_provider,
                            )
                        list_tokens.append(token)
                        """
                            Trả ra từng token
                        """
                        yield {
                            "event": SSE_EVENT_TOKEN,
                            "data": token
                        }
                    if piece_dict["token_count"]:
                        token_count = piece_dict["token_count"]

                full_content = "".join(list_tokens)
                tracker.mark(
                    "generate_stream_total",
                    (perf_counter() - _generate_start) * 1000,
                    token_count=token_count,
                    answer_chars=len(full_content),
                )

                if not full_content:
                    raise RuntimeError("Ollama trả response rỗng")

                logger.info(f"Đã chat xong với câu trả lời {full_content}")

                """
                    Nếu là conversation mới thì user_index sẽ là 0
                    Lưu các thông tin vào trong postgres
                """
                user_index = await self.conversation_repo.get_next_message_index(
                    conversation_id=conversation.conversation_id
                )

                await self.conversation_repo.add_message(
                    conversation_id=conversation.conversation_id,
                    content=request.message,
                    role_chat="user",
                    message_index=user_index,
                    dek=tenant_dek,
                )

                await self.conversation_repo.add_message(
                    conversation_id=conversation.conversation_id,
                    content=full_content,
                    role_chat="assistant",
                    message_index=user_index + 1,
                    citation_content=json.dumps(citations_out_for_client, ensure_ascii=False),
                    dek=tenant_dek,
                )

                await self.conversation_repo.bump_conversation(
                    conversation,
                    added_tokens=token_count
                )

                await self.conversation_repo.commit()

                latency_ms = round((perf_counter() - total_start) * 1000, 3)

                logger.info(
                    "chat_stream_completed",
                    conversation_id=str(conversation.conversation_id),
                    turn_count=conversation.turn_count,
                    latency_ms=latency_ms
                )

                yield {
                    "event": SSE_EVENT_DONE,
                    "data": {
                        "conversation_id": str(conversation.conversation_id),
                        "latency_ms": latency_ms
                    },
                }

            except (GeneratorExit, asyncio.CancelledError):
                # Client ngắt kết nối giữa chừng (bấm "Đoạn chat mới", đóng tab,
                # mất mạng). Hai exception này kế thừa BaseException nên KHÔNG
                # rơi vào `except Exception` bên dưới — trước đây lọt thẳng ra
                # ngoài, không commit gì, cả lượt chat biến mất im lặng. Chưa
                # có gì được lưu ở nhánh này (luồng thành công chỉ lưu ở cuối),
                # nên lưu cả câu hỏi lẫn câu trả lời dở dang rồi mới raise lại.
                await self._save_failed_turn(
                    conversation=conversation,
                    user_message=request.message,
                    partial_content="".join(list_tokens),
                    message_type="interrupted",
                    citations=citations_out_for_client,
                    dek=tenant_dek,
                )
                logger.warning(
                    "chat_stream_client_disconnected",
                    conversation_id=str(conversation.conversation_id),
                )
                raise
            except Exception as exc:
                logger.exception(
                    "chat_stream_failed",
                    conversation_id=str(conversation.conversation_id),
                    is_new_conversation=is_new_conversation
                )
                # Tương tự — lưu cả câu hỏi lẫn câu trả lời lỗi/dở dang trong
                # cùng 1 lần commit, thay vì rollback bỏ hết như code cũ.
                await self._save_failed_turn(
                    conversation=conversation,
                    user_message=request.message,
                    partial_content="".join(list_tokens),
                    message_type="error",
                    citations=citations_out_for_client,
                    dek=tenant_dek,
                )
                yield {"event": SSE_EVENT_ERROR, "data": {"message": str(exc)}}
        finally:
            # Chốt số đo latency ở finally để cả nhánh lỗi/ngắt kết nối vẫn có
            # dữ liệu — đó chính là lúc cần biết chặng nào chậm nhất.
            tracker.finish()
            # Always zeroize plaintext tenant DEK once stream finishes (including
            # error paths and early generator returns).
            zeroize(tenant_dek)
            tenant_dek = None

    async def _save_failed_turn(
        self,
        *,
        conversation,
        user_message: str,
        partial_content: str,
        message_type: str,
        citations: list[dict],
        dek: bytes,
    ) -> None:
        """Lưu 1 lượt chat bị lỗi/ngắt giữa chừng: câu hỏi user + câu trả lời
        dở dang (có thể rỗng), rồi commit — dùng chung cho 2 khối except của
        chat_stream() để không lặp lại cùng 1 đoạn logic 2 lần."""
        user_index = await self.conversation_repo.get_next_message_index(
            conversation_id=conversation.conversation_id
        )
        await self.conversation_repo.add_message(
            conversation_id=conversation.conversation_id,
            content=user_message,
            role_chat="user",
            message_index=user_index,
            dek=dek,
        )
        await self.conversation_repo.add_message(
            conversation_id=conversation.conversation_id,
            content=partial_content,
            role_chat="assistant",
            message_index=user_index + 1,
            message_type=message_type,
            citation_content=json.dumps(citations, ensure_ascii=False) if citations else None,
            dek=dek,
        )
        await self.conversation_repo.commit()

    @classmethod
    def _build_prompt(
        cls,
        *,
        history: list[Any],
        chunks: list[dict[str, Any]],
        question: str,
    ) -> str:
        """
        Ghép 3 khối thành 1 prompt duy nhất.

        OllamaClient.generate() hiện chỉ nhận 1 chuỗi prompt, nên lịch sử phải
        làm phẳng thành text thay vì gửi mảng messages theo đúng vai user/assistant.
        """
        blocks: list[str] = []

        if history:
            blocks.append(f"### LỊCH SỬ HỘI THOẠI:\n{cls._format_history(history)}")

        blocks.append(f"### TÀI LIỆU:\n{cls._format_context(chunks)}")
        blocks.append(f"### CÂU HỎI:\n{question}")

        return "\n\n".join(blocks)

    @staticmethod
    def _format_history(history: list[Any]) -> str:
        """Làm phẳng lịch sử thành text, giữ nguyên thứ tự cũ -> mới."""
        lines = []
        for message in history:
            speaker = "Người dùng" if message.role_chat == "user" else "Trợ lý"
            lines.append(f"{speaker}: {message.content}")
        return "\n".join(lines)

    @staticmethod
    def _format_context(chunks: list[dict[str, Any]]) -> str:
        """Ghép nội dung các chunk retrieve được thành khối TÀI LIỆU."""
        if not chunks:
            return "(Không tìm thấy tài liệu liên quan đến câu hỏi này.)"

        parts = []
        for i, chunk in enumerate(chunks, start=1):
            heading = (chunk.get("metadata") or {}).get("heading", "")
            header = f"[Nguồn {i}]" + (f" {heading}" if heading else "")
            parts.append(f"{header}\n{chunk.get('content', '')}")
        return "\n\n".join(parts)

    @staticmethod
    def _build_citations(chunks: list[dict[str, Any]]) -> list[Citation]:
        """Đổi kết quả retrieval thành Citation trả về cho client."""
        citations: list[Citation] = []
        for chunk in chunks:
            content = chunk.get("content", "")
            metadata = chunk.get("metadata") or {}
            citations.append(
                Citation(
                    doc_id=str(chunk.get("doc_id", "")),
                    doc_name=str(metadata.get("doc_name", "")),
                    chunk_index=chunk.get("chunk_index", -1),
                    content_snippet=content[:CITATION_SNIPPET_LENGTH],
                    score=(chunk.get("scores") or {}).get("final", 0.0),
                )
            )
        return citations

    async def _classify_intent(self, *, history: list[Any], question: str) -> IntentClassification:
        """
            Trong đây sẽ bao gồm bước classify câu hỏi với lại rewrite query
        """

        history_text = "(không có)" if not history else self._format_history(history)

        prompt = f"LỊCH SỬ HỘI THOẠI:\n{history_text}\n\nCÂU HỎI MỚI: {question}"

        # gọi đến model
        raw = await self._client_factory.build_classify_client().classify(
            prompt=prompt,
            system=INTENT_SYSTEM_PROMPT,
            schema=IntentClassification.model_json_schema(),
        )

        logger.info(f"[chat_service] schema gửi cho model dưới dạng json là {IntentClassification.model_json_schema()}")

        """
            model_json_schema sẽ cho ra format dữ liệu lưu dưới dạng json
            {
                "title": "IntentClassification",
                "type": "object",
                "properties": {
                    "intent": {"type": "string"},
                    "rewritten_query": {"type": "string"},
                },
                "required": ["intent", "rewritten_query"]
            }
        """
        # Decode json ra
        return IntentClassification.model_validate_json(raw)

    @staticmethod
    def _rerank_chunks(
        query: str,
        chunks: list[dict],
        cohere_client: cohere.ClientV2 | None = None,
        cohere_model: str = "rerank-v3.5",
    ) -> list[dict]:
        if not chunks:
            return []

        if cohere_client is None:
            logger.warning("cohere_client_missing_for_rerank")
            return chunks

        document_contents: list[str] = [chunk.get("content", "") for chunk in chunks]

        try:
            response = cohere_client.rerank(
                model=cohere_model,
                query=query,
                documents=document_contents,
                top_n=len(document_contents),
            )
            results: list[dict] = []
            for cohere_chunk_result in response.results:
                chunk = chunks[cohere_chunk_result.index]
                if "scores" not in chunk or chunk["scores"] is None:
                    chunk["scores"] = {}
                chunk["scores"]["final"] = cohere_chunk_result.relevance_score
                results.append(chunk)
            return results
        except Exception as exc:
            logger.warning("cohere_rerank_failed", error=str(exc))
            return chunks
