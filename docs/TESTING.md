# Testing Documentation: Tenants, Users, and Authentication

This document provides a comprehensive guide for developers on how to run, configure, and understand the unit and integration tests for the Core API endpoints (`/tenants`, `/users`, and `/auth/login`).

**Target Audience:** Backend Developers, QA Engineers, and DevOps Engineers.

---

## 1. Overview

The testing suite for the Ragnarok API Gateway ensures the stability and security of multi-tenant data access, user role-based access control (RBAC), and authentication. 

- **Unit Tests (`tests/unit/`)**: Focus on business logic inside the Service layer (`TenantService`, `UserService`, `AuthService`). They use `AsyncMock` to isolate the database (SQLAlchemy) and vector store (Qdrant). These are lightning-fast, highly isolated, and run without external dependencies.
- **Integration Tests (`tests/integration/`)**: Validate the end-to-end request lifecycle through the FastAPI routing layer, services, and into the live database/Qdrant containers. They use `httpx.AsyncClient` to simulate real HTTP requests and assert accurate status codes, validation responses, and database state mutations.

---

## 2. Installation Instructions

### Prerequisites
- **Python 3.11+**
- **Docker & Docker Compose** (Required for integration tests)
- **Virtual Environment**

### Setup Steps
1. **Clone and activate the virtual environment:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/Mac:
   source .venv/bin/activate
   ```
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Start the Integration Environment:**
   Integration tests require live PostgreSQL and Qdrant containers.
   ```bash
   docker compose up -d postgres qdrant
   ```
4. **Run Database Migrations and Seed Data:**
   ```bash
   alembic upgrade head
   python scripts/seed_UserTenant.py
   ```

> [!WARNING]
> **Common Pitfall**: Running integration tests without seeding the database will cause the authentication setup fixtures to fail, as the tests rely on the `platform_admin` seed user. The seed script is idempotent and can be safely re-run.

---

## 3. Configuration Options

Testing behavior is controlled via `pytest.ini` and environment variables defined in `.env`.

### `pytest.ini` Configuration
- `asyncio_mode = auto`: Ensures that `pytest-asyncio` automatically detects and runs asynchronous test functions.
- `asyncio_default_fixture_loop_scope = session` / `asyncio_default_test_loop_scope = session`: Ensures all tests and fixtures share the same asyncio event loop. This prevents connection teardown bugs and `httpx.WriteTimeout` network congestion across integration tests.
- `testpaths = tests`: Dictates the root directory for test discovery.

### Environment Variables
Integration tests rely on the following environment variables (can be set in `.env`):
- `DATABASE_URL`: Connection string for PostgreSQL (e.g., `postgresql+asyncpg://ragnarok:ragnarok_secret@localhost:5432/rag_db`).
- `QDRANT_URL`: URL for the Qdrant vector database (e.g., `http://localhost:6333`).
- `API_BASE_URL`: The URL of the local API for `httpx` to route requests to (e.g., `http://localhost:8000`).

> [!TIP]
> **Best Practice**: Never use production connection strings in your `.env` during local testing. Ensure Docker containers are mapped to localhost ports specifically for local development.

---

## 4. API Reference

The test suite provides complete coverage over the following core API endpoints:

| Endpoint | Method | Scope | Key Behaviors Tested |
| :--- | :--- | :--- | :--- |
| `/v1/auth/login` | POST | Unit / Integration | Valid credentials, Invalid passwords, Missing fields |
| `/v1/tenants` | POST | Unit / Integration | Creation, Qdrant collection creation, Schema Validation, Name collision |
| `/v1/tenants` | GET | Unit / Integration | Pagination, Tenant listing logic |
| `/v1/tenants/{id}` | GET | Unit / Integration | Retrieval, Not Found (404) on soft-deleted tenants |
| `/v1/tenants/{id}` | DELETE | Unit / Integration | Soft-delete logic, Qdrant Collection teardown |
| `/v1/users` | POST | Unit / Integration | `TENANT_ADMIN` RBAC restrictions, Cross-tenant isolation |
| `/v1/users` | GET | Unit / Integration | Cross-tenant user filtering |

---

## 5. Testing Logic Flow & Function Meaning

The following section breaks down the specific meaning, flow, and intent of each file and function in the test suite.

### Unit Tests (`tests/unit/`)

#### 1. `test_auth_service.py`
Validates the `AuthService` logic for authenticating users and issuing JWT tokens.
- **`TestLoginHappyPath`**
  - `test_valid_credentials_return_jwt_token`: Ensures a valid username/password pair successfully generates a token.
  - `test_password_hash_is_verified_not_compared_plaintext`: Guarantees that the service hashes the password before comparing it with the DB.
- **`TestLoginInvalidCredentials`**
  - `test_unknown_username_raises_value_error`: Ensures that if the DB returns `None`, an `InvalidCredentialsError` is thrown.
  - `test_wrong_password_raises_value_error`: Ensures mismatched hashes reject authentication.
- **`TestLoginEdgeCases`**
  - Includes edge cases like special characters, extra-long passwords, and whitespace-only usernames.

#### 2. `test_tenant_service.py`
Validates `TenantService` logic for creating, retrieving, listing, and deleting tenants alongside Qdrant vectors.
- **`TestCreateTenant`**
  - `test_happy_path_returns_tenant_response`: Verifies standard creation logic calling the postgres DB and Qdrant repo.
  - `test_qdrant_failure_raises_qdrant_error`: Ensures that if Qdrant is offline, a `QdrantCollectionCreationError` is safely propagated without leaving orphaned data.
  - `test_boundary_name_min_length` / `max_length`: Validates service-layer string boundaries.
- **`TestDeleteTenant`**
  - `test_happy_path_calls_soft_delete_and_qdrant`: Validates that a DELETE request flags the DB as inactive AND deletes the associated Qdrant collection.

#### 3. `test_user_service.py`
Validates `UserService` and its strict multi-tenant RBAC logic.
- **`TestCreateUser`**
  - `test_platform_admin_creates_tenant_admin`: Confirms root users can provision tenant managers.
  - `test_tenant_admin_cannot_create_user_in_other_tenant`: Crucial security test ensuring cross-tenant data leakage is impossible when provisioning users.
  - `test_tenant_admin_cannot_create_tenant_admin`: Restricts privilege escalation.
- **`TestDeleteUser`**
  - `test_tenant_admin_cannot_delete_user_in_other_tenant`: Prevents malicious IDs from being passed to delete external users.

#### 4. `test_time.py` & `test_hashing.py`
- Contains straightforward pure-function tests verifying that passwords resolve deterministically via SHA-256 and that UTC timestamps are timezone-aware.

### Integration Tests (`tests/integration/`)

#### 1. `conftest.py` (Fixtures)
This file establishes the testing ecosystem.
- `db_session`: Bootstraps an async SQLAlchemy engine inside the session event loop, yielding a connection for raw SQL teardowns.
- `http_client`: Bootstraps the `httpx.AsyncClient` pointing at `http://localhost:8000`.
- `platform_admin_token`: Executes a live POST to `/v1/auth/login` using the `platform_admin` seed data, yielding an active JWT for tests.
- `test_tenant_data`: A setup/teardown fixture that creates a temporary tenant via HTTP before a test, and completely purges it via raw SQL (and Qdrant SDK) after the test completes.

#### 2. `test_tenant_flow.py`
End-to-End lifecycle tests for the Tenant REST API.
- **`test_tenant_lifecycle`**
  - **Flow**: Creates a tenant → Queries it → Deletes it → Verifies it is missing.
  - **Meaning**: Proves that Qdrant collections are successfully provisioned via FastAPI, and that when a DELETE `204 No Content` is returned, the Qdrant SDK successfully purges the vector store.
- **`test_tenant_validation_errors`**
  - **Flow**: Sends empty strings and missing JSON fields.
  - **Meaning**: Proves that FastAPI/Pydantic returns HTTP `422 Unprocessable Entity` before hitting the database.
- **`test_tenant_unauthorized_access`**
  - **Meaning**: Verifies that requests lacking a valid Bearer token return `401 Unauthorized`.

#### 3. `test_user_flow.py`
End-to-End lifecycle tests for User RBAC and Isolation.
- **`test_user_lifecycle_and_rbac`**
  - **Flow**: A PLATFORM_ADMIN creates a TENANT_ADMIN → TENANT_ADMIN logs in → TENANT_ADMIN creates a USER in their tenant → TENANT_ADMIN tries (and fails) to create a USER in a different tenant → USER logs in and fails to list all users.
  - **Meaning**: The ultimate multi-tenant isolation test. Proves that the JWT payload correctly restricts authorization across different roles and tenants within the live routing layer.
- **`test_auth_edge_cases`**
  - **Meaning**: Submits invalid passwords and non-existent usernames to the live API to ensure it safely returns `401 Unauthorized` without crashing.

---

## 6. Usage Examples

### Running the Entire Test Suite
To run all tests (Unit and Integration):
```bash
pytest
```

### Running Only Unit Tests
If you don't have Docker running, you can isolate unit tests:
```bash
pytest tests/unit -v
```

### Running Only Integration Tests
```bash
pytest tests/integration -v
```

### Generating a Coverage Report
> [!IMPORTANT]
> To ensure your code meets coverage requirements, run pytest with the `coverage` module.
```bash
# Install coverage if not present
pip install coverage pytest-cov pytest-asyncio

# Run tests and generate an HTML report
pytest --cov=app tests/
coverage html
```
*Open `htmlcov/index.html` in your browser to view the interactive line-by-line coverage report.*

### Debugging a Specific Failure
If a specific integration test fails, use the `-s` flag to prevent pytest from swallowing `print()` statements, and the `-k` flag to target the test by name:
```bash
pytest tests/integration/test_tenant_flow.py -k "test_tenant_lifecycle" -v -s
```
