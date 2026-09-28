import asyncio
import boto3
import botocore.config
import datetime
from botocore.exceptions import (
    ConnectTimeoutError,
    ReadTimeoutError,
    EndpointConnectionError,
    ClientError,
)
import base64
import os
from pathlib import Path
from app.core.config import get_settings
from app.core.logging import get_logger
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = get_logger(__name__)

KMS_KEY_ALIAS = "alias/ragnarok-file-key"
ENCRYPTION_PURPOSE = "file"

# Nhóm lỗi mạng/timeout THẬT SỰ (transient) — nên raise để _is_retryable_error()
# ở document_service.py bắt được và tự động retry với backoff.
# KHÔNG gồm ClientError (AccessDenied, NoSuchKey, key không tồn tại...) vì đó
# là lỗi PERMANENT, retry vô ích -> giữ nguyên đi theo nhánh fallback cũ.
_NETWORK_ERRORS = (ConnectTimeoutError, ReadTimeoutError, EndpointConnectionError)

# Errors từ KMS mà fallback local KEK là hợp lý. Đã được thu hẹp tương tự
# danh sách trong app.core.encryption: chỉ những error xảy ra khi rotate
# KMS alias hợp lệ mới được fallback (IncorrectKeyException,
# KeyUnavailableException). Việc đếm fallback + giới hạn ngưỡng được chia sẻ
# qua ``app.core.encryption`` để có một cảnh báo duy nhất cho cả process.
_KMS_FALLBACK_ERRORS = (
    "IncorrectKeyException",
    "KeyUnavailableException",
    "UnrecognizedClientException",
    "InvalidSignatureException",
    "AccessDeniedException",
    "AuthFailure",
    "InvalidClientTokenId",
)


def _s3_boto_config() -> botocore.config.Config:
    settings = get_settings()
    return botocore.config.Config(
        connect_timeout=settings.s3_connect_timeout,
        read_timeout=settings.s3_read_timeout,
        retries={"max_attempts": settings.s3_max_retries, "mode": "standard"},
    )


def _kms_boto_config() -> botocore.config.Config:
    settings = get_settings()
    return botocore.config.Config(
        connect_timeout=settings.kms_connect_timeout,
        read_timeout=settings.kms_read_timeout,
        retries={"max_attempts": settings.kms_max_retries, "mode": "standard"},
    )


# Singleton S3 client — Boto3 client là thread-safe, dùng được từ nhiều
# coroutine. Trước đây mỗi call tạo client mới → tăng overhead + dễ leak
# connection pool khi retry burst.
_s3_client_singleton = None
_kms_client_singleton = None


def get_s3_client():
    global _s3_client_singleton
    if _s3_client_singleton is None:
        settings = get_settings()
        _s3_client_singleton = boto3.client(
            "s3",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            config=_s3_boto_config(),
        )
    return _s3_client_singleton


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


def _reset_clients_for_tests():
    """Reset singleton — chỉ dùng trong test suite."""
    global _s3_client_singleton, _kms_client_singleton
    _s3_client_singleton = None
    _kms_client_singleton = None


def _is_kms_fallback_error(exc: Exception) -> bool:
    err_code = ""
    if isinstance(exc, ClientError):
        err_code = exc.response.get("Error", {}).get("Code", "")
    return err_code in _KMS_FALLBACK_ERRORS


def _build_key(tenant_name: str, doc_type: str, ingested_at: datetime.datetime, doc_id: str, ext: str) -> str:
    """
    Không dùng doc_name trong key — tránh lộ tên tài liệu thật trên S3 Console
    (S3 Console không hỗ trợ custom column, key/Name là chỗ duy nhất hiện được
    trong danh sách mà không cần click từng object). doc_type + ingested_at đủ
    để phân biệt/tra cứu trên Console mà không lộ nội dung nhạy cảm. doc_id
    luôn đứng cuối làm chốt an toàn (unique tuyệt đối, không đụng version khác).
    """
    safe_tenant = tenant_name.replace("/", "_")
    safe_type = doc_type.replace("/", "_")
    ts = ingested_at.strftime("%Y%m%dT%H%M%S")
    return f"{safe_tenant}/{safe_type}_{ts}__{doc_id}.{ext.lstrip('.')}"


async def save_file_to_s3(
    *, tenant_name: str, doc_type: str, ingested_at: datetime.datetime,
    doc_id: str, ext: str, content: bytes,
) -> str:
    """Trả về key đã dùng để ghi — caller PHẢI lưu key này vào DB (storage_key).

    Timeout/mạng chậm -> raise RuntimeError để tầng retry bắt được, KHÔNG rơi
    vào fallback local nữa (khác hành vi cũ). Fallback local chỉ còn áp dụng
    cho lỗi permanent (access denied, bucket sai tên...).
    """
    settings = get_settings()
    key = _build_key(tenant_name, doc_type, ingested_at, doc_id, ext)
    try:
        client = get_s3_client()
        await asyncio.to_thread(
            client.put_object, Bucket=settings.s3_bucket_name, Key=key, Body=content,
        )
    except _NETWORK_ERRORS as exc:
        logger.warning("s3_put_object_network_error_no_fallback", key=key, error=str(exc))
        raise RuntimeError(f"S3 timeout/connection error khi ghi {key}: {exc}") from exc
    except Exception as exc:
        logger.warning("s3_put_object_failed_using_local_fallback", key=key, error=str(exc))
        local_path = Path("storage/s3_fallback") / key
        local_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(local_path.write_bytes, content)
    return key


async def read_file_from_s3_by_key(key: str) -> bytes:
    """Đọc file từ S3. Fallback sang local disk CHỈ áp dụng cho lỗi permanent
    (NoSuchKey, access denied...) — không áp dụng cho timeout/mạng chậm, vì
    dùng local trong lúc mạng chỉ đang chậm tạm thời dễ đọc nhầm bản rác nếu
    có sẵn file local trùng tên do 1 lần fallback trước đó để lại."""
    settings = get_settings()
    try:
        client = get_s3_client()
        response = await asyncio.to_thread(
            client.get_object, Bucket=settings.s3_bucket_name, Key=key
        )
        return await asyncio.to_thread(response["Body"].read)
    except _NETWORK_ERRORS as exc:
        logger.warning("s3_get_object_network_error_no_fallback", key=key, error=str(exc))
        raise RuntimeError(f"S3 timeout/connection error khi đọc {key}: {exc}") from exc
    except Exception as exc:
        local_path = Path("storage/s3_fallback") / key
        if local_path.exists():
            logger.info("s3_get_object_fallback_to_local", key=key)
            return await asyncio.to_thread(local_path.read_bytes)
        raise FileNotFoundError(f"File không tồn tại trên S3/Local: {key}") from exc


async def delete_file_from_s3_by_key(key: str) -> None:
    """Best-effort delete — giữ nguyên hành vi cũ (chỉ log, không raise) vì
    caller coi thao tác này là best-effort cleanup, không phải bước bắt buộc."""
    settings = get_settings()
    try:
        client = get_s3_client()
        await asyncio.to_thread(client.delete_object, Bucket=settings.s3_bucket_name, Key=key)
    except Exception as exc:
        logger.warning("s3_delete_object_failed", key=key, error=str(exc))
        local_path = Path("storage/s3_fallback") / key
        if local_path.exists():
            local_path.unlink()


# def get_kms_client():
#     settings = get_settings()
#     return boto3.client(
#         "kms",
#         region_name=settings.aws_region,
#         aws_access_key_id=settings.aws_access_key_id,
#         aws_secret_access_key=settings.aws_secret_access_key,
#         config=_kms_boto_config(),
#     )


def _encryption_context(tenant_name: str, doc_id: str | None = None) -> dict:
    """EncryptionContext / AAD cho file DEK.

    Bind theo tenant_name + doc_id (immutable identifier) để file DEK không
    bị swap giữa 2 file cùng tenant. ``doc_id`` optional để giữ backward-compat
    với data wrap trước đó (chưa có doc_id trong context) — trong trường hợp
    đó KMS vẫn reject vì context không khớp nếu blob mới bị unwrap với tenant
    khác; chỉ swap giữa cùng tenant mới bị chặn.
    """
    ctx = {"tenant_name": tenant_name, "purpose": ENCRYPTION_PURPOSE}
    if doc_id:
        ctx["doc_id"] = doc_id
    return ctx


async def generate_file_dek(tenant_name: str, doc_id: str | None = None) -> tuple[bytes, str]:
    """Sinh DEK mới cho file qua AWS KMS.

    Args:
        tenant_name: Tên tenant — dùng trong EncryptionContext / AAD.
        doc_id: UUID của document — bind vào EncryptionContext để file DEK
                không bị swap giữa 2 file cùng tenant.

    - Network/timeout -> raise (caller retry).
    - Lỗi KMS PERMANENT (key không tồn tại, InvalidKeyUsage...) -> fallback local KEK.
    - Lỗi không xác định -> raise để caller xử lý (không âm thầm fallback).
    - Sau khi số lần fallback vượt ngưỡng -> raise KMSUnavailableError.
    """
    from app.core.encryption import (
        is_kms_dev_mode,
        generate_dek,
        wrap_dek,
    )
    if is_kms_dev_mode():
        plaintext_dek = generate_dek()
        wrapped_dek = wrap_dek(plaintext_dek)
        encrypted_dek_b64 = base64.b64encode(wrapped_dek).decode("utf-8")
        return plaintext_dek, encrypted_dek_b64
    try:
        client = get_kms_client()
        response = await asyncio.to_thread(
            client.generate_data_key,
            KeyId=KMS_KEY_ALIAS,
            KeySpec="AES_256",
            EncryptionContext=_encryption_context(tenant_name, doc_id),
        )
        plaintext_dek = response["Plaintext"]
        encrypted_dek_b64 = base64.b64encode(response["CiphertextBlob"]).decode("utf-8")
        return plaintext_dek, encrypted_dek_b64
    except _NETWORK_ERRORS as exc:
        logger.warning("kms_generate_dek_network_error_no_fallback", error=str(exc))
        raise RuntimeError(f"KMS timeout/connection error khi generate DEK: {exc}") from exc
    except Exception as exc:
        if _is_kms_fallback_error(exc):
            from app.core.encryption import (
                _note_kms_fallback,
                _KMS_FALLBACK_THRESHOLD,
                _KMS_FALLBACK_COUNT,
                generate_dek,
                wrap_dek,
                KMSUnavailableError,
            )
            _note_kms_fallback("generate_file_dek", exc)
            if _KMS_FALLBACK_COUNT > _KMS_FALLBACK_THRESHOLD:
                raise KMSUnavailableError(
                    f"KMS fallback count exceeded threshold "
                    f"({_KMS_FALLBACK_COUNT}>{_KMS_FALLBACK_THRESHOLD}); "
                    f"refusing to use local KEK any longer."
                ) from exc
            plaintext_dek = generate_dek()
            wrapped_dek = wrap_dek(plaintext_dek)
            encrypted_dek_b64 = base64.b64encode(wrapped_dek).decode("utf-8")
            return plaintext_dek, encrypted_dek_b64
        logger.exception("kms_generate_dek_unexpected_error_no_fallback")
        raise


async def unwrap_file_dek(encrypted_dek_b64: str, tenant_name: str, doc_id: str | None = None) -> bytes:
    """Giải mã encrypted_file_dek.

    Args:
        encrypted_dek_b64: base64 của wrapped file DEK.
        tenant_name: Tên tenant — phải khớp với context lúc wrap.
        doc_id: UUID của document — phải khớp với context lúc wrap.

    - Network/timeout -> raise (caller retry).
    - IncorrectKeyException / KeyUnavailableException -> fallback local KEK
      (chỉ đúng với data cũ wrap bằng local trước khi bật KMS).
    - Sai EncryptionContext (InvalidCiphertextException, ...) -> raise (KHÔNG fallback).
    - Lỗi khác -> raise.
    """
    from app.core.encryption import (
        is_kms_dev_mode,
        unwrap_dek,
    )
    ciphertext_blob = base64.b64decode(encrypted_dek_b64)
    if is_kms_dev_mode():
        try:
            return unwrap_dek(ciphertext_blob)
        except Exception:
            pass
    try:
        client = get_kms_client()
        response = await asyncio.to_thread(
            client.decrypt,
            CiphertextBlob=ciphertext_blob,
            EncryptionContext=_encryption_context(tenant_name, doc_id),
            KeyId=KMS_KEY_ALIAS,
        )
        return response["Plaintext"]
    except _NETWORK_ERRORS as exc:
        logger.warning("kms_unwrap_dek_network_error_no_fallback", error=str(exc))
        raise RuntimeError(f"KMS timeout/connection error khi unwrap DEK: {exc}") from exc
    except Exception as exc:
        if _is_kms_fallback_error(exc):
            from app.core.encryption import (
                _note_kms_fallback,
                _KMS_FALLBACK_THRESHOLD,
                _KMS_FALLBACK_COUNT,
                unwrap_dek,
                KMSUnavailableError,
            )
            _note_kms_fallback("unwrap_file_dek", exc)
            if _KMS_FALLBACK_COUNT > _KMS_FALLBACK_THRESHOLD:
                raise KMSUnavailableError(
                    f"KMS fallback count exceeded threshold "
                    f"({_KMS_FALLBACK_COUNT}>{_KMS_FALLBACK_THRESHOLD}); "
                    f"refusing to use local KEK any longer."
                ) from exc
            return unwrap_dek(ciphertext_blob)
        logger.exception("kms_unwrap_dek_unexpected_error_no_fallback")
        raise


def encrypt_file_bytes(plaintext: bytes, dek: bytes) -> bytes:
    """AES-256-GCM encrypt. Nonce 12 byte random, prepend vào đầu ciphertext
    (object tự chứa đủ để decrypt, không cần cột DB riêng cho nonce)."""
    aesgcm = AESGCM(dek)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    return nonce + ciphertext


def decrypt_file_bytes(encrypted_blob: bytes, dek: bytes) -> bytes:
    aesgcm = AESGCM(dek)
    nonce, ciphertext = encrypted_blob[:12], encrypted_blob[12:]
    return aesgcm.decrypt(nonce, ciphertext, associated_data=None)