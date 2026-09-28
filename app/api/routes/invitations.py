"""
Tenant invitation endpoints (Flow B: TENANT_ADMIN → Users).

POST   /v1/tenants/{tenant_id}/invitations                        — Bulk invite users (B1)
GET    /v1/tenants/{tenant_id}/invitations                        — List invitations (B3)
DELETE /v1/tenants/{tenant_id}/invitations/{invitation_id}        — Revoke invite (B4)
POST   /v1/tenants/{tenant_id}/invitations/{invitation_id}/resend — Resend invite (B5)
POST   /v1/tenants/{tenant_id}/admin/resend-invite                — Resend admin invite (A3)

RBAC summary:
  PLATFORM_ADMIN → full access to any tenant
  TENANT_ADMIN   → scoped to their own tenant; can only assign 'USER' role
"""

from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, Depends, Query, Request, status, UploadFile, File, HTTPException

from app.api.deps import get_token_service, get_tenant_id
from app.core.security import bearer_scheme, requires_roles
from app.schemas.invitation import (
    BulkInviteRequest,
    BulkInviteResponse,
    InvitationListResponse,
    ResendInviteResponse,
)
from app.services.token_service import TokenService

router = APIRouter(
    prefix="/v1/tenants",
    tags=["Invitations"],
    dependencies=[Depends(bearer_scheme)],
)


# =============================================================================
# POST /tenants/{tenant_id}/invitations — Bulk invite users (B1)
# =============================================================================


@router.post(
    "/invitations",
    response_model=BulkInviteResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Bulk invite users to a tenant",
    description=(
        "Invite one or many users (up to 100 per request) to a tenant in a single call. "
        "Email delivery is asynchronous — the response is returned immediately after "
        "pre-creating all user accounts and queueing emails. "
        "**TENANT_ADMIN**: can invite 'USER' or 'TENANT_ADMIN' role to their own tenant. "
    ),
)
@requires_roles("PLATFORM_ADMIN", "TENANT_ADMIN")
async def bulk_invite_users(
    request: Request,
    data: BulkInviteRequest,
    tenant_id_str: str = Depends(get_tenant_id),
    token_service: TokenService = Depends(get_token_service),
) -> BulkInviteResponse:
    """Bulk-invite users; returns immediately with per-invitee results."""
    caller_role: str = request.state.role
    caller_tenant_id: str = request.state.tenant_id
    caller_user_id_str: str | None = getattr(request.state, "user_id", None)
    caller_user_id = uuid.UUID(caller_user_id_str) if caller_user_id_str else None

    # Use username from JWT payload as inviter display name
    inviter_name: str = getattr(request.state, "username", caller_role)
    
    tenant_id_uuid = uuid.UUID(tenant_id_str)

    return await token_service.bulk_invite_users(
        tenant_id=tenant_id_uuid,
        request=data,
        caller_role=caller_role,
        caller_tenant_id=str(caller_tenant_id),
        inviter_name=inviter_name,
        caller_user_id=caller_user_id,
    )


# =============================================================================
# POST /tenants/{tenant_id}/invitations/csv — Bulk invite users via CSV
# =============================================================================


@router.post(
    "/invitations/csv",
    response_model=BulkInviteResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Bulk invite users to a tenant via CSV upload",
    description=(
        "Upload a CSV file with headers `email` and `full_name`. "
        "The system will parse it and invoke the standard bulk invite logic. "
    ),
)
@requires_roles("PLATFORM_ADMIN", "TENANT_ADMIN")
async def bulk_invite_users_csv(
    request: Request,
    file: UploadFile = File(...),
    role_name: str = Query("USER", description="Role to assign"),
    expires_in_hours: int = Query(48, description="Token expiry in hours"),
    tenant_id_str: str = Depends(get_tenant_id),
    token_service: TokenService = Depends(get_token_service),
) -> BulkInviteResponse:
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_FILE_TYPE", "message": "Only .csv files are allowed."})
    
    try:
        contents = await file.read()
        decoded_string = contents.decode("utf-8-sig")
        csv_reader = csv.DictReader(io.StringIO(decoded_string))
        
        invitees = []
        for row in csv_reader:
            if 'email' not in row or 'full_name' not in row:
                raise ValueError("CSV must contain 'email' and 'full_name' headers.")
            if row['email'].strip() and row['full_name'].strip():
                invitees.append({
                    "email": row['email'].strip(),
                    "full_name": row['full_name'].strip()
                })
                
        if not invitees:
            raise ValueError("No valid rows found in CSV.")
            
        data = BulkInviteRequest(
            invitees=invitees,
            role_name=role_name,
            expires_in_hours=expires_in_hours
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_CSV_FORMAT", "message": str(ve)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error_code": "CSV_PARSE_ERROR", "message": f"Could not parse CSV: {e}"})

    caller_role: str = request.state.role
    caller_tenant_id: str = request.state.tenant_id
    caller_user_id_str: str | None = getattr(request.state, "user_id", None)
    caller_user_id = uuid.UUID(caller_user_id_str) if caller_user_id_str else None

    # Use username from JWT payload as inviter display name
    inviter_name: str = getattr(request.state, "username", caller_role)
    
    tenant_id_uuid = uuid.UUID(tenant_id_str)

    return await token_service.bulk_invite_users(
        tenant_id=tenant_id_uuid,
        request=data,
        caller_role=caller_role,
        caller_tenant_id=str(caller_tenant_id),
        inviter_name=inviter_name,
        caller_user_id=caller_user_id,
    )

# =============================================================================
# GET /tenants/{tenant_id}/invitations — List invitations (B3)
# =============================================================================


@router.get(
    "/invitations",
    response_model=InvitationListResponse,
    summary="List invitations for a tenant",
    description=(
        "Return a paginated list of invitation records for a tenant. "
        "Filter by status using the ``?status=`` query parameter. "
        "**TENANT_ADMIN**: scoped to their own tenant."
    ),
)
@requires_roles("PLATFORM_ADMIN", "TENANT_ADMIN")
async def list_invitations(
    request: Request,
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="Filter by status: pending | accepted | expired | revoked",
    ),
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)."),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page (max 100)."),
    tenant_id_str: str = Depends(get_tenant_id),
    token_service: TokenService = Depends(get_token_service),
) -> InvitationListResponse:
    """List invitations with optional status filter and pagination."""
    caller_role: str = request.state.role
    caller_tenant_id: str = request.state.tenant_id
    
    tenant_id_uuid = uuid.UUID(tenant_id_str)

    return await token_service.list_invitations(
        tenant_id=tenant_id_uuid,
        caller_role=caller_role,
        caller_tenant_id=str(caller_tenant_id),
        status_filter=status_filter,
        page=page,
        page_size=page_size,
    )


# =============================================================================
# DELETE /tenants/{tenant_id}/invitations/{invitation_id} — Revoke (B4)
# =============================================================================


@router.delete(
    "/invitations/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a pending invitation",
    description=(
        "Permanently revoke a pending invitation. "
        "Cannot revoke an invitation that has already been accepted. "
        "**TENANT_ADMIN**: scoped to their own tenant."
    ),
)
@requires_roles("PLATFORM_ADMIN", "TENANT_ADMIN")
async def revoke_invitation(
    request: Request,
    user_id: uuid.UUID,
    tenant_id_str: str = Depends(get_tenant_id),
    token_service: TokenService = Depends(get_token_service),
) -> None:
    """Revoke a pending invitation. Returns 204 No Content on success."""
    caller_role: str = request.state.role
    caller_tenant_id: str = request.state.tenant_id
    
    tenant_id_uuid = uuid.UUID(tenant_id_str)

    await token_service.revoke_invitation(
        tenant_id=tenant_id_uuid,
        user_id=user_id,
        caller_role=caller_role,
        caller_tenant_id=str(caller_tenant_id),
    )
    return None


# =============================================================================
# POST /tenants/{tenant_id}/invitations/{invitation_id}/resend — Resend (B5)
# =============================================================================


@router.post(
    "/invitations/{user_id}/resend",
    response_model=ResendInviteResponse,
    summary="Resend an invitation",
    description=(
        "Revoke the existing invite token and send a fresh one to the same email. "
        "Cannot resend an invitation that has already been accepted. "
        "**TENANT_ADMIN**: scoped to their own tenant."
    ),
)
@requires_roles("PLATFORM_ADMIN", "TENANT_ADMIN")
async def resend_invitation(
    request: Request,
    user_id: uuid.UUID,
    tenant_id_str: str = Depends(get_tenant_id),
    token_service: TokenService = Depends(get_token_service),
) -> ResendInviteResponse:
    """Resend a pending invitation with a fresh token and extended expiry."""
    caller_role: str = request.state.role
    caller_tenant_id: str = request.state.tenant_id
    inviter_name: str = getattr(request.state, "username", caller_role)
    
    tenant_id_uuid = uuid.UUID(tenant_id_str)

    return await token_service.resend_user_invite(
        tenant_id=tenant_id_uuid,
        user_id=user_id,
        caller_role=caller_role,
        caller_tenant_id=str(caller_tenant_id),
        inviter_name=inviter_name,
    )


# =============================================================================
# POST /tenants/{tenant_id}/admin/resend-invite — Resend admin invite (A3)
# =============================================================================


@router.post(
    "/{tenant_id}/admin/resend-invite",
    response_model=ResendInviteResponse,
    summary="Resend the TENANT_ADMIN invitation",
    description=(
        "Revoke the existing TENANT_ADMIN invitation for a tenant and send a fresh one. "
        "Returns 409 if the tenant admin has already accepted their invite. "
        "**PLATFORM_ADMIN** only."
    ),
)
@requires_roles("PLATFORM_ADMIN")
async def resend_admin_invite(
    request: Request,
    tenant_id: uuid.UUID,
    token_service: TokenService = Depends(get_token_service),
) -> ResendInviteResponse:
    """Resend the TENANT_ADMIN onboarding email with a fresh invite token."""
    inviter_name: str = getattr(request.state, "username", "PLATFORM_ADMIN")

    return await token_service.resend_tenant_admin_invite(
        tenant_id=tenant_id,
        inviter_name=inviter_name,
    )
