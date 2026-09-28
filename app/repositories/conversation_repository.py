"""
Conversation repository.

Data access layer cho hội thoại chat (bảng ``conversations`` + ``messages``).

Cả 2 bảng nằm TRONG schema của tenant (SCHEMA_XXX), nên không có cột
tenant_id — cô lập đã được đảm bảo bởi schema_translate_map gắn trên session
(xem app/core/custome_session.py). Repository này chỉ cần lo truy vấn.

Encryption:
    - Encrypted fields: Conversations.title, Messages.content, Messages.citation_content
    - All write methods accept a plaintext ``dek`` (bytes) and encrypt before insert.
    - All read methods accept a plaintext ``dek`` (bytes) and decrypt after fetch.
    - Legacy rows that do not start with "enc:" are returned as-is (backward compat).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import Conversations, Messages
from app.utils.field_cipher import encrypt_field, decrypt_field

logger = get_logger(__name__)

# Độ dài tối đa của title tự sinh từ câu hỏi đầu tiên (cột title là VARCHAR(255))
TITLE_MAX_LENGTH = 50


class ConversationRepository:
    """PostgreSQL data access cho conversations và messages."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Conversation ──────────────────────────────────────────────────────

    @staticmethod
    def build_title(first_message: str) -> str:
        """
        Sinh title cho conversation mới từ câu hỏi đầu tiên.

        Cột title là NOT NULL nên luôn phải có giá trị — cắt ngắn câu hỏi
        thay vì bắt client tự đặt tên.
        """
        title = " ".join(first_message.split())  # gộp xuống dòng / khoảng trắng thừa
        if len(title) > TITLE_MAX_LENGTH:
            title = title[:TITLE_MAX_LENGTH].rstrip() + "..."
        return title or "Cuộc hội thoại mới"

    async def create_conversation(
        self, *, user_id: uuid.UUID, title: str, dek: bytes
    ) -> Conversations:
        """Tạo phiên hội thoại mới. Chưa commit — để service quyết định.

        Args:
            dek: Plaintext 32-byte AES-256 Tenant DEK used to encrypt ``title``.
        """
        encrypted_title = encrypt_field(title, dek)
        conversation = Conversations(user_id=user_id, title=encrypted_title)
        self.session.add(conversation)
        await self.session.flush()      # flush để lấy conversation_id do DB sinh
        await self.session.refresh(conversation)
        return conversation

    async def get_by_id(self, conversation_id: uuid.UUID) -> Conversations | None:
        """
        Tìm conversation theo id.

        Không cần lọc tenant — session đã gắn đúng schema, tenant khác
        không thể thấy conversation của nhau.
        """
        result = await self.session.execute(
            select(Conversations).where(Conversations.conversation_id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def bump_conversation(
        self, conversation: Conversations, *, added_tokens: int = 0
    ) -> Conversations:
        """
        Sau mỗi lượt chat: tăng turn_count và cộng dồn token_total.
        Để kiểm tra cuộc hội thoại đó ngốn bao nhiêu token
        """
        conversation.turn_count += 1
        conversation.token_total += added_tokens
        await self.session.flush()
        await self.session.refresh(conversation)
        return conversation

    # ── Message ───────────────────────────────────────────────────────────

    async def get_next_message_index(self, conversation_id: uuid.UUID) -> int:
        """
        Tính message_index tiếp theo = max hiện tại + 1 (rỗng thì bắt đầu từ 0).

        Có unique index (conversation_id, message_index) nên không được trùng.
        Dùng max() thay vì turn_count vì mỗi lượt sinh ra 2 message
        (user + assistant), không map 1-1 với turn_count.

        => Làm cái này để đánh dấu cặp unique là (conversation_id, message_index) chứ không phải riêng conversation_id

        Nghĩa là: nhiều message CÙNG 1 conversation_id là chuyện bình thường,
        bắt buộc phải vậy (1 conversation có nhiều message mà)
        — chỉ là trong cùng conversation đó, không được có 2 message trùng message_index.

        conversation_id | message_index | role
        ----------------|----------------|----------
        conv-A          | 0              | user       ✓ ok
        conv-A          | 1              | assistant  ✓ ok
        conv-A          | 2              | user       ✓ ok
        conv-A          | 2              | assistant  ✗ LỖI — trùng (conv-A, 2) với dòng trên
        conv-B          | 0              | user       ✓ ok — conv-B khác conv-A, index 0 vẫn được dùng lại thoải mái
        """
        result = await self.session.execute(
            select(func.max(Messages.message_index)).where(
                Messages.conversation_id == conversation_id
            )
        )
        current_max = result.scalar()
        return 0 if current_max is None else current_max + 1

    async def get_recent_messages(
        self, conversation_id: uuid.UUID, limit: int, dek: bytes | None = None
    ) -> list[Messages]:
        """
        Lấy `limit` message GẦN NHẤT, trả về theo thứ tự CŨ -> MỚI.

        Phải giới hạn vì LLM có giới hạn độ dài input: hội thoại dài mà nhồi
        hết vào prompt sẽ tràn context.

        Query lấy mới nhất trước (desc) rồi đảo lại, để cắt đúng phần đuôi
        gần nhất chứ không phải phần đầu hội thoại.

        Args:
            dek: Plaintext Tenant DEK to decrypt content/citation_content.
                 If None, values are returned as stored (raw ciphertext).
        """
        result = await self.session.execute(
            select(Messages)
            .where(Messages.conversation_id == conversation_id)
            .order_by(Messages.message_index.desc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        rows.reverse()
        if dek:
            for msg in rows:
                msg.content = decrypt_field(msg.content, dek)
                if msg.citation_content:
                    msg.citation_content = decrypt_field(msg.citation_content, dek)
        return rows

    async def add_message(
        self,
        *,
        conversation_id: uuid.UUID,
        content: str,
        role_chat: str,
        message_index: int,
        dek: bytes,
        message_type: str = "text",
        citation_content: str | None = None,
    ) -> Messages:
        """
        Thêm 1 message vào hội thoại.

        role_chat bị CheckConstraint giới hạn ở 'user' | 'assistant' | 'system'.
        citation_content lưu nguồn (chunk nào) đã dùng để sinh câu trả lời —
        chỉ có ở message của assistant.

        Args:
            dek: Plaintext Tenant DEK to encrypt content and citation_content.
        """
        encrypted_content = encrypt_field(content, dek)
        encrypted_citation = encrypt_field(citation_content, dek) if citation_content else None
        message = Messages(
            conversation_id=conversation_id,
            content=encrypted_content,
            role_chat=role_chat,
            message_index=message_index,
            message_type=message_type,
            citation_content=encrypted_citation,
        )
        self.session.add(message)
        await self.session.flush()
        await self.session.refresh(message)
        return message

    async def list_by_user(
        self, user_id: uuid.UUID, *, limit: int, offset: int, dek: bytes | None = None
    ) -> tuple[list[Conversations], int]:
        """Trả (list hội thoại theo trang, tổng số hội thoại của user) — dùng cho sidebar.

        Args:
            dek: Plaintext Tenant DEK to decrypt conversation titles. If None,
                 titles are returned as stored (raw ciphertext).
        """
        count_result = await self.session.execute(
            select(func.count()).select_from(Conversations).where(Conversations.user_id == user_id)
        )
        total = count_result.scalar_one()

        result = await self.session.execute(
            select(Conversations)
            .where(Conversations.user_id == user_id)
            .order_by(Conversations.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        conversations = list(result.scalars().all())
        if dek:
            for conv in conversations:
                conv.title = decrypt_field(conv.title, dek)
        return conversations, total

    async def get_all_messages(
        self, conversation_id: uuid.UUID, dek: bytes | None = None
    ) -> list[Messages]:
        """
        Lấy TOÀN BỘ tin nhắn của 1 hội thoại, cũ -> mới.

        Khác get_recent_messages() (có limit, chỉ phục vụ build prompt cho LLM) —
        hàm này dùng để hiển thị đầy đủ lịch sử cho user xem lại.

        Args:
            dek: Plaintext Tenant DEK to decrypt message content/citations.
        """
        result = await self.session.execute(
            select(Messages)
            .where(Messages.conversation_id == conversation_id)
            .order_by(Messages.message_index.asc())
        )
        rows = list(result.scalars().all())
        if dek:
            for msg in rows:
                msg.content = decrypt_field(msg.content, dek)
                if msg.citation_content:
                    msg.citation_content = decrypt_field(msg.citation_content, dek)
        return rows

    async def delete_conversation(self, conversation: Conversations) -> None:
        """
        Xóa cứng — không có cột is_deleted như Documents vì hội thoại không
        cần restore lại (mất thì hỏi lại được, không tốn công re-index).
        Messages con tự động bị xóa theo nhờ FK ondelete='CASCADE'.
        """
        await self.session.delete(conversation)

    # ── Transaction ───────────────────────────────────────────────────────

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
