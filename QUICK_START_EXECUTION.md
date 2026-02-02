# 🚀 Quick Start: Atmosphere Execution Layer

## Prerequisites

1. **LlamaFarm running** on `localhost:14345`
2. **Atmosphere server** running on `localhost:8000`

Check with:
```bash
# Check LlamaFarm
curl http://localhost:14345/health

# Check Atmosphere
curl http://localhost:8000/v1/health
```

---

## 🔥 Quick Test (30 seconds)

### 1. Test from CLI

```bash
curl -X POST http://localhost:8000/v1/execute \
  -H "Content-Type: application/json" \
  -d '{"intent": "What is 2+2?"}'
```

**Expected output:**
```json
{
  "success": true,
  "data": {...},
  "execution_time_ms": 245.3,
  "capability": "chat"
}
```

### 2. Test from UI

1. Open browser: `http://localhost:8000`
2. Click **"Integrations"** tab
3. Click **"Show Test Execution"**
4. Enter: `"What is 2+2?"`
5. Click **"Execute on LlamaFarm"**
6. See response! 🎉

---

## 🧪 Run Full Test Suite

```bash
cd ~/clawd/projects/atmosphere
./test_execution.sh
```

This tests:
- ✅ LlamaFarm health
- ✅ Available models
- ✅ Execution through Atmosphere
- ✅ Model-specific execution

---

## 📚 API Examples

### Basic Execution
```bash
curl -X POST http://localhost:8000/v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "Explain quantum computing in 10 words"
  }'
```

### With Specific Model
```bash
curl -X POST http://localhost:8000/v1/integrations/test \
  -H "Content-Type: application/json" \
  -d '{
    "integration_id": "llamafarm",
    "prompt": "Write a haiku about coding",
    "model": "llama3.2:latest"
  }'
```

### Chat Completion (OpenAI-compatible)
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ]
  }'
```

---

## 🐛 Troubleshooting

### "Server not ready"
- Check Atmosphere is running: `ps aux | grep atmosphere`
- Start with: `python -m atmosphere.cli start`

### "No LLM backend available"
- Check LlamaFarm: `curl localhost:14345/health`
- Start LlamaFarm if needed

### "Connection refused"
- Verify ports: `lsof -i :8000` and `lsof -i :14345`
- Check firewall settings

---

## 📖 Documentation

- **Full implementation details**: `EXECUTION_LAYER_COMPLETE.md`
- **Architecture diagram**: See main README
- **API reference**: `atmosphere/api/routes.py`

---

## 💡 Pro Tips

1. **Use model selector** in UI to try different models
2. **Check latency** to identify slow models
3. **Test various prompts** to see capability routing in action
4. **Enable debug logging** for detailed execution traces:
   ```bash
   export LOG_LEVEL=DEBUG
   ```

---

**Ready to execute!** 🚀
