# Ami Cloud Backend Deployment

## Architecture

```
                    Caddy (reverse proxy, managed separately)
                    |
        +-----------+-----------+
        |                       |
   /api/* -> cloud-backend   /v1/* -> sub2api
                |
           surrealdb
```

**This compose manages:** Cloud Backend + SurrealDB + SurrealDB Backup

**Managed separately:** Sub2API, PostgreSQL, Redis, Caddy

## Prerequisites

1. **Sub2API** deployed and accessible (with its own postgres, redis, caddy)
2. **Embedding API key** from a third-party provider (e.g., SiliconFlow)
3. Docker and Docker Compose installed

## Quick Start

```bash
cd deploy/production

# 1. Configure environment variables
cp .env.example .env
nano .env
# Fill in: JWT_SECRET_KEY, SURREALDB_PASSWORD, SUB2API_ADMIN_API_KEY, EMBEDDING_API_KEY

# 2. Configure cloud-backend.yaml
#    Edit src/cloud_backend/config/cloud-backend.yaml
#    Set llm.proxy_url to your sub2api address, e.g.:
#      Development: http://localhost:8080
#      Production:  https://api.yourdomain.com

# 3. Start services
docker compose up -d

# 4. Check logs
docker compose logs -f cloud-backend

# 5. Verify
curl http://localhost:9090/health
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `JWT_SECRET_KEY` | Yes | JWT signing secret. Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `SURREALDB_PASSWORD` | Yes | SurrealDB root password |
| `SUB2API_ADMIN_API_KEY` | Yes | Sub2API admin API key (x-api-key header) |
| `EMBEDDING_API_KEY` | Yes | Embedding provider API key |
| `RERANK_API_KEY` | No | Rerank provider API key (disabled if empty) |
| `SURREALDB_USER` | No | SurrealDB username (default: root) |
| `BIND_HOST` | No | Bind address (default: 127.0.0.1) |
| `TZ` | No | Timezone (default: Asia/Shanghai) |

## Common Operations

```bash
# View logs
docker compose logs -f cloud-backend
docker compose logs -f surrealdb

# Restart cloud backend (e.g., after config change)
docker compose restart cloud-backend

# Rebuild after code update
docker compose up -d --build cloud-backend

# Stop all
docker compose down

# Stop and remove volumes (DESTROYS DATA)
docker compose down -v
```

## Backup

SurrealDB backups run automatically every 24 hours, keeping the last 7 daily exports.

```bash
# View backup logs
docker compose logs surrealdb-backup

# Manual backup
docker compose exec surrealdb surreal export \
  --conn http://localhost:8000 \
  --user root --pass YOUR_PASSWORD \
  --ns ami \
  /data/manual_backup.surql
```

## Updating

```bash
git pull
docker compose up -d --build cloud-backend
```
