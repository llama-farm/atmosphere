# Atmosphere SDK - Quick Reference

**Created**: 2025-02-04  
**Agent**: Atmosphere SDK Platform Agent

---

## 📋 Documentation Locations

### Mac Platform API
**File**: [`docs/PLATFORM_API.md`](./docs/PLATFORM_API.md)  
**What**: Complete REST & WebSocket API reference for Mac server

### Android SDK
**File**: [`../atmosphere-android/atmosphere-sdk/README.md`](../atmosphere-android/atmosphere-sdk/README.md)  
**What**: Full Android SDK documentation with AIDL details

### Overnight Report
**File**: [`OVERNIGHT_SDK_REPORT.md`](./OVERNIGHT_SDK_REPORT.md)  
**What**: Complete status report with testing results

---

## 🚀 Quick Start

### Mac Platform (Python)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11451/v1",
    api_key="not-needed"
)

response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Hello!"}]
)

print(response.choices[0].message.content)
```

### Android SDK (Kotlin)

```kotlin
val atmosphere = AtmosphereClient.connect(context)

val result = atmosphere.chat(
    messages = listOf(ChatMessage.user("Hello!"))
)

if (result.success) {
    println("AI: ${result.content}")
}
```

---

## 📁 Example Apps

### Python Chat Client
**File**: [`examples/python_chat_client.py`](./examples/python_chat_client.py)  
**Run**: `python3 examples/python_chat_client.py`

Features:
- Interactive chat with Atmosphere
- Mesh status monitoring
- Intent routing demos
- OpenAI SDK compatibility

### Android Demo App
**File**: [`../atmosphere-android/example-app/MainActivity.kt`](../atmosphere-android/example-app/MainActivity.kt)

Features:
- Chat interface
- Capability browser
- Mesh status monitoring
- Material Design 3 UI

---

## 🔧 Build Commands

### Mac Platform API
```bash
# Start server
atmosphere serve

# Test API
curl http://localhost:11451/health
curl http://localhost:11451/api/capabilities
```

### Android SDK
```bash
# Build AAR
cd ../atmosphere-android
./gradlew :atmosphere-sdk:assembleRelease

# Output: atmosphere-sdk/build/outputs/aar/atmosphere-sdk-release.aar
```

---

## ✅ Status

| Component | Status | Location |
|-----------|--------|----------|
| Mac API Docs | ✅ Complete | `docs/PLATFORM_API.md` |
| Android SDK Docs | ✅ Complete | `../atmosphere-android/atmosphere-sdk/README.md` |
| Python Example | ✅ Complete | `examples/python_chat_client.py` |
| Android Example | ✅ Complete | `../atmosphere-android/example-app/MainActivity.kt` |
| Cross-Platform Test | ✅ Verified | See report |
| SDK Build | ✅ Successful | AAR ready |

---

## 📖 API Endpoints (Mac)

### REST
- `GET /health` - Health check
- `POST /api/chat/completions` - OpenAI-compatible chat
- `POST /api/route` - Route intent to best capability
- `POST /api/execute` - Execute intent on mesh
- `GET /api/capabilities` - List capabilities
- `GET /api/mesh/status` - Mesh network status
- `GET /api/cost/current` - Cost metrics

### WebSocket
- `ws://localhost:11451/api/ws` - Real-time updates

### OpenAI Compatible
- `POST /v1/chat/completions`
- `POST /v1/embeddings`
- `GET /v1/models`

---

## 📱 Android SDK Methods

### Core
- `AtmosphereClient.connect(context)` - Connect to service
- `atmosphere.chat(messages)` - Chat completion
- `atmosphere.route(intent)` - Route intent
- `atmosphere.capabilities()` - List capabilities
- `atmosphere.meshStatus()` - Mesh status
- `atmosphere.costs()` - Cost metrics

### Reactive
- `atmosphere.meshStatusFlow()` - Real-time mesh updates
- `atmosphere.costMetricsFlow()` - Real-time cost updates

---

## 🧪 Testing

### Mac API Test
```bash
# Chat completion
curl -X POST http://localhost:11451/api/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### Android SDK Test
```kotlin
// In your app
val atmosphere = AtmosphereClient.connect(context)
val result = atmosphere.chat(
    messages = listOf(ChatMessage.user("Test message"))
)
Log.d("Test", "Response: ${result.content}")
```

---

## 🎯 Use Cases

### 1. OpenAI Drop-in Replacement (Mac)
Replace `https://api.openai.com` with `http://localhost:11451/v1`

### 2. Android App with AI (Android)
Add Atmosphere SDK → instant AI capabilities

### 3. Cross-Platform Mesh (Mac + Android)
Both platforms contribute and consume capabilities

---

## 📚 Further Reading

- **Architecture**: See `ARCHITECTURE.md`
- **Overnight Report**: See `OVERNIGHT_SDK_REPORT.md`
- **Mac Platform API**: See `docs/PLATFORM_API.md`
- **Android SDK**: See `../atmosphere-android/atmosphere-sdk/README.md`

---

**Need help?** Check the documentation or open an issue on GitHub.
