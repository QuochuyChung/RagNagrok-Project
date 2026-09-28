# ADR 0001: Schema-per-Tenant Architecture

**Status:** Accepted  
**Date:** 2026-07-19  

## 1. Context and Problem
The Ragnarok Multi-Tenant RAG API Gateway must securely serve multiple client organizations (tenants) from a single application instance. Previously, we relied on **Row-level Separation** (where every table shares all data and relies on a `tenant_id` column). 

This approach presented several challenges:
* **Data Leakage Risk:** A developer forgetting to include `WHERE tenant_id = ?` in a query could accidentally expose one tenant's documents or conversations to another.
* **Data Lifecycle Management:** Deleting a tenant required finding and deleting their rows across every single table in the database, which is slow and prone to orphan records.
* **Compliance & Security:** Enterprise clients often demand strict physical or logical separation of their vector/document data.

## 2. Options Considered

* **Option 1: Database-per-Tenant** 
  * *Pros:* Maximum isolation; highest security; easy backup/restore per tenant.
  * *Cons:* Extreme overhead; managing connection pools for hundreds of databases is resource-intensive and complex; expensive infrastructure.
* **Option 2: Schema-per-Tenant with Shared Identity** (Logical Separation)
  * *Pros:* Strong isolation at the PostgreSQL level; single database connection pool; easy tenant teardown (`DROP SCHEMA`); developers don't need to worry about `tenant_id` filters in ORM queries.
  * *Cons:* Migrations become more complex; background jobs need special context to know which schema to query.
* **Option 3: Row-level Separation (Status Quo)**
  * *Pros:* Easiest to implement initially; simple database migrations.
  * *Cons:* High risk of accidental data exposure; hard to isolate tenant backups.

## 3. Decision Made
We chose **Option 2: Schema-per-Tenant with Shared Identity**.

**Implementation Details:**
1. **Shared Identity (`public` schema):** Tables that span the entire platform (`users`, `tenants`, `roles`, `audit_logs`) reside strictly in the PostgreSQL `public` schema.
2. **Tenant Schemas:** When a new tenant is created, the system dynamically provisions an isolated PostgreSQL schema named `SCHEMA_{TENANT_NAME.upper()}`. Tenant-scoped tables (`documents`, `chunks`, `conversations`, `messages`) are instantiated inside this new schema without `tenant_id` columns.
3. **Strict Naming Rules:** To prevent SQL injection and naming conflicts, tenant names are validated via Pydantic (`^[A-Za-z0-9_]+$`), rejecting spaces and hyphens. The name is immutable once created.
4. **Dynamic Routing:** We utilize SQLAlchemy's `schema_translate_map` on the `AsyncSession`. The FastAPI middleware extracts the `tenant_name` from the JWT payload and dynamically injects the correct schema mapping into the execution options before hitting the Service layer.

## 4. Consequences

### Positive
* **Security & Isolation:** It is practically impossible for a query executed in one tenant's context to accidentally leak another tenant's documents. The schema boundary physically prevents it.
* **Cleaner Application Code:** The `tenant_id` foreign keys and filter logic were entirely stripped from the `Document` and `Conversation` repositories. The ORM models are much cleaner.
* **Easy Teardown:** Hard-deleting a tenant's entire knowledge base is now a single, O(1) operation: `DROP SCHEMA IF EXISTS "SCHEMA_FPTCORP" CASCADE`.

### Negative
* **Migration Complexity:** Alembic's `autogenerate` does not handle multi-schema setups gracefully. We had to move away from standard incremental migrations for tenant tables, opting instead for a single **Canonical Migration** script (`8517dd8e0f39_first_migration_for_db.py`) containing a helper function `_create_tenant_schema_tables` to generate DDL at runtime.
* **Background Worker Complexity:** Celery workers do not have an incoming HTTP request state. We had to manually implement schema mapping injection and database lookups inside worker tasks (`ingest_task.py`) to ensure they route to the correct tenant.
* **Transaction Management Conflicts:** SQLAlchemy's `session.connection(execution_options=...)` implicitly starts a transaction. We had to update our Service layer (e.g., `TenantService`) to check `session.in_transaction()` before attempting to call `session.begin()`, avoiding `InvalidRequestError` crashes.

## 5. Related Decisions & Trade-offs
* **Cross-Schema Foreign Keys:** To maintain a unified login system (Shared Identity), we allowed the `conversations` table (in tenant schemas) to hold a foreign key pointing to `public.users(user_id)`. PostgreSQL supports this natively, trading a small amount of physical isolation for a much simpler authentication flow.
* **Dropping Support for Hyphens:** We explicitly traded away the flexibility of allowing hyphens in tenant names (e.g., `fpt-corp`) to ensure tenant names map 1:1 to safe, unquoted PostgreSQL identifiers (`SCHEMA_FPTCORP`), significantly reducing the complexity of raw DDL execution in Python.
