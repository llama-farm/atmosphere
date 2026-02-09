//
//  ModelCatalogService.swift
//  AtmosphereMac
//
//  Discovers models from LlamaFarm and gossips them to the mesh.
//

import Foundation
import Combine

// MARK: - Model Catalog Types

struct ModelCapability: Codable, Identifiable, Hashable {
    let id: String  // model_id
    let name: String
    let task: String  // "detection", "classification", "llm", "embedding"
    let sizeMb: Float?
    let device: String?
    let loaded: Bool
    let nodeId: String  // Which node has this model
    
    enum CodingKeys: String, CodingKey {
        case id, name, task
        case sizeMb = "size_mb"
        case device, loaded
        case nodeId = "node_id"
    }
}

struct ModelCatalogMessage: Codable {
    let type: String  // "model_catalog"
    let nodeId: String
    let nodeName: String
    let capabilities: [ModelCapability]
    let timestamp: String
    
    enum CodingKeys: String, CodingKey {
        case type
        case nodeId = "node_id"
        case nodeName = "node_name"
        case capabilities, timestamp
    }
}

struct ModelTransferRequest: Codable {
    let type: String  // "model_request"
    let modelId: String
    let requestingNode: String
    
    enum CodingKeys: String, CodingKey {
        case type
        case modelId = "model_id"
        case requestingNode = "requesting_node"
    }
}

struct ModelTransferChunk: Codable {
    let type: String  // "model_transfer"
    let modelId: String
    let chunkIndex: Int
    let totalChunks: Int
    let data: String  // base64
    let checksum: String
    
    enum CodingKeys: String, CodingKey {
        case type
        case modelId = "model_id"
        case chunkIndex = "chunk_index"
        case totalChunks = "total_chunks"
        case data, checksum
    }
}

// MARK: - Model Catalog Service

@MainActor
class ModelCatalogService: ObservableObject {
    
    // MARK: Published State
    @Published var localModels: [ModelCapability] = []
    @Published var meshModels: [ModelCapability] = []  // Models from other nodes
    @Published var lastSync: Date?
    @Published var transferProgress: [String: Float] = [:]  // modelId -> progress
    
    // Dependencies
    private let bridge: LlamaFarmBridge
    private let meshManager: BLEMeshManager
    private let relayManager: RelayManager
    
    // Configuration
    private let syncInterval: TimeInterval = 300.0  // 5 minutes
    private let chunkSize = 256 * 1024  // 256KB chunks for transfer
    
    private var syncTask: Task<Void, Never>?
    private var cancellables = Set<AnyCancellable>()
    
    // MARK: Init
    
    init(bridge: LlamaFarmBridge, meshManager: BLEMeshManager, relayManager: RelayManager) {
        self.bridge = bridge
        self.meshManager = meshManager
        self.relayManager = relayManager
        
        setupMessageListeners()
        startPeriodicSync()
        
        log("📚 Model Catalog Service initialized")
    }
    
    deinit {
        syncTask?.cancel()
    }
    
    // MARK: - Public API
    
    /// Manually trigger a sync with LlamaFarm
    func syncNow() async {
        await performSync()
    }
    
    /// Get all available models (local + mesh)
    var allModels: [ModelCapability] {
        localModels + meshModels
    }
    
    /// Request a model from another node
    func requestModel(modelId: String, fromNode nodeId: String) async throws {
        log("📥 Requesting model \(modelId) from \(nodeId)")
        
        let request = ModelTransferRequest(
            type: "model_request",
            modelId: modelId,
            requestingNode: meshManager.nodeId
        )
        
        guard let data = try? JSONEncoder().encode(request) else {
            throw CatalogError.encodingFailed
        }
        
        meshManager.sendMessage(to: nodeId, payload: data)
    }
    
    // MARK: - Periodic Sync
    
    private func startPeriodicSync() {
        syncTask = Task { [weak self] in
            // Initial sync
            await self?.performSync()
            
            // Then periodic
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(syncInterval))
                await self?.performSync()
            }
        }
    }
    
    private func performSync() async {
        log("🔄 Syncing model catalog...")
        
        do {
            // Query LlamaFarm for available vision models
            let models = try await bridge.listModels()
            
            // Query packages endpoint for additional metadata
            let packages = try await bridge.listPackages()
            
            // Build package map
            var packageMap: [String: LFModelPackage] = [:]
            for pkg in packages {
                packageMap[pkg.modelId] = pkg
            }
            
            // Convert to ModelCapability format
            localModels = models.map { model in
                let pkg = packageMap[model.id]
                
                return ModelCapability(
                    id: model.id,
                    name: model.name,
                    task: model.task,
                    sizeMb: pkg?.sizeMb,
                    device: model.device,
                    loaded: model.loaded,
                    nodeId: meshManager.nodeId
                )
            }
            
            lastSync = Date()
            log("✅ Synced \(localModels.count) local models (\(packages.count) packages)")
            
            // Gossip to mesh
            await gossipCatalog()
            
        } catch {
            log("❌ Sync failed: \(error.localizedDescription)")
        }
    }
    
    // MARK: - Mesh Gossiping
    
    private func gossipCatalog() async {
        let message = ModelCatalogMessage(
            type: "model_catalog",
            nodeId: meshManager.nodeId,
            nodeName: meshManager.nodeName,
            capabilities: localModels,
            timestamp: ISO8601DateFormatter().string(from: Date())
        )
        
        guard let data = try? JSONEncoder().encode(message) else {
            log("❌ Failed to encode catalog")
            return
        }
        
        // Broadcast to all connected peers
        meshManager.broadcastMessage(payload: data)
        relayManager.broadcast(payload: data)
        
        log("📡 Gossiped catalog to mesh (\(localModels.count) models)")
    }
    
    // MARK: - Message Handling
    
    private func setupMessageListeners() {
        meshManager.$messages
            .sink { [weak self] messages in
                Task { @MainActor in
                    guard let self = self else { return }
                    for message in messages {
                        if message.type == .data {
                            await self.handleMeshMessage(message.payload, from: message.sourceId)
                        }
                    }
                }
            }
            .store(in: &cancellables)
    }
    
    private func handleMeshMessage(_ data: Data, from sourceId: String) async {
        // Try to decode as catalog message
        if let catalog = try? JSONDecoder().decode(ModelCatalogMessage.self, from: data),
           catalog.type == "model_catalog" {
            handleCatalogMessage(catalog)
            return
        }
        
        // Try to decode as model request
        if let request = try? JSONDecoder().decode(ModelTransferRequest.self, from: data),
           request.type == "model_request" {
            await handleModelRequest(request, from: sourceId)
            return
        }
        
        // Try to decode as model transfer chunk
        if let chunk = try? JSONDecoder().decode(ModelTransferChunk.self, from: data),
           chunk.type == "model_transfer" {
            await handleModelChunk(chunk)
            return
        }
    }
    
    private func handleCatalogMessage(_ catalog: ModelCatalogMessage) {
        log("📨 Received catalog from \(catalog.nodeName): \(catalog.capabilities.count) models")
        
        // Merge into meshModels (dedupe by node + model)
        for capability in catalog.capabilities {
            // Remove old entries from this node
            meshModels.removeAll { $0.nodeId == catalog.nodeId && $0.id == capability.id }
            
            // Add new entry
            meshModels.append(capability)
        }
        
        // Clean up stale entries (older than 10 minutes)
        let cutoff = Date().addingTimeInterval(-600)
        let decoder = ISO8601DateFormatter()
        meshModels.removeAll { model in
            // We'd need to track timestamps per model, simplified for now
            false
        }
    }
    
    private func handleModelRequest(_ request: ModelTransferRequest, from sourceId: String) async {
        log("📤 Node \(sourceId) requesting model \(request.modelId)")
        
        // Check if we have this model
        guard localModels.contains(where: { $0.id == request.modelId }) else {
            log("⚠️ Don't have model \(request.modelId)")
            return
        }
        
        // In a real implementation, we'd:
        // 1. Export the model to a temporary package (tar.gz)
        // 2. Split into chunks
        // 3. Send chunks via mesh
        
        // For now, just log
        log("TODO: Implement model transfer for \(request.modelId)")
    }
    
    private func handleModelChunk(_ chunk: ModelTransferChunk) async {
        log("📥 Received chunk \(chunk.chunkIndex + 1)/\(chunk.totalChunks) for \(chunk.modelId)")
        
        // Track progress
        let progress = Float(chunk.chunkIndex + 1) / Float(chunk.totalChunks)
        transferProgress[chunk.modelId] = progress
        
        // In a real implementation:
        // 1. Accumulate chunks in temporary directory
        // 2. Verify checksums
        // 3. Reassemble when complete
        // 4. Import into LlamaFarm
        
        if chunk.chunkIndex == chunk.totalChunks - 1 {
            log("✅ Model \(chunk.modelId) transfer complete")
            transferProgress.removeValue(forKey: chunk.modelId)
        }
    }
    
    // MARK: - Model Transfer (Outbound)
    
    func exportAndTransferModel(modelId: String, to nodeId: String) async throws {
        log("📦 Packaging model \(modelId) for transfer...")
        
        // This would call LlamaFarm's model export/package endpoints
        // POST /v1/vision/models/package with model_id
        // Then stream the resulting .tar.gz in chunks
        
        // For now, placeholder
        throw CatalogError.notImplemented
    }
    
    private func log(_ message: String) {
        print("[ModelCatalog] \(message)")
    }
}

// MARK: - Errors

enum CatalogError: LocalizedError {
    case encodingFailed
    case notImplemented
    case modelNotFound
    case transferFailed
    
    var errorDescription: String? {
        switch self {
        case .encodingFailed:
            return "Failed to encode message"
        case .notImplemented:
            return "Feature not yet implemented"
        case .modelNotFound:
            return "Model not found"
        case .transferFailed:
            return "Model transfer failed"
        }
    }
}
