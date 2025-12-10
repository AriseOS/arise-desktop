#!/bin/bash
# Development script for Ami Desktop App
# Runs daemon from source (not bundled binary) for faster iteration

echo "🚀 Starting Ami Desktop App (Development Mode)..."
echo ""

# Check if we're in the right directory
if [ ! -d "src/clients/desktop_app" ]; then
    echo "❌ Error: Please run this script from the project root directory"
    exit 1
fi

# Start daemon from source in background
echo "🐍 Starting daemon from source..."
cd src/app_backend
python3 daemon.py &
DAEMON_PID=$!
echo "✓ Daemon started (PID: $DAEMON_PID)"
cd ../..

# Wait a bit for daemon to start
sleep 2

# Start frontend
echo "🎨 Starting frontend..."
cd src/clients/desktop_app

# Kill daemon on exit
trap "echo '🛑 Stopping daemon...'; kill $DAEMON_PID 2>/dev/null" EXIT

npm run tauri dev
