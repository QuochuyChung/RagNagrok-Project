"""
Unit tests cho các thay đổi liên quan đến encryption (Sprint review).

Bao phủ:
  - field_cipher: encrypt_field / decrypt_field / is_encrypted
    roundtrip, backward-compat với legacy plaintext rows,
    ciphertext tampering phải raise.
  - encryption: KMS fallback whitelist đã được thu hẹp,
    fallback counter tăng + raise khi vượt ngưỡng.
  - cross-tenant: file DEK EncryptionContext có bind doc_id nên
    không thể swap giữa 2 file cùng tenant.
  - tenant_name immutability: rename bị block.
  - chat_service.chat / retrieval_service.run_search: zeroize
    plaintext tenant DEK trong finally block.
"""

from __future__ import annotations

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from botocore.exceptions import ClientError


# ── field_cipher ─────────────────────────────────────────────────────────


class TestFieldCipherRoundtrip:
    """Encrypt -> decrypt phải trả về đúng plaintext."""

    def test_roundtrip_ascii(self):
        from app.utils.field_cipher import encrypt_field, decrypt_field
        dek = b"0" * 32
        ct = encrypt_field("hello world", dek)
        assert ct.startswith("enc:")
        assert decrypt_field(ct, dek) == "hello world"

    def test_roundtrip_unicode_vietnamese(self):
        """Đặc biệt quan trọng với tiếng Việt có dấu phức tạp."""
        from app.utils.field_cipher import encrypt_field, decrypt_field
        dek = b"\x42" * 32
        text = "Xin chào các bạn — đây là test ă ơ ư đ"
        assert decrypt_field(encrypt_field(text, dek), dek) == text

    def test_roundtrip_long_text(self):
        from app.utils.field_cipher import encrypt_field, decrypt_field
        dek = b"a" * 32
        text = "x" * 100_000
        assert decrypt_field(encrypt_field(text, dek), dek) == text

    def test_roundtrip_empty_string(self):
        from app.utils.field_cipher import encrypt_field, decrypt_field
        dek = b"k" * 32
        assert decrypt_field(encrypt_field("", dek), dek) == ""

    def test_is_encrypted(self):
        from app.utils.field_cipher import encrypt_field, is_encrypted
        dek = b"k" * 32
        assert is_encrypted(encrypt_field("foo", dek))
        assert not is_encrypted("plaintext")
        assert not is_encrypted(None)


class TestFieldCipherBackwardCompat:
    """Giá trị không có prefix 'enc:' phải được trả về nguyên xi (legacy rows)."""

    def test_legacy_plaintext_returned_as_is(self):
        from app.utils.field_cipher import decrypt_field
        dek = b"k" * 32
        legacy = "Đây là dữ liệu cũ chưa được mã hoá"
        assert decrypt_field(legacy, dek) == legacy

    def test_legacy_empty_string(self):
        from app.utils.field_cipher import decrypt_field
        dek = b"k" * 32
        assert decrypt_field("", dek) == ""


class TestFieldCipherTampering:
    """Ciphertext bị sửa đổi / sai DEK phải raise ValueError."""

    def test_tampered_ciphertext_raises(self):
        from app.utils.field_cipher import encrypt_field, decrypt_field
        dek = b"k" * 32
        other_dek = b"j" * 32
        ct = encrypt_field("secret", dek)
        # GCM tag sẽ không khớp nếu dùng sai DEK
        with pytest.raises(ValueError):
            decrypt_field(ct, other_dek)

    def test_truncated_ciphertext_raises(self):
        from app.utils.field_cipher import encrypt_field, decrypt_field
        dek = b"k" * 32
        ct = encrypt_field("secret", dek)
        # Cắt bớt nửa ciphertext
        prefix_len = len("enc:")
        truncated = ct[:prefix_len + 10]
        with pytest.raises(ValueError):
            decrypt_field(truncated, dek)

    def test_invalid_dek_length_raises(self):
        from app.utils.field_cipher import encrypt_field
        with pytest.raises(ValueError):
            encrypt_field("foo", b"short")


# ── KMS fallback whitelist + counter ─────────────────────────────────────


class TestKMSFallbackWhitelist:
    """Danh sách fallback phải được thu hẹp — không còn InvalidCiphertextException,
    NotFoundException nằm trong whitelist."""

    def test_fallback_whitelist_is_narrow(self):
        from app.core.encryption import _KMS_FALLBACK_ERRORS
        # Phải bao gồm error rotate alias và error credentials không hợp lệ trong dev
        assert "IncorrectKeyException" in _KMS_FALLBACK_ERRORS
        assert "KeyUnavailableException" in _KMS_FALLBACK_ERRORS
        assert "UnrecognizedClientException" in _KMS_FALLBACK_ERRORS

    def test_unrecognized_client_in_whitelist(self):
        """UnrecognizedClientException (due to dummy/invalid AWS credentials in dev environment) should trigger local fallback."""
        from app.core.encryption import _is_kms_fallback_error
        exc = ClientError(
            {"Error": {"Code": "UnrecognizedClientException", "Message": "The security token included in the request is invalid."}},
            "GenerateDataKey",
        )
        assert _is_kms_fallback_error(exc) is True

    def test_invalid_ciphertext_not_in_whitelist(self):
        """InvalidCiphertextException có thể bị trigger bởi blob tuỳ ý, không được fallback."""
        from app.core.encryption import _is_kms_fallback_error
        exc = ClientError(
            {"Error": {"Code": "InvalidCiphertextException", "Message": "x"}},
            "Decrypt",
        )
        assert _is_kms_fallback_error(exc) is False

    def test_not_found_not_in_whitelist(self):
        from app.core.encryption import _is_kms_fallback_error
        exc = ClientError(
            {"Error": {"Code": "NotFoundException", "Message": "x"}},
            "Decrypt",
        )
        assert _is_kms_fallback_error(exc) is False

    def test_incorrect_key_in_whitelist(self):
        from app.core.encryption import _is_kms_fallback_error
        exc = ClientError(
            {"Error": {"Code": "IncorrectKeyException", "Message": "x"}},
            "Decrypt",
        )
        assert _is_kms_fallback_error(exc) is True

    def test_key_unavailable_in_whitelist(self):
        from app.core.encryption import _is_kms_fallback_error
        exc = ClientError(
            {"Error": {"Code": "KeyUnavailableException", "Message": "x"}},
            "Decrypt",
        )
        assert _is_kms_fallback_error(exc) is True


class TestKMSFallbackCounter:
    """Counter tăng sau mỗi fallback, raise khi vượt ngưỡng."""

    @pytest.fixture(autouse=True)
    def _reset_counter(self):
        from app.core.encryption import _reset_kms_fallback_count_for_tests
        _reset_kms_fallback_count_for_tests()
        yield
        _reset_kms_fallback_count_for_tests()

    @pytest.mark.asyncio
    async def test_counter_increments_on_fallback(self):
        from app.core.encryption import (
            generate_tenant_dek,
            get_kms_fallback_count,
            _reset_kms_fallback_count_for_tests,
        )
        _reset_kms_fallback_count_for_tests()
        assert get_kms_fallback_count() == 0

        exc = ClientError(
            {"Error": {"Code": "IncorrectKeyException", "Message": "x"}},
            "GenerateDataKey",
        )

        with patch("app.core.encryption.get_kms_client") as mock_get:
            mock_client = MagicMock()
            mock_client.generate_data_key = MagicMock(side_effect=exc)
            mock_get.return_value = mock_client

            # Fallback xảy ra -> counter tăng, kết quả vẫn OK
            plaintext, wrapped = await generate_tenant_dek("tenant-A")
            assert isinstance(plaintext, bytes) and len(plaintext) == 32
            assert isinstance(wrapped, bytes) and len(wrapped) > 32  # có nonce + tag
            assert plaintext != wrapped  # wrapped phải là ciphertext, không phải plaintext
            assert get_kms_fallback_count() == 1

    @pytest.mark.asyncio
    async def test_raises_after_threshold(self):
        """Khi vượt ngưỡng phải raise KMSUnavailableError thay vì fallback."""
        from app.core.encryption import (
            generate_tenant_dek,
            KMSUnavailableError,
            _KMS_FALLBACK_THRESHOLD,
        )

        exc = ClientError(
            {"Error": {"Code": "IncorrectKeyException", "Message": "x"}},
            "GenerateDataKey",
        )

        with patch("app.core.encryption.get_kms_client") as mock_get:
            mock_client = MagicMock()
            mock_client.generate_data_key = MagicMock(side_effect=exc)
            mock_get.return_value = mock_client

            # Gọi đủ _KMS_FALLBACK_THRESHOLD + 1 lần để trigger threshold
            for _ in range(_KMS_FALLBACK_THRESHOLD):
                await generate_tenant_dek("tenant-A")

            with pytest.raises(KMSUnavailableError) as excinfo:
                await generate_tenant_dek("tenant-A")
            assert "exceeded threshold" in str(excinfo.value)


# ── File DEK EncryptionContext bind doc_id ───────────────────────────────


class TestFileDEKContextBinding:
    """File DEK EncryptionContext phải chứa doc_id."""

    def test_context_with_doc_id(self):
        from app.utils.s3_storage import _encryption_context
        ctx = _encryption_context("tenant-X", doc_id="abc-123")
        assert ctx["tenant_name"] == "tenant-X"
        assert ctx["purpose"] == "file"
        assert ctx["doc_id"] == "abc-123"

    def test_context_without_doc_id(self):
        """Backward-compat: doc_id optional để không break dữ liệu cũ."""
        from app.utils.s3_storage import _encryption_context
        ctx = _encryption_context("tenant-X")
        assert ctx["tenant_name"] == "tenant-X"
        assert "doc_id" not in ctx

    @pytest.mark.asyncio
    async def test_generate_file_dek_passes_doc_id_to_context(self):
        """generate_file_dek phải truyền doc_id vào EncryptionContext của KMS."""
        from app.utils.s3_storage import (
            generate_file_dek,
            _reset_clients_for_tests,
        )
        _reset_clients_for_tests()

        with patch("app.utils.s3_storage.get_kms_client") as mock_get:
            mock_client = MagicMock()
            mock_client.generate_data_key = MagicMock(
                return_value={
                    "Plaintext": b"k" * 32,
                    "CiphertextBlob": b"wrapped-blob-bytes",
                }
            )
            mock_get.return_value = mock_client

            await generate_file_dek("tenant-Y", doc_id="doc-789")

            call_kwargs = mock_client.generate_data_key.call_args.kwargs
            assert call_kwargs["EncryptionContext"]["doc_id"] == "doc-789"
            assert call_kwargs["EncryptionContext"]["tenant_name"] == "tenant-Y"


# ── tenant_name immutability ─────────────────────────────────────────────


class TestTenantNameImmutability:
    """Gán lại tenant_name sau khi load phải raise AttributeError."""

    def test_rename_blocked_when_already_set(self):
        from app.models.tenant import Tenants

        tenant = Tenants(
            tenant_id=uuid.uuid4(),
            tenant_name="original",
            collection_name="COL_ORIGINAL",
            encrypted_dek=b"\x00" * 32,
        )
        # Gán trùng giá trị: OK
        tenant.tenant_name = "original"
        # Đổi sang tên khác: phải raise
        with pytest.raises(AttributeError):
            tenant.tenant_name = "renamed"

    def test_rename_allowed_during_init(self):
        """Trước khi tenant_id được gán, việc __init__ không bị block."""
        from app.models.tenant import Tenants

        # SQLAlchemy construct trống không có __init__ args
        tenant = Tenants()
        try:
            tenant.tenant_name = "first"
        except AttributeError:
            pytest.fail("Initial assignment should be allowed before tenant_id is set")


# ── Zeroize plaintext tenant DEK ─────────────────────────────────────────


class TestChatServiceZeroize:
    """Plaintext tenant DEK phải được zeroize sau khi request chat xong."""

    @pytest.mark.asyncio
    async def test_chat_zeroizes_dek_on_success(self):
        from app.services.chat_service import ChatService

        # Track zeroize calls
        with patch("app.services.chat_service.zeroize") as mock_zero:
            # Mock conversation repo
            conversation_repo = MagicMock()
            conversation_repo.get_by_id = AsyncMock(return_value=None)
            new_conv = MagicMock()
            new_conv.conversation_id = uuid.uuid4()
            new_conv.turn_count = 0
            new_conv.token_total = 0
            conversation_repo.create_conversation = AsyncMock(return_value=new_conv)
            conversation_repo.build_title = MagicMock(return_value="Title")
            conversation_repo.get_recent_messages = AsyncMock(return_value=[])
            conversation_repo.get_next_message_index = AsyncMock(return_value=0)
            conversation_repo.add_message = AsyncMock()
            conversation_repo.bump_conversation = AsyncMock()
            conversation_repo.commit = AsyncMock()
            conversation_repo.rollback = AsyncMock()

            # Mock retrieval
            retrieval_service = MagicMock()
            retrieval_service.run_search = AsyncMock(
                return_value={"results": [], "result_count": 0, "latency_ms": {}}
            )

            # Mock client factory
            client_factory = MagicMock()
            llm_result = MagicMock()
            llm_result.content = "answer"
            llm_result.prompt_tokens = 10
            llm_result.output_tokens = 5
            llm_client = MagicMock()
            llm_client.generate = AsyncMock(return_value=llm_result)
            client_factory.build_llm_client = MagicMock(return_value=llm_client)

            service = ChatService(
                retrieval_service=retrieval_service,
                client_factory=client_factory,
                conversation_repo=conversation_repo,
            )

            # Mock tenant with encrypted_dek
            tenant = MagicMock()
            tenant.tenant_name = "test_tenant"
            tenant.encrypted_dek = b"\x00" * 32

            fake_dek = b"\x42" * 32
            with patch(
                "app.services.chat_service.get_plaintext_dek",
                AsyncMock(return_value=fake_dek),
            ):
                from app.schemas.chat import ChatRequest
                request = ChatRequest(message="hi", top_k=3)
                await service.chat(tenant=tenant, user_id=uuid.uuid4(), request=request)

            # zeroize phải được gọi với plaintext DEK
            assert mock_zero.called
            assert mock_zero.call_args.args[0] == fake_dek

    @pytest.mark.asyncio
    async def test_chat_zeroizes_dek_on_error(self):
        """Phải zeroize cả khi raise exception."""
        from app.services.chat_service import ChatService

        with patch("app.services.chat_service.zeroize") as mock_zero:
            conversation_repo = MagicMock()
            # create_conversation là AsyncMock vì chat() gọi await lên nó
            conversation_repo.create_conversation = AsyncMock(
                side_effect=RuntimeError("DB boom")
            )
            conversation_repo.build_title = MagicMock(return_value="Title")
            conversation_repo.rollback = AsyncMock()

            retrieval_service = MagicMock()
            client_factory = MagicMock()

            service = ChatService(
                retrieval_service=retrieval_service,
                client_factory=client_factory,
                conversation_repo=conversation_repo,
            )

            tenant = MagicMock()
            tenant.tenant_name = "test_tenant"
            tenant.encrypted_dek = b"\x00" * 32

            fake_dek = b"\x77" * 32
            with patch(
                "app.services.chat_service.get_plaintext_dek",
                AsyncMock(return_value=fake_dek),
            ):
                from app.schemas.chat import ChatRequest
                request = ChatRequest(message="hi", top_k=3)
                with pytest.raises(RuntimeError):
                    await service.chat(
                        tenant=tenant, user_id=uuid.uuid4(), request=request
                    )

            # zeroize vẫn phải được gọi
            assert mock_zero.called
            assert mock_zero.call_args.args[0] == fake_dek


class TestRetrievalServiceZeroize:
    """run_search phải zeroize DEK trong finally."""

    @pytest.mark.asyncio
    async def test_run_search_zeroizes_dek(self):
        from app.services.retrieval_service import RetrievalService
        from app.schemas.retrieve import RetrieveRequest, SearchMode

        with patch("app.services.retrieval_service.zeroize") as mock_zero:
            qdrant_repo = MagicMock()
            embedding_client = MagicMock()
            # embed_text_async được await -> phải là AsyncMock
            embedding_client.embed_text_async = AsyncMock(
                return_value=[0.0] * 4
            )
            qdrant_repo.search = AsyncMock(return_value=[])
            service = RetrievalService(qdrant_repo, embedding_client)

            tenant = MagicMock()
            tenant.tenant_name = "test_tenant"
            tenant.encrypted_dek = b"\x00" * 32

            fake_dek = b"\x33" * 32
            with patch(
                "app.services.retrieval_service.get_plaintext_dek",
                AsyncMock(return_value=fake_dek),
            ):
                req = RetrieveRequest(query="q", top_k=3, mode=SearchMode.SEMANTIC_ONLY)
                await service.run_search(tenant, req)

            assert mock_zero.called
            assert mock_zero.call_args.args[0] == fake_dek

    @pytest.mark.asyncio
    async def test_run_search_zeroizes_dek_on_error(self):
        """Phải zeroize khi strategy raise."""
        from app.services.retrieval_service import RetrievalService
        from app.schemas.retrieve import RetrieveRequest, SearchMode

        with patch("app.services.retrieval_service.zeroize") as mock_zero:
            qdrant_repo = MagicMock()
            embedding_client = MagicMock()
            service = RetrievalService(qdrant_repo, embedding_client)

            tenant = MagicMock()
            tenant.tenant_name = "test_tenant"
            tenant.encrypted_dek = b"\x00" * 32

            fake_dek = b"\x55" * 32
            with patch(
                "app.services.retrieval_service.get_plaintext_dek",
                AsyncMock(return_value=fake_dek),
            ):
                # Force strategy method to raise so we hit the finally block.
                req = RetrieveRequest(query="q", top_k=3, mode=SearchMode.SEMANTIC_ONLY)
                with patch.object(
                    service,
                    "_run_semantic_only",
                    AsyncMock(side_effect=RuntimeError("boom")),
                ):
                    with pytest.raises(RuntimeError):
                        await service.run_search(tenant, req)

            assert mock_zero.called
            assert mock_zero.call_args.args[0] == fake_dek
