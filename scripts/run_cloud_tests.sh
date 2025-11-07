#!/bin/bash

echo "=========================================="
echo "🧪 Cloud Backend Tests"
echo "=========================================="
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Check API Key
if [ -z "$ANTHROPIC_API_KEY" ] && [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ Error: No LLM API key found!"
    echo ""
    echo "Please set one of:"
    echo "  export ANTHROPIC_API_KEY=your_key"
    echo "  export OPENAI_API_KEY=your_key"
    echo ""
    exit 1
fi

echo "✅ LLM API Key found"
echo ""

# Check if Cloud Backend is running
echo "📡 Checking if Cloud Backend is running..."
if curl -s http://localhost:9000/health > /dev/null 2>&1; then
    echo "✅ Cloud Backend is running"
    STARTED_BACKEND=false
else
    echo "⚠️  Cloud Backend not running"
    echo "   Starting Cloud Backend..."
    cd "$PROJECT_ROOT/src/cloud_backend" && python main.py &
    BACKEND_PID=$!
    echo "   PID: $BACKEND_PID"
    echo "   Waiting 5 seconds for startup..."
    sleep 5
    STARTED_BACKEND=true
fi

echo ""
echo "🧪 Running tests..."
echo ""

# Run tests
cd "$PROJECT_ROOT/tests/cloud_backend"
pytest -v -s

TEST_EXIT_CODE=$?

# Stop Backend (if we started it)
if [ "$STARTED_BACKEND" = true ]; then
    echo ""
    echo "🛑 Stopping Cloud Backend..."
    kill $BACKEND_PID 2>/dev/null
fi

echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "=========================================="
    echo "✅ All Tests Passed!"
    echo "=========================================="
else
    echo "=========================================="
    echo "❌ Some Tests Failed!"
    echo "=========================================="
fi

exit $TEST_EXIT_CODE
