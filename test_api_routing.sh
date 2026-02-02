#!/bin/bash
# Test Atmosphere OpenAI-Compatible API Routing
# 
# Prerequisites:
# - Atmosphere server running on port 8000 (or specify ATMOSPHERE_PORT)
# - LlamaFarm running on port 14345
# - Universal runtime on port 11540

ATMOSPHERE_PORT="${ATMOSPHERE_PORT:-8000}"
BASE_URL="http://localhost:${ATMOSPHERE_PORT}"

echo "=============================================="
echo "Testing Atmosphere OpenAI-Compatible API"
echo "Base URL: ${BASE_URL}"
echo "=============================================="

# Test 1: List models
echo ""
echo ">>> TEST 1: GET /v1/models"
echo "----------------------------------------"
curl -s "${BASE_URL}/v1/models" | python3 -c "
import json, sys
data = json.load(sys.stdin)
models = data.get('data', [])
print(f'Found {len(models)} models')
for m in models[:5]:
    print(f'  - {m.get(\"id\")} ({m.get(\"domain\", \"n/a\")})')
if len(models) > 5:
    print(f'  ... and {len(models) - 5} more')
"

# Test 2: Test routing endpoint
echo ""
echo ">>> TEST 2: POST /v1/routing/test (llama query)"
echo "----------------------------------------"
curl -s -X POST "${BASE_URL}/v1/routing/test" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "How do I shear a llama and process the fiber?"}
    ]
  }' | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f'Requested: {data.get(\"model_requested\")}')
print(f'Routed to: {data.get(\"routed_to\")}')
print(f'Domain:    {data.get(\"domain\")}')
print(f'Score:     {data.get(\"score\", 0):.2f}')
print(f'Reason:    {data.get(\"reason\")}')
print(f'Success:   {data.get(\"success\")}')
"

# Test 3: Test explicit model routing
echo ""
echo ">>> TEST 3: POST /v1/routing/test (explicit model)"
echo "----------------------------------------"
curl -s -X POST "${BASE_URL}/v1/routing/test" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default/llama-expert-14",
    "messages": [
      {"role": "user", "content": "Tell me anything"}
    ]
  }' | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f'Requested: {data.get(\"model_requested\")}')
print(f'Routed to: {data.get(\"routed_to\")}')
print(f'Score:     {data.get(\"score\", 0):.2f}')
print(f'Success:   {data.get(\"success\")}')
"

# Test 4: Routing stats
echo ""
echo ">>> TEST 4: GET /v1/routing/stats"
echo "----------------------------------------"
curl -s "${BASE_URL}/v1/routing/stats" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f'Total projects: {data.get(\"total_projects\")}')
print(f'Domains: {data.get(\"domains\")}')
print(f'Default: {data.get(\"default_project\")}')
"

# Test 5: List projects by domain
echo ""
echo ">>> TEST 5: GET /v1/routing/projects?domain=animals/camelids"
echo "----------------------------------------"
curl -s "${BASE_URL}/v1/routing/projects?domain=animals%2Fcamelids" | python3 -c "
import json, sys
data = json.load(sys.stdin)
projects = data.get('projects', [])
print(f'Found {len(projects)} camelid projects:')
for p in projects[:5]:
    print(f'  - {p.get(\"model_path\")} (RAG: {p.get(\"has_rag\")})')
"

# Test 6: Chat completions (if LlamaFarm is running)
echo ""
echo ">>> TEST 6: POST /v1/chat/completions (actual request)"
echo "----------------------------------------"
echo "(This test requires LlamaFarm to be running)"

# Quick check if LlamaFarm is up
if curl -s --connect-timeout 2 "http://localhost:14345/health" > /dev/null 2>&1; then
  curl -s -X POST "${BASE_URL}/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d '{
      "model": "auto",
      "messages": [
        {"role": "user", "content": "What do llamas eat? Be brief."}
      ],
      "max_tokens": 100,
      "temperature": 0.7
    }' | python3 -c "
import json, sys
data = json.load(sys.stdin)
atmosphere = data.get('_atmosphere', {})
print(f'Routed to: {atmosphere.get(\"routed_to\")}')
print(f'Score:     {atmosphere.get(\"score\", 0):.2f}')
choice = data.get('choices', [{}])[0]
message = choice.get('message', {})
print(f'Response:  {message.get(\"content\", \"(no response)\")[:200]}...')
"
else
  echo "⚠️  LlamaFarm not running - skipping actual chat test"
fi

echo ""
echo "=============================================="
echo "API Tests Complete"
echo "=============================================="
