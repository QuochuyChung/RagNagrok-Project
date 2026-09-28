"""
Seed script — populates the database with initial data for local development.

Creates:
  - 3 roles   : PLATFORM_ADMIN, TENANT_ADMIN, USER
  - 5 tenants : Team Alpha → Team Epsilon (mỗi tenant 1 Qdrant collection)
  - 250 users : Mỗi tenant có đúng 50 users, phân bổ role như sau:
      • 1 PLATFORM_ADMIN (chỉ có ở tenant đầu tiên, quản trị toàn hệ thống)
      • 1 TENANT_ADMIN   (mỗi tenant có 1 admin riêng)
      • 48 USER          (user thường của tenant đó)

Usage:
    # Chạy từ thư mục gốc của dự án
    python scripts/seed_UserTenant.py

    # Hoặc truyền DATABASE_URL tùy chỉnh
    DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db python scripts/seed_UserTenant.py
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys

# Ensure the app module can be found regardless of where the script is run from
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.repositories.schema_repository import provision_tenant_schema

# ── Config (có thể override bằng biến môi trường) ───────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://ragnarok:ragnarok_secret@localhost:5432/rag_db",
)
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
VECTOR_SIZE = int(os.getenv("RAG_VECTOR_SIZE", "768"))
DEFAULT_PASSWORD = "123456"

# ── Định nghĩa Tenants (UUID cố định để seed lại vẫn idempotent) ────────────
TENANT_DEFS = [
    {"tenant_id": uuid.UUID("11111111-1111-1111-1111-000000000001"), "tenant_name": "Team Alpha"},
    {"tenant_id": uuid.UUID("22222222-2222-2222-2222-000000000002"), "tenant_name": "Team Beta"},
    {"tenant_id": uuid.UUID("33333333-3333-3333-3333-000000000003"), "tenant_name": "Team Gamma"},
    {"tenant_id": uuid.UUID("44444444-4444-4444-4444-000000000004"), "tenant_name": "Team Delta"},
    {"tenant_id": uuid.UUID("55555555-5555-5555-5555-000000000005"), "tenant_name": "Team Epsilon"},
]

from app.utils.hashing import hash_password

# ── Helpers ──────────────────────────────────────────────────────────────────

def collection_name(tenant_id: uuid.UUID) -> str:
    return f"COLLECTION_{str(tenant_id).replace('-', '_')}"

def tenant_slug(tenant_name: str) -> str:
    """Team Alpha → team_alpha"""
    return tenant_name.lower().replace(" ", "_")


# ── Main Seed ────────────────────────────────────────────────────────────────
async def seed() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    hashed_pw = hash_password(DEFAULT_PASSWORD)

    async with session_maker() as session:

        # ── Bước 1: Seed Roles ───────────────────────────────────────────────
        print("\n[1/4] Seeding roles...")
        role_defs = [
            {"role_id": uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001"), "role_name": "PLATFORM_ADMIN"},
            {"role_id": uuid.UUID("aaaaaaaa-0000-0000-0000-000000000002"), "role_name": "TENANT_ADMIN"},
            {"role_id": uuid.UUID("aaaaaaaa-0000-0000-0000-000000000003"), "role_name": "USER"},
        ]
        for r in role_defs:
            exists = (await session.execute(text("SELECT 1 FROM roles WHERE role_name = :role_name"), {"role_name": r["role_name"]})).scalar()
            if not exists:
                await session.execute(text("""
                    INSERT INTO roles (role_id, role_name, is_deleted)
                    VALUES (:role_id, :role_name, false)
                    ON CONFLICT (role_id) DO NOTHING
                """), r)

        # Lấy role_id từ DB (đảm bảo dùng đúng ID dù đã tồn tại)
        rows = (await session.execute(
            text("SELECT role_id, role_name FROM roles WHERE is_deleted = false")
        )).fetchall()
        role_ids: dict[str, uuid.UUID] = {row.role_name: row.role_id for row in rows}
        print(f"  [+] Roles: {list(role_ids.keys())}")

        # ── Bước 2: Seed Tenants ─────────────────────────────────────────────
        print("\n[2/4] Seeding tenants (5)...")
        for t in TENANT_DEFS:
            col = collection_name(t["tenant_id"])
            exists = (await session.execute(text("SELECT 1 FROM tenants WHERE tenant_name = :tenant_name"), {"tenant_name": t["tenant_name"]})).scalar()
            if not exists:
                await session.execute(text("""
                    INSERT INTO tenants (tenant_id, tenant_name, collection_name, is_deleted, created_at)
                    VALUES (:tenant_id, :tenant_name, :collection_name, false, :created_at)
                    ON CONFLICT (tenant_id) DO NOTHING
                """), {
                    "tenant_id": t["tenant_id"],
                    "tenant_name": t["tenant_name"],
                    "collection_name": col,
                    "created_at": now,
                })
                # Provision the PostgreSQL schema for the tenant outside the transaction
                async with engine.begin() as raw_conn:
                    schema_name = await provision_tenant_schema(raw_conn, t["tenant_name"])
                    print(f"  [+] Provisioned schema: {schema_name}")
            print(f"  [+] {t['tenant_name']} -> collection: {col}")

        # ── Bước 3: Seed Users (50 per tenant = 250 total) ───────────────────
        print("\n[3/4] Seeding users (5 tenants x 50 users = 250)...")

        for tenant_idx, t in enumerate(TENANT_DEFS):
            t_id = t["tenant_id"]
            slug = tenant_slug(t["tenant_name"])
            is_first_tenant = (tenant_idx == 0)

            # Phân bổ 50 users cho mỗi tenant:
            #   - 1 PLATFORM_ADMIN (chỉ ở tenant đầu tiên)  →  user_index=0
            #   - 1 TENANT_ADMIN                             →  user_index=1 (hoặc 0 với các tenant còn lại)
            #   - Còn lại là USER
            users_for_tenant = []

            if is_first_tenant:
                # Platform Admin (1 người) — user đầu tiên của tenant đầu
                users_for_tenant.append({
                    "user_id": uuid.uuid4(),
                    "user_name": "platform_admin",
                    "email": "platform.admin@ragnarok.local",
                    "password_hash": hashed_pw,
                    "tenant_id": t_id,
                    "role_id": role_ids["PLATFORM_ADMIN"],
                    "status": "active",
                    "full_name": "Platform Admin",
                    "created_at": now,
                })
                # Tenant Admin (1 người)
                users_for_tenant.append({
                    "user_id": uuid.uuid4(),
                    "user_name": f"admin_{slug}",
                    "email": f"admin@{slug}.ragnarok.local",
                    "password_hash": hashed_pw,
                    "tenant_id": t_id,
                    "role_id": role_ids["TENANT_ADMIN"],
                    "status": "active",
                    "full_name": f"Admin {t['tenant_name']}",
                    "created_at": now,
                })
                # 48 Users thường
                for i in range(1, 49):
                    users_for_tenant.append({
                        "user_id": uuid.uuid4(),
                        "user_name": f"user_{slug}_{i:03d}",
                        "email": f"user{i:03d}@{slug}.ragnarok.local",
                        "password_hash": hashed_pw,
                        "tenant_id": t_id,
                        "role_id": role_ids["USER"],
                        "status": "active",
                        "full_name": f"User {i:03d} {t['tenant_name']}",
                        "created_at": now,
                    })
            else:
                # Các tenants còn lại: 1 TENANT_ADMIN + 49 USER = 50
                users_for_tenant.append({
                    "user_id": uuid.uuid4(),
                    "user_name": f"admin_{slug}",
                    "email": f"admin@{slug}.ragnarok.local",
                    "password_hash": hashed_pw,
                    "tenant_id": t_id,
                    "role_id": role_ids["TENANT_ADMIN"],
                    "status": "active",
                    "full_name": f"Admin {t['tenant_name']}",
                    "created_at": now,
                })
                for i in range(1, 50):
                    users_for_tenant.append({
                        "user_id": uuid.uuid4(),
                        "user_name": f"user_{slug}_{i:03d}",
                        "email": f"user{i:03d}@{slug}.ragnarok.local",
                        "password_hash": hashed_pw,
                        "tenant_id": t_id,
                        "role_id": role_ids["USER"],
                        "status": "active",
                        "full_name": f"User {i:03d} {t['tenant_name']}",
                        "created_at": now,
                    })

            # Bulk insert cho tenant này
            for u in users_for_tenant:
                exists = (await session.execute(text("SELECT 1 FROM users WHERE email = :email"), {"email": u["email"]})).scalar()
                if not exists:
                    await session.execute(text("""
                        INSERT INTO users
                            (user_id, user_name, email, password_hash, tenant_id, role_id, status, full_name, created_at)
                        VALUES
                            (:user_id, :user_name, :email, :password_hash, :tenant_id, :role_id, :status, :full_name, :created_at)
                        ON CONFLICT DO NOTHING
                    """), u)

            print(f"  [+] {t['tenant_name']}: {len(users_for_tenant)} users")

        await session.commit()

        # ── Bước 4: Tạo Qdrant Collections ─────────────────────────────────
        print("\n[4/4] Creating Qdrant collections...")
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            qdrant = QdrantClient(url=QDRANT_URL)
            for t in TENANT_DEFS:
                col = collection_name(t["tenant_id"])
                if not qdrant.collection_exists(col):
                    qdrant.create_collection(
                        collection_name=col,
                        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
                    )
                    print(f"  [+] Created: {col}")
                else:
                    print(f"  [!] Already exists: {col} (skipped)")
        except Exception as e:
            print(f"  [-] Qdrant error (skipped): {e}")

    await engine.dispose()

    print("\n" + "=" * 52)
    print("  [OK] Seed complete!")
    print("=" * 52)
    print(f"  Tenants : 5")
    print(f"  Users   : 250  (50 per tenant)")
    print(f"  +- PLATFORM_ADMIN :   1  (platform_admin)")
    print(f"  +- TENANT_ADMIN   :   5  (1 per tenant)")
    print(f"  +- USER           : 244  (remaining)")
    print(f"  Default password  : {DEFAULT_PASSWORD}")
    print("=" * 52)


if __name__ == "__main__":
    asyncio.run(seed())