//
//  ContentView.swift
//  AtmosphereMac
//
//  Main view for Atmosphere control center.
//

import SwiftUI

struct ContentView: View {
    @EnvironmentObject var meshManager: BLEMeshManager
    @EnvironmentObject var relayManager: RelayManager
    
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
                
                Section("Monitoring") {
                    Label("Network Map", systemImage: "network")
                        .tag(2)
                    Label("Messages", systemImage: "message")
                        .tag(3)
                    Label("Logs", systemImage: "doc.text")
                        .tag(4)
                }
                
                Section("Settings") {
                    Label("Node Identity", systemImage: "person.circle")
                        .tag(5)
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
                    NetworkMapView()
                case 3:
                    MessagesView()
                case 4:
                    LogsView()
                case 5:
                    NodeIdentityView()
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
                
                Divider()
                
                // Peer count
                Label("\(meshManager.peers.count + relayManager.connectedNodes.count)", systemImage: "person.2")
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
                        let angle = Double(index) * (2 * .pi / max(Double(meshManager.peers.count), 1))
                        let radius: CGFloat = 150
                        let x = geometry.size.width / 2 + radius * cos(angle)
                        let y = geometry.size.height / 2 + radius * sin(angle)
                        
                        VStack {
                            Image(systemName: "candybarphone")
                                .font(.system(size: 30))
                                .foregroundColor(peer.isConnected ? .green : .gray)
                            Text(peer.name)
                                .font(.caption2)
                        }
                        .position(x: x, y: y)
                    }
                    
                    // Relay nodes further out
                    ForEach(Array(relayManager.connectedNodes.enumerated()), id: \.element.id) { index, node in
                        let angle = Double(index) * (2 * .pi / max(Double(relayManager.connectedNodes.count), 1)) + .pi / 4
                        let radius: CGFloat = 250
                        let x = geometry.size.width / 2 + radius * cos(angle)
                        let y = geometry.size.height / 2 + radius * sin(angle)
                        
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
            }
        }
        .padding()
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
                .onChange(of: allLogs.count) { _, newCount in
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

// MARK: - Preview
#Preview {
    ContentView()
        .environmentObject(BLEMeshManager())
        .environmentObject(RelayManager())
}
