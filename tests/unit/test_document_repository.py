"""Unit tests for document/chunk soft-delete consistency."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import Chunks
from app.repositories.document_repository import DocumentRepository


def _assert_chunk_state_update(session: AsyncMock, expected_state: bool) -> None:
    statement = session.execute.await_args.args[0]
    assert statement.table is Chunks.__table__
    values = {column.key: value.value for column, value in statement._values.items()}
    assert values == {"is_deleted": expected_state}


@pytest.mark.asyncio
async def test_soft_delete_marks_document_chunks_deleted() -> None:
    session = AsyncMock()
    repository = DocumentRepository(session)
    document = MagicMock(doc_id=uuid.uuid4(), is_deleted=False)

    await repository.soft_delete(document)

    assert document.is_deleted is True
    _assert_chunk_state_update(session, expected_state=True)
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(document)


@pytest.mark.asyncio
async def test_mark_superseded_marks_document_chunks_deleted() -> None:
    session = AsyncMock()
    repository = DocumentRepository(session)
    document = MagicMock(doc_id=uuid.uuid4(), is_deleted=False)

    await repository.mark_superseded(document)

    assert document.is_deleted is True
    _assert_chunk_state_update(session, expected_state=True)
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(document)


@pytest.mark.asyncio
async def test_restore_marks_document_chunks_active() -> None:
    session = AsyncMock()
    repository = DocumentRepository(session)
    document = MagicMock(doc_id=uuid.uuid4(), is_deleted=True)

    await repository.restore(document)

    assert document.is_deleted is False
    _assert_chunk_state_update(session, expected_state=False)
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(document)
