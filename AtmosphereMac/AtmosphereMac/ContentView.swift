//
//  ContentView.swift
//  AtmosphereMac
//
//  Main view for Atmosphere control center.
//

import SwiftUI
import CoreBluetooth

struct ContentView: View {
    @EnvironmentObject var meshManager: BLEMeshManager
    @EnvironmentObject var relayManager: RelayManager
    @EnvironmentObject var llamaFarmBridge: LlamaFarmBridge
    @EnvironmentObject var escalationHandler: VisionEscalationHandler
    @EnvironmentObject var modelCatalog: ModelCatalogService
    @EnvironmentObject var atmosphereClient: AtmosphereAPIClient
    @EnvironmentObject var llamaFarmClient: LlamaFarmAPIClient
    
    @State private var selectedTab = 0
    
    var body: some View {
        NavigationSplitView {
            // Sidebar
            List(selection: $selectedTab) {
                Section("Connectivity") {
                    Label("BLE Mesh", systemImage: "antenna.radiowaves.left.and.right")
                        .tag(0)
                    Label("Cloud Relay", systemImage: "cloud")
                        .tag(1)
                }
                
                Section("AI Services") {
                    Label("LlamaFarm", systemImage: "cpu")
                        .tag(2)
                    Label("Chat", systemImage: "bubble.left.and.bubble.right")
                        .tag(9)
                    Label("Training", systemImage: "graduationcap")
                        .tag(7)
                    Label("Model Catalog", systemImage: "cube.box")
                        .tag(8)
                }
                
                Section("Monitoring") {
                    Label("Network Map", systemImage: "network")
                        .tag(3)
                    Label("Gossip", systemImage: "chart.bar")
                        .tag(10)
                    Label("Messages", systemImage: "message")
                        .tag(4)
                    Label("Logs", systemImage: "doc.text")
                        .tag(5)
                }
                
                Section("Settings") {
                    Label("Node Identity", systemImage: "person.circle")
                        .tag(6)
                    Label("Invites", systemImage: "key")
                        .tag(11)
                }
            }
            .listStyle(.sidebar)
            .frame(minWidth: 200)
            
        } detail: {
            // Main content
            Group {
                switch selectedTab {
                case 0:
                    BLEMeshView()
                case 1:
                    RelayView()
                case 2:
                    EnhancedLlamaFarmView()
                case 3:
                    EnhancedNetworkMapView()
                case 4:
                    MessagesView()
                case 5:
                    LogsView()
                case 6:
                    NodeIdentityView()
                case 7:
                    TrainingPanelView()
                case 8:
                    ModelCatalogDetailView()
                case 9:
                    ChatView()
                case 10:
                    GossipView()
                case 11:
                    InviteView()
                default:
                    BLEMeshView()
                }
            }
            .frame(minWidth: 500)
        }
        .toolbar {
            ToolbarItemGroup(placement: .automatic) {
                // BLE Status
                HStack(spacing: 4) {
                    Circle()
                        .fill(meshManager.isScanning ? Color.green : Color.gray)
                        .frame(width: 8, height: 8)
                    Text("BLE")
                        .font(.caption)
                }
                
                // Relay Status
                HStack(spacing: 4) {
                    Circle()
                        .fill(relayManager.state == .connected ? Color.green : Color.gray)
                        .frame(width: 8, height: 8)
                    Text("Relay")
                        .font(.caption)
                }
                
                // Atmosphere Server Status
                HStack(spacing: 4) {
                    Circle()
                        .fill(atmosphereClient.isConnected ? Color.green : Color.gray)
                        .frame(width: 8, height: 8)
                    Text("Atmo")
                        .font(.caption)
                }
                
                // LlamaFarm Status
                HStack(spacing: 4) {
                    Circle()
                        .fill(llamaFarmClient.isConnected ? Color.green : Color.gray)
                        .frame(width: 8, height: 8)
                    Text("LF")
                        .font(.caption)
                }
                
                // Universal Runtime Status
                HStack(spacing: 4) {
                    Circle()
                        .fill(llamaFarmStatusColor)
                        .frame(width: 8, height: 8)
                    Text("UR")
                        .font(.caption)
                }
                
                Divider()
                
                // Peer count
                Label("\(totalPeerCount)", systemImage: "person.2")
                    .help("Connected peers")
            }
        }
        .onAppear {
            // Sync node identity
            relayManager.nodeId = meshManager.nodeId
            relayManager.nodeName = meshManager.nodeName
            relayManager.capabilities = meshManager.capabilities
        }
    }
    
    var llamaFarmStatusColor: Color {
        switch llamaFarmBridge.state {
        case .connected: return .green
        case .connecting: return .yellow
        case .error: return .red
        case .disconnected: return .gray
        }
    }
    
    var totalPeerCount: Int {
        let blePeers = meshManager.peers.count
        let relayPeers = relayManager.connectedNodes.count
        let atmoPeers = atmosphereClient.peers.count
        // Use max to avoid double-counting
        return max(blePeers + relayPeers, atmoPeers)
    }
}

// MARK: - BLE Mesh View
struct BLEMeshView: View {
    @EnvironmentObject var meshManager: BLEMeshManager
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                VStack(alignment: .leading) {
                    Text("BLE Mesh")
                        .font(.title)
                        .fontWeight(.bold)
                    Text("Local device discovery via Bluetooth Low Energy")
                        .foregroundStyle(.secondary)
                }
                
                Spacer()
                
                // Controls
                HStack(spacing: 12) {
                    Button {
                        if meshManager.isScanning {
                            meshManager.stopScanning()
                        } else {
                            meshManager.startScanning()
                        }
                    } label: {
                        Label(
                            meshManager.isScanning ? "Stop Scan" : "Start Scan",
                            systemImage: meshManager.isScanning ? "stop.circle.fill" : "magnifyingglass"
                        )
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(meshManager.isScanning ? .red : .blue)
                    
                    Button {
                        if meshManager.isAdvertising {
                            meshManager.stopAdvertising()
                        } else {
                            meshManager.startAdvertising()
                        }
                    } label: {
                        Label(
                            meshManager.isAdvertising ? "Stop Advertise" : "Advertise",
                            systemImage: meshManager.isAdvertising ? "antenna.radiowaves.left.and.right.slash" : "antenna.radiowaves.left.and.right"
                        )
                    }
                    .buttonStyle(.bordered)
                }
            }
            .padding()
            .background(Color(.windowBackgroundColor))
            
            Divider()
            
            // Bluetooth State
            if meshManager.bluetoothState != .poweredOn {
                BluetoothWarningBanner(state: meshManager.bluetoothState)
            }
            
            // Peer List
            if meshManager.peers.isEmpty {
                EmptyPeerView()
            } else {
                List(meshManager.peers) { peer in
                    PeerRow(peer: peer) {
                        if peer.isConnected {
                            meshManager.disconnectFromPeer(peer)
                        } else {
                            meshManager.connectToPeer(peer)
                        }
                    }
                }
            }
        }
    }
}

struct BluetoothWarningBanner: View {
    let state: CBManagerState
    
    var body: some View {
        HStack {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(.yellow)
            
            Text(warningText)
            
            Spacer()
            
            if state == .poweredOff {
                Button("Open Settings") {
                    NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preferences.Bluetooth")!)
                }
                .buttonStyle(.bordered)
            }
        }
        .padding()
        .background(Color.yellow.opacity(0.15))
    }
    
    var warningText: String {
        switch state {
        case .poweredOff: return "Bluetooth is turned off"
        case .unauthorized: return "Bluetooth access not authorized"
        case .unsupported: return "Bluetooth not supported"
        default: return "Bluetooth initializing..."
        }
    }
}

struct EmptyPeerView: View {
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "antenna.radiowaves.left.and.right")
                .font(.system(size: 60))
                .foregroundStyle(.secondary)
            
            Text("No Peers Discovered")
                .font(.title2)
                .fontWeight(.medium)
            
            Text("Start scanning to discover nearby Atmosphere nodes.\nMake sure BLE is enabled on your Android device.")
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
            
            VStack(alignment: .leading, spacing: 8) {
                Text("📱 On Android:")
                    .fontWeight(.medium)
                Text("App → Test tab → Connectivity → BLE Mesh → Start")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            .padding()
            .background(Color(.controlBackgroundColor))
            .cornerRadius(8)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }
}

struct PeerRow: View {
    let peer: MeshPeer
    let onConnect: () -> Void
    
    var body: some View {
        HStack {
            // Status indicator
            Circle()
                .fill(peer.isConnected ? Color.green : Color.gray)
                .frame(width: 10, height: 10)
            
            VStack(alignment: .leading) {
                Text(peer.name)
                    .fontWeight(.medium)
                
                HStack(spacing: 8) {
                    Text(peer.id.prefix(8) + "...")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    
                    Text("RSSI: \(peer.rssi) dBm")
                        .font(.caption)
                        .foregroundStyle(rssiColor)
                    
                    if !peer.capabilities.isEmpty {
                        Text(peer.capabilities.joined(separator: ", "))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            
            Spacer()
            
            Button(peer.isConnected ? "Disconnect" : "Connect") {
                onConnect()
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
        .padding(.vertical, 4)
    }
    
    var rssiColor: Color {
        if peer.rssi > -50 { return .green }
        if peer.rssi > -70 { return .yellow }
        return .red
    }
}

// MARK: - Relay View
struct RelayView: View {
    @EnvironmentObject var relayManager: RelayManager
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                VStack(alignment: .leading) {
                    Text("Cloud Relay")
                        .font(.title)
                        .fontWeight(.bold)
                    Text("Internet-based mesh connectivity")
                        .foregroundStyle(.secondary)
                }
                
                Spacer()
                
                // Status
                HStack(spacing: 8) {
                    Circle()
                        .fill(stateColor)
                        .frame(width: 10, height: 10)
                    Text(relayManager.state.rawValue)
                    
                    if let latency = relayManager.latency {
                        Text("(\(latency)ms)")
                            .foregroundStyle(.secondary)
                    }
                }
                
                Button {
                    if relayManager.state == .connected {
                        relayManager.disconnect()
                    } else {
                        relayManager.connect()
                    }
                } label: {
                    Label(
                        relayManager.state == .connected ? "Disconnect" : "Connect",
                        systemImage: relayManager.state == .connected ? "xmark.circle" : "link"
                    )
                }
                .buttonStyle(.borderedProminent)
                .tint(relayManager.state == .connected ? .red : .blue)
            }
            .padding()
            .background(Color(.windowBackgroundColor))
            
            Divider()
            
            // URL config
            HStack {
                Text("Relay URL:")
                TextField("wss://...", text: $relayManager.relayUrl)
                    .textFieldStyle(.roundedBorder)
                    .disabled(relayManager.state == .connected)
            }
            .padding()
            
            Divider()
            
            // Connected nodes
            if relayManager.connectedNodes.isEmpty {
                VStack(spacing: 16) {
                    Image(systemName: "cloud")
                        .font(.system(size: 60))
                        .foregroundStyle(.secondary)
                    
                    Text(relayManager.state == .connected ? "No other nodes online" : "Connect to see online nodes")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(relayManager.connectedNodes) { node in
                    HStack {
                        Image(systemName: platformIcon(node.platform))
                        
                        VStack(alignment: .leading) {
                            Text(node.name)
                                .fontWeight(.medium)
                            Text("\(node.platform) • \(node.capabilities.joined(separator: ", "))")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        
                        Spacer()
                        
                        Button("Message") {
                            // Send message
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }
                }
            }
        }
    }
    
    var stateColor: Color {
        switch relayManager.state {
        case .connected: return .green
        case .connecting: return .yellow
        case .error: return .red
        case .disconnected: return .gray
        }
    }
    
    func platformIcon(_ platform: String) -> String {
        switch platform.lowercased() {
        case "android": return "candybarphone"
        case "ios": return "iphone"
        case "macos": return "laptopcomputer"
        default: return "desktopcomputer"
        }
    }
}

// MARK: - Network Map View
struct NetworkMapView: View {
    @EnvironmentObject var meshManager: BLEMeshManager
    @EnvironmentObject var relayManager: RelayManager
    
    var body: some View {
        VStack {
            Text("Network Map")
                .font(.title)
                .fontWeight(.bold)
            
            // Simple network visualization
            GeometryReader { geometry in
                ZStack {
                    // Center node (this Mac)
                    VStack {
                        Image(systemName: "laptopcomputer")
                            .font(.system(size: 40))
                        Text(meshManager.nodeName)
                            .font(.caption)
                    }
                    .position(x: geometry.size.width / 2, y: geometry.size.height / 2)
                    
                    // BLE peers in a circle
                    ForEach(Array(meshManager.peers.enumerated()), id: \.element.id) { index, peer in
                        peerNode(index: index, peer: peer, totalCount: meshManager.peers.count, radius: 150, geometry: geometry)
                    }
                    
                    // Relay nodes further out
                    ForEach(Array(relayManager.connectedNodes.enumerated()), id: \.element.id) { index, node in
                        relayNode(index: index, node: node, totalCount: relayManager.connectedNodes.count, radius: 250, geometry: geometry)
                    }
                }
            }
        }
        .padding()
    }

    @ViewBuilder
    private func peerNode(index: Int, peer: MeshPeer, totalCount: Int, radius: CGFloat, geometry: GeometryProxy) -> some View {
        let angle: Double = Double(index) * (2.0 * Double.pi / max(Double(totalCount), 1.0))
        let x: CGFloat = geometry.size.width / 2.0 + radius * CGFloat(cos(angle))
        let y: CGFloat = geometry.size.height / 2.0 + radius * CGFloat(sin(angle))
        VStack {
            Image(systemName: "candybarphone")
                .font(.system(size: 30))
                .foregroundColor(peer.isConnected ? .green : .gray)
            Text(peer.name)
                .font(.caption2)
        }
        .position(x: x, y: y)
    }
    
    @ViewBuilder
    private func relayNode(index: Int, node: RelayNode, totalCount: Int, radius: CGFloat, geometry: GeometryProxy) -> some View {
        let angle: Double = Double(index) * (2.0 * Double.pi / max(Double(totalCount), 1.0)) + Double.pi / 4.0
        let x: CGFloat = geometry.size.width / 2.0 + radius * CGFloat(cos(angle))
        let y: CGFloat = geometry.size.height / 2.0 + radius * CGFloat(sin(angle))
        VStack {
            Image(systemName: "cloud")
                .font(.system(size: 25))
                .foregroundColor(.blue)
            Text(node.name)
                .font(.caption2)
        }
        .position(x: x, y: y)
    }
}

// MARK: - Messages View
struct MessagesView: View {
    @EnvironmentObject var meshManager: BLEMeshManager
    
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Messages")
                    .font(.title)
                    .fontWeight(.bold)
                Spacer()
                Text("\(meshManager.messages.count) messages")
                    .foregroundStyle(.secondary)
            }
            .padding()
            
            Divider()
            
            if meshManager.messages.isEmpty {
                VStack {
                    Image(systemName: "message")
                        .font(.system(size: 60))
                        .foregroundStyle(.secondary)
                    Text("No messages yet")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(meshManager.messages) { message in
                    VStack(alignment: .leading) {
                        HStack {
                            Text("From: \(message.sourceId.prefix(8))...")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text(message.timestamp, style: .time)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Text("\(message.type) - \(message.payload.count) bytes")
                            .fontWeight(.medium)
                    }
                    .padding(.vertical, 4)
                }
            }
        }
    }
}

// MARK: - Logs View
struct LogsView: View {
    @EnvironmentObject var meshManager: BLEMeshManager
    @EnvironmentObject var relayManager: RelayManager
    
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Logs")
                    .font(.title)
                    .fontWeight(.bold)
                Spacer()
                
                Button("Clear") {
                    meshManager.logs.removeAll()
                    relayManager.logs.removeAll()
                }
                .buttonStyle(.bordered)
            }
            .padding()
            
            Divider()
            
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 2) {
                        ForEach(Array(allLogs.enumerated()), id: \.offset) { index, log in
                            Text(log)
                                .font(.system(.caption, design: .monospaced))
                                .textSelection(.enabled)
                                .id(index)
                        }
                    }
                    .padding()
                }
                .onChange(of: allLogs.count) { newCount in
                    withAnimation {
                        proxy.scrollTo(newCount - 1, anchor: .bottom)
                    }
                }
            }
        }
    }
    
    var allLogs: [String] {
        (meshManager.logs + relayManager.logs).sorted()
    }
}

// MARK: - Node Identity View
struct NodeIdentityView: View {
    @EnvironmentObject var meshManager: BLEMeshManager
    
    var body: some View {
        Form {
            Section("Node Identity") {
                TextField("Node Name", text: $meshManager.nodeName)
                
                LabeledContent("Node ID") {
                    Text(meshManager.nodeId)
                        .font(.system(.body, design: .monospaced))
                        .textSelection(.enabled)
                }
            }
            
            Section("Capabilities") {
                ForEach(meshManager.capabilities, id: \.self) { cap in
                    Text(cap)
                }
            }
            
            Section("Service UUID") {
                Text(MeshUUIDs.meshService.uuidString)
                    .font(.system(.caption, design: .monospaced))
                    .textSelection(.enabled)
            }
        }
        .formStyle(.grouped)
        .padding()
    }
}

// MARK: - Settings View
struct SettingsView: View {
    var body: some View {
        TabView {
            GeneralSettingsView()
                .tabItem {
                    Label("General", systemImage: "gear")
                }
            
            BluetoothSettingsView()
                .tabItem {
                    Label("Bluetooth", systemImage: "antenna.radiowaves.left.and.right")
                }
        }
        .frame(width: 450, height: 300)
    }
}

struct GeneralSettingsView: View {
    @AppStorage("launchAtLogin") private var launchAtLogin = false
    @AppStorage("showInMenuBar") private var showInMenuBar = true
    
    var body: some View {
        Form {
            Toggle("Launch at login", isOn: $launchAtLogin)
            Toggle("Show in menu bar", isOn: $showInMenuBar)
        }
        .padding()
    }
}

struct BluetoothSettingsView: View {
    @AppStorage("autoStartScan") private var autoStartScan = false
    @AppStorage("autoStartAdvertise") private var autoStartAdvertise = true
    
    var body: some View {
        Form {
            Toggle("Auto-start scanning", isOn: $autoStartScan)
            Toggle("Auto-start advertising", isOn: $autoStartAdvertise)
        }
        .padding()
    }
}

// MARK: - Menu Bar View
struct MenuBarView: View {
    @EnvironmentObject var meshManager: BLEMeshManager
    @EnvironmentObject var relayManager: RelayManager
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Status
            HStack {
                Image(systemName: "antenna.radiowaves.left.and.right")
                Text("Atmosphere")
                    .fontWeight(.bold)
            }
            
            Divider()
            
            // BLE
            HStack {
                Circle()
                    .fill(meshManager.isScanning ? Color.green : Color.gray)
                    .frame(width: 8, height: 8)
                Text("BLE: \(meshManager.peers.count) peers")
                
                Spacer()
                
                Button(meshManager.isScanning ? "Stop" : "Scan") {
                    if meshManager.isScanning {
                        meshManager.stopScanning()
                    } else {
                        meshManager.startScanning()
                    }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
            
            // Relay
            HStack {
                Circle()
                    .fill(relayManager.state == .connected ? Color.green : Color.gray)
                    .frame(width: 8, height: 8)
                Text("Relay: \(relayManager.state.rawValue)")
                
                Spacer()
                
                Button(relayManager.state == .connected ? "Disconnect" : "Connect") {
                    if relayManager.state == .connected {
                        relayManager.disconnect()
                    } else {
                        relayManager.connect()
                    }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
            
            Divider()
            
            Button("Open Atmosphere") {
                NSApp.activate(ignoringOtherApps: true)
            }
            
            Button("Quit") {
                NSApp.terminate(nil)
            }
        }
        .padding()
        .frame(width: 280)
    }
}

// MARK: - LlamaFarm View
struct LlamaFarmView: View {
    @EnvironmentObject var bridge: LlamaFarmBridge
    @EnvironmentObject var escalationHandler: VisionEscalationHandler
    @EnvironmentObject var modelCatalog: ModelCatalogService
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                VStack(alignment: .leading) {
                    Text("LlamaFarm Vision Bridge")
                        .font(.title)
                        .fontWeight(.bold)
                    Text("AI vision escalation and model distribution")
                        .foregroundStyle(.secondary)
                }
                
                Spacer()
                
                // Status & Controls
                HStack(spacing: 12) {
                    HStack(spacing: 8) {
                        Circle()
                            .fill(stateColor)
                            .frame(width: 10, height: 10)
                        Text(stateText)
                        
                        if let lastCheck = bridge.lastHealthCheck {
                            Text("(\(timeAgo(lastCheck)))")
                                .foregroundStyle(.secondary)
                                .font(.caption)
                        }
                    }
                    
                    Button {
                        Task {
                            await bridge.connect()
                        }
                    } label: {
                        Label("Connect", systemImage: "link")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(stateColor == .green || stateColor == .yellow)
                }
            }
            .padding()
            .background(Color(.windowBackgroundColor))
            
            Divider()
            
            // URL Configuration
            HStack {
                Text("URL:")
                TextField("http://localhost:14345", text: $bridge.baseUrl)
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 400)
            }
            .padding()
            
            Divider()
            
            // Tabs
            TabView {
                // Models Tab
                ModelsListView()
                    .environmentObject(modelCatalog)
                    .tabItem {
                        Label("Models", systemImage: "cube.box")
                    }
                
                // Escalations Tab
                EscalationsListView()
                    .environmentObject(escalationHandler)
                    .tabItem {
                        Label("Escalations", systemImage: "arrow.up.right.circle")
                    }
                
                // Activity Log Tab
                ActivityLogView()
                    .environmentObject(bridge)
                    .tabItem {
                        Label("Activity", systemImage: "list.bullet")
                    }
            }
        }
    }
    
    var stateColor: Color {
        switch bridge.state {
        case .connected: return .green
        case .connecting: return .yellow
        case .error: return .red
        case .disconnected: return .gray
        }
    }
    
    var stateText: String {
        switch bridge.state {
        case .connected: return "Connected"
        case .connecting: return "Connecting..."
        case .error(let msg): return "Error: \(msg)"
        case .disconnected: return "Disconnected"
        }
    }
    
    func timeAgo(_ date: Date) -> String {
        let seconds = Int(Date().timeIntervalSince(date))
        if seconds < 60 { return "\(seconds)s ago" }
        let minutes = seconds / 60
        if minutes < 60 { return "\(minutes)m ago" }
        let hours = minutes / 60
        return "\(hours)h ago"
    }
}

struct ModelsListView: View {
    @EnvironmentObject var catalog: ModelCatalogService
    
    var body: some View {
        VStack(spacing: 0) {
            // Stats bar
            HStack {
                Text("\(catalog.localModels.count) local • \(catalog.meshModels.count) mesh")
                    .foregroundStyle(.secondary)
                
                Spacer()
                
                if let lastSync = catalog.lastSync {
                    Text("Updated \(timeAgo(lastSync))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                
                Button("Sync Now") {
                    Task { await catalog.syncNow() }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
            .padding()
            
            Divider()
            
            // Models list
            if catalog.allModels.isEmpty {
                VStack(spacing: 16) {
                    Image(systemName: "cube.box")
                        .font(.system(size: 60))
                        .foregroundStyle(.secondary)
                    Text("No models discovered")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List {
                    Section("Local Models") {
                        ForEach(catalog.localModels) { model in
                            ModelRow(model: model, isLocal: true)
                        }
                    }
                    
                    if !catalog.meshModels.isEmpty {
                        Section("Mesh Models") {
                            ForEach(catalog.meshModels) { model in
                                ModelRow(model: model, isLocal: false)
                            }
                        }
                    }
                }
            }
        }
    }
    
    func timeAgo(_ date: Date) -> String {
        let seconds = Int(Date().timeIntervalSince(date))
        if seconds < 60 { return "\(seconds)s ago" }
        let minutes = seconds / 60
        return "\(minutes)m ago"
    }
}

struct ModelRow: View {
    let model: ModelCapability
    let isLocal: Bool
    
    var body: some View {
        HStack {
            Image(systemName: taskIcon)
                .foregroundColor(taskColor)
            
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
                    
                    if !isLocal {
                        Text("• \(model.nodeId.prefix(8))...")
                            .font(.caption)
                            .foregroundStyle(.blue)
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
    
    var taskIcon: String {
        switch model.task {
        case "detection": return "viewfinder.circle"
        case "classification": return "tag.circle"
        case "llm": return "text.bubble"
        case "embedding": return "point.3.connected.trianglepath.dotted"
        default: return "cube"
        }
    }
    
    var taskColor: Color {
        switch model.task {
        case "detection": return .blue
        case "classification": return .purple
        case "llm": return .green
        case "embedding": return .orange
        default: return .gray
        }
    }
}

struct EscalationsListView: View {
    @EnvironmentObject var handler: VisionEscalationHandler
    
    var body: some View {
        VStack(spacing: 0) {
            // Stats bar
            HStack(spacing: 20) {
                StatBadge(label: "Handled", value: "\(handler.totalHandled)")
                StatBadge(label: "Pending", value: "\(handler.pendingCount)")
                StatBadge(label: "Success", value: "\(Int(handler.successRate * 100))%")
                
                Spacer()
            }
            .padding()
            
            Divider()
            
            // Activities list
            if handler.activities.isEmpty {
                VStack(spacing: 16) {
                    Image(systemName: "arrow.up.right.circle")
                        .font(.system(size: 60))
                        .foregroundStyle(.secondary)
                    Text("No escalations yet")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(handler.activities) { activity in
                    EscalationRow(activity: activity)
                }
            }
        }
    }
}

struct StatBadge: View {
    let label: String
    let value: String
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.title3)
                .fontWeight(.semibold)
        }
    }
}

struct EscalationRow: View {
    let activity: EscalationActivity
    
    var body: some View {
        HStack {
            Image(systemName: resultIcon)
                .foregroundColor(resultColor)
            
            VStack(alignment: .leading) {
                HStack {
                    Text(activity.sourceNode.prefix(8) + "...")
                        .fontWeight(.medium)
                    Text("→")
                        .foregroundStyle(.secondary)
                    Text(activity.escalatedToModel)
                }
                
                HStack(spacing: 8) {
                    Text("\(activity.originalModel): \(Int(activity.originalConfidence * 100))%")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    
                    if let finalConf = activity.finalConfidence {
                        Text("→ \(Int(finalConf * 100))%")
                            .font(.caption)
                            .foregroundStyle(finalConf > 0.7 ? .green : .orange)
                    }
                    
                    Text("• \(Int(activity.duration * 1000))ms")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            
            Spacer()
            
            Text(activity.timestamp, style: .time)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }
    
    var resultIcon: String {
        switch activity.result {
        case "resolved": return "checkmark.circle.fill"
        case "failed": return "xmark.circle.fill"
        case "hops_exceeded": return "exclamationmark.triangle.fill"
        default: return "questionmark.circle"
        }
    }
    
    var resultColor: Color {
        switch activity.result {
        case "resolved": return .green
        case "failed": return .red
        case "hops_exceeded": return .orange
        default: return .gray
        }
    }
}

struct ActivityLogView: View {
    @EnvironmentObject var bridge: LlamaFarmBridge
    
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("\(bridge.activityLog.count) entries")
                    .foregroundStyle(.secondary)
                
                Spacer()
                
                Button("Clear") {
                    bridge.activityLog.removeAll()
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
            .padding()
            
            Divider()
            
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 2) {
                    ForEach(Array(bridge.activityLog.enumerated()), id: \.offset) { index, log in
                        Text(log)
                            .font(.system(.caption, design: .monospaced))
                            .textSelection(.enabled)
                    }
                }
                .padding()
            }
        }
    }
}

// MARK: - Preview
#Preview {
    ContentView()
        .environmentObject(BLEMeshManager())
        .environmentObject(RelayManager())
}

// MARK: - Training Panel View
struct TrainingPanelView: View {
    @EnvironmentObject var bridge: LlamaFarmBridge
    @State private var selectedDatasetURL: URL?
    @State private var modelName = "custom_model"
    @State private var epochs = 10
    @State private var learningRate = "0.001"
    @State private var isTraining = false
    @State private var trainingProgress: Double = 0.0
    @State private var trainingJobs: [TrainingJob] = []
    @State private var selectedJob: TrainingJob?
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                VStack(alignment: .leading) {
                    Text("Model Training")
                        .font(.title)
                        .fontWeight(.bold)
                    Text("Train custom vision models on local datasets")
                        .foregroundStyle(.secondary)
                }
                
                Spacer()
                
                Button {
                    selectDataset()
                } label: {
                    Label("Select Dataset", systemImage: "folder")
                }
                .buttonStyle(.borderedProminent)
                .disabled(isTraining)
            }
            .padding()
            .background(Color(.windowBackgroundColor))
            
            Divider()
            
            HSplitView {
                // Training configuration
                VStack(alignment: .leading, spacing: 16) {
                    Text("Training Configuration")
                        .font(.headline)
                    
                    if let datasetURL = selectedDatasetURL {
                        LabeledContent("Dataset") {
                            Text(datasetURL.lastPathComponent)
                                .foregroundStyle(.secondary)
                        }
                    } else {
                        Text("No dataset selected")
                            .foregroundStyle(.secondary)
                    }
                    
                    TextField("Model Name", text: $modelName)
                        .textFieldStyle(.roundedBorder)
                    
                    Stepper("Epochs: \(epochs)", value: $epochs, in: 1...100)
                    
                    TextField("Learning Rate", text: $learningRate)
                        .textFieldStyle(.roundedBorder)
                    
                    if isTraining {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Training in progress...")
                                .font(.caption)
                            ProgressView(value: trainingProgress)
                            Text("\(Int(trainingProgress * 100))% complete")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    } else {
                        Button {
                            startTraining()
                        } label: {
                            Label("Start Training", systemImage: "play.fill")
                        }
                        .buttonStyle(.bordered)
                        .disabled(selectedDatasetURL == nil)
                    }
                    
                    Spacer()
                }
                .padding()
                .frame(minWidth: 300)
                
                // Training history
                VStack(alignment: .leading, spacing: 0) {
                    HStack {
                        Text("Training History")
                            .font(.headline)
                        Spacer()
                        Text("\(trainingJobs.count) jobs")
                            .foregroundStyle(.secondary)
                            .font(.caption)
                    }
                    .padding()
                    
                    Divider()
                    
                    if trainingJobs.isEmpty {
                        VStack(spacing: 16) {
                            Image(systemName: "graduationcap")
                                .font(.system(size: 60))
                                .foregroundStyle(.secondary)
                            Text("No training jobs yet")
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else {
                        List(trainingJobs, selection: $selectedJob) { job in
                            TrainingJobRow(job: job)
                        }
                    }
                }
            }
        }
    }
    
    private func selectDataset() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        
        if panel.runModal() == .OK {
            selectedDatasetURL = panel.url
        }
    }
    
    private func startTraining() {
        guard let datasetURL = selectedDatasetURL else { return }
        
        isTraining = true
        trainingProgress = 0.0
        
        let job = TrainingJob(
            id: UUID().uuidString,
            modelName: modelName,
            status: "training",
            progress: 0.0,
            startTime: Date(),
            endTime: nil,
            accuracy: nil
        )
        trainingJobs.insert(job, at: 0)
        
        Task {
            // Simulate training progress
            // In real implementation, call LlamaFarm training API
            for i in 1...epochs {
                try? await Task.sleep(for: .seconds(2))
                await MainActor.run {
                    trainingProgress = Double(i) / Double(epochs)
                    if let index = trainingJobs.firstIndex(where: { $0.id == job.id }) {
                        trainingJobs[index].progress = trainingProgress
                    }
                }
            }
            
            await MainActor.run {
                if let index = trainingJobs.firstIndex(where: { $0.id == job.id }) {
                    trainingJobs[index].status = "completed"
                    trainingJobs[index].endTime = Date()
                    trainingJobs[index].accuracy = 0.87 + Double.random(in: 0...0.1)
                }
                isTraining = false
                trainingProgress = 0.0
            }
        }
    }
}

struct TrainingJob: Identifiable, Hashable {
    let id: String
    var modelName: String
    var status: String
    var progress: Double
    var startTime: Date
    var endTime: Date?
    var accuracy: Double?
}

struct TrainingJobRow: View {
    let job: TrainingJob
    
    var body: some View {
        HStack {
            Image(systemName: statusIcon)
                .foregroundColor(statusColor)
            
            VStack(alignment: .leading) {
                Text(job.modelName)
                    .fontWeight(.medium)
                
                HStack(spacing: 8) {
                    Text(job.status)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    
                    if job.status == "training" {
                        Text("\(Int(job.progress * 100))%")
                            .font(.caption)
                            .foregroundStyle(.blue)
                    }
                    
                    if let accuracy = job.accuracy {
                        Text("• \(Int(accuracy * 100))% acc")
                            .font(.caption)
                            .foregroundStyle(.green)
                    }
                }
            }
            
            Spacer()
            
            if job.status == "training" {
                ProgressView(value: job.progress)
                    .frame(width: 60)
            } else {
                Text(job.startTime, style: .relative)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
    
    var statusIcon: String {
        switch job.status {
        case "training": return "arrow.triangle.2.circlepath"
        case "completed": return "checkmark.circle.fill"
        case "failed": return "xmark.circle.fill"
        default: return "circle"
        }
    }
    
    var statusColor: Color {
        switch job.status {
        case "training": return .blue
        case "completed": return .green
        case "failed": return .red
        default: return .gray
        }
    }
}

// MARK: - Model Catalog Detail View
struct ModelCatalogDetailView: View {
    @EnvironmentObject var catalog: ModelCatalogService
    @State private var selectedModel: ModelCapability?
    @State private var showPushDialog = false
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                VStack(alignment: .leading) {
                    Text("Model Catalog")
                        .font(.title)
                        .fontWeight(.bold)
                    Text("Manage and distribute models across the mesh")
                        .foregroundStyle(.secondary)
                }
                
                Spacer()
                
                HStack(spacing: 12) {
                    if let lastSync = catalog.lastSync {
                        Text("Updated \(timeAgo(lastSync))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    
                    Button {
                        Task { await catalog.syncNow() }
                    } label: {
                        Label("Sync", systemImage: "arrow.triangle.2.circlepath")
                    }
                    .buttonStyle(.bordered)
                }
            }
            .padding()
            .background(Color(.windowBackgroundColor))
            
            Divider()
            
            HSplitView {
                // Model list
                VStack(alignment: .leading, spacing: 0) {
                    HStack {
                        Text("\(catalog.localModels.count) Local • \(catalog.meshModels.count) Mesh")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Spacer()
                    }
                    .padding()
                    
                    Divider()
                    
                    List(catalog.allModels, selection: $selectedModel) { model in
                        ModelCatalogRow(model: model, isLocal: catalog.localModels.contains(model))
                    }
                }
                .frame(minWidth: 350)
                
                // Model details
                if let model = selectedModel {
                    ModelDetailPane(model: model, onPushToMesh: {
                        showPushDialog = true
                    })
                } else {
                    VStack {
                        Image(systemName: "cube.box")
                            .font(.system(size: 60))
                            .foregroundStyle(.secondary)
                        Text("Select a model to view details")
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
        }
        .sheet(isPresented: $showPushDialog) {
            if let model = selectedModel {
                PushModelSheet(model: model, onPush: { nodeId in
                    // TODO: Implement push
                })
            }
        }
    }
    
    func timeAgo(_ date: Date) -> String {
        let seconds = Int(Date().timeIntervalSince(date))
        if seconds < 60 { return "\(seconds)s ago" }
        let minutes = seconds / 60
        if minutes < 60 { return "\(minutes)m ago" }
        let hours = minutes / 60
        return "\(hours)h ago"
    }
}

struct ModelCatalogRow: View {
    let model: ModelCapability
    let isLocal: Bool
    
    var body: some View {
        HStack {
            Image(systemName: isLocal ? "internaldrive" : "cloud")
                .foregroundColor(isLocal ? .green : .blue)
            
            VStack(alignment: .leading) {
                Text(model.name)
                    .fontWeight(.medium)
                Text(model.task)
                    .font(.caption)
                    .foregroundStyle(.secondary)
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

struct ModelDetailPane: View {
    let model: ModelCapability
    let onPushToMesh: () -> Void
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    VStack(alignment: .leading) {
                        Text(model.name)
                            .font(.title2)
                            .fontWeight(.bold)
                        Text(model.id)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    
                    Spacer()
                    
                    if model.loaded {
                        Label("Loaded", systemImage: "checkmark.circle.fill")
                            .foregroundColor(.green)
                    }
                }
                
                Divider()
                
                LabeledContent("Task") {
                    Text(model.task)
                }
                
                LabeledContent("Device") {
                    Text(model.device ?? "CPU")
                }
                
                if let sizeMb = model.sizeMb {
                    LabeledContent("Size") {
                        Text("\(Int(sizeMb)) MB")
                    }
                }
                
                LabeledContent("Node") {
                    Text(model.nodeId.prefix(8) + "...")
                        .font(.system(.body, design: .monospaced))
                }
                
                Divider()
                
                Button {
                    onPushToMesh()
                } label: {
                    Label("Push to Mesh", systemImage: "arrow.up.circle")
                }
                .buttonStyle(.borderedProminent)
                
                Spacer()
            }
            .padding()
        }
    }
}

struct PushModelSheet: View {
    let model: ModelCapability
    let onPush: (String) -> Void
    @Environment(\.dismiss) var dismiss
    @EnvironmentObject var meshManager: BLEMeshManager
    
    var body: some View {
        VStack(spacing: 16) {
            Text("Push \(model.name) to Mesh")
                .font(.headline)
            
            Text("Select destination nodes:")
            
            List(meshManager.peers) { peer in
                HStack {
                    Text(peer.name)
                    Spacer()
                    Button("Push") {
                        onPush(peer.id)
                        dismiss()
                    }
                }
            }
            
            Button("Cancel") {
                dismiss()
            }
            .buttonStyle(.bordered)
        }
        .padding()
        .frame(width: 400, height: 300)
    }
}
