import asyncio
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import get_settings

async def clear_dml_data():
    settings = get_settings()
    
    print(f"Connecting to database at {settings.postgres_host}...")
    engine = create_async_engine(settings.database_url)
    
    try:
        async with engine.begin() as conn:
            # 1. Fetch all schemas from the database
            print("Fetching schemas from database...")
            schemas_result = await conn.execute(
                text("SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')")
            )
            schemas = [row[0] for row in schemas_result.fetchall()]
            
            print(f"Found {len(schemas)} schemas: {', '.join(schemas)}")
            
            # Target tables to look for
            target_tables = {"conversations", "messages", "message", "chunks", "documents"}
            
            for schema in schemas:
                # 2. Check which target tables exist in this schema
                table_check_query = text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = :schema 
                      AND table_name = ANY(:targets)
                """)
                
                tables_result = await conn.execute(table_check_query, {"schema": schema, "targets": list(target_tables)})
                existing_tables = [row[0] for row in tables_result.fetchall()]
                
                if not existing_tables:
                    continue
                
                print(f"\nProcessing schema: \"{schema}\"")
                print(f"Found target tables: {', '.join(existing_tables)}")
                
                # Count rows before truncate
                counts = {}
                for table in existing_tables:
                    try:
                        count_result = await conn.execute(text(f'SELECT COUNT(*) FROM "{schema}"."{table}"'))
                        counts[table] = count_result.scalar()
                    except Exception as e:
                        counts[table] = f"Error counting: {e}"
                
                print(f"Row counts before truncation: {counts}")
                
                # Build the truncate SQL
                tables_to_truncate = ", ".join(f'"{schema}"."{table}"' for table in existing_tables)
                truncate_sql = f'TRUNCATE TABLE {tables_to_truncate} RESTART IDENTITY CASCADE;'
                
                print(f"Executing: {truncate_sql}")
                await conn.execute(text(truncate_sql))
                print(f"Successfully truncated tables in schema \"{schema}\".")
                
        print("\nDML clear operation completed successfully!")
        
    except Exception as e:
        print(f"\nAn error occurred during the clearing process: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(clear_dml_data())
