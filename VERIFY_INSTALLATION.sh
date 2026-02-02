#!/bin/bash

echo "╔════════════════════════════════════════════════════════════╗"
echo "║  ATMOSPHERE EXECUTION LAYER - VERIFICATION SCRIPT          ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

ERRORS=0

# Check Python files
echo "📦 Checking Backend Files..."

if [ -f "atmosphere/api/routes.py" ]; then
    if grep -q "websocket_endpoint" "atmosphere/api/routes.py"; then
        echo "  ✅ WebSocket endpoint found"
    else
        echo "  ❌ WebSocket endpoint missing"
        ERRORS=$((ERRORS + 1))
    fi
    
    if grep -q "test_integration" "atmosphere/api/routes.py"; then
        echo "  ✅ Test endpoint found"
    else
        echo "  ❌ Test endpoint missing"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "  ❌ routes.py not found"
    ERRORS=$((ERRORS + 1))
fi

if [ -f "atmosphere/discovery/llamafarm.py" ]; then
    if grep -q "port: int = 14345" "atmosphere/discovery/llamafarm.py"; then
        echo "  ✅ LlamaFarm port 14345"
    else
        echo "  ❌ LlamaFarm port not 14345"
        ERRORS=$((ERRORS + 1))
    fi
    
    if grep -q "async def generate" "atmosphere/discovery/llamafarm.py"; then
        echo "  ✅ generate() method found"
    else
        echo "  ❌ generate() method missing"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "  ❌ llamafarm.py not found"
    ERRORS=$((ERRORS + 1))
fi

if [ -f "atmosphere/router/executor.py" ]; then
    if grep -q "if self._llamafarm:" "atmosphere/router/executor.py"; then
        echo "  ✅ Executor uses LlamaFarm"
    else
        echo "  ❌ Executor doesn't use LlamaFarm"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "  ❌ executor.py not found"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "🎨 Checking Frontend Files..."

if [ -f "ui/src/components/IntegrationPanel.jsx" ]; then
    echo "  ✅ IntegrationPanel.jsx exists"
    
    if grep -q "handleTest" "ui/src/components/IntegrationPanel.jsx"; then
        echo "  ✅ Test functionality found"
    else
        echo "  ❌ Test functionality missing"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "  ❌ IntegrationPanel.jsx not found"
    ERRORS=$((ERRORS + 1))
fi

if [ -f "ui/src/components/IntegrationPanel.css" ]; then
    echo "  ✅ IntegrationPanel.css exists"
    
    if grep -q "test-result" "ui/src/components/IntegrationPanel.css"; then
        echo "  ✅ Test styling found"
    else
        echo "  ❌ Test styling missing"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "  ❌ IntegrationPanel.css not found"
    ERRORS=$((ERRORS + 1))
fi

if [ -f "ui/src/App.jsx" ]; then
    if grep -q "IntegrationPanel" "ui/src/App.jsx"; then
        echo "  ✅ IntegrationPanel imported in App.jsx"
    else
        echo "  ❌ IntegrationPanel not imported"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "  ❌ App.jsx not found"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "📚 Checking Documentation..."

for doc in INTEGRATION_IMPLEMENTATION.md EXECUTION_LAYER.md QUICKSTART_EXECUTION.md CHANGES_SUMMARY.md; do
    if [ -f "$doc" ]; then
        echo "  ✅ $doc exists"
    else
        echo "  ❌ $doc missing"
        ERRORS=$((ERRORS + 1))
    fi
done

echo ""
echo "📦 Checking Dependencies..."

if grep -q "requests>=2.31.0" "requirements.txt"; then
    echo "  ✅ requests dependency added"
else
    echo "  ❌ requests dependency missing"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "═══════════════════════════════════════════════════════════"

if [ $ERRORS -eq 0 ]; then
    echo "✅ ALL CHECKS PASSED!"
    echo ""
    echo "Next steps:"
    echo "  1. pip install -r requirements.txt"
    echo "  2. python3 -m atmosphere start"
    echo "  3. cd ui && npm install && npm start"
    echo "  4. Navigate to Integrations tab"
    echo "  5. Click Test button"
else
    echo "❌ $ERRORS ERRORS FOUND"
    echo ""
    echo "Please review the errors above and fix them."
fi

echo "═══════════════════════════════════════════════════════════"

exit $ERRORS
