"""
Conversation history endpoints.

GET    /v1/conversations                              — list hội thoại của user hiện tại (phân trang).
GET    /v1/conversations/{conversation_id}/messages    — lấy toàn bộ tin nhắn của 1 hội thoại.
DELETE /v1/conversations/{conversation_id}             — xóa cứng 1 hội thoại (kèm toàn bộ messages).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import get_conversation_service, get_current_tenant
from app.core.security import bearer_scheme, requires_roles
from app.models import Tenants
from app.schemas.conversation import (
    ConversationListResponse,
    ConversationMessagesResponse,
    ConversationSummary,
    MessageItem,
)
from app.services.conversation_service import ConversationService

router = APIRouter(
    prefix="/v1/conversations",
    tags=["Conversations"],
    dependencies=[Depends(bearer_scheme)],
)


@router.get("", response_model=ConversationListResponse)
@requires_roles("TENANT_ADMIN", "USER")
async def list_conversations(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tenant: Tenants = Depends(get_current_tenant),
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> ConversationListResponse:
    """Danh sách hội thoại của user đang đăng nhập, mới cập nhật trước, có phân trang."""
    user_id = uuid.UUID(str(request.state.user_id))
    conversations, total = await conversation_service.list_conversations(
        user_id, limit=limit, offset=offset, tenant=tenant
    )

    return ConversationListResponse(
        conversations=[
            ConversationSummary(
                conversation_id=str(c.conversation_id),
                title=c.title,
                updated_at=c.updated_at,
                turn_count=c.turn_count,
            )
            for c in conversations
        ],
        total=total,
    )


@router.get("/{conversation_id}/messages", response_model=ConversationMessagesResponse)
@requires_roles("TENANT_ADMIN", "USER")
async def get_conversation_messages(
    request: Request,
    conversation_id: uuid.UUID,
    tenant: Tenants = Depends(get_current_tenant),
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> ConversationMessagesResponse:
    """Toàn bộ tin nhắn của 1 hội thoại (service tự check quyền sở hữu)."""
    user_id = uuid.UUID(str(request.state.user_id))
    messages = await conversation_service.get_conversation_messages(user_id, conversation_id, tenant=tenant)

    return ConversationMessagesResponse(
        conversation_id=str(conversation_id),
        messages=[
            MessageItem(
                message_index=m.message_index,
                role_chat=m.role_chat,
                message_type=m.message_type,
                content=m.content,
                citation_content=m.citation_content,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


@router.delete("/{conversation_id}")
@requires_roles("TENANT_ADMIN", "USER")
async def delete_conversation(
    request: Request,
    conversation_id: uuid.UUID,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> dict[str, str]:
    """Xóa cứng 1 hội thoại (service tự check quyền sở hữu)."""
    user_id = uuid.UUID(str(request.state.user_id))
    await conversation_service.delete_conversation(user_id, conversation_id)
    return {"message": "Đã xóa hội thoại", "conversation_id": str(conversation_id)}
