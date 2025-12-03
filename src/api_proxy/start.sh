#!/bin/bash
# Quick start script for API Proxy with Caddy

set -e

echo "🚀 API Proxy Deployment Script"
echo "================================"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo ""
    echo "Please create .env file from .env.example:"
    echo "  cp .env.example .env"
    echo "  nano .env"
    echo ""
    echo "Then generate security keys:"
    echo "  python -m src.api_proxy.setup generate-keys"
    exit 1
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running!"
    echo "Please start Docker and try again."
    exit 1
fi

# Load environment variables
export $(cat .env | grep -v '^#' | xargs)

# Validate required variables
REQUIRED_VARS=("DOMAIN" "JWT_SECRET" "ENCRYPTION_KEY" "ANTHROPIC_API_KEY")
MISSING_VARS=()

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    echo "❌ Missing required environment variables:"
    printf '   - %s\n' "${MISSING_VARS[@]}"
    echo ""
    echo "Please edit .env and set all required variables."
    exit 1
fi

# Check domain configuration
if [[ "$DOMAIN" == *"example.com"* ]]; then
    echo "⚠️  WARNING: Using example domain!"
    echo "   DOMAIN=$DOMAIN"
    echo ""
    echo "For production, set your actual domain in .env"
    echo "Press Ctrl+C to cancel, or Enter to continue..."
    read
fi

echo "✅ Configuration validated"
echo ""
echo "📋 Deployment Summary:"
echo "   Domain: $DOMAIN"
echo "   Admin: ${ADMIN_USERNAME:-admin} <${ADMIN_EMAIL:-admin@ami.com}>"
echo "   Database: PostgreSQL"
echo "   SSL: Auto (Let's Encrypt)"
echo ""

# Build and start services
echo "🔨 Building Docker images..."
docker-compose build

echo ""
echo "🚀 Starting services..."
docker-compose up -d

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check service health
if docker-compose ps | grep -q "unhealthy"; then
    echo "❌ Some services are unhealthy!"
    echo ""
    docker-compose ps
    echo ""
    echo "Check logs with: docker-compose logs"
    exit 1
fi

echo "✅ All services started successfully!"
echo ""

# Initialize admin user
echo "👤 Creating admin user..."
if docker-compose exec -T api-proxy python -m src.api_proxy.setup create-admin 2>/dev/null; then
    echo "✅ Admin user created"
else
    echo "ℹ️  Admin user may already exist"
fi

echo ""
echo "🎉 Deployment Complete!"
echo ""
echo "📍 Your API is available at:"
echo "   https://$DOMAIN"
echo ""
echo "🔍 Health check:"
echo "   https://$DOMAIN/health"
echo ""
echo "🌐 Admin dashboard:"
echo "   https://$DOMAIN/admin/admin.html"
echo ""
echo "📚 API documentation:"
echo "   https://$DOMAIN/docs"
echo ""
echo "📊 View logs:"
echo "   docker-compose logs -f"
echo ""
echo "🛑 Stop services:"
echo "   docker-compose down"
echo ""
