"""
Pydantic v2 common/shared schemas.

These models define the shared error envelope used by every JSON error
response returned by the gateway.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# =============================================================================
# Standard Error Response
# =============================================================================


class ErrorResponse(BaseModel):
    """
    Uniform error envelope returned for all non-2xx responses.

    Every error carries a machine-readable ``error_code`` for programmatic
    handling and a human-readable ``message`` for debugging.
    """

    error_code: str = Field(
        ...,
        description="Machine-readable error code, e.g. 'TENANT_NOT_FOUND'.",
    )
    message: str = Field(
        ...,
        description="Human-readable explanation of the error.",
    )
    request_id: str = Field(
        ...,
        description="Correlation ID for tracing this request across services.",
    )
    timestamp: datetime = Field(
        ...,
        description="UTC timestamp when the error was generated.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "error_code": "TENANT_NOT_FOUND",
                    "message": "No tenant exists with the given ID.",
                    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "timestamp": "2026-06-19T09:00:00Z",
                }
            ]
        }
    }
