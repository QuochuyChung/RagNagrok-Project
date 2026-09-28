"""
Invitation Pydantic schemas.

Defines request/response models for:
    - POST /v1/tenants/{tenant_id}/invitations  (bulk invite users)
    - GET  /v1/tenants/{tenant_id}/invitations  (list invitations)
    - DELETE /v1/tenants/{tenant_id}/invitations/{invitation_id}  (revoke)
    - POST /v1/tenants/{tenant_id}/invitations/{invitation_id}/resend
    - GET  /v1/auth/invitations/validate?token=  (frontend pre-check)
    - POST /v1/auth/invitations/accept           (set password + activate)
    - POST /v1/tenants/{tenant_id}/admin/resend-invite (resend admin invite)

Also used by TenantCreate for the optional embedded tenant_admin details.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Simple RFC-5322-ish email regex (avoids email-validator dep)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(v: str) -> str:
    v = v.strip().lower()
    if not _EMAIL_RE.match(v):
        raise ValueError(f"Invalid email address: '{v}'")
    return v


# =============================================================================
# Shared sub-models
# =============================================================================


class InviteeInput(BaseModel):
    """A single invitee entry in a bulk invite request."""

    email: str = Field(..., description="Email address to invite.")
    full_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Invitee's display name — stored as name.",
    )
    username: str | None = Field(
        default=None,
        min_length=1,
        max_length=16,
        pattern=r"^[a-zA-Z0-9_.-]+$",
        description="Optional login username. Defaults to email prefix if not provided.",
    )

    @field_validator("email", mode="before")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        return _validate_email(v)


class TenantAdminInput(BaseModel):
    """
    Embedded tenant-admin details provided when creating a tenant.

    The platform admin supplies the future TENANT_ADMIN's name and email
    so the system can pre-create the account and send the invitation email
    in the same atomic tenant-creation call.
    """

    email: str = Field(
        ..., description="Email address of the future TENANT_ADMIN."
    )
    full_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Display name of the future TENANT_ADMIN.",
    )
    username: str | None = Field(
        default=None,
        min_length=1,
        max_length=16,
        pattern=r"^[a-zA-Z0-9_.-]+$",
        description="Optional login username (max 16 chars, alphanumeric/_/-/.). Defaults to email prefix if not provided.",
    )

    @field_validator("email", mode="before")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        return _validate_email(v)


# =============================================================================
# Request schemas
# =============================================================================


class BulkInviteRequest(BaseModel):
    """
    Request body for POST /v1/tenants/{tenant_id}/invitations.

    Allows TENANT_ADMIN (or PLATFORM_ADMIN) to invite one or many users
    in a single API call — reducing round-trips for large team onboarding.
    """

    invitees: list[InviteeInput] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of invitees (1–100 per request).",
    )
    role_name: str = Field(
        default="USER",
        description="Role to assign to all invitees. TENANT_ADMIN may only invite 'USER'.",
    )
    expires_in_hours: int = Field(
        default=48,
        ge=1,
        le=168,
        description="Token expiry in hours (1–168). Defaults to 48 h.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "invitees": [
                        {"email": "alice@acme.com", "full_name": "Alice Smith"},
                        {"email": "bob@acme.com", "full_name": "Bob Jones"},
                    ],
                    "role_name": "USER",
                    "expires_in_hours": 48,
                }
            ]
        }
    }


class AcceptInviteRequest(BaseModel):
    """
    Request body for POST /v1/auth/invitations/accept.

    The raw invite token is read from the email link and submitted here
    alongside the new password chosen by the invitee.
    """

    token: str = Field(
        ...,
        min_length=10,
        description="Raw invite token extracted from the email link query-string.",
    )
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="New password chosen by the invitee (min 8 chars).",
    )
    confirm_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Must match new_password exactly.",
    )

    @model_validator(mode="after")
    def _passwords_must_match(self) -> "AcceptInviteRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("new_password and confirm_password must match.")
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "token": "abc123xyz...",
                    "new_password": "S3cur3P@ssw0rd!",
                    "confirm_password": "S3cur3P@ssw0rd!",
                }
            ]
        }
    }


# =============================================================================
# Response schemas
# =============================================================================


class InvitedUserResult(BaseModel):
    """Result for a successfully invited user in a bulk invite response."""

    email: str
    user_id: uuid.UUID
    status: Literal["invited"]


class SkippedUserResult(BaseModel):
    """Result for a skipped invitee (e.g. email already registered)."""

    email: str
    reason: str


class BulkInviteResponse(BaseModel):
    """Response body for POST /v1/tenants/{tenant_id}/invitations."""

    invited: list[InvitedUserResult] = Field(
        default_factory=list,
        description="Invitees who were successfully invited.",
    )
    skipped: list[SkippedUserResult] = Field(
        default_factory=list,
        description="Invitees who were skipped with the reason.",
    )
    total_invited: int
    total_skipped: int


class InvitationStatus(BaseModel):
    """Status summary of a single invitation record."""

    invitation_id: uuid.UUID
    user_id: uuid.UUID
    email: str | None
    full_name: str
    role: str
    status: Literal["pending", "accepted", "expired", "revoked"]
    invited_by: uuid.UUID | None
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None = None

    model_config = {"from_attributes": True}


class InvitationListResponse(BaseModel):
    """Paginated list of invitations for a tenant."""

    invitations: list[InvitationStatus]
    total: int
    page: int
    page_size: int


class ValidateTokenResponse(BaseModel):
    """
    Response for GET /v1/auth/invitations/validate.

    Used by the frontend to populate the 'Set Password' form with context
    (user name, tenant name) before the user submits.
    """

    valid: bool
    email: str | None = None
    full_name: str | None = None
    tenant_name: str | None = None
    role: str | None = None
    expires_at: datetime | None = None
    error_code: str | None = None
    message: str | None = None


class AcceptInviteResponse(BaseModel):
    """Response for POST /v1/auth/invitations/accept."""

    message: str
    user: AcceptedUserInfo


class AcceptedUserInfo(BaseModel):
    """Minimal user info returned after accepting an invite."""

    user_id: uuid.UUID
    email: str | None
    role: str
    tenant_id: uuid.UUID | None


class ResendInviteResponse(BaseModel):
    """Response for resend-invite endpoints."""

    message: str
    invitation_expires_at: datetime


class TenantWithAdminResponse(BaseModel):
    """
    Extended response for POST /v1/tenants when tenant_admin is provided.

    Returns both the newly created tenant and the pre-created (inactive)
    TENANT_ADMIN account with invitation details.
    """

    tenant: dict  # TenantResponse serialized to dict to avoid circular import
    tenant_admin: "TenantAdminCreated"


class TenantAdminCreated(BaseModel):
    """Summary of the TENANT_ADMIN account created alongside the tenant."""

    user_id: uuid.UUID
    email: str
    user_name: str
    role: str = "TENANT_ADMIN"
    status: str
    invitation_sent: bool
    invitation_expires_at: datetime | None = None



