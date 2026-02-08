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
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(meshManager)
                .environmentObject(relayManager)
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width: 900, height: 700)
        
        Settings {
            SettingsView()
                .environmentObject(meshManager)
                .environmentObject(relayManager)
        }
        
        MenuBarExtra("Atmosphere", systemImage: "antenna.radiowaves.left.and.right") {
            MenuBarView()
                .environmentObject(meshManager)
                .environmentObject(relayManager)
        }
        .menuBarExtraStyle(.window)
    }
}
