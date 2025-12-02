# API Proxy Microservice

User management and LLM API proxy service for Ami platform.

## Features

- User registration and authentication
- API Key generation and management
- LLM API request forwarding (Anthropic Claude)
- Token usage statistics tracking
- Workflow execution quota management
- Admin dashboard

## Architecture

```
Desktop App / Cloud Backend
  ↓ (X-API-Key: ami_xxx)
API Proxy
  - Validate user API Key
  - Track token usage
  - Forward to Anthropic
  ↓ (X-API-Key: sk-ant-real-key)
Anthropic API
```

## Setup

### 1. Install Dependencies

```bash
cd src/api_proxy
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and fill in your values
```

### 3. Setup Database

```bash
# Create PostgreSQL database
createdb ami_proxy

# Run migrations
alembic upgrade head
```

### 4. Run Server

```bash
# Development
uvicorn main:app --reload --host 0.0.0.0 --port 8080

# Production
uvicorn main:app --host 0.0.0.0 --port 8080 --workers 4
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

Edit `config.yaml` to configure:
- Server settings
- Database connection
- Security settings (JWT, encryption)
- LLM API keys
- Quota limits

## Development

### Run Tests

```bash
pytest tests/ -v
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Security

- API Keys are encrypted with Fernet before storage
- Passwords are hashed with bcrypt (12 rounds)
- JWT tokens for session management
- HTTPS required for production

## Monitoring

Access admin dashboard at: `http://localhost:8080/admin/`

Default admin credentials:
- Username: admin
- Password: (set in ADMIN_PASSWORD env var)
