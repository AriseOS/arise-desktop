#!/bin/bash

echo "=========================================="
echo "💻 Starting Local Backend"
echo "=========================================="
echo ""

cd "$(dirname "$0")/../src/local_backend"

echo "📍 Location: src/local_backend"
echo "🔌 Port: 8000"
echo ""

python main.py
