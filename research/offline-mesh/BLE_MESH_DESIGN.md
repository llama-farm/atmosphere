# BLE Mesh Design for Atmosphere

**Purpose:** Design a BLE-based mesh transport for Atmosphere that works offline across Android and iOS.

---

## Overview

BLE Mesh provides a universal fallback transport for Atmosphere when WiFi and internet are unavailable. While slower than WiFi-based options, it works on virtually all modern devices and provides true mesh topology with multi-hop routing.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        AtmosphereBleTransport                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │  Discovery Layer │    │  Routing Layer   │    │  Message Layer   │  │
│  │                  │    │                  │    │                  │  │
│  │ • BLE Advertise  │    │ • Flood routing  │    │ • Fragmentation  │  │
│  │ • BLE Scan       │    │ • TTL management │    │ • Reassembly     │  │
│  │ • Peer registry  │    │ • Loop detection │    │ • Encryption     │  │
│  └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘  │
│           │                       │                       │             │
│           └───────────────────────┼───────────────────────┘             │
│                                   │                                      │
│  ┌────────────────────────────────┴─────────────────────────────────┐  │
│  │                     BLE GATT Server/Client                        │  │
│  │                                                                    │  │
│  │  Service: A7M0-MESH-0001-0000-000000000001                       │  │
│  │  ├── Characteristic: TX (Write, Notify) - Send messages          │  │
│  │  ├── Characteristic: RX (Read, Notify) - Receive messages        │  │
│  │  └── Characteristic: INFO (Read) - Node capabilities             │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Protocol Design

### Service UUID

```
Atmosphere Mesh Service: A7M0MESH-0001-0000-0000-000000000001

Characteristics:
- TX:   A7M0MESH-0001-0001-0000-000000000001 (Write, Notify)
- RX:   A7M0MESH-0001-0002-0000-000000000001 (Read, Notify) 
- INFO: A7M0MESH-0001-0003-0000-000000000001 (Read)
```

### Message Format

Using CBOR for compact binary encoding:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Atmosphere BLE Message                        │
├──────────┬──────────┬───────────────────────────────────────────┤
│  Header  │  8 bytes │ Fixed-size header                         │
│  Payload │ Variable │ CBOR-encoded data                         │
└──────────┴──────────┴───────────────────────────────────────────┘

Header Layout (8 bytes):
┌────┬────┬────┬────┬────────┬────────┬────────┐
│ V  │ T  │TTL │ F  │ SEQ    │ FRAG   │ TOTAL  │
│ 1  │ 1  │ 1  │ 1  │ 2      │ 1      │ 1      │
└────┴────┴────┴────┴────────┴────────┴────────┘

V:     Version (1)
T:     Type (see below)
TTL:   Time-to-live (hops remaining)
F:     Flags (encrypted, priority, etc.)
SEQ:   Sequence number
FRAG:  Fragment index (0-based)
TOTAL: Total fragments (1 = not fragmented)
```

### Message Types

```python
class MessageType(Enum):
    # Discovery
    HELLO = 0x01        # Node announcement
    HELLO_ACK = 0x02    # Response to HELLO
    GOODBYE = 0x03      # Node leaving
    
    # Routing
    ROUTE_REQ = 0x10    # Route discovery
    ROUTE_REP = 0x11    # Route reply
    
    # Data
    DATA = 0x20         # Application data
    DATA_ACK = 0x21     # Delivery confirmation
    
    # Mesh management
    MESH_INFO = 0x30    # Mesh topology info
    CAPABILITY = 0x31   # Node capability advertisement
```

### Flags Byte

```
Bit 0: Encrypted (1 = payload encrypted with mesh key)
Bit 1: Broadcast (1 = send to all nodes)
Bit 2: Priority (1 = high priority, skip queue)
Bit 3: Reliable (1 = require ACK)
Bits 4-7: Reserved
```

---

## Fragmentation

BLE MTU is typically 20-244 bytes. With a 244 byte MTU:
- Header: 8 bytes
- Available payload: 236 bytes per fragment

### Fragmentation Algorithm

```python
MAX_FRAGMENT_SIZE = 236  # Assuming 244 MTU

def fragment_message(message: bytes, seq: int) -> List[bytes]:
    """Fragment a message for BLE transmission."""
    fragments = []
    total = (len(message) + MAX_FRAGMENT_SIZE - 1) // MAX_FRAGMENT_SIZE
    
    for i in range(total):
        start = i * MAX_FRAGMENT_SIZE
        end = min(start + MAX_FRAGMENT_SIZE, len(message))
        
        header = struct.pack(
            'BBBBHBB',
            1,              # version
            MessageType.DATA.value,
            DEFAULT_TTL,
            0,              # flags
            seq,
            i,              # fragment index
            total           # total fragments
        )
        
        fragments.append(header + message[start:end])
    
    return fragments

def reassemble_message(fragments: Dict[int, bytes]) -> bytes:
    """Reassemble fragments into complete message."""
    total = struct.unpack('B', fragments[0][7:8])[0]
    
    if len(fragments) != total:
        raise IncompleteMessage()
    
    # Sort by fragment index and concatenate payloads
    sorted_frags = sorted(fragments.items())
    return b''.join(frag[8:] for _, frag in sorted_frags)
```

---

## Routing Algorithm

Using **managed flooding** with optimizations:

### Basic Flooding

```python
class MeshRouter:
    def __init__(self):
        self.seen_messages = LRUCache(maxsize=1000)
        self.peers = {}  # mac_addr -> PeerInfo
    
    def route_message(self, message: bytes, source: str):
        """Route incoming message through mesh."""
        header = parse_header(message)
        
        # Check for duplicate (loop prevention)
        msg_id = (header.source_id, header.seq)
        if msg_id in self.seen_messages:
            return  # Already processed
        self.seen_messages[msg_id] = time.time()
        
        # Check TTL
        if header.ttl <= 0:
            return  # Expired
        
        # Decrement TTL for forwarding
        new_ttl = header.ttl - 1
        
        # Check if we're the destination
        if header.is_for_us():
            self.deliver_message(message)
            return
        
        # Forward to all peers except source
        if new_ttl > 0:
            forwarded = self.update_ttl(message, new_ttl)
            for peer in self.peers.values():
                if peer.mac != source:
                    peer.send(forwarded)
```

### Optimizations

1. **Gossip-based forwarding:** Only forward to random subset of peers
2. **RSSI-based priority:** Prefer stronger connections
3. **Load balancing:** Track peer queue depth, avoid overloaded nodes
4. **Adaptive TTL:** Reduce TTL in dense networks

```python
def smart_forward(self, message: bytes, source: str):
    """Intelligent message forwarding."""
    peers = [p for p in self.peers.values() if p.mac != source]
    
    if len(peers) <= 3:
        # Small network: flood to all
        targets = peers
    else:
        # Large network: gossip to subset
        # Prioritize by RSSI and queue depth
        scored = [(p.rssi - p.queue_depth * 10, p) for p in peers]
        scored.sort(reverse=True)
        
        # Forward to top 50% + random selection
        n = max(2, len(peers) // 2)
        targets = [p for _, p in scored[:n]]
    
    for peer in targets:
        peer.send(message)
```

---

## Android Implementation

```kotlin
class AtmosphereBleService : Service() {
    
    companion object {
        val MESH_SERVICE_UUID = UUID.fromString("A7M0MESH-0001-0000-0000-000000000001")
        val TX_CHAR_UUID = UUID.fromString("A7M0MESH-0001-0001-0000-000000000001")
        val RX_CHAR_UUID = UUID.fromString("A7M0MESH-0001-0002-0000-000000000001")
        val INFO_CHAR_UUID = UUID.fromString("A7M0MESH-0001-0003-0000-000000000001")
    }
    
    private lateinit var bluetoothManager: BluetoothManager
    private lateinit var advertiser: BluetoothLeAdvertiser
    private lateinit var scanner: BluetoothLeScanner
    private lateinit var gattServer: BluetoothGattServer
    
    private val connectedPeers = mutableMapOf<String, BluetoothDevice>()
    private val router = MeshRouter()
    
    override fun onCreate() {
        super.onCreate()
        bluetoothManager = getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        setupGattServer()
        startAdvertising()
        startScanning()
    }
    
    private fun setupGattServer() {
        gattServer = bluetoothManager.openGattServer(this, gattCallback)
        
        val service = BluetoothGattService(
            MESH_SERVICE_UUID,
            BluetoothGattService.SERVICE_TYPE_PRIMARY
        )
        
        val txChar = BluetoothGattCharacteristic(
            TX_CHAR_UUID,
            BluetoothGattCharacteristic.PROPERTY_WRITE or
                BluetoothGattCharacteristic.PROPERTY_NOTIFY,
            BluetoothGattCharacteristic.PERMISSION_WRITE
        )
        
        val rxChar = BluetoothGattCharacteristic(
            RX_CHAR_UUID,
            BluetoothGattCharacteristic.PROPERTY_READ or
                BluetoothGattCharacteristic.PROPERTY_NOTIFY,
            BluetoothGattCharacteristic.PERMISSION_READ
        )
        
        service.addCharacteristic(txChar)
        service.addCharacteristic(rxChar)
        gattServer.addService(service)
    }
    
    private fun startAdvertising() {
        val settings = AdvertiseSettings.Builder()
            .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
            .setConnectable(true)
            .setTimeout(0)
            .build()
        
        val data = AdvertiseData.Builder()
            .addServiceUuid(ParcelUuid(MESH_SERVICE_UUID))
            .setIncludeDeviceName(false)
            .build()
        
        advertiser = bluetoothManager.adapter.bluetoothLeAdvertiser
        advertiser.startAdvertising(settings, data, advertiseCallback)
    }
    
    private fun startScanning() {
        val filter = ScanFilter.Builder()
            .setServiceUuid(ParcelUuid(MESH_SERVICE_UUID))
            .build()
        
        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build()
        
        scanner = bluetoothManager.adapter.bluetoothLeScanner
        scanner.startScan(listOf(filter), settings, scanCallback)
    }
    
    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            val device = result.device
            if (!connectedPeers.containsKey(device.address)) {
                connectToPeer(device)
            }
        }
    }
    
    private fun connectToPeer(device: BluetoothDevice) {
        device.connectGatt(this, false, object : BluetoothGattCallback() {
            override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
                if (newState == BluetoothProfile.STATE_CONNECTED) {
                    connectedPeers[device.address] = device
                    gatt.discoverServices()
                } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                    connectedPeers.remove(device.address)
                }
            }
            
            override fun onCharacteristicChanged(
                gatt: BluetoothGatt,
                characteristic: BluetoothGattCharacteristic,
                value: ByteArray
            ) {
                if (characteristic.uuid == RX_CHAR_UUID) {
                    router.handleIncomingMessage(value, device.address)
                }
            }
        })
    }
    
    fun sendMessage(message: ByteArray, destination: String?) {
        val fragments = router.fragmentMessage(message)
        
        for (fragment in fragments) {
            if (destination == null) {
                // Broadcast to all peers
                for (device in connectedPeers.values) {
                    sendToPeer(device, fragment)
                }
            } else {
                // Route to specific destination
                router.route(fragment, destination)
            }
        }
    }
    
    private fun sendToPeer(device: BluetoothDevice, data: ByteArray) {
        // Implementation depends on connection state
        // Either write to GATT client or notify via GATT server
    }
}
```

---

## iOS Implementation

iOS requires implementing BLE Mesh on top of CoreBluetooth:

```swift
import CoreBluetooth

class AtmosphereBleService: NSObject, CBCentralManagerDelegate, CBPeripheralManagerDelegate {
    
    static let meshServiceUUID = CBUUID(string: "A7M0MESH-0001-0000-0000-000000000001")
    static let txCharUUID = CBUUID(string: "A7M0MESH-0001-0001-0000-000000000001")
    static let rxCharUUID = CBUUID(string: "A7M0MESH-0001-0002-0000-000000000001")
    
    private var centralManager: CBCentralManager!
    private var peripheralManager: CBPeripheralManager!
    private var connectedPeers: [UUID: CBPeripheral] = [:]
    private var router = MeshRouter()
    
    override init() {
        super.init()
        centralManager = CBCentralManager(delegate: self, queue: nil)
        peripheralManager = CBPeripheralManager(delegate: self, queue: nil)
    }
    
    // MARK: - Peripheral Manager (Advertising)
    
    func peripheralManagerDidUpdateState(_ peripheral: CBPeripheralManager) {
        guard peripheral.state == .poweredOn else { return }
        startAdvertising()
    }
    
    private func startAdvertising() {
        let service = CBMutableService(type: Self.meshServiceUUID, primary: true)
        
        let txChar = CBMutableCharacteristic(
            type: Self.txCharUUID,
            properties: [.write, .notify],
            value: nil,
            permissions: [.writeable]
        )
        
        let rxChar = CBMutableCharacteristic(
            type: Self.rxCharUUID,
            properties: [.read, .notify],
            value: nil,
            permissions: [.readable]
        )
        
        service.characteristics = [txChar, rxChar]
        peripheralManager.add(service)
        
        peripheralManager.startAdvertising([
            CBAdvertisementDataServiceUUIDsKey: [Self.meshServiceUUID]
        ])
    }
    
    // MARK: - Central Manager (Scanning)
    
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        guard central.state == .poweredOn else { return }
        startScanning()
    }
    
    private func startScanning() {
        centralManager.scanForPeripherals(
            withServices: [Self.meshServiceUUID],
            options: [CBCentralManagerScanOptionAllowDuplicatesKey: false]
        )
    }
    
    func centralManager(_ central: CBCentralManager, 
                        didDiscover peripheral: CBPeripheral,
                        advertisementData: [String: Any],
                        rssi RSSI: NSNumber) {
        guard !connectedPeers.keys.contains(peripheral.identifier) else { return }
        
        connectedPeers[peripheral.identifier] = peripheral
        peripheral.delegate = self
        centralManager.connect(peripheral, options: nil)
    }
    
    // MARK: - Message Handling
    
    func sendMessage(_ data: Data, to destination: String?) {
        let fragments = router.fragment(data)
        
        for fragment in fragments {
            for peer in connectedPeers.values {
                sendToPeer(peer, data: fragment)
            }
        }
    }
    
    private func sendToPeer(_ peer: CBPeripheral, data: Data) {
        guard let txChar = peer.services?
            .first(where: { $0.uuid == Self.meshServiceUUID })?
            .characteristics?
            .first(where: { $0.uuid == Self.txCharUUID }) else { return }
        
        peer.writeValue(data, for: txChar, type: .withResponse)
    }
}
```

---

## Security

### Mesh Network Key

All mesh traffic is encrypted with a shared mesh key derived from the mesh invite token:

```python
def derive_mesh_key(invite_token: str) -> bytes:
    """Derive mesh encryption key from invite token."""
    return hashlib.pbkdf2_hmac(
        'sha256',
        invite_token.encode(),
        b'atmosphere-mesh-key',
        100000,
        dklen=32
    )

def encrypt_message(plaintext: bytes, mesh_key: bytes) -> bytes:
    """Encrypt message with mesh key using AES-GCM."""
    nonce = os.urandom(12)
    cipher = AES.new(mesh_key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    return nonce + tag + ciphertext

def decrypt_message(ciphertext: bytes, mesh_key: bytes) -> bytes:
    """Decrypt message with mesh key."""
    nonce = ciphertext[:12]
    tag = ciphertext[12:28]
    data = ciphertext[28:]
    cipher = AES.new(mesh_key, AES.MODE_GCM, nonce=nonce)
    return cipher.decrypt_and_verify(data, tag)
```

### Replay Protection

- Each message has a sequence number
- Nodes track seen (source, seq) pairs
- Messages older than window are rejected

---

## Performance Expectations

| Metric | Expected Value |
|--------|----------------|
| Discovery time | 1-3 seconds |
| Connection setup | 200-500ms |
| Per-hop latency | 200-400ms |
| Throughput | 50-200 KB/s |
| Max message size | 64 KB (fragmented) |
| Max hops | 5-7 practical |
| Battery impact | Low-Medium |

---

## Testing Strategy

1. **Unit tests:** Message parsing, fragmentation, routing logic
2. **Integration tests:** Two-device communication
3. **Mesh tests:** 3+ devices, verify multi-hop
4. **Stress tests:** Message flooding, connection churn
5. **Cross-platform:** Android ↔ iOS communication

---

## Limitations & Mitigations

| Limitation | Mitigation |
|------------|------------|
| Low bandwidth | Use compact formats (CBOR), compress data |
| High latency | Prefer WiFi Aware when available |
| Limited range | Multi-hop routing, strategic node placement |
| Connection limits | Limit to ~5 simultaneous connections |
| iOS background restrictions | Use background BLE modes, optimize for foreground |

---

## Next Steps

1. Implement basic Android GATT server/client
2. Test two-device communication
3. Add fragmentation layer
4. Implement routing
5. Port to iOS
6. Cross-platform testing
