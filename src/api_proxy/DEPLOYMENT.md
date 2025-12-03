# API Proxy Deployment Guide

Complete guide for deploying API Proxy with Caddy (Auto HTTPS) using Docker Compose.

## Prerequisites

- Docker and Docker Compose installed
- A domain name pointing to your server (e.g., `api.yourdomain.com`)
- Server with ports 80 and 443 open

## Quick Start

### 1. Clone and Navigate

```bash
cd /path/to/Ami/src/api_proxy
```

### 2. Generate Security Keys

```bash
# Generate JWT secret and encryption key
python -m src.api_proxy.setup generate-keys

# Output example:
# ENCRYPTION_KEY=abc123...xyz789
# JWT_SECRET=def456...uvw012
# ADMIN_PASSWORD=ghi789...rst345
```

### 3. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit with your values
nano .env
```

**Required changes in `.env`:**

```bash
# Your actual domain
DOMAIN=api.yourdomain.com

# Your email for SSL certificate notifications
ACME_EMAIL=your-email@example.com

# Paste generated keys from step 2
JWT_SECRET=<generated-jwt-secret>
ENCRYPTION_KEY=<generated-encryption-key>
ADMIN_PASSWORD=<generated-admin-password>

# Your Anthropic API key
ANTHROPIC_API_KEY=sk-ant-xxxxx

# Strong database password
DB_PASSWORD=your-strong-db-password
```

### 4. DNS Configuration

**Point your domain to server IP:**

```
A Record: api.yourdomain.com → Your.Server.IP.Address
```

Verify DNS propagation:
```bash
dig api.yourdomain.com
# or
nslookup api.yourdomain.com
```

### 5. Deploy

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Check status
docker-compose ps
```

### 6. Verify Deployment

```bash
# Wait ~30 seconds for SSL certificate
# Then test HTTPS endpoint
curl https://api.yourdomain.com/health

# Expected output:
# {
#   "status": "healthy",
#   "service": "API Proxy",
#   "version": "1.0.0",
#   ...
# }
```

### 7. Initialize Admin User

```bash
# Create admin user (using credentials from .env)
docker-compose exec api-proxy python -m src.api_proxy.setup create-admin
```

## 🎉 Done!

Your API Proxy is now running with:
- ✅ Auto HTTPS (Let's Encrypt)
- ✅ Auto certificate renewal
- ✅ HTTP → HTTPS redirect
- ✅ PostgreSQL database
- ✅ Secure API key storage

## Usage

### Register a New User

```bash
curl -X POST https://api.yourdomain.com/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "SecurePassword123!"
  }'

# Save the returned API key!
# {
#   "success": true,
#   "api_key": "ami_abc123def456...",
#   ...
# }
```

### Use LLM API (Anthropic-compatible)

```bash
curl -X POST https://api.yourdomain.com/v1/messages \
  -H "x-api-key: ami_abc123def456..." \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5-20250929",
    "max_tokens": 1024,
    "messages": [
      {"role": "user", "content": "Hello, Claude!"}
    ]
  }'
```

### Access Admin Dashboard

Open in browser:
```
https://api.yourdomain.com/admin/admin.html
```

Login with admin credentials from `.env`.

## Management Commands

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f caddy
docker-compose logs -f api-proxy
docker-compose logs -f postgres
```

### Restart Services

```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart api-proxy
```

### Update Configuration

```bash
# Edit Caddyfile or docker-compose.yml
nano Caddyfile

# Reload Caddy configuration (zero downtime)
docker-compose exec caddy caddy reload --config /etc/caddy/Caddyfile

# Or restart all services
docker-compose restart
```

### Database Backup

```bash
# Backup PostgreSQL database
docker-compose exec postgres pg_dump -U ami_user ami_proxy > backup_$(date +%Y%m%d).sql

# Restore from backup
cat backup_20250101.sql | docker-compose exec -T postgres psql -U ami_user ami_proxy
```

### Stop Services

```bash
# Stop but keep data
docker-compose down

# Stop and remove all data (DANGEROUS!)
docker-compose down -v
```

## SSL Certificate Management

### Certificate Auto-Renewal

Caddy automatically renews certificates 30 days before expiration. No action needed!

### View Certificate Status

```bash
# Check certificate expiration
echo | openssl s_client -servername api.yourdomain.com -connect api.yourdomain.com:443 2>/dev/null | openssl x509 -noout -dates

# View Caddy certificate storage
docker-compose exec caddy ls -la /data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/
```

### Force Certificate Renewal (if needed)

```bash
# Delete certificate to force renewal
docker-compose exec caddy rm -rf /data/caddy/certificates/
docker-compose restart caddy
```

## Monitoring

### Health Checks

```bash
# API Proxy health
curl https://api.yourdomain.com/health

# Check all container health
docker-compose ps
```

### Resource Usage

```bash
# CPU and memory usage
docker stats

# Disk usage
docker system df
```

## Troubleshooting

### Certificate Not Issuing

**Problem:** Caddy fails to get SSL certificate

**Solutions:**

1. **Check DNS:** Ensure domain points to server IP
   ```bash
   dig api.yourdomain.com
   ```

2. **Check ports:** Ports 80 and 443 must be accessible
   ```bash
   sudo netstat -tlnp | grep -E ':(80|443)'
   ```

3. **Check logs:**
   ```bash
   docker-compose logs caddy | grep -i error
   ```

4. **Use staging environment first:**
   ```caddy
   # In Caddyfile, add:
   {
       acme_ca https://acme-staging-v02.api.letsencrypt.org/directory
   }
   ```

### Database Connection Errors

```bash
# Check PostgreSQL status
docker-compose exec postgres pg_isready -U ami_user

# View database logs
docker-compose logs postgres

# Restart database
docker-compose restart postgres
```

### API Proxy Not Starting

```bash
# View detailed logs
docker-compose logs api-proxy

# Check environment variables
docker-compose exec api-proxy env | grep API_PROXY

# Rebuild container
docker-compose build --no-cache api-proxy
docker-compose up -d api-proxy
```

## Security Checklist

Before going to production:

- [ ] Changed all default passwords in `.env`
- [ ] Generated strong JWT_SECRET and ENCRYPTION_KEY
- [ ] Set strong DB_PASSWORD
- [ ] Set strong ADMIN_PASSWORD
- [ ] Added valid ANTHROPIC_API_KEY
- [ ] DNS correctly points to server
- [ ] Firewall allows ports 80 and 443
- [ ] Used a real domain (not example.com)
- [ ] HTTPS is working (green lock in browser)
- [ ] Backed up `.env` file securely
- [ ] Enabled database backups

## Production Recommendations

### 1. Regular Backups

```bash
# Add to crontab
0 2 * * * cd /path/to/api_proxy && docker-compose exec postgres pg_dump -U ami_user ami_proxy > /backups/ami_proxy_$(date +\%Y\%m\%d).sql
```

### 2. Log Rotation

Logs are automatically rotated by Caddy (100MB max, keep 10 files).

### 3. Monitoring

Consider adding:
- Uptime monitoring (e.g., UptimeRobot)
- Error tracking (e.g., Sentry)
- Metrics (e.g., Prometheus + Grafana)

### 4. Firewall

```bash
# Allow only necessary ports
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

### 5. Rate Limiting

For DDoS protection, consider adding Cloudflare in front of Caddy.

## Support

For issues, check:
- API Proxy logs: `docker-compose logs api-proxy`
- Caddy logs: `docker-compose logs caddy`
- Database logs: `docker-compose logs postgres`

## License

See main project LICENSE file.
