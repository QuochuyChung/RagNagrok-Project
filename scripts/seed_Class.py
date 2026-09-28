"""
Seed script — populates database and Qdrant directly with hardcoded data
from the class group list (no HTTP API requests required).

Usage:
    python scripts/seed_Class.py
"""

from __future__ import annotations

import asyncio
import os
import re
import unicodedata
import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from qdrant_client import AsyncQdrantClient

import sys
from pathlib import Path

# Ensure project root is in sys.path when script is executed directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings
from app.utils.hashing import hash_password
from app.repositories.schema_repository import provision_tenant_schema
from app.repositories.qdrant_repository import QdrantRepository


def remove_vietnamese_accents(text_str: str) -> str:
    text_str = text_str.replace('đ', 'd').replace('Đ', 'D')
    nfkd_form = unicodedata.normalize('NFKD', text_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


GROUPS_DATA = [
  {
    "group_name": "Hello World",
    "users": [
      {"display_name": "Nguyễn Việt Minh Phú", "student_id": "1391", "role": "TENANT_ADMIN"},
      {"display_name": "Hoàng Ngô Thiên Phúc", "student_id": "1056", "role": "USER"},
      {"display_name": "Thi Minh Thức", "student_id": "1172", "role": "USER"},
      {"display_name": "Thân Trọng Minh Văn", "student_id": "1121", "role": "USER"},
      {"display_name": "Nguyễn Tấn Phát", "student_id": "1103", "role": "USER"},
      {"display_name": "Nguyễn Hữu Cầu", "student_id": "537", "role": "USER"},
      {"display_name": "Vũ Đức Thắng", "student_id": "1248", "role": "USER"}
    ]
  },
  {
    "group_name": "Hội bàn tròn",
    "users": [
      {"display_name": "Đặng Quốc Thái", "student_id": "1186", "role": "TENANT_ADMIN"},
      {"display_name": "Nguyễn Nhân Thành Châu", "student_id": "516", "role": "USER"},
      {"display_name": "Phạm Trương Anh Huy", "student_id": "1240", "role": "USER"},
      {"display_name": "Nguyễn Minh Hy", "student_id": "521", "role": "USER"},
      {"display_name": "Hoàng Văn Tấn", "student_id": "522", "role": "USER"},
      {"display_name": "Đặng Trung Hiêu", "student_id": "1128", "role": "USER"}
    ]
  },
  {
    "group_name": "Mushealy",
    "users": [
      {"display_name": "Nguyễn Thị Thảo Nguyên", "student_id": "1199", "role": "TENANT_ADMIN"},
      {"display_name": "Nguyễn Anh Thư", "student_id": "1330", "role": "USER"},
      {"display_name": "Nguyễn Đại Phú Sang", "student_id": "1107", "role": "USER"},
      {"display_name": "Phan Lê Bảo Hoàng", "student_id": "1215", "role": "USER"},
      {"display_name": "Lê Thành Nhân", "student_id": "506", "role": "USER"},
      {"display_name": "Trần Đức Mạnh", "student_id": "1264", "role": "USER"}
    ]
  },
  {
    "group_name": "Six Senses",
    "users": [
      {"display_name": "Nguyễn Anh Khánh Sơn", "student_id": "1064", "role": "TENANT_ADMIN"},
      {"display_name": "Đặng Duy Nguyên", "student_id": "1231", "role": "USER"},
      {"display_name": "Lưu Nguyên Thanh Bình", "student_id": "1116", "role": "USER"},
      {"display_name": "Văn Quốc Huy", "student_id": "1250", "role": "USER"},
      {"display_name": "Trịnh Duy Nghiêm", "student_id": "1127", "role": "USER"},
      {"display_name": "Trần Đức Thiện", "student_id": "1185", "role": "USER"}
    ]
  },
  {
    "group_name": "RAGnarok",
    "users": [
      {"display_name": "Bùi Ngọc Phúc", "student_id": "501", "role": "TENANT_ADMIN"},
      {"display_name": "Trương Lục Gia Bảo", "student_id": "1179", "role": "USER"},
      {"display_name": "Huỳnh Nhật Huy", "student_id": "535", "role": "USER"},
      {"display_name": "Bùi Vũ Thiên Đăng", "student_id": "1129", "role": "USER"},
      {"display_name": "Phạm Nguyễn Đăng Khoa", "student_id": "503", "role": "USER"},
      {"display_name": "Chung Quốc Huy", "student_id": "510", "role": "USER"}
    ]
  }
]


async def seed() -> None:
    print("--- Starting Direct DB & Qdrant Seed ---")
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    qdrant_url = os.getenv("QDRANT_URL") or settings.qdrant_url
    qdrant_client = AsyncQdrantClient(
        url=qdrant_url,
        api_key=settings.qdrant_api_key,
    )

    try:
        # Fetch Role IDs map
        async with engine.begin() as conn:
            res = await conn.execute(text("SELECT role_name, role_id FROM public.roles WHERE is_deleted = false"))
            role_ids = {row[0]: row[1] for row in res.fetchall()}

        for group in GROUPS_DATA:
            group_name = group["group_name"]
            clean_group_name = remove_vietnamese_accents(str(group_name)).strip().replace(" ", "_").replace("-", "_").lower()
            tenant_name = re.sub(r'[^a-z0-9_]', '', clean_group_name)
            if not tenant_name:
                tenant_name = "tenant_dummy"
            collection_name = f"COL_{tenant_name.upper()}"

            print(f"\nProcessing Group: {group_name} -> Tenant Name: {tenant_name}")

            # 1. Insert/Get Tenant in DB
            from app.core.encryption import generate_tenant_dek
            # Generate DEK via AWS KMS (or local KEK fallback if KMS unavailable)
            _plaintext_dek, wrapped_dek = await generate_tenant_dek(tenant_name)
            _plaintext_dek = None  # zero out plaintext immediately

            async with engine.begin() as conn:
                tenant_res = await conn.execute(
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
                        "tenant_name": tenant_name,
                        "collection_name": collection_name,
                        "encrypted_dek": wrapped_dek,
                    },
                )
                tenant_id = tenant_res.scalar_one()
                print(f"  [+] Tenant DB Record: {tenant_name} (ID={tenant_id}, collection={collection_name})")

            # 2. Provision Tenant Postgres Schema (SCHEMA_{TENANT_NAME})
            async with engine.begin() as conn:
                schema_name = await provision_tenant_schema(conn, tenant_name)
                print(f"  [+] Postgres Schema '{schema_name}' ready.")

            # 3. Provision Qdrant Collection
            try:
                qdrant_repo = QdrantRepository(client=qdrant_client, vector_size=settings.rag_vector_size)
                await qdrant_repo.create_collection(collection_name)
                print(f"  [+] Qdrant Collection '{collection_name}' ready.")
            except Exception as e:
                print(f"  [-] Qdrant collection creation warning: {e}")

            # 4. Insert Users for Tenant
            async with engine.begin() as conn:
                for user in group["users"]:
                    display_name = user["display_name"].strip()
                    role = user["role"]
                    words = display_name.split()
                    last_two = words[-2:] if len(words) >= 2 else words
                    raw_user_name = "".join(last_two)
                    user_name = re.sub(r'[^a-z0-9]', '', remove_vietnamese_accents(raw_user_name).lower())
                    email_domain = tenant_name.replace("_", "")
                    email = f"{user_name}@{email_domain}.local"
                    pwd_hash = hash_password("123456")

                    u_res = await conn.execute(
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
                            "user_name": user_name,
                            "email": email,
                            "password_hash": pwd_hash,
                            "tenant_id": tenant_id,
                            "role_id": role_ids[role],
                            "full_name": display_name,
                        },
                    )
                    uid = u_res.scalar_one()
                    print(f"    [+] Created User: {display_name} | Role: {role} | username: {user_name} (ID={uid})")

        print("\n--- Direct Seed Complete ---")

    finally:
        await qdrant_client.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())

