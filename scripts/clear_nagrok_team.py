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
from app.repositories.qdrant_repository import QdrantRepository

async def main() -> None:
    settings = get_settings()
    
    schema_name = "SCHEMA_TEAM NAGROK"
    collection_name = "COL_TEAM NAGROK"
    
    print(f"Connecting to database at {settings.postgres_host}...")
    engine = create_async_engine(settings.database_url)
    
    print(f"Connecting to Qdrant at {settings.qdrant_url}...")
    qdrant_client = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )
    qdrant_repo = QdrantRepository(client=qdrant_client, vector_size=settings.rag_vector_size)
    
    try:
        # Step 1: PostgreSQL DML data deletion
        print(f"\n--- Checking PostgreSQL Schema: \"{schema_name}\" ---")
        async with engine.begin() as conn:
            # Check if schema exists
            schema_exists_result = await conn.execute(
                text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = :schema"),
                {"schema": schema_name}
            )
            if not schema_exists_result.fetchone():
                print(f"Schema \"{schema_name}\" does not exist in PostgreSQL. Exiting.")
                return
            
            # Fetch all tables in the schema
            tables_result = await conn.execute(
                text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = :schema AND table_type = 'BASE TABLE'
                """),
                {"schema": schema_name}
            )
            tables = [row[0] for row in tables_result.fetchall()]
            print(f"Found tables in schema \"{schema_name}\": {tables}")
            
            # Count rows before truncate
            print("Row counts before clearing:")
            for table in tables:
                cnt_res = await conn.execute(text(f'SELECT COUNT(*) FROM "{schema_name}"."{table}"'))
                cnt = cnt_res.scalar()
                print(f" - \"{schema_name}\".\"{table}\": {cnt} row(s)")
                
            # Perform DML clearing (Truncate)
            if tables:
                print(f"\nClearing DML data for tables in \"{schema_name}\"...")
                truncate_statements = ", ".join([f'"{schema_name}"."{table}"' for table in tables])
                # We use CASCADE to handle foreign key dependencies and RESTART IDENTITY to reset auto-increment fields
                await conn.execute(text(f"TRUNCATE TABLE {truncate_statements} RESTART IDENTITY CASCADE;"))
                print("DML tables truncated successfully.")
            
            # Count rows after truncate to verify
            print("\nRow counts after clearing:")
            for table in tables:
                cnt_res = await conn.execute(text(f'SELECT COUNT(*) FROM "{schema_name}"."{table}"'))
                cnt = cnt_res.scalar()
                print(f" - \"{schema_name}\".\"{table}\": {cnt} row(s)")
                
        # Step 2: Qdrant collection deletion and recreation
        print(f"\n--- Checking Qdrant Collection: \"{collection_name}\" ---")
        exists = await qdrant_client.collection_exists(collection_name)
        if exists:
            # Count points before deletion
            col_info = await qdrant_client.get_collection(collection_name)
            points_count = col_info.points_count
            print(f"Collection \"{collection_name}\" exists with {points_count} points.")
            
            print(f"Deleting collection: \"{collection_name}\"...")
            await qdrant_repo.delete_collection(collection_name)
            print("Deleted collection successfully.")
        else:
            print(f"Collection \"{collection_name}\" does not exist in Qdrant.")
            
        print(f"Recreating empty collection: \"{collection_name}\"...")
        await qdrant_repo.create_collection(collection_name)
        print("Recreated empty collection successfully.")
        
        # Verify collection status
        col_info = await qdrant_client.get_collection(collection_name)
        print(f"Verified: Collection \"{collection_name}\" now exists with {col_info.points_count} points.")
        
        print("\nAll tasks completed successfully without touching S3.")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        await engine.dispose()
        await qdrant_client.close()

if __name__ == "__main__":
    asyncio.run(main())
