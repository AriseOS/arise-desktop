#!/bin/bash
# Start HTTP daemon

echo "Starting App Backend HTTP Daemon..."
echo ""
echo "API will be available at: http://127.0.0.1:8765"
echo "API docs: http://127.0.0.1:8765/docs"
echo ""

python src/app_backend/daemon.py
