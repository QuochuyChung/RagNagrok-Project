"""
Combined Reset and Seed Script for Ragnarok Multi-Tenant RAG API Gateway.

Deletes all existing DB data & Qdrant collections, then seeds initial roles,
platform admin, tenant, tenant admin, standard user, and tenant Qdrant collection.

Run inside gateway container:
    docker compose exec gateway python scripts/reset_and_seed_db.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from qdrant_client import AsyncQdrantClient, QdrantClient

from app.core.config import get_settings
from app.core.encryption import generate_tenant_dek
from app.repositories.qdrant_repository import QdrantRepository
from app.repositories.schema_repository import provision_tenant_schema
from app.utils.hashing import hash_password

ROLE_NAMES = ("USER", "TENANT_ADMIN", "PLATFORM_ADMIN")

PLATFORM_ADMIN_USER = {
    "user_name": "platform0",
    "email": "thien.duong@platform.local",
    "password": "123456",
    "full_name": "Thiện Dương",
}

TENANT_NAME = "dev_team"
COLLECTION_NAME = f"COL_{TENANT_NAME.upper()}"

USERS_TO_CREATE = [
    {
        "user_name": "tenant0",
        "email": "admin@devteam.local",
        "password": "12345678",
        "role_name": "TENANT_ADMIN",
        "full_name": "Nguyễn Văn Admin",
    },
    {
        "user_name": "user0",
        "email": "user0@devteam.local",
        "password": "123456",
        "role_name": "USER",
        "full_name": "Trần Văn User",
    },
]


async def reset() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)

    tables = [
        "audit_logs",
        "tokens",
        "users",
        "tenants",
        "roles",
    ]

    try:
        async with engine.begin() as conn:
            print("Resetting database...")

            # 1. Drop all tenant schemas
            print("Fetching tenant schemas...")
            result = await conn.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name LIKE 'SCHEMA_%' OR schema_name LIKE 'schema_%'"
                )
            )
            schemas = result.fetchall()
            for row in schemas:
                schema_name = row[0]
                print(f"Dropping schema {schema_name}...")
                await conn.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))

            # 2. Truncate public tables, restart identity sequences, and cascade
            tables_str = ", ".join(tables)
            await conn.execute(text(f"TRUNCATE TABLE {tables_str} RESTART IDENTITY CASCADE;"))
            print("Database tables truncated successfully.")

            # 3. Delete all Qdrant collections
            print("Deleting Qdrant collections...")
            try:
                qdrant_url = os.getenv("QDRANT_URL") or settings.qdrant_url
                qdrant = QdrantClient(url=qdrant_url, api_key=settings.qdrant_api_key)
                collections_response = qdrant.get_collections()
                for collection in collections_response.collections:
                    print(f"Deleting Qdrant collection: {collection.name}...")
                    qdrant.delete_collection(collection_name=collection.name)
                print("All Qdrant collections deleted successfully.")
            except Exception as e:
                print(f"Qdrant reset error (skipped): {e}")
    except Exception as e:
        print(f"Error resetting database: {e}")
    finally:
        await engine.dispose()


async def seed() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)

    try:
        # 1. Seed Roles, Platform Admin, and Tenant
        async with engine.begin() as conn:
            print("1. Seeding basic roles...")
            role_ids = {}
            for role_name in ROLE_NAMES:
                result = await conn.execute(
                    text(
                        """
                        INSERT INTO roles (role_name, is_deleted)
                        VALUES (:role_name, false)
                        ON CONFLICT (role_name) WHERE is_deleted = false
                        DO UPDATE SET role_name = EXCLUDED.role_name
                        RETURNING role_id
                        """
                    ),
                    {"role_name": role_name},
                )
                role_ids[role_name] = result.scalar_one()

            print("2. Seeding platform admin user...")
            pwd_hash = hash_password(PLATFORM_ADMIN_USER["password"])
            platform_result = await conn.execute(
                text(
                    """
                    INSERT INTO users (
                        user_name,
                        email,
                        password_hash,
                        tenant_id,
                        role_id,
                        status,
                        full_name
                    )
                    VALUES (
                        :user_name,
                        :email,
                        :password_hash,
                        NULL,
                        :role_id,
                        'active',
                        :full_name
                    )
                    ON CONFLICT (email)
                    DO UPDATE SET
                        user_name = EXCLUDED.user_name,
                        password_hash = EXCLUDED.password_hash,
                        role_id = EXCLUDED.role_id,
                        tenant_id = NULL,
                        status = 'active',
                        full_name = EXCLUDED.full_name
                    RETURNING user_id
                    """
                ),
                {
                    "user_name": PLATFORM_ADMIN_USER["user_name"],
                    "email": PLATFORM_ADMIN_USER["email"],
                    "password_hash": pwd_hash,
                    "role_id": role_ids["PLATFORM_ADMIN"],
                    "full_name": PLATFORM_ADMIN_USER["full_name"],
                },
            )
            platform_id = platform_result.scalar_one()
            print(f"Platform admin created (ID={platform_id}).")

            print(f"3. Seeding tenant '{TENANT_NAME}'...")
            # Generate DEK via AWS KMS (or local KEK fallback if KMS unavailable)
            _plaintext_dek, wrapped_dek = await generate_tenant_dek(TENANT_NAME)
            _plaintext_dek = None  # zero out plaintext immediately
            tenant_result = await conn.execute(
                text(
                    """
                    INSERT INTO tenants (tenant_name, collection_name, encrypted_dek, is_deleted)
                    VALUES (:tenant_name, :collection_name, :encrypted_dek, false)
                    ON CONFLICT (tenant_name)
                    DO UPDATE SET collection_name = EXCLUDED.collection_name, encrypted_dek = EXCLUDED.encrypted_dek
                    RETURNING tenant_id
                    """
                ),
                {
                    "tenant_name": TENANT_NAME,
                    "collection_name": COLLECTION_NAME,
                    "encrypted_dek": wrapped_dek,
                },
            )
            tenant_id = tenant_result.scalar_one()
            print(f"Tenant '{TENANT_NAME}' inserted (ID={tenant_id}, collection={COLLECTION_NAME}).")

        # 4. Provision Tenant Postgres Schema (SCHEMA_DEV_TEAM)
        print(f"4. Provisioning schema for '{TENANT_NAME}'...")
        async with engine.begin() as conn:
            schema_name = await provision_tenant_schema(conn, TENANT_NAME)
        print(f"Postgres schema '{schema_name}' provisioned successfully.")

        # 5. Seed Users for Tenant
        print("5. Seeding tenant users...")
        async with engine.begin() as conn:
            for u in USERS_TO_CREATE:
                u_pwd_hash = hash_password(u["password"])
                u_result = await conn.execute(
                    text(
                        """
                        INSERT INTO users (
                            user_name,
                            email,
                            password_hash,
                            tenant_id,
                            role_id,
                            status,
                            full_name
                        )
                        VALUES (
                            :user_name,
                            :email,
                            :password_hash,
                            :tenant_id,
                            :role_id,
                            'active',
                            :full_name
                        )
                        ON CONFLICT (email)
                        DO UPDATE SET
                            user_name = EXCLUDED.user_name,
                            password_hash = EXCLUDED.password_hash,
                            role_id = EXCLUDED.role_id,
                            tenant_id = EXCLUDED.tenant_id,
                            status = 'active',
                            full_name = EXCLUDED.full_name
                        RETURNING user_id
                        """
                    ),
                    {
                        "user_name": u["user_name"],
                        "email": u["email"],
                        "password_hash": u_pwd_hash,
                        "tenant_id": tenant_id,
                        "role_id": role_ids[u["role_name"]],
                        "full_name": u["full_name"],
                    },
                )
                uid = u_result.scalar_one()
                print(f"Created user '{u['user_name']}' ({u['role_name']}) (ID={uid}).")

        # 6. Create Qdrant Collection directly
        print(f"6. Creating Qdrant collection '{COLLECTION_NAME}'...")
        qdrant_url = os.getenv("QDRANT_URL") or settings.qdrant_url
        qdrant_client = AsyncQdrantClient(
            url=qdrant_url,
            api_key=settings.qdrant_api_key,
        )
        try:
            qdrant_repo = QdrantRepository(client=qdrant_client, vector_size=settings.rag_vector_size)
            await qdrant_repo.create_collection(COLLECTION_NAME)
            print(f"Qdrant collection '{COLLECTION_NAME}' ready.")
        finally:
            await qdrant_client.close()

        print("Seed data completed successfully via direct database & Qdrant inserts.")

    finally:
        await engine.dispose()


async def main() -> None:
    print("==================================================")
    print(" 1. Resetting Database & Clearing Qdrant Collections")
    print("==================================================")
    await reset()

    print("\n==================================================")
    print(" 2. Seeding Initial Roles, Tenants & Users")
    print("==================================================")
    await seed()

    print("\n==================================================")
    print(" RESET & INITIALIZATION COMPLETED SUCCESSFULLY!")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(main())
