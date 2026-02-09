//
//  AtmosphereMacApp.swift
//  AtmosphereMac
//
//  The central hub for Atmosphere mesh network on macOS.
//

import SwiftUI

@main
struct AtmosphereMacApp: App {
    @StateObject private var meshManager = BLEMeshManager()
    @StateObject private var relayManager = RelayManager()
    @StateObject private var llamaFarmBridge = LlamaFarmBridge()
    @StateObject private var escalationHandler: VisionEscalationHandler
    @StateObject private var modelCatalog: ModelCatalogService
    @StateObject private var atmosphereClient = AtmosphereAPIClient()
    @StateObject private var llamaFarmClient = LlamaFarmAPIClient()
    
    init() {
        // Initialize dependent services
        let bridge = LlamaFarmBridge()
        let mesh = BLEMeshManager()
        let relay = RelayManager()
        
        _llamaFarmBridge = StateObject(wrappedValue: bridge)
        _meshManager = StateObject(wrappedValue: mesh)
        _relayManager = StateObject(wrappedValue: relay)
        _escalationHandler = StateObject(wrappedValue: VisionEscalationHandler(
            bridge: bridge,
            meshManager: mesh,
            relayManager: relay
        ))
        _modelCatalog = StateObject(wrappedValue: ModelCatalogService(
            bridge: bridge,
            meshManager: mesh,
            relayManager: relay
        ))
    }
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(meshManager)
                .environmentObject(relayManager)
                .environmentObject(llamaFarmBridge)
                .environmentObject(escalationHandler)
                .environmentObject(modelCatalog)
                .environmentObject(atmosphereClient)
                .environmentObject(llamaFarmClient)
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width: 900, height: 700)
        
        Settings {
            SettingsView()
                .environmentObject(meshManager)
                .environmentObject(relayManager)
                .environmentObject(atmosphereClient)
                .environmentObject(llamaFarmClient)
        }
        
        MenuBarExtra("Atmosphere", systemImage: "antenna.radiowaves.left.and.right") {
            MenuBarView()
                .environmentObject(meshManager)
                .environmentObject(relayManager)
                .environmentObject(atmosphereClient)
                .environmentObject(llamaFarmClient)
        }
        .menuBarExtraStyle(.window)
    }
}
