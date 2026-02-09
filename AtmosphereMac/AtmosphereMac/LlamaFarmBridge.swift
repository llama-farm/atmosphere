//
//  LlamaFarmBridge.swift
//  AtmosphereMac
//
//  Bridge to LlamaFarm vision API for escalation handling.
//

import Foundation
import Combine

// MARK: - LlamaFarm Types

struct LFModelInfo: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let task: String  // "detection", "classification", "llm"
    let loaded: Bool
    let device: String?
    
    enum CodingKeys: String, CodingKey {
        case id = "model_id"
        case name, task, loaded, device
    }
}

struct LFHealthResponse: Codable {
    let status: String
    let version: String?
    let models: [LFModelInfo]?
    let seeds: [LFSeed]?
}

struct LFSeed: Codable, Identifiable {
    var id: String { nodeId }
    let nodeId: String
    let runtime: LFRuntimeInfo?
    
    enum CodingKeys: String, CodingKey {
        case nodeId = "node_id"
        case runtime
    }
}

struct LFRuntimeInfo: Codable {
    let model: String?
    let provider: String?
    let status: String?
}

struct LFDetectRequest: Codable {
    let images: [String]  // base64 array
    let model: String
    let confidenceThreshold: Float
    let classes: [String]?
    
    enum CodingKeys: String, CodingKey {
        case images, model
        case confidenceThreshold = "confidence_threshold"
        case classes
    }
}

struct LFBoundingBox: Codable {
    let x1: Float
    let y1: Float
    let x2: Float
    let y2: Float
}

struct LFDetection: Codable {
    let box: LFBoundingBox
    let className: String
    let classId: Int
    let confidence: Float
    
    enum CodingKeys: String, CodingKey {
        case box
        case className = "class_name"
        case classId = "class_id"
        case confidence
    }
}

struct LFDetectResponse: Codable {
    let detections: [LFDetection]
    let model: String
    let inferenceTimeMs: Float
    
    enum CodingKeys: String, CodingKey {
        case detections, model
        case inferenceTimeMs = "inference_time_ms"
    }
}

struct LFClassifyRequest: Codable {
    let images: [String]
    let model: String
    let labels: [String]
    
    enum CodingKeys: String, CodingKey {
        case images, model, labels
    }
}

struct LFClassifyResponse: Codable {
    let className: String
    let classId: Int
    let confidence: Float
    let allScores: [String: Float]
    let model: String
    
    enum CodingKeys: String, CodingKey {
        case className = "class_name"
        case classId = "class_id"
        case confidence
        case allScores = "all_scores"
        case model
    }
}

struct LFOpinion: Codable {
    let modelId: String
    let nodeId: String
    let className: String
    let confidence: Float
    let bbox: [Float]?
    let maskPolygon: [[Float]]?
    let inferenceTimeMs: Float
    
    enum CodingKeys: String, CodingKey {
        case modelId = "model_id"
        case nodeId = "node_id"
        case className = "class_name"
        case confidence, bbox
        case maskPolygon = "mask_polygon"
        case inferenceTimeMs = "inference_time_ms"
    }
}

struct LFEscalateRequest: Codable {
    let image: String
    let model: String
    let confidenceThreshold: Float
    let opinions: [LFOpinion]
    
    enum CodingKeys: String, CodingKey {
        case image, model, opinions
        case confidenceThreshold = "confidence_threshold"
    }
}

struct LFEscalateResponse: Codable {
    let resolved: Bool
    let detection: LFDetection?
    let opinion: LFOpinion?
    let addedToReplay: Bool
    
    enum CodingKeys: String, CodingKey {
        case resolved, detection, opinion
        case addedToReplay = "added_to_replay"
    }
}

struct LFModelsListResponse: Codable {
    let models: [LFModelInfo]
}

struct LFPeerRegistration: Codable {
    let nodeId: String
    let name: String
    let url: String
    let models: [String]
    let priority: Int
    
    enum CodingKeys: String, CodingKey {
        case nodeId = "node_id"
        case name, url, models, priority
    }
}

struct LFPeerInfo: Codable {
    let nodeId: String
    let name: String
    let url: String
    let models: [String]
    let lastSeen: String?
    
    enum CodingKeys: String, CodingKey {
        case nodeId = "node_id"
        case name, url, models
        case lastSeen = "last_seen"
    }
}

struct LFPeersListResponse: Codable {
    let peers: [LFPeerInfo]
}

struct LFModelPackage: Codable {
    let modelId: String
    let name: String
    let path: String
    let sizeMb: Float
    let checksum: String
    
    enum CodingKeys: String, CodingKey {
        case modelId = "model_id"
        case name, path
        case sizeMb = "size_mb"
        case checksum
    }
}

struct LFPackagesListResponse: Codable {
    let packages: [LFModelPackage]
}

struct LFCreatePackageRequest: Codable {
    let modelId: String
    
    enum CodingKeys: String, CodingKey {
        case modelId = "model_id"
    }
}

struct EmptyResponse: Codable {}

// Import EscalationEnvelope from VisionEscalationHandler
// (Forward declaration - actual type defined in VisionEscalationHandler.swift)

// MARK: - Bridge State

enum BridgeState {
    case disconnected
    case connecting
    case connected
    case error(String)
}

// MARK: - LlamaFarm Bridge

@MainActor
class LlamaFarmBridge: ObservableObject {
    
    // MARK: Published State
    @Published var state: BridgeState = .disconnected
    @Published var availableModels: [LFModelInfo] = []
    @Published var lastHealthCheck: Date?
    @Published var activityLog: [String] = []
    
    // Configuration
    @Published var baseUrl: String = "http://localhost:11540" {
        didSet {
            if oldValue != baseUrl {
                healthCheckTask?.cancel()
                startHealthChecks()
            }
        }
    }
    
    private var healthCheckTask: Task<Void, Never>?
    private let healthCheckInterval: TimeInterval = 30.0
    
    // MARK: Init
    
    init() {
        log("🦙 LlamaFarm Bridge initialized (Universal Runtime @ :11540)")
        startHealthChecks()
    }
    
    deinit {
        healthCheckTask?.cancel()
    }
    
    // MARK: - Public API
    
    /// Perform initial connection and health check
    func connect() async {
        state = .connecting
        log("🔗 Connecting to LlamaFarm at \(baseUrl)")
        
        await performHealthCheck()
    }
    
    /// Disconnect and stop health checks
    func disconnect() {
        healthCheckTask?.cancel()
        state = .disconnected
        log("🔌 Disconnected from LlamaFarm")
    }
    
    /// Forward an escalation envelope to LlamaFarm vision/detect
    func detectObjects(imageBase64: String, model: String = "yolov8n", confidenceThreshold: Float = 0.5, classes: [String]? = nil) async throws -> LFDetectResponse {
        let endpoint = "/v1/vision/detect"
        let request = LFDetectRequest(
            images: [imageBase64],  // Wrap in array
            model: model,
            confidenceThreshold: confidenceThreshold,
            classes: classes
        )
        
        log("📤 Forwarding detection to \(model)...")
        
        let response: LFDetectResponse = try await post(endpoint, body: request)
        
        log("✅ Detection complete: \(response.detections.count) objects (\(Int(response.inferenceTimeMs))ms)")
        
        return response
    }
    
    /// Classify an image using CLIP
    func classifyImage(imageBase64: String, labels: [String], model: String = "openai/clip-vit-base-patch32") async throws -> LFClassifyResponse {
        let endpoint = "/v1/vision/classify"
        let request = LFClassifyRequest(
            images: [imageBase64],  // Wrap in array
            model: model,
            labels: labels
        )
        
        log("📤 Classifying with \(model)...")
        
        let response: LFClassifyResponse = try await post(endpoint, body: request)
        
        log("✅ Classification: \(response.className) (\(Int(response.confidence * 100))%)")
        
        return response
    }
    
    /// Forward escalation to LlamaFarm federation endpoint
    func escalate(envelope: EscalationEnvelope, model: String = "yolov8x", confidenceThreshold: Float = 0.5) async throws -> LFEscalateResponse {
        let endpoint = "/v1/vision/federation/escalate"
        let request = LFEscalateRequest(
            image: envelope.imageBase64,
            model: model,
            confidenceThreshold: confidenceThreshold,
            opinions: envelope.opinions.map { opinion in
                LFOpinion(
                    modelId: opinion.modelId,
                    nodeId: opinion.nodeId,
                    className: opinion.className,
                    confidence: opinion.confidence,
                    bbox: opinion.bbox,
                    maskPolygon: opinion.maskPolygon,
                    inferenceTimeMs: opinion.inferenceTimeMs
                )
            }
        )
        
        log("📤 Escalating to \(model) via federation endpoint...")
        
        let response: LFEscalateResponse = try await post(endpoint, body: request)
        
        log("✅ Escalation response: \(response.resolved ? "resolved" : "unresolved")")
        
        return response
    }
    
    /// Add result to LlamaFarm replay buffer for training
    func addToReplayBuffer(imageBase64: String, label: String, confidence: Float, source: String = "escalation_resolved") async throws {
        // LlamaFarm's streaming API handles replay buffer automatically
        // But we can also explicitly POST to training endpoints if needed
        log("📝 Added to replay buffer: \(label) (\(source))")
    }
    
    /// List available vision models from LlamaFarm
    func listModels() async throws -> [LFModelInfo] {
        let response: LFModelsListResponse = try await get("/v1/vision/models")
        return response.models
    }
    
    /// Register this node as a federation peer
    func registerAsPeer(nodeId: String, nodeName: String, capabilities: [String]) async throws {
        let endpoint = "/v1/vision/federation/peers"
        let request = LFPeerRegistration(
            nodeId: nodeId,
            name: nodeName,
            url: "atmosphere://\(nodeId)",  // Atmosphere mesh URL
            models: capabilities,
            priority: 0
        )
        
        log("📝 Registering as federation peer: \(nodeName)")
        
        let _: EmptyResponse = try await post(endpoint, body: request)
    }
    
    /// List federation peers
    func listPeers() async throws -> [LFPeerInfo] {
        let response: LFPeersListResponse = try await get("/v1/vision/federation/peers")
        return response.peers
    }
    
    /// List available model packages
    func listPackages() async throws -> [LFModelPackage] {
        let response: LFPackagesListResponse = try await get("/v1/vision/federation/packages")
        return response.packages
    }
    
    /// Create a model package for distribution
    func createPackage(modelId: String) async throws -> LFModelPackage {
        let endpoint = "/v1/vision/federation/packages"
        let request = LFCreatePackageRequest(modelId: modelId)
        
        log("📦 Creating package for \(modelId)...")
        
        let response: LFModelPackage = try await post(endpoint, body: request)
        
        log("✅ Package created: \(response.path)")
        
        return response
    }
    
    // MARK: - Private Helpers
    
    private func startHealthChecks() {
        healthCheckTask = Task { [weak self] in
            // Initial check immediately
            await self?.performHealthCheck()
            
            // Then periodic checks
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(healthCheckInterval))
                await self?.performHealthCheck()
            }
        }
    }
    
    private func performHealthCheck() async {
        do {
            let health: LFHealthResponse = try await get("/health")
            
            state = .connected
            lastHealthCheck = Date()
            
            if let models = health.models {
                availableModels = models
                log("💚 Health OK: \(models.count) models available")
            }
            
        } catch {
            let errorMsg = error.localizedDescription
            state = .error(errorMsg)
            log("❌ Health check failed: \(errorMsg)")
        }
    }
    
    // MARK: - HTTP Client
    
    private func get<T: Decodable>(_ path: String) async throws -> T {
        guard let url = URL(string: baseUrl + path) else {
            throw BridgeError.invalidUrl
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 30.0
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw BridgeError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            throw BridgeError.httpError(httpResponse.statusCode)
        }
        
        let decoder = JSONDecoder()
        return try decoder.decode(T.self, from: data)
    }
    
    private func post<T: Encodable, R: Decodable>(_ path: String, body: T) async throws -> R {
        guard let url = URL(string: baseUrl + path) else {
            throw BridgeError.invalidUrl
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 60.0  // Longer for inference
        
        let encoder = JSONEncoder()
        request.httpBody = try encoder.encode(body)
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw BridgeError.invalidResponse
        }
        
        guard httpResponse.statusCode == 200 else {
            throw BridgeError.httpError(httpResponse.statusCode)
        }
        
        let decoder = JSONDecoder()
        return try decoder.decode(R.self, from: data)
    }
    
    private func log(_ message: String) {
        let timestamp = ISO8601DateFormatter().string(from: Date())
        let entry = "[\(timestamp.suffix(12))] \(message)"
        activityLog.append(entry)
        
        // Keep log manageable
        if activityLog.count > 200 {
            activityLog.removeFirst(50)
        }
        
        print("[LlamaFarm] \(message)")
    }
}

// MARK: - Errors

enum BridgeError: LocalizedError {
    case invalidUrl
    case invalidResponse
    case httpError(Int)
    case timeout
    
    var errorDescription: String? {
        switch self {
        case .invalidUrl:
            return "Invalid LlamaFarm URL"
        case .invalidResponse:
            return "Invalid response from LlamaFarm"
        case .httpError(let code):
            return "HTTP error: \(code)"
        case .timeout:
            return "Request timed out"
        }
    }
}
