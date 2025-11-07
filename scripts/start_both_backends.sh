#!/bin/bash

echo "=========================================="
echo "🚀 Starting Ami Backends"
echo "=========================================="
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Start Cloud Backend
echo "☁️  Starting Cloud Backend (port 9000)..."
cd "$PROJECT_ROOT/src/cloud_backend" && python main.py &
CLOUD_PID=$!
echo "   PID: $CLOUD_PID"

sleep 2

# Start Local Backend
echo ""
echo "💻 Starting Local Backend (port 8000)..."
cd "$PROJECT_ROOT/src/local_backend" && python main.py &
LOCAL_PID=$!
echo "   PID: $LOCAL_PID"

sleep 3

echo ""
echo "=========================================="
echo "✅ Both backends started!"
echo "=========================================="
echo ""
echo "Cloud Backend: http://localhost:9000/docs"
echo "Local Backend: http://localhost:8000/docs"
echo ""
echo "To stop: kill $CLOUD_PID $LOCAL_PID"
echo ""
