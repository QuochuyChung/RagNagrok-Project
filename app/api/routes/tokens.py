"""
Tokens router.

Public endpoints for the password reset and invitation flows.
Includes:
- POST /v1/tokens/forgot-password
- GET  /v1/tokens/reset-password/validate
- POST /v1/tokens/reset-password
- GET  /v1/tokens/invitations/validate
- POST /v1/tokens/invitations/accept
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_token_service
from app.core.security import public
from app.repositories.token_repository import TOKEN_INVITATION, TOKEN_PASSWORD_RESET
from app.schemas.auth import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    ValidateResetTokenResponse,
)
from app.schemas.invitation import (
    AcceptInviteRequest,
    AcceptInviteResponse,
    ValidateTokenResponse,
)
from app.services.token_service import TokenService

router = APIRouter(prefix="/v1/tokens", tags=["Tokens"])

# =============================================================================
# Password Reset Endpoints
# =============================================================================

@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
    summary="Request a password reset link",
    description="Send a password reset email if the user exists. Always returns 200.",
)
@public
async def forgot_password(
    data: ForgotPasswordRequest,
    token_service: TokenService = Depends(get_token_service),
):
    await token_service.request_reset(data.email)
    return {"message": "If that email is in our system, you will receive a reset link shortly."}

@router.get(
    "/reset-password/validate",
    response_model=ValidateResetTokenResponse,
    summary="Validate a password reset token",
    description="Check if a reset token is valid before showing the reset form.",
)
@public
async def validate_reset_token(
    token: str = Query(..., description="The raw token from the email link"),
    token_service: TokenService = Depends(get_token_service),
):
    result = await token_service.validate_token(token, token_type=TOKEN_PASSWORD_RESET)
    return ValidateResetTokenResponse(**result)

@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
    summary="Reset password",
    description="Complete the password reset flow using a valid token.",
)
@public
async def reset_password(
    data: ResetPasswordRequest,
    token_service: TokenService = Depends(get_token_service),
):
    result = await token_service.consume_token(
        raw_token=data.token,
        token_type=TOKEN_PASSWORD_RESET,
        new_password=data.new_password,
    )
    return result

# =============================================================================
# Invitation Validation & Acceptance Endpoints
# =============================================================================

@router.get(
    "/invitations/validate",
    response_model=ValidateTokenResponse,
    summary="Validate an invite token",
    description="Check if an invite token is valid and return context (email, role).",
)
@public
async def validate_invitation(
    token: str = Query(..., description="The raw invite token"),
    token_service: TokenService = Depends(get_token_service),
):
    result = await token_service.validate_token(token, token_type=TOKEN_INVITATION)
    return ValidateTokenResponse(**result)

@router.post(
    "/invitations/accept",
    response_model=AcceptInviteResponse,
    status_code=status.HTTP_200_OK,
    summary="Accept an invitation and set password",
)
@public
async def accept_invitation(
    data: AcceptInviteRequest,
    token_service: TokenService = Depends(get_token_service),
):
    result = await token_service.consume_token(
        raw_token=data.token,
        token_type=TOKEN_INVITATION,
        new_password=data.new_password,
    )
    return AcceptInviteResponse(**result)
