# API Proxy Quick Start Guide

## Prerequisites

- Python 3.9+
- PostgreSQL (or use SQLite for testing)
- pip or uv

## Setup Steps

### 1. Install Dependencies

```bash
cd src/api_proxy
pip install -r requirements.txt
```

### 2. Generate Security Keys

```bash
python setup.py generate-keys
```

This will output:
```
ENCRYPTION_KEY=xxxxx
JWT_SECRET=yyyyy
ADMIN_PASSWORD=zzzzz
```

### 3. Create .env File

```bash
cp .env.example .env
```

Edit `.env` and add the generated keys plus your Anthropic API key:

```bash
# Database
DB_PASSWORD=your_database_password

# Security
JWT_SECRET=<generated_jwt_secret>
ENCRYPTION_KEY=<generated_encryption_key>

# LLM API Keys
ANTHROPIC_API_KEY=sk-ant-your-real-key-here

# Admin
ADMIN_PASSWORD=<generated_admin_password>
```

### 4. Setup Database

#### Option A: PostgreSQL (Production)

```bash
# Create database
createdb ami_proxy

# Or using psql
psql -U postgres
CREATE DATABASE ami_proxy;
\q

# Initialize tables
python setup.py init-db
```

#### Option B: SQLite (Testing)

Edit `config.yaml`:

```yaml
database:
  host: ""
  port: 0
  database: "./ami_proxy.db"
  user: ""
  password: ""
```

Then:

```bash
python setup.py init-db
```

### 5. Create Admin User

```bash
python setup.py create-admin
```

This will create an admin user and display the API key. **Save this API key!**

### 6. Start Server

```bash
# Development (with auto-reload)
python main.py

# Or using uvicorn directly
uvicorn main:app --reload --host 0.0.0.0 --port 8080

# Production
uvicorn main:app --host 0.0.0.0 --port 8080 --workers 4
```

### 7. Test the API

Open your browser: http://localhost:8080/docs

Or use curl:

```bash
# Health check
curl http://localhost:8080/health

# Register a user
curl -X POST http://localhost:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "SecurePassword123!"
  }'

# Response will include your API key:
# {
#   "success": true,
#   "user": {...},
#   "api_key": "ami_xxxxxxxxxxxxx"
# }

# Test LLM proxy (use your API key)
curl -X POST http://localhost:8080/v1/messages \
  -H "x-api-key: ami_xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "max_tokens": 1024,
    "messages": [
      {"role": "user", "content": "Hello, Claude!"}
    ]
  }'
```

## Configuration

### Custom LLM Backend

Edit `config.yaml` to point to a custom backend:

```yaml
llm:
  default_provider: "anthropic"

  anthropic:
    api_key: "${ANTHROPIC_API_KEY}"
    base_url: "http://your-custom-backend.com"  # <-- Change this
```

### Quota Settings

Edit `config.yaml`:

```yaml
quota:
  trial_duration_days: 30
  trial_workflow_limit: 100
  overage_percentage: 20
  warning_thresholds:
    - 80
    - 100
    - 120
```

## Troubleshooting

### Database Connection Error

```
sqlalchemy.exc.OperationalError: could not connect to server
```

**Solution**: Make sure PostgreSQL is running and credentials are correct in `.env`

### Import Error

```
ModuleNotFoundError: No module named 'src'
```

**Solution**: Run from project root directory, not from `src/api_proxy/`

```bash
# Wrong
cd src/api_proxy
python main.py

# Correct
cd /path/to/Ami
python -m src.api_proxy.main
```

### Encryption Key Error

```
ValueError: Encryption key must be 32 url-safe base64-encoded bytes
```

**Solution**: Generate a proper Fernet key using `python setup.py generate-keys`

## Docker Deployment (Optional)

```bash
cd src/api_proxy

# Build image
docker build -t ami-api-proxy .

# Run container
docker run -d \
  --name ami-api-proxy \
  -p 8080:8080 \
  --env-file .env \
  ami-api-proxy
```

## Next Steps

1. Integrate with Cloud Backend (modify LLM provider to use this proxy)
2. Integrate with App Backend (send workflow execution reports)
3. Integrate with Desktop App (add login UI)

See `docs/requirements/user_management_and_api_proxy.md` for full architecture.
