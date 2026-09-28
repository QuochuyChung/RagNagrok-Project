import uuid

from pydantic import BaseModel, Field, model_validator


class LoginRequest(BaseModel):
    """
    Request body for login.

    Supports login by either ``email`` (unique platform-wide) or ``username``.
    Exactly one of the two must be provided.
    """
    username: str | None = None
    email: str | None = None
    password: str

    @model_validator(mode="after")
    def _require_username_or_email(self) -> "LoginRequest":
        if not self.username and not self.email:
            raise ValueError("Either 'username' or 'email' must be provided.")
        return self


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., description="Email address to send the reset link to.")


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10, description="Raw password reset token from the email link.")
    new_password: str = Field(..., min_length=8, max_length=128, description="New password (min 8 chars).")
    confirm_password: str = Field(..., min_length=8, max_length=128, description="Must match new_password.")

    @model_validator(mode="after")
    def check_passwords_match(self) -> "ResetPasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("new_password and confirm_password must match.")
        return self


class ValidateResetTokenResponse(BaseModel):
    valid: bool
    email: str | None = None
    error_code: str | None = None
    message: str | None = None
