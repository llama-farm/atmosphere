#!/bin/bash
# Build the UI for production

set -e

echo "🏗️  Building Atmosphere UI for production..."
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

# Build the UI
echo "⚡ Building..."
cd ui
npm run build

echo ""
echo "✅ Build complete!"
echo "   UI built to: ui/dist/"
echo ""
echo "To serve the UI with the API:"
echo "  python -m atmosphere.api.server"
echo ""
echo "Or preview the build:"
echo "  cd ui && npm run preview"
