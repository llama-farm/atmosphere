# Atmosphere Client SDK Design

> Universal API for any app to tap into the Atmosphere mesh

## Philosophy

**One line to connect. One line to use.**

```python
mesh = Atmosphere()
result = mesh.route("summarize this", document)
```

No mesh configuration. No capability discovery. No cost optimization code.
The SDK handles everything.

---

## API Surface (All Platforms)

### Core Methods

```
connect()           → AtmosphereClient
route(intent, payload) → RouteResult  
chat(messages, model?) → ChatResponse | Stream
capabilities()      → List<Capability>
status()            → MeshStatus
```

### Event Subscription

```
on(event, callback)     → Unsubscribe
onCapability(id, callback) → Unsubscribe
```

### Advanced

```
execute(capabilityId, params) → ExecuteResult
nodes()                       → List<Node>
costs()                       → CostMetrics
```

---

## Platform Implementations

### Python (`pip install atmosphere-client`)

```python
from atmosphere import Atmosphere

# Connect (auto-discovers local daemon)
mesh = Atmosphere()

# Or explicit URL
mesh = Atmosphere(url="http://192.168.1.100:11451")

# Route an intent
result = mesh.route("summarize this document", pdf_bytes)
print(result.response)

# Chat (OpenAI-compatible)
response = mesh.chat([
    {"role": "user", "content": "Hello!"}
])
print(response.choices[0].message.content)

# Streaming
for chunk in mesh.chat(messages, stream=True):
    print(chunk.delta, end="")

# Get capabilities
caps = mesh.capabilities()
for cap in caps:
    print(f"{cap.name} ({cap.type}) - cost: {cap.cost}")

# Subscribe to events
def on_motion(event):
    print(f"Motion detected: {event}")

mesh.on("motion_detected", on_motion)
```

### JavaScript/TypeScript (`npm install @atmosphere/client`)

```typescript
import { Atmosphere } from '@atmosphere/client';

// Connect
const mesh = new Atmosphere();

// Route
const result = await mesh.route("summarize this", document);

// Chat
const response = await mesh.chat([
  { role: "user", content: "Hello!" }
]);

// Streaming
for await (const chunk of mesh.chat(messages, { stream: true })) {
  process.stdout.write(chunk.delta);
}

// Events
mesh.on("motion_detected", (event) => {
  console.log("Motion:", event);
});
```

### Kotlin/Android (`implementation 'com.llamafarm:atmosphere-sdk:1.0.0'`)

```kotlin
// Connect (uses AIDL on Android, HTTP elsewhere)
val mesh = Atmosphere.connect(context)

// Route
val result = mesh.route("summarize this", payload)

// Chat
val response = mesh.chat(listOf(
    ChatMessage(role = "user", content = "Hello!")
))

// Streaming
mesh.chat(messages, stream = true).collect { chunk ->
    print(chunk.delta)
}

// Capabilities
mesh.capabilities().forEach { cap ->
    println("${cap.name} (${cap.type}) - cost: ${cap.cost}")
}

// Events
mesh.onCapability("motion_detected") { event ->
    Log.d("Mesh", "Motion: $event")
}
```

### Swift/iOS (`https://github.com/llamafarm/atmosphere-swift`)

```swift
import Atmosphere

// Connect
let mesh = Atmosphere()

// Route
let result = try await mesh.route("summarize this", payload: document)

// Chat
let response = try await mesh.chat([
    .user("Hello!")
])

// Streaming
for try await chunk in mesh.chat(messages, stream: true) {
    print(chunk.delta, terminator: "")
}

// Events
mesh.on("motion_detected") { event in
    print("Motion: \(event)")
}
```

### Go (`go get github.com/llamafarm/atmosphere-go`)

```go
package main

import "github.com/llamafarm/atmosphere-go"

func main() {
    mesh := atmosphere.Connect()
    
    result, _ := mesh.Route("summarize this", document)
    fmt.Println(result.Response)
    
    // Chat
    response, _ := mesh.Chat([]atmosphere.Message{
        {Role: "user", Content: "Hello!"},
    })
    
    // Events
    mesh.On("motion_detected", func(event atmosphere.Event) {
        fmt.Printf("Motion: %v\n", event)
    })
}
```

### Rust (`cargo add atmosphere-client`)

```rust
use atmosphere::Atmosphere;

#[tokio::main]
async fn main() {
    let mesh = Atmosphere::connect().await?;
    
    let result = mesh.route("summarize this", &document).await?;
    println!("{}", result.response);
    
    // Chat
    let response = mesh.chat(&[
        Message::user("Hello!")
    ]).await?;
    
    // Events
    mesh.on("motion_detected", |event| {
        println!("Motion: {:?}", event);
    });
}
```

---

## Connection Discovery

SDKs try these in order:

1. **AIDL** (Android only) - Bind to `com.llamafarm.atmosphere.BIND`
2. **localhost:11451** - Local daemon
3. **Environment** - `ATMOSPHERE_URL` env var
4. **Config file** - `~/.atmosphere/config.json`
5. **mDNS/Bonjour** - Discover on local network

```python
# Auto-discovery (default)
mesh = Atmosphere()

# Explicit local
mesh = Atmosphere(url="http://localhost:11451")

# Remote mesh
mesh = Atmosphere(url="https://mesh.example.com", token="...")

# Specific node
mesh = Atmosphere(node="rob-macbook")
```

---

## Transport Layer

```
┌─────────────────────────────────────────────────────┐
│                  SDK Public API                      │
├─────────────────────────────────────────────────────┤
│              Transport Abstraction                   │
├──────────┬──────────┬──────────┬───────────────────┤
│   AIDL   │   HTTP   │WebSocket │   gRPC (future)   │
│ (Android)│  (REST)  │ (events) │                   │
└──────────┴──────────┴──────────┴───────────────────┘
```

- **AIDL**: Android inter-process, lowest latency, auto-reconnect
- **HTTP**: Universal, works everywhere, stateless
- **WebSocket**: For event subscriptions, maintained connection
- **gRPC**: Future optimization for high-throughput scenarios

---

## Error Handling

```python
from atmosphere import Atmosphere, AtmosphereError, NoMeshError, RoutingError

try:
    mesh = Atmosphere()
    result = mesh.route("...", payload)
except NoMeshError:
    print("Atmosphere not running")
except RoutingError as e:
    print(f"No capability for intent: {e}")
except AtmosphereError as e:
    print(f"Mesh error: {e}")
```

---

## Package Structure

```
atmosphere-client/
├── python/
│   ├── atmosphere/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── transport/
│   │   │   ├── http.py
│   │   │   └── websocket.py
│   │   └── models.py
│   ├── pyproject.toml
│   └── README.md
├── node/
│   ├── src/
│   │   ├── index.ts
│   │   ├── client.ts
│   │   └── transport.ts
│   ├── package.json
│   └── README.md
├── kotlin/
│   ├── atmosphere-sdk/
│   │   ├── src/main/kotlin/
│   │   │   ├── Atmosphere.kt
│   │   │   ├── ServiceConnector.kt
│   │   │   └── transport/
│   │   └── build.gradle.kts
│   └── README.md
├── swift/
│   ├── Sources/Atmosphere/
│   │   ├── Atmosphere.swift
│   │   └── Transport.swift
│   ├── Package.swift
│   └── README.md
└── README.md
```

---

## Version Strategy

All SDKs share the same version number tied to API version:

- `1.0.x` - Initial release (route, chat, capabilities)
- `1.1.x` - Events/subscriptions
- `1.2.x` - Advanced routing options
- `2.0.x` - Breaking API changes (if ever)

---

## Priority Order

1. **Python** - Primary dev language, fastest iteration
2. **Kotlin/Android** - AIDL integration critical
3. **TypeScript/Node** - Web/Electron apps
4. **Swift/iOS** - Mobile parity
5. **Go** - CLI tools, servers
6. **Rust** - Performance-critical integrations
