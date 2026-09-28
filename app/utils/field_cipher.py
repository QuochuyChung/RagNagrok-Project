"""
Field-level cipher utilities for per-tenant database and Qdrant payload encryption.

Design:
    - All encrypted fields are stored as URL-safe Base64 strings so they fit
      into existing TEXT / VARCHAR columns without schema migration overhead.
    - Wire format:  base64url( nonce(12B) | ciphertext | GCM-tag(16B) )
    - The DEK passed in must already be a plaintext 32-byte AES-256 key
      (unwrapped via KMS or local KEK).  This module is intentionally
      stateless — callers are responsible for fetching and zeroing the DEK.

Usage:
    from app.utils.field_cipher import encrypt_field, decrypt_field

    ciphertext_b64 = encrypt_field(plaintext_str, dek_bytes)
    plaintext_str  = decrypt_field(ciphertext_b64, dek_bytes)
"""

from __future__ import annotations

import base64
import os
import hmac
import hashlib

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ── Sentinel prefix to detect encrypted values ─────────────────────────────
# Stored values are prefixed with "enc:" so we can skip decryption for legacy
# plaintext rows that may exist before encryption was enabled.
_PREFIX = "enc:"


def encrypt_field(plaintext: str, dek: bytes) -> str:
    """
    Encrypt a plaintext string and return a Base64-encoded ciphertext string.

    Args:
        plaintext: The raw string to encrypt.
        dek: 32-byte AES-256 plaintext key.

    Returns:
        A URL-safe Base64 string with "enc:" prefix suitable for TEXT columns.

    Raises:
        ValueError: If dek is not 32 bytes.
    """
    if len(dek) != 32:
        raise ValueError(f"DEK must be 32 bytes, got {len(dek)}")

    aesgcm = AESGCM(dek)
    nonce = os.urandom(12)
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    blob = nonce + ciphertext_with_tag
    return _PREFIX + base64.urlsafe_b64encode(blob).decode("ascii")


def decrypt_field(value: str, dek: bytes) -> str:
    """
    Decrypt a previously encrypted field value.

    If the value does NOT start with "enc:", it is returned as-is (backward
    compatibility with legacy plaintext rows seeded before encryption).

    Args:
        value: The Base64-encoded ciphertext string from the database.
        dek: 32-byte AES-256 plaintext key.

    Returns:
        The original plaintext string.

    Raises:
        ValueError: On decryption failure (bad DEK, tampered data, etc.).
    """
    if not value.startswith(_PREFIX):
        # Legacy row — not encrypted, return as-is
        return value

    encoded = value[len(_PREFIX):]
    try:
        blob = base64.urlsafe_b64decode(encoded)
    except Exception as exc:
        raise ValueError("Invalid Base64 in encrypted field.") from exc

    if len(blob) < 28:  # 12 nonce + 16 tag minimum
        raise ValueError("Encrypted field blob is too short.")

    nonce = blob[:12]
    ciphertext_with_tag = blob[12:]

    aesgcm = AESGCM(dek)
    try:
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext_with_tag, associated_data=None)
        return plaintext_bytes.decode("utf-8")
    except Exception as exc:
        raise ValueError(
            "Failed to decrypt field. Integrity check failed or incorrect DEK."
        ) from exc


def is_encrypted(value: str | None) -> bool:
    """Return True if the value looks like an encrypted field (has enc: prefix)."""
    return isinstance(value, str) and value.startswith(_PREFIX)


def encrypt_field_bytes(plaintext: str, dek: bytes) -> str:
    """Alias for encrypt_field — kept for naming consistency with s3_storage."""
    return encrypt_field(plaintext, dek)

def compute_doc_name_lookup_hash(plaintext: str, dek: bytes) -> str:
    """
    HMAC-SHA256 xác định (deterministic) dùng làm blind index để query
    WHERE trên doc_name mà không cần lưu plaintext.

    Khác với encrypt_field (AES-GCM, cố tình random nonce mỗi lần để
    chống known-plaintext attack -> không dùng so sánh bằng được), hàm
    này CÙNG plaintext + CÙNG dek luôn cho CÙNG kết quả -> query WHERE
    hoạt động đúng, nhưng không thể giải mã ngược lại thành plaintext
    (one-way, chỉ dùng để so khớp, không dùng để hiển thị).
    """
    return hmac.new(dek, plaintext.encode("utf-8"), hashlib.sha256).hexdigest()