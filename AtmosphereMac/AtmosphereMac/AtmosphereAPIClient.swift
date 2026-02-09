//
//  AtmosphereAPIClient.swift
//  AtmosphereMac
//
//  API client for the Atmosphere Python server (http://localhost:11451)
//

import Foundation
import Combine

// MARK: - Response Models

struct AtmosphereMeshStatus: Codable {
    let nodeId: String
    let nodeName: String
    let peerCount: Int
    let capabilities: [String]
    let uptime: Double?
    
    enum CodingKeys: String, CodingKey {
        case nodeId = "node_id"
        case nodeName = "node_name"
        case peerCount = "peer_count"
        case capabilities
        case uptime
    }
}

struct AtmospherePeer: Codable, Identifiable {
    let id: String
    let name: String
    let source: String  // "mdns", "relay", "ble"
    let capabilities: [String]
    let lastSeen: String?
    let latencyMs: Int?
    
    enum CodingKeys: String, CodingKey {
        case id
        case name
        case source
        case capabilities
        case lastSeen = "last_seen"
        case latencyMs = "latency_ms"
    }
}

struct AtmospherePeersResponse: Codable {
    let peers: [AtmospherePeer]
}

struct AtmosphereCapability: Codable, Identifiable {
    let id: String
    let name: String
    let version: String?
    let nodeId: String
    let nodeName: String
    
    enum CodingKeys: String, CodingKey {
        case id
        case name
        case version
        case nodeId = "node_id"
        case nodeName = "node_name"
    }
}

struct AtmosphereCapabilitiesResponse: Codable {
    let capabilities: [AtmosphereCapability]
}

struct AtmosphereGossipStatus: Codable {
    let protocolState: String
    let peerCount: Int
    let messagesSent: Int
    let messagesReceived: Int
    let bytesTransferred: Int
    
    enum CodingKeys: String, CodingKey {
        case protocolState = "protocol_state"
        case peerCount = "peer_count"
        case messagesSent = "messages_sent"
        case messagesReceived = "messages_received"
        case bytesTransferred = "bytes_transferred"
    }
}

struct AtmosphereGossipStats: Codable {
    let avgLatencyMs: Double
    let successRate: Double
    let activeTopics: [String]
    let messageQueue: Int
    
    enum CodingKeys: String, CodingKey {
        case avgLatencyMs = "avg_latency_ms"
        case successRate = "success_rate"
        case activeTopics = "active_topics"
        case messageQueue = "message_queue"
    }
}

struct AtmosphereBackend: Codable, Identifiable {
    let id: String
    let name: String
    let type: String
    let status: String
    let modelName: String?
    
    enum CodingKeys: String, CodingKey {
        case id
        case name
        case type
        case status
        case modelName = "model_name"
    }
}

struct AtmosphereBackendsResponse: Codable {
    let backends: [AtmosphereBackend]
}

struct AtmosphereHealthResponse: Codable {
    let status: String
    let version: String?
    let uptime: Double?
}

struct AtmosphereDevice: Codable, Identifiable {
    let id: String
    let name: String
    let type: String
    let connected: Bool
    let lastSeen: String?
    
    enum CodingKeys: String, CodingKey {
        case id
        case name
        case type
        case connected
        case lastSeen = "last_seen"
    }
}

struct AtmosphereDevicesResponse: Codable {
    let devices: [AtmosphereDevice]
}

struct AtmosphereTokenRequest: Codable {
    let ttlSeconds: Int?
    
    enum CodingKeys: String, CodingKey {
        case ttlSeconds = "ttl_seconds"
    }
}

struct AtmosphereTokenResponse: Codable {
    let token: String
    let expiresAt: String?
    let inviteUrl: String?
    
    enum CodingKeys: String, CodingKey {
        case token
        case expiresAt = "expires_at"
        case inviteUrl = "invite_url"
    }
}

struct AtmosphereChatRequest: Codable {
    let messages: [ChatMessage]
    let model: String?
    let temperature: Double?
    let maxTokens: Int?
    
    enum CodingKeys: String, CodingKey {
        case messages
        case model
        case temperature
        case maxTokens = "max_tokens"
    }
}

struct ChatMessage: Codable {
    let role: String
    let content: String
}

struct AtmosphereChatResponse: Codable {
    let id: String
    let choices: [ChatChoice]
    let model: String?
    let usage: TokenUsage?
}

struct ChatChoice: Codable {
    let index: Int
    let message: ChatMessage
    let finishReason: String?
    
    enum CodingKeys: String, CodingKey {
        case index
        case message
        case finishReason = "finish_reason"
    }
}

struct TokenUsage: Codable {
    let promptTokens: Int
    let completionTokens: Int
    let totalTokens: Int
    
    enum CodingKeys: String, CodingKey {
        case promptTokens = "prompt_tokens"
        case completionTokens = "completion_tokens"
        case totalTokens = "total_tokens"
    }
}

// MARK: - Atmosphere API Client

@MainActor
class AtmosphereAPIClient: ObservableObject {
    
    // MARK: Published State
    @Published var isConnected: Bool = false
    @Published var meshStatus: AtmosphereMeshStatus?
    @Published var peers: [AtmospherePeer] = []
    @Published var capabilities: [AtmosphereCapability] = []
    @Published var gossipStatus: AtmosphereGossipStatus?
    @Published var gossipStats: AtmosphereGossipStats?
    @Published var backends: [AtmosphereBackend] = []
    @Published var devices: [AtmosphereDevice] = []
    @Published var lastError: String?
    
    // Configuration
    @Published var baseUrl: String = "http://localhost:11451"
    
    private var refreshTask: Task<Void, Never>?
    private let refreshInterval: TimeInterval = 5.0
    
    // MARK: Init
    
    init() {
        print("🌐 Atmosphere API Client initialized")
        startAutoRefresh()
    }
    
    deinit {
        refreshTask?.cancel()
    }
    
    // MARK: - Public API
    
    func connect() async {
        await refreshAll()
    }
    
    func disconnect() {
        refreshTask?.cancel()
        isConnected = false
    }
    
    // Mesh endpoints
    
    func fetchMeshStatus() async throws -> AtmosphereMeshStatus {
        return try await get("/api/mesh/status")
    }
    
    func fetchPeers() async throws -> [AtmospherePeer] {
        let response: AtmospherePeersResponse = try await get("/api/mesh/peers")
        return response.peers
    }
    
    func fetchCapabilities() async throws -> [AtmosphereCapability] {
        let response: AtmosphereCapabilitiesResponse = try await get("/api/mesh/capabilities")
        return response.capabilities
    }
    
    func fetchLocalCapabilities() async throws -> [AtmosphereCapability] {
        let response: AtmosphereCapabilitiesResponse = try await get("/api/capabilities")
        return response.capabilities
    }
    
    // Gossip endpoints
    
    func fetchGossipStatus() async throws -> AtmosphereGossipStatus {
        return try await get("/api/gossip/status")
    }
    
    func fetchGossipStats() async throws -> AtmosphereGossipStats {
        return try await get("/api/gossip/stats")
    }
    
    // Backend endpoints
    
    func fetchBackends() async throws -> [AtmosphereBackend] {
        let response: AtmosphereBackendsResponse = try await get("/api/backends")
        return response.backends
    }
    
    // Health endpoint
    
    func fetchHealth() async throws -> AtmosphereHealthResponse {
        return try await get("/api/health")
    }
    
    // Devices endpoint
    
    func fetchDevices() async throws -> [AtmosphereDevice] {
        let response: AtmosphereDevicesResponse = try await get("/api/devices")
        return response.devices
    }
    
    // Token/Invite endpoint
    
    func createInviteToken(ttlSeconds: Int? = nil) async throws -> AtmosphereTokenResponse {
        let request = AtmosphereTokenRequest(ttlSeconds: ttlSeconds)
        return try await post("/api/mesh/token", body: request)
    }
    
    // Chat endpoint
    
    func sendChatCompletion(messages: [ChatMessage], model: String? = nil, temperature: Double? = nil, maxTokens: Int? = nil) async throws -> AtmosphereChatResponse {
        let request = AtmosphereChatRequest(
            messages: messages,
            model: model,
            temperature: temperature,
            maxTokens: maxTokens
        )
        return try await post("/api/chat/completions", body: request)
    }
    
    // MARK: - Auto Refresh
    
    private func startAutoRefresh() {
        refreshTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refreshAll()
                try? await Task.sleep(for: .seconds(self?.refreshInterval ?? 5.0))
            }
        }
    }
    
    private func refreshAll() async {
        do {
            // Fetch all data in parallel
            async let statusTask = fetchMeshStatus()
            async let peersTask = fetchPeers()
            async let capsTask = fetchCapabilities()
            async let gossipStatusTask = fetchGossipStatus()
            async let gossipStatsTask = fetchGossipStats()
            async let backendsTask = fetchBackends()
            async let devicesTask = fetchDevices()
            
            let (status, peers, caps, gossipStatus, gossipStats, backends, devices) = try await (
                statusTask,
                peersTask,
                capsTask,
                gossipStatusTask,
                gossipStatsTask,
                backendsTask,
                devicesTask
            )
            
            self.meshStatus = status
            self.peers = peers
            self.capabilities = caps
            self.gossipStatus = gossipStatus
            self.gossipStats = gossipStats
            self.backends = backends
            self.devices = devices
            self.isConnected = true
            self.lastError = nil
            
        } catch {
            self.isConnected = false
            self.lastError = error.localizedDescription
            print("❌ Atmosphere refresh error: \(error)")
        }
    }
    
    // MARK: - HTTP Client
    
    private func get<T: Decodable>(_ path: String) async throws -> T {
        guard let url = URL(string: baseUrl + path) else {
            throw URLError(.badURL)
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 10.0
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        
        guard httpResponse.statusCode == 200 else {
            throw URLError(.init(rawValue: httpResponse.statusCode))
        }
        
        let decoder = JSONDecoder()
        return try decoder.decode(T.self, from: data)
    }
    
    private func post<T: Encodable, R: Decodable>(_ path: String, body: T) async throws -> R {
        guard let url = URL(string: baseUrl + path) else {
            throw URLError(.badURL)
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 30.0
        
        let encoder = JSONEncoder()
        request.httpBody = try encoder.encode(body)
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        
        guard httpResponse.statusCode == 200 else {
            throw URLError(.init(rawValue: httpResponse.statusCode))
        }
        
        let decoder = JSONDecoder()
        return try decoder.decode(R.self, from: data)
    }
}
