"""
Chat / RAG pipeline endpoint.

POST /v1/chat — Accept a user message and run the full RAG pipeline:
                retrieve → build prompt → call LLM → return response with citations.

Streaming (Server-Sent Events) chưa hỗ trợ ở giai đoạn này — trường
``ChatRequest.stream`` hiện bị bỏ qua.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
import json
from app.api.deps import get_chat_service, get_current_tenant
from app.core.security import bearer_scheme, requires_roles
from app.models import Tenants
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter(
    prefix="/v1",
    tags=["Chat"],
    dependencies=[Depends(bearer_scheme)],
)


@router.post("/chat", response_model=None)
@requires_roles("TENANT_ADMIN", "USER")
async def chat(
    request: Request,
    body: ChatRequest,
    tenant: Tenants = Depends(get_current_tenant),
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse | StreamingResponse:
    """
    Hỏi đáp trên tài liệu của tenant (RAG).

    - Không truyền ``conversation_id`` -> tạo hội thoại mới.
    - Truyền ``conversation_id`` -> chat tiếp trong hội thoại đó, LLM có
      ngữ cảnh các lượt trước.
    """
    # user_id được JWTAuthenticationMiddleware gán từ claim "sub" của token
    user_id = uuid.UUID(str(request.state.user_id))

    if body.stream:
        generator = chat_service.chat_stream(tenant=tenant, user_id=user_id, request=body)
        # hàm này gọi generator để lấy các chunk => nếu không gọi là không có gì xả ra
        json_chunk = _format_json_result(generator)
        return StreamingResponse(json_chunk, media_type="text/event-stream")

    return await chat_service.chat(
        tenant=tenant,
        user_id=user_id,
        request=body,
    )



async def _format_json_result(events: AsyncIterator[dict]) -> AsyncIterator[str]:
    async for chunk in events:
        payload = json.dumps(chunk["data"], ensure_ascii=False)
        yield f"event: {chunk['event']}\ndata: {payload}\n\n"


        """
            event:
                "SSE-GEMINI-TOKEN"
            data: 
                "câu trả lời của gemini đang gì đó"
                
                
            event:
                "SSE-GEMINI-TOKEN"
            data: 
                "câu trả lời của gemini đang gì đó"
                
        """

