"""
Shared FastAPI dependencies (Depends() factories).

Import from this module to wire service/repository instances into
route handlers without tight coupling.

Usage:
    from app.api.deps import get_tenant_id

    @router.get("/example")
    async def example(tenant_id: str = Depends(get_tenant_id)):
        ...
"""

from __future__ import annotations
###########################################
import uuid

from fastapi.exceptions import DependencyScopeError

from app.clients.client_factory import ClientFactory
from app.clients.gemini_client import GeminiClient
from app.core.custome_session import get_db_with_tenant_scope_session
from app.core.errors import TenantNotFoundError, TenantRequiredError
from app.models import Tenants
from app.repositories.document_repository import DocumentRepository
from app.services.document_service import DocumentService
from app.services.conversation_service import ConversationService
##############################################

from contextlib import asynccontextmanager

from fastapi import Header, HTTPException, Request

from typing import AsyncIterator

from fastapi.params import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.ollama_client import OllamaClient
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.token_repository import TokenRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.core.config import get_settings
from app.repositories.qdrant_repository import QdrantRepository
from app.services.chat_service import ChatService
from app.services.token_service import TokenService
from app.services.retrieval_service import RetrievalService
from app.services.chunker_service import ChunkerService
from app.services.tenant_service import TenantService
from app.services.user_service import UserService

settings = get_settings()

async def get_tenant_id(
    request: Request,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
) -> str:
    """
    Extract and validate the tenant ID.

    If the request went through JWTAuthenticationMiddleware, we extract
    the tenant_id from request.state.tenant_id.
    Otherwise, or if the user is a PLATFORM_ADMIN wishing to override,
    we look up the X-Tenant-ID header.

    Raises:
        HTTPException 400: If the tenant ID is missing or blank.

    Returns:
        The tenant ID string.
    """
    tenant_id_str = getattr(request.state, "tenant_id", None)
    user_role = getattr(request.state, "role", None)

    # PLATFORM_ADMIN can override tenant using X-Tenant-ID header
    if user_role == "PLATFORM_ADMIN" and x_tenant_id and x_tenant_id.strip():
        tenant_id_str = x_tenant_id.strip()
    elif not tenant_id_str and x_tenant_id and x_tenant_id.strip():
        tenant_id_str = x_tenant_id.strip()

    if not tenant_id_str:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "TENANT_REQUIRED",
                "message": "The X-Tenant-ID header is required for this endpoint.",
            },
        )
    return str(tenant_id_str).strip()


"""
    Có ai gọi Depends(get_db_session) thì sẽ gọi vào bên trong đây
    + gọi rồi chạy tới yield -> đưa session ra ngoài để thao tác trong request
    + sau khi request kết thúc thì chạy vào đây sau dòng yield lại đóng session - thoát khỏi vùng using5
"""
async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_maker = request.app.state.db_sessionmaker # lấy db từ state của app
    
    tenant_name: str | None = getattr(request.state, "tenant_name", None)
    tenant_id = getattr(request.state, "tenant_id", None)
    
    # Query tenant_name if not available
    if not tenant_name and tenant_id:
        async with session_maker() as temp_session:
            from sqlalchemy import text
            result = await temp_session.execute(
                text("SELECT tenant_name FROM public.tenants WHERE tenant_id = :tid"),
                {"tid": str(tenant_id)}
            )
            tenant_name = result.scalar_one_or_none()
            if tenant_name:
                request.state.tenant_name = tenant_name

    # Create the actual session for the request, injecting schema_translate_map if we have a tenant
    if tenant_name:
        engine = request.app.state.db_engine
        async with get_db_with_tenant_scope_session(engine=engine, session_maker=session_maker, tenant_name=tenant_name) as session:
            yield session
    else:
        async with session_maker() as session:
            yield session


async def get_ollama_client(request: Request) -> OllamaClient:
    # AsyncClient đã được khởi tạo trong lifespan của main.py, dùng chung cả app
    return OllamaClient(client=request.app.state.ollama_client)

async def get_gemini_client(request: Request) -> GeminiClient:
    return GeminiClient(client=request.app.state.gemini_client)

async def get_client_factory(
        ollama_client: OllamaClient = Depends(get_ollama_client),
        gemini_client: GeminiClient =  Depends(get_gemini_client)) -> ClientFactory:
    return ClientFactory(ollama_client=ollama_client, gemini_client=gemini_client)

async def get_qdrant_repo(request: Request) -> QdrantRepository:
    # Lấy client đã được khởi tạo trong lifespan của main.py
    qdrant_client = request.app.state.qdrant_client 
    return QdrantRepository(client=qdrant_client, vector_size=settings.rag_vector_size)


"""
    Truyền vào context để có cái khởi tạo repo rồi mới có cái khởi tạo service
"""
async def get_tenant_service(
    session: AsyncSession = Depends(get_db_session),
    qdrant_repo: QdrantRepository = Depends(get_qdrant_repo)
) -> TenantService:
    tenant_repo = TenantRepository(session)
    user_repo = UserRepository(session)
    tenant_service = TenantService(tenant_repo, qdrant_repo, user_repo)
    return tenant_service

async def get_user_service(session: AsyncSession = Depends(get_db_session)) -> UserService:
    user_repo = UserRepository(session)
    user_service = UserService(user_repo)
    return user_service



##################################################################
# async def get_current_tenant(
#     request: Request,
#     x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
#     session: AsyncSession = Depends(get_db_session),
# ) -> Tenants:
#     """
#     Validate tenant ID from either request state (JWT payload) or X-Tenant-ID header.
    
#     The tenant must exist in the database and not be soft-deleted.
#     """
#     tenant_id_str = getattr(request.state, "tenant_id", None)
#     user_role = getattr(request.state, "role", None)

#     # PLATFORM_ADMIN can override tenant using X-Tenant-ID header
#     if user_role == "PLATFORM_ADMIN" and x_tenant_id and x_tenant_id.strip():
#         tenant_id_str = x_tenant_id.strip()
#     elif not tenant_id_str and x_tenant_id and x_tenant_id.strip():
#         tenant_id_str = x_tenant_id.strip()

#     if not tenant_id_str:
#         raise TenantRequiredError()

#     try:
#         tenant_uuid = uuid.UUID(str(tenant_id_str).strip())
#     except ValueError:
#         raise TenantNotFoundError(str(tenant_id_str))

#     tenant_repo = TenantRepository(session)
#     tenant = await tenant_repo.get_by_id(tenant_uuid)
#     if tenant is None:
#         raise TenantNotFoundError(str(tenant_id_str))

#     return tenant
async def get_current_tenant(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> Tenants:
    tenant_id_raw = getattr(request.state, "tenant_id", None)
    if not tenant_id_raw:
        raise TenantRequiredError()

    if isinstance(tenant_id_raw, uuid.UUID):
        tenant_uuid = tenant_id_raw
    else:
        try:
            tenant_uuid = uuid.UUID(str(tenant_id_raw).strip())
        except ValueError:
            raise TenantNotFoundError(str(tenant_id_raw))

    tenant_repo = TenantRepository(session)
    tenant = await tenant_repo.get_by_id(tenant_uuid)

    if tenant is None:
        raise TenantNotFoundError(str(tenant_id_raw))

    return tenant


async def get_document_service(
    session: AsyncSession = Depends(get_db_session),
    qdrant_repo: QdrantRepository = Depends(get_qdrant_repo),
) -> DocumentService:
    return DocumentService(DocumentRepository(session), qdrant_repo)

async def get_chunker_service() -> ChunkerService:
    return ChunkerService()

async def get_retrieval_service(
    qdrant_repo: QdrantRepository = Depends(get_qdrant_repo),
    embedding_client: ChunkerService = Depends(get_chunker_service),
) -> RetrievalService:
    return RetrievalService(qdrant_repo, embedding_client)

async def get_conversation_repository(
    session: AsyncSession = Depends(get_db_session),
) -> ConversationRepository:
    return ConversationRepository(session)


async def get_conversation_service(
    conversation_repo: ConversationRepository = Depends(get_conversation_repository),
) -> ConversationService:
    return ConversationService(conversation_repo)


async def get_chat_service(
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
    client_factory: ClientFactory = Depends(get_client_factory),
    conversation_repo: ConversationRepository = Depends(get_conversation_repository),
) -> ChatService:
    return ChatService(retrieval_service, client_factory, conversation_repo)


async def get_user_repository(session: AsyncSession = Depends(get_db_session)) -> UserRepository:
    return UserRepository(session)


async def get_token_repository(session: AsyncSession = Depends(get_db_session)) -> TokenRepository:
    return TokenRepository(session)


async def get_auth_service(repo: UserRepository = Depends(get_user_repository)) -> AuthService:
    return AuthService(repo)


async def get_token_service(
    session: AsyncSession = Depends(get_db_session),
    qdrant_repo: QdrantRepository = Depends(get_qdrant_repo),
) -> TokenService:
    """
    Build a TokenService with all required repositories.

    Shares the same DB session as other services in the same request so
    all DB operations participate in the same transaction context.
    """
    token_repo = TokenRepository(session)
    user_repo = UserRepository(session)
    tenant_repo = TenantRepository(session)
    return TokenService(token_repo, user_repo, tenant_repo)
