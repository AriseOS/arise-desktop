# Cloud Backend

Memory-as-a-Service + Auth proxy for Ami (v3.2.0). All user management delegated to sub2api — Cloud Backend has NO local users table.

## Architecture

- **No local users table**: Sub2api's PostgreSQL is the single source of truth for all user data (accounts, passwords, roles, status, subscriptions)
- **Cloud Backend = proxy layer**: Auth endpoints delegate to sub2api, memory endpoints use SurrealDB
- **JWT auth**: Cloud Backend issues its own JWT tokens (user_id = sub2api user ID)
- **Server-side API keys**: Embedding and rerank API keys are server-managed (env vars)
- **Per-user LLM keys**: Via sub2api integration (provisioned at registration)
- **User isolation**: Each user gets own private SurrealDB database for memory
- **Public memory**: Shared community memory for published CognitivePhrases
- **HTTPS**: Caddy reverse proxy with auto Let's Encrypt (deploy/caddy/)

## Dependencies

### SurrealDB (Required for Memory System)

Memory system uses SurrealDB for persistent graph storage.

### Sub2api (Required for User Management)

Sub2api manages users, API keys, subscriptions, email verification, password reset. Cloud Backend communicates via Admin API (`x-api-key`) and User API (`Bearer JWT`).

### Environment Variables (Required)

```bash
export JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export EMBEDDING_API_KEY="your-embedding-api-key"
export SUB2API_ADMIN_API_KEY="your-sub2api-admin-key"
# Optional:
export RERANK_API_KEY="your-rerank-api-key"
```

## Directories

- `api/` - JWT service, Pydantic schemas, structured error codes
- `core/` - Config service, logging, middleware (security headers), rate limiter
- `services/` - Storage service, Sub2API client (all user operations)
- `config/` - YAML configuration
- `deploy/caddy/` - Caddy reverse proxy for HTTPS

## Key Files

- `main.py` - FastAPI application with all API routes (typed Pydantic models)
- `api/auth.py` - JWT token creation/verification only (no user database)
- `api/schemas.py` - Pydantic request/response models for all endpoints
- `api/errors.py` - Structured error codes (ErrorCode enum, AppError, exception handlers)
- `services/sub2api_client.py` - Sub2API client (user CRUD, API keys, auth proxying)
- `core/middleware.py` - Request context + security headers middleware
- `core/rate_limiter.py` - slowapi rate limiting per endpoint
- `config/cloud-backend.yaml` - Server configuration
- `cli.py` - Admin CLI (create-admin, list-users) via sub2api

## API Patterns

### User Data Flow

```
Client → Cloud Backend (JWT auth) → sub2api Admin API (user data)
                                   → SurrealDB (memory data)
```

Registration: `sub2api.register()` creates user + API key in sub2api → Cloud Backend issues JWT with `sub=sub2api_user_id`.

### Structured Error Responses

All errors return unified format:
```json
{"success": false, "error": {"code": "AUTH_INVALID_CREDENTIALS", "message": "..."}}
```

### Security Headers

`SecurityHeadersMiddleware` adds X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy. CORS `allow_headers` restricted to: Authorization, Content-Type, X-Request-ID.

## Logging

Structured JSON logging with request context injection (request_id, user_id from JWT).
