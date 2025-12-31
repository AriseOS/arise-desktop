#!/bin/bash
# Quick start script for Ami Desktop App

# Parse arguments
USE_LOCAL_CLOUD=false
for arg in "$@"; do
    case $arg in
        --local)
            USE_LOCAL_CLOUD=true
            shift
            ;;
    esac
done

echo "🚀 Starting Ami Desktop App..."
if [ "$USE_LOCAL_CLOUD" = true ]; then
    echo "   Mode: Using LOCAL Cloud Backend (http://localhost:9000)"
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

    # Install Tauri CLI
    echo "📦 Installing Tauri CLI..."
    npm install --save-dev @tauri-apps/cli

    cd ../../..
fi

# Check if Tauri CLI is installed
cd src/clients/desktop_app
if ! npm list @tauri-apps/cli > /dev/null 2>&1; then
    echo "📦 Installing Tauri CLI..."
    npm install --save-dev @tauri-apps/cli
fi

# Start the app in development mode
echo "✅ Starting Tauri app (Development Mode)..."
echo "   AMI_DEV_MODE=1 → Using Python source code"

if [ "$USE_LOCAL_CLOUD" = true ]; then
    echo "   APP_BACKEND_CLOUD_API_URL=http://localhost:9000"
    echo ""
    AMI_DEV_MODE=1 APP_BACKEND_CLOUD_API_URL=http://localhost:9000 npm run tauri dev
else
    echo ""
    AMI_DEV_MODE=1 npm run tauri dev
fi
