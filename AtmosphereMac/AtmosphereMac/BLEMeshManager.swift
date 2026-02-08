//
//  BLEMeshManager.swift
//  AtmosphereMac
//
//  CoreBluetooth-based BLE mesh for discovering and connecting to Atmosphere nodes.
//

import Foundation
import CoreBluetooth
import Combine

// MARK: - UUIDs (Must match Android exactly!)
struct MeshUUIDs {
    static let meshService = CBUUID(string: "A7A05F30-0001-4000-8000-00805F9B34FB")
    static let txChar = CBUUID(string: "A7A05F30-0002-4000-8000-00805F9B34FB")
    static let rxChar = CBUUID(string: "A7A05F30-0003-4000-8000-00805F9B34FB")
    static let infoChar = CBUUID(string: "A7A05F30-0004-4000-8000-00805F9B34FB")
    static let meshIdChar = CBUUID(string: "A7A05F30-0005-4000-8000-00805F9B34FB")
}

// MARK: - Peer Model
struct MeshPeer: Identifiable, Hashable {
    let id: String  // Node ID
    var name: String
    var rssi: Int
    var capabilities: [String]
    var lastSeen: Date
    var peripheral: CBPeripheral?
    var isConnected: Bool = false
    
    func hash(into hasher: inout Hasher) {
        hasher.combine(id)
    }
    
    static func == (lhs: MeshPeer, rhs: MeshPeer) -> Bool {
        lhs.id == rhs.id
    }
}

// MARK: - Message Types
enum MeshMessageType: UInt8 {
    case hello = 0x01
    case helloAck = 0x02
    case goodbye = 0x03
    case routeReq = 0x10
    case routeRep = 0x11
    case data = 0x20
    case dataAck = 0x21
    case meshInfo = 0x30
    case capability = 0x31
}

struct MeshMessage: Identifiable {
    let id = UUID()
    let sourceId: String
    let destId: String
    let type: MeshMessageType
    let payload: Data
    let timestamp: Date
}

// MARK: - BLE Mesh Manager
@MainActor
class BLEMeshManager: NSObject, ObservableObject {
    
    // MARK: Published State
    @Published var isScanning = false
    @Published var isAdvertising = false
    @Published var bluetoothState: CBManagerState = .unknown
    @Published var peers: [MeshPeer] = []
    @Published var messages: [MeshMessage] = []
    @Published var logs: [String] = []
    
    // Node identity
    @Published var nodeName: String = "Atmosphere-Mac"
    @Published var nodeId: String = ""
    @Published var capabilities: [String] = ["relay", "llm", "embeddings"]
    
    // MARK: Private
    private var centralManager: CBCentralManager!
    private var peripheralManager: CBPeripheralManager!
    private var discoveredPeripherals: [UUID: CBPeripheral] = [:]
    private var connectedPeripherals: [UUID: CBPeripheral] = [:]
    private var peerCleanupTimer: Timer?
    
    // GATT Server characteristics
    private var txCharacteristic: CBMutableCharacteristic?
    private var rxCharacteristic: CBMutableCharacteristic?
    private var infoCharacteristic: CBMutableCharacteristic?
    private var meshIdCharacteristic: CBMutableCharacteristic?
    
    // MARK: Init
    override init() {
        super.init()
        
        // Generate stable node ID from hardware
        nodeId = generateNodeId()
        
        log("🔵 Atmosphere BLE Mesh starting...")
        log("   Node: \(nodeName) (\(nodeId.prefix(8))...)")
        log("   Service UUID: \(MeshUUIDs.meshService.uuidString)")
        
        // Initialize Bluetooth managers
        centralManager = CBCentralManager(delegate: self, queue: .main)
        peripheralManager = CBPeripheralManager(delegate: self, queue: .main)
        
        // Start peer cleanup timer
        startPeerCleanup()
    }
    
    // MARK: - Public API
    
    func startScanning() {
        guard centralManager.state == .poweredOn else {
            log("⚠️ Bluetooth not ready for scanning")
            return
        }
        
        log("🔍 Starting BLE scan...")
        isScanning = true
        
        centralManager.scanForPeripherals(
            withServices: [MeshUUIDs.meshService],
            options: [
                CBCentralManagerScanOptionAllowDuplicatesKey: true
            ]
        )
    }
    
    func stopScanning() {
        log("⏹ Stopping BLE scan")
        centralManager.stopScan()
        isScanning = false
    }
    
    func startAdvertising() {
        guard peripheralManager.state == .poweredOn else {
            log("⚠️ Bluetooth not ready for advertising")
            return
        }
        
        log("📡 Starting BLE advertising...")
        
        // Build advertisement data
        let advertisementData: [String: Any] = [
            CBAdvertisementDataServiceUUIDsKey: [MeshUUIDs.meshService],
            CBAdvertisementDataLocalNameKey: nodeName
        ]
        
        peripheralManager.startAdvertising(advertisementData)
        isAdvertising = true
    }
    
    func stopAdvertising() {
        log("⏹ Stopping BLE advertising")
        peripheralManager.stopAdvertising()
        isAdvertising = false
    }
    
    func connectToPeer(_ peer: MeshPeer) {
        guard let peripheral = peer.peripheral else {
            log("❌ No peripheral for peer \(peer.name)")
            return
        }
        
        log("🔗 Connecting to \(peer.name)...")
        centralManager.connect(peripheral, options: nil)
    }
    
    func disconnectFromPeer(_ peer: MeshPeer) {
        guard let peripheral = peer.peripheral else { return }
        log("🔌 Disconnecting from \(peer.name)")
        centralManager.cancelPeripheralConnection(peripheral)
    }
    
    func sendMessage(to peerId: String, payload: Data) {
        // Find connected peer
        guard let peer = peers.first(where: { $0.id == peerId && $0.isConnected }),
              let peripheral = peer.peripheral else {
            log("❌ Peer not connected: \(peerId.prefix(8))...")
            return
        }
        
        // Build message with header
        var messageData = Data()
        messageData.append(1) // version
        messageData.append(MeshMessageType.data.rawValue)
        // Add source/dest IDs, payload...
        messageData.append(payload)
        
        // Find TX characteristic and write
        if let service = peripheral.services?.first(where: { $0.uuid == MeshUUIDs.meshService }),
           let txChar = service.characteristics?.first(where: { $0.uuid == MeshUUIDs.txChar }) {
            peripheral.writeValue(messageData, for: txChar, type: .withResponse)
            log("📤 Sent \(payload.count) bytes to \(peer.name)")
        }
    }
    
    func broadcastMessage(payload: Data) {
        for peer in peers where peer.isConnected {
            sendMessage(to: peer.id, payload: payload)
        }
    }
    
    // MARK: - Private Helpers
    
    private func generateNodeId() -> String {
        // Use hardware UUID or generate a stable one
        if let uuid = getHardwareUUID() {
            return uuid
        }
        
        // Fall back to stored or new UUID
        let key = "atmosphere.nodeId"
        if let stored = UserDefaults.standard.string(forKey: key) {
            return stored
        }
        
        let newId = UUID().uuidString.lowercased().replacingOccurrences(of: "-", with: "")
        UserDefaults.standard.set(newId, forKey: key)
        return newId
    }
    
    private func getHardwareUUID() -> String? {
        let platformExpert = IOServiceGetMatchingService(
            kIOMainPortDefault,
            IOServiceMatching("IOPlatformExpertDevice")
        )
        
        defer { IOObjectRelease(platformExpert) }
        
        if let uuid = IORegistryEntryCreateCFProperty(
            platformExpert,
            kIOPlatformUUIDKey as CFString,
            kCFAllocatorDefault,
            0
        )?.takeUnretainedValue() as? String {
            return uuid.lowercased().replacingOccurrences(of: "-", with: "")
        }
        
        return nil
    }
    
    private func setupGATTServer() {
        // Create characteristics
        txCharacteristic = CBMutableCharacteristic(
            type: MeshUUIDs.txChar,
            properties: [.write, .writeWithoutResponse],
            value: nil,
            permissions: [.writeable]
        )
        
        rxCharacteristic = CBMutableCharacteristic(
            type: MeshUUIDs.rxChar,
            properties: [.read, .notify],
            value: nil,
            permissions: [.readable]
        )
        
        infoCharacteristic = CBMutableCharacteristic(
            type: MeshUUIDs.infoChar,
            properties: [.read],
            value: buildNodeInfo(),
            permissions: [.readable]
        )
        
        meshIdCharacteristic = CBMutableCharacteristic(
            type: MeshUUIDs.meshIdChar,
            properties: [.read],
            value: nodeId.data(using: .utf8),
            permissions: [.readable]
        )
        
        // Create service
        let service = CBMutableService(type: MeshUUIDs.meshService, primary: true)
        service.characteristics = [
            txCharacteristic!,
            rxCharacteristic!,
            infoCharacteristic!,
            meshIdCharacteristic!
        ]
        
        peripheralManager.add(service)
        log("✅ GATT server configured")
    }
    
    private func buildNodeInfo() -> Data {
        let info: [String: Any] = [
            "name": nodeName,
            "nodeId": nodeId,
            "capabilities": capabilities,
            "platform": "macOS",
            "version": "1.0.0"
        ]
        
        return (try? JSONSerialization.data(withJSONObject: info)) ?? Data()
    }
    
    private func startPeerCleanup() {
        peerCleanupTimer = Timer.scheduledTimer(withTimeInterval: 10.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.cleanupStalePeers()
            }
        }
    }
    
    private func cleanupStalePeers() {
        let staleThreshold = Date().addingTimeInterval(-30)
        let stalePeers = peers.filter { $0.lastSeen < staleThreshold && !$0.isConnected }
        
        for peer in stalePeers {
            log("🔴 Peer lost: \(peer.name)")
            peers.removeAll { $0.id == peer.id }
        }
    }
    
    private func log(_ message: String) {
        let timestamp = ISO8601DateFormatter().string(from: Date())
        let entry = "[\(timestamp.suffix(12))] \(message)"
        logs.append(entry)
        
        // Keep log size manageable
        if logs.count > 500 {
            logs.removeFirst(100)
        }
        
        print(entry)
    }
}

// MARK: - CBCentralManagerDelegate
extension BLEMeshManager: CBCentralManagerDelegate {
    
    nonisolated func centralManagerDidUpdateState(_ central: CBCentralManager) {
        Task { @MainActor in
            bluetoothState = central.state
            
            switch central.state {
            case .poweredOn:
                log("✅ Bluetooth Central ready")
            case .poweredOff:
                log("⚠️ Bluetooth is OFF")
            case .unauthorized:
                log("❌ Bluetooth not authorized")
            case .unsupported:
                log("❌ Bluetooth not supported")
            default:
                log("⚠️ Bluetooth state: \(central.state.rawValue)")
            }
        }
    }
    
    nonisolated func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral, advertisementData: [String: Any], rssi RSSI: NSNumber) {
        Task { @MainActor in
            let name = peripheral.name ?? advertisementData[CBAdvertisementDataLocalNameKey] as? String ?? "Unknown"
            let nodeId = peripheral.identifier.uuidString.lowercased()
            
            // Update or add peer
            if let index = peers.firstIndex(where: { $0.id == nodeId }) {
                peers[index].rssi = RSSI.intValue
                peers[index].lastSeen = Date()
            } else {
                let peer = MeshPeer(
                    id: nodeId,
                    name: name,
                    rssi: RSSI.intValue,
                    capabilities: [],
                    lastSeen: Date(),
                    peripheral: peripheral
                )
                peers.append(peer)
                log("🎉 Discovered: \(name) (RSSI: \(RSSI))")
            }
            
            discoveredPeripherals[peripheral.identifier] = peripheral
        }
    }
    
    nonisolated func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        Task { @MainActor in
            log("✅ Connected to \(peripheral.name ?? "Unknown")")
            
            if let index = peers.firstIndex(where: { $0.peripheral?.identifier == peripheral.identifier }) {
                peers[index].isConnected = true
            }
            
            connectedPeripherals[peripheral.identifier] = peripheral
            peripheral.delegate = self
            peripheral.discoverServices([MeshUUIDs.meshService])
        }
    }
    
    nonisolated func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        Task { @MainActor in
            log("🔌 Disconnected from \(peripheral.name ?? "Unknown")")
            
            if let index = peers.firstIndex(where: { $0.peripheral?.identifier == peripheral.identifier }) {
                peers[index].isConnected = false
            }
            
            connectedPeripherals.removeValue(forKey: peripheral.identifier)
        }
    }
    
    nonisolated func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        Task { @MainActor in
            log("❌ Failed to connect: \(error?.localizedDescription ?? "Unknown")")
        }
    }
}

// MARK: - CBPeripheralDelegate
extension BLEMeshManager: CBPeripheralDelegate {
    
    nonisolated func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        guard error == nil else {
            Task { @MainActor in
                log("❌ Service discovery error: \(error!.localizedDescription)")
            }
            return
        }
        
        for service in peripheral.services ?? [] {
            peripheral.discoverCharacteristics(nil, for: service)
        }
    }
    
    nonisolated func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        guard error == nil else { return }
        
        for characteristic in service.characteristics ?? [] {
            // Subscribe to notifications on RX characteristic
            if characteristic.uuid == MeshUUIDs.rxChar {
                peripheral.setNotifyValue(true, for: characteristic)
            }
            
            // Read node info
            if characteristic.uuid == MeshUUIDs.infoChar {
                peripheral.readValue(for: characteristic)
            }
            
            // Read mesh ID
            if characteristic.uuid == MeshUUIDs.meshIdChar {
                peripheral.readValue(for: characteristic)
            }
        }
    }
    
    nonisolated func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        guard let data = characteristic.value, error == nil else { return }
        
        Task { @MainActor in
            if characteristic.uuid == MeshUUIDs.rxChar {
                // Handle incoming message
                handleIncomingMessage(data, from: peripheral)
            } else if characteristic.uuid == MeshUUIDs.infoChar {
                // Parse node info
                if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let name = json["name"] as? String,
                   let caps = json["capabilities"] as? [String] {
                    if let index = peers.firstIndex(where: { $0.peripheral?.identifier == peripheral.identifier }) {
                        peers[index].name = name
                        peers[index].capabilities = caps
                        log("📋 Got info for \(name): \(caps.joined(separator: ", "))")
                    }
                }
            }
        }
    }
    
    private func handleIncomingMessage(_ data: Data, from peripheral: CBPeripheral) {
        guard data.count >= 2 else { return }
        
        let version = data[0]
        let typeRaw = data[1]
        let payload = data.count > 2 ? data.subdata(in: 2..<data.count) : Data()
        
        guard let type = MeshMessageType(rawValue: typeRaw) else {
            log("⚠️ Unknown message type: \(typeRaw)")
            return
        }
        
        let peerId = peripheral.identifier.uuidString.lowercased()
        let message = MeshMessage(
            sourceId: peerId,
            destId: nodeId,
            type: type,
            payload: payload,
            timestamp: Date()
        )
        
        messages.append(message)
        log("📨 Received \(type) from \(peripheral.name ?? "Unknown"): \(payload.count) bytes")
        
        // Keep message history manageable
        if messages.count > 100 {
            messages.removeFirst(20)
        }
    }
}

// MARK: - CBPeripheralManagerDelegate
extension BLEMeshManager: CBPeripheralManagerDelegate {
    
    nonisolated func peripheralManagerDidUpdateState(_ peripheral: CBPeripheralManager) {
        Task { @MainActor in
            switch peripheral.state {
            case .poweredOn:
                log("✅ Bluetooth Peripheral ready")
                setupGATTServer()
            case .poweredOff:
                log("⚠️ Peripheral Bluetooth is OFF")
            default:
                log("⚠️ Peripheral state: \(peripheral.state.rawValue)")
            }
        }
    }
    
    nonisolated func peripheralManagerDidStartAdvertising(_ peripheral: CBPeripheralManager, error: Error?) {
        Task { @MainActor in
            if let error = error {
                log("❌ Advertising error: \(error.localizedDescription)")
                isAdvertising = false
            } else {
                log("📡 Now advertising as '\(nodeName)'")
            }
        }
    }
    
    nonisolated func peripheralManager(_ peripheral: CBPeripheralManager, didReceiveWrite requests: [CBATTRequest]) {
        for request in requests {
            if request.characteristic.uuid == MeshUUIDs.txChar,
               let data = request.value {
                Task { @MainActor in
                    handleIncomingServerMessage(data)
                }
            }
            peripheral.respond(to: request, withResult: .success)
        }
    }
    
    nonisolated func peripheralManager(_ peripheral: CBPeripheralManager, didReceiveRead request: CBATTRequest) {
        if request.characteristic.uuid == MeshUUIDs.infoChar {
            request.value = buildNodeInfo()
        } else if request.characteristic.uuid == MeshUUIDs.meshIdChar {
            request.value = nodeId.data(using: .utf8)
        }
        peripheral.respond(to: request, withResult: .success)
    }
    
    private func handleIncomingServerMessage(_ data: Data) {
        log("📨 GATT server received \(data.count) bytes")
        // Process message similar to client side
    }
}
