"""
Health-check and version endpoints.

Endpoints
---------
* ``GET /health``  — aggregate health of all backing services.
* ``GET /version`` — build / runtime version metadata.

Sprint 2 Scope
--------------
Health checks now cover: **FastAPI**, **PostgreSQL**, **Qdrant**, **Ollama**.
"""

from __future__ import annotations

import asyncio
import os
import platform
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import bearer_scheme, public
from app.schemas.health import (
    HealthResponse,
    ServiceHealth,
    VersionResponse,
)

logger = get_logger(__name__)

# The router has no prefix — endpoints are mounted at the root level.
router = APIRouter(tags=["Infrastructure"], dependencies=[Depends(bearer_scheme)])


# =============================================================================
# Individual service health-check helpers
# =============================================================================
# Each helper returns a ``ServiceHealth`` and is designed to be run
# concurrently via ``asyncio.gather``.  On any error the service is
# marked "down" with the error message included.


async def _check_postgres(request: Request) -> ServiceHealth:
    """
    Verify PostgreSQL connectivity by executing a lightweight ``SELECT 1``.

    Retrieves the async SQLAlchemy engine from ``app.state`` (set by lifespan).
    Returns ``down`` if the engine is not yet available or the query fails.
    """
    start = time.perf_counter()
    try:
        engine = getattr(request.app.state, "db_engine", None)
        if engine is None:
            raise RuntimeError("Database engine not initialised in app.state.")

        async with engine.connect() as conn:
            from sqlalchemy import text
            await conn.execute(text("SELECT 1"))

        latency = (time.perf_counter() - start) * 1000
        return ServiceHealth(status="up", latency_ms=round(latency, 2))
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return ServiceHealth(
            status="down",
            latency_ms=round(latency, 2),
            error=str(exc),
        )


async def _check_qdrant(http_client: httpx.AsyncClient) -> ServiceHealth:
    """Ping the Qdrant REST healthcheck endpoint."""
    settings = get_settings()
    start = time.perf_counter()
    try:
        resp = await http_client.get(
            f"{settings.qdrant_url}/healthz",
            timeout=settings.qdrant_timeout,
        )
        resp.raise_for_status()
        latency = (time.perf_counter() - start) * 1000
        return ServiceHealth(status="up", latency_ms=round(latency, 2))
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return ServiceHealth(
            status="down",
            latency_ms=round(latency, 2),
            error=str(exc),
        )


async def _check_ollama(http_client: httpx.AsyncClient) -> ServiceHealth:
    """Ping Ollama's root endpoint (returns 200 when the server is ready)."""
    settings = get_settings()
    start = time.perf_counter()
    try:
        resp = await http_client.get(
            settings.ollama_url,
            timeout=settings.ollama_timeout,
        )
        resp.raise_for_status()
        latency = (time.perf_counter() - start) * 1000
        return ServiceHealth(status="up", latency_ms=round(latency, 2))
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return ServiceHealth(
            status="down",
            latency_ms=round(latency, 2),
            error=str(exc),
        )


# async def _check_open_webui(http_client: httpx.AsyncClient) -> ServiceHealth:
#     """
#     Ping Open WebUI's health endpoint.

#     Open WebUI exposes a simple health check at its root or ``/health``
#     endpoint that returns HTTP 200 when the service is ready.
#     """
#     settings = get_settings()
#     start = time.perf_counter()
#     try:
#         resp = await http_client.get(
#             f"{settings.open_webui_url}/health",
#             timeout=5,
#         )
#         resp.raise_for_status()
#         latency = (time.perf_counter() - start) * 1000
#         return ServiceHealth(status="up", latency_ms=round(latency, 2))
#     except Exception as exc:
#         latency = (time.perf_counter() - start) * 1000
#         return ServiceHealth(
#             status="down",
#             latency_ms=round(latency, 2),
#             error=str(exc),
#         )


# =============================================================================
# Shared health response builder
# =============================================================================


async def _build_health_response(
    request: Request,
    *,
    include_details: bool,
) -> HealthResponse | JSONResponse:
    """
    Run health checks against all backing services **concurrently** and
    derive an aggregate status.

    Status logic
    -------------
    * **healthy** — every service is ``up``.
    * **degraded** — non-critical services (Open WebUI) are ``down``
      but critical ones (PostgreSQL, Qdrant, Ollama) are ``up``.  Returns HTTP 200.
    * **unhealthy** — at least one critical service is ``down``.  Returns HTTP 503.
    """
    # Retrieve the shared httpx client stored in app.state by the lifespan
    http_client: httpx.AsyncClient = request.app.state.http_client

    # Run all checks concurrently
    pg_health, qd_health, ol_health = await asyncio.gather(
        _check_postgres(request),
        _check_qdrant(http_client),
        _check_ollama(http_client),
    )

    # Build the services dict (used in debug mode)
    services: dict[str, ServiceHealth] = {
        "postgres": pg_health,
        "qdrant": qd_health,
        "ollama": ol_health,
    }

    # --- Determine aggregate status ----------------------------------------
    all_up = all(s.status == "up" for s in services.values())

    if all_up:
        overall_status = "healthy"
    else:
        overall_status = "unhealthy"

    settings = get_settings()

    response = HealthResponse(
        status=overall_status,
        timestamp=datetime.now(timezone.utc),
        version=settings.app_version,
        services=services if include_details else None,
    )

    # Log the health-check result
    logger.info(
        "health_check_completed",
        overall_status=overall_status,
        services={name: svc.status for name, svc in services.items()},
    )

    # Return 503 for unhealthy so orchestrators can detect failures
    if overall_status == "unhealthy":
        return JSONResponse(
            status_code=503,
            content=response.model_dump(mode="json"),
        )

    return response


# =============================================================================
# GET /health
# =============================================================================


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Public aggregate health check",
    description=(
        "Returns the aggregate gateway health status without per-service "
        "debug details. This endpoint is public for infrastructure probes."
    ),
)
@public
async def health_check(request: Request) -> HealthResponse | JSONResponse:
    """Return public health status without debug details."""
    return await _build_health_response(request, include_details=False)


# =============================================================================
# GET /health/debug
# =============================================================================


@router.get(
    "/health/debug",
    response_model=HealthResponse,
    summary="Authenticated detailed health check",
    description=(
        "Returns the aggregate gateway health status with per-service details. "
        "Requires a valid bearer token."
    ),
    dependencies=[Depends(bearer_scheme)],
)
async def health_check_debug(request: Request) -> HealthResponse | JSONResponse:
    """Return detailed health status for authenticated callers."""
    return await _build_health_response(request, include_details=True)


# =============================================================================
# GET /version
# =============================================================================


def _get_git_commit() -> str | None:
    """
    Attempt to retrieve the short git commit SHA.

    Priority:
    1. ``GIT_COMMIT`` environment variable (set at build time in Docker).
    2. ``git rev-parse --short HEAD`` subprocess call.
    3. ``None`` if neither is available.
    """
    # Check environment variable first (fastest, works in containers)
    env_commit = os.environ.get("GIT_COMMIT")
    if env_commit:
        return env_commit

    # Fall back to subprocess (useful in dev)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # git not installed or timed out — that's fine
        pass

    return None


@router.get(
    "/version",
    response_model=VersionResponse,
    summary="Build & version info",
    description="Returns version metadata for the running gateway instance.",
)
@public
async def get_version() -> VersionResponse:
    """Return version and build metadata."""
    settings = get_settings()

    return VersionResponse(
        version=settings.app_version,
        api_version="v1",
        python_version=platform.python_version(),
        build_date=os.environ.get("BUILD_DATE"),
        git_commit=_get_git_commit(),
    )
