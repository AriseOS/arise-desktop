#!/bin/bash
# Quick start script for Ami Desktop App

echo "🚀 Starting Ami Desktop App..."
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

# Start the app
echo "✅ Starting Tauri app..."
echo ""
npm run tauri dev
