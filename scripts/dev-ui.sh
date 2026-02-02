#!/bin/bash
# Development script to run both API and UI

set -e

echo "🚀 Starting Atmosphere Development Environment"
echo ""

# Check if we're in the project root
if [ ! -f "pyproject.toml" ]; then
    echo "❌ Error: Must run from project root"
    exit 1
fi

# Check if UI dependencies are installed
if [ ! -d "ui/node_modules" ]; then
    echo "📦 Installing UI dependencies..."
    cd ui && npm install && cd ..
fi

# Start API server in background
echo "🔧 Starting API server on port 8000..."
python -m atmosphere.api.server &
API_PID=$!

# Wait for API to be ready
sleep 3

# Start UI dev server
echo "🎨 Starting UI dev server on port 11451..."
cd ui
npm run dev

# Cleanup on exit
trap "kill $API_PID" EXIT
