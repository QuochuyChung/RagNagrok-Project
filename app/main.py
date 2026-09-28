"""
FastAPI application entry-point.

This module wires together configuration, middleware, exception handlers,
and routers into a single ASGI application.

Run locally with::

    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from asyncio import timeout
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI
from google import genai
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, async_sessionmaker
from qdrant_client import AsyncQdrantClient
from app.services.audit_logger import audit_logger

from app.api.routes.health import router as health_router
from app.api.routes.tenants import router as tenant_router
from app.api.routes.auth import router as auth_router
from app.api.routes.users import router as users_router
from app.api.routes.invitations import router as invitations_router
from app.api.routes.tokens import router as tokens_router


###############################################################
from app.api.routes.documents import router as documents_router
from app.api.routes.retrieve import router as retrieve_router
from app.api.routes.chat import router as chat_router
from app.api.routes.conversations import router as conversations_router
from ollama import AsyncClient as OllamaAsyncClient
###############################################################


from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.core.security import public
from app.middleware.jwt_auth import JWTAuthenticationMiddleware
from app.middleware.request_id import RequestIDMiddleware

logger = get_logger(__name__)


# =============================================================================
# Lifespan — replaces the deprecated @app.on_event("startup") / ("shutdown")
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Manage application-wide resources.

    * **Startup**: configure logging, create a shared ``httpx.AsyncClient``,
      initialise the SQLAlchemy async engine for PostgreSQL, and log a
      configuration summary.
    * **Shutdown**: close the HTTP client, dispose the DB engine, and log
      a clean exit.
    """
    settings = get_settings()

    # --- Startup -----------------------------------------------------------
    # 1. Initialise structured logging as early as possible
    setup_logging(settings.log_level)

    # 2. Create a shared httpx client for outbound calls (health checks,
    #    Ollama, etc.).  Sharing a single client enables connection pooling.
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=True,
    )

    # noinspection PyUnresolvedReferences
    app.state.http_client = http_client

    # 3. Initialise the async SQLAlchemy engine for PostgreSQL
    db_engine: AsyncEngine = create_async_engine(
        settings.database_url,
        pool_size=settings.postgres_pool_size,
        max_overflow=settings.postgres_max_overflow,
        # Test 1 connection bằng ping nhẹ trước khi phát ra dùng — nếu server
        # đã đóng kết nối (idle timeout, mất mạng tạm thời...) thì âm thầm mở
        # lại connection mới thay vì để lỗi "connection is closed" lộ ra tới
        # tận client. pool_recycle chủ động đóng connection quá cũ trước khi
        # DB server tự ý đóng, giảm tần suất phải fallback vào pre_ping.
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"command_timeout": settings.db_connect_timeout},
        echo=settings.debug_mode,  # Log SQL in debug mode
    )

    # noinspection PyUnresolvedReferences
    app.state.db_engine = db_engine

    # tạo 1 context riêng cho 1 session
    # noinspection PyUnresolvedReferences
    app.state.db_sessionmaker = async_sessionmaker(db_engine, expire_on_commit=False)

    ollama_client = OllamaAsyncClient(
        host=settings.ollama_url,
        timeout=settings.ollama_timeout
    )

    gemini_client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=genai.types.HttpOptions(
            timeout=settings.gemini_timeout * 1000,  # settings tính giây, SDK cần milliseconds
        ),
    )

    app.state.gemini_client = gemini_client

    app.state.ollama_client = ollama_client

    # Khởi tạo Qdrant Client
    qdrant_client = AsyncQdrantClient(
        url=f"http://{settings.qdrant_host}:{settings.qdrant_port}",
        api_key=settings.qdrant_api_key,
        timeout=settings.qdrant_timeout,
    )
    app.state.qdrant_client = qdrant_client

    audit_logger.init_app(app.state.db_sessionmaker)
    await audit_logger.start_worker()

    # 4. Log a startup summary so operators can verify config at a glance
    logger.info(
        "gateway_starting",
        host=settings.gateway_host,
        port=settings.gateway_port,
        debug_mode=settings.debug_mode,
        log_level=settings.log_level,
        version=settings.app_version,
        database=settings.postgres_host,
        qdrant=settings.qdrant_url,
        ollama=settings.ollama_url,
    )
    logger.info("gateway_started")

    # Hand control to the application
    yield

    # --- Shutdown ----------------------------------------------------------
    await audit_logger.stop_worker()
    await http_client.aclose()
    await db_engine.dispose()
    try:
        await app.state.ollama_client._client.aclose()
    except Exception:
        logger.exception("ollama_client_close_failed")
    try:
        await app.state.gemini_client.aio.aclose()
    except Exception:
        logger.exception("gemini_client_close_failed")
    try:
        qdrant_client.close()
    except Exception:
        logger.exception("qdrant_client_close_failed")
    logger.info("gateway_stopped")


# =============================================================================
# Application factory
# =============================================================================


def create_app() -> FastAPI:
    """
    Build and return a fully configured ``FastAPI`` application.

    This factory function:
    1. Reads settings from the environment.
    2. Creates the ``FastAPI`` instance with OpenAPI metadata.
    3. Registers middleware (outermost first — last registered runs first).
    4. Attaches exception handlers.
    5. Includes API routers.
    """
    settings = get_settings()

    app = FastAPI(
        title="Multi-Tenant RAG API Gateway",
        description=(
            "A multi-tenant Retrieval-Augmented Generation API gateway that "
            "orchestrates document ingestion, vector search, and LLM-powered "
            "chat via Ollama, Qdrant, and Open WebUI."
        ),
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    from app.middleware.audit_middleware import AuditLogMiddleware
    app.add_middleware(AuditLogMiddleware)

    # ── Middleware ────────────────────────────────────────────────────────
    from fastapi.middleware.cors import CORSMiddleware
    # RequestIDMiddleware attaches a request_id for tracing/log correlation.
    app.add_middleware(JWTAuthenticationMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # SECURITY: KHÔNG dùng allow_origins=["*"] với allow_credentials=True.
    # Browser spec CORS từ chối cặp này — kẻ tấn công có thể lợi dụng để
    # gửi request có cookie/session của victim đến API. Lấy origins từ
    # CORS_ALLOWED_ORIGINS env (đã được validator ở config.py check không có "*").
    cors_origins_raw = settings.cors_allowed_origins
    if isinstance(cors_origins_raw, str):
        cors_origins_list = [
            o.strip() for o in cors_origins_raw.split(",") if o.strip()
        ]
    else:
        cors_origins_list = list(cors_origins_raw)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Tenant-ID", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    # ── Exception handlers ────────────────────────────────────────────────
    register_exception_handlers(app)

    # ── Routers ───────────────────────────────────────────────────────────
    # Health & version endpoints are mounted at root for infrastructure probes.
    app.include_router(health_router)
    app.include_router(invitations_router)
    app.include_router(tenant_router)
    app.include_router(users_router)
    app.include_router(auth_router)
    app.include_router(tokens_router)



    #############################################################
    app.include_router(documents_router)
    app.include_router(retrieve_router)
    app.include_router(chat_router)
    app.include_router(conversations_router)
    #############################################################


    @public
    @app.get("/", tags=["Infrastructure"])
    async def root() -> dict[str, str]:
        """Return a small index response for the gateway root."""
        return {
            "name": app.title,
            "status": "ok",
            "health": "/health",
            "version": "/version",
            "docs": "/docs",
        }

    return app


# =============================================================================
# Module-level app instance
# =============================================================================
# Uvicorn discovers this when invoked as: uvicorn app.main:app
app: FastAPI = create_app()
