# WiFi Direct & WiFi Aware Design for Atmosphere

**Purpose:** Design high-bandwidth offline transports using WiFi Direct (legacy Android) and WiFi Aware (modern cross-platform).

---

## Overview

WiFi-based P2P provides 10-100x the bandwidth of BLE Mesh, making it ideal for larger data transfers and real-time communication. This document covers both:

1. **WiFi Aware (NAN)** - The future standard (cross-platform by iOS 19)
2. **WiFi Direct** - Legacy Android-only fallback

---

## WiFi Aware (Recommended)

### Why WiFi Aware?

The EU Digital Markets Act (DMA) is forcing Apple to adopt WiFi Aware in iOS 19, replacing the proprietary AWDL protocol. This creates a true cross-platform P2P WiFi standard for the first time.

**Key advantages:**
- ~100+ Mbps throughput
- BLE-triggered discovery (low power until needed)
- Works alongside infrastructure WiFi
- Will work across Android, iOS, macOS, Linux

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     AtmosphereWifiAwareTransport                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────┐                    ┌──────────────────────┐       │
│  │  Discovery Layer │                    │  Data Path Layer     │       │
│  │                  │                    │                      │       │
│  │ • Publish        │                    │ • Network Specifier  │       │
│  │ • Subscribe      │                    │ • Socket Connection  │       │
│  │ • Match Callback │───────────────────▶│ • Data Transfer      │       │
│  │                  │   On peer found    │                      │       │
│  └──────────────────┘                    └──────────────────────┘       │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                     WiFi Aware Session                            │  │
│  │                                                                    │  │
│  │  • Attach to WiFi Aware cluster                                   │  │
│  │  • Maintain session across publish/subscribe                      │  │
│  │  • Handle session termination/recovery                            │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Android Implementation

```kotlin
class AtmosphereWifiAwareService : Service() {
    
    companion object {
        const val SERVICE_NAME = "atmosphere-mesh"
        const val PORT = 11452
    }
    
    private lateinit var wifiAwareManager: WifiAwareManager
    private var wifiAwareSession: WifiAwareSession? = null
    private val connectedPeers = mutableMapOf<String, PeerConnection>()
    
    override fun onCreate() {
        super.onCreate()
        
        if (!packageManager.hasSystemFeature(PackageManager.FEATURE_WIFI_AWARE)) {
            Log.e(TAG, "WiFi Aware not supported on this device")
            return
        }
        
        wifiAwareManager = getSystemService(Context.WIFI_AWARE_SERVICE) as WifiAwareManager
        attachToWifiAware()
    }
    
    private fun attachToWifiAware() {
        wifiAwareManager.attach(object : AttachCallback() {
            override fun onAttached(session: WifiAwareSession) {
                wifiAwareSession = session
                startPublishing()
                startSubscribing()
            }
            
            override fun onAttachFailed() {
                Log.e(TAG, "Failed to attach to WiFi Aware")
                // Retry with backoff
                handler.postDelayed({ attachToWifiAware() }, 5000)
            }
        }, handler)
    }
    
    // MARK: - Publishing (Advertising our presence)
    
    private fun startPublishing() {
        val config = PublishConfig.Builder()
            .setServiceName(SERVICE_NAME)
            .setServiceSpecificInfo(buildServiceInfo())
            .build()
        
        wifiAwareSession?.publish(config, object : DiscoverySessionCallback() {
            override fun onPublishStarted(session: PublishDiscoverySession) {
                publishSession = session
            }
            
            override fun onMessageReceived(peerHandle: PeerHandle, message: ByteArray) {
                handleDiscoveryMessage(peerHandle, message)
            }
        }, handler)
    }
    
    private fun buildServiceInfo(): ByteArray {
        // Include mesh ID and node capabilities in service info
        return JSONObject().apply {
            put("mesh_id", meshId)
            put("node_id", nodeId)
            put("capabilities", capabilities.toJson())
        }.toString().toByteArray()
    }
    
    // MARK: - Subscribing (Discovering peers)
    
    private fun startSubscribing() {
        val config = SubscribeConfig.Builder()
            .setServiceName(SERVICE_NAME)
            .build()
        
        wifiAwareSession?.subscribe(config, object : DiscoverySessionCallback() {
            override fun onSubscribeStarted(session: SubscribeDiscoverySession) {
                subscribeSession = session
            }
            
            override fun onServiceDiscovered(
                peerHandle: PeerHandle,
                serviceSpecificInfo: ByteArray,
                matchFilter: List<ByteArray>
            ) {
                handlePeerDiscovered(peerHandle, serviceSpecificInfo)
            }
        }, handler)
    }
    
    private fun handlePeerDiscovered(peerHandle: PeerHandle, serviceInfo: ByteArray) {
        val info = JSONObject(String(serviceInfo))
        val peerMeshId = info.getString("mesh_id")
        
        // Only connect to peers in the same mesh
        if (peerMeshId != meshId) return
        
        // Initiate data path
        initiateDataPath(peerHandle)
    }
    
    // MARK: - Data Path (High-speed connection)
    
    private fun initiateDataPath(peerHandle: PeerHandle) {
        val networkSpecifier = WifiAwareNetworkSpecifier.Builder(subscribeSession!!, peerHandle)
            .setPskPassphrase(meshKey) // Use mesh key for authentication
            .setPort(PORT)
            .build()
        
        val networkRequest = NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_WIFI_AWARE)
            .setNetworkSpecifier(networkSpecifier)
            .build()
        
        connectivityManager.requestNetwork(networkRequest, object : NetworkCallback() {
            override fun onAvailable(network: Network) {
                // Network is ready, get peer's IPv6 address
            }
            
            override fun onCapabilitiesChanged(
                network: Network,
                networkCapabilities: NetworkCapabilities
            ) {
                val peerAwareInfo = networkCapabilities.transportInfo as WifiAwareNetworkInfo
                val peerIpv6 = peerAwareInfo.peerIpv6Addr
                val peerPort = peerAwareInfo.port
                
                // Connect via socket
                connectToPeer(network, peerIpv6, peerPort)
            }
            
            override fun onLost(network: Network) {
                handlePeerDisconnected(peerHandle)
            }
        })
    }
    
    private fun connectToPeer(network: Network, address: Inet6Address, port: Int) {
        thread {
            try {
                val socket = network.socketFactory.createSocket()
                socket.connect(InetSocketAddress(address, port), 10000)
                
                // Start message handling
                val connection = PeerConnection(socket)
                connectedPeers[address.hostAddress!!] = connection
                
                // Notify transport layer
                onPeerConnected(connection)
                
                // Read loop
                connection.startReading { message ->
                    handleMessage(message)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to connect to peer", e)
            }
        }
    }
    
    // MARK: - Accept incoming connections (Server side)
    
    private fun startServer() {
        thread {
            val serverSocket = ServerSocket(PORT)
            
            while (!Thread.currentThread().isInterrupted) {
                try {
                    val socket = serverSocket.accept()
                    handleIncomingConnection(socket)
                } catch (e: Exception) {
                    Log.e(TAG, "Server error", e)
                }
            }
        }
    }
    
    // MARK: - Message sending
    
    fun sendMessage(message: ByteArray, destination: String?) {
        if (destination == null) {
            // Broadcast to all peers
            for (peer in connectedPeers.values) {
                peer.send(message)
            }
        } else {
            connectedPeers[destination]?.send(message)
        }
    }
}
```

### iOS Implementation (Preparing for iOS 19)

Until iOS 19 with WiFi Aware, use MultipeerConnectivity as a bridge:

```swift
import MultipeerConnectivity
import Network

class AtmosphereWifiTransport: NSObject {
    
    // Current: MultipeerConnectivity (iOS 13+)
    // Future: WiFi Aware (iOS 19+)
    
    private var peerID: MCPeerID!
    private var session: MCSession!
    private var advertiser: MCNearbyServiceAdvertiser!
    private var browser: MCNearbyServiceBrowser!
    
    static let serviceType = "atmosphere" // Max 15 chars, lowercase/hyphen only
    
    override init() {
        super.init()
        
        peerID = MCPeerID(displayName: nodeId)
        session = MCSession(
            peer: peerID,
            securityIdentity: nil,
            encryptionPreference: .required
        )
        session.delegate = self
        
        // Advertise our presence
        advertiser = MCNearbyServiceAdvertiser(
            peer: peerID,
            discoveryInfo: ["mesh": meshId, "node": nodeId],
            serviceType: Self.serviceType
        )
        advertiser.delegate = self
        
        // Discover peers
        browser = MCNearbyServiceBrowser(peer: peerID, serviceType: Self.serviceType)
        browser.delegate = self
    }
    
    func start() {
        advertiser.startAdvertisingPeer()
        browser.startBrowsingForPeers()
    }
    
    func send(_ data: Data, to peers: [MCPeerID]? = nil) throws {
        let targets = peers ?? session.connectedPeers
        try session.send(data, toPeers: targets, with: .reliable)
    }
}

// MARK: - MCSessionDelegate

extension AtmosphereWifiTransport: MCSessionDelegate {
    func session(_ session: MCSession, peer peerID: MCPeerID, didChange state: MCSessionState) {
        switch state {
        case .connected:
            onPeerConnected(peerID)
        case .notConnected:
            onPeerDisconnected(peerID)
        case .connecting:
            break
        @unknown default:
            break
        }
    }
    
    func session(_ session: MCSession, didReceive data: Data, fromPeer peerID: MCPeerID) {
        handleMessage(data, from: peerID)
    }
    
    // ... other delegate methods
}

// MARK: - MCNearbyServiceBrowserDelegate

extension AtmosphereWifiTransport: MCNearbyServiceBrowserDelegate {
    func browser(_ browser: MCNearbyServiceBrowser, 
                 foundPeer peerID: MCPeerID, 
                 withDiscoveryInfo info: [String: String]?) {
        // Check if same mesh
        guard info?["mesh"] == meshId else { return }
        
        // Invite to session
        browser.invitePeer(peerID, to: session, withContext: nil, timeout: 30)
    }
    
    func browser(_ browser: MCNearbyServiceBrowser, lostPeer peerID: MCPeerID) {
        // Peer lost
    }
}
```

### WiFi Aware Message Protocol

Since WiFi Aware provides a raw socket connection, use a simple framed protocol:

```
┌───────────────────────────────────────────────────┐
│         WiFi Aware Message Frame                  │
├──────────┬──────────┬─────────────────────────────┤
│ Length   │ Type     │ Payload                     │
│ 4 bytes  │ 1 byte   │ Variable                    │
└──────────┴──────────┴─────────────────────────────┘

Length: Total message length (big-endian uint32)
Type: Message type (same as BLE mesh types)
Payload: CBOR-encoded message body
```

```kotlin
class WifiAwareProtocol {
    
    fun writeMessage(output: OutputStream, type: Byte, payload: ByteArray) {
        val length = 1 + payload.size
        output.write(ByteBuffer.allocate(4).putInt(length).array())
        output.write(byteArrayOf(type))
        output.write(payload)
        output.flush()
    }
    
    fun readMessage(input: InputStream): Pair<Byte, ByteArray>? {
        val lengthBytes = ByteArray(4)
        if (input.read(lengthBytes) != 4) return null
        
        val length = ByteBuffer.wrap(lengthBytes).int
        if (length <= 0 || length > MAX_MESSAGE_SIZE) return null
        
        val type = input.read().toByte()
        val payload = ByteArray(length - 1)
        input.readFully(payload)
        
        return type to payload
    }
}
```

---

## WiFi Direct (Legacy Fallback)

WiFi Direct is the older P2P WiFi standard. Use as fallback on Android when WiFi Aware is unavailable.

### Limitations

- **No iOS support**
- Only one device can be Group Owner (soft AP)
- Can disconnect from infrastructure WiFi
- More battery intensive
- Longer discovery times

### When to Use

```kotlin
fun selectWifiTransport(): WifiTransport {
    return when {
        // Prefer WiFi Aware when available
        hasWifiAware() -> WifiAwareTransport()
        // Fall back to WiFi Direct on Android
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.ICE_CREAM_SANDWICH -> WifiDirectTransport()
        // No WiFi P2P available
        else -> null
    }
}
```

### Android Implementation

```kotlin
class AtmosphereWifiDirectService : Service() {
    
    private lateinit var manager: WifiP2pManager
    private lateinit var channel: WifiP2pManager.Channel
    private val connectedPeers = mutableMapOf<String, Socket>()
    
    private val intentFilter = IntentFilter().apply {
        addAction(WifiP2pManager.WIFI_P2P_STATE_CHANGED_ACTION)
        addAction(WifiP2pManager.WIFI_P2P_PEERS_CHANGED_ACTION)
        addAction(WifiP2pManager.WIFI_P2P_CONNECTION_CHANGED_ACTION)
        addAction(WifiP2pManager.WIFI_P2P_THIS_DEVICE_CHANGED_ACTION)
    }
    
    override fun onCreate() {
        super.onCreate()
        manager = getSystemService(Context.WIFI_P2P_SERVICE) as WifiP2pManager
        channel = manager.initialize(this, mainLooper, null)
        registerReceiver(receiver, intentFilter)
    }
    
    // MARK: - Peer Discovery
    
    fun startDiscovery() {
        manager.discoverPeers(channel, object : WifiP2pManager.ActionListener {
            override fun onSuccess() {
                Log.d(TAG, "Discovery started")
            }
            
            override fun onFailure(reason: Int) {
                Log.e(TAG, "Discovery failed: $reason")
            }
        })
    }
    
    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            when (intent.action) {
                WifiP2pManager.WIFI_P2P_PEERS_CHANGED_ACTION -> {
                    manager.requestPeers(channel) { peers ->
                        handlePeersDiscovered(peers.deviceList)
                    }
                }
                
                WifiP2pManager.WIFI_P2P_CONNECTION_CHANGED_ACTION -> {
                    val networkInfo = intent.getParcelableExtra<NetworkInfo>(
                        WifiP2pManager.EXTRA_NETWORK_INFO
                    )
                    if (networkInfo?.isConnected == true) {
                        manager.requestConnectionInfo(channel) { info ->
                            handleConnectionInfo(info)
                        }
                    }
                }
            }
        }
    }
    
    private fun handlePeersDiscovered(devices: Collection<WifiP2pDevice>) {
        for (device in devices) {
            // Filter by device name (must contain our mesh ID)
            if (device.deviceName.contains(meshId)) {
                connectToPeer(device)
            }
        }
    }
    
    // MARK: - Connection
    
    private fun connectToPeer(device: WifiP2pDevice) {
        val config = WifiP2pConfig().apply {
            deviceAddress = device.deviceAddress
            wps.setup = WpsInfo.PBC
            // Prefer being client (let others be GO)
            groupOwnerIntent = 0
        }
        
        manager.connect(channel, config, object : WifiP2pManager.ActionListener {
            override fun onSuccess() {
                Log.d(TAG, "Connection initiated to ${device.deviceName}")
            }
            
            override fun onFailure(reason: Int) {
                Log.e(TAG, "Connection failed: $reason")
            }
        })
    }
    
    private fun handleConnectionInfo(info: WifiP2pInfo) {
        if (info.groupFormed) {
            if (info.isGroupOwner) {
                // We're the server - start accepting connections
                startServer()
            } else {
                // We're a client - connect to group owner
                connectToGroupOwner(info.groupOwnerAddress)
            }
        }
    }
    
    // MARK: - Data Transfer
    
    private fun startServer() {
        thread {
            val serverSocket = ServerSocket(PORT)
            while (!Thread.currentThread().isInterrupted) {
                try {
                    val client = serverSocket.accept()
                    handleClientConnection(client)
                } catch (e: Exception) {
                    Log.e(TAG, "Server error", e)
                }
            }
        }
    }
    
    private fun connectToGroupOwner(address: InetAddress) {
        thread {
            try {
                val socket = Socket()
                socket.connect(InetSocketAddress(address, PORT), 10000)
                handleConnection(socket)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to connect to GO", e)
            }
        }
    }
    
    companion object {
        const val PORT = 11453
    }
}
```

### Group Owner Selection Strategy

Since only one device can be Group Owner, use a deterministic selection:

```kotlin
fun calculateGroupOwnerIntent(myNodeId: String, peerNodeId: String): Int {
    // Higher intent = more likely to be GO
    // Use lexicographic comparison of node IDs for consistency
    return when {
        myNodeId < peerNodeId -> 15  // I should be GO
        myNodeId > peerNodeId -> 0   // Peer should be GO
        else -> 7  // Same ID (shouldn't happen), random
    }
}
```

---

## Hybrid Discovery: BLE → WiFi

For power efficiency, use BLE for discovery and WiFi for data:

```kotlin
class HybridDiscovery {
    
    private val bleScanner = BleScanner()
    private val wifiAware = WifiAwareTransport()
    
    fun start() {
        // Start low-power BLE scan for Atmosphere nodes
        bleScanner.scanForService(ATMOSPHERE_BLE_UUID) { device ->
            // Found a peer via BLE, now establish WiFi Aware connection
            val serviceInfo = device.serviceData
            val peerNodeId = serviceInfo.nodeId
            
            // Trigger WiFi Aware discovery for this specific peer
            wifiAware.discoverPeer(peerNodeId) { connection ->
                // High-bandwidth connection established
                onPeerConnected(connection)
            }
        }
    }
}
```

This mirrors how Apple's AirDrop works: BLE for discovery, AWDL/WiFi for transfer.

---

## Transport Selection

```kotlin
class TransportManager {
    
    private val transports = listOf(
        WebSocketTransport(),      // Internet (primary)
        WifiAwareTransport(),      // Offline, high bandwidth
        WifiDirectTransport(),     // Android fallback
        BleMeshTransport()         // Universal fallback
    )
    
    fun getBestTransport(peer: PeerId, requirements: Requirements): Transport? {
        for (transport in transports) {
            if (!transport.isAvailable()) continue
            if (!transport.canReach(peer)) continue
            
            if (requirements.minBandwidth > transport.estimatedBandwidth) continue
            if (requirements.maxLatency < transport.estimatedLatency) continue
            
            return transport
        }
        return null
    }
    
    fun sendWithFallback(peer: PeerId, message: ByteArray, requirements: Requirements) {
        var lastError: Exception? = null
        
        for (transport in transports) {
            if (!transport.isAvailable()) continue
            
            try {
                if (transport.canReach(peer)) {
                    transport.send(peer, message)
                    return
                }
            } catch (e: Exception) {
                lastError = e
                Log.w(TAG, "Transport ${transport.name} failed, trying next", e)
            }
        }
        
        throw NoRouteException("All transports failed", lastError)
    }
}
```

---

## Performance Comparison

| Metric | WiFi Aware | WiFi Direct | BLE Mesh |
|--------|------------|-------------|----------|
| Discovery time | 1-3s | 3-10s | 1-3s |
| Connection setup | 0.5-2s | 2-5s | 0.5s |
| Throughput | 100+ Mbps | 250 Mbps | ~1 Mbps |
| Latency | 10-50ms | 20-100ms | 200-400ms/hop |
| Power (active) | Medium | High | Low |
| Power (idle) | Low | High | Very Low |
| iOS support | iOS 19+ | ❌ | ✅ (custom) |

---

## Security

### WiFi Aware Authentication

Use PSK (Pre-Shared Key) derived from mesh key:

```kotlin
val networkSpecifier = WifiAwareNetworkSpecifier.Builder(session, peerHandle)
    .setPskPassphrase(deriveWifiPsk(meshKey))
    .build()

fun deriveWifiPsk(meshKey: ByteArray): String {
    // Derive a WPA2-compatible PSK (8-63 ASCII chars)
    val hash = MessageDigest.getInstance("SHA-256").digest(meshKey + "wifi-psk".toByteArray())
    return Base64.encodeToString(hash, Base64.NO_WRAP).take(32)
}
```

### WiFi Direct Security

Use WPS PBC (Push Button Configuration) for initial connection, then authenticate at application layer using mesh key.

---

## Implementation Priority

1. **WiFi Aware (Android)** - Start now, best future-proof option
2. **MultipeerConnectivity (iOS)** - Bridge until iOS 19
3. **WiFi Direct (Android)** - Fallback for older devices
4. **BLE Mesh** - Universal fallback (see BLE_MESH_DESIGN.md)

---

## Next Steps

1. Implement `WifiAwareTransport` for Android
2. Test WiFi Aware on physical devices (emulators don't support it)
3. Implement hybrid BLE → WiFi discovery
4. Monitor iOS 19 beta for WiFi Aware API availability
5. Create transport abstraction layer
