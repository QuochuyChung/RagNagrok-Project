"""
Chat Pydantic schemas.

Defines request/response models for the /chat endpoint (RAG pipeline).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request body for a RAG chat completion."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="The user's message to the RAG pipeline.",
    )
    conversation_id: str | None = Field(
        default=None,
        description="Optional conversation ID for multi-turn memory.",
    )
    stream: bool = Field(
        default=False,
        description="Whether to stream the response as Server-Sent Events.",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of chunks to retrieve for context.",
    )
    llm_provider: str = Field(
        default="",
        description="Provider for LLM provider.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "message": "What is the refund policy?",
                    "conversation_id": None,
                    "stream": False,
                    "top_k": 5,
                }
            ]
        }
    }


class LLMResult(BaseModel):
    """
    Kết quả 1 lần gọi LLM (nội bộ giữa OllamaClient và ChatService).

    Không phải response trả cho client — ChatResponse mới là thứ đi ra HTTP.
    Giữ lại số token để cập nhật conversations.token_total.
    """

    content: str = Field(..., description="Nội dung text model sinh ra.")
    prompt_tokens: int = Field(default=0, description="Số token của phần prompt gửi lên.")
    output_tokens: int = Field(default=0, description="Số token model sinh ra.")


class Citation(BaseModel):
    """A source chunk cited in the chat response."""

    doc_id: str = Field(..., description="Source document identifier.")
    doc_name: str = Field(default="", description="Source document file name.")
    chunk_index: int = Field(..., description="Source chunk position.")
    content_snippet: str = Field(..., description="Relevant excerpt from the chunk.")
    score: float = Field(..., description="Retrieval similarity score.")


class ChatResponse(BaseModel):
    """Response from the RAG chat pipeline."""

    conversation_id: str = Field(..., description="Conversation session identifier.")
    message: str = Field(..., description="The assistant's generated response.")
    citations: list[Citation] = Field(
        default_factory=list,
        description="Source chunks used to generate the response.",
    )
    latency_ms: float | None = Field(
        default=None, description="Total pipeline latency in milliseconds."
    )
    timestamp: datetime = Field(..., description="UTC timestamp of the response.")


class IntentType(str, Enum):
        CHAT_NORMAL = "CHAT_NORMAL"
        CHAT_RETRIEVE = "CHAT_RETRIEVE"


class IntentClassification(BaseModel):
    intent: Literal[IntentType.CHAT_NORMAL, IntentType.CHAT_RETRIEVE] = Field(
        description="Đây là chỗ để định nghĩa intent classification."
    )
    rewritten_query: str = Field(
        default="",
        description="Câu query đã được rewrite lại từ câu query gốc.",
    )


