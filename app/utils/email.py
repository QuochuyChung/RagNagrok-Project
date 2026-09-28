"""
Email sending utility.

Provides async wrappers around Python's built-in smtplib for sending
HTML system emails (invitations and password resets).

Design notes:
    - Tokens are NEVER exposed as raw text. They are embedded only inside
      the href of the CTA button, so they don't appear as readable text.
    - Email templates follow the Stitch/Cognitive Architecture design system
      (Hanken Grotesk + Inter typography, #0D0D0D primary, #10A37F accent).
    - Sender label logic:
        * PLATFORM_ADMIN → inviter_display = 'RAG platform'
        * TENANT_ADMIN   → inviter_display = <tenant_name> (company name)
    - All functions are async via asyncio.to_thread (non-blocking).

Configuration (via .env):
    SMTP_HOST       — SMTP server hostname (default: localhost)
    SMTP_PORT       — SMTP port (default: 587)
    SMTP_USERNAME   — SMTP auth username (optional)
    SMTP_PASSWORD   — SMTP auth password (optional)
    SMTP_USE_TLS    — Whether to use STARTTLS (default: true)
    SMTP_FROM_EMAIL — Sender address (default: noreply@ragnarok.local)
    SMTP_FROM_NAME  — Sender display name
    FRONTEND_BASE_URL — Base URL of the frontend for building links
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# ── Shared email wrapper ────────────────────────────────────────────────────

def _send_email_sync(
    to_email: str,
    subject: str,
    html_body: str,
) -> None:
    """
    Synchronously send an HTML email via SMTP.

    Runs inside asyncio.to_thread so it does not block the event loop.
    """
    settings = get_settings()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to_email

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if settings.smtp_use_tls:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
            server.ehlo()
            server.starttls()
            server.ehlo()
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)

        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)

        server.sendmail(settings.smtp_from_email, to_email, msg.as_string())
        server.quit()
        logger.info("email_sent", extra={"to": to_email, "subject": subject})
    except Exception as exc:
        logger.error(
            "email_send_failed",
            extra={"to": to_email, "error": str(exc)},
        )
        raise


# ── Invitation email ────────────────────────────────────────────────────────

def _build_invite_html(
    invitee_name: str,
    tenant_name: str,
    inviter_display: str,
    invite_link: str,
    expires_hours: int,
    invitee_role: str = "Member",
) -> str:
    """
    Render the invitation email as an HTML string using robust inline CSS.
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>Collaboration Invite</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f0f7f4; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
<div style="background-color: #f0f7f4; padding: 40px 20px; color: #003828;">
    <div style="max-width: 600px; margin: 0 auto; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,108,80,0.1); border: 1px solid #d1e2d8;">
        <!-- Header -->
        <div style="padding: 24px; text-align: center; background: #e0ede6; border-bottom: 1px solid #d1e2d8;">
            <h1 style="margin: 0; color: #006c50; font-size: 28px; font-weight: bold; letter-spacing: -0.5px;">RAG PLATFORM</h1>
        </div>
        <!-- Content -->
        <div style="padding: 32px 24px;">
            <h2 style="color: #006c50; font-size: 24px; margin-top: 0; margin-bottom: 16px;">Collaboration Invite</h2>
            <p style="font-size: 16px; line-height: 1.6; color: #2d4a3e; margin: 0;">
                Hello {invitee_name}, you have been invited by {inviter_display} to join the {tenant_name} workspace.
            </p>
            
            <div style="background: #f8faf9; border-radius: 8px; padding: 24px; margin: 32px 0; border: 1px solid #e0ede6;">
                <div style="font-size: 12px; font-weight: bold; color: #006c50; text-transform: uppercase; letter-spacing: 1px; opacity: 0.8;">Assigned Team</div>
                <div style="font-size: 24px; color: #006c50; font-weight: bold; margin-top: 4px; margin-bottom: 16px;">{tenant_name}</div>
                <div style="border-top: 1px solid #e0ede6; margin-bottom: 16px;"></div>
                <div style="font-size: 12px; font-weight: bold; color: #006c50; text-transform: uppercase; letter-spacing: 1px; opacity: 0.8;">Role</div>
                <div style="font-size: 16px; color: #006c50; font-weight: bold; margin-top: 4px;">{invitee_role}</div>
            </div>

            <div style="text-align: center; margin-top: 32px;">
                <a href="{invite_link}" style="display: inline-block; background-color: #5bdcb0; color: #006c50; font-weight: bold; font-size: 16px; padding: 16px 40px; border-radius: 8px; text-decoration: none; box-shadow: 0 4px 6px rgba(91,220,176,0.2);">
                    Accept Invitation
                </a>
            </div>

            <div style="margin-top: 40px; text-align: center;">
                <p style="font-size: 14px; color: #2d4a3e; margin-bottom: 8px;">Having trouble with the button? Copy this link.</p>
                <div style="background: #e0ede6; padding: 12px; border-radius: 4px; border: 1px solid #d1e2d8; font-family: monospace; font-size: 13px; color: #006c50; word-break: break-all;">
                    <a href="{invite_link}" style="color: #006c50; text-decoration: underline;">Click here or right-click to copy link</a>
                </div>
            </div>
        </div>
        
        <!-- Footer -->
        <div style="background: #f8faf9; padding: 24px; border-top: 1px solid #e0ede6; text-align: center;">
            <p style="font-size: 14px; color: #2d4a3e; opacity: 0.8; margin: 0; line-height: 1.5;">
                This is a secure communication from the RAGnarok Platform. If you were not expecting this invite, please ignore this email.
            </p>
        </div>
    </div>
    <div style="text-align: center; margin-top: 32px;">
        <p style="font-size: 12px; font-weight: bold; color: #2d4a3e; opacity: 0.6; margin: 0;">© 2026 RAGnarok Platform. All Rights Reserved.</p>
    </div>
</div>
</body>
</html>"""


async def send_invitation_email(
    to_email: str,
    invitee_name: str,
    tenant_name: str,
    inviter_display: str,
    raw_token: str,
    expires_in_hours: int = 120,
    invitee_role: str = "Member",
) -> None:
    """
    Send an invitation email asynchronously (runs SMTP in a thread).

    The token is embedded ONLY as the href of the CTA button — it is never
    visible as plaintext in the email body.

    Args:
        to_email:        Recipient email address.
        invitee_name:    Display name of the invited person.
        tenant_name:     Name of the tenant workspace they are joining.
        inviter_display: Display label for the inviter.
                         Pass 'RAG platform' for PLATFORM_ADMIN.
                         Pass the tenant_name (company) for TENANT_ADMIN.
        raw_token:       The raw (un-hashed) invite token to embed in the link.
        expires_in_hours: Token TTL shown in the email body.
    """
    settings = get_settings()
    # Token is embedded in href only — not shown as readable text
    invite_link = f"{settings.frontend_base_url}/accept-invite?token={raw_token}"
    html = _build_invite_html(
        invitee_name=invitee_name,
        tenant_name=tenant_name,
        inviter_display=inviter_display,
        invite_link=invite_link,
        expires_hours=expires_in_hours,
        invitee_role=invitee_role,
    )
    subject = f"You're invited to join {tenant_name} on RAG Platform"

    from app.profiling import LatencyTracker
    tracker = LatencyTracker("email_invitation", to_email=to_email)
    try:
        async with tracker.astage("smtp_send"):
            await asyncio.to_thread(_send_email_sync, to_email, subject, html)
    finally:
        tracker.finish()


# ── Password Reset email ────────────────────────────────────────────────────

def _build_reset_html(
    user_name: str,
    reset_link: str,
    expires_minutes: int,
) -> str:
    """Render the password reset email as an HTML string."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>Reset Your RAGnarok Password</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f0f9f6; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
<div style="background-color: #f0f9f6; padding: 40px 20px; color: #191a29;">
    <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 20px -2px rgba(91, 220, 176, 0.15); border: 1px solid #d1e5dd;">
        <!-- Header -->
        <div style="padding: 40px 24px 24px; text-align: center; background: #e8f5f1;">
            <div style="margin-bottom: 16px;">
                <img alt="RAGnarok Logo" style="height: 64px; width: 64px; object-fit: contain;" src="https://lh3.googleusercontent.com/aida-public/AB6AXuCxqGTktWyXHRCcyst4BvSCuvFnlmaiGSrciKu-ClmLrE5fHlgrG05JeP-uJ1VJqPrcjAb38LRdjXWLsVSroYWZGie826I3F19jo3_c4MVCfAusKRU4Q6rQpGNyNEoVHZzGecZ7QVxS4MaGEaN7N0aH1-7A0ncuvHk5Y0p7GNR7B3TyhVnCckP8YtyQH6jmnirOwzjdQHcG6IlG1tTE9TPjrXOE8Sp02FCRCBV79kZ7cILXBj9uzf7WAr-ND_efkvMyDs8"/>
            </div>
            <h1 style="margin: 0; color: #191a29; font-size: 24px; font-weight: 900; letter-spacing: 0.2em; text-transform: uppercase;">RAGNARok</h1>
        </div>
        <!-- Content -->
        <div style="padding: 48px 24px; text-align: center;">
            <div style="max-width: 480px; margin: 0 auto;">
                <h2 style="font-size: 24px; font-weight: 600; color: #191a29; margin-top: 0; margin-bottom: 8px;">
                    Hello {user_name},
                </h2>
                <p style="font-size: 16px; line-height: 1.5; color: #444748; margin-top: 0; margin-bottom: 32px;">
                    We received a request to reset your password for your RAGnarok account. If you made this request, please click the button below to secure your identity.
                </p>
                
                <a href="{reset_link}" style="display: inline-block; background-color: #5bdcb0; color: #003828; font-weight: bold; font-size: 16px; padding: 16px 40px; border-radius: 8px; text-decoration: none; margin-bottom: 32px;">
                    Reset Password
                </a>

                <div style="margin-bottom: 32px;">
                    <p style="font-size: 14px; color: #444748; margin: 0;">
                        Having trouble with the button? <a href="{reset_link}" style="color: #006c52; font-weight: 500; text-decoration: underline; word-break: break-all;">Click here or right-click to copy link</a>
                    </p>
                </div>

                <!-- Security Note -->
                <div style="background-color: #f0f9f6; padding: 16px; border-radius: 8px; text-align: left; border: 1px solid #d1e5dd;">
                    <div style="display: flex; align-items: flex-start; gap: 8px;">
                        <span style="color: #006c52; font-size: 18px; margin-top: 2px;">ℹ️</span>
                        <div>
                            <p style="font-size: 14px; color: #444748; margin: 0 0 4px 0;">
                                This link will expire in <span style="font-weight: bold; color: #006c52;">{expires_minutes} minutes</span>.
                            </p>
                            <p style="font-size: 14px; color: #444748; margin: 0; opacity: 0.7;">
                                If you didn't request this, you can safely ignore this email. No changes will be made to your account.
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Footer -->
        <div style="background-color: #e8f5f1; padding: 32px 24px; text-align: center; border-top: 1px solid #d1e5dd;">
            <p style="font-size: 14px; color: #444748; opacity: 0.7; margin: 0;">
                © 2026 RAGnarok Platform. All Rights Reserved.
            </p>
        </div>
    </div>
</div>
</body>
</html>"""


async def send_password_reset_email(
    to_email: str,
    user_name: str,
    raw_token: str,
    expires_in_minutes: int = 30,
) -> None:
    """
    Send a password-reset email asynchronously.

    The token is embedded ONLY as the href of the CTA button — never as visible text.

    Args:
        to_email:           Recipient email address.
        user_name:          Display name of the user.
        raw_token:          The raw (un-hashed) reset token to embed in the link.
        expires_in_minutes: Token TTL shown in the email body (default 30 min).
    """
    settings = get_settings()
    reset_link = f"{settings.frontend_base_url}/reset-password?token={raw_token}"
    html = _build_reset_html(
        user_name=user_name,
        reset_link=reset_link,
        expires_minutes=expires_in_minutes,
    )
    subject = "Reset your RAG Platform password"

    from app.profiling import LatencyTracker
    tracker = LatencyTracker("email_password_reset", to_email=to_email)
    try:
        async with tracker.astage("smtp_send"):
            await asyncio.to_thread(_send_email_sync, to_email, subject, html)
    finally:
        tracker.finish()
