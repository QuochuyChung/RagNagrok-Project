import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from qdrant_client import AsyncQdrantClient

from app.core.config import get_settings
from app.repositories.qdrant_repository import QdrantRepository

async def clear_db_and_qdrant_only():
    settings = get_settings()
    
    # 1. Connect to PostgreSQL
    print(f"Connecting to database at {settings.postgres_host}...")
    engine = create_async_engine(settings.database_url)
    
    # 2. Connect to Qdrant
    print(f"Connecting to Qdrant at {settings.qdrant_url}...")
    qdrant_client = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        timeout=settings.qdrant_timeout
    )
    qdrant_repo = QdrantRepository(client=qdrant_client, vector_size=settings.rag_vector_size)

    try:
        # Step A: Fetch all schemas and active tenants
        async with engine.begin() as conn:
            # Fetch all existing schemas
            print("Fetching schemas from database...")
            schemas_result = await conn.execute(
                text("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'SCHEMA_%' OR schema_name LIKE 'schema_%'")
            )
            schemas = [row[0] for row in schemas_result.fetchall()]

            # Fetch active tenants
            print("Fetching active tenants from public schema...")
            tenants_result = await conn.execute(
                text("SELECT tenant_id, tenant_name, collection_name FROM public.tenants WHERE is_deleted = false")
            )
            active_tenants = tenants_result.fetchall()

        # Step B: Clear PostgreSQL tables inside tenant schemas
        print(f"Found {len(schemas)} tenant schema(s) in PostgreSQL.")
        for schema_name in schemas:
            print(f"Clearing documents and chunks inside schema: \"{schema_name}\"...")
            async with engine.begin() as conn:
                try:
                    # Let's count rows before deleting (for reporting)
                    chunks_count = (await conn.execute(text(f'SELECT COUNT(*) FROM "{schema_name}".chunks'))).scalar()
                    docs_count = (await conn.execute(text(f'SELECT COUNT(*) FROM "{schema_name}".documents'))).scalar()
                    print(f" - Found {docs_count} documents and {chunks_count} chunks.")
                    
                    # Truncate tables
                    await conn.execute(text(f'TRUNCATE TABLE "{schema_name}".chunks CASCADE;'))
                    await conn.execute(text(f'TRUNCATE TABLE "{schema_name}".documents CASCADE;'))
                    print(f" - Successfully truncated tables in \"{schema_name}\".")
                except Exception as e:
                    print(f" - Error truncating schema \"{schema_name}\": {e}")

        # Step C: Delete all Qdrant collections
        print("Fetching Qdrant collections...")
        collections_resp = await qdrant_client.get_collections()
        collections = [col.name for col in collections_resp.collections]
        print(f"Found {len(collections)} collection(s) in Qdrant.")
        
        for col_name in collections:
            print(f"Deleting Qdrant collection: {col_name}...")
            try:
                await qdrant_repo.delete_collection(col_name)
                print(f" - Successfully deleted collection: {col_name}")
            except Exception as e:
                print(f" - Error deleting collection {col_name}: {e}")

        # Step D: Recreate Qdrant collections for active tenants
        print(f"Recreating Qdrant collections for {len(active_tenants)} active tenant(s)...")
        for tenant in active_tenants:
            tenant_id, tenant_name, collection_name = tenant
            print(f"Recreating collection '{collection_name}' for tenant '{tenant_name}'...")
            try:
                await qdrant_repo.create_collection(collection_name)
                print(f" - Successfully created collection: {collection_name}")
            except Exception as e:
                print(f" - Error creating collection {collection_name}: {e}")

        print("\nAll database tables (documents, chunks) and Qdrant collections have been cleared successfully!")
        print("S3 files and local folder backup files were NOT modified or deleted.")

    except Exception as e:
        print(f"An error occurred during the clearing process: {e}")
    finally:
        await engine.dispose()
        await qdrant_client.close()

if __name__ == "__main__":
    asyncio.run(clear_db_and_qdrant_only())
