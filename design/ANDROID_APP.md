# Android App Design

**Mobile Nodes in the Mesh — Phones Are Everywhere**

---

## Overview

Android phones represent the largest potential node pool for the Atmosphere mesh:
- **3+ billion** active Android devices worldwide
- Always-on sensors: camera, microphone, GPS, accelerometer
- Persistent connectivity: WiFi, cellular, Bluetooth
- Significant compute: modern phones have 8-core CPUs, NPUs, and 6-12GB RAM

The Android app turns every phone into a mesh node that can:
- **Provide capabilities**: camera, location, audio, on-device inference
- **Consume capabilities**: route intents to powerful nodes in the mesh
- **Relay traffic**: act as a bridge between nodes

**Critical constraint:** We must share the core protocol implementation with Python. No protocol divergence. Ever.

---

## Code Sharing Strategy

### Option Analysis

| Approach | Pros | Cons | Recommendation |
|----------|------|------|----------------|
| **Rust core + JNI** | Fast, single codebase, strong types, PyO3 for Python | Complex build, JNI boilerplate | ✅ **Recommended** |
| **Python + Chaquopy** | Easy port, same code | 50MB+ APK, 3-5s startup, battery drain | ❌ Too heavy |
| **Kotlin rewrite** | Native Android feel, easy UI | Protocol divergence, double maintenance | ❌ Never |
| **Go + gomobile** | Good FFI, single binary | Weaker ecosystem, no Python bindings | ❌ |
| **C++ core** | Fast, portable | Manual memory management, no PyO3 | ❌ |

### Why Rust?

1. **Single source of truth**: Core protocol in Rust, bindings for everything
2. **PyO3**: Excellent Python bindings (replaces Python implementation over time)
3. **JNI via jni-rs**: Mature Android support
4. **Safety**: No segfaults, no data races
5. **Performance**: Near-C speed, crucial for mobile battery life
6. **Async**: Tokio runtime works on Android

---

## Rust Core Architecture

The shared Rust library contains ALL protocol logic. Platform code is just UI and OS bindings.

```
atmosphere-core/                    # Shared Rust library
├── Cargo.toml
├── src/
│   ├── lib.rs                     # Library entry point
│   │
│   ├── types/                     # Core data types
│   │   ├── mod.rs
│   │   ├── capability.rs          # CapabilityInfo, Capability
│   │   ├── announcement.rs        # Announcement, ResourceInfo
│   │   ├── gradient.rs            # GradientEntry
│   │   └── message.rs             # Protocol messages
│   │
│   ├── protocol/                  # Protocol implementation
│   │   ├── mod.rs
│   │   ├── gossip.rs              # Gossip protocol (port from Python)
│   │   ├── gradient_table.rs      # Gradient table (port from Python)
│   │   ├── router.rs              # Semantic routing
│   │   └── cost.rs                # Cost model (battery, data, etc.)
│   │
│   ├── embedding/                 # Embedding support
│   │   ├── mod.rs
│   │   ├── engine.rs              # Embedding engine abstraction
│   │   └── onnx.rs                # ONNX Runtime integration
│   │
│   ├── transport/                 # Network abstraction
│   │   ├── mod.rs
│   │   ├── websocket.rs           # WebSocket client
│   │   └── quic.rs                # QUIC transport (future)
│   │
│   ├── node/                      # Node management
│   │   ├── mod.rs
│   │   ├── local.rs               # Local node state
│   │   └── mesh.rs                # Mesh connection manager
│   │
│   └── ffi/                       # Foreign function interfaces
│       ├── mod.rs
│       ├── android.rs             # JNI bindings
│       ├── python.rs              # PyO3 bindings
│       └── c.rs                   # C bindings (for iOS/other)
│
├── build.rs                       # Build script
├── Cargo.toml
└── cbindgen.toml                  # C header generation
```

### Core Types (Rust)

```rust
// src/types/capability.rs

use serde::{Deserialize, Serialize};

/// Capability information for announcements.
/// Direct port from Python's CapabilityInfo dataclass.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CapabilityInfo {
    pub id: String,
    pub label: String,
    pub description: String,
    #[serde(with = "vector_serde")]
    pub vector: Vec<f32>,  // 384-dim embedding
    pub local: bool,
    pub hops: u8,
    pub via: Option<String>,
    pub models: Vec<String>,
    pub constraints: serde_json::Value,
    pub estimated_latency_ms: f32,
}

/// Local capability with handler reference.
#[derive(Debug, Clone)]
pub struct Capability {
    pub id: String,
    pub label: String,
    pub description: String,
    pub vector: Vec<f32>,
    pub handler: String,
    pub models: Vec<String>,
    pub constraints: CapabilityConstraints,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CapabilityConstraints {
    pub requires_gpu: bool,
    pub max_input_size: Option<usize>,
    pub supported_formats: Vec<String>,
}
```

```rust
// src/types/announcement.rs

use serde::{Deserialize, Serialize};
use std::time::{SystemTime, UNIX_EPOCH};
use uuid::Uuid;

use super::capability::CapabilityInfo;

pub const MAX_TTL: u8 = 10;
pub const MAX_CAPABILITIES_PER_ANNOUNCE: usize = 50;

/// Resource information for load balancing.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResourceInfo {
    pub cpu_available: f32,       // 0.0 - 1.0
    pub memory_available_mb: u32,
    pub gpu_available: f32,       // 0.0 - 1.0
    pub battery_percent: Option<u8>,
    pub charging: Option<bool>,
    pub network_type: Option<NetworkType>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum NetworkType {
    Wifi,
    Cellular,
    Ethernet,
    Offline,
}

/// A capability announcement message.
/// Direct port from Python's Announcement dataclass.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Announcement {
    #[serde(rename = "type")]
    pub msg_type: String,
    #[serde(rename = "from")]
    pub from_node: String,
    pub capabilities: Vec<CapabilityInfo>,
    pub resources: Option<ResourceInfo>,
    pub timestamp: f64,
    pub ttl: u8,
    pub nonce: String,
}

impl Announcement {
    pub fn new(from_node: String, capabilities: Vec<CapabilityInfo>) -> Self {
        Self {
            msg_type: "announce".to_string(),
            from_node,
            capabilities,
            resources: None,
            timestamp: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_secs_f64(),
            ttl: MAX_TTL,
            nonce: Uuid::new_v4().to_string()[..16].to_string(),
        }
    }
    
    pub fn decrement_ttl(&mut self) {
        if self.ttl > 0 {
            self.ttl -= 1;
        }
    }
}
```

```rust
// src/types/gradient.rs

use std::time::{SystemTime, UNIX_EPOCH};

/// A single entry in the gradient table.
/// Direct port from Python's GradientEntry dataclass.
#[derive(Debug, Clone)]
pub struct GradientEntry {
    pub capability_id: String,
    pub capability_label: String,
    pub capability_vector: Vec<f32>,
    pub hops: u8,
    pub next_hop: String,
    pub via_node: String,
    pub estimated_latency_ms: f32,
    pub last_updated: f64,
    pub confidence: f32,
}

impl GradientEntry {
    pub fn new(
        capability_id: String,
        capability_label: String,
        capability_vector: Vec<f32>,
        hops: u8,
        next_hop: String,
        via_node: String,
        estimated_latency_ms: f32,
    ) -> Self {
        Self {
            capability_id,
            capability_label,
            capability_vector,
            hops,
            next_hop,
            via_node,
            estimated_latency_ms,
            last_updated: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_secs_f64(),
            confidence: 0.95_f32.powi(hops as i32),
        }
    }
    
    pub fn is_expired(&self, expire_sec: f64) -> bool {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs_f64();
        (now - self.last_updated) > expire_sec
    }
}
```

### Gradient Table (Rust)

```rust
// src/protocol/gradient_table.rs

use std::collections::HashMap;
use std::sync::RwLock;

use crate::types::gradient::GradientEntry;

const GRADIENT_EXPIRE_SEC: f64 = 300.0;  // 5 minutes
const MAX_GRADIENT_TABLE_SIZE: usize = 1000;
const LINK_LATENCY_MS: f32 = 10.0;

/// Gradient table for semantic routing.
/// Thread-safe via RwLock.
pub struct GradientTable {
    node_id: String,
    max_size: usize,
    expire_sec: f64,
    entries: RwLock<HashMap<String, GradientEntry>>,
    index_dirty: RwLock<bool>,
}

impl GradientTable {
    pub fn new(node_id: String) -> Self {
        Self {
            node_id,
            max_size: MAX_GRADIENT_TABLE_SIZE,
            expire_sec: GRADIENT_EXPIRE_SEC,
            entries: RwLock::new(HashMap::new()),
            index_dirty: RwLock::new(true),
        }
    }
    
    /// Update gradient table with new routing info.
    /// Only updates if entry doesn't exist or new route has fewer hops.
    pub fn update(
        &self,
        capability_id: String,
        capability_label: String,
        capability_vector: Vec<f32>,
        hops: u8,
        next_hop: String,
        via_node: String,
        estimated_latency_ms: Option<f32>,
    ) -> bool {
        let latency = estimated_latency_ms
            .unwrap_or(hops as f32 * LINK_LATENCY_MS);
        
        let mut entries = self.entries.write().unwrap();
        
        // Check if better route exists
        if let Some(existing) = entries.get(&capability_id) {
            if hops >= existing.hops {
                return false;
            }
        }
        
        // Evict if at capacity
        if entries.len() >= self.max_size && !entries.contains_key(&capability_id) {
            self.evict_one(&mut entries);
        }
        
        // Insert new entry
        entries.insert(
            capability_id.clone(),
            GradientEntry::new(
                capability_id,
                capability_label,
                capability_vector,
                hops,
                next_hop,
                via_node,
                latency,
            ),
        );
        
        *self.index_dirty.write().unwrap() = true;
        true
    }
    
    /// Find the best route for an intent using cosine similarity.
    pub fn find_best_route(
        &self,
        intent_vector: &[f32],
        min_score: f32,
    ) -> Option<GradientEntry> {
        let entries = self.entries.read().unwrap();
        
        if entries.is_empty() {
            return None;
        }
        
        let mut best_entry: Option<&GradientEntry> = None;
        let mut best_score: f32 = min_score;
        
        for entry in entries.values() {
            if entry.is_expired(self.expire_sec) {
                continue;
            }
            
            let similarity = cosine_similarity(intent_vector, &entry.capability_vector);
            let adjusted = similarity * entry.confidence;
            
            if adjusted > best_score {
                best_score = adjusted;
                best_entry = Some(entry);
            }
        }
        
        best_entry.cloned()
    }
    
    fn evict_one(&self, entries: &mut HashMap<String, GradientEntry>) {
        // Find lowest confidence/oldest entry
        let worst_id = entries
            .iter()
            .min_by(|a, b| {
                let score_a = a.1.confidence / (1.0 + (self.expire_sec - a.1.last_updated) / 60.0) as f32;
                let score_b = b.1.confidence / (1.0 + (self.expire_sec - b.1.last_updated) / 60.0) as f32;
                score_a.partial_cmp(&score_b).unwrap()
            })
            .map(|(id, _)| id.clone());
        
        if let Some(id) = worst_id {
            entries.remove(&id);
        }
    }
    
    /// Prune expired entries.
    pub fn prune_expired(&self) -> usize {
        let mut entries = self.entries.write().unwrap();
        let before = entries.len();
        entries.retain(|_, e| !e.is_expired(self.expire_sec));
        *self.index_dirty.write().unwrap() = true;
        before - entries.len()
    }
    
    pub fn len(&self) -> usize {
        self.entries.read().unwrap().len()
    }
}

/// Compute cosine similarity between two vectors.
fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    let dot: f32 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
    let norm_a: f32 = a.iter().map(|x| x * x).sum::<f32>().sqrt();
    let norm_b: f32 = b.iter().map(|x| x * x).sum::<f32>().sqrt();
    
    if norm_a == 0.0 || norm_b == 0.0 {
        0.0
    } else {
        dot / (norm_a * norm_b)
    }
}
```

### Gossip Protocol (Rust)

```rust
// src/protocol/gossip.rs

use std::collections::{HashMap, HashSet};
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use tokio::sync::RwLock;
use tokio::time::interval;

use crate::protocol::gradient_table::GradientTable;
use crate::types::announcement::{Announcement, ResourceInfo, MAX_CAPABILITIES_PER_ANNOUNCE};
use crate::types::capability::CapabilityInfo;

const ANNOUNCE_INTERVAL_SEC: u64 = 30;
const NONCE_CACHE_SEC: f64 = 300.0;

/// Callback for broadcasting messages to peers.
pub type BroadcastFn = Arc<dyn Fn(&[u8]) + Send + Sync>;

/// Gossip protocol for capability propagation.
pub struct GossipProtocol {
    node_id: String,
    gradient_table: Arc<GradientTable>,
    local_capabilities: RwLock<Vec<CapabilityInfo>>,
    broadcast_fn: RwLock<Option<BroadcastFn>>,
    nonce_cache: RwLock<HashMap<String, f64>>,
    known_nodes: RwLock<HashMap<String, f64>>,
    running: RwLock<bool>,
    
    // Metrics
    announcements_sent: RwLock<u64>,
    announcements_received: RwLock<u64>,
    announcements_forwarded: RwLock<u64>,
}

impl GossipProtocol {
    pub fn new(
        node_id: String,
        gradient_table: Arc<GradientTable>,
        local_capabilities: Vec<CapabilityInfo>,
    ) -> Self {
        Self {
            node_id,
            gradient_table,
            local_capabilities: RwLock::new(local_capabilities),
            broadcast_fn: RwLock::new(None),
            nonce_cache: RwLock::new(HashMap::new()),
            known_nodes: RwLock::new(HashMap::new()),
            running: RwLock::new(false),
            announcements_sent: RwLock::new(0),
            announcements_received: RwLock::new(0),
            announcements_forwarded: RwLock::new(0),
        }
    }
    
    pub fn set_broadcast_fn(&self, f: BroadcastFn) {
        *self.broadcast_fn.blocking_write() = Some(f);
    }
    
    /// Build an announcement from local capabilities.
    pub async fn build_announcement(&self) -> Announcement {
        let local_caps = self.local_capabilities.read().await;
        let capabilities: Vec<CapabilityInfo> = local_caps
            .iter()
            .take(MAX_CAPABILITIES_PER_ANNOUNCE)
            .cloned()
            .collect();
        
        let mut announcement = Announcement::new(
            self.node_id.clone(),
            capabilities,
        );
        
        // Add resource info (platform-specific)
        announcement.resources = Some(ResourceInfo {
            cpu_available: 0.8,
            memory_available_mb: 2048,
            gpu_available: 0.0,
            battery_percent: None,
            charging: None,
            network_type: None,
        });
        
        announcement
    }
    
    /// Broadcast announcement to all peers.
    pub async fn announce(&self) -> Result<(), String> {
        let broadcast_fn = self.broadcast_fn.read().await;
        let Some(ref f) = *broadcast_fn else {
            return Err("No broadcast function set".to_string());
        };
        
        let announcement = self.build_announcement().await;
        let data = serde_json::to_vec(&announcement)
            .map_err(|e| e.to_string())?;
        
        f(&data);
        *self.announcements_sent.write().await += 1;
        
        Ok(())
    }
    
    /// Handle incoming announcement from peer.
    pub async fn handle_announcement(
        &self,
        data: &[u8],
        from_peer: &str,
    ) -> Result<(), String> {
        let announcement: Announcement = serde_json::from_slice(data)
            .map_err(|e| e.to_string())?;
        
        // Check nonce for replay protection
        if !self.check_nonce(&announcement.nonce, announcement.timestamp).await {
            return Ok(());  // Duplicate, ignore
        }
        
        *self.announcements_received.write().await += 1;
        
        // Track known node
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs_f64();
        self.known_nodes.write().await.insert(
            announcement.from_node.clone(),
            now,
        );
        
        // Update gradient table
        for cap in &announcement.capabilities {
            let new_hops = if cap.local { 1 } else { cap.hops + 1 };
            
            self.gradient_table.update(
                cap.id.clone(),
                cap.label.clone(),
                cap.vector.clone(),
                new_hops,
                from_peer.to_string(),
                cap.via.clone().unwrap_or(announcement.from_node.clone()),
                Some(cap.estimated_latency_ms + 10.0),
            );
        }
        
        Ok(())
    }
    
    async fn check_nonce(&self, nonce: &str, timestamp: f64) -> bool {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs_f64();
        
        // Reject old timestamps
        if (now - timestamp).abs() > NONCE_CACHE_SEC {
            return false;
        }
        
        let mut cache = self.nonce_cache.write().await;
        
        // Prune old nonces
        cache.retain(|_, t| now - *t < NONCE_CACHE_SEC);
        
        // Check for duplicate
        if cache.contains_key(nonce) {
            return false;
        }
        
        cache.insert(nonce.to_string(), timestamp);
        true
    }
    
    /// Start periodic announcement loop.
    pub async fn start(&self) {
        *self.running.write().await = true;
        
        let mut ticker = interval(Duration::from_secs(ANNOUNCE_INTERVAL_SEC));
        
        while *self.running.read().await {
            ticker.tick().await;
            let _ = self.announce().await;
        }
    }
    
    pub async fn stop(&self) {
        *self.running.write().await = false;
    }
    
    pub async fn known_nodes(&self) -> HashSet<String> {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs_f64();
        
        self.known_nodes
            .read()
            .await
            .iter()
            .filter(|(_, t)| now - **t < NONCE_CACHE_SEC)
            .map(|(id, _)| id.clone())
            .collect()
    }
}
```

### JNI Bindings (Rust → Android)

```rust
// src/ffi/android.rs

use jni::JNIEnv;
use jni::objects::{JClass, JObject, JString, JByteArray};
use jni::sys::{jlong, jboolean, jint, jfloat};
use std::sync::Arc;

use crate::node::AtmosphereNode;
use crate::types::capability::CapabilityInfo;

/// Opaque pointer to Rust node.
#[no_mangle]
pub extern "system" fn Java_com_llamafarm_atmosphere_NativeCore_createNode(
    mut env: JNIEnv,
    _class: JClass,
    node_id: JString,
) -> jlong {
    let node_id: String = env.get_string(&node_id)
        .expect("Invalid node_id string")
        .into();
    
    let node = Box::new(AtmosphereNode::new(node_id));
    Box::into_raw(node) as jlong
}

#[no_mangle]
pub extern "system" fn Java_com_llamafarm_atmosphere_NativeCore_destroyNode(
    _env: JNIEnv,
    _class: JClass,
    ptr: jlong,
) {
    if ptr != 0 {
        unsafe {
            let _ = Box::from_raw(ptr as *mut AtmosphereNode);
        }
    }
}

#[no_mangle]
pub extern "system" fn Java_com_llamafarm_atmosphere_NativeCore_registerCapability(
    mut env: JNIEnv,
    _class: JClass,
    ptr: jlong,
    label: JString,
    description: JString,
    vector: JByteArray,
) -> jboolean {
    let node = unsafe { &mut *(ptr as *mut AtmosphereNode) };
    
    let label: String = env.get_string(&label).unwrap().into();
    let description: String = env.get_string(&description).unwrap().into();
    
    // Convert byte array to f32 vector
    let vector_bytes = env.convert_byte_array(&vector).unwrap();
    let vector: Vec<f32> = vector_bytes
        .chunks_exact(4)
        .map(|b| f32::from_le_bytes([b[0], b[1], b[2], b[3]]))
        .collect();
    
    let cap = CapabilityInfo {
        id: format!("{}:{}", node.node_id(), &label),
        label,
        description,
        vector,
        local: true,
        hops: 0,
        via: None,
        models: vec![],
        constraints: serde_json::Value::Null,
        estimated_latency_ms: 0.0,
    };
    
    node.register_capability(cap);
    1  // true
}

#[no_mangle]
pub extern "system" fn Java_com_llamafarm_atmosphere_NativeCore_handleAnnouncement(
    mut env: JNIEnv,
    _class: JClass,
    ptr: jlong,
    data: JByteArray,
    from_peer: JString,
) -> jboolean {
    let node = unsafe { &mut *(ptr as *mut AtmosphereNode) };
    
    let data = env.convert_byte_array(&data).unwrap();
    let from_peer: String = env.get_string(&from_peer).unwrap().into();
    
    match node.handle_announcement_sync(&data, &from_peer) {
        Ok(_) => 1,
        Err(_) => 0,
    }
}

#[no_mangle]
pub extern "system" fn Java_com_llamafarm_atmosphere_NativeCore_routeIntent(
    mut env: JNIEnv,
    _class: JClass,
    ptr: jlong,
    intent_vector: JByteArray,
) -> JObject {
    let node = unsafe { &*(ptr as *mut AtmosphereNode) };
    
    let vector_bytes = env.convert_byte_array(&intent_vector).unwrap();
    let vector: Vec<f32> = vector_bytes
        .chunks_exact(4)
        .map(|b| f32::from_le_bytes([b[0], b[1], b[2], b[3]]))
        .collect();
    
    match node.find_best_route(&vector, 0.5) {
        Some(entry) => {
            // Create RouteResult Java object
            let class = env.find_class("com/llamafarm/atmosphere/RouteResult").unwrap();
            let obj = env.alloc_object(&class).unwrap();
            
            let capability_id = env.new_string(&entry.capability_id).unwrap();
            let next_hop = env.new_string(&entry.next_hop).unwrap();
            
            env.set_field(&obj, "capabilityId", "Ljava/lang/String;", (&capability_id).into()).unwrap();
            env.set_field(&obj, "nextHop", "Ljava/lang/String;", (&next_hop).into()).unwrap();
            env.set_field(&obj, "score", "F", (entry.confidence).into()).unwrap();
            env.set_field(&obj, "hops", "I", (entry.hops as i32).into()).unwrap();
            
            obj
        }
        None => JObject::null(),
    }
}

#[no_mangle]
pub extern "system" fn Java_com_llamafarm_atmosphere_NativeCore_getStats(
    mut env: JNIEnv,
    _class: JClass,
    ptr: jlong,
) -> JString {
    let node = unsafe { &*(ptr as *mut AtmosphereNode) };
    let stats = node.stats();
    let json = serde_json::to_string(&stats).unwrap_or_default();
    env.new_string(&json).unwrap()
}
```

### PyO3 Bindings (Rust → Python)

```rust
// src/ffi/python.rs

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::sync::Arc;

use crate::node::AtmosphereNode;
use crate::types::capability::CapabilityInfo;
use crate::protocol::gradient_table::GradientTable;

/// Python-compatible AtmosphereNode wrapper.
#[pyclass]
pub struct PyAtmosphereNode {
    inner: AtmosphereNode,
}

#[pymethods]
impl PyAtmosphereNode {
    #[new]
    fn new(node_id: String) -> Self {
        Self {
            inner: AtmosphereNode::new(node_id),
        }
    }
    
    fn register_capability(
        &mut self,
        label: String,
        description: String,
        vector: Vec<f32>,
    ) -> PyResult<()> {
        let cap = CapabilityInfo {
            id: format!("{}:{}", self.inner.node_id(), &label),
            label,
            description,
            vector,
            local: true,
            hops: 0,
            via: None,
            models: vec![],
            constraints: serde_json::Value::Null,
            estimated_latency_ms: 0.0,
        };
        self.inner.register_capability(cap);
        Ok(())
    }
    
    fn handle_announcement(&mut self, data: &[u8], from_peer: &str) -> PyResult<bool> {
        self.inner
            .handle_announcement_sync(data, from_peer)
            .map(|_| true)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e))
    }
    
    fn route_intent(&self, py: Python, vector: Vec<f32>) -> PyResult<Option<PyObject>> {
        match self.inner.find_best_route(&vector, 0.5) {
            Some(entry) => {
                let dict = PyDict::new(py);
                dict.set_item("capability_id", entry.capability_id)?;
                dict.set_item("next_hop", entry.next_hop)?;
                dict.set_item("hops", entry.hops)?;
                dict.set_item("score", entry.confidence)?;
                Ok(Some(dict.into()))
            }
            None => Ok(None),
        }
    }
    
    fn gradient_table_size(&self) -> usize {
        self.inner.gradient_table_len()
    }
}

/// Python module.
#[pymodule]
fn atmosphere_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<PyAtmosphereNode>()?;
    Ok(())
}
```

---

## Android Project Structure

```
atmosphere-android/
├── app/
│   ├── src/main/
│   │   ├── java/com/llamafarm/atmosphere/
│   │   │   ├── AtmosphereApp.kt           # Application class
│   │   │   ├── MainActivity.kt            # Main activity
│   │   │   │
│   │   │   ├── core/                      # Core wrappers
│   │   │   │   ├── NativeCore.kt          # JNI wrapper
│   │   │   │   ├── AtmosphereNode.kt      # Kotlin node wrapper
│   │   │   │   └── RouteResult.kt         # Routing result
│   │   │   │
│   │   │   ├── service/                   # Background service
│   │   │   │   ├── AtmosphereService.kt   # Foreground service
│   │   │   │   ├── MeshConnection.kt      # WebSocket management
│   │   │   │   └── ServiceBinder.kt       # IPC binder
│   │   │   │
│   │   │   ├── capabilities/              # Android capabilities
│   │   │   │   ├── CapabilityManager.kt   # Capability lifecycle
│   │   │   │   ├── CameraCapability.kt    # Camera provider
│   │   │   │   ├── LocationCapability.kt  # Location provider
│   │   │   │   ├── MicrophoneCapability.kt # Audio recording
│   │   │   │   └── InferenceCapability.kt # On-device ML
│   │   │   │
│   │   │   └── ui/                        # Jetpack Compose UI
│   │   │       ├── theme/
│   │   │       │   └── Theme.kt
│   │   │       ├── screens/
│   │   │       │   ├── JoinScreen.kt      # QR scan / token paste
│   │   │       │   ├── StatusScreen.kt    # Connection status
│   │   │       │   └── SettingsScreen.kt  # Capability toggles
│   │   │       └── components/
│   │   │           ├── NodeStatus.kt
│   │   │           └── CapabilityList.kt
│   │   │
│   │   ├── res/
│   │   │   ├── drawable/
│   │   │   ├── values/
│   │   │   └── xml/
│   │   │
│   │   ├── jniLibs/                       # Prebuilt .so files
│   │   │   ├── arm64-v8a/
│   │   │   │   └── libatmosphere_core.so
│   │   │   ├── armeabi-v7a/
│   │   │   │   └── libatmosphere_core.so
│   │   │   └── x86_64/
│   │   │       └── libatmosphere_core.so
│   │   │
│   │   └── AndroidManifest.xml
│   │
│   └── build.gradle.kts
│
├── core/                                   # Rust library (submodule)
│   └── -> ../atmosphere-core/
│
├── gradle/
├── build.gradle.kts
├── settings.gradle.kts
└── README.md
```

---

## Kotlin Wrappers

### JNI Bridge

```kotlin
// core/NativeCore.kt

package com.llamafarm.atmosphere.core

/**
 * JNI bridge to Rust atmosphere-core library.
 * 
 * All protocol logic lives in Rust. This is just the FFI boundary.
 */
object NativeCore {
    init {
        System.loadLibrary("atmosphere_core")
    }
    
    // Node lifecycle
    external fun createNode(nodeId: String): Long
    external fun destroyNode(ptr: Long)
    
    // Capability registration
    external fun registerCapability(
        ptr: Long,
        label: String,
        description: String,
        vector: ByteArray  // f32[] as bytes
    ): Boolean
    
    // Protocol handling
    external fun handleAnnouncement(
        ptr: Long,
        data: ByteArray,
        fromPeer: String
    ): Boolean
    
    // Routing
    external fun routeIntent(
        ptr: Long,
        intentVector: ByteArray
    ): RouteResult?
    
    // Introspection
    external fun getStats(ptr: Long): String  // JSON
}
```

```kotlin
// core/AtmosphereNode.kt

package com.llamafarm.atmosphere.core

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Kotlin wrapper for Rust AtmosphereNode.
 */
class AtmosphereNode(private val nodeId: String) : AutoCloseable {
    private var ptr: Long = NativeCore.createNode(nodeId)
    
    val isValid: Boolean get() = ptr != 0L
    
    /**
     * Register a local capability.
     * 
     * @param label Short name (e.g., "camera", "location")
     * @param description Full description for semantic matching
     * @param vector 384-dim embedding vector
     */
    fun registerCapability(
        label: String,
        description: String,
        vector: FloatArray
    ): Boolean {
        check(isValid) { "Node already destroyed" }
        return NativeCore.registerCapability(
            ptr,
            label,
            description,
            vector.toByteArray()
        )
    }
    
    /**
     * Handle incoming gossip announcement.
     */
    suspend fun handleAnnouncement(data: ByteArray, fromPeer: String): Boolean {
        check(isValid) { "Node already destroyed" }
        return withContext(Dispatchers.IO) {
            NativeCore.handleAnnouncement(ptr, data, fromPeer)
        }
    }
    
    /**
     * Route an intent to the best capability.
     */
    fun routeIntent(intentVector: FloatArray): RouteResult? {
        check(isValid) { "Node already destroyed" }
        return NativeCore.routeIntent(ptr, intentVector.toByteArray())
    }
    
    /**
     * Get node statistics as JSON.
     */
    fun getStats(): String {
        check(isValid) { "Node already destroyed" }
        return NativeCore.getStats(ptr)
    }
    
    override fun close() {
        if (ptr != 0L) {
            NativeCore.destroyNode(ptr)
            ptr = 0L
        }
    }
    
    private fun FloatArray.toByteArray(): ByteArray {
        val buffer = ByteBuffer.allocate(size * 4).order(ByteOrder.LITTLE_ENDIAN)
        forEach { buffer.putFloat(it) }
        return buffer.array()
    }
}
```

```kotlin
// core/RouteResult.kt

package com.llamafarm.atmosphere.core

/**
 * Result of routing an intent.
 * 
 * Created by JNI from Rust.
 */
data class RouteResult(
    val capabilityId: String,
    val nextHop: String,
    val score: Float,
    val hops: Int
) {
    val isLocal: Boolean get() = hops == 0
}
```

---

## Capabilities

### Camera Capability

```kotlin
// capabilities/CameraCapability.kt

package com.llamafarm.atmosphere.capabilities

import android.content.Context
import android.graphics.Bitmap
import android.graphics.ImageFormat
import android.hardware.camera2.*
import android.media.ImageReader
import android.os.Handler
import android.os.HandlerThread
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import java.io.ByteArrayOutputStream

/**
 * Camera capability - exposes phone cameras to the mesh.
 * 
 * Triggers:
 *   - photo_taken: When a photo is captured
 *   - qr_scanned: When a QR code is detected
 *   
 * Tools:
 *   - take_photo: Capture a still image
 *   - scan_qr: Scan for QR codes
 *   - start_video: Begin video capture
 */
class CameraCapability(
    private val context: Context,
    private val nodeId: String
) : Capability {
    
    override val label = "camera"
    override val description = """
        Mobile device camera. Can capture photos, scan QR codes, and record video.
        Available cameras: front-facing selfie camera, rear main camera.
        Supports: JPEG photos up to 12MP, QR/barcode scanning, H.264 video.
    """.trimIndent()
    
    private val cameraManager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
    private var cameraThread: HandlerThread? = null
    private var cameraHandler: Handler? = null
    
    // Triggers (events this capability can emit)
    sealed class CameraTrigger {
        data class PhotoTaken(val imageData: ByteArray, val cameraId: String) : CameraTrigger()
        data class QrScanned(val content: String) : CameraTrigger()
        data class VideoStarted(val sessionId: String) : CameraTrigger()
        data class VideoStopped(val sessionId: String, val durationMs: Long) : CameraTrigger()
    }
    
    private val triggerChannel = Channel<CameraTrigger>(Channel.BUFFERED)
    
    val triggers: Flow<CameraTrigger> = flow {
        for (trigger in triggerChannel) {
            emit(trigger)
        }
    }
    
    // Tools (operations agents can invoke)
    
    /**
     * Capture a photo from the specified camera.
     * 
     * @param facing "front" or "back"
     * @param quality JPEG quality 1-100
     * @return JPEG image data
     */
    suspend fun takePhoto(
        facing: CameraFacing = CameraFacing.BACK,
        quality: Int = 85
    ): Result<ByteArray> = runCatching {
        ensureInitialized()
        
        val cameraId = getCameraId(facing)
        val imageReader = ImageReader.newInstance(
            1920, 1080,
            ImageFormat.JPEG,
            1
        )
        
        // ... camera capture logic ...
        
        val image = imageReader.acquireLatestImage()
        val buffer = image.planes[0].buffer
        val data = ByteArray(buffer.remaining())
        buffer.get(data)
        image.close()
        
        // Emit trigger
        triggerChannel.send(CameraTrigger.PhotoTaken(data, cameraId))
        
        data
    }
    
    /**
     * Scan for QR codes using camera preview.
     * 
     * @param timeout Maximum time to scan
     * @return Decoded QR content or null if timeout
     */
    suspend fun scanQr(timeout: Long = 30_000): Result<String?> = runCatching {
        ensureInitialized()
        
        // Use ML Kit or ZXing for QR scanning
        // ... QR scan logic ...
        
        val content = "decoded_qr_content"  // placeholder
        
        if (content != null) {
            triggerChannel.send(CameraTrigger.QrScanned(content))
        }
        
        content
    }
    
    /**
     * Get list of available cameras.
     */
    fun listCameras(): List<CameraInfo> {
        return cameraManager.cameraIdList.map { id ->
            val characteristics = cameraManager.getCameraCharacteristics(id)
            val facing = when (characteristics.get(CameraCharacteristics.LENS_FACING)) {
                CameraCharacteristics.LENS_FACING_FRONT -> CameraFacing.FRONT
                CameraCharacteristics.LENS_FACING_BACK -> CameraFacing.BACK
                else -> CameraFacing.EXTERNAL
            }
            CameraInfo(id, facing)
        }
    }
    
    private fun ensureInitialized() {
        if (cameraThread == null) {
            cameraThread = HandlerThread("CameraThread").also { it.start() }
            cameraHandler = Handler(cameraThread!!.looper)
        }
    }
    
    private fun getCameraId(facing: CameraFacing): String {
        return cameraManager.cameraIdList.firstOrNull { id ->
            val characteristics = cameraManager.getCameraCharacteristics(id)
            val lensFacing = characteristics.get(CameraCharacteristics.LENS_FACING)
            when (facing) {
                CameraFacing.FRONT -> lensFacing == CameraCharacteristics.LENS_FACING_FRONT
                CameraFacing.BACK -> lensFacing == CameraCharacteristics.LENS_FACING_BACK
                CameraFacing.EXTERNAL -> lensFacing == CameraCharacteristics.LENS_FACING_EXTERNAL
            }
        } ?: throw IllegalStateException("No camera found for facing: $facing")
    }
    
    override fun destroy() {
        cameraThread?.quitSafely()
        cameraThread = null
        cameraHandler = null
        triggerChannel.close()
    }
}

enum class CameraFacing { FRONT, BACK, EXTERNAL }

data class CameraInfo(val id: String, val facing: CameraFacing)
```

### Location Capability

```kotlin
// capabilities/LocationCapability.kt

package com.llamafarm.atmosphere.capabilities

import android.Manifest
import android.content.Context
import android.location.Geocoder
import android.location.Location
import android.os.Looper
import androidx.annotation.RequiresPermission
import com.google.android.gms.location.*
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

/**
 * Location capability - exposes device location to the mesh.
 * 
 * Triggers:
 *   - location_changed: Significant location change
 *   - geofence_entered: Entered a defined geofence
 *   - geofence_exited: Exited a defined geofence
 *   
 * Tools:
 *   - get_location: Get current location
 *   - get_address: Reverse geocode location to address
 *   - add_geofence: Create a geofence trigger
 */
class LocationCapability(
    private val context: Context,
    private val nodeId: String
) : Capability {
    
    override val label = "location"
    override val description = """
        Mobile device location services. Provides GPS coordinates, 
        reverse geocoding, and geofence monitoring.
        Accuracy: up to 3m with GPS, 20m with network, 100m coarse.
    """.trimIndent()
    
    private val fusedClient = LocationServices.getFusedLocationProviderClient(context)
    private val geofencingClient = LocationServices.getGeofencingClient(context)
    private val geocoder = Geocoder(context)
    
    // Triggers
    sealed class LocationTrigger {
        data class LocationChanged(
            val latitude: Double,
            val longitude: Double,
            val accuracy: Float,
            val altitude: Double?
        ) : LocationTrigger()
        
        data class GeofenceEntered(val geofenceId: String) : LocationTrigger()
        data class GeofenceExited(val geofenceId: String) : LocationTrigger()
    }
    
    private val triggerChannel = Channel<LocationTrigger>(Channel.BUFFERED)
    
    val triggers: Flow<LocationTrigger> = flow {
        for (trigger in triggerChannel) {
            emit(trigger)
        }
    }
    
    // Tools
    
    /**
     * Get current device location.
     * 
     * @param priority Location priority (balanced, high accuracy, low power)
     * @return Current location or error
     */
    @RequiresPermission(anyOf = [
        Manifest.permission.ACCESS_FINE_LOCATION,
        Manifest.permission.ACCESS_COARSE_LOCATION
    ])
    suspend fun getLocation(
        priority: LocationPriority = LocationPriority.BALANCED
    ): Result<LocationData> = runCatching {
        suspendCancellableCoroutine { cont ->
            val request = CurrentLocationRequest.Builder()
                .setPriority(priority.toGmsPriority())
                .setMaxUpdateAgeMillis(10_000)
                .build()
            
            fusedClient.getCurrentLocation(request, null)
                .addOnSuccessListener { location ->
                    if (location != null) {
                        cont.resume(location.toLocationData())
                    } else {
                        cont.resume(LocationData(0.0, 0.0, 0f, null, null))
                    }
                }
                .addOnFailureListener { e ->
                    cont.cancel(e)
                }
        }
    }
    
    /**
     * Reverse geocode coordinates to an address.
     */
    suspend fun getAddress(latitude: Double, longitude: Double): Result<AddressData?> = runCatching {
        @Suppress("DEPRECATION")
        val addresses = geocoder.getFromLocation(latitude, longitude, 1)
        addresses?.firstOrNull()?.let { addr ->
            AddressData(
                street = addr.thoroughfare,
                city = addr.locality,
                state = addr.adminArea,
                country = addr.countryName,
                postalCode = addr.postalCode,
                formatted = addr.getAddressLine(0)
            )
        }
    }
    
    /**
     * Start continuous location updates.
     */
    @RequiresPermission(anyOf = [
        Manifest.permission.ACCESS_FINE_LOCATION,
        Manifest.permission.ACCESS_COARSE_LOCATION
    ])
    fun startLocationUpdates(
        intervalMs: Long = 60_000,
        minDistanceM: Float = 50f
    ) {
        val request = LocationRequest.Builder(intervalMs)
            .setMinUpdateDistanceMeters(minDistanceM)
            .setPriority(Priority.PRIORITY_BALANCED_POWER_ACCURACY)
            .build()
        
        fusedClient.requestLocationUpdates(
            request,
            locationCallback,
            Looper.getMainLooper()
        )
    }
    
    private val locationCallback = object : LocationCallback() {
        override fun onLocationResult(result: LocationResult) {
            result.lastLocation?.let { location ->
                triggerChannel.trySend(
                    LocationTrigger.LocationChanged(
                        latitude = location.latitude,
                        longitude = location.longitude,
                        accuracy = location.accuracy,
                        altitude = if (location.hasAltitude()) location.altitude else null
                    )
                )
            }
        }
    }
    
    override fun destroy() {
        fusedClient.removeLocationUpdates(locationCallback)
        triggerChannel.close()
    }
    
    private fun Location.toLocationData() = LocationData(
        latitude = latitude,
        longitude = longitude,
        accuracy = accuracy,
        altitude = if (hasAltitude()) altitude else null,
        bearing = if (hasBearing()) bearing else null
    )
    
    private fun LocationPriority.toGmsPriority() = when (this) {
        LocationPriority.HIGH_ACCURACY -> Priority.PRIORITY_HIGH_ACCURACY
        LocationPriority.BALANCED -> Priority.PRIORITY_BALANCED_POWER_ACCURACY
        LocationPriority.LOW_POWER -> Priority.PRIORITY_LOW_POWER
        LocationPriority.PASSIVE -> Priority.PRIORITY_PASSIVE
    }
}

enum class LocationPriority { HIGH_ACCURACY, BALANCED, LOW_POWER, PASSIVE }

data class LocationData(
    val latitude: Double,
    val longitude: Double,
    val accuracy: Float,
    val altitude: Double?,
    val bearing: Float?
)

data class AddressData(
    val street: String?,
    val city: String?,
    val state: String?,
    val country: String?,
    val postalCode: String?,
    val formatted: String?
)
```

### Microphone Capability

```kotlin
// capabilities/MicrophoneCapability.kt

package com.llamafarm.atmosphere.capabilities

import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Microphone capability - exposes audio recording to the mesh.
 * 
 * Triggers:
 *   - recording_complete: Audio recording finished
 *   - voice_detected: Voice activity detected
 *   
 * Tools:
 *   - start_recording: Begin audio capture
 *   - stop_recording: End and return audio
 *   - get_audio_level: Current input level
 */
class MicrophoneCapability(
    private val context: Context,
    private val nodeId: String
) : Capability {
    
    override val label = "microphone"
    override val description = """
        Mobile device microphone. Records audio for transcription, voice commands,
        or ambient sound analysis. Supports WAV and AAC formats.
        Sample rates: 8kHz, 16kHz, 44.1kHz, 48kHz.
    """.trimIndent()
    
    private var mediaRecorder: MediaRecorder? = null
    private var audioRecord: AudioRecord? = null
    private var isRecording = false
    private var currentFile: File? = null
    
    // Triggers
    sealed class MicrophoneTrigger {
        data class RecordingComplete(
            val filePath: String,
            val durationMs: Long,
            val format: AudioFormat
        ) : MicrophoneTrigger()
        
        data class VoiceDetected(val level: Float) : MicrophoneTrigger()
    }
    
    private val triggerChannel = Channel<MicrophoneTrigger>(Channel.BUFFERED)
    
    val triggers: Flow<MicrophoneTrigger> = flow {
        for (trigger in triggerChannel) {
            emit(trigger)
        }
    }
    
    // Tools
    
    /**
     * Start audio recording.
     * 
     * @param format Output format (WAV, AAC, etc.)
     * @param sampleRate Sample rate in Hz
     * @return Session ID for this recording
     */
    suspend fun startRecording(
        format: AudioOutputFormat = AudioOutputFormat.AAC,
        sampleRate: Int = 44100
    ): Result<String> = withContext(Dispatchers.IO) {
        runCatching {
            check(!isRecording) { "Already recording" }
            
            val sessionId = java.util.UUID.randomUUID().toString()
            val extension = when (format) {
                AudioOutputFormat.WAV -> "wav"
                AudioOutputFormat.AAC -> "m4a"
                AudioOutputFormat.OPUS -> "opus"
            }
            
            currentFile = File(context.cacheDir, "recording_$sessionId.$extension")
            
            mediaRecorder = MediaRecorder(context).apply {
                setAudioSource(MediaRecorder.AudioSource.MIC)
                setOutputFormat(format.toMediaFormat())
                setAudioEncoder(format.toAudioEncoder())
                setAudioSamplingRate(sampleRate)
                setOutputFile(currentFile!!.absolutePath)
                prepare()
                start()
            }
            
            isRecording = true
            sessionId
        }
    }
    
    /**
     * Stop recording and return the audio data.
     * 
     * @return Audio file path
     */
    suspend fun stopRecording(): Result<String> = withContext(Dispatchers.IO) {
        runCatching {
            check(isRecording) { "Not recording" }
            
            mediaRecorder?.apply {
                stop()
                release()
            }
            mediaRecorder = null
            isRecording = false
            
            val path = currentFile!!.absolutePath
            
            // Emit trigger
            triggerChannel.send(
                MicrophoneTrigger.RecordingComplete(
                    filePath = path,
                    durationMs = 0, // TODO: calculate
                    format = AudioFormat.Default
                )
            )
            
            path
        }
    }
    
    /**
     * Get current audio input level (0.0 - 1.0).
     */
    fun getAudioLevel(): Float {
        return mediaRecorder?.maxAmplitude?.let { amp ->
            (amp / 32767f).coerceIn(0f, 1f)
        } ?: 0f
    }
    
    override fun destroy() {
        mediaRecorder?.release()
        audioRecord?.release()
        triggerChannel.close()
    }
    
    private fun AudioOutputFormat.toMediaFormat() = when (this) {
        AudioOutputFormat.WAV -> MediaRecorder.OutputFormat.DEFAULT
        AudioOutputFormat.AAC -> MediaRecorder.OutputFormat.MPEG_4
        AudioOutputFormat.OPUS -> MediaRecorder.OutputFormat.OGG
    }
    
    private fun AudioOutputFormat.toAudioEncoder() = when (this) {
        AudioOutputFormat.WAV -> MediaRecorder.AudioEncoder.DEFAULT
        AudioOutputFormat.AAC -> MediaRecorder.AudioEncoder.AAC
        AudioOutputFormat.OPUS -> MediaRecorder.AudioEncoder.OPUS
    }
}

enum class AudioOutputFormat { WAV, AAC, OPUS }
```

### On-Device Inference Capability

```kotlin
// capabilities/InferenceCapability.kt

package com.llamafarm.atmosphere.capabilities

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/**
 * On-device inference capability using llama.cpp.
 * 
 * Supports small models only:
 *   - TinyLlama-1.1B
 *   - Phi-3-mini (3.8B quantized)
 *   - Gemma-2B
 *   
 * Triggers:
 *   - inference_complete: Model finished generating
 *   
 * Tools:
 *   - generate: Generate text from prompt
 *   - embed: Generate embeddings
 */
class InferenceCapability(
    private val context: Context,
    private val nodeId: String
) : Capability {
    
    override val label = "inference"
    override val description = """
        On-device language model inference using llama.cpp.
        Supports small models (1-4B parameters) quantized to 4-bit.
        Good for: simple chat, classification, embeddings, summarization of short texts.
        Not suitable for: long documents, complex reasoning, code generation.
    """.trimIndent()
    
    // Native llama.cpp bindings
    private external fun loadModel(modelPath: String, contextSize: Int): Long
    private external fun unloadModel(ptr: Long)
    private external fun generate(
        ptr: Long,
        prompt: String,
        maxTokens: Int,
        temperature: Float,
        topP: Float
    ): String
    private external fun embed(ptr: Long, text: String): FloatArray
    
    companion object {
        init {
            System.loadLibrary("llama")
        }
    }
    
    private var modelPtr: Long = 0
    private var loadedModel: String? = null
    
    // Available models (must be downloaded separately)
    enum class Model(val filename: String, val contextSize: Int) {
        TINYLLAMA("tinyllama-1.1b-q4_k_m.gguf", 2048),
        PHI3_MINI("phi-3-mini-4k-q4_k_m.gguf", 4096),
        GEMMA_2B("gemma-2b-q4_k_m.gguf", 2048)
    }
    
    /**
     * Load a model into memory.
     */
    suspend fun loadModel(model: Model): Result<Unit> = withContext(Dispatchers.IO) {
        runCatching {
            val modelFile = File(context.filesDir, "models/${model.filename}")
            check(modelFile.exists()) { "Model not found: ${model.filename}" }
            
            // Unload previous model
            if (modelPtr != 0L) {
                unloadModel(modelPtr)
            }
            
            modelPtr = loadModel(modelFile.absolutePath, model.contextSize)
            check(modelPtr != 0L) { "Failed to load model" }
            loadedModel = model.filename
        }
    }
    
    /**
     * Generate text from a prompt.
     * 
     * @param prompt Input prompt
     * @param maxTokens Maximum tokens to generate
     * @param temperature Sampling temperature (0.0 = deterministic)
     * @return Generated text
     */
    suspend fun generate(
        prompt: String,
        maxTokens: Int = 256,
        temperature: Float = 0.7f,
        topP: Float = 0.9f
    ): Result<String> = withContext(Dispatchers.IO) {
        runCatching {
            check(modelPtr != 0L) { "No model loaded" }
            generate(modelPtr, prompt, maxTokens, temperature, topP)
        }
    }
    
    /**
     * Generate embedding vector for text.
     */
    suspend fun embed(text: String): Result<FloatArray> = withContext(Dispatchers.IO) {
        runCatching {
            check(modelPtr != 0L) { "No model loaded" }
            embed(modelPtr, text)
        }
    }
    
    /**
     * Check if a model is downloaded.
     */
    fun isModelAvailable(model: Model): Boolean {
        return File(context.filesDir, "models/${model.filename}").exists()
    }
    
    /**
     * Get model download URL.
     */
    fun getModelUrl(model: Model): String {
        return "https://huggingface.co/llamafarm/atmosphere-models/resolve/main/${model.filename}"
    }
    
    override fun destroy() {
        if (modelPtr != 0L) {
            unloadModel(modelPtr)
            modelPtr = 0L
        }
    }
}
```

---

## Background Service

```kotlin
// service/AtmosphereService.kt

package com.llamafarm.atmosphere.service

import android.app.*
import android.content.Context
import android.content.Intent
import android.os.Binder
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import com.llamafarm.atmosphere.R
import com.llamafarm.atmosphere.capabilities.*
import com.llamafarm.atmosphere.core.AtmosphereNode
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*

/**
 * Foreground service that keeps the Atmosphere node running.
 * 
 * Handles:
 *   - WebSocket connection to relay
 *   - Gossip protocol
 *   - Capability lifecycle
 *   - Battery optimization
 */
class AtmosphereService : Service() {
    
    companion object {
        private const val NOTIFICATION_ID = 1
        private const val CHANNEL_ID = "atmosphere_service"
        
        fun start(context: Context, relayUrl: String) {
            val intent = Intent(context, AtmosphereService::class.java).apply {
                putExtra("relay_url", relayUrl)
            }
            context.startForegroundService(intent)
        }
        
        fun stop(context: Context) {
            context.stopService(Intent(context, AtmosphereService::class.java))
        }
    }
    
    private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())
    
    private lateinit var node: AtmosphereNode
    private lateinit var meshConnection: MeshConnection
    private lateinit var capabilityManager: CapabilityManager
    
    private var wakeLock: PowerManager.WakeLock? = null
    
    // State
    private val _connectionState = MutableStateFlow(ConnectionState.DISCONNECTED)
    val connectionState: StateFlow<ConnectionState> = _connectionState
    
    private val _stats = MutableStateFlow(NodeStats())
    val stats: StateFlow<NodeStats> = _stats
    
    // Binder for local binding
    inner class LocalBinder : Binder() {
        val service: AtmosphereService get() = this@AtmosphereService
    }
    
    private val binder = LocalBinder()
    
    override fun onBind(intent: Intent?): IBinder = binder
    
    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        
        // Initialize node
        val nodeId = getOrCreateNodeId()
        node = AtmosphereNode(nodeId)
        
        // Initialize capabilities
        capabilityManager = CapabilityManager(this, node)
        
        // Initialize mesh connection
        meshConnection = MeshConnection(node)
    }
    
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIFICATION_ID, createNotification())
        
        val relayUrl = intent?.getStringExtra("relay_url")
            ?: "wss://relay.atmosphere.llamafarm.com"
        
        scope.launch {
            connect(relayUrl)
        }
        
        // Acquire wake lock for reliable operation
        acquireWakeLock()
        
        return START_STICKY
    }
    
    private suspend fun connect(relayUrl: String) {
        _connectionState.value = ConnectionState.CONNECTING
        
        try {
            meshConnection.connect(relayUrl)
            _connectionState.value = ConnectionState.CONNECTED
            
            // Register capabilities
            capabilityManager.registerAll()
            
            // Start gossip
            meshConnection.startGossip()
            
            // Collect stats periodically
            scope.launch {
                while (isActive) {
                    delay(5000)
                    updateStats()
                }
            }
            
        } catch (e: Exception) {
            _connectionState.value = ConnectionState.ERROR(e.message ?: "Unknown error")
            
            // Retry with backoff
            delay(5000)
            connect(relayUrl)
        }
    }
    
    private fun updateStats() {
        val statsJson = node.getStats()
        // Parse and update _stats
    }
    
    override fun onDestroy() {
        scope.cancel()
        meshConnection.disconnect()
        capabilityManager.destroyAll()
        node.close()
        releaseWakeLock()
        super.onDestroy()
    }
    
    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Atmosphere Service",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "Keeps your device connected to the Atmosphere mesh"
        }
        
        val notificationManager = getSystemService(NotificationManager::class.java)
        notificationManager.createNotificationChannel(channel)
    }
    
    private fun createNotification(): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Atmosphere Active")
            .setContentText("Connected to mesh")
            .setSmallIcon(R.drawable.ic_mesh)
            .setOngoing(true)
            .build()
    }
    
    private fun acquireWakeLock() {
        val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = powerManager.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "Atmosphere::MeshConnection"
        ).apply {
            acquire(10 * 60 * 1000L) // 10 minutes max
        }
    }
    
    private fun releaseWakeLock() {
        wakeLock?.let {
            if (it.isHeld) it.release()
        }
    }
    
    private fun getOrCreateNodeId(): String {
        val prefs = getSharedPreferences("atmosphere", MODE_PRIVATE)
        return prefs.getString("node_id", null) ?: run {
            val id = java.util.UUID.randomUUID().toString()
            prefs.edit().putString("node_id", id).apply()
            id
        }
    }
}

sealed class ConnectionState {
    object DISCONNECTED : ConnectionState()
    object CONNECTING : ConnectionState()
    object CONNECTED : ConnectionState()
    data class ERROR(val message: String) : ConnectionState()
}

data class NodeStats(
    val gradientTableSize: Int = 0,
    val knownNodes: Int = 0,
    val announcementsSent: Long = 0,
    val announcementsReceived: Long = 0
)
```

---

## Mesh Connection

```kotlin
// service/MeshConnection.kt

package com.llamafarm.atmosphere.service

import com.llamafarm.atmosphere.core.AtmosphereNode
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel
import okhttp3.*
import okio.ByteString
import okio.ByteString.Companion.toByteString
import java.util.concurrent.TimeUnit

/**
 * WebSocket connection to the Atmosphere relay.
 * 
 * Handles:
 *   - Connection management
 *   - Message serialization
 *   - Gossip protocol over WebSocket
 *   - Reconnection with exponential backoff
 */
class MeshConnection(
    private val node: AtmosphereNode
) {
    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)  // No timeout for WebSocket
        .pingInterval(30, TimeUnit.SECONDS)
        .build()
    
    private var webSocket: WebSocket? = null
    private var relayUrl: String? = null
    
    private val outgoingMessages = Channel<ByteArray>(Channel.BUFFERED)
    private var gossipJob: Job? = null
    
    // Connection state
    var isConnected: Boolean = false
        private set
    
    /**
     * Connect to relay server.
     */
    suspend fun connect(url: String) {
        relayUrl = url
        
        val request = Request.Builder()
            .url(url)
            .build()
        
        suspendCancellableCoroutine<Unit> { cont ->
            webSocket = client.newWebSocket(request, object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    isConnected = true
                    cont.resume(Unit) {}
                }
                
                override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                    handleMessage(bytes.toByteArray())
                }
                
                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    isConnected = false
                    if (cont.isActive) {
                        cont.cancel(t)
                    }
                }
                
                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    isConnected = false
                }
            })
        }
        
        // Start message sender
        CoroutineScope(Dispatchers.IO).launch {
            for (msg in outgoingMessages) {
                webSocket?.send(msg.toByteString())
            }
        }
    }
    
    /**
     * Disconnect from relay.
     */
    fun disconnect() {
        gossipJob?.cancel()
        webSocket?.close(1000, "Normal closure")
        webSocket = null
        isConnected = false
    }
    
    /**
     * Start periodic gossip announcements.
     */
    fun startGossip() {
        gossipJob = CoroutineScope(Dispatchers.Default).launch {
            while (isActive) {
                // Build and send announcement
                // The Rust core builds the announcement, we just forward it
                // This would call into the native layer
                
                delay(30_000)  // 30 second interval
            }
        }
    }
    
    /**
     * Send a message to the relay.
     */
    suspend fun send(data: ByteArray) {
        outgoingMessages.send(data)
    }
    
    private fun handleMessage(data: ByteArray) {
        // Dispatch to node for processing
        CoroutineScope(Dispatchers.Default).launch {
            node.handleAnnouncement(data, relayUrl ?: "unknown")
        }
    }
}
```

---

## UI Screens

### Join Screen

```kotlin
// ui/screens/JoinScreen.kt

package com.llamafarm.atmosphere.ui.screens

import android.Manifest
import androidx.camera.view.PreviewView
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.google.accompanist.permissions.ExperimentalPermissionsApi
import com.google.accompanist.permissions.isGranted
import com.google.accompanist.permissions.rememberPermissionState

/**
 * Join screen - scan QR code or paste token to join a mesh.
 */
@OptIn(ExperimentalPermissionsApi::class)
@Composable
fun JoinScreen(
    onJoin: (meshToken: String) -> Unit,
    modifier: Modifier = Modifier
) {
    var tokenInput by remember { mutableStateOf("") }
    var showScanner by remember { mutableStateOf(true) }
    
    val cameraPermission = rememberPermissionState(Manifest.permission.CAMERA)
    
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = "Join Mesh",
            style = MaterialTheme.typography.headlineMedium
        )
        
        Spacer(modifier = Modifier.height(24.dp))
        
        // QR Scanner
        if (showScanner && cameraPermission.status.isGranted) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(1f)
            ) {
                QrScannerView(
                    onQrDetected = { token ->
                        onJoin(token)
                    }
                )
            }
            
            Spacer(modifier = Modifier.height(16.dp))
            
            TextButton(onClick = { showScanner = false }) {
                Text("Enter token manually")
            }
        } else if (!cameraPermission.status.isGranted) {
            // Request camera permission
            Button(onClick = { cameraPermission.launchPermissionRequest() }) {
                Text("Allow Camera")
            }
            
            Spacer(modifier = Modifier.height(8.dp))
            
            Text(
                text = "Camera permission needed to scan QR codes",
                style = MaterialTheme.typography.bodySmall
            )
            
            Spacer(modifier = Modifier.height(16.dp))
            
            TextButton(onClick = { showScanner = false }) {
                Text("Enter token manually instead")
            }
        } else {
            // Manual token entry
            OutlinedTextField(
                value = tokenInput,
                onValueChange = { tokenInput = it },
                label = { Text("Mesh Token") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            
            Spacer(modifier = Modifier.height(16.dp))
            
            Button(
                onClick = { onJoin(tokenInput) },
                enabled = tokenInput.isNotBlank(),
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("Join")
            }
            
            Spacer(modifier = Modifier.height(16.dp))
            
            TextButton(onClick = { showScanner = true }) {
                Text("Scan QR code instead")
            }
        }
    }
}

@Composable
private fun QrScannerView(
    onQrDetected: (String) -> Unit
) {
    val context = LocalContext.current
    
    AndroidView(
        factory = { ctx ->
            PreviewView(ctx).apply {
                // Setup camera preview and QR scanning
                // Using ML Kit Barcode Scanning
            }
        },
        modifier = Modifier.fillMaxSize()
    )
}
```

### Status Screen

```kotlin
// ui/screens/StatusScreen.kt

package com.llamafarm.atmosphere.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.llamafarm.atmosphere.service.ConnectionState
import com.llamafarm.atmosphere.service.NodeStats

/**
 * Status screen - shows connection status and mesh info.
 */
@Composable
fun StatusScreen(
    connectionState: ConnectionState,
    stats: NodeStats,
    capabilities: List<CapabilityStatus>,
    onDisconnect: () -> Unit,
    onSettingsClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        // Header
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "Atmosphere",
                style = MaterialTheme.typography.headlineMedium
            )
            
            IconButton(onClick = onSettingsClick) {
                Icon(Icons.Default.Settings, contentDescription = "Settings")
            }
        }
        
        Spacer(modifier = Modifier.height(16.dp))
        
        // Connection Status
        ConnectionStatusCard(connectionState)
        
        Spacer(modifier = Modifier.height(16.dp))
        
        // Mesh Stats
        MeshStatsCard(stats)
        
        Spacer(modifier = Modifier.height(16.dp))
        
        // Capabilities
        Text(
            text = "Capabilities",
            style = MaterialTheme.typography.titleMedium
        )
        
        Spacer(modifier = Modifier.height(8.dp))
        
        LazyColumn(
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(capabilities) { capability ->
                CapabilityCard(capability)
            }
        }
        
        Spacer(modifier = Modifier.weight(1f))
        
        // Disconnect button
        if (connectionState is ConnectionState.CONNECTED) {
            Button(
                onClick = onDisconnect,
                colors = ButtonDefaults.buttonColors(
                    containerColor = MaterialTheme.colorScheme.error
                ),
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("Disconnect")
            }
        }
    }
}

@Composable
private fun ConnectionStatusCard(state: ConnectionState) {
    Card(
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            val (icon, color, text) = when (state) {
                ConnectionState.DISCONNECTED -> Triple(
                    Icons.Default.CloudOff,
                    Color.Gray,
                    "Disconnected"
                )
                ConnectionState.CONNECTING -> Triple(
                    Icons.Default.Sync,
                    Color.Yellow,
                    "Connecting..."
                )
                ConnectionState.CONNECTED -> Triple(
                    Icons.Default.Cloud,
                    Color.Green,
                    "Connected"
                )
                is ConnectionState.ERROR -> Triple(
                    Icons.Default.Error,
                    Color.Red,
                    "Error: ${state.message}"
                )
            }
            
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = color
            )
            
            Spacer(modifier = Modifier.width(12.dp))
            
            Text(text = text)
        }
    }
}

@Composable
private fun MeshStatsCard(stats: NodeStats) {
    Card(
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(
            modifier = Modifier.padding(16.dp)
        ) {
            Text(
                text = "Mesh Stats",
                style = MaterialTheme.typography.titleSmall
            )
            
            Spacer(modifier = Modifier.height(8.dp))
            
            StatRow("Known Nodes", stats.knownNodes.toString())
            StatRow("Capabilities", stats.gradientTableSize.toString())
            StatRow("Announcements Sent", stats.announcementsSent.toString())
            StatRow("Announcements Received", stats.announcementsReceived.toString())
        }
    }
}

@Composable
private fun StatRow(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(text = label, style = MaterialTheme.typography.bodyMedium)
        Text(text = value, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun CapabilityCard(capability: CapabilityStatus) {
    Card(
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = capability.icon,
                contentDescription = null,
                modifier = Modifier.size(24.dp)
            )
            
            Spacer(modifier = Modifier.width(12.dp))
            
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = capability.label,
                    style = MaterialTheme.typography.bodyLarge
                )
                Text(
                    text = capability.status,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            
            Switch(
                checked = capability.enabled,
                onCheckedChange = capability.onToggle
            )
        }
    }
}

data class CapabilityStatus(
    val label: String,
    val icon: androidx.compose.ui.graphics.vector.ImageVector,
    val status: String,
    val enabled: Boolean,
    val onToggle: (Boolean) -> Unit
)
```

---

## Build Process

### Cargo Configuration

```toml
# atmosphere-core/Cargo.toml

[package]
name = "atmosphere-core"
version = "0.1.0"
edition = "2021"

[lib]
name = "atmosphere_core"
crate-type = ["cdylib", "staticlib", "rlib"]

[features]
default = []
android = ["jni"]
python = ["pyo3"]

[dependencies]
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
uuid = { version = "1.0", features = ["v4"] }
tokio = { version = "1", features = ["rt", "sync", "time"] }
thiserror = "1.0"

# JNI bindings (optional)
jni = { version = "0.21", optional = true }

# Python bindings (optional)
pyo3 = { version = "0.20", features = ["extension-module"], optional = true }

[target.'cfg(target_os = "android")'.dependencies]
android_logger = "0.13"
log = "0.4"

[profile.release]
lto = true
codegen-units = 1
opt-level = "s"  # Optimize for size
strip = true
```

### Android Build Script

```bash
#!/bin/bash
# build-android.sh

set -e

RUST_PROJECT="atmosphere-core"
ANDROID_PROJECT="atmosphere-android"

# Android NDK targets
TARGETS=(
    "aarch64-linux-android"
    "armv7-linux-androideabi"
    "x86_64-linux-android"
)

# Ensure targets are installed
for target in "${TARGETS[@]}"; do
    rustup target add "$target"
done

# Build for each target
for target in "${TARGETS[@]}"; do
    echo "Building for $target..."
    
    case $target in
        aarch64-linux-android)
            JNI_DIR="arm64-v8a"
            ;;
        armv7-linux-androideabi)
            JNI_DIR="armeabi-v7a"
            ;;
        x86_64-linux-android)
            JNI_DIR="x86_64"
            ;;
    esac
    
    # Build with cargo-ndk
    cargo ndk -t $target -o "$ANDROID_PROJECT/app/src/main/jniLibs" \
        --manifest-path "$RUST_PROJECT/Cargo.toml" \
        build --release --features android
done

echo "Rust build complete!"
echo "Native libraries placed in: $ANDROID_PROJECT/app/src/main/jniLibs/"
```

### Gradle Configuration

```kotlin
// atmosphere-android/app/build.gradle.kts

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.llamafarm.atmosphere"
    compileSdk = 34
    
    defaultConfig {
        applicationId = "com.llamafarm.atmosphere"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
        
        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64")
        }
    }
    
    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    
    buildFeatures {
        compose = true
    }
    
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.8"
    }
}

dependencies {
    // Compose
    implementation(platform("androidx.compose:compose-bom:2024.01.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.8.2")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.7.0")
    
    // Permissions
    implementation("com.google.accompanist:accompanist-permissions:0.34.0")
    
    // Camera
    implementation("androidx.camera:camera-camera2:1.3.1")
    implementation("androidx.camera:camera-lifecycle:1.3.1")
    implementation("androidx.camera:camera-view:1.3.1")
    
    // ML Kit for QR scanning
    implementation("com.google.mlkit:barcode-scanning:17.2.0")
    
    // Location
    implementation("com.google.android.gms:play-services-location:21.1.0")
    
    // WebSocket
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    
    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
}
```

---

## Implementation Plan

### Phase 1: Rust Core (2 weeks)
| Task | Effort | Priority |
|------|--------|----------|
| Port GradientTable to Rust | 2 days | P0 |
| Port GossipProtocol to Rust | 2 days | P0 |
| Implement cosine similarity | 0.5 days | P0 |
| Add JNI bindings | 2 days | P0 |
| Add PyO3 bindings | 1 day | P1 |
| Unit tests | 2 days | P0 |
| Integration tests with Python | 1 day | P1 |

### Phase 2: Android Project Setup (1 week)
| Task | Effort | Priority |
|------|--------|----------|
| Create Android project | 0.5 days | P0 |
| Configure Rust build pipeline | 1 day | P0 |
| Implement NativeCore wrapper | 1 day | P0 |
| Basic UI scaffolding | 1 day | P0 |
| Foreground service | 1 day | P0 |
| WebSocket connection | 1 day | P0 |

### Phase 3: Capabilities (2 weeks)
| Task | Effort | Priority |
|------|--------|----------|
| Camera capability | 2 days | P0 |
| Location capability | 2 days | P0 |
| Microphone capability | 2 days | P1 |
| Inference capability (llama.cpp) | 3 days | P2 |
| Capability manager | 1 day | P0 |

### Phase 4: UI & Polish (1 week)
| Task | Effort | Priority |
|------|--------|----------|
| Join screen (QR + manual) | 1 day | P0 |
| Status screen | 1 day | P0 |
| Settings screen | 1 day | P1 |
| Permission handling | 1 day | P0 |
| Battery optimization | 1 day | P1 |

### Phase 5: Testing & Release (1 week)
| Task | Effort | Priority |
|------|--------|----------|
| End-to-end testing | 2 days | P0 |
| Battery/performance profiling | 1 day | P1 |
| Play Store listing | 1 day | P1 |
| Documentation | 1 day | P1 |

**Optimistic Estimate: ~7 weeks**

---

## Realistic Implementation Timeline

> **⚠️ REALITY CHECK:** The above ~7 week estimate assumes everything goes smoothly.
> It won't. Here's what to actually expect.

**Realistic Total Estimate: 11-15 weeks** (not days, not 7 weeks)

### Phase 1: Rust Core (3-4 weeks)

| Week | Task | Blockers/Risks |
|------|------|----------------|
| 1-2 | Port GradientTable, GossipProtocol to Rust | Learning curve if team is new to Rust. Async patterns differ from Python. |
| 3 | Add JNI bindings, test on Android NDK | JNI is notoriously tricky. Expect debugging segfaults. Memory management across FFI boundary is hard. |
| 4 | Add PyO3 bindings, verify Python compatibility | Ensuring exact behavioral parity with existing Python code. Integration tests will surface edge cases. |

**Reality check:** JNI binding work alone can take longer than expected. The Android NDK toolchain has quirks, and cross-compilation from macOS to Android ARM targets can surface surprising issues.

### Phase 2: Android Shell (2-3 weeks)

| Week | Task | Blockers/Risks |
|------|------|----------------|
| 5 | Basic app structure, foreground service | Android foreground service requirements change frequently. Battery optimization (Doze) will fight you. |
| 6 | WebSocket mesh connection | Maintaining persistent WebSocket on Android is hard. OS kills background connections aggressively. |
| 7 | Capability registration flow | Getting the JNI bridge stable under real-world conditions. |

**Reality check:** Android's aggressive battery optimization (Doze mode, App Standby) will require significant testing and workarounds. What works in dev may break on real devices.

### Phase 3: Capabilities (3-4 weeks)

| Week | Task | Blockers/Risks |
|------|------|----------------|
| 8 | Camera capability | Runtime permissions, CameraX vs Camera2 API decisions, handling various device quirks. |
| 9 | Location capability | GPS accuracy varies wildly. Fused location provider has its own quirks. Background location is heavily restricted. |
| 10 | Microphone + transcription | Audio recording permissions, format compatibility, on-device Whisper integration. |
| 11 | On-device inference (llama.cpp) | **HIGH RISK**: llama.cpp on Android is not trivial. Memory constraints, thermal throttling, ANR risks. |

**Reality check:** On-device inference with llama.cpp is the highest-risk item. Mobile devices have limited RAM (many still ship with 4GB), and running even small LLMs will hit memory pressure. Expect significant optimization work.

### Phase 4: Polish (2-3 weeks)

| Week | Task | Blockers/Risks |
|------|------|----------------|
| 12 | UI/UX refinement | User testing will surface UX issues not caught in development. |
| 13 | Battery optimization, Doze handling | This is a rabbit hole. Different OEMs (Samsung, Xiaomi, etc.) have their own aggressive battery managers. |
| 14-15 | Testing, bug fixes | Real-world testing on diverse devices always takes longer than expected. |

### Risk Factors (Add to Timeline)

| Risk | Impact | Mitigation |
|------|--------|------------|
| Cross-compilation issues | +1-2 weeks | Start with simpler ARM target first, add x86 later |
| llama.cpp Android integration | +1-2 weeks | Consider making inference optional in v1.0 |
| OEM-specific battery issues | +1 week | Test on Samsung/Xiaomi early |
| App store review process | +2 weeks | Account for review cycles, potential rejections |
| JNI memory leaks | +1 week | Invest in memory profiling early |
| Real-world network conditions | +1 week | Test on cellular, flaky WiFi, offline transitions |

### Recommended Approach

**v1.0 (MVP): 8-10 weeks**
- Focus on core mesh functionality only
- Camera + Location capabilities only
- Defer on-device inference to v1.1
- Skip llama.cpp until core is stable

**v1.1 (Full): +4-6 weeks**
- Add microphone capability
- Add on-device inference (with memory-safe fallbacks)
- Optimize battery usage based on v1.0 feedback

### Honest Summary

| Scenario | Timeline |
|----------|----------|
| Everything goes perfectly | 7 weeks (the original estimate) |
| Normal development pace | 11-13 weeks |
| Including llama.cpp + polishing | 13-15 weeks |
| Until stable in production | 16-20 weeks |

**Don't promise 7 weeks unless you're prepared to cut scope significantly.**

---

## Migration Path: Python → Rust Core

Long-term, the Rust core becomes the single source of truth:

```
Phase 1 (Now):
┌─────────────────┐     ┌─────────────────┐
│  Python impl    │     │  Android app    │
│  (current)      │     │  (new)          │
└────────┬────────┘     └────────┬────────┘
         │                       │
         │                       ▼
         │              ┌─────────────────┐
         │              │  Rust core      │
         │              │  (JNI bindings) │
         │              └─────────────────┘
         │
         ▼
   Works independently

Phase 2 (6 months):
┌─────────────────┐     ┌─────────────────┐
│  Python app     │     │  Android app    │
│  (thin wrapper) │     │  (thin wrapper) │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
┌─────────────────────────────────────────┐
│           Rust atmosphere-core          │
│  PyO3 bindings  │    │  JNI bindings   │
└─────────────────────────────────────────┘

Phase 3 (1 year):
┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐
│ Python  │  │ Android │  │   iOS   │  │  WASM   │
│ (PyO3)  │  │  (JNI)  │  │ (Swift) │  │ (wasm)  │
└────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘
     │            │            │            │
     └────────────┴────────────┴────────────┘
                       │
                       ▼
            ┌─────────────────┐
            │ atmosphere-core │
            │    (Rust)       │
            └─────────────────┘
```

---

## Summary

The Android app follows a **Rust core + thin Kotlin wrapper** architecture:

1. **Rust core** (`atmosphere-core/`) contains ALL protocol logic
2. **JNI bindings** expose the core to Android
3. **Kotlin wrappers** provide idiomatic Android APIs
4. **Capabilities** are Kotlin classes that call into the core
5. **UI** is pure Jetpack Compose

This ensures:
- ✅ No protocol divergence between Python and Android
- ✅ Single codebase for protocol logic
- ✅ Native performance on mobile
- ✅ Future-proof for iOS (add Swift bindings to Rust core)
- ✅ Python can migrate to Rust core over time via PyO3

---

*Document Version: 1.0*  
*Date: 2025-02-02*  
*Architecture: Rust core + JNI + Kotlin wrappers*
