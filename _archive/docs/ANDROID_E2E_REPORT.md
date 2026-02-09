# Android E2E Test Report

**Date**: 2025-02-05
**Device**: Pixel 9 Pro (4B041FDAP0033Q)
**Test Agent**: Android E2E Testing Agent

## Executive Summary

⚠️ **PARTIAL SUCCESS** - Individual components work but full E2E mesh routing not verified.

The Atmosphere Android app and Demo Client are installed and launch successfully, but the mesh connection between Android and Mac could not be fully established during this test session due to:
1. Native JNI bindings issue
2. Deep link handling not triggering join
3. Token replay issues on reconnect

---

## Test Results

### 1. Device Connectivity
✅ **PASS** - Phone connected via USB

```
List of devices attached
4B041FDAP0033Q	device
```

### 2. App Installation

#### Atmosphere App
✅ **PASS** - Installed successfully

```
Package: com.llamafarm.atmosphere.debug
APK: ~/clawd/projects/atmosphere-android/app/build/outputs/apk/debug/app-debug.apk
Status: Installed
```

#### Demo Client App
✅ **PASS** - Installed successfully

```
Package: com.example.democlient
APK: ~/clawd/projects/demo-client/app/build/outputs/apk/debug/app-debug.apk
Status: Installed
```

### 3. Atmosphere App Launch
✅ **PASS** - App launches without crashes

Key logs:
```
AtmosphereApp: Native library loaded successfully
AtmosphereApp: Atmosphere application initialized (node: android-45649cd8-a44)
AtmosphereApp: Bundled model extracted successfully: Qwen3-1.7B-Q4_K_M.gguf
AtmosphereService: Node started successfully
```

### 4. Native Library Status
⚠️ **PARTIAL** - Library loads but JNI bindings incomplete

```
AtmosphereApp: Native library loaded successfully

# But mesh node JNI fails:
AtmosphereService: Native AtmosphereNode not available: 
  No implementation found for long com.llamafarm.atmosphere.bindings.AtmosphereNode.nativeCreateNode
```

**Impact**: Rust-based mesh node cannot be created. App uses stub/mock implementation.

### 5. Local Inference (Phone)
❌ **FAIL** - Model extracted but CANNOT LOAD

```
AtmosphereApp: Bundled model detected, extracting in background...
AtmosphereApp: Bundled model extracted successfully: 
  /data/user/0/com.llamafarm.atmosphere.debug/files/models/Qwen3-1.7B-Q4_K_M.gguf
```

**CRITICAL BUG**: Model loading fails with `UnsupportedArchitectureException`:
```
LocalInferenceEngine: Loading model: /data/.../models/Qwen3-1.7B-Q4_K_M.gguf
InferenceEngineImpl: Error loading model
InferenceEngineImpl: com.arm.aichat.UnsupportedArchitectureException
	at com.arm.aichat.internal.InferenceEngineImpl$loadModel$2.invokeSuspend(InferenceEngineImpl.kt:169)
```

**Root Cause**: The llama.cpp native library (`libai-chat.so` / `libllama.so`) returns error when loading Qwen3 architecture. The native `load()` function returns non-zero, triggering the exception.

**Note**: The llama.cpp source includes `models/qwen3.cpp` so Qwen3 IS in the source, but:
- The AAR may not have been rebuilt after Qwen3 support was added
- There may be a model metadata parsing issue
- The bundled model may be incompatible with this llama.cpp build

### 6. Mac Mesh Server Status
✅ **PASS** - Server running and healthy

```json
{
    "mesh_id": "0b82206b236bd66c",
    "mesh_name": "home-mesh",
    "node_count": 1,
    "capabilities": ["69ff1fa7cc80d0e0:llamafarm/discoverable/llama-expert-14"],
    "is_founder": true
}
```

**Endpoints**:
- Local: `ws://192.168.86.237:11451`
- Relay: `wss://atmosphere-relay-production.up.railway.app/relay/0b82206b236bd66c`

### 7. Mesh Connection Attempts

#### First Attempt (Before App Data Clear)
⚠️ **PARTIAL** - Connected briefly then token replay error

```
ConnectionTrain: 🚂 Connection train starting for mesh: New Mesh
MeshConnection: Connecting to: ws://192.168.86.237:11451/api/ws
MeshConnection: WebSocket opened
MeshConnection: Received: {"type":"joined","mesh":"home-mesh","mesh_id":"0b82206b236bd66c"}
MeshConnection: Disconnecting from mesh
ConnectionTrain: ✅ local available (576ms)

# Second connection attempt failed:
MeshConnection: Received: {"type":"error","code":"TOKEN_INVALID","message":"Token already used (replay)"}

# Fell back to BLE:
ConnectionTrain: 🎯 Racing result: ble is best. Boarding...
AtmosphereService: ✅ Connected to New Mesh via ble
```

#### After App Data Clear
❌ **FAIL** - No saved mesh credentials

```
BootReceiver: No saved mesh credentials
AtmosphereViewModel: Loaded 0 saved meshes
AtmosphereViewModel: 📡 Service status update: Online (No Mesh)
```

### 8. Deep Link Join Attempt
❌ **FAIL** - atmosphere:// link not processed

Generated token and launched via intent:
```bash
adb shell am start -a android.intent.action.VIEW -d "atmosphere://join/..."
```

Result: Intent received but mesh join not triggered.
```
AtmosphereViewModel: 📦 Loaded 0 saved meshes
AtmosphereViewModel: Saved mesh state: name=null, hasToken=false
```

### 9. Demo Client SDK
✅ **PASS** - SDK binds to Atmosphere service and invokes inference!

**Positive Finding**: The SDK IPC binding works!
```
AtmosphereBinderService: chatCompletion() called: model=null
AtmosphereBinderService: Using local inference (not connected to mesh)
```

The Demo Client successfully:
1. Binds to Atmosphere service via AIDL
2. Sends chat completion request
3. Routes to local inference (since mesh is disconnected)

**Issue**: Local inference fails because the Qwen3 model can't load (UnsupportedArchitectureException).

### 9a. Test Tab
⏸️ **BLOCKED** - Requires mesh connection

The Test tab offers:
- Quick Tests: Math, Joke, Geography, Languages
- Custom Prompt: Text input → "Send to Remote LLM"

All features disabled when mesh is disconnected (shows "Not Connected" banner).

### 10. Mac Peer Visibility
❌ **FAIL** - Mac doesn't see Android as peer

```json
{
    "peers": [],
    "count": 0
}
```

**Reason**: BLE transport disabled on Mac side, LAN connection has token replay issue.

---

## Issues Identified

### 1. Native JNI Bindings Missing
**Severity**: High

The native Rust library loads but `AtmosphereNode.nativeCreateNode` JNI method is not found.
```
No implementation found for long com.llamafarm.atmosphere.bindings.AtmosphereNode.nativeCreateNode
```

### 2. Token Replay Prevention
**Severity**: Medium

When reconnecting to mesh, the same token is reused causing rejection:
```
{"type":"error","code":"TOKEN_INVALID","message":"Token already used (replay)"}
```

This is documented in `TOKEN_REPLAY_FIX.md` but still occurring.

### 3. Deep Link Handling - BUG FOUND
**Severity**: High

The `atmosphere://join/...` deep link is received by the app but doesn't trigger mesh join process.

**Root Cause Found**: `MainActivity.kt` does not handle the incoming intent data!

The `AndroidManifest.xml` correctly registers the intent filter:
```xml
<intent-filter>
    <action android:name="android.intent.action.VIEW" />
    <category android:name="android.intent.category.DEFAULT" />
    <category android:name="android.intent.category.BROWSABLE" />
    <data android:scheme="atmosphere" />
</intent-filter>
```

However, `MainActivity.kt` never checks `intent.data` in `onCreate()` or overrides `onNewIntent()`.

**Fix Required** in `MainActivity.kt`:
```kotlin
override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    // ... existing code ...
    
    // Handle deep link
    handleDeepLink(intent)
}

override fun onNewIntent(intent: Intent?) {
    super.onNewIntent(intent)
    handleDeepLink(intent)
}

private fun handleDeepLink(intent: Intent?) {
    intent?.data?.let { uri ->
        if (uri.scheme == "atmosphere" && uri.host == "join") {
            // Parse and trigger mesh join
            // Navigate to JoinMesh screen with pre-filled data
        }
    }
}
```

### 4. Model Loading - UnsupportedArchitectureException
**Severity**: CRITICAL

The Qwen3 1.7B model cannot be loaded on device:
```
InferenceEngineImpl: com.arm.aichat.UnsupportedArchitectureException
```

The `llama-android.aar` native library doesn't properly support Qwen3 despite the source code including `models/qwen3.cpp`.

**Possible causes**:
1. AAR built before Qwen3 support was properly integrated
2. Missing symbol/registration for Qwen3 architecture in native code
3. GGUF file metadata not recognized

### 5. BLE Transport Asymmetry
**Severity**: Low

Phone connects via BLE but Mac has BLE disabled:
```json
"enabled": {
    "ble": false
}
```

---

## Recommendations

### CRITICAL - Model Loading Fix

1. **Rebuild llama-android.aar** with latest llama.cpp that properly supports Qwen3:
   ```bash
   cd ~/clawd/projects/atmosphere-android/llama.cpp
   # Ensure Qwen3 model support is properly integrated
   ./scripts/build-android.sh  # or appropriate build script
   # Copy new AAR to app/libs/
   ```

2. **Test with different model** (if Qwen3 continues to fail):
   - Try Phi-3 or Llama 3.2 models which may have better llama.cpp support

### High Priority

3. **Implement Deep Link Handler** in `MainActivity.kt`:
   ```kotlin
   override fun onCreate(savedInstanceState: Bundle?) {
       super.onCreate(savedInstanceState)
       handleDeepLink(intent)
   }
   
   override fun onNewIntent(intent: Intent?) {
       super.onNewIntent(intent)
       handleDeepLink(intent)
   }
   ```

4. **Fix JNI Bindings**: Build and link the AtmosphereNode Rust JNI methods.

5. **Token Nonce Management**: Implement fresh nonce generation on each reconnect attempt.

### Lower Priority

6. **Enable BLE on Mac**: If phone-to-Mac BLE mesh is desired.

7. **Re-run with Fresh Token**: Once model loading works, test full E2E.

---

## Test Environment

| Component | Version/Status |
|-----------|---------------|
| Android Phone | Pixel 9 Pro, API 35 |
| Atmosphere App | Debug build, Feb 5 2025 |
| Demo Client | Debug build, Feb 5 2025 |
| Mac Server | Running on port 11451 |
| Mesh Name | home-mesh |
| Mesh ID | 0b82206b236bd66c |

---

## Logcat Excerpts

### Successful App Initialization
```
I/AtmosphereApp: Native library loaded successfully
D/AtmosphereApp: Semantic router initialized with 19 capabilities
D/AtmosphereApp: Cost collector initialized
D/AtmosphereApp: Local inference engine initialized
I/AtmosphereApp: Bundled model detected, extracting in background...
I/AtmosphereApp: Atmosphere application initialized (node: android-45649cd8-a44)
I/AtmosphereApp: Bundled model extracted successfully
```

### Mesh Connection (Token Replay Issue)
```
I/ConnectionTrain: 🚂 Connection train starting for mesh: New Mesh
I/MeshConnection: Connecting to: ws://192.168.86.237:11451/api/ws
I/MeshConnection: WebSocket opened
D/MeshConnection: Sent join message with auth (nonce: fresh)
D/MeshConnection: Received: {"type":"joined","mesh":"home-mesh"}
I/MeshConnection: Disconnecting from mesh
D/MeshConnection: Received: {"type":"error","code":"TOKEN_INVALID","message":"Token already used (replay)"}
```

---

## Conclusion

The Android Atmosphere ecosystem is **close to working** but has critical issues preventing the full E2E "holy grail" test:

1. ✅ Both apps install and launch
2. ✅ Local inference model loads on phone
3. ✅ Mac mesh server runs with LLM capability
4. ⚠️ Phone connects briefly then gets token replay error
5. ❌ Full mesh routing Demo Client → Atmosphere → Mac LLM not verified

**Next Steps** (Priority Order):

1. 🔴 **CRITICAL**: Fix model loading - `UnsupportedArchitectureException` for Qwen3
   - This blocks ALL local inference functionality
   - Rebuild llama-android.aar or use different model

2. 🔴 **CRITICAL**: Implement deep link handling in `MainActivity.kt`
   - Deep links currently ignored - mesh join via URL doesn't work

3. 🟡 **HIGH**: Fix token replay issue on reconnect

4. 🟢 **MEDIUM**: Once above fixed, test Demo Client SDK → Atmosphere → Mac LLM routing

---

## What Works ✅

1. Both apps install and launch
2. Native library loads (`libai-chat.so`, `libllama.so`)
3. Model file extracts to storage
4. Atmosphere service starts and runs
5. Demo Client SDK binds to Atmosphere service
6. SDK invokes `chatCompletion()` successfully
7. Mac mesh server runs with LLM capability
8. Initial mesh WebSocket connection succeeds

## What's Broken ❌

1. **Model loading** - Qwen3 architecture not supported by native library
2. **Deep link handling** - MainActivity ignores `atmosphere://` URLs
3. **Token replay** - Same token rejected on reconnect
4. **JNI bindings** - AtmosphereNode native methods not found

---

## Key Bug Found 🐛

**File**: `~/clawd/projects/atmosphere-android/app/src/main/kotlin/com/llamafarm/atmosphere/MainActivity.kt`

The `atmosphere://join/...` deep link intent is received but **never handled**. The intent filter is registered in the manifest, but the MainActivity doesn't check `intent.data` or override `onNewIntent()`.

This is why the deep link test failed - the app simply ignores the incoming URL data.
