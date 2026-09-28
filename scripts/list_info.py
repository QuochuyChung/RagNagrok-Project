import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from qdrant_client import AsyncQdrantClient

from app.core.config import get_settings

async def main() -> None:
    settings = get_settings()
    
    print("Database URL:", settings.database_url)
    print("Qdrant URL:", settings.qdrant_url)
    
    engine = create_async_engine(settings.database_url)
    
    async with engine.begin() as conn:
        print("\n--- PostgreSQL Schemas ---")
        result = await conn.execute(text("SELECT schema_name FROM information_schema.schemata"))
        schemas = [row[0] for row in result.fetchall()]
        for s in schemas:
            print(" -", s)
            
        print("\n--- Tenants (public.tenants) ---")
        try:
            result = await conn.execute(text("SELECT tenant_id, tenant_name, collection_name, is_deleted FROM public.tenants"))
            tenants = result.fetchall()
            for t in tenants:
                print(f" - ID: {t[0]} | Name: {t[1]} | Collection: {t[2]} | Deleted: {t[3]}")
        except Exception as e:
            print("Error reading tenants:", e)
            
    await engine.dispose()
    
    print("\n--- Qdrant Collections ---")
    try:
        qdrant_client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )
        collections_resp = await qdrant_client.get_collections()
        collections = [col.name for col in collections_resp.collections]
        for c in collections:
            print(" -", c)
        await qdrant_client.close()
    except Exception as e:
        print("Error reading Qdrant collections:", e)

if __name__ == "__main__":
    asyncio.run(main())
