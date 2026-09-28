"""
Token service.

Business logic for the full token lifecycle, handling both INVITATION
and PASSWORD_RESET flows.

Flows:
    - create_tenant_admin_invite(): Pre-create TENANT_ADMIN + send invite
    - resend_tenant_admin_invite(): Revoke old + resend
    - bulk_invite_users(): Batch pre-create users + send invites
    - resend_user_invite(): Revoke old + resend for one user
    - revoke_invitation(): Permanently revoke a pending invite
    - list_invitations(): Paginated list for a tenant
    - request_reset(): Initiate password reset (with timing attack mitigation)
    
    Shared:
    - validate_token(): Frontend pre-check (read-only)
    - consume_token(): Set password + activate/reset account
"""

from __future__ import annotations

import asyncio
import time
import uuid
import random
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import HTTPException

from app.core.config import get_settings
from app.core.errors import (
    InvitationNotFoundError,
    InvitationAlreadyAcceptedError,
    InvalidInviteTokenError,
    TokenExpiredError,
    TenantNotFoundError,
    UserNotFoundError,
)
from app.core.logging import get_logger
from app.repositories.token_repository import (
    TokenRepository,
    generate_raw_token,
    TOKEN_INVITATION,
    TOKEN_PASSWORD_RESET,
)
from app.repositories.user_repository import UserRepository
from app.repositories.tenant_repository import TenantRepository
from app.schemas.invitation import (
    AcceptedUserInfo,
    AcceptInviteResponse,
    BulkInviteRequest,
    BulkInviteResponse,
    InvitationListResponse,
    InvitationStatus,
    InvitedUserResult,
    ResendInviteResponse,
    SkippedUserResult,
    TenantAdminCreated,
    TenantAdminInput,
    ValidateTokenResponse,
)
from app.utils.email import send_invitation_email, send_password_reset_email

if TYPE_CHECKING:
    from app.models.token import Tokens
    from app.models.user import Users

logger = get_logger(__name__)


def _compute_status(record: "Tokens") -> str:
    """Derive the human-readable status string for an invitation record."""
    if record.accepted_at is not None:
        return "accepted"
    if record.is_revoked:
        return "revoked"
    if record.expires_at < datetime.now(timezone.utc):
        return "expired"
    return "pending"


def _to_invitation_status(record: "Tokens") -> InvitationStatus:
    """Convert an ORM invitation record to the API response schema."""
    user = record.user
    role_name = user.role.role_name if user and user.role else "USER"
    full_name = user.user_name if user else ""
    email = user.email if user else None

    return InvitationStatus(
        invitation_id=record.token_id,
        user_id=record.user_id,
        email=email,
        full_name=full_name,
        role=role_name,
        status=_compute_status(record),
        invited_by=record.invited_by,
        created_at=record.created_at,
        expires_at=record.expires_at,
        accepted_at=record.accepted_at,
    )


class TokenService:
    """Business logic layer for email invitations and password resets."""

    def __init__(
        self,
        token_repo: TokenRepository,
        user_repo: UserRepository,
        tenant_repo: TenantRepository,
    ) -> None:
        self.token_repo = token_repo
        self.user_repo = user_repo
        self.tenant_repo = tenant_repo

    # ── Flow A: PLATFORM_ADMIN → TENANT_ADMIN ────────────────────────────

    async def create_tenant_admin_invite(
        self,
        tenant_id: uuid.UUID,
        tenant_name: str,
        admin_input: TenantAdminInput,
        invited_by_id: uuid.UUID | None,
        inviter_name: str,
    ) -> TenantAdminCreated:
        settings = get_settings()

        role_obj = await self.user_repo.get_role_by_name("TENANT_ADMIN")
        if role_obj is None:
            raise HTTPException(
                status_code=500,
                detail={
                    "error_code": "ROLE_NOT_FOUND",
                    "message": "TENANT_ADMIN role is not seeded in the database.",
                },
            )

        username = admin_input.username or admin_input.email.split("@")[0][:16]

        new_user = await self.user_repo.create_inactive(
            user_name=username,
            tenant_id=tenant_id,
            role_id=role_obj.role_id,
            email=admin_input.email,
            full_name=admin_input.full_name,
        )

        raw_token = generate_raw_token()
        print(f"\n==================================================")
        print(f"🚀 [LOCAL TEST] RAW TOKEN FOR {admin_input.email}:")
        print(f"   {raw_token}")
        print(f"==================================================\n")
        
        expires_in = settings.invite_token_expire_hours
        token_record = await self.token_repo.create(
            user_id=new_user.user_id,
            tenant_id=tenant_id,
            raw_token=raw_token,
            expires_in_hours=expires_in,
            token_type=TOKEN_INVITATION,
            invited_by=invited_by_id,
        )

        await self.token_repo.session.commit()

        display_sender = "RAG Platform" if inviter_name == "PLATFORM_ADMIN" else inviter_name

        asyncio.create_task(
            send_invitation_email(
                to_email=admin_input.email,
                invitee_name=admin_input.full_name,
                tenant_name=tenant_name,
                inviter_display=display_sender,
                raw_token=raw_token,
                expires_in_hours=expires_in,
                invitee_role="Tenant Admin",
            )
        )

        logger.info(
            "tenant_admin_invite_sent",
            user_id=str(new_user.user_id),
            tenant_id=str(tenant_id),
            email=admin_input.email,
        )

        return TenantAdminCreated(
            user_id=new_user.user_id,
            email=admin_input.email,
            user_name=new_user.user_name,
            role="TENANT_ADMIN",
            status="pending_invitation",
            invitation_sent=True,
            invitation_expires_at=token_record.expires_at,
        )

    async def resend_tenant_admin_invite(
        self,
        tenant_id: uuid.UUID,
        inviter_name: str,
    ) -> ResendInviteResponse:
        settings = get_settings()

        tenant = await self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise TenantNotFoundError(str(tenant_id))

        pending = await self.token_repo.get_tenant_admin_pending(tenant_id)
        if pending is None:
            raise InvitationNotFoundError(
                "No pending TENANT_ADMIN invitation found for this tenant. "
                "The admin may have already accepted their invite."
            )

        admin_user = pending.user
        if admin_user.status == 'active':
            raise InvitationAlreadyAcceptedError()

        await self.token_repo.revoke_pending_for_user(admin_user.user_id)

        raw_token = generate_raw_token()
        expires_in = settings.invite_token_expire_hours
        new_record = await self.token_repo.create(
            user_id=admin_user.user_id,
            tenant_id=tenant_id,
            raw_token=raw_token,
            expires_in_hours=expires_in,
            token_type=TOKEN_INVITATION,
        )
        await self.token_repo.session.commit()

        display_sender = "RAG Platform" if inviter_name == "PLATFORM_ADMIN" else inviter_name

        asyncio.create_task(
            send_invitation_email(
                to_email=admin_user.email,
                invitee_name=admin_user.user_name,
                tenant_name=tenant.tenant_name,
                inviter_display=display_sender,
                raw_token=raw_token,
                expires_in_hours=expires_in,
                invitee_role="Tenant Admin",
            )
        )

        logger.info(
            "tenant_admin_invite_resent",
            tenant_id=str(tenant_id),
            user_id=str(admin_user.user_id),
        )

        return ResendInviteResponse(
            message=f"Invitation re-sent to {admin_user.email}",
            invitation_expires_at=new_record.expires_at,
        )

    # ── Flow B: TENANT_ADMIN → Users (bulk) ──────────────────────────────

    async def bulk_invite_users(
        self,
        tenant_id: uuid.UUID,
        request: BulkInviteRequest,
        caller_role: str,
        caller_tenant_id: str,
        inviter_name: str,
        caller_user_id: uuid.UUID | None,
    ) -> BulkInviteResponse:
        if caller_role == "TENANT_ADMIN":
            if str(tenant_id) != caller_tenant_id:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error_code": "PERMISSION_DENIED",
                        "message": "TENANT_ADMIN can only invite users to their own tenant.",
                    },
                )
            if request.role_name not in ["USER", "TENANT_ADMIN"]:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error_code": "PERMISSION_DENIED",
                        "message": "TENANT_ADMIN can only assign the 'USER' or 'TENANT_ADMIN' role.",
                    },
                )

        tenant = await self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise TenantNotFoundError(str(tenant_id))

        role_obj = await self.user_repo.get_role_by_name(request.role_name)
        if role_obj is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "INVALID_ROLE",
                    "message": f"Role '{request.role_name}' does not exist.",
                },
            )

        settings = get_settings()
        expires_in = request.expires_in_hours

        invited: list[InvitedUserResult] = []
        skipped: list[SkippedUserResult] = []
        email_tasks: list[tuple[str, str, str]] = []

        display_sender = "RAG Platform" if caller_role == "PLATFORM_ADMIN" else tenant.tenant_name

        for invitee in request.invitees:
            try:
                username = invitee.username or invitee.email.split("@")[0][:16]
                new_user = await self.user_repo.create_inactive(
                    user_name=username,
                    tenant_id=tenant_id,
                    role_id=role_obj.role_id,
                    email=invitee.email,
                    full_name=invitee.full_name,
                )
            except Exception as exc:
                from app.core.errors import EmailAlreadyExistsError, UserAlreadyExistsError
                if isinstance(exc, (EmailAlreadyExistsError, UserAlreadyExistsError)):
                    skipped.append(
                        SkippedUserResult(
                            email=invitee.email,
                            reason="EMAIL_ALREADY_REGISTERED",
                        )
                    )
                    continue
                raise

            raw_token = generate_raw_token()
            print(f"🚀 [LOCAL TEST] RAW TOKEN FOR {invitee.email}: {raw_token}")
            await self.token_repo.create(
                user_id=new_user.user_id,
                tenant_id=tenant_id,
                raw_token=raw_token,
                expires_in_hours=expires_in,
                token_type=TOKEN_INVITATION,
                invited_by=caller_user_id,
            )

            invited.append(
                InvitedUserResult(
                    email=invitee.email,
                    user_id=new_user.user_id,
                    status="invited",
                )
            )
            email_tasks.append((invitee.email, invitee.full_name, raw_token))

        await self.token_repo.session.commit()

        for to_email, full_name, raw_token in email_tasks:
            asyncio.create_task(
                send_invitation_email(
                    to_email=to_email,
                    invitee_name=full_name,
                    tenant_name=tenant.tenant_name,
                    inviter_display=display_sender,
                    raw_token=raw_token,
                    expires_in_hours=expires_in,
                    invitee_role="Tenant Admin" if request.role_name == "TENANT_ADMIN" else "Member",
                )
            )

        logger.info(
            "bulk_invite_sent",
            tenant_id=str(tenant_id),
            invited=len(invited),
            skipped=len(skipped),
        )

        return BulkInviteResponse(
            invited=invited,
            skipped=skipped,
            total_invited=len(invited),
            total_skipped=len(skipped),
        )

    async def list_invitations(
        self,
        tenant_id: uuid.UUID,
        caller_role: str,
        caller_tenant_id: str,
        status_filter: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> InvitationListResponse:
        if caller_role == "TENANT_ADMIN" and str(tenant_id) != caller_tenant_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "PERMISSION_DENIED",
                    "message": "TENANT_ADMIN can only list invitations for their own tenant.",
                },
            )

        records, total = await self.token_repo.list_by_tenant(
            tenant_id=tenant_id,
            status_filter=status_filter,
            page=page,
            page_size=page_size,
        )

        return InvitationListResponse(
            invitations=[_to_invitation_status(r) for r in records],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def revoke_invitation(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        caller_role: str,
        caller_tenant_id: str,
    ) -> None:
        if caller_role == "TENANT_ADMIN" and str(tenant_id) != caller_tenant_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "PERMISSION_DENIED",
                    "message": "TENANT_ADMIN can only revoke invitations for their own tenant.",
                },
            )

        user = await self.user_repo.get_by_id_include_inactive(user_id)
        if not user or user.tenant_id != tenant_id:
            raise UserNotFoundError(str(user_id))
        
        if user.status not in ('pending_invitation', 'expired', 'revoked'):
            raise InvitationAlreadyAcceptedError()

        await self.token_repo.revoke_pending_for_user(user_id)
        
        if user.status != 'revoked':
            user.status = 'revoked'

        await self.token_repo.session.commit()

        logger.info("invitation_revoked", user_id=str(user_id))

    async def resend_user_invite(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        caller_role: str,
        caller_tenant_id: str,
        inviter_name: str,
    ) -> ResendInviteResponse:
        if caller_role == "TENANT_ADMIN" and str(tenant_id) != caller_tenant_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "PERMISSION_DENIED",
                    "message": "TENANT_ADMIN can only resend invitations for their own tenant.",
                },
            )

        user = await self.user_repo.get_by_id_include_inactive(user_id)
        if not user or user.tenant_id != tenant_id:
            raise UserNotFoundError(str(user_id))
        
        if user.status not in ('pending_invitation', 'expired', 'revoked'):
            raise InvitationAlreadyAcceptedError()

        tenant = await self.tenant_repo.get_by_id(tenant_id)
        settings = get_settings()

        await self.token_repo.revoke_pending_for_user(user_id)
        
        if user.status in ('expired', 'revoked'):
            user.status = 'pending_invitation'

        raw_token = generate_raw_token()
        new_record = await self.token_repo.create(
            user_id=user_id,
            tenant_id=tenant_id,
            raw_token=raw_token,
            expires_in_hours=settings.invite_token_expire_hours,
            token_type=TOKEN_INVITATION,
        )
        await self.token_repo.session.commit()

        display_sender = "RAG Platform" if caller_role == "PLATFORM_ADMIN" else (tenant.tenant_name if tenant else str(tenant_id))

        asyncio.create_task(
            send_invitation_email(
                to_email=user.email,
                invitee_name=user.user_name,
                tenant_name=tenant.tenant_name if tenant else str(tenant_id),
                inviter_display=display_sender,
                raw_token=raw_token,
                expires_in_hours=settings.invite_token_expire_hours,
                invitee_role="Tenant Admin" if user.role.role_name == "TENANT_ADMIN" else "Member",
            )
        )

        logger.info(
            "invitation_resent",
            user_id=str(user_id),
        )

        return ResendInviteResponse(
            message=f"Invitation re-sent to {user.email}",
            invitation_expires_at=new_record.expires_at,
        )

    # ── Password Reset Flow ──────────────────────────────────────────────

    async def request_reset(self, email: str) -> None:
        """
        Initiate the password reset flow.
        """
        settings = get_settings()
        user = await self.user_repo.get_by_email(email)

        if user is None:
            logger.info("password_reset_requested_unknown_email", email=email)
            raise HTTPException(
                status_code=404,
                detail={
                    "error_code": "USER_NOT_FOUND",
                    "message": "Không tìm thấy tài khoản với email này.",
                },
            )
            
        if user.status != "active":
            logger.info("password_reset_requested_for_inactive_user", email=email, status=user.status)
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "USER_NOT_ACTIVATED",
                    "message": "Tài khoản của bạn chưa được kích hoạt hoặc đã bị vô hiệu hóa.",
                },
            )

        await self.token_repo.revoke_pending_for_user(
            user_id=user.user_id,
            token_type=TOKEN_PASSWORD_RESET,
        )

        raw_token = generate_raw_token()
        expires_in_minutes = settings.password_reset_token_expire_minutes

        await self.token_repo.create_reset_token(
            user_id=user.user_id,
            raw_token=raw_token,
            expires_in_minutes=expires_in_minutes,
        )
        await self.token_repo.session.commit()

        asyncio.create_task(
            send_password_reset_email(
                to_email=user.email or email,
                user_name=user.user_name,
                raw_token=raw_token,
                expires_in_minutes=expires_in_minutes,
            )
        )

        logger.info(
            "password_reset_email_sent",
            user_id=str(user.user_id),
            email=email,
        )

    # ── Shared Validation and Consumption ────────────────────────────────

    async def validate_token(self, raw_token: str, token_type: str) -> dict:
        """
        Validate a token and return context for the frontend (read-only).
        """
        record = await self.token_repo.get_by_raw_token(raw_token, token_type=token_type)
        
        if record is None:
            return {
                "valid": False,
                "error_code": "INVALID_TOKEN",
                "message": "This link is invalid or has already been used.",
            }

        if record.is_revoked:
            return {
                "valid": False,
                "error_code": "TOKEN_REVOKED",
                "message": "This link has been revoked.",
            }

        if record.accepted_at is not None:
            return {
                "valid": False,
                "error_code": "TOKEN_ALREADY_USED",
                "message": "This link has already been used.",
            }

        if record.expires_at < datetime.now(timezone.utc):
            if token_type == TOKEN_INVITATION:
                user = record.user
                if user and user.status == 'pending_invitation':
                    user.status = 'expired'
                    await self.token_repo.session.commit()
            return {
                "valid": False,
                "error_code": "TOKEN_EXPIRED",
                "message": "This link has expired. Please request a new one.",
            }

        user = record.user
        tenant_name = None
        if record.tenant_id:
            tenant = await self.tenant_repo.get_by_id(record.tenant_id)
            tenant_name = tenant.tenant_name if tenant else None

        return {
            "valid": True,
            "email": user.email if user else None,
            "user_name": user.user_name if user else None,
            "full_name": user.user_name if user else None,
            "tenant_name": tenant_name,
            "role": user.role.role_name if user and user.role else None,
            "expires_at": record.expires_at.isoformat(),
        }

    async def consume_token(
        self,
        raw_token: str,
        token_type: str,
        new_password: str,
    ) -> dict:
        """
        Accept an invitation or reset password: validate token, set password, activate.
        """
        record = await self.token_repo.get_by_raw_token(raw_token, token_type=token_type)

        if record is None or record.is_revoked or record.accepted_at is not None:
            if token_type == TOKEN_INVITATION:
                raise InvalidInviteTokenError()
            raise ValueError("INVALID_TOKEN")

        if record.expires_at < datetime.now(timezone.utc):
            if token_type == TOKEN_INVITATION:
                user = record.user
                if user and user.status == 'pending_invitation':
                    user.status = 'expired'
                    await self.token_repo.session.commit()
                raise TokenExpiredError()
            raise ValueError("TOKEN_EXPIRED")

        user = await self.user_repo.activate_and_set_password(
            user_id=record.user_id,
            plain_password=new_password,
        )

        await self.token_repo.accept(record.token_id)
        await self.token_repo.session.commit()

        if token_type == TOKEN_INVITATION:
            logger.info("invitation_accepted", user_id=str(user.user_id))
            return {
                "message": "Account activated successfully. You can now log in.",
                "user": AcceptedUserInfo(
                    user_id=user.user_id,
                    email=user.email,
                    role=user.role.role_name,
                    tenant_id=user.tenant_id,
                ).model_dump(),
            }
        else:
            logger.info("password_reset_completed", user_id=str(user.user_id))
            return {
                "message": "Password reset successfully. You can now log in with your new password.",
                "email": user.email,
            }
