#!/bin/bash
# Test the LlamaFarm execution layer

echo "🧪 Testing Atmosphere Execution Layer"
echo "======================================"
echo ""

# Test 1: Health check
echo "1️⃣ Testing LlamaFarm health..."
curl -s http://localhost:14345/health | jq . || echo "❌ LlamaFarm not available"
echo ""

# Test 2: List models
echo "2️⃣ Listing available models..."
curl -s http://localhost:14345/v1/models | jq '.data[] | {id, owned_by}' || echo "❌ Failed to list models"
echo ""

# Test 3: Test direct execution
echo "3️⃣ Testing execution through Atmosphere..."
curl -s -X POST http://localhost:8000/v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "What is 2+2?",
    "kwargs": {}
  }' | jq .
echo ""

# Test 4: Test with specific model
echo "4️⃣ Testing with specific model..."
curl -s -X POST http://localhost:8000/v1/integrations/test \
  -H "Content-Type: application/json" \
  -d '{
    "integration_id": "llamafarm",
    "prompt": "Count to 5",
    "model": "llama3.2:latest"
  }' | jq .
echo ""

echo "✅ Tests complete!"
