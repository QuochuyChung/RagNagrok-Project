import datetime
import uuid
from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, PrimaryKeyConstraint, Index, Uuid, text, String, DateTime, \
    Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Messages(Base):
    __tablename__ = 'messages'
    __table_args__ = (
        CheckConstraint("role_chat::text = ANY (ARRAY['user'::character varying, 'assistant'::character varying, 'system'::character varying]::text[])", name='chk_messages_role_chat'),
        ForeignKeyConstraint(['conversation_id'], ['conversations.conversation_id'], ondelete='CASCADE', name='messages_conversation_id_fkey'),
        PrimaryKeyConstraint('message_id', name='messages_pkey'),
        Index('ix_messages_conversation_id', 'conversation_id'),
        Index('ux_messages_conversation_index', 'conversation_id', 'message_index', unique=True)
    )

    message_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    role_chat: Mapped[str] = mapped_column(String(255), nullable=False)
    message_index: Mapped[int] = mapped_column(Integer, nullable=False)
    message_type: Mapped[str] = mapped_column(String(255), nullable=False)
    citation_content: Mapped[Optional[str]] = mapped_column(Text)

    conversation: Mapped['Conversations'] = relationship('Conversations', back_populates='messages')
