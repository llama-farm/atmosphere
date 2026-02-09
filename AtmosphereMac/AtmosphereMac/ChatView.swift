//
//  ChatView.swift
//  AtmosphereMac
//
//  Chat interface for testing inference with LlamaFarm projects
//

import SwiftUI

struct ChatView: View {
    @EnvironmentObject var llamaFarmClient: LlamaFarmAPIClient
    
    @State private var selectedProject: LFDiscoverableProject?
    @State private var messages: [ChatBubble] = []
    @State private var inputText: String = ""
    @State private var isProcessing: Bool = false
    @State private var lastLatencyMs: Double = 0
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                VStack(alignment: .leading) {
                    Text("AI Chat")
                        .font(.title)
                        .fontWeight(.bold)
                    Text("Test inference with LlamaFarm projects")
                        .foregroundStyle(.secondary)
                }
                
                Spacer()
                
                // Project selector
                if !llamaFarmClient.discoverableProjects.isEmpty {
                    HStack {
                        Text("Project:")
                        Picker("", selection: $selectedProject) {
                            Text("Select a project...").tag(nil as LFDiscoverableProject?)
                            ForEach(llamaFarmClient.discoverableProjects) { project in
                                Text(project.name).tag(project as LFDiscoverableProject?)
                            }
                        }
                        .frame(width: 200)
                    }
                }
                
                // Clear button
                Button {
                    messages.removeAll()
                } label: {
                    Label("Clear", systemImage: "trash")
                }
                .buttonStyle(.bordered)
                .disabled(messages.isEmpty)
            }
            .padding()
            .background(Color(.windowBackgroundColor))
            
            Divider()
            
            if selectedProject == nil {
                // Project selection prompt
                VStack(spacing: 16) {
                    Image(systemName: "bubble.left.and.bubble.right")
                        .font(.system(size: 60))
                        .foregroundStyle(.secondary)
                    
                    if llamaFarmClient.discoverableProjects.isEmpty {
                        Text("No discoverable projects available")
                            .foregroundStyle(.secondary)
                        Text("Check LlamaFarm server status")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else {
                        Text("Select a project to start chatting")
                            .foregroundStyle(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                
            } else {
                // Chat interface
                VStack(spacing: 0) {
                    // Project info bar
                    HStack {
                        Image(systemName: "cube")
                            .foregroundColor(.blue)
                        VStack(alignment: .leading) {
                            Text(selectedProject!.name)
                                .fontWeight(.medium)
                            if let model = selectedProject!.modelName {
                                Text(model)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        
                        Spacer()
                        
                        if lastLatencyMs > 0 {
                            Text(String(format: "%.0f ms", lastLatencyMs))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding()
                    .background(Color(.controlBackgroundColor))
                    
                    Divider()
                    
                    // Chat messages
                    ScrollViewReader { proxy in
                        ScrollView {
                            LazyVStack(alignment: .leading, spacing: 12) {
                                ForEach(messages) { message in
                                    ChatBubbleView(bubble: message)
                                        .id(message.id)
                                }
                                
                                if isProcessing {
                                    HStack {
                                        ProgressView()
                                            .controlSize(.small)
                                        Text("Thinking...")
                                            .foregroundStyle(.secondary)
                                            .font(.caption)
                                    }
                                    .padding()
                                }
                            }
                            .padding()
                        }
                        .onChange(of: messages.count) { _ in
                            if let lastMessage = messages.last {
                                withAnimation {
                                    proxy.scrollTo(lastMessage.id, anchor: .bottom)
                                }
                            }
                        }
                    }
                    
                    Divider()
                    
                    // Input area
                    HStack(spacing: 12) {
                        TextField("Type a message...", text: $inputText, axis: .vertical)
                            .textFieldStyle(.plain)
                            .lineLimit(1...5)
                            .padding(8)
                            .background(Color(.controlBackgroundColor))
                            .cornerRadius(8)
                            .disabled(isProcessing)
                            .onSubmit {
                                sendMessage()
                            }
                        
                        Button {
                            sendMessage()
                        } label: {
                            Image(systemName: isProcessing ? "stop.circle.fill" : "arrow.up.circle.fill")
                                .font(.title2)
                        }
                        .buttonStyle(.borderless)
                        .disabled(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                    .padding()
                }
            }
        }
    }
    
    private func sendMessage() {
        guard let project = selectedProject else { return }
        let userMessage = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !userMessage.isEmpty else { return }
        
        // Add user message
        let userBubble = ChatBubble(role: "user", content: userMessage)
        messages.append(userBubble)
        inputText = ""
        isProcessing = true
        
        Task {
            let startTime = Date()
            
            do {
                // Build message history
                let chatMessages = messages.map { bubble in
                    LFChatMessage(role: bubble.role, content: bubble.content)
                }
                
                // Send to LlamaFarm
                let response = try await llamaFarmClient.chatWithProject(
                    namespace: project.namespace,
                    project: project.id,
                    messages: chatMessages,
                    temperature: 0.7,
                    maxTokens: 512
                )
                
                let latency = Date().timeIntervalSince(startTime) * 1000
                lastLatencyMs = latency
                
                // Add assistant response
                if let firstChoice = response.choices.first {
                    let assistantBubble = ChatBubble(
                        role: firstChoice.message.role,
                        content: firstChoice.message.content
                    )
                    await MainActor.run {
                        messages.append(assistantBubble)
                        isProcessing = false
                    }
                } else {
                    await MainActor.run {
                        isProcessing = false
                    }
                }
                
            } catch {
                print("❌ Chat error: \(error)")
                let errorBubble = ChatBubble(
                    role: "system",
                    content: "Error: \(error.localizedDescription)"
                )
                await MainActor.run {
                    messages.append(errorBubble)
                    isProcessing = false
                }
            }
        }
    }
}

// MARK: - Chat Bubble Model

struct ChatBubble: Identifiable {
    let id = UUID()
    let role: String
    let content: String
    let timestamp = Date()
}

// MARK: - Chat Bubble View

struct ChatBubbleView: View {
    let bubble: ChatBubble
    
    var body: some View {
        HStack {
            if bubble.role == "user" {
                Spacer()
            }
            
            VStack(alignment: bubble.role == "user" ? .trailing : .leading, spacing: 4) {
                Text(roleLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                
                Text(bubble.content)
                    .padding(12)
                    .background(backgroundColor)
                    .foregroundColor(textColor)
                    .cornerRadius(12)
                    .textSelection(.enabled)
                
                Text(bubble.timestamp, style: .time)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: 600, alignment: bubble.role == "user" ? .trailing : .leading)
            
            if bubble.role != "user" {
                Spacer()
            }
        }
    }
    
    private var roleLabel: String {
        switch bubble.role {
        case "user": return "You"
        case "assistant": return "Assistant"
        case "system": return "System"
        default: return bubble.role.capitalized
        }
    }
    
    private var backgroundColor: Color {
        switch bubble.role {
        case "user": return .blue
        case "system": return .red.opacity(0.2)
        default: return Color(.controlBackgroundColor)
        }
    }
    
    private var textColor: Color {
        bubble.role == "user" ? .white : .primary
    }
}

#Preview {
    ChatView()
        .environmentObject(LlamaFarmAPIClient())
}
