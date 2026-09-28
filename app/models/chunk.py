import datetime
import uuid
from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, PrimaryKeyConstraint, Index, Uuid, text, Integer, String, \
    DateTime, Boolean, Text
from sqlalchemy.orm import mapped_column, Mapped, relationship
from app.models.base import Base

class Chunks(Base):
    __tablename__ = 'chunks'
    __table_args__ = (
        CheckConstraint('page_start IS NULL OR page_end IS NULL OR page_start <= page_end', name='chk_chunks_page_range'),
        ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE', name='chunks_doc_id_fkey'),
        PrimaryKeyConstraint('chunk_id', name='chunks_pkey'),
        Index('ix_chunks_doc_id', 'doc_id'),
        Index('ux_chunks_doc_index', 'doc_id', 'chunk_index', unique=True)
    )

    chunk_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    doc_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    section: Mapped[Optional[str]] = mapped_column(Text)
    page_start: Mapped[Optional[int]] = mapped_column(Integer)
    page_end: Mapped[Optional[int]] = mapped_column(Integer)

    doc: Mapped['Documents'] = relationship('Documents', back_populates='chunks')