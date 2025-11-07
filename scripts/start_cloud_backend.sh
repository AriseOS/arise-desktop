#!/bin/bash

echo "=========================================="
echo "☁️  Starting Cloud Backend"
echo "=========================================="
echo ""

cd "$(dirname "$0")/../src/cloud_backend"

echo "📍 Location: src/cloud_backend"
echo "🔌 Port: 9000"
echo ""

python main.py
