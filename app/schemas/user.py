"""
User Pydantic schemas.

Defines request/response models for the /users endpoints.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Request schemas
# =============================================================================


class UserCreate(BaseModel):
    """Request body for creating a new user.

    Notes
    -----
    - ``tenant_id`` is optional for TENANT_ADMIN callers. The service layer
      will enforce their own ``tenant_id`` if not provided or if it mismatches.
    - ``role_name`` is the human-readable role string (e.g. 'USER', 'TENANT_ADMIN').
      The service layer resolves it to a ``role_id`` UUID.
    - ``email`` must be unique across the entire platform (globally unique).
    """

    user_name: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Username (must be unique within the tenant).",
    )
    email: str | None = Field(
        default=None,
        max_length=255,
        description="Optional email address. Must be unique across the entire platform.",
    )
    full_name: str | None = Field(
        default=None,
        max_length=255,
        description="Optional full name.",
    )
    password: str = Field(
        ...,
        min_length=6,
        max_length=64,
        description="Plain-text password — will be hashed before storage.",
    )
    tenant_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "UUID of the tenant this user belongs to. "
            "Required for PLATFORM_ADMIN; ignored / overridden for TENANT_ADMIN."
        ),
    )
    role_name: str = Field(
        ...,
        description=(
            "Role name to assign to this user. "
            "Allowed values: 'USER', 'TENANT_ADMIN'."
        ),
    )

    @field_validator("user_name")
    @classmethod
    def _no_whitespace(cls, v: str) -> str:
        if " " in v:
            raise ValueError("user_name must not contain spaces.")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_name": "john_doe",
                    "email": "john.doe@example.com",
                    "full_name": "John Doe",
                    "password": "s3cur3P@ssword",
                    "tenant_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                    "role_name": "USER",
                }
            ]
        }
    }


# =============================================================================
# Response schemas
# =============================================================================


class UserResponse(BaseModel):
    """Full user representation returned by the API (no password)."""

    user_id: uuid.UUID = Field(..., description="Unique user identifier.")
    user_name: str = Field(..., description="Username.")
    email: str | None = Field(default=None, description="Optional email address of the user.")
    full_name: str | None = Field(default=None, description="Optional full name of the user.")
    tenant_id: uuid.UUID | None = Field(default=None, description="Owning tenant UUID. Null for PLATFORM_ADMIN.")
    role_id: uuid.UUID = Field(..., description="Assigned role UUID.")
    role_name: str | None = Field(default=None, description="Assigned role name (e.g. TENANT_ADMIN, USER).")
    status: str = Field(..., description="Current status of the user account (active, pending_invitation, disabled, expired).")
    created_at: datetime = Field(..., description="UTC creation timestamp.")
    updated_at: datetime | None = Field(default=None, description="UTC last-update timestamp.")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                    "user_name": "john_doe",
                    "email": "john.doe@example.com",
                    "full_name": "John Doe",
                    "tenant_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                    "role_id": "3fa85f64-5717-4562-b3fc-2c963f66afa7",
                    "status": "active",
                    "created_at": "2026-06-19T09:00:00Z",
                    "updated_at": "2026-06-19T09:00:00Z",
                }
            ]
        },
    }


class UserListResponse(BaseModel):
    """Paginated list of users."""

    users: list[UserResponse] = Field(..., description="List of user objects.")
    total: int = Field(..., description="Total number of active users.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "users": [
                        {
                            "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                            "user_name": "john_doe",
                            "email": "john.doe@example.com",
                            "full_name": "John Doe",
                            "tenant_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                            "role_id": "3fa85f64-5717-4562-b3fc-2c963f66afa7",
                            "status": "active",
                            "created_at": "2026-06-19T09:00:00Z",
                            "updated_at": "2026-06-19T09:00:00Z",
                        }
                    ],
                    "total": 1,
                }
            ]
        }
    }
