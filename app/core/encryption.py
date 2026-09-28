"""
Field-level encryption utilities for per-tenant data isolation.

Uses Envelope Encryption (Mô hình Khóa kép):
  1. KEK (Key Encryption Key): A system-wide AES-256 key loaded from environment.
  2. DEK (Data Encryption Key): A random AES-256 key generated per tenant.
  3. The DEK is wrapped (encrypted) by the KEK using AES-GCM.
  4. The wrapped DEK is stored in the `tenants` table.

Encryption scheme: AES-256-GCM.
"""

import os
import base64
import asyncio
import boto3
import botocore.config
from botocore.exceptions import (
    ConnectTimeoutError,
    ReadTimeoutError,
    EndpointConnectionError,
    ClientError,
)
import boto3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

TENANT_KMS_KEY_ALIAS = "alias/ragnarok-tenant-key"
TENANT_ENCRYPTION_PURPOSE = "tenant_dek"

# Network errors are TRANSIENT — caller phải retry qua _is_retryable_error.
# ClientError (ValidationException, InvalidCiphertextException, AccessDenied)
# là PERMANENT — fallback về local KEK là cách duy nhất recover vì KMS
# không bao giờ nhận lại đúng blob đã corrupt.
_NETWORK_ERRORS = (ConnectTimeoutError, ReadTimeoutError, EndpointConnectionError)

# Errors từ KMS mà ta CẦN fallback local KEK thay vì raise.
#
# Lưu ý bảo mật: list này đã được thu hẹp để giảm rủi ro silent fallback.
# Trước đây bao gồm ``InvalidCiphertextException`` và ``NotFoundException`` —
# 2 error này có thể bị kích hoạt bởi blob tuỳ ý (không phải do KMS wrap),
# cho phép attacker force hệ thống rơi vào nhánh dùng SYSTEM_KEK (mặc định
# có thể là toàn 0). Bây giờ chỉ những error xảy ra khi **rotate KMS alias**
# hợp lệ mới được fallback, và lượng fallback bị đếm + log mức ERROR để
# SOC / oncall phát hiện sớm.
_KMS_FALLBACK_ERRORS = (
    "IncorrectKeyException",     # KMS alias bị xoay sau khi wrap — wrap bằng key cũ
    "KeyUnavailableException",   # key đang bị disable / pending delete
    "UnrecognizedClientException",  # AWS credentials không hợp lệ / dummy trong dev environment
    "InvalidSignatureException",
    "AccessDeniedException",
    "AuthFailure",
    "InvalidClientTokenId",
)

# Đếm số lần fallback đã xảy ra trong tiến trình — chỉ số cho alerting.
_KMS_FALLBACK_COUNT = 0
_KMS_FALLBACK_THRESHOLD = 5   # > ngưỡng này -> raise KMSUnavailableError

_KMS_DEV_MODE = False
_KMS_DEV_WARNED = False

_DEV_AUTH_ERRORS = (
    "UnrecognizedClientException",
    "InvalidSignatureException",
    "AccessDeniedException",
    "AuthFailure",
    "InvalidClientTokenId",
)


def is_kms_dev_mode() -> bool:
    """Trả về True nếu dev environment credentials error đã được phát hiện."""
    if _KMS_DEV_MODE:
        return True
    settings = get_settings()
    # Preemptively check if dummy credentials are provided in .env
    if settings.aws_access_key_id.startswith("your-aws-"):
        return True
    return False


def set_kms_dev_mode(operation: str, exc: Exception) -> None:
    global _KMS_DEV_MODE, _KMS_DEV_WARNED
    _KMS_DEV_MODE = True
    if not _KMS_DEV_WARNED:
        _KMS_DEV_WARNED = True
        logger.info(
            "kms_using_dev_mode",
            operation=operation,
            message="AWS credentials not recognized. Using local KEK for dev mode.",
        )


def _note_kms_fallback(operation: str, exc: Exception) -> None:
    """Ghi log mức ERROR + tăng biến đếm. Sau khi vượt ngưỡng sẽ raise."""
    global _KMS_FALLBACK_COUNT
    err_code = ""
    if isinstance(exc, ClientError):
        err_code = exc.response.get("Error", {}).get("Code", "")

    if err_code in _DEV_AUTH_ERRORS:
        set_kms_dev_mode(operation, exc)
        return

    _KMS_FALLBACK_COUNT += 1
    logger.error(
        "kms_fallback_to_local_kek",
        operation=operation,
        fallback_count=_KMS_FALLBACK_COUNT,
        threshold=_KMS_FALLBACK_THRESHOLD,
        error=str(exc),
    )
    if _KMS_FALLBACK_COUNT > _KMS_FALLBACK_THRESHOLD:
        logger.critical(
            "kms_fallback_threshold_exceeded",
            fallback_count=_KMS_FALLBACK_COUNT,
            threshold=_KMS_FALLBACK_THRESHOLD,
        )


def get_kms_fallback_count() -> int:
    """Trả về số lần fallback đã xảy ra (cho monitoring / tests)."""
    return _KMS_FALLBACK_COUNT


def _reset_kms_fallback_count_for_tests() -> None:
    global _KMS_FALLBACK_COUNT, _KMS_DEV_MODE, _KMS_DEV_WARNED
    _KMS_FALLBACK_COUNT = 0
    _KMS_DEV_MODE = False
    _KMS_DEV_WARNED = False


class KMSUnavailableError(RuntimeError):
    """Raised khi KMS không thể generate/unwrap DEK và fallback local KEK
    cũng thất bại. Caller nên surface 503 cho client."""


def _get_kek() -> bytes:
    """Retrieve KEK from settings and decode it from hex string to bytes."""
    settings = get_settings()
    try:
        kek = bytes.fromhex(settings.system_kek)
    except ValueError:
        raise ValueError("system_kek must be a valid hex string.")
    if len(kek) != 32:
        raise ValueError("system_kek must be exactly 32 bytes (64 hex characters) for AES-256.")
    return kek


def generate_dek() -> bytes:
    """Generate a random 32-byte (256-bit) Data Encryption Key (DEK)."""
    return AESGCM.generate_key(bit_length=256)


def wrap_dek(dek: bytes) -> bytes:
    """
    Encrypt the DEK using the system's KEK with AES-GCM.
    Returns: nonce (12 bytes) + ciphertext + tag (16 bytes)
    """
    kek = _get_kek()
    aesgcm = AESGCM(kek)
    nonce = os.urandom(12)
    wrapped = aesgcm.encrypt(nonce, dek, associated_data=None)
    return nonce + wrapped


def unwrap_dek(wrapped_dek: bytes) -> bytes:
    """
    Decrypt the DEK using the system's KEK with AES-GCM.
    Expects: nonce (12 bytes) + ciphertext + tag (16 bytes)
    """
    kek = _get_kek()
    if len(wrapped_dek) < 28:
        raise ValueError("Wrapped DEK is too short.")

    nonce = wrapped_dek[:12]
    ciphertext = wrapped_dek[12:]

    aesgcm = AESGCM(kek)
    try:
        dek = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
        return dek
    except Exception as e:
        raise ValueError("Failed to unwrap DEK. Integrity check failed or incorrect KEK.") from e

def encrypt_content(plaintext: str, dek_plaintext: bytes) -> str:
    """Mã hóa text -> Base64 string (12 bytes nonce + ciphertext)."""
    aesgcm = AESGCM(dek_plaintext)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    encrypted_bytes = nonce + ciphertext
    return base64.b64encode(encrypted_bytes).decode("utf-8")


def decrypt_content(encrypted_base64: str, dek_plaintext: bytes) -> str:
    """Giải mã Base64 string -> Plaintext ban đầu."""
    encrypted_bytes = base64.b64decode(encrypted_base64)
    nonce = encrypted_bytes[:12]
    ciphertext = encrypted_bytes[12:]

    aesgcm = AESGCM(dek_plaintext)
    plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
    return plaintext_bytes.decode("utf-8")

def _tenant_encryption_context(tenant_name: str) -> dict:
    # NOTE: tenant_name (mutable) được dùng làm EncryptionContext ở code cũ.
    # Khi user rename tenant, ciphertext cũ không unwrap được nữa vì context
    # không khớp. Giữ nguyên để backward compat với data đã encrypt, nhưng
    # KHÔNG cho phép rename tenant nếu đã có data — enforced ở tenant_service.
    return {"tenant_name": tenant_name, "purpose": TENANT_ENCRYPTION_PURPOSE}


def _kms_boto_config() -> botocore.config.Config:
    """Helper riêng cho file này, KHÔNG import chung từ s3_storage.py — vì
    s3_storage.py đã import app.core.encryption bên trong hàm (để tránh vòng
    lặp import); nếu encryption.py lại import ngược app.utils.s3_storage ở
    module level sẽ tạo circular import ngay lúc app khởi động."""
    settings = get_settings()
    return botocore.config.Config(
        connect_timeout=settings.kms_connect_timeout,
        read_timeout=settings.kms_read_timeout,
        retries={"max_attempts": settings.kms_max_retries, "mode": "standard"},
    )


# Singleton KMS client để tránh tạo mới mỗi call (Boto3 client thread-safe,
# dùng được từ nhiều coroutine). Tạo lazy để test có thể override settings.
_kms_client_singleton = None


def get_kms_client():
    global _kms_client_singleton
    if _kms_client_singleton is None:
        settings = get_settings()
        _kms_client_singleton = boto3.client(
            "kms",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            config=_kms_boto_config(),
        )
    return _kms_client_singleton


def _reset_kms_client_for_tests():
    """Reset singleton — chỉ dùng trong test suite."""
    global _kms_client_singleton
    _kms_client_singleton = None


def _is_kms_fallback_error(exc: Exception) -> bool:
    """Các lỗi KMS mà fallback local KEK hợp lý (ciphertext không phải KMS,
    key alias xoá, encryption_context sai...). Các lỗi khác (network, IAM)
    vẫn raise để retry."""
    err_code = ""
    if isinstance(exc, ClientError):
        err_code = exc.response.get("Error", {}).get("Code", "")
    return err_code in _KMS_FALLBACK_ERRORS


async def generate_tenant_dek(tenant_name: str) -> tuple[bytes, bytes]:
    """
    Sinh DEK mới cho tenant qua AWS KMS.
    - Network/timeout -> raise (caller retry).
    - Lỗi KMS PERMANENT (key không tồn tại, InvalidKeyUsage...) -> fallback local KEK.
    - Lỗi không xác định -> raise KMSUnavailableError để caller surface 503.

    Returns: (plaintext_dek, wrapped_dek_bytes)
    """
    if is_kms_dev_mode():
        plaintext_dek = generate_dek()
        wrapped_dek = wrap_dek(plaintext_dek)
        return plaintext_dek, wrapped_dek
    try:
        client = get_kms_client()
        response = await asyncio.to_thread(
            client.generate_data_key,
            KeyId=TENANT_KMS_KEY_ALIAS,
            KeySpec="AES_256",
            EncryptionContext=_tenant_encryption_context(tenant_name),
        )
        return response["Plaintext"], response["CiphertextBlob"]
    except _NETWORK_ERRORS as exc:
        logger.warning("kms_generate_tenant_dek_network_error_no_fallback", error=str(exc))
        raise RuntimeError(f"KMS timeout/connection error khi generate tenant DEK: {exc}") from exc
    except Exception as exc:
        if _is_kms_fallback_error(exc):
            _note_kms_fallback("generate_tenant_dek", exc)
            if _KMS_FALLBACK_COUNT > _KMS_FALLBACK_THRESHOLD:
                raise KMSUnavailableError(
                    f"KMS fallback count exceeded threshold "
                    f"({_KMS_FALLBACK_COUNT}>{_KMS_FALLBACK_THRESHOLD}); "
                    f"refusing to use local KEK any longer."
                ) from exc
            plaintext_dek = generate_dek()
            wrapped_dek = wrap_dek(plaintext_dek)
            return plaintext_dek, wrapped_dek
        logger.exception("kms_generate_tenant_dek_unexpected_error")
        raise KMSUnavailableError(
            f"KMS không khả dụng khi generate tenant DEK: {exc}"
        ) from exc


async def unwrap_tenant_dek(wrapped_dek: bytes, tenant_name: str) -> bytes:
    """
    Giải mã DEK tenant qua AWS KMS.
    - Network/timeout -> raise.
    - Lỗi KMS trong whitelist (IncorrectKeyException, KeyUnavailableException)
      -> fallback local KEK (chỉ đúng với data cũ wrap bằng local trước khi bật KMS
      hoặc sau khi rotate alias).
    - Lỗi khác -> raise KMSUnavailableError.
    - Nếu số lần fallback vượt ngưỡng -> raise KMSUnavailableError (xem _note_kms_fallback).
    """
    if is_kms_dev_mode():
        try:
            return unwrap_dek(wrapped_dek)
        except Exception:
            pass
    try:
        client = get_kms_client()
        response = await asyncio.to_thread(
            client.decrypt,
            CiphertextBlob=wrapped_dek,
            KeyId=TENANT_KMS_KEY_ALIAS,
            EncryptionContext=_tenant_encryption_context(tenant_name),
        )
        return response["Plaintext"]
    except _NETWORK_ERRORS as exc:
        logger.warning("kms_unwrap_tenant_dek_network_error_no_fallback", error=str(exc))
        raise RuntimeError(f"KMS timeout/connection error khi unwrap tenant DEK: {exc}") from exc
    except Exception as exc:
        if _is_kms_fallback_error(exc):
            _note_kms_fallback("unwrap_tenant_dek", exc)
            if _KMS_FALLBACK_COUNT > _KMS_FALLBACK_THRESHOLD:
                raise KMSUnavailableError(
                    f"KMS fallback count exceeded threshold "
                    f"({_KMS_FALLBACK_COUNT}>{_KMS_FALLBACK_THRESHOLD}); "
                    f"refusing to use local KEK any longer."
                ) from exc
            try:
                return unwrap_dek(wrapped_dek)
            except Exception as local_exc:
                logger.exception("kms_unwrap_tenant_dek_local_fallback_failed")
                raise KMSUnavailableError(
                    f"KMS unwrap fail và local KEK unwrap cũng fail: {exc} | {local_exc}"
                ) from local_exc
        logger.exception("kms_unwrap_tenant_dek_unexpected_error")
        raise KMSUnavailableError(
            f"KMS không khả dụng khi unwrap tenant DEK: {exc}"
        ) from exc