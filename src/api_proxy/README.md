# API Proxy

User management and LLM API proxy microservice for Ami platform.

## Features

- User registration and authentication
- API Key generation and management
- LLM API request forwarding (Anthropic Claude)
- Token usage statistics tracking
- Workflow execution quota management

## Deployment

See: `docs/deployment/api_proxy_deployment.md`

Quick deployment on server:

```bash
# 1. Prepare config
mkdir -p /opt/ami/config
cp src/api_proxy/config/api-proxy.yaml /opt/ami/config/
vim /opt/ami/config/api-proxy.yaml  # Edit encryption_key

# 2. Build image
cd /data/workspace/Ami
./scripts/deploy_api_proxy.sh

# 3. Run container
docker run -d \
    --name ami-api-proxy \
    --restart unless-stopped \
    -p 127.0.0.1:8080:8080 \
    -v /opt/ami/config/api-proxy.yaml:/app/src/api_proxy/config/api-proxy.yaml:ro \
    -v /opt/ami/logs:/root/.ami/logs \
    -v /opt/ami/database:/root/.ami/database \
    ami-api-proxy:latest
```

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - User login
- `GET /api/auth/me` - Get current user info

### LLM Proxy
- `POST /v1/messages` - Anthropic-compatible message endpoint

### Statistics
- `POST /api/stats/workflow-execution` - Report workflow execution
- `GET /api/stats/quota` - Get user quota status

### Admin
- `GET /api/admin/users` - List all users
- `GET /api/admin/users/{user_id}/stats` - Get user statistics

## Configuration

Edit `config/api-proxy.yaml`:
- Database settings (SQLite/PostgreSQL)
- Security (JWT secret, encryption key)
- LLM provider settings
- User quota limits

## Security

- API Keys encrypted with Fernet
- Passwords hashed with bcrypt
- JWT tokens for sessions
- Bind to localhost only (127.0.0.1:8080)
- External access via reverse proxy only
