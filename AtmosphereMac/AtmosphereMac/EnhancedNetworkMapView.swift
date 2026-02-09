//
//  EnhancedNetworkMapView.swift
//  AtmosphereMac
//
//  Enhanced network map showing real mesh peers, devices, and capabilities
//

import SwiftUI

struct EnhancedNetworkMapView: View {
    @EnvironmentObject var meshManager: BLEMeshManager
    @EnvironmentObject var relayManager: RelayManager
    @EnvironmentObject var atmosphereClient: AtmosphereAPIClient
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                VStack(alignment: .leading) {
                    Text("Network Map")
                        .font(.title)
                        .fontWeight(.bold)
                    Text("Mesh topology and node visualization")
                        .foregroundStyle(.secondary)
                }
                
                Spacer()
                
                // Stats
                HStack(spacing: 20) {
                    StatLabel(icon: "antenna.radiowaves.left.and.right", label: "BLE", value: "\(meshManager.peers.count)")
                    StatLabel(icon: "cloud", label: "Relay", value: "\(relayManager.connectedNodes.count)")
                    StatLabel(icon: "desktopcomputer", label: "Devices", value: "\(atmosphereClient.devices.count)")
                    StatLabel(icon: "star", label: "Capabilities", value: "\(atmosphereClient.capabilities.count)")
                }
            }
            .padding()
            .background(Color(.windowBackgroundColor))
            
            Divider()
            
            TabView {
                // Visual Map Tab
                NetworkVisualizationTab()
                    .environmentObject(meshManager)
                    .environmentObject(relayManager)
                    .environmentObject(atmosphereClient)
                    .tabItem {
                        Label("Map", systemImage: "map")
                    }
                
                // Peers List Tab
                PeersListTab()
                    .environmentObject(atmosphereClient)
                    .tabItem {
                        Label("Peers", systemImage: "person.2")
                    }
                
                // Devices List Tab
                DevicesListTab()
                    .environmentObject(atmosphereClient)
                    .tabItem {
                        Label("Devices", systemImage: "laptopcomputer")
                    }
            }
        }
    }
}

struct StatLabel: View {
    let icon: String
    let label: String
    let value: String
    
    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .foregroundStyle(.secondary)
            Text(label)
                .foregroundStyle(.secondary)
                .font(.caption)
            Text(value)
                .fontWeight(.semibold)
        }
    }
}

// MARK: - Visual Map Tab

struct NetworkVisualizationTab: View {
    @EnvironmentObject var meshManager: BLEMeshManager
    @EnvironmentObject var relayManager: RelayManager
    @EnvironmentObject var atmosphereClient: AtmosphereAPIClient
    
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                // Center node (this Mac)
                VStack {
                    Image(systemName: "laptopcomputer.circle.fill")
                        .font(.system(size: 50))
                        .foregroundColor(.blue)
                    Text(meshManager.nodeName)
                        .font(.caption)
                        .fontWeight(.medium)
                    Text("(This Mac)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                .position(x: geometry.size.width / 2, y: geometry.size.height / 2)
                
                // BLE peers in inner circle
                ForEach(Array(meshManager.peers.enumerated()), id: \.element.id) { index, peer in
                    bleNode(index: index, peer: peer, totalCount: meshManager.peers.count, radius: 120, geometry: geometry)
                }
                
                // Relay nodes in middle circle
                ForEach(Array(relayManager.connectedNodes.enumerated()), id: \.element.id) { index, node in
                    relayNode(index: index, node: node, totalCount: relayManager.connectedNodes.count, radius: 200, geometry: geometry)
                }
                
                // API peers in outer circle (from Atmosphere server)
                ForEach(Array(atmosphereClient.peers.enumerated()), id: \.element.id) { index, peer in
                    apiPeerNode(index: index, peer: peer, totalCount: atmosphereClient.peers.count, radius: 280, geometry: geometry)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .padding()
    }
    
    @ViewBuilder
    private func bleNode(index: Int, peer: MeshPeer, totalCount: Int, radius: CGFloat, geometry: GeometryProxy) -> some View {
        let angle = angleFor(index: index, total: totalCount, offset: 0)
        let position = positionFor(angle: angle, radius: radius, geometry: geometry)
        
        VStack {
            Image(systemName: "candybarphone")
                .font(.system(size: 30))
                .foregroundColor(peer.isConnected ? .green : .gray)
            Text(peer.name)
                .font(.caption2)
            Text("\(peer.rssi) dBm")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .position(position)
    }
    
    @ViewBuilder
    private func relayNode(index: Int, node: RelayNode, totalCount: Int, radius: CGFloat, geometry: GeometryProxy) -> some View {
        let angle = angleFor(index: index, total: totalCount, offset: 0.3)
        let position = positionFor(angle: angle, radius: radius, geometry: geometry)
        
        VStack {
            Image(systemName: "cloud.fill")
                .font(.system(size: 25))
                .foregroundColor(.blue)
            Text(node.name)
                .font(.caption2)
            Text(node.platform)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .position(position)
    }
    
    @ViewBuilder
    private func apiPeerNode(index: Int, peer: AtmospherePeer, totalCount: Int, radius: CGFloat, geometry: GeometryProxy) -> some View {
        let angle = angleFor(index: index, total: totalCount, offset: 0.6)
        let position = positionFor(angle: angle, radius: radius, geometry: geometry)
        
        VStack {
            Image(systemName: sourceIcon(peer.source))
                .font(.system(size: 25))
                .foregroundColor(sourceColor(peer.source))
            Text(peer.name)
                .font(.caption2)
            Text(peer.source)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .position(position)
    }
    
    private func angleFor(index: Int, total: Int, offset: Double) -> Double {
        guard total > 0 else { return 0 }
        return Double(index) * (2.0 * Double.pi / Double(total)) + offset
    }
    
    private func positionFor(angle: Double, radius: CGFloat, geometry: GeometryProxy) -> CGPoint {
        let x = geometry.size.width / 2.0 + radius * CGFloat(cos(angle))
        let y = geometry.size.height / 2.0 + radius * CGFloat(sin(angle))
        return CGPoint(x: x, y: y)
    }
    
    private func sourceIcon(_ source: String) -> String {
        switch source.lowercased() {
        case "mdns": return "network"
        case "relay": return "cloud"
        case "ble": return "antenna.radiowaves.left.and.right"
        default: return "circle"
        }
    }
    
    private func sourceColor(_ source: String) -> Color {
        switch source.lowercased() {
        case "mdns": return .green
        case "relay": return .blue
        case "ble": return .purple
        default: return .gray
        }
    }
}

// MARK: - Peers List Tab

struct PeersListTab: View {
    @EnvironmentObject var atmosphereClient: AtmosphereAPIClient
    
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("\(atmosphereClient.peers.count) peers")
                    .foregroundStyle(.secondary)
                Spacer()
            }
            .padding()
            
            Divider()
            
            if atmosphereClient.peers.isEmpty {
                VStack(spacing: 16) {
                    Image(systemName: "person.2")
                        .font(.system(size: 60))
                        .foregroundStyle(.secondary)
                    Text("No peers discovered")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List {
                    ForEach(groupedPeers.keys.sorted(), id: \.self) { source in
                        Section(source.capitalized) {
                            ForEach(groupedPeers[source] ?? []) { peer in
                                PeerRowView(peer: peer)
                            }
                        }
                    }
                }
            }
        }
    }
    
    private var groupedPeers: [String: [AtmospherePeer]] {
        Dictionary(grouping: atmosphereClient.peers, by: { $0.source })
    }
}

struct PeerRowView: View {
    let peer: AtmospherePeer
    
    var body: some View {
        HStack {
            Image(systemName: sourceIcon(peer.source))
                .foregroundColor(sourceColor(peer.source))
            
            VStack(alignment: .leading) {
                Text(peer.name)
                    .fontWeight(.medium)
                
                HStack(spacing: 8) {
                    Text(peer.id.prefix(12) + "...")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    
                    if let latency = peer.latencyMs {
                        Text("\(latency)ms")
                            .font(.caption)
                            .foregroundStyle(latencyColor(latency))
                    }
                    
                    if !peer.capabilities.isEmpty {
                        Text("• \(peer.capabilities.count) caps")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            
            Spacer()
            
            if let lastSeen = peer.lastSeen {
                Text(lastSeen)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
    
    private func sourceIcon(_ source: String) -> String {
        switch source.lowercased() {
        case "mdns": return "network"
        case "relay": return "cloud"
        case "ble": return "antenna.radiowaves.left.and.right"
        default: return "circle"
        }
    }
    
    private func sourceColor(_ source: String) -> Color {
        switch source.lowercased() {
        case "mdns": return .green
        case "relay": return .blue
        case "ble": return .purple
        default: return .gray
        }
    }
    
    private func latencyColor(_ latency: Int) -> Color {
        if latency < 50 { return .green }
        if latency < 200 { return .yellow }
        return .red
    }
}

// MARK: - Devices List Tab

struct DevicesListTab: View {
    @EnvironmentObject var atmosphereClient: AtmosphereAPIClient
    
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("\(atmosphereClient.devices.count) devices")
                    .foregroundStyle(.secondary)
                Spacer()
            }
            .padding()
            
            Divider()
            
            if atmosphereClient.devices.isEmpty {
                VStack(spacing: 16) {
                    Image(systemName: "desktopcomputer")
                        .font(.system(size: 60))
                        .foregroundStyle(.secondary)
                    Text("No devices connected")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(atmosphereClient.devices) { device in
                    DeviceRowView(device: device)
                }
            }
        }
    }
}

struct DeviceRowView: View {
    let device: AtmosphereDevice
    
    var body: some View {
        HStack {
            Image(systemName: deviceIcon(device.type))
                .foregroundColor(device.connected ? .green : .gray)
            
            VStack(alignment: .leading) {
                Text(device.name)
                    .fontWeight(.medium)
                
                HStack(spacing: 8) {
                    Text(device.type)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    
                    Text(device.connected ? "connected" : "disconnected")
                        .font(.caption)
                        .foregroundStyle(device.connected ? .green : .secondary)
                }
            }
            
            Spacer()
            
            if let lastSeen = device.lastSeen {
                Text(lastSeen)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
    
    private func deviceIcon(_ type: String) -> String {
        switch type.lowercased() {
        case "phone", "mobile": return "candybarphone"
        case "tablet": return "ipad"
        case "laptop", "computer": return "laptopcomputer"
        case "desktop": return "desktopcomputer"
        default: return "desktopcomputer"
        }
    }
}

#Preview {
    EnhancedNetworkMapView()
        .environmentObject(BLEMeshManager())
        .environmentObject(RelayManager())
        .environmentObject(AtmosphereAPIClient())
}
