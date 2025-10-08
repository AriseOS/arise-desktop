# Web Backend Configuration

This directory contains configuration files for the AgentCrafter web backend.

## Configuration File

**File**: `backend.yaml`

Copy from the example template to get started:
```bash
cp backend.yaml.example backend.yaml
```

## Configuration Structure

### Project Settings
```yaml
project:
  name: AgentCrafter
  version: 1.0.0
  root: ${PROJECT_ROOT}  # Optional, auto-detected if not set
```

### Database Configuration

**Option 1: Direct Database URL**
```yaml
database:
  url: sqlite:///./agentcrafter_users.db
  # url: postgresql://username:password@localhost/agentcrafter
```

**Option 2: Database File Path (SQLite only)**
```yaml
database:
  path: dbfiles/agentcrafter.db  # Relative to project root
  # path: /absolute/path/to/database.db
```

### Server Configuration
```yaml
server:
  host: 0.0.0.0
  port: 8000
  reload: true  # Enable hot reload in development
```

### Security Configuration
```yaml
security:
  secret_key: your-secret-key-here-change-in-production
  algorithm: HS256
  access_token_expire_minutes: 30
```

### Logging Configuration
```yaml
logging:
  level: INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

## Environment Variable Overrides

You can override any configuration value using environment variables with the `BACKEND_` prefix:

| Config Key | Environment Variable | Example |
|-----------|---------------------|---------|
| `server.port` | `BACKEND_SERVER_PORT` | `BACKEND_SERVER_PORT=9000` |
| `server.host` | `BACKEND_SERVER_HOST` | `BACKEND_SERVER_HOST=127.0.0.1` |
| `database.path` | `BACKEND_DATABASE_PATH` | `BACKEND_DATABASE_PATH=/data/db.sqlite` |
| `security.secret_key` | `BACKEND_SECURITY_SECRET_KEY` | `BACKEND_SECURITY_SECRET_KEY=my-key` |
| `logging.level` | `BACKEND_LOGGING_LEVEL` | `BACKEND_LOGGING_LEVEL=DEBUG` |

## Environment Variables in Config

You can reference environment variables in the YAML file:

```yaml
database:
  path: ${DATABASE_PATH}  # Will use DATABASE_PATH env var

llm:
  openai_api_key: ${OPENAI_API_KEY}
  anthropic_api_key: ${ANTHROPIC_API_KEY}
```

## Configuration Priority

1. **Environment Variables** (highest priority)
2. **YAML Configuration File**
3. **Code Defaults** (lowest priority)

Example:
- If `BACKEND_SERVER_PORT=9000` is set as an environment variable
- And `server.port: 8000` is in `backend.yaml`
- The server will run on port **9000**

## Example Configurations

### Development Configuration
```yaml
server:
  host: 0.0.0.0
  port: 8000
  reload: true

database:
  path: dbfiles/dev.db

security:
  secret_key: dev-secret-key

logging:
  level: DEBUG
```

### Production Configuration
```yaml
server:
  host: 0.0.0.0
  port: 8000
  reload: false

database:
  url: postgresql://user:pass@localhost/agentcrafter

security:
  secret_key: ${SECRET_KEY}  # Load from environment

logging:
  level: INFO
```

## Usage in Code

The configuration is automatically loaded when importing from `config.py`:

```python
from config import get_database_url, get_server_config

# Get specific values
db_url = get_database_url()
server_config = get_server_config()

# Or use the global config object
from config import config
print(config.host)
print(config.port)
```
