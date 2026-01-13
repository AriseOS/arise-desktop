#!/bin/bash

# Cloud Backend Startup Script
# Usage:
#   ./start_cloud_backend.sh           # Start Cloud Backend only
#   ./start_cloud_backend.sh --with-logging  # Start with Loki + Grafana

SCRIPT_DIR="$(dirname "$0")"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "☁️  Starting Cloud Backend"
echo "=========================================="
echo ""

# Check for --with-logging flag
WITH_LOGGING=false
for arg in "$@"; do
    if [ "$arg" == "--with-logging" ]; then
        WITH_LOGGING=true
    fi
done

# Log file path (must match config: ~/ami-server/logs/cloud-backend.log)
LOG_DIR="$HOME/ami-server/logs"

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

echo "📍 Location: src/cloud_backend"
echo "🔌 Port: 9000"
if [ "$WITH_LOGGING" = true ]; then
    echo "📊 Logging: Loki + Grafana enabled"
    echo "📁 Logs: $LOG_DIR/cloud-backend.log"
fi
echo ""

python main.py
