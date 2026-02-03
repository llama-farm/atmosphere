# Matter/Thread Integration Research for Atmosphere

**Purpose:** Explore whether Atmosphere can leverage Matter/Thread for offline mesh networking, particularly by using existing smart home infrastructure.

---

## Executive Summary

**Short answer:** Direct Matter/Thread integration is possible but complex. However, there's a pragmatic opportunity: **use Thread Border Routers (TBRs) as bridge points** between Atmosphere nodes.

**Key insight:** Many homes already have Thread Border Routers (Apple HomePod, Google Nest Hub, Amazon Echo). These could potentially relay Atmosphere traffic when the main internet is down.

---

## Background

### What is Thread?

Thread is an IPv6-based mesh networking protocol using IEEE 802.15.4 radio (the same physical layer as Zigbee, but incompatible at the protocol level).

**Key characteristics:**
- True mesh topology (self-healing, no single point of failure)
- Very low power (ideal for battery devices)
- IPv6 native (easy to route to/from IP networks)
- Supports ~250 nodes per network
- ~250 Kbps throughput

### What is Matter?

Matter is a smart home interoperability standard that can run over:
- WiFi (high bandwidth devices)
- Thread (low power devices)
- Ethernet

Matter handles device discovery, commissioning, and control. It's the "application layer" while Thread is one possible "network layer."

### Thread Border Router (TBR)

A Thread Border Router bridges Thread mesh to IP networks:

```
Internet ← WiFi/Ethernet ← TBR → Thread Mesh → Thread Devices
                            ↑
                    (Apple HomePod, Google Nest Hub, etc.)
```

---

## The Opportunity

### Existing Infrastructure

Many homes already have Thread Border Routers:
- **Apple:** HomePod (2nd gen), HomePod mini, Apple TV 4K
- **Google:** Nest Hub (2nd gen), Nest Hub Max, Nest Wifi Pro
- **Amazon:** Echo (4th gen)
- **Others:** Nanoleaf, Eve, etc.

These devices:
1. Have Thread radios
2. Are always-on (plugged in)
3. Bridge Thread ↔ IP
4. Could potentially relay Atmosphere traffic

### Hypothetical Use Case

```
┌──────────────────────────────────────────────────────────────────────┐
│                        INTERNET DOWN                                  │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  Phone A                                                   Phone B    │
│  (WiFi)                                                    (WiFi)     │
│     │                                                         │       │
│     │ Local WiFi still works                                  │       │
│     │ (router on, no internet)                                │       │
│     ↓                                                         ↓       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                     Local Network (WiFi)                        │ │
│  └───────────┬───────────────────────────────────────┬─────────────┘ │
│              │                                       │               │
│              ↓                                       ↓               │
│       HomePod (TBR)                           Nest Hub (TBR)        │
│              │                                       │               │
│              └───────────┬───────────────────────────┘               │
│                          │ Thread Mesh                               │
│                          ↓                                           │
│                   Thread Devices                                     │
│              (lights, sensors, etc.)                                 │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

Even without internet, local WiFi often still works. Thread Border Routers on that network can relay traffic.

---

## Integration Approaches

### Approach 1: Use TBRs as Relay Points (Easiest)

**Concept:** Atmosphere nodes discover TBRs on the local network and use them as message relays when direct WiFi communication is blocked.

**Implementation:**
1. Discover TBRs via mDNS/DNS-SD (they advertise `_meshcop._udp`)
2. Connect to TBR's Thread management interface
3. Route Atmosphere messages through Thread mesh

**Challenges:**
- TBRs don't expose arbitrary data forwarding APIs
- Would need to use Matter's data model (limited)
- Security/authentication concerns

**Verdict:** Difficult without cooperation from TBR vendors.

---

### Approach 2: Custom Thread Device (Medium Effort)

**Concept:** Build a dedicated Atmosphere Thread device that joins the Thread mesh and bridges Atmosphere traffic.

**Hardware options:**
- Nordic nRF52840 (~$5 chip, has Thread radio)
- Silicon Labs EFR32 (~$5 chip)
- ESP32-H2 (~$3, has Thread radio)

**Architecture:**
```
Phone ←──WiFi──→ Atmosphere Bridge ←──Thread──→ Thread Mesh
                  (ESP32-H2)
```

**Implementation:**
1. Flash ESP32-H2 with OpenThread + Atmosphere firmware
2. Device advertises Atmosphere service on Thread
3. Phone discovers bridge via mDNS
4. Messages route: Phone → WiFi → Bridge → Thread → Other Bridges → WiFi → Other Phones

**Pros:**
- Full control over protocol
- Can carry arbitrary data
- Low cost hardware

**Cons:**
- Requires custom hardware
- Users must deploy bridges
- More complex setup

**Code sketch (ESP-IDF):**
```c
// Atmosphere Thread Bridge - ESP32-H2
#include "openthread/thread.h"
#include "openthread/udp.h"

#define ATMOSPHERE_PORT 11454

static otUdpSocket atmosphereSocket;

void atmosphere_init(otInstance *instance) {
    // Open UDP socket on Thread mesh
    otUdpOpen(instance, &atmosphereSocket, handle_atmosphere_message, NULL);
    
    otSockAddr bindAddr;
    memset(&bindAddr, 0, sizeof(bindAddr));
    bindAddr.mPort = ATMOSPHERE_PORT;
    
    otUdpBind(instance, &atmosphereSocket, &bindAddr, OT_NETIF_THREAD);
}

void handle_atmosphere_message(void *context, otMessage *message, 
                                const otMessageInfo *messageInfo) {
    // Received message from Thread mesh
    uint16_t length = otMessageGetLength(message);
    uint8_t *buffer = malloc(length);
    otMessageRead(message, 0, buffer, length);
    
    // Forward to WiFi side
    wifi_forward_message(buffer, length, &messageInfo->mPeerAddr);
    free(buffer);
}

void send_to_thread_mesh(const uint8_t *data, uint16_t length, 
                          const otIp6Address *dest) {
    otMessage *message = otUdpNewMessage(instance, NULL);
    otMessageAppend(message, data, length);
    
    otMessageInfo messageInfo;
    memset(&messageInfo, 0, sizeof(messageInfo));
    messageInfo.mPeerAddr = *dest;
    messageInfo.mPeerPort = ATMOSPHERE_PORT;
    
    otUdpSend(instance, &atmosphereSocket, message, &messageInfo);
}
```

---

### Approach 3: Matter Application (Hard)

**Concept:** Register Atmosphere as a Matter device/bridge, using Matter's device model to carry messages.

**Matter Device Types:**
- Most are for specific functions (lights, thermostats, etc.)
- No generic "message relay" device type
- Could potentially abuse "Generic Switch" or custom clusters

**Custom Matter Cluster:**
```
Cluster: AtmosphereMesh (Vendor-specific: 0xFC00)
  Attributes:
    - NodeId (string)
    - MeshId (string)  
    - Capabilities (list)
  Commands:
    - SendMessage(destination: string, payload: bytes)
    - Subscribe(filter: string)
  Events:
    - MessageReceived(source: string, payload: bytes)
```

**Implementation via Matter SDK:**
```cpp
// Using Connectedhomeip (Matter SDK)
#include <app/clusters/custom/AtmosphereMeshCluster.h>

class AtmosphereMeshServer : public chip::app::Clusters::AtmosphereMesh::Server {
public:
    CHIP_ERROR HandleSendMessage(const chip::ByteSpan& destination,
                                  const chip::ByteSpan& payload) override {
        // Route message through Atmosphere network
        atmosphere_route_message(destination.data(), destination.size(),
                                  payload.data(), payload.size());
        return CHIP_NO_ERROR;
    }
};
```

**Challenges:**
- Complex Matter SDK integration
- Custom clusters may not work with all controllers
- Certification required for commercial use

**Verdict:** High effort, limited benefit over simpler approaches.

---

### Approach 4: Thread Credentials Sharing (Research)

**Concept:** Obtain Thread network credentials and have Atmosphere nodes join directly.

**Background:**
- Thread networks have credentials (Network Key, PAN ID, etc.)
- Apple/Google/Samsung can share credentials between their TBRs
- No standard way to share with third-party apps

**iOS Thread Credentials API:**
```swift
import ThreadNetwork

// Request Thread credentials (iOS 15+)
THClient().retrieveAllCredentials { credentials, error in
    for cred in credentials ?? [] {
        print("Network: \(cred.networkName)")
        print("Extended PAN ID: \(cred.extendedPANID)")
        // Note: Network Key is NOT exposed for security
    }
}
```

**The Problem:**
- Apple/Google expose Thread network **info** but not the **Network Key**
- Can't join Thread network without the key
- Would need user to manually enter credentials from router

**Verdict:** Not viable without vendor cooperation.

---

## Recommended Approach

Given the constraints, I recommend a **pragmatic hybrid strategy**:

### Phase 1: WiFi + BLE First
Don't depend on Thread/Matter initially. Build robust:
- WiFi Aware for high-bandwidth offline
- BLE Mesh for universal fallback

### Phase 2: Thread Bridge Hardware (Optional)
For advanced users who want maximum mesh coverage:
- Develop ESP32-H2 based Atmosphere Bridge
- Open-source hardware + firmware
- Bridges WiFi ↔ Thread for Atmosphere messages
- Users can deploy in strategic locations (basement, garage, etc.)

### Phase 3: Monitor Matter Development
The Matter ecosystem is evolving rapidly. Watch for:
- Matter 2.0+ features
- Thread credential sharing improvements
- Generic data relay device types
- APIs in iOS/Android for Thread access

---

## Thread Bridge Hardware Design

If pursuing the custom bridge approach:

### Bill of Materials

| Component | Cost | Notes |
|-----------|------|-------|
| ESP32-H2 | ~$3 | Thread + BLE radio |
| USB-C connector | ~$0.50 | Power |
| PCB | ~$1 | Simple 2-layer |
| Enclosure | ~$2 | 3D printed |
| **Total** | **~$7** | Per unit |

### Firmware Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Atmosphere Thread Bridge                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────┐          ┌────────────────┐                 │
│  │  WiFi Module   │          │ Thread Module  │                 │
│  │                │          │                │                 │
│  │ • mDNS advert  │          │ • OpenThread   │                 │
│  │ • TCP/UDP      │◄────────►│ • Mesh routing │                 │
│  │ • WebSocket    │  Bridge  │ • CoAP         │                 │
│  │                │  Logic   │                │                 │
│  └────────────────┘          └────────────────┘                 │
│           ↑                           ↑                          │
│           │                           │                          │
│           ▼                           ▼                          │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              Atmosphere Protocol Handler                     ││
│  │                                                              ││
│  │  • Message serialization/deserialization                    ││
│  │  • Routing decisions (WiFi vs Thread)                       ││
│  │  • Encryption (mesh key)                                    ││
│  │  • Peer discovery                                           ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Discovery

Bridge advertises on both networks:

**WiFi (mDNS):**
```
_atmosphere._tcp.local.
  TXT: meshId=xxx, nodeId=yyy, type=bridge
```

**Thread (DNS-SD over Thread):**
```
_atmosphere._udp.default.service.arpa.
  TXT: meshId=xxx, nodeId=yyy, type=bridge
```

### Message Routing

```python
def route_message(message: AtmosphereMessage, source: str) -> None:
    """Route message between WiFi and Thread."""
    
    if source == "wifi":
        # Message came from WiFi side
        # Check if destination is on Thread mesh
        if destination_on_thread(message.destination):
            send_via_thread(message)
        else:
            # Maybe other bridge will handle it
            flood_via_thread(message)
    
    elif source == "thread":
        # Message came from Thread mesh
        # Check if destination is on WiFi
        if destination_on_wifi(message.destination):
            send_via_wifi(message)
        else:
            # Forward to WiFi for other nodes
            broadcast_via_wifi(message)
```

---

## Existing Matter Code Review

The task mentioned checking `~/clawd/projects/atmosphere/atmosphere/matter/` — this directory doesn't exist, indicating Matter integration hasn't been started.

**Recommendation:** Don't create Matter code yet. Focus on:
1. Core transport abstraction
2. BLE Mesh implementation
3. WiFi Aware implementation

Matter/Thread can be added later as an optional "mesh extender" for users with compatible hardware.

---

## Summary

| Approach | Effort | Benefit | Recommendation |
|----------|--------|---------|----------------|
| Use existing TBRs | Low | Low (APIs limited) | ❌ Not viable |
| Custom Thread bridge | Medium | High (full control) | ✅ Phase 2 |
| Matter application | High | Medium | ❌ Too complex |
| Thread credentials | N/A | N/A | ❌ Not possible |

**Bottom line:** Thread/Matter is interesting for future mesh expansion but shouldn't be the primary offline strategy. BLE Mesh + WiFi Aware provide better immediate value with less complexity.

---

## References

1. [Thread Protocol Specification](https://www.threadgroup.org/support#specifications)
2. [OpenThread Documentation](https://openthread.io/guides)
3. [Matter SDK (connectedhomeip)](https://github.com/project-chip/connectedhomeip)
4. [ESP32-H2 Thread Support](https://docs.espressif.com/projects/esp-idf/en/latest/esp32h2/api-guides/thread.html)
5. [Home Assistant Thread Integration](https://www.home-assistant.io/integrations/thread/)
6. [Apple Thread Credentials API](https://developer.apple.com/documentation/threadnetwork)

---

## Next Steps

1. **Defer Matter integration** to Phase 2/3
2. **Focus on BLE + WiFi Aware** for immediate offline support
3. **Create hardware design** for ESP32-H2 bridge (optional future work)
4. **Monitor** Matter ecosystem for better APIs
