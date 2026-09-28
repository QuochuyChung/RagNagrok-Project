"""
Unit tests for app/utils/hashing.py
"""

from app.utils.hashing import compute_sha256, compute_sha256_str


def test_compute_sha256_known_hash() -> None:
    """SHA-256 of empty bytes is a known constant."""
    expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert compute_sha256(b"") == expected


def test_compute_sha256_str() -> None:
    """compute_sha256_str should match compute_sha256 of encoded bytes."""
    text = "hello world"
    assert compute_sha256_str(text) == compute_sha256(text.encode("utf-8"))


def test_compute_sha256_deterministic() -> None:
    """Same input always produces same hash (idempotency)."""
    content = b"some document content"
    assert compute_sha256(content) == compute_sha256(content)


def test_compute_sha256_different_inputs() -> None:
    """Different inputs must produce different hashes."""
    assert compute_sha256(b"doc_a") != compute_sha256(b"doc_b")
