"""Initial schema — Schema-per-Tenant architecture (squashed)

Revision ID: 8517dd8e0f39
Revises:
Create Date: 2026-07-03 00:51:25.611229

Architecture overview
---------------------
This is the SINGLE canonical migration that bootstraps the entire database
for a fresh install.  All subsequent migrations have been squashed into this file.

Schema layout
~~~~~~~~~~~~~
public (shared / platform-level)
    roles           — platform role definitions
    tenants         — tenant registry
    users           — global user identity table (Option 1 — Shared Identity)
                      * uses 'status' column (active/pending_invitation/disabled/etc.)
                        instead of 'is_active' boolean
                      * includes 'full_name' column
    audit_logs      — platform-wide audit trail (streamlined schema)
    tokens          — unified token table for invitations & password resets

SCHEMA_{TENANT_NAME} (one per tenant, created by provision_tenant_schema())
    documents       — document metadata (includes file_size, storage_key, encrypted_file_dek)
    chunks          — document chunks
    conversations   — conversation headers (FK → public.users.user_id)
    messages        — individual chat messages

Key design decisions
~~~~~~~~~~~~~~~~~~~~
* public tables have NO tenant_id in conversations/documents — isolation is
  schema-level, not row-level.
* users lives ONLY in public (Option 1 — Shared Identity). Tenant-scoped
  tables reference public.users via cross-schema FK.
* Tenant schema tables are NOT created here — they are provisioned at runtime
  by ``provision_tenant_schema()`` in schema_repository.py whenever a new
  tenant is created.
* The ``tokens`` table handles both INVITATION and PASSWORD_RESET flows
  via the ``token_type`` column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8517dd8e0f39'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Helper — tenant-schema DDL (documentation + used by provision_tenant_schema)
# ---------------------------------------------------------------------------

def _create_tenant_schema_tables(schema: str) -> None:
    """
    Create all tenant-scoped tables inside ``schema``.

    This function is called by ``provision_tenant_schema()`` at runtime, NOT
    during ``alembic upgrade head``.  It is defined here so the DDL is
    co-located with the public-schema DDL and easy to keep in sync.

    Args:
        schema: Quoted schema name, e.g. ``'"SCHEMA_FPTCORP"'``.
    """
    # documents — no tenant_id; uniqueness scoped to schema
    # Includes: file_size, storage_key, encrypted_file_dek (all squashed in)
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.documents (
            doc_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            doc_name            TEXT NOT NULL,
            doc_type            VARCHAR(255) NOT NULL,
            doc_version         INT4 NOT NULL DEFAULT 1,
            ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            content_hash        VARCHAR(255) NOT NULL,
            is_deleted          BOOLEAN NOT NULL DEFAULT FALSE,
            file_size           BIGINT NOT NULL DEFAULT 0,
            storage_key         VARCHAR(1000),
            encrypted_file_dek  VARCHAR(1000),
            doc_name_lookup_hash VARCHAR(64)
        )
    """)
    op.execute(f"""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_documents_hash_version
            ON {schema}.documents (content_hash, doc_version)
    """)
    op.execute(f"""
        CREATE INDEX IF NOT EXISTS ix_documents_lookup_hash
            ON {schema}.documents (doc_name_lookup_hash)
    """)

    # chunks — lives inside the tenant schema, FK → tenant-local documents
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.chunks (
            chunk_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            doc_id      UUID NOT NULL
                            REFERENCES {schema}.documents (doc_id) ON DELETE CASCADE,
            section     TEXT,
            chunk_index INT4 NOT NULL,
            content     TEXT NOT NULL,
            page_start  INT4,
            page_end    INT4,
            token_count INT4 NOT NULL DEFAULT 0,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            is_deleted  BOOLEAN NOT NULL DEFAULT FALSE,

            CONSTRAINT chk_chunks_page_range
                CHECK (page_start IS NULL OR page_end IS NULL OR page_start <= page_end)
        )
    """)
    op.execute(f"""
        CREATE INDEX IF NOT EXISTS ix_chunks_doc_id
            ON {schema}.chunks (doc_id)
    """)
    op.execute(f"""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_chunks_doc_index
            ON {schema}.chunks (doc_id, chunk_index)
    """)

    # conversations — cross-schema FK → public.users
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.conversations (
            conversation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID NOT NULL
                                REFERENCES public.users (user_id) ON DELETE RESTRICT,
            title           TEXT NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            turn_count      INT4 NOT NULL DEFAULT 0,
            token_total     INT4 NOT NULL DEFAULT 0
        )
    """)
    op.execute(f"""
        CREATE INDEX IF NOT EXISTS ix_conversations_user_id
            ON {schema}.conversations (user_id)
    """)

    # messages — FK → tenant-local conversations
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.messages (
            message_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID NOT NULL
                                REFERENCES {schema}.conversations (conversation_id)
                                ON DELETE CASCADE,
            content         TEXT NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            role_chat       VARCHAR(255) NOT NULL,
            message_index   INT4 NOT NULL,
            message_type    VARCHAR(255) NOT NULL,
            citation_content TEXT,

            CONSTRAINT chk_messages_role_chat
                CHECK (role_chat IN ('user', 'assistant', 'system'))
        )
    """)
    op.execute(f"""
        CREATE INDEX IF NOT EXISTS ix_messages_conversation_id
            ON {schema}.messages (conversation_id)
    """)
    op.execute(f"""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_messages_conversation_index
            ON {schema}.messages (conversation_id, message_index)
    """)


# ---------------------------------------------------------------------------
# Alembic upgrade / downgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    """
    Bootstrap the public schema for a fresh database install.

    This is the squashed canonical migration that includes all changes
    from the original first migration plus all subsequent migrations:
      - file_size, storage_key, encrypted_file_dek on tenant documents
      - users.status (replaces is_active boolean)
      - users.full_name
      - audit_logs: streamlined schema (no action_type, additional_data, source)
      - public.tokens: unified table for INVITATION and PASSWORD_RESET flows
        (replaces the old invitation_tokens table)
    """
    # ── 0. Extensions ────────────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ── 1. public.roles ──────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS public.roles (
            role_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            role_name   VARCHAR(255) NOT NULL,
            is_deleted  BOOLEAN NOT NULL DEFAULT FALSE
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_roles_role_name
            ON public.roles (role_name)
            WHERE is_deleted = FALSE
    """)

    # ── 2. public.tenants ────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS public.tenants (
            tenant_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_name         VARCHAR(255) NOT NULL,
            collection_name     VARCHAR(255) NOT NULL,
            encrypted_dek       BYTEA NOT NULL,
            is_deleted          BOOLEAN NOT NULL DEFAULT FALSE,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_tenants_collection_name
            ON public.tenants (collection_name)
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_tenants_tenant_name
            ON public.tenants (tenant_name)
    """)

    # ── 3. public.users ──────────────────────────────────────────────────────
    # Uses 'status' column (not is_active boolean), includes full_name.
    # email is unique platform-wide; username is unique per-tenant.
    op.execute("""
        CREATE TABLE IF NOT EXISTS public.users (
            user_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_name       VARCHAR(255) NOT NULL,
            password_hash   VARCHAR(255) NOT NULL,
            tenant_id       UUID
                                REFERENCES public.tenants (tenant_id) ON DELETE RESTRICT,
            role_id         UUID NOT NULL
                                REFERENCES public.roles (role_id) ON DELETE RESTRICT,
            status          VARCHAR(50) NOT NULL DEFAULT 'active',
            email           VARCHAR(255),
            full_name       VARCHAR(255),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_users_tenant_username
            ON public.users (tenant_id, user_name)
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email_global
            ON public.users (email)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_users_role_id
            ON public.users (role_id)
    """)

    # ── 4. public.audit_logs ─────────────────────────────────────────────────
    # Streamlined schema: removed action_type, additional_data, source columns.
    op.execute("""
        CREATE TABLE IF NOT EXISTS public.audit_logs (
            id              BIGSERIAL PRIMARY KEY,
            tenant_id       VARCHAR(64) NOT NULL,
            user_id         UUID REFERENCES public.users (user_id) ON DELETE SET NULL,
            request_id      VARCHAR(64),
            ip_address      INET,
            action_time     TIMESTAMPTZ NOT NULL DEFAULT now(),
            endpoint        VARCHAR(255),
            method          VARCHAR(10),
            status_code     INT4,
            latency_ms      INT4
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id
            ON public.audit_logs (user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_action_time
            ON public.audit_logs (action_time)
    """)

    # ── 5. public.tokens ─────────────────────────────────────────────────────
    # Unified table for INVITATION and PASSWORD_RESET flows.
    # Replaces the old invitation_tokens table.
    # token_type: 'INVITATION' | 'PASSWORD_RESET'
    # invited_by: UUID of the user who sent the invite (nullable)
    # tenant_id: nullable (NULL for PASSWORD_RESET tokens, set for INVITATION)
    op.execute("""
        CREATE TABLE IF NOT EXISTS public.tokens (
            token_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID NOT NULL
                            REFERENCES public.users (user_id) ON DELETE CASCADE,
            tenant_id   UUID
                            REFERENCES public.tenants (tenant_id) ON DELETE CASCADE,
            token_type  VARCHAR(50) NOT NULL,
            token_hash  VARCHAR(64) NOT NULL,
            invited_by  UUID
                            REFERENCES public.users (user_id) ON DELETE SET NULL,
            expires_at  TIMESTAMPTZ NOT NULL,
            accepted_at TIMESTAMPTZ,
            is_revoked  BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_tokens_token_hash_type
            ON public.tokens (token_hash, token_type)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tokens_user_id
            ON public.tokens (user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tokens_tenant_id
            ON public.tokens (tenant_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tokens_token_type
            ON public.tokens (token_type)
    """)


def downgrade() -> None:
    """
    Drop all public-schema tables in reverse FK order.

    NOTE: Tenant schemas (SCHEMA_*) must be dropped separately before
    running downgrade, as they contain cross-schema FKs pointing to
    public.users that will prevent DROP TABLE from succeeding.
    Drop them with:
        DROP SCHEMA "SCHEMA_<name>" CASCADE;
    for each tenant before running: alembic downgrade base
    """
    op.execute("DROP TABLE IF EXISTS public.tokens CASCADE")
    op.execute("DROP TABLE IF EXISTS public.audit_logs CASCADE")
    op.execute("DROP TABLE IF EXISTS public.users CASCADE")
    op.execute("DROP TABLE IF EXISTS public.tenants CASCADE")
    op.execute("DROP TABLE IF EXISTS public.roles CASCADE")
