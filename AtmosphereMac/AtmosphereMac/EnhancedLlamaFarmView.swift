//
//  EnhancedLlamaFarmView.swift
//  AtmosphereMac
//
//  Enhanced LlamaFarm view with Projects, Chat, and Health tabs
//

import SwiftUI

struct EnhancedLlamaFarmView: View {
    @EnvironmentObject var llamaFarmClient: LlamaFarmAPIClient
    @EnvironmentObject var bridge: LlamaFarmBridge  // Keep for Universal Runtime access
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                VStack(alignment: .leading) {
                    Text("LlamaFarm")
                        .font(.title)
                        .fontWeight(.bold)
                    Text("Distributed AI project platform")
                        .foregroundStyle(.secondary)
                }
                
                Spacer()
                
                // Status indicators
                HStack(spacing: 16) {
                    // LlamaFarm status
                    HStack(spacing: 8) {
                        Circle()
                            .fill(llamaFarmClient.isConnected ? .green : .gray)
                            .frame(width: 10, height: 10)
                        Text("LlamaFarm")
                        Text(llamaFarmClient.healthStatus)
                            .foregroundStyle(.secondary)
                            .font(.caption)
                    }
                    
                    // Universal Runtime status
                    HStack(spacing: 8) {
                        Circle()
                            .fill(universalRuntimeColor)
                            .frame(width: 10, height: 10)
                        Text("Universal")
                        Text(universalRuntimeStatus)
                            .foregroundStyle(.secondary)
                            .font(.caption)
                    }
                }
            }
            .padding()
            .background(Color(.windowBackgroundColor))
            
            Divider()
            
            // Tabs
            TabView {
                // Projects Tab
                LFProjectsTab()
                    .environmentObject(llamaFarmClient)
                    .tabItem {
                        Label("Projects", systemImage: "cube.box")
                    }
                
                // Health Tab
                LFHealthTab()
                    .environmentObject(llamaFarmClient)
                    .environmentObject(bridge)
                    .tabItem {
                        Label("Health", systemImage: "heart.text.square")
                    }
                
                // Models Tab (from bridge - vision models)
                LFVisionModelsTab()
                    .environmentObject(bridge)
                    .tabItem {
                        Label("Vision Models", systemImage: "eye")
                    }
            }
        }
    }
    
    private var universalRuntimeColor: Color {
        switch bridge.state {
        case .connected: return .green
        case .connecting: return .yellow
        case .error: return .red
        case .disconnected: return .gray
        }
    }
    
    private var universalRuntimeStatus: String {
        switch bridge.state {
        case .connected: return "online"
        case .connecting: return "connecting"
        case .error(let msg): return "error"
        case .disconnected: return "offline"
        }
    }
}

// MARK: - Projects Tab

struct LFProjectsTab: View {
    @EnvironmentObject var llamaFarmClient: LlamaFarmAPIClient
    @State private var selectedProject: LFDiscoverableProject?
    
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("\(llamaFarmClient.discoverableProjects.count) discoverable projects")
                    .foregroundStyle(.secondary)
                Spacer()
            }
            .padding()
            
            Divider()
            
            if llamaFarmClient.discoverableProjects.isEmpty {
                VStack(spacing: 16) {
                    Image(systemName: "cube.box")
                        .font(.system(size: 60))
                        .foregroundStyle(.secondary)
                    Text("No discoverable projects")
                        .foregroundStyle(.secondary)
                    Text("Projects must be marked as discoverable in llamafarm.yaml")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                HSplitView {
                    // Project list
                    List(llamaFarmClient.discoverableProjects, selection: $selectedProject) { project in
                        ProjectRow(project: project)
                    }
                    .frame(minWidth: 300)
                    
                    // Project detail
                    if let project = selectedProject {
                        ProjectDetailPane(project: project)
                    } else {
                        VStack {
                            Image(systemName: "cube")
                                .font(.system(size: 60))
                                .foregroundStyle(.secondary)
                            Text("Select a project")
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    }
                }
            }
        }
    }
}

struct ProjectRow: View {
    let project: LFDiscoverableProject
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(project.name)
                .fontWeight(.medium)
            
            HStack {
                Text(project.namespace)
                    .font(.caption)
                    .foregroundStyle(.blue)
                
                if let model = project.modelName {
                    Text("•")
                        .foregroundStyle(.secondary)
                        .font(.caption)
                    Text(model)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 4)
    }
}

struct ProjectDetailPane: View {
    let project: LFDiscoverableProject
    @EnvironmentObject var llamaFarmClient: LlamaFarmAPIClient
    @State private var isTesting: Bool = false
    @State private var testResult: String = ""
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Project info
                VStack(alignment: .leading, spacing: 8) {
                    Text(project.name)
                        .font(.title2)
                        .fontWeight(.bold)
                    
                    if let description = project.description {
                        Text(description)
                            .foregroundStyle(.secondary)
                    }
                }
                
                Divider()
                
                // Details
                LabeledContent("Namespace") {
                    Text(project.namespace)
                        .font(.system(.body, design: .monospaced))
                }
                
                LabeledContent("Project ID") {
                    Text(project.id)
                        .font(.system(.body, design: .monospaced))
                }
                
                if let model = project.modelName {
                    LabeledContent("Model") {
                        Text(model)
                    }
                }
                
                if let provider = project.provider {
                    LabeledContent("Provider") {
                        Text(provider)
                    }
                }
                
                Divider()
                
                // Quick test
                VStack(alignment: .leading, spacing: 8) {
                    Text("Quick Test")
                        .font(.headline)
                    
                    Button {
                        testProject()
                    } label: {
                        Label(isTesting ? "Testing..." : "Send Test Message", systemImage: "play.circle")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(isTesting)
                    
                    if !testResult.isEmpty {
                        Text(testResult)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .padding(8)
                            .background(Color(.controlBackgroundColor))
                            .cornerRadius(6)
                    }
                }
                
                Spacer()
            }
            .padding()
        }
    }
    
    private func testProject() {
        isTesting = true
        testResult = ""
        
        Task {
            do {
                let messages = [LFChatMessage(role: "user", content: "Hello! Please respond with a short greeting.")]
                let response = try await llamaFarmClient.chatWithProject(
                    namespace: project.namespace,
                    project: project.id,
                    messages: messages,
                    maxTokens: 50
                )
                
                if let firstChoice = response.choices.first {
                    await MainActor.run {
                        testResult = "✅ Response: \(firstChoice.message.content)"
                        isTesting = false
                    }
                } else {
                    await MainActor.run {
                        testResult = "⚠️ No response"
                        isTesting = false
                    }
                }
            } catch {
                await MainActor.run {
                    testResult = "❌ Error: \(error.localizedDescription)"
                    isTesting = false
                }
            }
        }
    }
}

// MARK: - Health Tab

struct LFHealthTab: View {
    @EnvironmentObject var llamaFarmClient: LlamaFarmAPIClient
    @EnvironmentObject var bridge: LlamaFarmBridge
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // LlamaFarm Server Health
                GroupBox {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Circle()
                                .fill(llamaFarmClient.isConnected ? .green : .gray)
                                .frame(width: 10, height: 10)
                            Text("LlamaFarm Server")
                                .fontWeight(.medium)
                            Spacer()
                            Text(llamaFarmClient.healthStatus)
                                .foregroundStyle(.secondary)
                        }
                        
                        LabeledContent("Endpoint") {
                            Text(llamaFarmClient.baseUrl)
                                .font(.system(.caption, design: .monospaced))
                        }
                        
                        if let error = llamaFarmClient.lastError {
                            Text("Error: \(error)")
                                .font(.caption)
                                .foregroundColor(.red)
                        }
                    }
                } label: {
                    Label("LlamaFarm Server (Port 14345)", systemImage: "server.rack")
                }
                
                // Seeds info
                if !llamaFarmClient.seeds.isEmpty {
                    GroupBox {
                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(llamaFarmClient.seeds) { seed in
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(seed.nodeId)
                                        .font(.system(.caption, design: .monospaced))
                                    
                                    if let runtime = seed.runtime {
                                        HStack {
                                            if let model = runtime.model {
                                                Text(model)
                                                    .font(.caption)
                                                    .foregroundStyle(.secondary)
                                            }
                                            if let provider = runtime.provider {
                                                Text("• \(provider)")
                                                    .font(.caption)
                                                    .foregroundStyle(.blue)
                                            }
                                        }
                                    }
                                }
                                .padding(.vertical, 4)
                                
                                if seed.id != llamaFarmClient.seeds.last?.id {
                                    Divider()
                                }
                            }
                        }
                    } label: {
                        Label("Seeds (\(llamaFarmClient.seeds.count))", systemImage: "leaf")
                    }
                }
                
                // Universal Runtime Health
                GroupBox {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Circle()
                                .fill(universalRuntimeColor)
                                .frame(width: 10, height: 10)
                            Text("Universal Runtime")
                                .fontWeight(.medium)
                            Spacer()
                            Text(universalRuntimeStatus)
                                .foregroundStyle(.secondary)
                        }
                        
                        LabeledContent("Endpoint") {
                            Text(bridge.baseUrl)
                                .font(.system(.caption, design: .monospaced))
                        }
                        
                        if let lastCheck = bridge.lastHealthCheck {
                            LabeledContent("Last Check") {
                                Text(lastCheck, style: .relative)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        
                        LabeledContent("Models") {
                            Text("\(bridge.availableModels.count)")
                        }
                    }
                } label: {
                    Label("Universal Runtime (Port 11540)", systemImage: "cpu")
                }
                
                // Available models from Universal Runtime
                if !bridge.availableModels.isEmpty {
                    GroupBox {
                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(bridge.availableModels) { model in
                                HStack {
                                    Image(systemName: model.loaded ? "checkmark.circle.fill" : "circle")
                                        .foregroundColor(model.loaded ? .green : .gray)
                                    
                                    VStack(alignment: .leading) {
                                        Text(model.name)
                                            .fontWeight(.medium)
                                        Text(model.task)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                    
                                    Spacer()
                                    
                                    if let device = model.device {
                                        Text(device)
                                            .font(.caption)
                                            .foregroundStyle(.blue)
                                    }
                                }
                                .padding(.vertical, 4)
                                
                                if model.id != bridge.availableModels.last?.id {
                                    Divider()
                                }
                            }
                        }
                    } label: {
                        Label("Vision Models (\(bridge.availableModels.count))", systemImage: "eye")
                    }
                }
            }
            .padding()
        }
    }
    
    private var universalRuntimeColor: Color {
        switch bridge.state {
        case .connected: return .green
        case .connecting: return .yellow
        case .error: return .red
        case .disconnected: return .gray
        }
    }
    
    private var universalRuntimeStatus: String {
        switch bridge.state {
        case .connected: return "online"
        case .connecting: return "connecting"
        case .error(let msg): return "error"
        case .disconnected: return "offline"
        }
    }
}

// MARK: - Vision Models Tab

struct LFVisionModelsTab: View {
    @EnvironmentObject var bridge: LlamaFarmBridge
    
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("\(bridge.availableModels.count) vision models")
                    .foregroundStyle(.secondary)
                Spacer()
                
                if let lastCheck = bridge.lastHealthCheck {
                    Text("Updated \(lastCheck, style: .relative)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding()
            
            Divider()
            
            if bridge.availableModels.isEmpty {
                VStack(spacing: 16) {
                    Image(systemName: "eye.slash")
                        .font(.system(size: 60))
                        .foregroundStyle(.secondary)
                    Text("No vision models loaded")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(bridge.availableModels) { model in
                    HStack {
                        Image(systemName: taskIcon(model.task))
                            .foregroundColor(taskColor(model.task))
                        
                        VStack(alignment: .leading) {
                            Text(model.name)
                                .fontWeight(.medium)
                            
                            HStack(spacing: 8) {
                                Text(model.task)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                
                                if let device = model.device {
                                    Text("• \(device)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                        
                        Spacer()
                        
                        if model.loaded {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundColor(.green)
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
    }
    
    private func taskIcon(_ task: String) -> String {
        switch task {
        case "detection": return "viewfinder.circle"
        case "classification": return "tag.circle"
        default: return "cube"
        }
    }
    
    private func taskColor(_ task: String) -> Color {
        switch task {
        case "detection": return .blue
        case "classification": return .purple
        default: return .gray
        }
    }
}

#Preview {
    EnhancedLlamaFarmView()
        .environmentObject(LlamaFarmAPIClient())
        .environmentObject(LlamaFarmBridge())
}
