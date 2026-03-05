#!/bin/bash
# Quick start script for Arise Desktop App (Electron)

# Parse arguments
USE_LOCAL_CLOUD=false
ARISE_DEBUG_MODE=false
for arg in "$@"; do
    case $arg in
        --local)
            USE_LOCAL_CLOUD=true
            shift
            ;;
        --debug)
            ARISE_DEBUG_MODE=true
            shift
            ;;
    esac
done

echo "🚀 Starting Arise Desktop App..."
if [ "$USE_LOCAL_CLOUD" = true ]; then
    echo "   Mode: Using LOCAL Cloud Backend (http://localhost:9090)"
else
    echo "   Mode: Using REMOTE Cloud Backend"
fi
echo ""

# Resolve project root from script location
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Check if node_modules exists
if [ ! -d "${PROJECT_ROOT}/node_modules" ]; then
    echo "📦 Installing dependencies..."
    cd "${PROJECT_ROOT}"
    npm install
fi

# Check if daemon-ts node_modules exists
if [ ! -d "${PROJECT_ROOT}/daemon-ts/node_modules" ]; then
    echo "📦 Installing daemon-ts dependencies..."
    cd "${PROJECT_ROOT}/daemon-ts"
    npm install
fi

# Start the app in development mode
cd "${PROJECT_ROOT}"

echo "✅ Starting Electron app (Development Mode)..."
echo "   ARISE_DEV_MODE=1 → Using TypeScript daemon (tsx)"

# Build environment variables
ENV_VARS="ARISE_DEV_MODE=1"
if [ "$ARISE_DEBUG_MODE" = true ]; then
    ENV_VARS="$ENV_VARS ARISE_DEBUG=1"
    echo "   Debug Mode: ENABLED"
fi

# Disable proxy for local connections (fix 502 error on ports 8765-8774)
export no_proxy="localhost,127.0.0.1,::1"
export NO_PROXY="localhost,127.0.0.1,::1"

if [ "$USE_LOCAL_CLOUD" = true ]; then
    echo "   APP_BACKEND_CLOUD_API_URL=http://localhost:9090"
    echo ""
    eval "$ENV_VARS APP_BACKEND_CLOUD_API_URL=http://localhost:9090 npm run electron:dev"
else
    echo ""
    eval "$ENV_VARS npm run electron:dev"
fi
