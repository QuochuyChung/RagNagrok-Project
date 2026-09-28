"""
Time utilities.

Helper functions for timestamp handling and TTL calculations used by
conversation memory and document versioning.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


def is_expired(timestamp: datetime, ttl_seconds: int) -> bool:
    """
    Check whether a timestamp has exceeded the given TTL.

    Args:
        timestamp: The datetime to check (must be timezone-aware).
        ttl_seconds: Time-to-live in seconds.

    Returns:
        ``True`` if the timestamp is older than ``ttl_seconds``.
    """
    expiry = timestamp + timedelta(seconds=ttl_seconds)
    return utcnow() > expiry


def seconds_until_expiry(timestamp: datetime, ttl_seconds: int) -> float:
    """
    Return seconds remaining until a timestamp expires, or 0 if already expired.

    Args:
        timestamp: The datetime to check (must be timezone-aware).
        ttl_seconds: Time-to-live in seconds.

    Returns:
        Remaining seconds as a float (0.0 if already expired).
    """
    expiry = timestamp + timedelta(seconds=ttl_seconds)
    remaining = (expiry - utcnow()).total_seconds()
    return max(0.0, remaining)
