# Offline Mesh Networking Research

**Research Date:** 2026-02-03  
**Purpose:** Enable Atmosphere mesh communication when WiFi and internet are completely down.

---

## TL;DR

**Recommended approach: Hybrid transport layer**

1. **WiFi Aware** (primary offline) — 100+ Mbps, cross-platform by iOS 19
2. **BLE Mesh** (universal fallback) — Works everywhere, ~1 Mbps
3. **WebSocket** (when internet available) — Existing infrastructure

**Key discovery:** The EU DMA is forcing Apple to adopt WiFi Aware in iOS 19, enabling true cross-platform P2P WiFi for the first time. This changes everything.

---

## Documents

| Document | Description |
|----------|-------------|
| [OFFLINE_MESH_RESEARCH.md](./OFFLINE_MESH_RESEARCH.md) | Comprehensive technology comparison and recommendations |
| [BLE_MESH_DESIGN.md](./BLE_MESH_DESIGN.md) | Protocol design for Atmosphere over BLE |
| [WIFI_DIRECT_DESIGN.md](./WIFI_DIRECT_DESIGN.md) | WiFi Direct & WiFi Aware implementation designs |
| [MATTER_INTEGRATION.md](./MATTER_INTEGRATION.md) | Thread/Matter research and potential integration |
| [POC_BLE_DISCOVERY.md](./POC_BLE_DISCOVERY.md) | Proof of concept: BLE node discovery for Android |

---

## Quick Comparison

| Technology | Throughput | Range | Power | Cross-Platform | Mesh |
|------------|------------|-------|-------|----------------|------|
| WiFi Aware | 100+ Mbps | 100m | Medium | ⏳ (iOS 19) | Partial |
| BLE Mesh | ~1 Mbps | 30m/hop | Low | ✅ | True |
| WiFi Direct | 250 Mbps | 200m | High | Android only | No |
| Thread | 250 Kbps | 30m/hop | Very Low | Hardware only | True |

---

## Implementation Priority

### Phase 1: Foundation (Now)
- [ ] Transport abstraction layer
- [ ] BLE Mesh for Android
- [ ] Basic peer discovery

### Phase 2: WiFi Transports (Next)
- [ ] WiFi Aware for Android
- [ ] MultipeerConnectivity bridge for iOS
- [ ] Hybrid BLE → WiFi discovery

### Phase 3: iOS Parity (iOS 19 Release)
- [ ] WiFi Aware for iOS (when available)
- [ ] Cross-platform testing

### Phase 4: Advanced (Future)
- [ ] Thread bridge hardware (optional)
- [ ] Matter integration (monitoring)

---

## Key Insights

### 1. WiFi Aware is the Future
Apple's forced adoption of WiFi Aware via EU DMA means true cross-platform P2P WiFi is coming. Build for this future.

### 2. BLE Mesh is Universal
Every modern phone has BLE. It's slower but works everywhere. Essential fallback.

### 3. Thread Requires Hardware
Thread/Matter is interesting but requires dedicated radios. Not viable for phone-to-phone without bridges.

### 4. Hybrid Discovery is Optimal
Use BLE for low-power discovery, then negotiate WiFi Aware connections for data. This is how AirDrop works.

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                   Atmosphere Transport Layer                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   selectBestTransport(peer, requirements) → Transport           │
│                                                                  │
│   ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐      │
│   │ WebSocket │ │WiFi Aware │ │ BLE Mesh  │ │WiFi Direct│      │
│   │ (primary) │ │ (offline) │ │(fallback) │ │ (legacy)  │      │
│   └───────────┘ └───────────┘ └───────────┘ └───────────┘      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Next Steps

1. **Review documents** in this folder
2. **Build POC** from [POC_BLE_DISCOVERY.md](./POC_BLE_DISCOVERY.md)
3. **Test on devices** (need 2+ Android phones)
4. **Iterate on design** based on real-world results

---

## References

- [Nordic nRF Mesh Library](https://github.com/NordicSemiconductor/Android-nRF-Mesh-Library)
- [BE-Mesh Android BLE](https://github.com/netlab-sapienza/android-ble-mesh)
- [WiFi Aware Android](https://developer.android.com/develop/connectivity/wifi/wifi-aware)
- [Ditto P2P WiFi Article](https://www.ditto.com/blog/cross-platform-p2p-wi-fi-how-the-eu-killed-awdl) (EU DMA + WiFi Aware)
- [Thread Protocol](https://www.threadgroup.org/)
- [Apple MultipeerConnectivity](https://developer.apple.com/documentation/multipeerconnectivity)
