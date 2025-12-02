#!/bin/bash

# API Proxy Startup Script
# Starts the API Proxy server on port 8080

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "============================================"
echo "Starting API Proxy Server"
echo "============================================"
echo "Port: 8080"
echo "Host: 0.0.0.0"
echo "Directory: $PROJECT_ROOT"
echo "============================================"

# Set PYTHONPATH to project root
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Start uvicorn server with proper module path
python -m uvicorn src.api_proxy.main:app --host 0.0.0.0 --port 8080 --reload
