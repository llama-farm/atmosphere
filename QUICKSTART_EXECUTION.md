# Atmosphere Execution Layer - Quick Start Guide

## 🚀 5-Minute Setup & Test

### Prerequisites

1. **LlamaFarm running** on port 14345
2. **Python 3.9+** with dependencies installed
3. **Node.js 18+** for the UI

---

## Step 1: Install Dependencies

```bash
cd ~/clawd/projects/atmosphere

# Python dependencies
pip install -r requirements.txt

# Frontend dependencies
cd ui
npm install
cd ..
```

---

## Step 2: Start Atmosphere Backend

```bash
python3 -m atmosphere start
```

**Expected Output:**
```
INFO: Executor initialized: ollama=True, llamafarm=True
INFO: Uvicorn running on http://0.0.0.0:8000
```

✅ If you see `llamafarm=True`, the backend is connected to LlamaFarm!

---

## Step 3: Start Frontend

**New Terminal:**
```bash
cd ~/clawd/projects/atmosphere/ui
npm start
```

Opens browser at `http://localhost:3000`

---

## Step 4: Test Execution

### Via UI:

1. Navigate to **"Integrations"** tab (puzzle icon)
2. You should see:
   ```
   ┌─────────────────────────────────────┐
   │ 🖥️  LlamaFarm                       │
   │ localhost:14345                     │
   │ ✓ Healthy                           │
   │                                     │
   │ 26 Models | 3 Capabilities          │
   │ [llama3.2:3b] [qwen2.5] ...        │
   │                                     │
   │ [Test] [Disconnect]                 │
   └─────────────────────────────────────┘
   ```

3. Click **"Test"** button
4. Wait 1-3 seconds
5. See result:
   ```
   ┌─────────────────────────────────────┐
   │ ✓ Test Successful         245ms     │
   ├─────────────────────────────────────┤
   │ Response:                           │
   │ 1, 2, 3, 4, 5                       │
   │ Model: llama3.2:3b                  │
   └─────────────────────────────────────┘
   ```

### Via API:

```bash
# Test the integration
curl -X POST http://localhost:8000/v1/integrations/test \
  -H "Content-Type: application/json" \
  -d '{
    "integration_id": "llamafarm",
    "prompt": "Say hello in 3 words"
  }'
```

**Expected Response:**
```json
{
  "success": true,
  "response": "Hello there friend!",
  "latency_ms": 234.5,
  "model_used": "llama3.2:3b"
}
```

### Test Chat Completion:

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.2:3b",
    "messages": [
      {"role": "user", "content": "What is 2+2?"}
    ]
  }'
```

**Response:**
```json
{
  "id": "chatcmpl-1738532...",
  "object": "chat.completion",
  "created": 1738532...,
  "model": "llama3.2:3b",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "2 + 2 = 4"
    },
    "finish_reason": "stop"
  }],
  "usage": {...}
}
```

---

## Step 5: Verify Execution Flow

### Check Logs:

Backend logs should show:
```
DEBUG: Executing locally: chat
INFO: Using LlamaFarm backend
POST http://localhost:14345/v1/chat/completions
Response: 200 OK
```

### Test Fallback:

1. Stop LlamaFarm
2. Test again
3. Should fallback to Ollama automatically
4. Logs show:
   ```
   WARNING: LlamaFarm chat failed: Connection refused, trying Ollama
   INFO: Using Ollama backend
   ```

---

## 🎯 What You Should See

### Integration Panel:
- ✅ Green "Healthy" status on LlamaFarm card
- ✅ Model count (e.g., "26 Models")
- ✅ Model tags (e.g., `llama3.2:3b`, `qwen2.5`)
- ✅ "Test" button active
- ✅ Test results show after clicking

### Test Results:
- ✅ Success indicator (green checkmark)
- ✅ Response text
- ✅ Latency in milliseconds
- ✅ Model name used

### API Response:
- ✅ `success: true`
- ✅ `response: "..."` with actual text
- ✅ `latency_ms: 234.5`
- ✅ `model_used: "llama3.2:3b"`

---

## 🐛 Troubleshooting

### LlamaFarm shows "Offline"

**Check:**
```bash
curl http://localhost:14345/health
```

**Should return:**
```json
{"status": "healthy"}
```

**Fix:**
- Start LlamaFarm
- Check port isn't blocked
- Verify firewall settings

### Test button doesn't work

**Check browser console:**
```
POST http://localhost:8000/v1/integrations/test
```

**Check backend logs:**
```
ERROR: Server not ready
```

**Fix:**
- Verify backend is running
- Check executor initialized
- Restart backend

### "No chat backend available"

**Cause:** Neither LlamaFarm nor Ollama are accessible

**Fix:**
```bash
# Check LlamaFarm
curl http://localhost:14345/health

# Check Ollama
curl http://localhost:11434/api/tags
```

Start at least one backend.

---

## 📊 Quick Reference

### Endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/integrations` | GET | List backends |
| `/v1/integrations/test` | POST | Test execution |
| `/v1/chat/completions` | POST | Chat (OpenAI-compatible) |
| `/v1/execute` | POST | Intent routing |
| `/health` | GET | Health check |
| `/ws` | WebSocket | Real-time updates |

### Ports:

| Service | Port |
|---------|------|
| Atmosphere API | 8000 |
| Atmosphere UI | 3000 |
| LlamaFarm | 14345 |
| Ollama | 11434 |

### Test Prompts:

```bash
# Simple count
"Hello! Can you count to 5?"

# Question
"What is 2+2?"

# Creative
"Write a haiku about AI"

# Complex
"Explain quantum computing in simple terms"
```

---

## ✨ Success Indicators

You know it's working when:

1. ✅ Backend logs show `llamafarm=True`
2. ✅ Integration panel shows green status
3. ✅ Test button returns results in &lt;3 seconds
4. ✅ API calls execute through LlamaFarm
5. ✅ Latency is measured correctly
6. ✅ Model name is displayed

---

## 🚀 Next Steps

Once execution is working:

1. Try different models in LlamaFarm
2. Test with longer prompts
3. Measure latency across models
4. Compare LlamaFarm vs Ollama performance
5. Build custom capabilities on top

---

## 📝 Summary

The execution layer is complete when:

- Integration panel discovers backends ✅
- Test button executes real prompts ✅
- Results display with latency ✅
- Automatic fallback works ✅
- OpenAI-compatible API works ✅

**You're now running a fully functional mesh AI network with real execution!** 🎉
