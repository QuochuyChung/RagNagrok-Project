import asyncio
from logging.config import fileConfig

from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.core.config import get_settings
from app.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Gán connection strings vào bên trong Alembic Config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# metadata là toàn bộ thông tin về db đó
target_metadata = Base.metadata


# ── Feature 2: Multi-schema awareness ───────────────────────────────────────
# Alembic's autogenerate should only scan the "public" schema for system tables.
# Tenant schemas (tenant_*) are created programmatically by provision_tenant_schema()
# and should NOT be auto-detected by alembic revision --autogenerate.

def include_name(name, type_, parent_names):
    """
    Filter function that tells Alembic which schemas to include in autogenerate.
    """
    if type_ == "schema":
        # Only autogenerate against the public schema
        return name is None or name == "public"
    return True

def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table":
        # Exclude tenant-scoped tables from being generated in public
        tenant_tables = {"documents", "chunks", "conversations", "messages"}
        if name in tenant_tables:
            return False
    elif type_ == "foreign_key_constraint":
        # Ignore spurious FK drops/adds on public tables due to schema='public' vs schema=None
        if object.table.name in {"users", "audit_logs"}:
            return False
    return True

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Feature 2: Scan only the public schema during autogenerate
        include_schemas=True,
        include_name=include_name,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """
    Run migrations against a live DB connection.

    ``include_schemas=True`` tells Alembic to be aware of multiple schemas.
    ``include_name`` restricts autogenerate to the public schema so that
    tenant_* schemas don't appear as "unexpected tables" in every revision.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Feature 2: Multi-schema support
        include_schemas=True,
        include_name=include_name,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations against it."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

