"""
Tenant Pydantic schemas.

Defines request/response models for the /tenants endpoints.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field


class TenantCreate(BaseModel):
    """
    Request body for creating a new tenant.

    Optionally includes ``tenant_admin`` details so the Platform Admin can
    pre-create the TENANT_ADMIN account and trigger the invitation email in
    the same atomic call.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable display name for the tenant.",
    )
    tenant_admin: "TenantAdminInput | None" = Field(
        default=None,
        description=(
            "Optional. If provided, a TENANT_ADMIN account is pre-created "
            "and an invitation email is sent to the supplied email address."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Team Alpha",
                    "tenant_admin": {
                        "email": "jane.doe@acme.com",
                        "full_name": "Jane Doe",
                    },
                }
            ]
        }
    }


# Forward ref — resolved after InvitationSchemas are imported
from app.schemas.invitation import TenantAdminInput  # noqa: E402
TenantCreate.model_rebuild()


class TenantResponse(BaseModel):
    """Full tenant representation returned by the API."""

    id: uuid.UUID = Field(..., description="Unique tenant slug.")
    name: str = Field(..., description="Human-readable tenant name.")
    qdrant_collection: str = Field(
        ..., description="Name of the dedicated Qdrant vector collection."
    )
    is_active: bool = Field(..., description="Whether the tenant is active.")
    created_at: datetime = Field(..., description="UTC creation timestamp.")
    updated_at: datetime | None= Field(description="UTC last-update timestamp.")

    # Allow ORM model instances to be passed directly (Pydantic v2)
    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "examples": [
                {
                    "id": "team-alpha",
                    "name": "Team Alpha",
                    "qdrant_collection": "tenant_team_alpha",
                    "is_active": True,
                    "created_at": "2026-06-19T09:00:00Z",
                    "updated_at": "2026-06-19T09:00:00Z",
                }
            ]
        },
    }


class TenantListResponse(BaseModel):
    """Paginated list of tenants."""

    tenants: list[TenantResponse] = Field(..., description="List of tenant objects.")
    total: int = Field(..., description="Total number of tenants matching the query.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "tenants": [
                        {
                            "id": "team-alpha",
                            "name": "Team Alpha",
                            "qdrant_collection": "tenant_team_alpha",
                            "is_active": True,
                            "created_at": "2026-06-19T09:00:00Z",
                            "updated_at": "2026-06-19T09:00:00Z",
                        }
                    ],
                    "total": 1,
                }
            ]
        }
    }
