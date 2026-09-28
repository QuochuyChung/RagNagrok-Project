"""
Authentication endpoints.

POST /v1/auth/login                    — Login with email or username + password
GET  /v1/auth/invitations/validate     — Validate an invite token (frontend pre-check, B6)
POST /v1/auth/invitations/accept       — Accept an invite and set password (A2 / B2)
POST /v1/auth/forgot-password          — Request a password-reset email
GET  /v1/auth/reset-password/validate  — Validate a password-reset token (read-only)
POST /v1/auth/reset-password           — Complete the password reset (set new password)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import get_auth_service
from app.core.security import public
from app.schemas.auth import LoginRequest, TokenResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/v1/auth", tags=["auth"])


# =============================================================================
# POST /auth/login
# =============================================================================

@router.post("/login", response_model=TokenResponse)
@public
async def login(request: LoginRequest, service: AuthService = Depends(get_auth_service)) -> TokenResponse:
    try:
        token = await service.login(
            username=request.username,
            password=request.password,
            email=request.email,
        )
        return TokenResponse(access_token=token)
    except ValueError as exc:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "INVALID_CREDENTIALS",
                "message": str(exc) or "Invalid username or password.",
            },
        )


