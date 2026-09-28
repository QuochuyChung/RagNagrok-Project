"""
Health check and version Pydantic schemas.

Moved from models/schemas.py. Used by app/api/routes/health.py.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# =============================================================================
# Health Check Schemas
# =============================================================================


class ServiceHealth(BaseModel):
    """Health status of an individual backing service."""

    status: str = Field(
        ...,
        description="Service availability: 'up', 'down', or 'unknown'.",
    )
    latency_ms: float | None = Field(
        default=None,
        description="Round-trip latency in milliseconds (only in debug mode).",
    )
    error: str | None = Field(
        default=None,
        description="Error message when service is 'down'.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "up",
                    "latency_ms": 2.3,
                    "error": None,
                }
            ]
        }
    }


class HealthResponse(BaseModel):
    """
    Aggregate health of the gateway and its backing services.

    In normal mode only ``status``, ``timestamp``, and ``version`` are
    returned.  When debug mode is active the ``services`` dict provides
    per-service breakdowns.
    """

    status: str = Field(
        ...,
        description="Overall status: 'healthy', 'degraded', or 'unhealthy'.",
    )
    timestamp: datetime = Field(
        ...,
        description="UTC timestamp of the health check.",
    )
    version: str = Field(
        ...,
        description="Application version string.",
    )
    services: dict[str, ServiceHealth] | None = Field(
        default=None,
        description=(
            "Per-service health breakdown (only included in debug mode)."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "healthy",
                    "timestamp": "2026-06-19T09:00:00Z",
                    "version": "0.2.0",
                    "services": {
                        "postgres": {
                            "status": "up",
                            "latency_ms": 1.1,
                            "error": None,
                        },
                        "qdrant": {
                            "status": "up",
                            "latency_ms": 1.5,
                            "error": None,
                        },
                        "ollama": {
                            "status": "up",
                            "latency_ms": 5.2,
                            "error": None,
                        },
                        "open_webui": {
                            "status": "up",
                            "latency_ms": 3.1,
                            "error": None,
                        },
                    },
                }
            ]
        }
    }


# =============================================================================
# Version Response
# =============================================================================


class VersionResponse(BaseModel):
    """Build / version metadata for the running gateway instance."""

    version: str = Field(
        ...,
        description="Application semantic version.",
    )
    api_version: str = Field(
        default="v1",
        description="Current REST API version prefix.",
    )
    python_version: str = Field(
        ...,
        description="Python interpreter version.",
    )
    build_date: str | None = Field(
        default=None,
        description="ISO-8601 build date (if set at build time).",
    )
    git_commit: str | None = Field(
        default=None,
        description="Short SHA of the git commit this build was made from.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "version": "0.2.0",
                    "api_version": "v1",
                    "python_version": "3.12.4",
                    "build_date": "2026-07-01",
                    "git_commit": "abc1234",
                }
            ]
        }
    }
