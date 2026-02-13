#!/bin/bash
# Quick start script for Ami Desktop App (Electron)

# Parse arguments
USE_LOCAL_CLOUD=false
AMI_DEBUG_MODE=false
for arg in "$@"; do
    case $arg in
        --local)
            USE_LOCAL_CLOUD=true
            shift
            ;;
        --debug)
            AMI_DEBUG_MODE=true
            shift
            ;;
    esac
done

echo "🚀 Starting Ami Desktop App..."
if [ "$USE_LOCAL_CLOUD" = true ]; then
    echo "   Mode: Using LOCAL Cloud Backend (http://localhost:9090)"
else
    echo "   Mode: Using REMOTE Cloud Backend"
fi
echo ""

# Check if we're in the right directory
if [ ! -d "src/clients/desktop_app" ]; then
    echo "❌ Error: Please run this script from the project root directory"
    echo "   Current directory: $(pwd)"
    exit 1
fi

# Check if node_modules exists
if [ ! -d "src/clients/desktop_app/node_modules" ]; then
    echo "📦 Installing dependencies..."
    cd src/clients/desktop_app
    npm install
    cd ../../..
fi

# Start the app in development mode
cd src/clients/desktop_app

echo "✅ Starting Electron app (Development Mode)..."
echo "   AMI_DEV_MODE=1 → Using Python source code"

# Build environment variables
ENV_VARS="AMI_DEV_MODE=1"
if [ "$AMI_DEBUG_MODE" = true ]; then
    ENV_VARS="$ENV_VARS AMI_DEBUG=1"
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
