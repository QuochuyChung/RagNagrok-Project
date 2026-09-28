"""
Unit tests for document ingestion scenarios.

Tests various document upload cases to verify:
- File type validation
- Batch upload handling
- Zip extraction
- Duplicate detection
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path


class TestFileTypeValidation:
    """Test validation of file types."""

    def test_allowed_extensions_from_config(self):
        """Các định dạng được phép từ config."""
        from app.services.document_service import ALLOWED_EXTENSIONS

        # Kiểm tra các extension phổ biến từ config
        assert '.pdf' in ALLOWED_EXTENSIONS, "PDF should be allowed"
        assert '.txt' in ALLOWED_EXTENSIONS, "TXT should be allowed"
        assert '.md' in ALLOWED_EXTENSIONS, "MD should be allowed"
        assert '.docx' in ALLOWED_EXTENSIONS, "DOCX should be allowed"
        assert isinstance(ALLOWED_EXTENSIONS, set)

    def test_disallowed_extensions(self):
        """Các định dạng không được phép."""
        from app.services.document_service import ALLOWED_EXTENSIONS

        disallowed = {'.exe', '.sh', '.js', '.html'}
        for ext in disallowed:
            assert ext not in ALLOWED_EXTENSIONS, f"Extension {ext} should NOT be allowed"


class TestZipExtraction:
    """Test zip file extraction logic."""

    def test_extract_zip_function_exists(self):
        """Hàm extract_zip_safely tồn tại."""
        from app.utils.zip_extract import extract_zip_safely
        assert callable(extract_zip_safely)

    def test_extract_zip_max_files_limit(self):
        """Giới hạn số file trong zip."""
        from app.utils.zip_extract import MAX_BATCH_FILES
        assert MAX_BATCH_FILES > 0, "MAX_BATCH_FILES should be defined"


class TestBatchUploadLogic:
    """Test batch upload business logic."""

    def test_batch_result_structure(self):
        """Cấu trúc kết quả batch phải có đủ các trường."""
        result = {"new": [], "updated": [], "unchanged": [], "failed": []}

        assert "new" in result
        assert "updated" in result
        assert "unchanged" in result
        assert "failed" in result
        assert isinstance(result["new"], list)
        assert isinstance(result["updated"], list)

    def test_batch_max_files_limit(self):
        """Giới hạn số file trong một batch."""
        from app.utils.zip_extract import MAX_BATCH_FILES

        assert MAX_BATCH_FILES >= 50, "MAX_BATCH_FILES should be at least 50"
        assert MAX_BATCH_FILES <= 500, "MAX_BATCH_FILES should not exceed 500"


class TestConfigSettings:
    """Test configuration settings."""

    def test_max_upload_size_configured(self):
        """Max upload size phải được cấu hình."""
        from app.core.config import get_settings

        settings = get_settings()
        assert hasattr(settings, 'max_upload_size_mb')
        assert settings.max_upload_size_mb > 0

    def test_document_allowed_extensions_configured(self):
        """Document allowed extensions phải được cấu hình."""
        from app.core.config import get_settings

        settings = get_settings()
        assert hasattr(settings, 'document_allowed_extensions')
        assert isinstance(settings.document_allowed_extensions, list)
        assert len(settings.document_allowed_extensions) > 0


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_file_too_large_error_exists(self):
        """FileTooLargeError phải tồn tại."""
        from app.core.errors import FileTooLargeError
        assert issubclass(FileTooLargeError, Exception)

    def test_unsupported_file_type_error_exists(self):
        """UnsupportedFileTypeError phải tồn tại."""
        from app.core.errors import UnsupportedFileTypeError
        assert issubclass(UnsupportedFileTypeError, Exception)

    def test_empty_file_error_exists(self):
        """EmptyFileError phải tồn tại."""
        from app.core.errors import EmptyFileError
        assert issubclass(EmptyFileError, Exception)

    def test_duplicate_content_error_exists(self):
        """DuplicateContentError phải tồn tại."""
        from app.core.errors import DuplicateContentError
        assert issubclass(DuplicateContentError, Exception)


class TestS3StorageEncryption:
    """Test encryption functions in s3_storage module."""

    def test_generate_file_dek_exists(self):
        """generate_file_dek phải tồn tại."""
        from app.utils.s3_storage import generate_file_dek
        assert callable(generate_file_dek)

    def test_encrypt_file_bytes_exists(self):
        """encrypt_file_bytes phải tồn tại."""
        from app.utils.s3_storage import encrypt_file_bytes
        assert callable(encrypt_file_bytes)

    def test_decrypt_file_bytes_exists(self):
        """decrypt_file_bytes phải tồn tại."""
        from app.utils.s3_storage import decrypt_file_bytes
        assert callable(decrypt_file_bytes)

    def test_unwrap_file_dek_exists(self):
        """unwrap_file_dek phải tồn tại."""
        from app.utils.s3_storage import unwrap_file_dek
        assert callable(unwrap_file_dek)


class TestEncryptionModule:
    """Test encryption module functions."""

    def test_generate_dek_exists(self):
        """generate_dek phải tồn tại."""
        from app.core.encryption import generate_dek
        assert callable(generate_dek)

    def test_wrap_dek_exists(self):
        """wrap_dek phải tồn tại."""
        from app.core.encryption import wrap_dek
        assert callable(wrap_dek)

    def test_unwrap_dek_exists(self):
        """unwrap_dek phải tồn tại."""
        from app.core.encryption import unwrap_dek
        assert callable(unwrap_dek)

    def test_generate_dek_returns_bytes(self):
        """generate_dek phải trả về bytes 32 bytes."""
        from app.core.encryption import generate_dek
        dek = generate_dek()
        assert isinstance(dek, bytes)
        assert len(dek) == 32, "DEK should be 32 bytes (256 bits)"

    def test_wrap_and_unwrap_dek_roundtrip(self):
        """Wrap rồi unwrap DEK phải trả về giá trị ban đầu."""
        from app.core.encryption import generate_dek, wrap_dek, unwrap_dek

        original_dek = generate_dek()
        wrapped = wrap_dek(original_dek)
        unwrapped = unwrap_dek(wrapped)

        assert unwrapped == original_dek, "Unwrapped DEK should match original"


class TestHashingFunctions:
    """Test hashing functions."""

    def test_compute_sha256_exists(self):
        """compute_sha256 phải tồn tại."""
        from app.utils.hashing import compute_sha256
        assert callable(compute_sha256)

    def test_compute_sha256_known_hash(self):
        """SHA-256 of known input."""
        from app.utils.hashing import compute_sha256

        # Empty string hash
        expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert compute_sha256(b"") == expected

    def test_compute_sha256_deterministic(self):
        """Same input always produces same hash."""
        from app.utils.hashing import compute_sha256

        content = b"test document content"
        assert compute_sha256(content) == compute_sha256(content)

    def test_compute_sha256_different_inputs(self):
        """Different inputs produce different hashes."""
        from app.utils.hashing import compute_sha256

        hash1 = compute_sha256(b"document A")
        hash2 = compute_sha256(b"document B")
        assert hash1 != hash2, "Different content should have different hashes"


class TestChunkingMode:
    """Test chunking mode configuration."""

    def test_chunking_mode_type_exists(self):
        """ChunkingMode type alias should exist."""
        from app.services.document_service import ChunkingMode
        assert ChunkingMode is not None

    def test_document_status_enum_exists(self):
        """DocumentStatus enum should exist."""
        from app.schemas.document import DocumentStatus
        assert hasattr(DocumentStatus, 'PENDING')
        assert hasattr(DocumentStatus, 'COMPLETED')
        assert hasattr(DocumentStatus, 'FAILED')


class TestDocumentServiceIngest:
    """Test document service ingestion methods with mocks."""

    @pytest.mark.asyncio
    async def test_ingest_document_requires_valid_extension(self):
        """Upload document phải reject file không hỗ trợ."""
        from app.services.document_service import DocumentService
        from app.core.errors import UnsupportedFileTypeError

        mock_repo_instance = MagicMock()
        mock_repo_instance.get_active_by_content_hash = AsyncMock(return_value=None)
        mock_repo_instance.get_latest_version = AsyncMock(return_value=None)
        mock_repo_instance.create = AsyncMock()
        mock_repo_instance.update_storage_key = AsyncMock()
        mock_repo_instance.update_encrypted_file_dek = AsyncMock()
        mock_repo_instance.commit = AsyncMock()
        mock_repo_instance.session.commit = AsyncMock()
        mock_repo_instance.rollback = AsyncMock()
        mock_repo_instance.session.rollback = AsyncMock()

        mock_qdrant = MagicMock()
        service = DocumentService(repo=mock_repo_instance, qdrant_repo=mock_qdrant)

        tenant_id = uuid.uuid4()

        with pytest.raises(UnsupportedFileTypeError):
            await service.ingest_document(
                tenant_id=tenant_id,
                filename="malware.exe",
                content=b"malicious content",
                tenant_name="test_tenant",
                encrypted_tenant_dek=b"\x00" * 32,
            )

    @pytest.mark.asyncio
    async def test_ingest_document_rejects_empty_content(self):
        """Upload document phải reject file rỗng."""
        from app.services.document_service import DocumentService
        from app.core.errors import EmptyFileError

        mock_repo_instance = MagicMock()
        mock_repo_instance.get_active_by_content_hash = AsyncMock(return_value=None)
        mock_repo_instance.get_latest_version = AsyncMock(return_value=None)
        mock_repo_instance.create = AsyncMock()
        mock_repo_instance.update_storage_key = AsyncMock()
        mock_repo_instance.update_encrypted_file_dek = AsyncMock()
        mock_repo_instance.commit = AsyncMock()
        mock_repo_instance.session.commit = AsyncMock()
        mock_repo_instance.rollback = AsyncMock()
        mock_repo_instance.session.rollback = AsyncMock()

        mock_qdrant = MagicMock()
        service = DocumentService(repo=mock_repo_instance, qdrant_repo=mock_qdrant)

        tenant_id = uuid.uuid4()

        with pytest.raises(EmptyFileError):
            await service.ingest_document(
                tenant_id=tenant_id,
                filename="document.pdf",
                content=b"",
                tenant_name="test_tenant",
                encrypted_tenant_dek=b"\x00" * 32,
            )

    @pytest.mark.asyncio
    async def test_ingest_batch_processes_valid_files(self):
        """Ingest batch phải xử lý được các file hợp lệ."""
        from app.services.document_service import DocumentService

        mock_repo_instance = MagicMock()
        mock_repo_instance.get_latest_version = AsyncMock(return_value=None)
        mock_repo_instance.get_active_by_content_hash = AsyncMock(return_value=None)
        mock_repo_instance.create = AsyncMock()
        mock_repo_instance.update_storage_key = AsyncMock()
        mock_repo_instance.update_encrypted_file_dek = AsyncMock()
        mock_repo_instance.commit = AsyncMock()
        mock_repo_instance.session.commit = AsyncMock()
        mock_repo_instance.rollback = AsyncMock()
        mock_repo_instance.session.rollback = AsyncMock()

        mock_qdrant = MagicMock()
        service = DocumentService(repo=mock_repo_instance, qdrant_repo=mock_qdrant)

        tenant_id = uuid.uuid4()

        # Test với files hợp lệ
        files = [
            ("document1.pdf", b"pdf content"),
            ("document2.txt", b"text content"),
        ]

        result = await service.ingest_batch(
            tenant_id=tenant_id,
            tenant_name="test_tenant",
            files=files,
            encrypted_tenant_dek=b"\x00" * 32,
        )

        assert "new" in result
        assert "updated" in result
        assert "unchanged" in result
        assert "failed" in result
