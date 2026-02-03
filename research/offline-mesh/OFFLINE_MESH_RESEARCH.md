# Offline Mesh Networking Research for Atmosphere

**Goal:** Create a TRUE mesh network that works when WiFi and internet are completely down. Devices communicate directly via radio protocols.

**Date:** 2026-02-03

---

## Executive Summary

After researching available technologies, **the recommended approach is a hybrid transport layer** that uses:

1. **WiFi Aware (NAN)** as the primary offline transport (best speed, cross-platform by iOS 19)
2. **BLE Mesh** as the universal fallback (works everywhere, lower bandwidth)
3. **WiFi Direct** as a legacy/Android-specific fallback
4. **Thread/Matter** integration for IoT device mesh expansion

The key insight: **Apple is being forced by the EU (DMA) to adopt WiFi Aware by iOS 19**, making true cross-platform P2P WiFi connectivity possible for the first time. This fundamentally changes the landscape.

---

## Technology Comparison

| Technology | Range | Throughput | Power | Mesh | Android | iOS | Mac | Linux | Complexity |
|------------|-------|------------|-------|------|---------|-----|-----|-------|------------|
| **WiFi Aware (NAN)** | 100m+ | 100+ Mbps | Medium | Partial | ✅ 8.0+ | ⏳ iOS 19 | ❌ | ✅ ESP32 | Medium |
| **BLE Mesh** | 30m (hop) | ~1 Mbps | Low | ✅ True | ✅ 4.3+ | ⚠️ Custom | ✅ | ✅ | High |
| **WiFi Direct** | 200m | 250 Mbps | High | ❌ | ✅ 4.0+ | ❌ | ❌ | ✅ | Low |
| **Apple AWDL** | 100m | 100+ Mbps | Medium | ❌ | ❌ | ✅ | ✅ | ❌ | N/A (private) |
| **Thread** | 30m (hop) | 250 Kbps | Very Low | ✅ True | ❌ | ❌ | ❌ | ✅ | High |
| **Multipeer (Apple)** | 30m BLE / 100m WiFi | Variable | Medium | ❌ | ❌ | ✅ | ✅ | ❌ | Low |

### Latency Analysis

| Technology | Discovery | Connection Setup | Per-Hop Latency |
|------------|-----------|------------------|-----------------|
| WiFi Aware | 1-5s | 100-500ms | N/A (star) |
| BLE Mesh | 1-3s | 200ms | ~300ms |
| WiFi Direct | 3-10s | 500ms-2s | N/A (P2P) |
| Thread | 1-2s | 100ms | ~50ms |

---

## Deep Dive: Each Technology

### 1. WiFi Aware / Neighbor Awareness Networking (NAN)

**The Game Changer 🎯**

WiFi Aware is the emerging standard for P2P WiFi discovery and data transfer. The EU's Digital Markets Act (DMA) is forcing Apple to adopt WiFi Aware in iOS 19, deprecating their proprietary AWDL protocol.

**Key Features:**
- Continuous, efficient discovery via synchronized Discovery Windows
- BLE-triggered "Instant Communication" mode for fast discovery
- Full WiFi PHY throughput (100+ Mbps)
- Works alongside infrastructure WiFi (can be on AP and P2P simultaneously)
- Standard WPA3 security

**Android Support:**
```kotlin
// Check WiFi Aware support
val wifiAwareManager = context.getSystemService(Context.WIFI_AWARE_SERVICE) as WifiAwareManager
if (packageManager.hasSystemFeature(PackageManager.FEATURE_WIFI_AWARE)) {
    // WiFi Aware supported (Android 8.0+)
}

// Publish a service
wifiAwareManager.attach(object : AttachCallback() {
    override fun onAttached(session: WifiAwareSession) {
        val config = PublishConfig.Builder()
            .setServiceName("atmosphere-mesh")
            .build()
        session.publish(config, publishCallback, handler)
    }
})

// Subscribe to discover peers
val subscribeConfig = SubscribeConfig.Builder()
    .setServiceName("atmosphere-mesh")
    .build()
session.subscribe(subscribeConfig, subscribeCallback, handler)
```

**iOS Support (iOS 19+):**
The EU mandate requires Apple to implement WiFi Aware 4.0 in iOS 19. Currently, iOS only exposes AWDL via MultipeerConnectivity framework, which doesn't interoperate with Android.

**Pros:**
- High throughput (~100+ Mbps)
- Cross-platform (Android now, iOS by 2025/2026)
- Can coexist with infrastructure WiFi
- BLE co-discovery supported
- Industry standard

**Cons:**
- iOS support not available yet (coming iOS 19)
- Not all Android devices support it (hardware dependent)
- Not true mesh (star topology), but can relay

---

### 2. BLE Mesh (Bluetooth Mesh)

**Universal Fallback 📡**

BLE Mesh is the official Bluetooth SIG standard for mesh networking. Uses managed flooding for message propagation.

**Key Features:**
- True mesh topology with up to 32,767 nodes
- Multi-hop message relay (TTL-based)
- Low power consumption
- Works on nearly all modern devices

**Android Implementation:**
```kotlin
// Using Nordic's nRF Mesh Library
implementation 'no.nordicsemi.android:mesh:3.4.0'

class AtmosphereMeshService : Service() {
    private lateinit var meshManagerApi: MeshManagerApi
    
    override fun onCreate() {
        meshManagerApi = MeshManagerApi(this)
        meshManagerApi.setMeshManagerCallbacks(meshCallbacks)
        meshManagerApi.loadMeshNetwork()
    }
    
    // Provisioning a new device
    fun provisionDevice(uuid: UUID) {
        meshManagerApi.identifyNode(uuid)
        meshManagerApi.startProvisioning(unprovisionedNode)
    }
    
    // Send message through mesh
    fun sendMessage(address: Int, message: ByteArray) {
        val appKey = meshNetwork.getAppKey(0)
        val vendorModelMessage = VendorModelMessage(appKey, message)
        meshManagerApi.createMeshPdu(address, vendorModelMessage)
    }
}
```

**iOS Considerations:**
- iOS doesn't have native BLE Mesh APIs
- Must implement BLE Mesh protocol on top of CoreBluetooth
- Can use libraries like ST's STBLEMesh
- More complex but achievable

**MTU Limitations:**
- BLE typically has 20-244 byte MTU
- Messages must be fragmented
- Consider CBOR or MessagePack for compact serialization

**Pros:**
- Universal device support
- True mesh topology
- Low power
- Works everywhere

**Cons:**
- Low throughput (~1 Mbps theoretical, often less)
- ~300ms latency per hop
- Complex to implement correctly
- MTU limitations require fragmentation

---

### 3. WiFi Direct (P2P)

**Android Legacy Option 📱**

WiFi Direct creates a soft AP for direct device-to-device connections.

**Android Implementation:**
```kotlin
class WifiDirectManager(context: Context) {
    private val manager = context.getSystemService(Context.WIFI_P2P_SERVICE) as WifiP2pManager
    private val channel = manager.initialize(context, Looper.getMainLooper(), null)
    
    fun discoverPeers() {
        manager.discoverPeers(channel, object : WifiP2pManager.ActionListener {
            override fun onSuccess() {
                // Discovery started
            }
            override fun onFailure(reason: Int) {
                // Handle failure
            }
        })
    }
    
    fun connectToPeer(device: WifiP2pDevice) {
        val config = WifiP2pConfig().apply {
            deviceAddress = device.deviceAddress
            wps.setup = WpsInfo.PBC
        }
        manager.connect(channel, config, connectListener)
    }
}
```

**Limitations:**
- Only ONE device can be group owner (soft AP)
- Not true mesh - requires topology management
- iOS doesn't support WiFi Direct
- High power consumption

**Pros:**
- High throughput (250 Mbps)
- Good range (200m)
- Simple API on Android

**Cons:**
- No iOS support
- High power
- Star topology only
- Can interfere with normal WiFi

---

### 4. Apple MultipeerConnectivity + AWDL

**Apple Ecosystem Only 🍎**

Apple's MultipeerConnectivity framework uses AWDL (Apple Wireless Direct Link) and BLE for device discovery and communication.

**Key Points:**
- Uses BLE for discovery, AWDL for data
- High performance (100+ Mbps)
- Seamless with normal WiFi usage
- **iOS 19 will deprecate AWDL for WiFi Aware** (per EU DMA mandate)

**Current Implementation:**
```swift
import MultipeerConnectivity

class AtmosphereMesh: NSObject, MCSessionDelegate, MCNearbyServiceBrowserDelegate {
    let serviceType = "atmosphere"
    var peerID: MCPeerID
    var session: MCSession
    var browser: MCNearbyServiceBrowser
    var advertiser: MCNearbyServiceAdvertiser
    
    override init() {
        peerID = MCPeerID(displayName: UIDevice.current.name)
        session = MCSession(peer: peerID, securityIdentity: nil, encryptionPreference: .required)
        browser = MCNearbyServiceBrowser(peer: peerID, serviceType: serviceType)
        advertiser = MCNearbyServiceAdvertiser(peer: peerID, discoveryInfo: nil, serviceType: serviceType)
        
        super.init()
        session.delegate = self
        browser.delegate = self
    }
    
    func send(data: Data, to peers: [MCPeerID]) {
        try? session.send(data, toPeers: peers, with: .reliable)
    }
}
```

**Limitations:**
- Max 8 peers in a session
- 6 peer limit over Bluetooth-only
- Apple devices only
- Will transition to WiFi Aware

---

### 5. Thread Protocol

**IoT Mesh Backbone 🏠**

Thread is an IPv6-based mesh protocol using 802.15.4 radio (same as Zigbee).

**Key Features:**
- True self-healing mesh
- Very low power
- IPv6 native
- Used by Matter for IoT

**The Catch:**
- Requires dedicated Thread radio (802.15.4)
- Most phones don't have Thread radios
- Border Routers bridge Thread ↔ IP networks

**Opportunity:**
- Many smart home devices already have Thread
- Could use Thread devices as mesh relay nodes
- Apple HomePod, Google Nest Hub have Thread border routers

**Integration Idea:**
```
Phone (WiFi/BLE) → Thread Border Router → Thread Mesh → Border Router → Phone
```

This requires:
1. Atmosphere-aware Thread device firmware
2. Protocol for routing Atmosphere messages over Thread
3. Discovery of Thread border routers on local network

---

## Recommended Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Atmosphere Transport Abstraction                     │
├─────────────────────────────────────────────────────────────────────────┤
│  TransportManager                                                        │
│  ├── selectBestTransport(peer, requirements) → Transport                │
│  ├── onTransportAvailable(callback)                                     │
│  └── sendMessage(peer, data, priority)                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │  WebSocket  │  │ WiFi Aware  │  │  BLE Mesh   │  │ WiFi Direct │    │
│  │  (primary)  │  │  (offline)  │  │ (fallback)  │  │  (Android)  │    │
│  │             │  │             │  │             │  │             │    │
│  │ • Internet  │  │ • P2P WiFi  │  │ • Universal │  │ • Legacy    │    │
│  │ • Relay     │  │ • 100+ Mbps │  │ • True mesh │  │ • Fast      │    │
│  │ • Cloud     │  │ • Cross-plat│  │ • Low power │  │ • No iOS    │    │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘    │
│         │                │                │                │            │
│         └────────────────┴────────────────┴────────────────┘            │
│                          ↓                                              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    Peer Discovery Service                        │   │
│  │  • Unifies discovery across all transports                       │   │
│  │  • Maintains peer registry with reachability info                │   │
│  │  • Handles transport failover                                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Transport Selection Logic

```python
def select_transport(peer: Peer, message: Message) -> Transport:
    """Select the best transport for a message to a peer."""
    
    # Priority order (fast → universal)
    transports = [
        WebSocketTransport,  # Internet available
        WifiAwareTransport,  # Offline, high bandwidth
        WifiDirectTransport, # Android offline
        BleMeshTransport,    # Universal fallback
    ]
    
    for transport in transports:
        if transport.is_available() and transport.can_reach(peer):
            if message.size > transport.max_message_size:
                continue  # Too big for this transport
            if message.priority == 'realtime' and transport.latency > 100:
                continue  # Too slow for realtime
            return transport
    
    raise NoRouteError(f"Cannot reach peer {peer.id}")
```

### Message Format (Compact for BLE)

```
┌─────────────────────────────────────────────┐
│ Atmosphere Mesh Message (CBOR encoded)      │
├──────────┬──────────────────────────────────┤
│ version  │ 1 byte                           │
│ type     │ 1 byte (data/ack/discover/route) │
│ ttl      │ 1 byte                           │
│ flags    │ 1 byte                           │
│ src_id   │ 8 bytes (truncated node ID)      │
│ dst_id   │ 8 bytes (or broadcast 0xFF...)   │
│ seq      │ 2 bytes                          │
│ payload  │ variable (max ~200 bytes for BLE)│
│ checksum │ 2 bytes                          │
└──────────┴──────────────────────────────────┘

Total header: 24 bytes
Max BLE payload: ~220 bytes (with 244 MTU)
```

---

## Implementation Phases

### Phase 1: Foundation (2 weeks)
- [ ] Create `TransportManager` abstraction
- [ ] Implement `BleMeshTransport` for Android
- [ ] Basic peer discovery over BLE
- [ ] Message routing with TTL

### Phase 2: WiFi Aware (2 weeks)
- [ ] Implement `WifiAwareTransport` for Android
- [ ] Hybrid discovery (BLE trigger → WiFi Aware data)
- [ ] Transport failover logic

### Phase 3: iOS Support (3 weeks)
- [ ] Implement BLE Mesh on iOS (CoreBluetooth)
- [ ] MultipeerConnectivity bridge (temporary)
- [ ] Prepare for WiFi Aware when iOS 19 releases

### Phase 4: Thread Integration (4 weeks)
- [ ] Research Matter/Thread SDK integration
- [ ] Prototype Thread border router discovery
- [ ] Custom Atmosphere-over-Thread protocol

---

## Security Considerations

### Mesh Security Requirements
1. **Node Authentication** - Only authorized nodes join mesh
2. **Message Encryption** - End-to-end for sensitive data
3. **Replay Protection** - Sequence numbers + timestamps
4. **Mesh Key Distribution** - Secure provisioning

### Proposed Security Model
```
┌─────────────────────────────────────────────────┐
│ Layer 3: Atmosphere Protocol                    │
│  • End-to-end encryption (node ↔ node)         │
│  • Signed capability advertisements             │
├─────────────────────────────────────────────────┤
│ Layer 2: Mesh Network Key                       │
│  • Shared secret for mesh membership            │
│  • Derived from mesh creation token             │
├─────────────────────────────────────────────────┤
│ Layer 1: Transport Security                     │
│  • BLE: LE Secure Connections                   │
│  • WiFi Aware: WPA3                            │
│  • Thread: Native Thread security               │
└─────────────────────────────────────────────────┘
```

---

## References

1. [Nordic nRF Mesh Library](https://github.com/NordicSemiconductor/Android-nRF-Mesh-Library)
2. [BE-Mesh Android BLE Library](https://github.com/netlab-sapienza/android-ble-mesh)
3. [WiFi Aware Android Docs](https://developer.android.com/develop/connectivity/wifi/wifi-aware)
4. [Ditto: Cross-Platform P2P WiFi](https://www.ditto.com/blog/cross-platform-p2p-wi-fi-how-the-eu-killed-awdl)
5. [Thread Protocol - Home Assistant](https://www.home-assistant.io/integrations/thread/)
6. [Apple MultipeerConnectivity](https://developer.apple.com/documentation/multipeerconnectivity)
7. EU DMA WiFi Aware Mandate (iOS 19 requirement)

---

## Conclusion

The offline mesh problem is solvable with current technology. The key insight is that **WiFi Aware is becoming the universal standard** - Apple's forced adoption via EU DMA will enable true cross-platform P2P WiFi by iOS 19.

**Immediate actions:**
1. Build on BLE Mesh as the universal fallback
2. Implement WiFi Aware for Android (ready now)
3. Use MultipeerConnectivity for iOS (bridge until iOS 19)
4. Design the transport abstraction to handle multiple paths

**Long-term vision:**
- WiFi Aware as primary offline transport (fast, cross-platform)
- BLE Mesh for ultra-low-power scenarios
- Thread integration for IoT mesh expansion
- Seamless failover between all transports
