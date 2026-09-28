"""
Global exception handlers and error formatting utilities.

This module provides FastAPI exception handlers that ensure every error
response — whether from validation, a missing resource, or an unexpected
crash — is returned in the standard ``ErrorResponse`` JSON envelope.

Usage:
    Register handlers in the FastAPI app factory:

    from app.core.errors import register_exception_handlers
    register_exception_handlers(app)
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger, request_id_ctx
from app.schemas.common import ErrorResponse

logger = get_logger(__name__)

class DocumentNotFoundError(Exception):
    """Raised when a document does not exist or is already soft-deleted."""

    def __init__(self, doc_id: str) -> None:
        self.doc_id = doc_id
        super().__init__(f"Document '{doc_id}' not found.")


class ConversationNotFoundError(Exception):
    """Raised when a conversation does not exist or belongs to a different tenant."""

    def __init__(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        super().__init__(f"Conversation '{conversation_id}' not found.")

class FileTooLargeError(Exception):
    def __init__(self, max_mb: int) -> None:
        self.max_mb = max_mb
        super().__init__(f"File vượt quá {max_mb}MB")


class UnsupportedFileTypeError(Exception):
    def __init__(self, ext: str) -> None:
        self.ext = ext
        super().__init__(f"Định dạng file '{ext}' không được hỗ trợ.")


class EmptyFileError(Exception):
    def __init__(self) -> None:
        super().__init__("File rỗng, không thể lưu vào hệ thống.")

class DuplicateContentError(Exception):
    def __init__(self, existing_doc_name: str) -> None:
        self.existing_doc_name = existing_doc_name
        super().__init__(
            f"Nội dung này đã tồn tại trong tài liệu '{existing_doc_name}'."
        )
class TenantNotFoundError(Exception):
    """Raised when a tenant ID does not exist in the database."""

    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id
        super().__init__(f"Tenant '{tenant_id}' not found.")


class TenantRequiredError(Exception):
    """Raised when the X-Tenant-ID header is missing."""


class TenantAlreadyExistsError(Exception):
    """Raised when trying to create a tenant that already exists."""
    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id
        super().__init__(f"Tenant '{tenant_id}' already exists.")

class TenantAlreadyExistsErrorWithName(Exception):
    """Raised when trying to create a tenant that already exists."""
    def __init__(self, tenant_name: str) -> None:
        self.tenant_name = tenant_name
        super().__init__(f"Tenant '{tenant_name}' already exists.")

class QdrantCollectionCreationError(Exception):
    """Raised when failing to create a Qdrant collection."""
    def __init__(self, tenant_id: str, detail: str) -> None:
        self.tenant_id = tenant_id
        self.detail = detail
        super().__init__(f"Failed to create vector collection for tenant '{tenant_id}': {detail}")


class UserNotFoundError(Exception):
    """Raised when a user UUID does not exist or is inactive."""

    def __init__(self, user_id: object) -> None:
        self.user_id = user_id
        super().__init__(f"User '{user_id}' not found.")


class UserAlreadyExistsError(Exception):
    """Raised when trying to create a user whose (tenant_id, user_name) already exists."""

    def __init__(self, user_name: str) -> None:
        self.user_name = user_name
        super().__init__(f"User '{user_name}' already exists.")


class EmailAlreadyExistsError(Exception):
    """Raised when trying to register an email that is already in use platform-wide."""

    def __init__(self, email: str) -> None:
        self.email = email
        super().__init__(f"Email '{email}' is already registered on this platform.")


class PermissionDeniedError(Exception):
    """Raised when a caller attempts an action their role does not permit."""

    def __init__(self, message: str = "You do not have permission to perform this action.") -> None:
        self.message = message
        super().__init__(message)


class InvitationNotFoundError(Exception):
    """Raised when an invitation token/ID does not exist or belongs to another tenant."""

    def __init__(self, invitation_id: str = "") -> None:
        self.invitation_id = invitation_id
        super().__init__(f"Invitation '{invitation_id}' not found.")


class InvitationAlreadyAcceptedError(Exception):
    """Raised when trying to revoke or resend an invitation that was already accepted."""

    def __init__(self) -> None:
        super().__init__("This invitation has already been accepted and cannot be modified.")


class InvalidInviteTokenError(Exception):
    """Raised when an invitation token is invalid, revoked, or already used."""

    def __init__(self) -> None:
        super().__init__("The invitation token is invalid, revoked, or has already been used.")


class TokenExpiredError(Exception):
    """Raised when an invitation token has passed its expiry timestamp."""

    def __init__(self) -> None:
        super().__init__("This invitation link has expired. Please request a new one.")

def register_exception_handlers(app: FastAPI) -> None:
    """
    Attach all global exception handlers to the FastAPI application.

    Args:
        app: The FastAPI application instance.
    """
    app.add_exception_handler(RequestValidationError, _validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(TenantNotFoundError, _tenant_not_found_handler)  # type: ignore[arg-type]
    app.add_exception_handler(TenantRequiredError, _tenant_required_handler)  # type: ignore[arg-type]
    app.add_exception_handler(TenantAlreadyExistsError, _tenant_already_exists_handler)
    app.add_exception_handler(TenantAlreadyExistsErrorWithName, _tenant_already_exists_with_name_handler)
    app.add_exception_handler(QdrantCollectionCreationError, _qdrant_creation_error_handler)
    app.add_exception_handler(UserNotFoundError, _user_not_found_handler)  # type: ignore[arg-type]
    app.add_exception_handler(UserAlreadyExistsError, _user_already_exists_handler)  # type: ignore[arg-type]
    app.add_exception_handler(EmailAlreadyExistsError, _email_already_exists_handler)  # type: ignore[arg-type]
    app.add_exception_handler(PermissionDeniedError, _permission_denied_handler)  # type: ignore[arg-type]
    app.add_exception_handler(InvitationNotFoundError, _invitation_not_found_handler)  # type: ignore[arg-type]
    app.add_exception_handler(InvitationAlreadyAcceptedError, _invitation_already_accepted_handler)  # type: ignore[arg-type]
    app.add_exception_handler(InvalidInviteTokenError, _invalid_invite_token_handler)  # type: ignore[arg-type]
    app.add_exception_handler(TokenExpiredError, _token_expired_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _generic_error_handler)
    app.add_exception_handler(DocumentNotFoundError, _document_not_found_handler)
    app.add_exception_handler(ConversationNotFoundError, _conversation_not_found_handler)
    app.add_exception_handler(DuplicateContentError, _duplicate_content_handler)
    app.add_exception_handler(FileTooLargeError, _file_too_large_handler)
    app.add_exception_handler(UnsupportedFileTypeError, _unsupported_file_type_handler)
    app.add_exception_handler(EmptyFileError, _empty_file_handler)


# =============================================================================
# Individual handlers
# =============================================================================


async def _validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Convert Pydantic / FastAPI validation errors → HTTP 422."""
    logger.warning(
        "validation_error",
        endpoint=request.url.path,
        error_code="VALIDATION_ERROR",
        errors=exc.errors(),
    )
    errors = exc.errors()
    error_msgs = []
    for err in errors:
        field = err.get("loc", [""])[-1]
        msg = err.get("msg", "")
        error_msgs.append(f"'{field}': {msg}")
    formatted_message = "Dữ liệu không hợp lệ: " + ", ".join(error_msgs)

    body = ErrorResponse(
        error_code="VALIDATION_ERROR",
        message=formatted_message,
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=422, content=body.model_dump(mode="json"))


async def _tenant_not_found_handler(
    request: Request,
    exc: TenantNotFoundError,
) -> JSONResponse:
    """Return HTTP 404 when the tenant does not exist."""
    logger.warning(
        "tenant_not_found",
        endpoint=request.url.path,
        tenant_id=exc.tenant_id,
    )
    body = ErrorResponse(
        error_code="TENANT_NOT_FOUND",
        message=str(exc),
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=404, content=body.model_dump(mode="json"))


async def _tenant_required_handler(
    request: Request,
    exc: TenantRequiredError,
) -> JSONResponse:
    """Return HTTP 400 when the X-Tenant-ID header is absent."""
    logger.warning(
        "tenant_required",
        endpoint=request.url.path,
    )
    body = ErrorResponse(
        error_code="TENANT_REQUIRED",
        message="The X-Tenant-ID header is required for this endpoint.",
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=400, content=body.model_dump(mode="json"))


async def _tenant_already_exists_handler(request: Request, exc: TenantAlreadyExistsError) -> JSONResponse:
    logger.warning("tenant_already_exists", endpoint=request.url.path, tenant_id=exc.tenant_id)
    body = ErrorResponse(
        error_code="TENANT_ALREADY_EXISTS",
        message=str(exc),
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))


async def _qdrant_creation_error_handler(request: Request, exc: QdrantCollectionCreationError) -> JSONResponse:
    logger.error("qdrant_collection_creation_failed", endpoint=request.url.path, tenant_id=exc.tenant_id, detail=exc.detail)
    body = ErrorResponse(
        error_code="QDRANT_CREATION_FAILED",
        message="Could not provision vector database resources. Please try again later.",
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=500, content=body.model_dump(mode="json"))


async def _user_not_found_handler(
    request: Request,
    exc: UserNotFoundError,
) -> JSONResponse:
    """Return HTTP 404 when the user does not exist or is inactive."""
    logger.warning(
        "user_not_found",
        endpoint=request.url.path,
        user_id=str(exc.user_id),
    )
    body = ErrorResponse(
        error_code="USER_NOT_FOUND",
        message=str(exc),
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=404, content=body.model_dump(mode="json"))


async def _user_already_exists_handler(
    request: Request,
    exc: UserAlreadyExistsError,
) -> JSONResponse:
    """Return HTTP 409 when the username is already taken within the tenant."""
    logger.warning(
        "user_already_exists",
        endpoint=request.url.path,
        user_name=exc.user_name,
    )
    body = ErrorResponse(
        error_code="USER_ALREADY_EXISTS",
        message=str(exc),
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))


async def _generic_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Catch-all handler for unhandled exceptions → HTTP 500."""
    logger.exception(
        "unhandled_exception",
        endpoint=request.url.path,
        error_code="INTERNAL_SERVER_ERROR",
        error=str(exc),
    )
    body = ErrorResponse(
        error_code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred. Please try again later.",
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=500, content=body.model_dump(mode="json"))

async def _document_not_found_handler(
    request: Request,
    exc: DocumentNotFoundError,
) -> JSONResponse:
    logger.warning("document_not_found", endpoint=request.url.path, doc_id=exc.doc_id)
    body = ErrorResponse(
        error_code="DOCUMENT_NOT_FOUND",
        message=str(exc),
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=404, content=body.model_dump(mode="json"))


async def _conversation_not_found_handler(
    request: Request,
    exc: ConversationNotFoundError,
) -> JSONResponse:
    logger.warning("conversation_not_found", endpoint=request.url.path, conversation_id=exc.conversation_id)
    body = ErrorResponse(
        error_code="CONVERSATION_NOT_FOUND",
        message=str(exc),
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=404, content=body.model_dump(mode="json"))


async def _tenant_already_exists_with_name_handler(
    request: Request,
    exc: TenantAlreadyExistsErrorWithName,
) -> JSONResponse:
    """Return HTTP 409 when a tenant with the same name already exists."""
    logger.warning("tenant_already_exists", endpoint=request.url.path, tenant_name=exc.tenant_name)
    body = ErrorResponse(
        error_code="TENANT_ALREADY_EXISTS",
        message=str(exc),
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))


async def _email_already_exists_handler(
    request: Request,
    exc: EmailAlreadyExistsError,
) -> JSONResponse:
    """Return HTTP 409 when the email is already registered platform-wide."""
    logger.warning(
        "email_already_exists",
        endpoint=request.url.path,
        email=exc.email,
    )
    body = ErrorResponse(
        error_code="EMAIL_ALREADY_EXISTS",
        message=str(exc),
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))


async def _permission_denied_handler(
    request: Request,
    exc: PermissionDeniedError,
) -> JSONResponse:
    """Return HTTP 403 when an action is not permitted for the caller's role."""
    logger.warning(
        "permission_denied",
        endpoint=request.url.path,
        message=exc.message,
    )
    body = ErrorResponse(
        error_code="PERMISSION_DENIED",
        message=exc.message,
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=403, content=body.model_dump(mode="json"))

async def _duplicate_content_handler(
    request: Request,
    exc: DuplicateContentError,
) -> JSONResponse:
    logger.warning("duplicate_content", endpoint=request.url.path, existing_doc_name=exc.existing_doc_name)
    body = ErrorResponse(
        error_code="DUPLICATE_CONTENT",
        message=str(exc),
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))

async def _file_too_large_handler(
    request: Request,
    exc: FileTooLargeError,
) -> JSONResponse:
    logger.warning("file_too_large", endpoint=request.url.path, max_mb=exc.max_mb)
    body = ErrorResponse(
        error_code="FILE_TOO_LARGE",
        message=str(exc),
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=413, content=body.model_dump(mode="json"))


async def _unsupported_file_type_handler(
    request: Request,
    exc: UnsupportedFileTypeError,
) -> JSONResponse:
    logger.warning("unsupported_file_type", endpoint=request.url.path, ext=exc.ext)
    body = ErrorResponse(
        error_code="UNSUPPORTED_FILE_TYPE",
        message=str(exc),
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=422, content=body.model_dump(mode="json"))


async def _empty_file_handler(
    request: Request,
    exc: EmptyFileError,
) -> JSONResponse:
    logger.warning("empty_file", endpoint=request.url.path)
    body = ErrorResponse(
        error_code="EMPTY_FILE",
        message=str(exc),
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=422, content=body.model_dump(mode="json"))


# =============================================================================
# Invitation error handlers
# =============================================================================


async def _invitation_not_found_handler(
    request: Request,
    exc: InvitationNotFoundError,
) -> JSONResponse:
    """Return HTTP 404 when an invitation does not exist in the given tenant."""
    logger.warning(
        "invitation_not_found",
        endpoint=request.url.path,
        invitation_id=exc.invitation_id,
    )
    body = ErrorResponse(
        error_code="INVITATION_NOT_FOUND",
        message=str(exc),
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=404, content=body.model_dump(mode="json"))


async def _invitation_already_accepted_handler(
    request: Request,
    exc: InvitationAlreadyAcceptedError,
) -> JSONResponse:
    """Return HTTP 409 when trying to modify an already-accepted invitation."""
    logger.warning("invitation_already_accepted", endpoint=request.url.path)
    body = ErrorResponse(
        error_code="INVITATION_ALREADY_ACCEPTED",
        message=str(exc),
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))


async def _invalid_invite_token_handler(
    request: Request,
    exc: InvalidInviteTokenError,
) -> JSONResponse:
    """Return HTTP 400 when an invite token is invalid, revoked, or already used."""
    logger.warning("invalid_invite_token", endpoint=request.url.path)
    body = ErrorResponse(
        error_code="INVALID_TOKEN",
        message=str(exc),
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=400, content=body.model_dump(mode="json"))


async def _token_expired_handler(
    request: Request,
    exc: TokenExpiredError,
) -> JSONResponse:
    """Return HTTP 410 Gone when an invite token has passed its expiry."""
    logger.warning("invite_token_expired", endpoint=request.url.path)
    body = ErrorResponse(
        error_code="TOKEN_EXPIRED",
        message=str(exc),
        request_id=request_id_ctx.get(),
        timestamp=datetime.now(timezone.utc),
    )
    return JSONResponse(status_code=410, content=body.model_dump(mode="json"))
