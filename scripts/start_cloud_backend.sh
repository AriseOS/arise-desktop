#!/bin/bash

# Cloud Backend Startup Script
# Usage:
#   ./start_cloud_backend.sh                          # Start Cloud Backend only
#   ./start_cloud_backend.sh --with-db                # Start with SurrealDB
#   ./start_cloud_backend.sh --with-logging           # Start with Loki + Grafana
#   ./start_cloud_backend.sh --with-db --with-logging # Start with both

SCRIPT_DIR="$(dirname "$0")"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "☁️  Starting Cloud Backend"
echo "=========================================="
echo ""

# Check for flags
WITH_LOGGING=false
WITH_DB=false
for arg in "$@"; do
    if [ "$arg" == "--with-logging" ]; then
        WITH_LOGGING=true
    fi
    if [ "$arg" == "--with-db" ]; then
        WITH_DB=true
    fi
done

# Log file path (must match config: ~/ami-server/logs/cloud-backend.log)
LOG_DIR="$HOME/ami-server/logs"

# Start SurrealDB if requested
if [ "$WITH_DB" = true ]; then
    echo "🗄️  Starting SurrealDB..."

    # Check if Docker is running
    if ! docker info > /dev/null 2>&1; then
        echo "❌ Docker is not running. Please start Docker first."
        exit 1
    fi

    cd "$PROJECT_ROOT/deploy/surrealdb"
    docker compose up -d

    if [ $? -eq 0 ]; then
        echo "✅ SurrealDB started successfully"
        echo "   - HTTP API:      http://localhost:8000"
        echo "   - WebSocket RPC: ws://localhost:8000/rpc"
    else
        echo "❌ Failed to start SurrealDB, aborting."
        exit 1
    fi
    echo ""
fi

# Start Loki + Grafana if requested
if [ "$WITH_LOGGING" = true ]; then
    echo "📊 Starting Loki + Grafana logging stack..."

    # Check if Docker is running
    if ! docker info > /dev/null 2>&1; then
        echo "❌ Docker is not running. Please start Docker first."
        exit 1
    fi

    # Create log directory for Cloud Backend to write to
    mkdir -p "$LOG_DIR"
    echo "📁 Log directory: $LOG_DIR"

    cd "$PROJECT_ROOT/deploy/logging"

    # Export AMI_LOG_DIR for docker-compose
    export AMI_LOG_DIR="$LOG_DIR"

    # Start logging stack (use new docker compose v2 syntax)
    docker compose up -d

    if [ $? -eq 0 ]; then
        echo "✅ Logging stack started successfully"
        echo "   - Grafana: http://localhost:3000 (admin/admin)"
        echo "   - Loki:    http://localhost:3100"
    else
        echo "⚠️  Failed to start logging stack, continuing without it..."
    fi
    echo ""
fi

# Start Cloud Backend
cd "$PROJECT_ROOT/src/cloud_backend"

# Load .env if present
if [ -f .env ]; then
    set -a
    source .env
    set +a
    echo "🔑 Loaded environment from .env"
fi

# Activate venv
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
    echo "🐍 Activated venv: $(python --version)"
else
    echo "⚠️  No .venv found at $PROJECT_ROOT/.venv — using system python"
fi

echo "📍 Location: src/cloud_backend"
echo "🔌 Port: 9000"
if [ "$WITH_DB" = true ]; then
    echo "🗄️  Database: SurrealDB (ws://localhost:8000/rpc)"
fi
if [ "$WITH_LOGGING" = true ]; then
    echo "📊 Logging: Loki + Grafana enabled"
    echo "📁 Logs: $LOG_DIR/cloud-backend.log"
fi
echo ""

python main.py
