#!/bin/bash

echo "=========================================="
echo "🧪 Integration Test - Ami System"
echo "=========================================="
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Prerequisites:"
echo "  - App Backend running on localhost:8000"
echo "  - Cloud Backend running on localhost:9000"
echo ""
echo "Tip: Run './scripts/start_both_backends.sh' first"
echo ""

read -p "Press Enter to continue or Ctrl+C to cancel..."

# Run integration test
cd "$PROJECT_ROOT" && python tests/integration/test_integration.py
