"""
Auth service.

Handles API key validation and tenant authentication.

TODO (Sprint 3+): Implement API key management.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI

from app.core.logging import get_logger
from app.core.security import create_access_token
from app.repositories.user_repository import UserRepository
from app.utils.hashing import verify_password

logger = get_logger(__name__)


class AuthService:
    """Business logic layer for authentication and authorisation."""

    def __init__(self, user_repository: UserRepository) -> None:
        self._user_repository = user_repository

    async def login(self, username: str | None, password: str, email: str | None = None) -> str:
        """
        Authenticate a user by email or username and return a JWT token.

        Email is preferred because it is globally unique (platform-wide).
        Username lookup is a fallback (note: username is only unique per-tenant,
        so in multi-tenant scenarios, email login is more precise).

        Raises:
            ValueError: If credentials are invalid or the user is inactive.
        """
        user = None

        # Xử lý trường hợp UI gửi email vào trường username
        if not email and username and "@" in username:
            email = username
            username = None

        if email:
            # Email is globally unique — direct lookup
            user = await self._user_repository.get_active_by_email(email)
        elif username:
            # Username fallback (unique per tenant, not globally)
            user = await self._user_repository.get_by_username(username=username)

        if user is None or not verify_password(password, user.password_hash):
            raise ValueError('Invalid credentials')

        access_token = create_access_token(user=user)
        return access_token
