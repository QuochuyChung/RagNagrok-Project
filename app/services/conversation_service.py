"""
Conversation service.

Business logic layer cho việc list / xem lại / xóa hội thoại chat — tách biệt
khỏi ChatService (vốn lo chạy pipeline RAG), vì đây thuần là CRUD lịch sử,
không đụng gì tới retrieval/LLM.

Encryption:
    Conversation titles and message content are stored encrypted.  All read
    methods accept an optional ``dek`` (bytes) and forward it to the repository
    so the repository can transparently decrypt before returning data.
"""

from __future__ import annotations

import uuid

from app.core.errors import ConversationNotFoundError
from app.models import Conversations, Messages, Tenants
from app.repositories.conversation_repository import ConversationRepository
from app.core.tenant_dek_provider import get_plaintext_dek


class ConversationService:
    """Business logic layer cho lịch sử hội thoại."""

    def __init__(self, conversation_repo: ConversationRepository) -> None:
        self.conversation_repo = conversation_repo

    async def list_conversations(
        self, user_id: uuid.UUID, *, limit: int, offset: int, tenant: Tenants | None = None
    ) -> tuple[list[Conversations], int]:
        """Danh sách hội thoại của user, có phân trang.

        Args:
            tenant: Current tenant. If provided, titles will be decrypted before return.
        """
        dek: bytes | None = None
        if tenant and tenant.encrypted_dek:
            dek = await get_plaintext_dek(tenant)
        return await self.conversation_repo.list_by_user(user_id, limit=limit, offset=offset, dek=dek)

    async def get_conversation_messages(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID, tenant: Tenants | None = None
    ) -> list[Messages]:
        """Toàn bộ tin nhắn của 1 hội thoại — chỉ khi user đó sở hữu hội thoại này.

        Args:
            tenant: Current tenant. If provided, message content/citations will be decrypted.
        """
        conversation = await self._get_owned_conversation(user_id, conversation_id)
        dek: bytes | None = None
        if tenant and tenant.encrypted_dek:
            dek = await get_plaintext_dek(tenant)
        return await self.conversation_repo.get_all_messages(conversation.conversation_id, dek=dek)

    async def delete_conversation(self, user_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
        """Xóa cứng 1 hội thoại — chỉ khi user đó sở hữu hội thoại này."""
        conversation = await self._get_owned_conversation(user_id, conversation_id)
        await self.conversation_repo.delete_conversation(conversation)
        await self.conversation_repo.commit()

    async def _get_owned_conversation(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Conversations:
        """
        Lấy conversation theo id, raise nếu không tồn tại HOẶC không thuộc user này.

        Nhiều user khác nhau trong CÙNG 1 tenant vẫn có thể có hội thoại riêng —
        session tenant-scoped chỉ cô lập theo tenant, không cô lập theo user,
        nên phải tự check user_id ở đây.
        """
        conversation = await self.conversation_repo.get_by_id(conversation_id)
        if conversation is None or conversation.user_id != user_id:
            raise ConversationNotFoundError(str(conversation_id))
        return conversation
