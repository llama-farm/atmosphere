//
//  LlamaFarmAPIClient.swift
//  AtmosphereMac
//
//  API client for LlamaFarm server (http://localhost:14345)
//

import Foundation
import Combine

// MARK: - Response Models

struct LFDiscoverableProject: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let namespace: String
    let description: String?
    let modelName: String?
    let provider: String?
    
    enum CodingKeys: String, CodingKey {
        case id
        case name
        case namespace
        case description
        case modelName = "model_name"
        case provider
    }
}

struct LFDiscoverableProjectsResponse: Codable {
    let projects: [LFDiscoverableProject]
}

// LFHealthResponse, LFSeed, and LFRuntimeInfo are defined in LlamaFarmBridge.swift

struct LFChatRequest: Codable {
    let messages: [LFChatMessage]
    let temperature: Double?
    let maxTokens: Int?
    let stream: Bool?
    
    enum CodingKeys: String, CodingKey {
        case messages
        case temperature
        case maxTokens = "max_tokens"
        case stream
    }
}

struct LFChatMessage: Codable {
    let role: String
    let content: String
}

struct LFChatResponse: Codable {
    let id: String
    let choices: [LFChatChoice]
    let model: String?
    let usage: LFTokenUsage?
}

struct LFChatChoice: Codable {
    let index: Int
    let message: LFChatMessage
    let finishReason: String?
    
    enum CodingKeys: String, CodingKey {
        case index
        case message
        case finishReason = "finish_reason"
    }
}

struct LFTokenUsage: Codable {
    let promptTokens: Int
    let completionTokens: Int
    let totalTokens: Int
    
    enum CodingKeys: String, CodingKey {
        case promptTokens = "prompt_tokens"
        case completionTokens = "completion_tokens"
        case totalTokens = "total_tokens"
    }
}

// MARK: - LlamaFarm API Client

@MainActor
class LlamaFarmAPIClient: ObservableObject {
    
    // MARK: Published State
    @Published var isConnected: Bool = false
    @Published var discoverableProjects: [LFDiscoverableProject] = []
    @Published var seeds: [LFSeed] = []
    @Published var healthStatus: String = "unknown"
    @Published var lastError: String?
    
    // Configuration
    @Published var baseUrl: String = "http://localhost:14345"
    
    private var refreshTask: Task<Void, Never>?
    private let refreshInterval: TimeInterval = 10.0
    
    // MARK: Init
    
    init() {
        print("🦙 LlamaFarm API Client initialized")
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
    
    // Projects endpoint
    
    func fetchDiscoverableProjects() async throws -> [LFDiscoverableProject] {
        let response: LFDiscoverableProjectsResponse = try await get("/v1/projects/discoverable")
        return response.projects
    }
    
    // Health endpoint
    
    func fetchHealth() async throws -> LFHealthResponse {
        return try await get("/health")
    }
    
    // Chat with a specific project
    
    func chatWithProject(namespace: String, project: String, messages: [LFChatMessage], temperature: Double? = nil, maxTokens: Int? = nil) async throws -> LFChatResponse {
        let request = LFChatRequest(
            messages: messages,
            temperature: temperature,
            maxTokens: maxTokens,
            stream: false
        )
        let path = "/v1/projects/discoverable/\(namespace):\(project)/chat/completions"
        return try await post(path, body: request)
    }
    
    // MARK: - Auto Refresh
    
    private func startAutoRefresh() {
        refreshTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refreshAll()
                try? await Task.sleep(for: .seconds(self?.refreshInterval ?? 10.0))
            }
        }
    }
    
    private func refreshAll() async {
        do {
            // Fetch health and projects
            async let healthTask = fetchHealth()
            async let projectsTask = fetchDiscoverableProjects()
            
            let (health, projects) = try await (healthTask, projectsTask)
            
            self.healthStatus = health.status
            self.seeds = health.seeds ?? []
            self.discoverableProjects = projects
            self.isConnected = true
            self.lastError = nil
            
        } catch {
            self.isConnected = false
            self.lastError = error.localizedDescription
            print("❌ LlamaFarm refresh error: \(error)")
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
        request.timeoutInterval = 60.0  // Longer for inference
        
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
