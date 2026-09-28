-- ============================================================================
-- sglf-ai — PostgreSQL Schema
-- Sinh ra từ ERD: Roles, Users, Tenants, Conversations, Messages,
-- Documents, Chunks, AuditLogs
-- ============================================================================
-- Thứ tự tạo bảng phải theo đúng thứ tự phụ thuộc FK:
--   1. Roles, Tenants        (không phụ thuộc bảng nào)
--   2. Users                 (phụ thuộc Roles, Tenants)
--   3. Conversations, Documents (phụ thuộc Users/Tenants)
--   4. Messages, Chunks      (phụ thuộc Conversations/Documents)
--   5. AuditLogs             (phụ thuộc Users)
-- ============================================================================

-- Bật extension sinh UUID (pgcrypto cho gen_random_uuid(), có sẵn từ PG13+)
CREATE EXTENSION IF NOT EXISTS pgcrypto;


BEGIN;

-- ============================================================================
-- 1. ROLES
-- ============================================================================
CREATE TABLE IF NOT EXISTS roles (
    role_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_name   VARCHAR(255) NOT NULL,
    is_deleted  BOOLEAN NOT NULL DEFAULT FALSE
);

-- role_name nên là unique để tránh trùng role (vd 2 role cùng tên "Admin")
CREATE UNIQUE INDEX IF NOT EXISTS ux_roles_role_name ON roles (role_name) WHERE is_deleted = FALSE;

-- ============================================================================
-- 2. TENANTS
-- ============================================================================
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_name     VARCHAR(255) NOT NULL,
    collection_name VARCHAR(255) NOT NULL,   -- tên Qdrant collection tương ứng: COLLECTION_{TENANT_NAME_UPPER}
    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE
);

-- collection_name phải unique tuyệt đối (map 1-1 với Qdrant collection, không được trùng dù đã xoá)
CREATE UNIQUE INDEX IF NOT EXISTS ux_tenants_collection_name ON tenants (collection_name);
-- tenant_name phải unique trong toàn hệ thống
CREATE UNIQUE INDEX IF NOT EXISTS ux_tenants_tenant_name ON tenants (tenant_name);

-- ============================================================================
-- 3. USERS
-- ============================================================================
CREATE TABLE IF NOT EXISTS users (
    user_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_name       VARCHAR(255) NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    tenant_id       UUID NOT NULL REFERENCES tenants (tenant_id) ON DELETE RESTRICT,
    role_id         UUID NOT NULL REFERENCES roles (role_id) ON DELETE RESTRICT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

-- user_name unique trong phạm vi 1 tenant (2 tenant khác nhau được phép trùng username)
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_tenant_username ON users (tenant_id, user_name);
CREATE INDEX IF NOT EXISTS ix_users_role_id ON users (role_id);

-- ============================================================================
-- 4. CONVERSATIONS
-- ============================================================================
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants (tenant_id) ON DELETE RESTRICT,
    user_id         UUID NOT NULL REFERENCES users (user_id) ON DELETE RESTRICT,
    title           VARCHAR(255) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    turn_count      INT4 NOT NULL DEFAULT 0,
    token_total     INT4 NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_conversations_tenant_id ON conversations (tenant_id);
CREATE INDEX IF NOT EXISTS ix_conversations_user_id ON conversations (user_id);

-- ============================================================================
-- 5. DOCUMENTS
-- ============================================================================
CREATE TABLE IF NOT EXISTS documents (
    doc_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_name        VARCHAR(255) NOT NULL,
    doc_type        VARCHAR(255) NOT NULL,
    doc_version     INT4 NOT NULL DEFAULT 1,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    tenant_id       UUID NOT NULL REFERENCES tenants (tenant_id) ON DELETE RESTRICT,
    content_hash    VARCHAR(255) NOT NULL,   -- dùng để phát hiện file trùng nội dung (dedupe khi ingest)
    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS ix_documents_tenant_id ON documents (tenant_id);
-- Tránh ingest trùng file (cùng tenant, cùng hash, cùng version) nhiều lần
CREATE UNIQUE INDEX IF NOT EXISTS ux_documents_tenant_hash_version
    ON documents (tenant_id, content_hash, doc_version);

-- ============================================================================
-- 6. MESSAGES
-- ============================================================================
CREATE TABLE IF NOT EXISTS messages (
    message_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations (conversation_id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    role_chat       VARCHAR(255) NOT NULL,   -- 'user' | 'assistant' | 'system'
    message_index   INT4 NOT NULL,           -- thứ tự message trong conversation
    message_type    VARCHAR(255) NOT NULL,   -- 'text' | 'citation' | ...
    citation_content VARCHAR(255),

    CONSTRAINT chk_messages_role_chat
        CHECK (role_chat IN ('user', 'assistant', 'system'))
);

CREATE INDEX IF NOT EXISTS ix_messages_conversation_id ON messages (conversation_id);
-- message_index phải unique trong 1 conversation để đảm bảo đúng thứ tự hội thoại
CREATE UNIQUE INDEX IF NOT EXISTS ux_messages_conversation_index
    ON messages (conversation_id, message_index);

-- ============================================================================
-- 7. CHUNKS
-- ============================================================================
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id          UUID NOT NULL REFERENCES documents (doc_id) ON DELETE CASCADE,
    section         VARCHAR(255),
    chunk_index     INT4 NOT NULL,
    content         TEXT NOT NULL,
    page_start      INT4,
    page_end        INT4,
    token_count     INT4 NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT chk_chunks_page_range
        CHECK (page_start IS NULL OR page_end IS NULL OR page_start <= page_end)
);

CREATE INDEX IF NOT EXISTS ix_chunks_doc_id ON chunks (doc_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_chunks_doc_index ON chunks (doc_id, chunk_index);

-- ============================================================================
-- 8. AUDIT LOGS
-- ============================================================================
-- Lưu ý: ERD gốc để tất cả cột dạng int4 (kể cả user_id, ip_address, action_time...)
-- Đã điều chỉnh theo kiểu dữ liệu hợp lý hơn:
--   user_id        int4 -> uuid (FK về users)
--   ip_address     int4 -> inet (kiểu chuẩn Postgres cho IPv4/IPv6)
--   action_time    int4 -> timestamptz
--   action_type    int4 -> varchar(255)
--   additional_data int4 -> jsonb (payload tự do, ví dụ before/after state)
--   source         int4 -> varchar(255)
CREATE TABLE IF NOT EXISTS audit_logs (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID REFERENCES users (user_id) ON DELETE SET NULL,
    ip_address      INET,
    action_time     TIMESTAMPTZ NOT NULL DEFAULT now(),
    action_type     VARCHAR(255),
    additional_data JSONB,
    source          VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs (user_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_action_time ON audit_logs (action_time);

COMMIT;