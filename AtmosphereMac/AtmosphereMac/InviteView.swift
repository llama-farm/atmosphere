//
//  InviteView.swift
//  AtmosphereMac
//
//  Create and display invite tokens for mesh pairing
//

import SwiftUI

struct InviteView: View {
    @EnvironmentObject var atmosphereClient: AtmosphereAPIClient
    
    @State private var generatedToken: AtmosphereTokenResponse?
    @State private var isGenerating: Bool = false
    @State private var ttlHours: Int = 24
    @State private var errorMessage: String?
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                VStack(alignment: .leading) {
                    Text("Mesh Invites")
                        .font(.title)
                        .fontWeight(.bold)
                    Text("Generate invite tokens for new nodes to join the mesh")
                        .foregroundStyle(.secondary)
                }
                
                Spacer()
            }
            .padding()
            .background(Color(.windowBackgroundColor))
            
            Divider()
            
            ScrollView {
                VStack(spacing: 24) {
                    // Token configuration
                    GroupBox {
                        VStack(alignment: .leading, spacing: 16) {
                            Text("Generate New Token")
                                .font(.headline)
                            
                            HStack {
                                Text("Token Lifetime:")
                                Stepper("\(ttlHours) hours", value: $ttlHours, in: 1...168)
                            }
                            
                            Button {
                                generateToken()
                            } label: {
                                Label("Generate Invite Token", systemImage: "key")
                            }
                            .buttonStyle(.borderedProminent)
                            .disabled(isGenerating || !atmosphereClient.isConnected)
                            
                            if isGenerating {
                                ProgressView()
                                    .controlSize(.small)
                            }
                            
                            if let error = errorMessage {
                                Text(error)
                                    .foregroundColor(.red)
                                    .font(.caption)
                            }
                        }
                    }
                    
                    // Generated token display
                    if let token = generatedToken {
                        GroupBox {
                            VStack(alignment: .leading, spacing: 16) {
                                HStack {
                                    Text("Generated Token")
                                        .font(.headline)
                                    Spacer()
                                    if let expiresAt = token.expiresAt {
                                        Text("Expires: \(expiresAt)")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                                
                                // Token string
                                VStack(alignment: .leading, spacing: 8) {
                                    Text("Token:")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    
                                    HStack {
                                        Text(token.token)
                                            .font(.system(.body, design: .monospaced))
                                            .textSelection(.enabled)
                                            .lineLimit(1)
                                            .truncationMode(.middle)
                                            .frame(maxWidth: .infinity, alignment: .leading)
                                        
                                        Button {
                                            copyToClipboard(token.token)
                                        } label: {
                                            Image(systemName: "doc.on.doc")
                                        }
                                        .buttonStyle(.bordered)
                                        .help("Copy token")
                                    }
                                    .padding(8)
                                    .background(Color(.controlBackgroundColor))
                                    .cornerRadius(6)
                                }
                                
                                // Invite URL (if available)
                                if let inviteUrl = token.inviteUrl {
                                    VStack(alignment: .leading, spacing: 8) {
                                        Text("Invite URL:")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                        
                                        HStack {
                                            Text(inviteUrl)
                                                .font(.system(.body, design: .monospaced))
                                                .textSelection(.enabled)
                                                .lineLimit(1)
                                                .truncationMode(.middle)
                                                .frame(maxWidth: .infinity, alignment: .leading)
                                            
                                            Button {
                                                copyToClipboard(inviteUrl)
                                            } label: {
                                                Image(systemName: "doc.on.doc")
                                            }
                                            .buttonStyle(.bordered)
                                            .help("Copy URL")
                                        }
                                        .padding(8)
                                        .background(Color(.controlBackgroundColor))
                                        .cornerRadius(6)
                                    }
                                }
                                
                                // QR code placeholder
                                VStack {
                                    Text("QR Code")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    
                                    ZStack {
                                        Rectangle()
                                            .fill(Color.white)
                                            .frame(width: 200, height: 200)
                                        
                                        VStack {
                                            Image(systemName: "qrcode")
                                                .font(.system(size: 60))
                                                .foregroundStyle(.gray)
                                            Text("QR code generation\ncoming soon")
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                                .multilineTextAlignment(.center)
                                        }
                                    }
                                    .cornerRadius(8)
                                }
                                
                                Divider()
                                
                                // Usage instructions
                                VStack(alignment: .leading, spacing: 8) {
                                    Text("📱 On Android/iOS:")
                                        .fontWeight(.medium)
                                    Text("1. Open Atmosphere app")
                                        .font(.callout)
                                    Text("2. Go to Settings → Join Mesh")
                                        .font(.callout)
                                    Text("3. Paste the token or scan the QR code")
                                        .font(.callout)
                                }
                                .padding()
                                .background(Color(.controlBackgroundColor).opacity(0.5))
                                .cornerRadius(8)
                            }
                        }
                    }
                    
                    // Endpoint info
                    GroupBox {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Connection Endpoints")
                                .font(.headline)
                            
                            if let meshStatus = atmosphereClient.meshStatus {
                                LabeledContent("Node ID") {
                                    Text(meshStatus.nodeId.prefix(12) + "...")
                                        .font(.system(.caption, design: .monospaced))
                                        .textSelection(.enabled)
                                }
                                
                                LabeledContent("Node Name") {
                                    Text(meshStatus.nodeName)
                                }
                            }
                            
                            LabeledContent("Local") {
                                Text("mdns://\(getHostname()).local")
                                    .font(.caption)
                                    .textSelection(.enabled)
                            }
                            
                            LabeledContent("Relay") {
                                Text("Available if relay connected")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                .padding()
            }
        }
    }
    
    private func generateToken() {
        isGenerating = true
        errorMessage = nil
        
        Task {
            do {
                let ttlSeconds = ttlHours * 3600
                let token = try await atmosphereClient.createInviteToken(ttlSeconds: ttlSeconds)
                
                await MainActor.run {
                    generatedToken = token
                    isGenerating = false
                }
                
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isGenerating = false
                }
            }
        }
    }
    
    private func copyToClipboard(_ text: String) {
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(text, forType: .string)
    }
    
    private func getHostname() -> String {
        ProcessInfo.processInfo.hostName
    }
}

#Preview {
    InviteView()
        .environmentObject(AtmosphereAPIClient())
}
