# Cloud Backend

Memory-as-a-Service + Auth platform for Ami. Provides JWT-based authentication and memory endpoints with server-side API keys.

## Dependencies

### SurrealDB (Required for Memory System)

Memory system uses SurrealDB for persistent graph storage.

```bash
docker run -d --name surrealdb \
  -p 8000:8000 \
  surrealdb/surrealdb:latest \
  start --allow-experimental record_references --user root --pass your_password
```

### Environment Variables (Required)

```bash
export JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export EMBEDDING_API_KEY="your-embedding-api-key"
export LLM_API_KEY="your-llm-api-key"
```

## Directories

- `api/` - Authentication (auth.py with JWT-based AuthService)
- `core/` - Config service, logging, middleware
- `database/` - SQLAlchemy models (User)
- `services/` - Storage service (minimal, filesystem management)
- `config/` - YAML configuration

## Key Files

- `main.py` - FastAPI application with all API routes
- `api/auth.py` - JWT auth service (SECRET_KEY from env, bcrypt passwords)
- `core/middleware.py` - Request context middleware (JWT-based user extraction)
- `config/cloud-backend.yaml` - Server configuration including API key env var names

## API Endpoints

All endpoints use `/api/v1/` prefix.

### Auth (no auth required)
- `POST /api/v1/auth/login` - User login, returns access_token + refresh_token
- `POST /api/v1/auth/register` - User registration (auto-login, returns tokens)
- `POST /api/v1/auth/refresh` - Exchange refresh_token for new access_token

### Auth (JWT auth required)
- `GET /api/v1/auth/me` - Get current user profile
- `PUT /api/v1/auth/me` - Update profile (full_name)
- `POST /api/v1/auth/change-password` - Change password

### Memory (JWT auth required)
- `POST /api/v1/memory/add` - Add recording to user's workflow memory
- `POST /api/v1/memory/query` - Unified memory query (task/navigation/action)
- `POST /api/v1/memory/phrase/query` - Query CognitivePhrase
- `POST /api/v1/memory/state` - Get State by URL
- `GET /api/v1/memory/stats` - User's memory statistics
- `DELETE /api/v1/memory` - Clear user's private memory
- `GET /api/v1/memory/phrases` - List user's CognitivePhrases
- `GET /api/v1/memory/phrases/{id}` - Get phrase detail
- `DELETE /api/v1/memory/phrases/{id}` - Delete phrase
- `POST /api/v1/memory/share` - Share phrase to public
- `GET /api/v1/memory/publish-status` - Check publish status
- `POST /api/v1/memory/unpublish` - Unpublish phrase
- `POST /api/v1/memory/workflow-query` - Reasoner workflow query
- `POST /api/v1/memory/plan-route` - Reasoner path planning
- `POST /api/v1/memory/plan` - PlannerAgent task analysis
- `POST /api/v1/memory/learn` - Post-execution learning

### Public (no auth required)
- `GET /api/v1/memory/stats/public` - Aggregated public stats
- `GET /api/v1/memory/public/phrases` - List public phrases (supports `sort`, `limit`)
- `GET /api/v1/memory/public/phrases/{id}` - Get public phrase detail

### Utility
- `GET /health` - Health check
- `POST /api/v1/app/version-check` - Client version compatibility

## Architecture

- Server-side API keys: Embedding and LLM API keys are server-managed (from env vars), not user-provided
- JWT auth: All memory endpoints require `Authorization: Bearer <token>` header
- User isolation: Each user gets their own private SurrealDB database for memory
- Public memory: Shared community memory for published CognitivePhrases

## Logging

Structured JSON logging with request context injection (request_id, user_id from JWT).
