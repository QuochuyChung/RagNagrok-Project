"""
Conversation Pydantic schemas.

Định nghĩa response cho việc list hội thoại (sidebar) và lấy lại toàn bộ
lịch sử tin nhắn của 1 hội thoại cụ thể.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ConversationSummary(BaseModel):
    """1 dòng trong danh sách hội thoại — không kèm nội dung tin nhắn."""

    conversation_id: str = Field(..., description="Conversation identifier.")
    title: str = Field(..., description="Tiêu đề hội thoại.")
    updated_at: datetime = Field(..., description="Lần cập nhật gần nhất.")
    turn_count: int = Field(..., description="Số lượt hỏi-đáp.")


class ConversationListResponse(BaseModel):
    """Response phân trang cho GET /v1/conversations."""

    conversations: list[ConversationSummary] = Field(default_factory=list)
    total: int = Field(..., description="Tổng số hội thoại của user.")


class MessageItem(BaseModel):
    """1 tin nhắn trong lịch sử hội thoại."""

    message_index: int = Field(..., description="Thứ tự tin nhắn trong hội thoại.")
    role_chat: str = Field(..., description="'user' | 'assistant' | 'system'.")
    message_type: str = Field(
        default="text",
        description="'text' bình thường | 'error' lỗi giữa chừng | 'interrupted' bị ngắt kết nối.",
    )
    content: str = Field(..., description="Nội dung tin nhắn.")
    citation_content: str | None = Field(
        default=None, description="Citation JSON (chỉ có ở message assistant)."
    )
    created_at: datetime = Field(..., description="Thời điểm tạo tin nhắn.")


class ConversationMessagesResponse(BaseModel):
    """Response cho GET /v1/conversations/{conversation_id}/messages."""

    conversation_id: str = Field(..., description="Conversation identifier.")
    messages: list[MessageItem] = Field(default_factory=list)
