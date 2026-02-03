# E2E Mesh Connection Test: Mac ↔ Android

**Date:** 2026-02-03  
**Status:** 🔴 NOT WORKING - Critical gaps identified

---

## Executive Summary

Rob's Android app cannot find his Mac because **the Android app has NO way to join a mesh**. The UI is scaffolded but all the connection logic is missing. The Mac server is working perfectly.

---

## Part 1: Mac Server Status ✅ WORKING

### Mesh Status
```json
{
  "mesh_id": "0b82206b236bd66c",
  "mesh_name": "home-mesh",
  "node_count": 1,
  "peer_count": 0,
  "capabilities": ["llm", "embeddings"],
  "is_founder": true
}
```

### Token Generation ✅ WORKING
```json
{
  "token": "ATM-FA32EA68D422B9C24788369830D66123",
  "mesh_id": "0b82206b236bd66c",
  "mesh_name": "home-mesh",
  "endpoint": "ws://192.168.86.237:11451",
  "qr_data": "atmosphere://join?token=ATM-FA32EA68D422B9C24788369830D66123&mesh=home-mesh&endpoint=ws://192.168.86.237:11451"
}
```

### Network Accessibility ✅ WORKING
- **Local IP:** 192.168.86.237
- **Port 11451:** Connection succeeded
- **Firewall:** Enabled but not blocking

### mDNS Discovery ✅ CONFIGURED
- zeroconf library: AVAILABLE
- mdns_enabled: true
- Service type: `_atmosphere._tcp.local.`
- **Status:** Running but no peers discovered (because Android can't discover)

### QR Code in UI ✅ WORKING
- `JoinPanel.jsx` generates QR codes using `qrcode.react`
- QR contains: `atmosphere://join?token=...&mesh=...&endpoint=...`

---

## Part 2: Android App Status 🔴 BROKEN

### QR Scanner: ❌ NOT IMPLEMENTED
- **No camera dependencies** in build.gradle
- **No CameraX or MLKit** imports
- **No QR scanning code** anywhere in the app
- `MeshScreen.kt` has a "Scan" button that does nothing

### Manual Join UI: ❌ NOT IMPLEMENTED
- **No text field** to paste invite token
- **No IP entry** field
- **No "Connect" button** with endpoint input

### mDNS Discovery: ❌ NOT IMPLEMENTED IN RUST
- The Rust `MeshClient` has a `connect(address)` method
- But this is **NOT EXPOSED** via JNI to Android
- Android's `AtmosphereNode` bindings only have:
  - `start()` / `stop()` / `isRunning()`
  - `statusJson()` / `registerCapability()` / `routeIntent()`
- **Missing:** `connect(endpoint)`, `joinMesh(token)`, `discoverPeers()`

### Current MeshScreen.kt
```kotlin
// TODO: Connect to actual mesh state via ViewModel
var peers by remember { mutableStateOf<List<MeshPeer>>(emptyList()) }
var isScanning by remember { mutableStateOf(false) }

FilledTonalButton(onClick = {
    isScanning = !isScanning
    // TODO: Trigger peer discovery  <-- THIS IS EMPTY
}) { ... }
```

### Current JNI Bindings (android/src/lib.rs)
```rust
// What EXISTS:
pub fn start() -> Result<(), String>
pub fn stop()
pub fn is_running() -> bool
pub fn status_json() -> String
pub fn register_capability_json(json: &str) -> Result<(), String>
pub fn route_intent_json(json: &str) -> Result<String, String>

// What's MISSING:
// pub fn connect_to_peer(endpoint: &str) -> Result<NodeId, String>
// pub fn join_mesh_with_token(token: &str) -> Result<MeshInfo, String>
// pub fn discover_peers() -> Vec<PeerInfo>
```

---

## Part 3: What's WORKING

| Component | Status |
|-----------|--------|
| Mac mesh server | ✅ Running |
| Mac token generation | ✅ Working |
| Mac QR code display | ✅ Working |
| Mac mDNS advertising | ✅ Configured |
| Mac network accessibility | ✅ Port 11451 open |
| Android service start/stop | ✅ Working |
| Android capability registration | ✅ Working |
| Android UI scaffolding | ✅ Present |

---

## Part 4: What's BROKEN

| Component | Status | Priority |
|-----------|--------|----------|
| Android QR scanner | ❌ Missing | P0 |
| Android manual join UI | ❌ Missing | P0 |
| Rust JNI `connect()` binding | ❌ Missing | P0 |
| Rust JNI `joinMesh()` binding | ❌ Missing | P0 |
| Android mDNS discovery | ❌ Missing | P1 |
| Android peer list sync | ❌ Missing | P1 |

---

## Part 5: Fix Plan (Prioritized)

### Priority 0: Make QR Join Work (4-6 hours)

#### Step 1: Add QR Scanner to Android (2 hours)

**1.1 Add dependencies to `app/build.gradle.kts`:**
```kotlin
// ML Kit Barcode Scanning
implementation("com.google.mlkit:barcode-scanning:17.2.0")
// CameraX
implementation("androidx.camera:camera-camera2:1.3.1")
implementation("androidx.camera:camera-lifecycle:1.3.1")
implementation("androidx.camera:camera-view:1.3.1")
```

**1.2 Create `QrScannerScreen.kt`:**
```kotlin
@Composable
fun QrScannerScreen(
    onQrScanned: (String) -> Unit,
    onClose: () -> Unit
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    
    val barcodeScanner = remember {
        BarcodeScanning.getClient(
            BarcodeScannerOptions.Builder()
                .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
                .build()
        )
    }
    
    AndroidView(
        factory = { ctx ->
            PreviewView(ctx).apply {
                val cameraProviderFuture = ProcessCameraProvider.getInstance(ctx)
                cameraProviderFuture.addListener({
                    val cameraProvider = cameraProviderFuture.get()
                    val preview = Preview.Builder().build()
                    preview.setSurfaceProvider(surfaceProvider)
                    
                    val imageAnalysis = ImageAnalysis.Builder()
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                        .build()
                    
                    imageAnalysis.setAnalyzer(Executors.newSingleThreadExecutor()) { imageProxy ->
                        val inputImage = InputImage.fromMediaImage(
                            imageProxy.image!!,
                            imageProxy.imageInfo.rotationDegrees
                        )
                        barcodeScanner.process(inputImage)
                            .addOnSuccessListener { barcodes ->
                                barcodes.firstOrNull()?.rawValue?.let { qrData ->
                                    if (qrData.startsWith("atmosphere://")) {
                                        onQrScanned(qrData)
                                    }
                                }
                            }
                            .addOnCompleteListener { imageProxy.close() }
                    }
                    
                    cameraProvider.bindToLifecycle(
                        lifecycleOwner,
                        CameraSelector.DEFAULT_BACK_CAMERA,
                        preview,
                        imageAnalysis
                    )
                }, ContextCompat.getMainExecutor(ctx))
            }
        }
    )
}
```

#### Step 2: Add JNI Connect Binding (2 hours)

**2.1 Update `android/src/lib.rs`:**
```rust
impl AndroidNode {
    // Add mesh client
    mesh_client: Option<Arc<MeshClient>>,
    
    pub async fn connect_to_peer(&self, endpoint: &str) -> Result<String, String> {
        // Parse endpoint URL
        let url = url::Url::parse(endpoint)
            .map_err(|e| format!("Invalid endpoint URL: {}", e))?;
        
        // Create WebSocket connection
        let (ws_stream, _) = tokio_tungstenite::connect_async(&url)
            .await
            .map_err(|e| format!("Connection failed: {}", e))?;
        
        // Perform handshake
        // ... send Hello message, receive peer info
        
        Ok(peer_id.to_string())
    }
    
    pub fn join_mesh_with_token(&self, qr_data: &str) -> Result<String, String> {
        // Parse QR data: atmosphere://join?token=X&mesh=Y&endpoint=Z
        let url = url::Url::parse(qr_data)
            .map_err(|e| format!("Invalid QR data: {}", e))?;
        
        let params: HashMap<_, _> = url.query_pairs().collect();
        let endpoint = params.get("endpoint")
            .ok_or("Missing endpoint in QR data")?;
        let token = params.get("token")
            .ok_or("Missing token in QR data")?;
        
        // Connect to endpoint
        // Send join request with token
        // Return mesh info
        
        Ok(format!("{{\"mesh_id\":\"{}\",\"success\":true}}", 
            params.get("mesh").unwrap_or(&"unknown")))
    }
}

// JNI bindings
#[no_mangle]
pub extern "C" fn Java_com_llamafarm_atmosphere_bindings_AtmosphereNode_nativeJoinMesh(
    _env: *mut std::ffi::c_void,
    _obj: *mut std::ffi::c_void,
    handle: c_long,
    qr_data: *const c_char,
) -> *mut c_char {
    // ... implementation
}
```

**2.2 Update `Atmosphere.kt` bindings:**
```kotlin
class AtmosphereNode private constructor(private val handle: Long) {
    // Add new methods
    @Throws(AtmosphereException::class)
    fun joinMesh(qrData: String): String {
        val result = nativeJoinMesh(handle, qrData)
        if (result.startsWith("ERROR:")) {
            throw AtmosphereException.NetworkError(result.removePrefix("ERROR:"))
        }
        return result
    }
    
    private external fun nativeJoinMesh(handle: Long, qrData: String): String
}
```

#### Step 3: Wire Up the UI (1 hour)

**3.1 Update `MeshScreen.kt`:**
```kotlin
@Composable
fun MeshScreen(viewModel: AtmosphereViewModel = viewModel()) {
    var showScanner by remember { mutableStateOf(false) }
    var joinResult by remember { mutableStateOf<String?>(null) }
    
    if (showScanner) {
        QrScannerScreen(
            onQrScanned = { qrData ->
                showScanner = false
                viewModel.joinMesh(qrData)
            },
            onClose = { showScanner = false }
        )
    } else {
        Column {
            // ... existing peer list UI
            
            Button(onClick = { showScanner = true }) {
                Icon(Icons.Default.QrCodeScanner)
                Text("Scan QR to Join")
            }
        }
    }
}
```

**3.2 Update `AtmosphereViewModel.kt`:**
```kotlin
class AtmosphereViewModel : ViewModel() {
    private val _joinStatus = MutableStateFlow<JoinStatus>(JoinStatus.Idle)
    val joinStatus: StateFlow<JoinStatus> = _joinStatus
    
    fun joinMesh(qrData: String) {
        viewModelScope.launch {
            _joinStatus.value = JoinStatus.Joining
            try {
                val result = node?.joinMesh(qrData)
                _joinStatus.value = JoinStatus.Success(result)
            } catch (e: Exception) {
                _joinStatus.value = JoinStatus.Error(e.message)
            }
        }
    }
}
```

---

### Priority 1: Add Alternative Join Methods (2-3 hours)

#### Manual Endpoint Entry
```kotlin
@Composable
fun ManualJoinDialog(onJoin: (String) -> Unit) {
    var endpoint by remember { mutableStateOf("") }
    var token by remember { mutableStateOf("") }
    
    Column {
        OutlinedTextField(
            value = endpoint,
            onValueChange = { endpoint = it },
            label = { Text("Endpoint (e.g., ws://192.168.1.100:11451)") }
        )
        OutlinedTextField(
            value = token,
            onValueChange = { token = it },
            label = { Text("Invite Token (ATM-...)") }
        )
        Button(onClick = {
            val qrData = "atmosphere://join?token=$token&endpoint=$endpoint"
            onJoin(qrData)
        }) {
            Text("Connect")
        }
    }
}
```

---

### Priority 2: Add mDNS Discovery (4+ hours)

Would require implementing zeroconf in Rust for Android, which is complex. Lower priority since QR scanning solves the immediate problem.

---

## Immediate Action Items

1. **Add MLKit + CameraX** to Android build.gradle ✏️
2. **Create QrScannerScreen.kt** ✏️
3. **Add `joinMesh()` JNI binding** in Rust ✏️
4. **Update Kotlin bindings** ✏️
5. **Wire up MeshScreen** to use scanner ✏️
6. **Test end-to-end** 🧪

---

## Test Procedure

Once implemented:

1. **On Mac:** Go to http://localhost:3007 → "Join" tab → "Generate Invitation"
2. **On Android:** Open Atmosphere app → Mesh tab → "Scan QR"
3. **Scan:** Point camera at Mac screen
4. **Verify:** Android shows "Connected to home-mesh"
5. **Confirm:** Mac's `/api/mesh/peers` shows Android node

---

## Files to Modify

| File | Action |
|------|--------|
| `app/build.gradle.kts` | Add MLKit, CameraX deps |
| `app/src/main/.../QrScannerScreen.kt` | CREATE - QR scanner UI |
| `app/src/main/.../MeshScreen.kt` | Add scanner integration |
| `android/src/lib.rs` | Add joinMesh JNI binding |
| `app/src/.../bindings/Atmosphere.kt` | Add joinMesh method |
| `app/src/.../viewmodel/AtmosphereViewModel.kt` | Add joinMesh function |
| `AndroidManifest.xml` | Add camera permission |

---

**Bottom Line:** The Mac server is 100% ready. The Android app needs ~4-6 hours of work to add QR scanning and the connect logic. The code structure is there, it just needs the actual implementation.
