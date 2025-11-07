# Cloud Backend Configuration

## Overview

The Cloud Backend uses YAML-based configuration with support for environment variables.

## Configuration File Location

Priority order (highest to lowest):

1. **Environment variable**: `CLOUD_BACKEND_CONFIG`
   ```bash
   export CLOUD_BACKEND_CONFIG=/path/to/config.yaml
   ```

2. **Command line argument**: Pass to CloudConfigService
   ```python
   config = CloudConfigService(config_path="/path/to/config.yaml")
   ```

3. **Default location**: `src/cloud-backend/config/cloud-backend.yaml`

4. **User home**: `~/.ami/cloud-backend.yaml`

5. **System-wide**: `/etc/ami/cloud-backend.yaml`

## Configuration Sections

### Server
```yaml
server:
  host: 0.0.0.0
  port: 9000
  debug: false
  reload: false
```

### Storage
```yaml
storage:
  type: filesystem  # or s3
  base_path: ~/ami-server
```

### Database
```yaml
database:
  type: sqlite  # or postgresql
  sqlite:
    path: ~/ami-server/database/ami.db
```

### LLM
```yaml
llm:
  default_provider: anthropic  # or openai
  anthropic:
    api_key_env: ANTHROPIC_API_KEY
    model: claude-3-5-sonnet-20241022
```

### Workflow Generation
```yaml
workflow_generation:
  save_intermediates: true
  timeout_seconds: 300
  max_retries: 3
```

## Environment Variables

Required environment variables:
- `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` - LLM API key
- `JWT_SECRET_KEY` - JWT signing key (optional for development)

Optional environment variables:
- `CLOUD_BACKEND_CONFIG` - Path to config file
- `PROJECT_ROOT` - Project root directory

## Usage in Code

```python
from core.config_service import CloudConfigService

# Load configuration
config = CloudConfigService()

# Get values with dot notation
port = config.get("server.port")  # Returns 9000
model = config.get("llm.anthropic.model")  # Returns "claude-3-5-sonnet-20241022"

# Get with default
timeout = config.get("workflow_generation.timeout_seconds", 300)

# Get environment variables
api_key = config.get_env("llm.anthropic.api_key_env")  # Returns value of ANTHROPIC_API_KEY

# Get expanded paths
storage_path = config.get_storage_path()  # Returns Path object with ~ expanded
db_path = config.get_db_path()
log_path = config.get_log_path()
```

## Development vs Production

**Development** (default config):
- Debug mode: off
- Auto-reload: off
- Storage: `~/ami-server`
- Database: SQLite

**Production** (customize via config file):
- Debug mode: off
- Auto-reload: off
- Storage: `/var/lib/ami` or S3
- Database: PostgreSQL
- CORS: Restricted origins
- Rate limiting: Enabled

## Example Production Config

```yaml
server:
  host: 0.0.0.0
  port: 443  # Or use reverse proxy
  debug: false

storage:
  type: s3
  s3_bucket: ami-production
  s3_region: us-east-1

database:
  type: postgresql
  postgresql:
    host: db.production.com
    database: ami
    user: ami_user
    password_env: DB_PASSWORD

cors:
  allow_origins:
    - https://app.ami.com
  allow_credentials: true

logging:
  level: WARNING
  file: /var/log/ami/cloud-backend.log
```
