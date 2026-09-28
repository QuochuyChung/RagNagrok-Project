"""
Content hashing utilities.

Provides deterministic SHA-256 hashing for document content to enable
idempotent ingestion — uploading the same file twice produces the same hash,
allowing the system to detect duplicates and skip re-processing.
"""

from __future__ import annotations

import ctypes
import hashlib

import bcrypt


def compute_sha256(content: bytes) -> str:
    """
    Compute the SHA-256 hex digest of ``content``.

    Args:
        content: Raw bytes of the document to hash.

    Returns:
        64-character lowercase hexadecimal string.
    """
    return hashlib.sha256(content).hexdigest()


def compute_sha256_str(text: str, encoding: str = "utf-8") -> str:
    """
    Compute the SHA-256 hex digest of a text string.

    Args:
        text: The text to hash.
        encoding: Character encoding to use (default: utf-8).

    Returns:
        64-character lowercase hexadecimal string.
    """
    return compute_sha256(text.encode(encoding))

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def zeroize(buf) -> None:
    """Best-effort xoá nội dung của buffer in-place.

    CPython thường giữ bytes trong memory reuse pool, nên ``buf = None``
    KHÔNG đảm bảo plaintext đã bị xoá. Hàm này:
      1. Nếu buf là ``bytearray``/``memoryview``: ghi đè 0 trực tiếp.
      2. Nếu buf là ``bytes`` (immutable): dùng ``ctypes.memset`` chỗ bytes
         đó để best-effort xoá pool.
    Best-effort: với debug build CPython có thể đã copy đi chỗ khác, nhưng
    đây vẫn là lớp phòng thủ tốt nhất có thể ở Python layer. Không bao giờ
    raise để không phá vỡ request ingest.
    """
    if buf is None:
        return
    try:
        if isinstance(buf, (bytearray, memoryview)):
            for i in range(len(buf)):
                buf[i] = 0
            return
        if isinstance(buf, bytes):
            mv = memoryview(buf)
            ctypes.memset(mv.obj, 0, len(mv))
    except Exception:
        pass