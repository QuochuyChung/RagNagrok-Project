# Sprint 2 Report — Repository Restructuring & PostgreSQL Setup

**Period**: Sprint 2 (2026-07-01)

## What Was Accomplished

### Repository Restructuring
- Migrated from a flat structure to the layered architecture defined in `repo-x.txt`
- All code now lives under `app/` with clear separation of concerns:
  - `api/` — HTTP layer (routes, deps)
  - `core/` — infrastructure (config, logging, errors)
  - `middleware/` — request processing (request_id, tenant)
  - `schemas/` — Pydantic contracts (split per domain)
  - `services/` — business logic stubs
  - `repositories/` — data access stubs
  - `clients/` — external service wrappers
  - `utils/` — pure helper functions

### PostgreSQL Integration
- Replaced SQLite with `postgres:15-alpine` in `compose.yaml`
- Added Docker healthcheck (`pg_isready`) with `depends_on: condition: service_healthy` for the gateway
- SQLAlchemy async engine initialized in the FastAPI lifespan, stored as `app.state.db_engine`
- Health check endpoint now verifies PostgreSQL connectivity via `SELECT 1`

### New Files
- `app/core/errors.py` — centralized exception handler registration
- `app/middleware/request_id.py` — X-Request-ID propagation
- `app/middleware/tenant.py` — X-Tenant-ID validation
- `docker/Dockerfile.gateway` — production image
- `Makefile` — common dev commands
- `docs/api_contract.md` — endpoint documentation
- `tests/unit/test_hashing.py`, `tests/unit/test_time.py` — first unit tests
- `scripts/curl_examples/health_check.sh`, `scripts/load_test.sh`

## What Was Learned
- SQLAlchemy async engine must be disposed in shutdown to avoid connection leaks
- Docker `service_healthy` condition requires an explicit healthcheck on the postgres service
- Starlette middleware registration order is reversed (last registered runs first)

## Blockers / Next Steps
- Sprint 3: Implement `TenantService`, `TenantRepository`, and full CRUD for `/v1/tenants`
- Sprint 3: Implement document ingestion pipeline
- Sprint 3: Add Alembic migrations for tenant and document tables
