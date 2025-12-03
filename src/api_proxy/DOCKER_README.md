# API Proxy - Docker Deployment

One-command deployment with Caddy (Auto HTTPS)

## 🚀 Quick Start (3 Steps)

### 1. Configure Environment

```bash
# Copy example file
cp .env.example .env

# Generate security keys
python -m src.api_proxy.setup generate-keys

# Edit .env with generated keys
nano .env
```

**Minimum required in `.env`:**
```bash
DOMAIN=api.yourdomain.com
ACME_EMAIL=your-email@example.com
JWT_SECRET=<generated>
ENCRYPTION_KEY=<generated>
ADMIN_PASSWORD=<generated>
ANTHROPIC_API_KEY=sk-ant-xxxxx
```

### 2. Configure DNS

Point your domain to server:
```
A Record: api.yourdomain.com → Your.Server.IP
```

### 3. Deploy

```bash
./start.sh
```

That's it! 🎉

## 📁 Files Overview

```
src/api_proxy/
├── docker-compose.yml   # Multi-service orchestration
├── Dockerfile           # API Proxy container
├── Caddyfile           # Reverse proxy config (auto HTTPS)
├── .env.example        # Environment template
├── start.sh            # One-command deployment
└── DEPLOYMENT.md       # Detailed documentation
```

## 🔧 Architecture

```
Internet
    ↓
Caddy (Port 80/443)
    ↓ HTTPS with Let's Encrypt
    ↓ Auto certificate renewal
    ↓
API Proxy (Port 8080)
    ↓
PostgreSQL Database
```

## 📋 Services

| Service | Container | Port | Description |
|---------|-----------|------|-------------|
| **Caddy** | ami-caddy | 80, 443 | Reverse proxy, Auto HTTPS |
| **API Proxy** | ami-api-proxy | 8080 (internal) | Main application |
| **PostgreSQL** | ami-postgres | 5432 (internal) | Database |

## 🌐 Endpoints

After deployment:

- **API Base**: `https://api.yourdomain.com`
- **Health Check**: `https://api.yourdomain.com/health`
- **Admin Dashboard**: `https://api.yourdomain.com/admin/admin.html`
- **API Docs**: `https://api.yourdomain.com/docs`

## 🛠️ Management

### View Logs
```bash
docker-compose logs -f
```

### Restart Services
```bash
docker-compose restart
```

### Stop All
```bash
docker-compose down
```

### Rebuild
```bash
docker-compose build --no-cache
docker-compose up -d
```

## 🔐 Security Features

✅ **Auto HTTPS** - Let's Encrypt certificates  
✅ **Auto Renewal** - Certificates renewed automatically  
✅ **Secure Headers** - HSTS, CSP, XSS protection  
✅ **Encrypted Storage** - API keys encrypted in database  
✅ **Password Hashing** - bcrypt with salt  
✅ **JWT Tokens** - Secure session management  

## 📊 Monitoring

### Check Service Status
```bash
docker-compose ps
```

### Check Certificate Expiration
```bash
echo | openssl s_client -servername api.yourdomain.com \
  -connect api.yourdomain.com:443 2>/dev/null | \
  openssl x509 -noout -dates
```

### Resource Usage
```bash
docker stats
```

## 🆘 Troubleshooting

### SSL Certificate Issues

```bash
# Check Caddy logs
docker-compose logs caddy | grep -i error

# Verify DNS
dig api.yourdomain.com

# Check ports
sudo netstat -tlnp | grep -E ':(80|443)'
```

### API Proxy Not Responding

```bash
# Check container health
docker-compose ps

# View logs
docker-compose logs api-proxy

# Restart service
docker-compose restart api-proxy
```

### Database Connection Failed

```bash
# Check PostgreSQL
docker-compose exec postgres pg_isready -U ami_user

# View logs
docker-compose logs postgres
```

## 🔄 Updates

### Update API Proxy Code

```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose build api-proxy
docker-compose up -d api-proxy
```

### Update Configuration

```bash
# Edit Caddyfile or docker-compose.yml
nano Caddyfile

# Reload (zero downtime)
docker-compose exec caddy caddy reload --config /etc/caddy/Caddyfile
```

## 📦 Backup

### Database Backup

```bash
# Create backup
docker-compose exec postgres pg_dump -U ami_user ami_proxy > backup.sql

# Restore
cat backup.sql | docker-compose exec -T postgres psql -U ami_user ami_proxy
```

### Volume Backup

```bash
# Backup all volumes
docker run --rm -v api_proxy_postgres_data:/data \
  -v $(pwd):/backup alpine tar czf /backup/postgres_backup.tar.gz /data
```

## 🌍 Production Checklist

Before going live:

- [ ] Set real domain in `.env` (not example.com)
- [ ] Generate strong security keys
- [ ] Change all default passwords
- [ ] Configure DNS A record
- [ ] Open firewall ports 80, 443
- [ ] Test HTTPS is working
- [ ] Set up database backups
- [ ] Configure monitoring/alerts
- [ ] Review security headers in Caddyfile

## 📚 Documentation

For detailed documentation, see:
- [DEPLOYMENT.md](./DEPLOYMENT.md) - Complete deployment guide
- [QUICKSTART.md](./QUICKSTART.md) - API usage examples
- [IMPLEMENTATION_SUMMARY.md](./IMPLEMENTATION_SUMMARY.md) - Architecture details

## 🆘 Support

- Check logs: `docker-compose logs`
- Issues: File a GitHub issue
- Documentation: See DEPLOYMENT.md

## 📄 License

See main project LICENSE.
