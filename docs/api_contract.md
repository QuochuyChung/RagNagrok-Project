# API Contract — Multi-Tenant RAG Gateway

> **Version**: 0.2.0 (Sprint 2)
> **Base URL**: `http://localhost:8000`

---

## Authentication

All endpoints under `/v1/` require the `X-Tenant-ID` header.

| Header | Required | Description |
|--------|----------|-------------|
| `X-Tenant-ID` | Yes (for `/v1/*`) | The tenant's unique slug (e.g. `team-alpha`) |
| `X-Request-ID` | No | Client-provided correlation ID; one is generated if absent |

---

## Public Endpoints (No Auth Required)

### `GET /health`

Returns aggregate health status of the gateway and backing services.

**Query Params**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `debug` | boolean | `false` | Include per-service latency breakdown |

**Response 200 — healthy / degraded**

```json
{
  "status": "healthy",
  "timestamp": "2026-07-01T06:00:00Z",
  "version": "0.2.0",
  "services": null
}
```

**Response 200 — healthy (debug mode)**

```json
{
  "status": "healthy",
  "timestamp": "2026-07-01T06:00:00Z",
  "version": "0.2.0",
  "services": {
    "postgres": { "status": "up", "latency_ms": 1.1, "error": null },
    "qdrant":   { "status": "up", "latency_ms": 1.5, "error": null },
    "ollama":   { "status": "up", "latency_ms": 5.2, "error": null },
    "open_webui": { "status": "down", "latency_ms": 3.1, "error": "Connection refused" }
  }
}
```

**Response 503 — unhealthy** (critical service down: postgres, qdrant, or ollama)

---

### `GET /version`

Returns build and runtime version metadata.

**Response 200**

```json
{
  "version": "0.2.0",
  "api_version": "v1",
  "python_version": "3.12.4",
  "build_date": "2026-07-01",
  "git_commit": "abc1234"
}
```

---

## Protected Endpoints (Sprint 3+)

> The following endpoints are **scaffolded** and will be fully implemented in Sprint 3.

### `POST /v1/tenants` — Create Tenant
### `GET /v1/tenants` — List Tenants
### `GET /v1/tenants/{id}` — Get Tenant
### `DELETE /v1/tenants/{id}` — Delete Tenant

### `POST /v1/documents` — Upload Document
### `GET /v1/documents` — List Documents
### `DELETE /v1/documents/{doc_id}` — Delete Document

### `POST /v1/retrieve` — Semantic Search
### `POST /v1/chat` — RAG Chat

---

## Standard Error Response

All errors use a consistent envelope:

```json
{
  "error_code": "TENANT_NOT_FOUND",
  "message": "No tenant exists with the given ID.",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "timestamp": "2026-07-01T06:00:00Z"
}
```

| HTTP Status | Error Code | Cause |
|-------------|------------|-------|
| 400 | `TENANT_REQUIRED` | Missing `X-Tenant-ID` header |
| 400 | `VALIDATION_ERROR` | Invalid request body |
| 404 | `TENANT_NOT_FOUND` | Tenant does not exist |
| 503 | — | Critical backing service is down |
| 500 | `INTERNAL_SERVER_ERROR` | Unhandled exception |
