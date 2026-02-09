//
//  VisionEscalationHandler.swift
//  AtmosphereMac
//
//  Handles escalation requests from mesh nodes and routes to LlamaFarm.
//

import Foundation
import Combine

// MARK: - Escalation Types (matches Android/LlamaFarm)

struct ModelOpinion: Codable {
    let modelId: String
    let nodeId: String
    let className: String
    let confidence: Float
    let bbox: [Float]?  // [x1, y1, x2, y2]
    let maskPolygon: [[Float]]?
    let inferenceTimeMs: Float
    let timestamp: String
    
    enum CodingKeys: String, CodingKey {
        case modelId = "model_id"
        case nodeId = "node_id"
        case className = "class_name"
        case confidence, bbox
        case maskPolygon = "mask_polygon"
        case inferenceTimeMs = "inference_time_ms"
        case timestamp
    }
}

struct EscalationEnvelope: Codable {
    let imageBase64: String
    let imageHash: String
    let sourceId: String
    let timestamp: String
    var opinions: [ModelOpinion]
    var detections: [DetectionWithMask]?
    let originNode: String
    var hops: Int
    let maxHops: Int
    let urgency: String?
    
    enum CodingKeys: String, CodingKey {
        case imageBase64 = "image_base64"
        case imageHash = "image_hash"
        case sourceId = "source_id"
        case timestamp, opinions, detections
        case originNode = "origin_node"
        case hops
        case maxHops = "max_hops"
        case urgency
    }
}

struct DetectionWithMask: Codable {
    let bbox: [Float]
    let cropBytes: String?  // base64
    let maskPolygon: [[Float]]?
    let maskRle: String?
    let className: String
    let confidence: Float
    
    enum CodingKeys: String, CodingKey {
        case bbox
        case cropBytes = "crop_bytes"
        case maskPolygon = "mask_polygon"
        case maskRle = "mask_rle"
        case className = "class_name"
        case confidence
    }
}

struct EscalationRequest: Codable {
    let type: String  // "escalation_request"
    let envelope: EscalationEnvelope
}

struct EscalationResponse: Codable {
    let type: String  // "escalation_response"
    let requestId: String
    let success: Bool
    var envelope: EscalationEnvelope?  // Updated envelope with new opinions
    let error: String?
    
    enum CodingKeys: String, CodingKey {
        case type
        case requestId = "request_id"
        case success, envelope, error
    }
}

// MARK: - Escalation Activity

struct EscalationActivity: Identifiable {
    let id = UUID()
    let timestamp: Date
    let sourceNode: String
    let originalModel: String
    let originalConfidence: Float
    let escalatedToModel: String
    let finalConfidence: Float?
    let result: String  // "resolved", "failed", "hops_exceeded"
    let duration: TimeInterval
}

// MARK: - Escalation Handler

@MainActor
class VisionEscalationHandler: ObservableObject {
    
    // MARK: Published State
    @Published var activities: [EscalationActivity] = []
    @Published var pendingCount: Int = 0
    @Published var totalHandled: Int = 0
    @Published var successRate: Float = 0.0
    
    // Dependencies
    private let bridge: LlamaFarmBridge
    private let meshManager: BLEMeshManager
    private let relayManager: RelayManager
    
    // Configuration
    private let defaultEscalationModel = "yolov8m"  // Bigger model for escalations
    private let maxConcurrentEscalations = 3
    
    private var cancellables = Set<AnyCancellable>()
    private var activeEscalations: [String: Task<Void, Never>] = [:]
    
    // MARK: Init
    
    init(bridge: LlamaFarmBridge, meshManager: BLEMeshManager, relayManager: RelayManager) {
        self.bridge = bridge
        self.meshManager = meshManager
        self.relayManager = relayManager
        
        setupMessageListeners()
        log("🎯 Vision Escalation Handler initialized")
    }
    
    // MARK: - Message Handling
    
    private func setupMessageListeners() {
        // Listen for escalation messages on BLE mesh
        meshManager.$messages
            .sink { [weak self] messages in
                Task { @MainActor in
                    guard let self = self else { return }
                    for message in messages {
                        if message.type == .data {
                            await self.handlePotentialEscalation(message.payload, from: message.sourceId)
                        }
                    }
                }
            }
            .store(in: &cancellables)
        
        // Also listen on relay (for remote nodes)
        // Note: RelayManager would need a similar message publisher
    }
    
    private func handlePotentialEscalation(_ data: Data, from sourceId: String) async {
        // Try to decode as escalation request
        guard let request = try? JSONDecoder().decode(EscalationRequest.self, from: data) else {
            return  // Not an escalation request, ignore
        }
        
        guard request.type == "escalation_request" else { return }
        
        log("📨 Escalation request from \(sourceId)")
        
        // Circuit breaker: check hops
        if request.envelope.hops >= request.envelope.maxHops {
            log("⚠️ Max hops exceeded, sending to review queue")
            await sendToReviewQueue(request.envelope)
            return
        }
        
        // Rate limiting: max concurrent
        if activeEscalations.count >= maxConcurrentEscalations {
            log("⚠️ Too many active escalations, queuing")
            // Could implement a queue here
            return
        }
        
        // Handle the escalation
        let requestId = UUID().uuidString
        let task = Task {
            await processEscalation(request.envelope, requestId: requestId, sourceId: sourceId)
        }
        
        activeEscalations[requestId] = task
        pendingCount = activeEscalations.count
    }
    
    // MARK: - Escalation Processing
    
    private func processEscalation(_ envelope: EscalationEnvelope, requestId: String, sourceId: String) async {
        let startTime = Date()
        
        defer {
            activeEscalations.removeValue(forKey: requestId)
            pendingCount = activeEscalations.count
        }
        
        // Determine which model to use for escalation
        let escalationModel = selectEscalationModel(for: envelope)
        
        log("🔍 Processing escalation with \(escalationModel)")
        
        do {
            // Forward to LlamaFarm federation escalate endpoint
            let escalateResponse = try await bridge.escalate(
                envelope: envelope,
                model: escalationModel,
                confidenceThreshold: 0.5
            )
            
            // Build updated envelope with LlamaFarm's opinion
            var updatedEnvelope = envelope
            updatedEnvelope.hops += 1
            
            // LlamaFarm returns the opinion directly
            if let lfOpinion = escalateResponse.opinion {
                let opinion = ModelOpinion(
                    modelId: lfOpinion.modelId,
                    nodeId: lfOpinion.nodeId,
                    className: lfOpinion.className,
                    confidence: lfOpinion.confidence,
                    bbox: lfOpinion.bbox,
                    maskPolygon: lfOpinion.maskPolygon,
                    inferenceTimeMs: lfOpinion.inferenceTimeMs,
                    timestamp: ISO8601DateFormatter().string(from: Date())
                )
                updatedEnvelope.opinions.append(opinion)
            } else {
                // Fallback if no opinion returned
                log("⚠️ No opinion in escalation response")
                await sendEscalationResponse(
                    requestId: requestId,
                    envelope: updatedEnvelope,
                    success: false,
                    to: sourceId
                )
                recordActivity(envelope: envelope, opinion: nil, result: "failed", duration: Date().timeIntervalSince(startTime))
                return
            }
            
            let opinion = updatedEnvelope.opinions.last!
            
            // Check if LlamaFarm resolved it (auto-added to replay if so)
            let resolved = escalateResponse.resolved
            
            if resolved {
                log("✅ Escalation resolved: \(opinion.className) (\(Int(opinion.confidence * 100))%)")
                
                if escalateResponse.addedToReplay {
                    log("📝 LlamaFarm auto-added to replay buffer")
                }
                
                // Send response back to originating node
                await sendEscalationResponse(
                    requestId: requestId,
                    envelope: updatedEnvelope,
                    success: true,
                    to: sourceId
                )
                
                // Record activity
                recordActivity(envelope: envelope, opinion: opinion, result: "resolved", duration: Date().timeIntervalSince(startTime))
                
            } else if updatedEnvelope.hops >= updatedEnvelope.maxHops {
                log("⚠️ Still uncertain after max hops, sending to review")
                
                await sendToReviewQueue(updatedEnvelope)
                
                await sendEscalationResponse(
                    requestId: requestId,
                    envelope: updatedEnvelope,
                    success: false,
                    to: sourceId
                )
                
                recordActivity(envelope: envelope, opinion: opinion, result: "hops_exceeded", duration: Date().timeIntervalSince(startTime))
                
            } else {
                log("🔄 Still uncertain, could escalate further")
                
                // Could forward to another node here
                await sendEscalationResponse(
                    requestId: requestId,
                    envelope: updatedEnvelope,
                    success: false,
                    to: sourceId
                )
                
                recordActivity(envelope: envelope, opinion: opinion, result: "unresolved", duration: Date().timeIntervalSince(startTime))
            }
            
        } catch {
            log("❌ Escalation failed: \(error.localizedDescription)")
            
            await sendEscalationResponse(
                requestId: requestId,
                envelope: envelope,
                success: false,
                to: sourceId
            )
            
            recordActivity(envelope: envelope, opinion: nil, result: "failed", duration: Date().timeIntervalSince(startTime))
        }
    }
    
    // MARK: - Model Selection
    
    private func selectEscalationModel(for envelope: EscalationEnvelope) -> String {
        // Look at what models have already been tried
        let triedModels = Set(envelope.opinions.map { $0.modelId })
        
        // Cascade chain: yolov8n -> yolov8m -> yolov8x
        let availableModels = ["yolov8m", "yolov8l", "yolov8x"]
        
        for model in availableModels {
            if !triedModels.contains(model) {
                // Check if LlamaFarm has this model
                if bridge.availableModels.contains(where: { $0.id == model }) {
                    return model
                }
            }
        }
        
        // Fallback to default
        return defaultEscalationModel
    }
    
    // MARK: - Response Handling
    
    private func sendEscalationResponse(requestId: String, envelope: EscalationEnvelope?, success: Bool, to nodeId: String) async {
        let response = EscalationResponse(
            type: "escalation_response",
            requestId: requestId,
            success: success,
            envelope: envelope,
            error: success ? nil : "Escalation failed or unresolved"
        )
        
        guard let data = try? JSONEncoder().encode(response) else {
            log("❌ Failed to encode response")
            return
        }
        
        // Send back via the same channel it came from
        meshManager.sendMessage(to: nodeId, payload: data)
    }
    
    private func sendToReviewQueue(_ envelope: EscalationEnvelope) async {
        // LlamaFarm's review queue endpoint
        // For now, just log it. Could POST to /v1/vision/review
        log("📋 Added to review queue: \(envelope.imageHash)")
    }
    
    // MARK: - Activity Tracking
    
    private func recordActivity(envelope: EscalationEnvelope, opinion: ModelOpinion?, result: String, duration: TimeInterval) {
        let originalOpinion = envelope.opinions.first
        
        let activity = EscalationActivity(
            timestamp: Date(),
            sourceNode: envelope.originNode,
            originalModel: originalOpinion?.modelId ?? "unknown",
            originalConfidence: originalOpinion?.confidence ?? 0.0,
            escalatedToModel: opinion?.modelId ?? "none",
            finalConfidence: opinion?.confidence,
            result: result,
            duration: duration
        )
        
        activities.insert(activity, at: 0)
        
        // Keep history manageable
        if activities.count > 100 {
            activities.removeLast(20)
        }
        
        totalHandled += 1
        
        // Update success rate
        let successes = activities.filter { $0.result == "resolved" }.count
        successRate = activities.isEmpty ? 0.0 : Float(successes) / Float(activities.count)
    }
    
    private func log(_ message: String) {
        print("[Escalation] \(message)")
    }
}
