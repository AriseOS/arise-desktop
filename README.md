# Ami - AI-Powered Workflow Automation

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Building AI agents that learn from your actions and automate complex workflows.**

Ami allows you to record browser operations, describe tasks in natural language, and let AI automatically generate executable workflows. No programming required — just demonstrate once, and let AI handle the repetition.

> **From manual operations to automated workflows in minutes.**

## Architecture

```
┌─────────────┐       ┌──────────────────────────────────┐       ┌────────────┐
│ ami-desktop  │──────▶│   Cloud Backend (FastAPI :9090)   │──────▶│  SurrealDB  │
│ (Electron +  │       │                                  │       │  (Memory)   │
│  TS Daemon)  │       │  Auth ─▶ sub2api (users, keys)   │       └────────────┘
└─────────────┘       │  Memory (learn, plan, query)     │
                      │  Embedding & Rerank (server-side)│
                      └──────────────────────────────────┘
```

**This repo** = Cloud Backend + shared modules (`src/common/`).

The desktop app lives in a separate repository: [ami-desktop](https://github.com/AriseOS/ami-desktop).

### Key Components

| Path | Description |
|------|-------------|
| `src/cloud_backend/` | FastAPI server — Memory-as-a-Service + Auth proxy |
| `src/common/memory/` | Memory system (SurrealDB graph store) |
| `src/common/llm/` | LLM provider abstraction (Anthropic, OpenAI) |
| `web/` | Vue 3 + TypeScript management frontend |
| `deploy/` | Docker Compose, Caddy, SurrealDB configs |

## Quick Start (Development)

### Prerequisites

- **Python 3.12+**
- **SurrealDB** (via Docker or native)
- **Sub2API** deployed and accessible (user auth & API key management)

### 1. Clone and install

```bash
git clone https://github.com/AriseOS/Ami.git
cd Ami
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[cloud,memory]"
```

### 2. Configure environment

```bash
cd src/cloud_backend
cp .env.example .env
```

Edit `.env` and fill in values:

```bash
# ---- REQUIRED ----

# Cloud Backend JWT signing secret (独立于 sub2api，不需要一致)
# Cloud Backend 自行签发 JWT，sub2api 的 JWT 会被加密嵌入 (s2a claim)
# Generate: python -c "import secrets; print(secrets.token_urlsafe(32))"
JWT_SECRET_KEY=<your-random-secret>

# Sub2API admin API key (用于服务端调用 sub2api Admin API)
# 从 sub2api 管理后台获取，对应 x-api-key header
SUB2API_ADMIN_API_KEY=<your-sub2api-admin-key>

# Embedding 向量化服务 API key (服务端统一使用，不走 sub2api)
# 例如 SiliconFlow、OpenAI 或其他 OpenAI 兼容 API
EMBEDDING_API_KEY=<your-embedding-api-key>

# ---- OPTIONAL ----

# Rerank 重排序服务 API key (留空则禁用 rerank)
# RERANK_API_KEY=<your-rerank-api-key>
```

Then edit `config/cloud-backend.yaml`:

```yaml
llm:
  # Set to your sub2api address (LLM requests are proxied through sub2api for per-user token tracking)
  #   Development: http://localhost:8080
  #   Production:  https://llm.yourdomain.com
  proxy_url: "http://localhost:8080"
```

> **Note**: `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` are NOT needed. All LLM calls go through sub2api which manages per-user API keys. Only `EMBEDDING_API_KEY` is needed server-side because embedding providers don't go through sub2api.

### 3. Start SurrealDB

```bash
# Option A: Docker
cd deploy/surrealdb && docker compose up -d

# Option B: Use the startup script flag
./scripts/start_cloud_backend.sh --with-db
```

### 4. Start the Cloud Backend

```bash
./scripts/start_cloud_backend.sh
# Cloud Backend starts on port 9090
# API docs: http://localhost:9090/docs
# Health check: http://localhost:9090/health
```

## Production Deployment (Docker Compose)

See [deploy/production/README.md](deploy/production/README.md) for the full Docker Compose setup with SurrealDB and automated backups.

```bash
cd deploy/production
cp .env.example .env && nano .env
docker compose up -d
```

## How It Works

```
User performs task  ──▶  Memory Engine learns  ──▶  Extracts reusable Intents  ──▶  Stores in Graph
                                                                                         │
User requests task  ◀──  Execution Engine runs  ◀──  Planning Engine plans     ◀──  Retrieves Intents
                                                                                         │
                                                              System evolves with each task
```

## Documentation

- **[CLAUDE.md](./CLAUDE.md)** - AI development guide and project conventions
- **CONTEXT.md files** - Fractal documentation in each source directory

## License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.
