"""
Unit tests for app/utils/time.py
"""

from datetime import datetime, timedelta, timezone

from app.utils.time import is_expired, seconds_until_expiry, utcnow


def test_utcnow_is_timezone_aware() -> None:
    """utcnow() must return a timezone-aware datetime."""
    now = utcnow()
    assert now.tzinfo is not None
    assert now.tzinfo == timezone.utc


def test_is_expired_old_timestamp() -> None:
    """A timestamp older than TTL should be expired."""
    old = datetime.now(timezone.utc) - timedelta(seconds=120)
    assert is_expired(old, ttl_seconds=60) is True


def test_is_expired_fresh_timestamp() -> None:
    """A very recent timestamp should NOT be expired."""
    fresh = datetime.now(timezone.utc)
    assert is_expired(fresh, ttl_seconds=3600) is False


def test_seconds_until_expiry_expired() -> None:
    """An already-expired timestamp returns 0.0."""
    old = datetime.now(timezone.utc) - timedelta(seconds=200)
    assert seconds_until_expiry(old, ttl_seconds=60) == 0.0


def test_seconds_until_expiry_positive() -> None:
    """A fresh timestamp returns a positive remaining time."""
    fresh = datetime.now(timezone.utc)
    remaining = seconds_until_expiry(fresh, ttl_seconds=3600)
    assert remaining > 0
    assert remaining <= 3600
