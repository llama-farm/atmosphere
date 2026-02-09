//
//  GossipView.swift
//  AtmosphereMac
//
//  Gossip protocol monitoring and capability table
//

import SwiftUI

struct GossipView: View {
    @EnvironmentObject var atmosphereClient: AtmosphereAPIClient
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                VStack(alignment: .leading) {
                    Text("Gossip Protocol")
                        .font(.title)
                        .fontWeight(.bold)
                    Text("Peer-to-peer message propagation and capability discovery")
                        .foregroundStyle(.secondary)
                }
                
                Spacer()
                
                // Status indicator
                HStack(spacing: 8) {
                    Circle()
                        .fill(atmosphereClient.isConnected ? .green : .gray)
                        .frame(width: 10, height: 10)
                    Text(atmosphereClient.gossipStatus?.protocolState ?? "unknown")
                }
            }
            .padding()
            .background(Color(.windowBackgroundColor))
            
            Divider()
            
            // Tabs
            TabView {
                // Status Tab
                GossipStatusTab()
                    .environmentObject(atmosphereClient)
                    .tabItem {
                        Label("Status", systemImage: "chart.bar")
                    }
                
                // Capabilities Table
                CapabilitiesTableTab()
                    .environmentObject(atmosphereClient)
                    .tabItem {
                        Label("Capabilities", systemImage: "list.bullet.rectangle")
                    }
                
                // Statistics
                GossipStatsTab()
                    .environmentObject(atmosphereClient)
                    .tabItem {
                        Label("Statistics", systemImage: "chart.line.uptrend.xyaxis")
                    }
            }
        }
    }
}

// MARK: - Status Tab

struct GossipStatusTab: View {
    @EnvironmentObject var atmosphereClient: AtmosphereAPIClient
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                if let status = atmosphereClient.gossipStatus {
                    // Protocol state
                    GroupBox {
                        VStack(alignment: .leading, spacing: 12) {
                            LabeledContent("Protocol State") {
                                Text(status.protocolState)
                                    .foregroundColor(stateColor(status.protocolState))
                                    .fontWeight(.medium)
                            }
                            
                            LabeledContent("Connected Peers") {
                                Text("\(status.peerCount)")
                                    .fontWeight(.medium)
                            }
                            
                            LabeledContent("Messages Sent") {
                                Text("\(status.messagesSent)")
                            }
                            
                            LabeledContent("Messages Received") {
                                Text("\(status.messagesReceived)")
                            }
                            
                            LabeledContent("Data Transferred") {
                                Text(formatBytes(status.bytesTransferred))
                            }
                        }
                    } label: {
                        Label("Protocol Status", systemImage: "network")
                    }
                    
                } else {
                    VStack(spacing: 16) {
                        Image(systemName: "network.slash")
                            .font(.system(size: 60))
                            .foregroundStyle(.secondary)
                        Text("Gossip data not available")
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .padding()
        }
    }
    
    private func stateColor(_ state: String) -> Color {
        switch state.lowercased() {
        case "active", "running": return .green
        case "initializing": return .yellow
        case "stopped", "error": return .red
        default: return .gray
        }
    }
    
    private func formatBytes(_ bytes: Int) -> String {
        let formatter = ByteCountFormatter()
        formatter.countStyle = .binary
        return formatter.string(fromByteCount: Int64(bytes))
    }
}

// MARK: - Capabilities Table

struct CapabilitiesTableTab: View {
    @EnvironmentObject var atmosphereClient: AtmosphereAPIClient
    
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("\(atmosphereClient.capabilities.count) capabilities across the mesh")
                    .foregroundStyle(.secondary)
                    .padding()
                Spacer()
            }
            
            Divider()
            
            if atmosphereClient.capabilities.isEmpty {
                VStack(spacing: 16) {
                    Image(systemName: "list.bullet.rectangle")
                        .font(.system(size: 60))
                        .foregroundStyle(.secondary)
                    Text("No capabilities discovered")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List {
                    ForEach(groupedCapabilities.keys.sorted(), id: \.self) { nodeName in
                        Section(nodeName) {
                            ForEach(groupedCapabilities[nodeName] ?? []) { capability in
                                HStack {
                                    Image(systemName: capabilityIcon(capability.name))
                                        .foregroundColor(capabilityColor(capability.name))
                                    
                                    VStack(alignment: .leading) {
                                        Text(capability.name)
                                            .fontWeight(.medium)
                                        
                                        if let version = capability.version {
                                            Text("v\(version)")
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                        }
                                    }
                                    
                                    Spacer()
                                    
                                    Text(capability.nodeId.prefix(8) + "...")
                                        .font(.caption)
                                        .foregroundStyle(.blue)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    
    private var groupedCapabilities: [String: [AtmosphereCapability]] {
        Dictionary(grouping: atmosphereClient.capabilities, by: { $0.nodeName })
    }
    
    private func capabilityIcon(_ name: String) -> String {
        let lowerName = name.lowercased()
        if lowerName.contains("llm") || lowerName.contains("chat") {
            return "text.bubble"
        } else if lowerName.contains("vision") || lowerName.contains("detect") {
            return "eye"
        } else if lowerName.contains("embedding") {
            return "point.3.connected.trianglepath.dotted"
        } else if lowerName.contains("tts") || lowerName.contains("speech") {
            return "speaker.wave.2"
        } else {
            return "star"
        }
    }
    
    private func capabilityColor(_ name: String) -> Color {
        let lowerName = name.lowercased()
        if lowerName.contains("llm") || lowerName.contains("chat") {
            return .green
        } else if lowerName.contains("vision") || lowerName.contains("detect") {
            return .blue
        } else if lowerName.contains("embedding") {
            return .orange
        } else if lowerName.contains("tts") || lowerName.contains("speech") {
            return .purple
        } else {
            return .gray
        }
    }
}

// MARK: - Statistics Tab

struct GossipStatsTab: View {
    @EnvironmentObject var atmosphereClient: AtmosphereAPIClient
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                if let stats = atmosphereClient.gossipStats {
                    // Performance metrics
                    GroupBox {
                        VStack(alignment: .leading, spacing: 12) {
                            LabeledContent("Avg Latency") {
                                Text(String(format: "%.1f ms", stats.avgLatencyMs))
                                    .foregroundColor(latencyColor(stats.avgLatencyMs))
                                    .fontWeight(.medium)
                            }
                            
                            LabeledContent("Success Rate") {
                                HStack {
                                    ProgressView(value: stats.successRate)
                                        .frame(width: 100)
                                    Text(String(format: "%.1f%%", stats.successRate * 100))
                                        .foregroundColor(successRateColor(stats.successRate))
                                        .fontWeight(.medium)
                                }
                            }
                            
                            LabeledContent("Message Queue") {
                                Text("\(stats.messageQueue)")
                                    .foregroundColor(stats.messageQueue > 100 ? .red : .primary)
                            }
                        }
                    } label: {
                        Label("Performance Metrics", systemImage: "speedometer")
                    }
                    
                    // Active topics
                    GroupBox {
                        if stats.activeTopics.isEmpty {
                            Text("No active topics")
                                .foregroundStyle(.secondary)
                        } else {
                            VStack(alignment: .leading, spacing: 8) {
                                ForEach(stats.activeTopics, id: \.self) { topic in
                                    Label(topic, systemImage: "antenna.radiowaves.left.and.right")
                                }
                            }
                        }
                    } label: {
                        Label("Active Topics (\(stats.activeTopics.count))", systemImage: "list.bullet")
                    }
                    
                } else {
                    VStack(spacing: 16) {
                        Image(systemName: "chart.line.uptrend.xyaxis")
                            .font(.system(size: 60))
                            .foregroundStyle(.secondary)
                        Text("Statistics not available")
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .padding()
        }
    }
    
    private func latencyColor(_ latency: Double) -> Color {
        if latency < 50 { return .green }
        if latency < 200 { return .yellow }
        return .red
    }
    
    private func successRateColor(_ rate: Double) -> Color {
        if rate > 0.95 { return .green }
        if rate > 0.80 { return .yellow }
        return .red
    }
}

#Preview {
    GossipView()
        .environmentObject(AtmosphereAPIClient())
}
