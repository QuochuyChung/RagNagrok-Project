"""
Schema Repository — Feature 2: One Schema per Tenant (PostgreSQL)

Handles the provisioning and dropping of isolated PostgreSQL schemas for
tenants using a name-based convention: ``SCHEMA_{TENANT_NAME.upper()}``.

Naming rule:
    tenant_name = "fptcorp"  →  schema = "SCHEMA_FPTCORP"
    tenant_name = "ACME"     →  schema = "SCHEMA_ACME"

Constraints enforced upstream (at the API validation layer):
    - tenant_name must match ``^[A-Za-z0-9_]+$`` (no spaces, no hyphens).
    - tenant_name is immutable after creation (no rename allowed).

These two constraints make the name safe to use directly as a PostgreSQL
identifier without any replace() transforms and guarantee that the schema
name never needs to change after it is created.

Tables created inside each tenant schema:
    documents, chunks, conversations, messages

The ``conversations`` table uses a cross-schema FK that references
``public.users(user_id)`` because Users live only in the shared public
schema (Option 1 — Shared Identity).

Usage:
    from app.repositories.schema_repository import (
        get_schema_name,
        provision_tenant_schema,
        drop_tenant_schema,
        apply_to_all_tenant_schemas,
    )
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.logging import get_logger
from app.models.base import Base
from app.models.document import Documents
from app.models.chunk import Chunks
from app.models.coversation import Conversations
from app.models.message import Messages

logger = get_logger(__name__)

# ── Tenant-scoped tables ──────────────────────────────────────────────────────
# These tables are created inside every tenant schema.
# Users / Roles / Tenants / AuditLogs remain in the public schema and are
# NOT included here.
_TENANT_TABLES = [
    Documents.__table__,
    Chunks.__table__,
    Conversations.__table__,
    Messages.__table__,
]


# ── Naming helper ─────────────────────────────────────────────────────────────

def get_schema_name(tenant_name: str) -> str:
    """
    Convert a tenant name into the PostgreSQL schema identifier.

    Convention: ``SCHEMA_{TENANT_NAME.upper()}``

    Examples:
        >>> get_schema_name("fptcorp")
        'SCHEMA_FPTCORP'
        >>> get_schema_name("ACME")
        'SCHEMA_ACME'

    Note: No character replacement is performed here because tenant names
    are validated upstream to only contain ``[A-Za-z0-9_]``.  If a name
    with special characters is passed, PostgreSQL will raise an error at
    the DDL level, which is the correct behaviour.
    """
    return f"SCHEMA_{tenant_name.upper()}"


# ── Provisioning ──────────────────────────────────────────────────────────────

async def provision_tenant_schema(
    conn: AsyncConnection,
    tenant_name: str,
) -> str:
    """
    Create a new PostgreSQL schema for the tenant and populate it with all
    tenant-scoped tables using SQLAlchemy metadata (no hardcoded DDL).

    The function is idempotent: ``CREATE SCHEMA IF NOT EXISTS`` and
    ``create_all(checkfirst=True)`` ensure it is safe to call multiple times.

    Args:
        conn:        A raw ``AsyncConnection`` obtained from the engine
                     (NOT an ORM session) so DDL auto-commits correctly.
        tenant_name: The immutable tenant name (e.g. ``"FPTCORP"``).

    Returns:
        The schema name that was created (e.g. ``"SCHEMA_FPTCORP"``).
    """
    schema = get_schema_name(tenant_name)

    logger.info("provisioning_tenant_schema", tenant_name=tenant_name, schema=schema)

    # 1. Create the schema namespace (idempotent)
    await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    # 2. Apply schema_translate_map so that SQLAlchemy generates DDL targeting
    #    the new schema instead of the default (public) schema.
    conn_with_schema = await conn.execution_options(
        schema_translate_map={None: schema}
    )

    # 3. Generate and execute CREATE TABLE … for every tenant-scoped model.
    #    SQLAlchemy reads the ORM model definitions and emits correct DDL —
    #    no hardcoded column lists needed here.
    await conn_with_schema.run_sync(
        Base.metadata.create_all,
        tables=_TENANT_TABLES,
        checkfirst=True,
    )

    logger.info(
        "tenant_schema_provisioned",
        tenant_name=tenant_name,
        schema=schema,
    )
    return schema


# ── Teardown ──────────────────────────────────────────────────────────────────

async def drop_tenant_schema(conn: AsyncConnection, tenant_name: str) -> None:
    """
    Permanently drop a tenant's schema and ALL its data (CASCADE).

    This is an irreversible, destructive operation.  Call only when the
    tenant record is being hard-deleted (not soft-deleted).

    Args:
        conn:        Raw ``AsyncConnection`` from the engine.
        tenant_name: The tenant name whose schema will be dropped.
    """
    schema = get_schema_name(tenant_name)
    logger.warning("dropping_tenant_schema", tenant_name=tenant_name, schema=schema)
    await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    await conn.commit()


# ── Alembic / migration helper ────────────────────────────────────────────────

async def apply_to_all_tenant_schemas(
    conn: AsyncConnection,
    ddl_template: str,
) -> list[str]:
    """
    Execute a DDL statement against every existing tenant schema.

    Use this helper inside Alembic migration files when a structural change
    (e.g. adding a column) must be applied to all tenant schemas at once.

    The ``ddl_template`` string must contain a ``{schema}`` placeholder that
    will be substituted with the quoted schema name for each tenant.

    Example:
        ddl_template = 'ALTER TABLE {schema}.documents ADD COLUMN summary TEXT'
        await apply_to_all_tenant_schemas(conn, ddl_template)

    Args:
        conn:         Raw ``AsyncConnection`` from the engine.
        ddl_template: SQL template string with a ``{schema}`` placeholder.

    Returns:
        List of schema names that were updated.
    """
    result = await conn.execute(
        text(
            "SELECT tenant_name FROM public.tenants WHERE is_deleted = false"
        )
    )
    rows = result.fetchall()

    updated: list[str] = []
    for row in rows:
        schema = get_schema_name(str(row[0]))
        sql = ddl_template.format(schema=f'"{schema}"')
        await conn.execute(text(sql))
        updated.append(schema)
        logger.info("migration_applied_to_schema", schema=schema)

    await conn.commit()
    return updated
