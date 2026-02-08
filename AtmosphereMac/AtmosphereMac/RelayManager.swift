//
//  RelayManager.swift
//  AtmosphereMac
//
//  Manages connection to Atmosphere cloud relay server.
//

import Foundation
import Combine

// MARK: - Relay Connection State
enum RelayState: String {
    case disconnected = "Disconnected"
    case connecting = "Connecting..."
    case connected = "Connected"
    case error = "Error"
}

// MARK: - Relay Node
struct RelayNode: Identifiable, Codable {
    let id: String
    let name: String
    let platform: String
    let capabilities: [String]
    let connectedAt: Date?
}

// MARK: - Relay Manager
@MainActor
class RelayManager: ObservableObject {
    
    @Published var state: RelayState = .disconnected
    @Published var relayUrl: String = "wss://atmosphere-relay.railway.app"
    @Published var connectedNodes: [RelayNode] = []
    @Published var logs: [String] = []
    @Published var latency: Int? = nil
    
    private var webSocketTask: URLSessionWebSocketTask?
    private var pingTimer: Timer?
    private var reconnectAttempts = 0
    private let maxReconnectAttempts = 5
    
    // Node identity
    var nodeId: String = ""
    var nodeName: String = "Atmosphere-Mac"
    var capabilities: [String] = ["relay", "llm", "embeddings"]
    
    init() {
        log("🌐 Relay Manager initialized")
    }
    
    // MARK: - Public API
    
    func connect() {
        guard state != .connected && state != .connecting else { return }
        
        state = .connecting
        reconnectAttempts = 0
        log("🔗 Connecting to relay: \(relayUrl)")
        
        establishConnection()
    }
    
    func disconnect() {
        log("🔌 Disconnecting from relay")
        webSocketTask?.cancel(with: .goingAway, reason: nil)
        webSocketTask = nil
        pingTimer?.invalidate()
        pingTimer = nil
        state = .disconnected
        connectedNodes = []
    }
    
    func sendMessage(to nodeId: String, payload: Data) {
        let message: [String: Any] = [
            "type": "message",
            "to": nodeId,
            "payload": payload.base64EncodedString()
        ]
        
        sendJSON(message)
    }
    
    func broadcast(payload: Data) {
        let message: [String: Any] = [
            "type": "broadcast",
            "payload": payload.base64EncodedString()
        ]
        
        sendJSON(message)
    }
    
    // MARK: - Private
    
    private func establishConnection() {
        guard let url = URL(string: relayUrl) else {
            log("❌ Invalid relay URL")
            state = .error
            return
        }
        
        let session = URLSession(configuration: .default)
        webSocketTask = session.webSocketTask(with: url)
        webSocketTask?.resume()
        
        // Send join message
        let joinMessage: [String: Any] = [
            "type": "join",
            "nodeId": nodeId,
            "name": nodeName,
            "platform": "macOS",
            "capabilities": capabilities
        ]
        
        sendJSON(joinMessage)
        
        // Start receiving messages
        receiveMessage()
        
        // Start ping timer
        startPingTimer()
        
        state = .connected
        log("✅ Connected to relay")
    }
    
    private func receiveMessage() {
        webSocketTask?.receive { [weak self] result in
            Task { @MainActor in
                switch result {
                case .success(let message):
                    self?.handleMessage(message)
                    self?.receiveMessage()  // Continue receiving
                    
                case .failure(let error):
                    self?.log("❌ WebSocket error: \(error.localizedDescription)")
                    self?.handleDisconnect()
                }
            }
        }
    }
    
    private func handleMessage(_ message: URLSessionWebSocketTask.Message) {
        switch message {
        case .string(let text):
            if let data = text.data(using: .utf8),
               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let type = json["type"] as? String {
                handleJSONMessage(type: type, json: json)
            }
            
        case .data(let data):
            log("📨 Received binary: \(data.count) bytes")
            
        @unknown default:
            break
        }
    }
    
    private func handleJSONMessage(type: String, json: [String: Any]) {
        switch type {
        case "welcome":
            if let nodes = json["nodes"] as? [[String: Any]] {
                updateNodeList(from: nodes)
            }
            log("👋 Welcomed by relay, \(connectedNodes.count) nodes online")
            
        case "node_joined":
            if let nodeData = json["node"] as? [String: Any] {
                addNode(from: nodeData)
            }
            
        case "node_left":
            if let leftId = json["nodeId"] as? String {
                removeNode(id: leftId)
            }
            
        case "message":
            if let from = json["from"] as? String,
               let payloadB64 = json["payload"] as? String,
               let payload = Data(base64Encoded: payloadB64) {
                log("📨 Message from \(from.prefix(8))...: \(payload.count) bytes")
            }
            
        case "pong":
            if let sent = json["timestamp"] as? Double {
                let now = Date().timeIntervalSince1970 * 1000
                latency = Int(now - sent)
            }
            
        default:
            log("⚠️ Unknown message type: \(type)")
        }
    }
    
    private func updateNodeList(from nodes: [[String: Any]]) {
        connectedNodes = nodes.compactMap { dict -> RelayNode? in
            guard let id = dict["nodeId"] as? String ?? dict["id"] as? String,
                  let name = dict["name"] as? String else { return nil }
            
            return RelayNode(
                id: id,
                name: name,
                platform: dict["platform"] as? String ?? "unknown",
                capabilities: dict["capabilities"] as? [String] ?? [],
                connectedAt: nil
            )
        }
    }
    
    private func addNode(from dict: [String: Any]) {
        guard let id = dict["nodeId"] as? String ?? dict["id"] as? String,
              let name = dict["name"] as? String else { return }
        
        let node = RelayNode(
            id: id,
            name: name,
            platform: dict["platform"] as? String ?? "unknown",
            capabilities: dict["capabilities"] as? [String] ?? [],
            connectedAt: Date()
        )
        
        if !connectedNodes.contains(where: { $0.id == id }) {
            connectedNodes.append(node)
            log("🟢 Node joined: \(name)")
        }
    }
    
    private func removeNode(id: String) {
        if let index = connectedNodes.firstIndex(where: { $0.id == id }) {
            let node = connectedNodes.remove(at: index)
            log("🔴 Node left: \(node.name)")
        }
    }
    
    private func handleDisconnect() {
        state = .disconnected
        connectedNodes = []
        pingTimer?.invalidate()
        
        // Attempt reconnect
        if reconnectAttempts < maxReconnectAttempts {
            reconnectAttempts += 1
            log("🔄 Reconnecting (attempt \(reconnectAttempts)/\(maxReconnectAttempts))...")
            
            DispatchQueue.main.asyncAfter(deadline: .now() + Double(reconnectAttempts) * 2) { [weak self] in
                self?.establishConnection()
            }
        } else {
            log("❌ Max reconnect attempts reached")
            state = .error
        }
    }
    
    private func startPingTimer() {
        pingTimer?.invalidate()
        pingTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.sendPing()
            }
        }
    }
    
    private func sendPing() {
        let ping: [String: Any] = [
            "type": "ping",
            "timestamp": Date().timeIntervalSince1970 * 1000
        ]
        sendJSON(ping)
    }
    
    private func sendJSON(_ dict: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: dict),
              let text = String(data: data, encoding: .utf8) else { return }
        
        webSocketTask?.send(.string(text)) { [weak self] error in
            if let error = error {
                Task { @MainActor in
                    self?.log("❌ Send error: \(error.localizedDescription)")
                }
            }
        }
    }
    
    private func log(_ message: String) {
        let timestamp = ISO8601DateFormatter().string(from: Date())
        let entry = "[\(timestamp.suffix(12))] \(message)"
        logs.append(entry)
        
        if logs.count > 500 {
            logs.removeFirst(100)
        }
        
        print("[Relay] \(message)")
    }
}
