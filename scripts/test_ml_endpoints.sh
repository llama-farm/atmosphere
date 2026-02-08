#!/bin/bash
# Test ML endpoints for Atmosphere <-> LlamaFarm integration

echo "🧪 Testing Atmosphere ML Execution Layer"
echo "========================================="
echo ""

BASE_URL="http://localhost:8000"
LLAMAFARM_URL="http://localhost:14345"

# Test 1: Check LlamaFarm is available
echo "1️⃣ Testing LlamaFarm health..."
curl -s $LLAMAFARM_URL/health | jq . || echo "❌ LlamaFarm not available"
echo ""

# Test 2: List anomaly detection models
echo "2️⃣ Listing anomaly detection models..."
curl -s $LLAMAFARM_URL/v1/ml/anomaly/models | jq . || echo "❌ Failed to list anomaly models"
echo ""

# Test 3: List classifier models
echo "3️⃣ Listing classifier models..."
curl -s $LLAMAFARM_URL/v1/ml/classifier/models | jq . || echo "❌ Failed to list classifier models"
echo ""

# Test 4: Test anomaly detection via Atmosphere
echo "4️⃣ Testing anomaly detection through Atmosphere..."
curl -s -X POST $BASE_URL/v1/ml/anomaly \
  -H "Content-Type: application/json" \
  -d '{
    "model": "isolation_forest",
    "data": [[1, 2], [2, 3], [3, 4], [100, 200]],
    "action": "detect"
  }' | jq .
echo ""

# Test 5: Test classification via Atmosphere
echo "5️⃣ Testing classification through Atmosphere..."
curl -s -X POST $BASE_URL/v1/ml/classify \
  -H "Content-Type: application/json" \
  -d '{
    "model": "random_forest",
    "data": [[1, 2], [3, 4]],
    "action": "predict"
  }' | jq .
echo ""

# Test 6: Test via /v1/execute with intent routing
echo "6️⃣ Testing intent routing to anomaly detection..."
curl -s -X POST $BASE_URL/v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "detect anomalies",
    "kwargs": {
      "model": "isolation_forest",
      "data": [[1, 2], [2, 3], [100, 200]]
    }
  }' | jq .
echo ""

# Test 7: List anomaly models via Atmosphere
echo "7️⃣ Listing anomaly models via Atmosphere..."
curl -s $BASE_URL/v1/ml/anomaly/models | jq .
echo ""

# Test 8: List classifier models via Atmosphere
echo "8️⃣ Listing classifier models via Atmosphere..."
curl -s $BASE_URL/v1/ml/classifier/models | jq .
echo ""

echo "✅ ML endpoint tests complete!"
