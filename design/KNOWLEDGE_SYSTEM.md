# Knowledge Distribution System Design

**Version:** 1.0  
**Status:** Draft  
**Last Updated:** 2025-02-02

---

## Executive Summary

This document defines how **knowledge** (RAG data, embeddings, documents) gets distributed across the Atmosphere mesh. The core challenge: nodes need knowledge to answer questions, but not every node needs all knowledge, and we can't ship everything everywhere.

**The Solution:** Domain-based knowledge subscription with chunk-level synchronization, pre-computed embeddings, and intelligent query routing.

---

## 1. The Problem

### What Nodes Need

Nodes need knowledge to be useful:
- **RAG databases** — Vector stores for semantic search
- **Document embeddings** — Pre-computed vectors for retrieval
- **Reference data** — Lookup tables, configurations, specs
- **Model weights** — Local LLMs, embedding models (separate concern)

### Why We Can't Ship Everything

| Constraint | Impact |
|------------|--------|
| **Storage** | Edge devices have limited disk (ESP32: 4MB, RPi: 32GB, phone: varies) |
| **Bandwidth** | Cellular/LoRa can't handle GB transfers |
| **Relevance** | Factory floor doesn't need HR policies |
| **Freshness** | Stale knowledge is dangerous in some domains |
| **Privacy** | Some knowledge can't leave certain boundaries |

### The Goal

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   USER: "What's the torque spec for Widget-A assembly bolt?"               │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    FACTORY FLOOR NODE (Edge)                        │   │
│   │                                                                     │   │
│   │   Local RAG: ✓ Has manufacturing procedures                        │   │
│   │   Query: "torque spec Widget-A assembly bolt"                      │   │
│   │   Match: chunk[mfg-proc-042] → "Widget-A bolt torque: 45 N·m"     │   │
│   │                                                                     │   │
│   │   Response time: 50ms (local)                                      │   │
│   │   No network needed: ✓                                             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   vs.                                                                       │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    WITHOUT KNOWLEDGE DISTRIBUTION                   │   │
│   │                                                                     │   │
│   │   Edge node has no RAG                                             │   │
│   │   Must call cloud: +200ms latency                                  │   │
│   │   Network required: WiFi/cellular                                  │   │
│   │   Fails if offline: ✗                                              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        KNOWLEDGE DISTRIBUTION SYSTEM                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      KNOWLEDGE LAYER                                 │   │
│  │                                                                      │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │   │
│  │  │   Domain    │  │   Domain    │  │   Domain    │  │   Domain   │  │   │
│  │  │ Definitions │  │  Registry   │  │Subscriptions│  │  Manifests │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      SYNC LAYER                                      │   │
│  │                                                                      │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │   │
│  │  │  Manifest   │  │   Chunk     │  │   Delta     │  │  Priority  │  │   │
│  │  │  Exchange   │  │  Transfer   │  │   Sync      │  │   Queue    │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      STORAGE LAYER                                   │   │
│  │                                                                      │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │   │
│  │  │ Chunk Store │  │  Embedding  │  │   Vector    │  │  Metadata  │  │   │
│  │  │  (Content)  │  │   Store     │  │    Index    │  │   Index    │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      QUERY LAYER                                     │   │
│  │                                                                      │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │   │
│  │  │   Local     │  │   Query     │  │  Result     │  │   Cache    │  │   │
│  │  │    RAG      │  │   Router    │  │ Aggregator  │  │  Manager   │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Integration with Atmosphere Layers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│                          ATMOSPHERE MESH                                    │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ WORK LAYER                                                            │ │
│  │   Intent: "answer question about manufacturing"                       │ │
│  │   → Decomposes to: [embed query, search RAG, generate answer]        │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                    │                                        │
│                                    ▼                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ ROUTING LAYER                                                         │ │
│  │   Capability: "rag:manufacturing-procedures" → Node A, Node B        │ │
│  │   Gradient table knows which nodes have which knowledge domains       │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                    │                                        │
│                                    ▼                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ MESH LAYER (Gossip)                                                   │ │
│  │   Knowledge manifests propagate via gossip                           │ │
│  │   "Node A has domain X: 5,000 chunks, version 42"                    │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                    │                                        │
│                                    ▼                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ KNOWLEDGE SYSTEM ← This Document                                      │ │
│  │   Domain subscription, chunk sync, local RAG, query routing          │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Data Structures

### 3.1 Knowledge Domain Definition

A **domain** is a logical grouping of related knowledge:

```yaml
# Domain definition: manufacturing-procedures
domain:
  id: manufacturing-procedures
  version: 1
  description: "Manufacturing SOPs, procedures, and specifications"
  
  # Where knowledge comes from
  sources:
    # Source 1: LlamaFarm RAG database
    - type: llamafarm_rag
      project: manufacturing
      strategy: procedures_db
      refresh: hourly
    
    # Source 2: Local documentation directory
    - type: directory
      path: /docs/manufacturing/
      glob: "**/*.md"
      refresh: on_change  # Watch for file changes
    
    # Source 3: External API
    - type: api
      endpoint: https://erp.internal/procedures
      auth: ${ERP_API_KEY}
      refresh: daily
  
  # How documents are chunked
  chunking:
    strategy: semantic      # semantic | fixed | paragraph | sentence
    max_chunk_size: 512     # Max tokens per chunk
    overlap: 50             # Token overlap between chunks
    respect_boundaries: true # Don't split across sections
  
  # Embedding configuration
  embedding:
    model: nomic-embed-text
    dimensions: 768
    normalize: true
    batch_size: 100
  
  # Distribution rules
  distribution:
    # Who gets this knowledge
    replicate_to:
      - capability: manufacturing_inspection   # Nodes with this capability
      - capability: quality_control
      - mission: production-line              # Nodes with this mission
      - node_tag: factory_floor               # Nodes with this tag
    
    # Constraints
    max_chunks_per_node: 10000   # Limit for constrained devices
    priority: high               # Sync priority (high | normal | low)
    ttl_days: 30                 # How long until stale
    
    # Geographic/privacy constraints
    boundaries:
      - type: region
        allowed: [us-east, us-west]
      - type: classification
        max_level: internal  # Don't sync to external nodes
  
  # Metadata for the domain
  metadata:
    owner: manufacturing-team
    contact: mfg@company.com
    tags: [sop, procedures, manufacturing]
```

### 3.2 Knowledge Chunk

A **chunk** is the atomic unit of knowledge:

```yaml
# Individual knowledge chunk
chunk:
  # Identity
  id: "mfg-proc-001-chunk-042"
  domain: manufacturing-procedures
  
  # Source information
  source:
    doc_id: "procedures/assembly-line-setup.md"
    doc_version: 3
    chunk_index: 42
    total_chunks: 128
    byte_offset: 24576
    byte_length: 1847
  
  # Content
  content: |
    When setting up the assembly line for Widget-A production, ensure the 
    following bolt torque specifications are applied:
    
    - Main frame bolts: 45 N·m ± 2 N·m
    - Motor mount bolts: 35 N·m ± 1 N·m
    - Safety guard bolts: 25 N·m ± 1 N·m
    
    CRITICAL: Always use calibrated torque wrench (CAL-001 or CAL-002).
    Verify calibration date before use.
  
  # Pre-computed embedding (768 floats)
  embedding:
    model: nomic-embed-text
    dimensions: 768
    values: [0.0234, -0.0456, 0.0123, ...]  # Actual 768-dim vector
  
  # Metadata for filtering/ranking
  metadata:
    section: "Assembly Line Setup"
    subsection: "Bolt Torque Specifications"
    document_title: "Widget-A Production Procedures"
    last_updated: 2024-02-01T14:30:00Z
    author: "J. Smith"
    language: en
    importance: high
    keywords: [torque, bolt, assembly, widget-a]
  
  # Sync tracking
  sync:
    version: 3
    checksum: "sha256:a1b2c3d4e5f6..."
    created_at: 2024-01-15T09:00:00Z
    updated_at: 2024-02-01T14:30:00Z
```

### 3.3 Domain Manifest

A **manifest** summarizes a domain's chunks for efficient sync:

```yaml
# Domain manifest (exchanged during sync)
manifest:
  domain_id: manufacturing-procedures
  version: 42
  
  # Summary statistics
  stats:
    total_chunks: 5247
    total_bytes: 12847293
    embedding_bytes: 16117248  # 5247 × 768 × 4 bytes
    
  # Chunk list (compact format for sync)
  chunks:
    - id: mfg-proc-001-chunk-001
      v: 3           # Version
      cs: "a1b2c3"   # Checksum (truncated)
    - id: mfg-proc-001-chunk-002
      v: 3
      cs: "d4e5f6"
    # ... thousands more
  
  # Batched checksum for quick comparison
  batch_checksums:
    - range: [0, 999]
      checksum: "sha256:batch0..."
    - range: [1000, 1999]
      checksum: "sha256:batch1..."
    # Quick way to find which batches differ
  
  # Timestamp for freshness
  generated_at: 2024-02-01T15:00:00Z
  expires_at: 2024-02-01T16:00:00Z
```

### 3.4 Node Knowledge State

Each node tracks what knowledge it has:

```yaml
# Node's local knowledge state
node_knowledge:
  node_id: factory-floor-node-01
  
  # Subscribed domains
  subscriptions:
    - domain: manufacturing-procedures
      subscribed_at: 2024-01-01T00:00:00Z
      reason: mission:production-line
    - domain: safety-protocols
      subscribed_at: 2024-01-01T00:00:00Z
      reason: capability:safety_monitoring
  
  # Domain states
  domains:
    manufacturing-procedures:
      local_version: 41           # What we have
      remote_version: 42          # What's available
      chunks_total: 5247
      chunks_local: 5100          # What we've synced
      chunks_pending: 147         # Awaiting sync
      last_sync: 2024-02-01T14:00:00Z
      sync_status: partial        # full | partial | stale
      storage_bytes: 28964541
    
    safety-protocols:
      local_version: 7
      remote_version: 7
      chunks_total: 823
      chunks_local: 823
      chunks_pending: 0
      last_sync: 2024-02-01T12:00:00Z
      sync_status: full
      storage_bytes: 4829104
  
  # Storage budget
  storage:
    allocated_bytes: 50000000     # 50 MB budget
    used_bytes: 33793645
    available_bytes: 16206355
```

---

## 4. Sync Protocol

### 4.1 Protocol Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         KNOWLEDGE SYNC PROTOCOL                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. SUBSCRIPTION    Node announces domain subscriptions                     │
│         │                                                                   │
│         ▼                                                                   │
│  2. DISCOVERY       Find nodes that have the knowledge                      │
│         │                                                                   │
│         ▼                                                                   │
│  3. MANIFEST        Exchange chunk manifests                                │
│         │                                                                   │
│         ▼                                                                   │
│  4. DIFF            Calculate what's missing/outdated                       │
│         │                                                                   │
│         ▼                                                                   │
│  5. TRANSFER        Pull missing chunks (batched)                           │
│         │                                                                   │
│         ▼                                                                   │
│  6. INDEX           Update local vector index                               │
│         │                                                                   │
│         ▼                                                                   │
│  7. ANNOUNCE        Gossip updated state to mesh                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Sequence Diagram: Full Sync

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    KNOWLEDGE SYNC SEQUENCE                                   │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Edge Node                  Hub Node                   LlamaFarm             │
│      │                          │                          │                 │
│      │  1. Subscribe(domain)    │                          │                 │
│      │─────────────────────────>│                          │                 │
│      │                          │                          │                 │
│      │  2. GetManifest(domain)  │                          │                 │
│      │─────────────────────────>│                          │                 │
│      │                          │                          │                 │
│      │                          │  3. FetchManifest()      │                 │
│      │                          │─────────────────────────>│                 │
│      │                          │                          │                 │
│      │                          │  4. Manifest(5247 chunks)│                 │
│      │                          │<─────────────────────────│                 │
│      │                          │                          │                 │
│      │  5. Manifest(5247 chunks)│                          │                 │
│      │<─────────────────────────│                          │                 │
│      │                          │                          │                 │
│      │  [Calculate diff: need 147 chunks]                  │                 │
│      │                          │                          │                 │
│      │  6. GetChunks([id1, id2, ...])                      │                 │
│      │─────────────────────────>│                          │                 │
│      │                          │                          │                 │
│      │                          │  7. FetchChunks()        │                 │
│      │                          │─────────────────────────>│                 │
│      │                          │                          │                 │
│      │                          │  8. Chunks(content+embed)│                 │
│      │                          │<─────────────────────────│                 │
│      │                          │                          │                 │
│      │  9. Chunks(147 chunks)   │                          │                 │
│      │<─────────────────────────│                          │                 │
│      │                          │                          │                 │
│      │  [Store chunks, update vector index]                │                 │
│      │                          │                          │                 │
│      │  10. Gossip: "I have domain X v42"                  │                 │
│      │──────────────────────────────────────────────────>  │                 │
│      │                          │                          │                 │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Delta Sync

For ongoing updates (not full sync):

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    DELTA SYNC SEQUENCE                                       │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Edge Node                  Hub Node                                         │
│      │                          │                                            │
│      │  1. DeltaRequest         │                                            │
│      │     domain: X            │                                            │
│      │     my_version: 41       │                                            │
│      │     batch_checksums: [...] (optional, for efficient diff)             │
│      │─────────────────────────>│                                            │
│      │                          │                                            │
│      │  2. DeltaResponse        │                                            │
│      │     current_version: 42  │                                            │
│      │     chunks_added: [...]  │                                            │
│      │     chunks_updated: [...] │                                           │
│      │     chunks_deleted: [...] │                                           │
│      │<─────────────────────────│                                            │
│      │                          │                                            │
│      │  3. GetChunks(added + updated IDs)                                    │
│      │─────────────────────────>│                                            │
│      │                          │                                            │
│      │  4. Chunks(content+embed)│                                            │
│      │<─────────────────────────│                                            │
│      │                          │                                            │
│      │  [Apply delta: add, update, delete]                                   │
│      │  [Update vector index]                                                │
│      │                          │                                            │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 4.4 Gossip Integration

Knowledge state propagates via the existing gossip protocol:

```yaml
# Gossip message for knowledge state
gossip_message:
  type: knowledge_state
  node_id: factory-floor-node-01
  timestamp: 2024-02-01T15:00:00Z
  
  # Compact summary of what this node has
  domains:
    - id: manufacturing-procedures
      version: 42
      chunks: 5247
      status: full
    - id: safety-protocols
      version: 7
      chunks: 823
      status: full
  
  # This becomes part of node's capability advertisement
  # Other nodes can route RAG queries here
```

The gradient table incorporates knowledge domains:

```python
# Gradient table entry with knowledge
gradient_entry = {
    "node_id": "factory-floor-node-01",
    "capabilities": ["manufacturing_inspection", "vibration_analysis"],
    "knowledge_domains": {
        "manufacturing-procedures": {"version": 42, "status": "full"},
        "safety-protocols": {"version": 7, "status": "full"}
    },
    "hops": 1,
    "latency_ms": 5,
    "last_seen": "2024-02-01T15:00:00Z"
}
```

---

## 5. Query Routing

### 5.1 Local-First Query Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         QUERY ROUTING LOGIC                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Query: "What's the torque spec for Widget-A?"                             │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 1: Local RAG Search                                            │   │
│  │                                                                     │   │
│  │   Embed query → Search local vector index                          │   │
│  │   Results: [chunk_042 (0.92), chunk_043 (0.87), chunk_001 (0.71)]  │   │
│  │                                                                     │   │
│  │   Best match score: 0.92 (above threshold 0.75)                    │   │
│  │   → Use local results ✓                                            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  If local results insufficient (below threshold OR explicitly requested):  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 2: Remote Escalation                                           │   │
│  │                                                                     │   │
│  │   Find nodes with better coverage of this domain                   │   │
│  │   → Node B has full domain, higher version                         │   │
│  │   Route query to Node B                                            │   │
│  │                                                                     │   │
│  │   Combine: Local results + Remote results                          │   │
│  │   Re-rank by relevance                                             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 3: Cross-Domain (if needed)                                    │   │
│  │                                                                     │   │
│  │   If query spans multiple domains:                                 │   │
│  │   "Compare Widget-A torque spec to safety requirements"            │   │
│  │                                                                     │   │
│  │   → Search manufacturing-procedures locally                        │   │
│  │   → Route safety query to node with safety-protocols               │   │
│  │   → Merge results                                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Query Routing Algorithm

```python
async def route_knowledge_query(
    query: str,
    domains: List[str] = None,  # Optional: limit to specific domains
    local_only: bool = False,
    min_confidence: float = 0.75,
    max_results: int = 5
) -> List[KnowledgeResult]:
    """
    Route a RAG query through the mesh.
    Local-first: search locally, escalate if needed.
    """
    
    # 1. EMBED THE QUERY
    query_embedding = await embed(query)
    
    # 2. DETERMINE TARGET DOMAINS
    if domains is None:
        # Infer from query content
        domains = infer_relevant_domains(query_embedding)
    
    results = []
    
    # 3. LOCAL SEARCH
    for domain in domains:
        if has_local_domain(domain):
            local_results = search_local_rag(
                query_embedding, 
                domain,
                limit=max_results
            )
            results.extend(local_results)
    
    # 4. CHECK IF ESCALATION NEEDED
    best_score = max((r.score for r in results), default=0)
    
    if not local_only and best_score < min_confidence:
        # Find nodes with better coverage
        remote_nodes = find_nodes_with_domain(
            domains,
            exclude=[local_node_id],
            min_version=get_local_version(domains[0]) + 1
        )
        
        # 5. REMOTE SEARCH (parallel)
        remote_tasks = []
        for node in remote_nodes[:3]:  # Limit to 3 nodes
            task = asyncio.create_task(
                remote_rag_query(node, query_embedding, domains)
            )
            remote_tasks.append(task)
        
        remote_results = await asyncio.gather(*remote_tasks)
        for batch in remote_results:
            results.extend(batch)
    
    # 6. MERGE AND RE-RANK
    results = deduplicate_by_chunk_id(results)
    results.sort(key=lambda r: r.score, reverse=True)
    
    return results[:max_results]
```

### 5.3 Query Routing Decision Tree

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      QUERY ROUTING DECISION TREE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│                         ┌─────────────────┐                                 │
│                         │  Query arrives  │                                 │
│                         └────────┬────────┘                                 │
│                                  │                                          │
│                                  ▼                                          │
│                    ┌─────────────────────────┐                              │
│                    │ Do I have this domain?  │                              │
│                    └────────┬───────┬────────┘                              │
│                        YES  │       │  NO                                   │
│                             ▼       ▼                                       │
│              ┌──────────────────┐  ┌────────────────────┐                   │
│              │  Search local    │  │ Route to node that │                   │
│              │  vector index    │  │ has this domain    │                   │
│              └────────┬─────────┘  └────────────────────┘                   │
│                       │                                                     │
│                       ▼                                                     │
│           ┌────────────────────────┐                                        │
│           │ Score >= threshold?    │                                        │
│           │     (e.g., 0.75)       │                                        │
│           └───────┬───────┬────────┘                                        │
│               YES │       │ NO                                              │
│                   ▼       ▼                                                 │
│        ┌───────────────┐ ┌────────────────────┐                             │
│        │ Return local  │ │ Is escalation      │                             │
│        │ results       │ │ allowed?           │                             │
│        └───────────────┘ └───────┬──────┬─────┘                             │
│                              YES │      │ NO                                │
│                                  ▼      ▼                                   │
│                   ┌───────────────────┐ ┌──────────────┐                    │
│                   │ Find nodes with   │ │ Return local │                    │
│                   │ better coverage   │ │ + warning    │                    │
│                   └─────────┬─────────┘ └──────────────┘                    │
│                             │                                               │
│                             ▼                                               │
│                   ┌───────────────────┐                                     │
│                   │ Query remote nodes│                                     │
│                   │ (parallel)        │                                     │
│                   └─────────┬─────────┘                                     │
│                             │                                               │
│                             ▼                                               │
│                   ┌───────────────────┐                                     │
│                   │ Merge + Re-rank   │                                     │
│                   │ Return combined   │                                     │
│                   └───────────────────┘                                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. LlamaFarm Integration

### 6.1 LlamaFarm as Master RAG

LlamaFarm serves as the **authoritative source** for knowledge:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LLAMAFARM INTEGRATION                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      LLAMAFARM (Master)                              │   │
│  │                                                                     │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │   │
│  │  │ RAG Project │  │ RAG Project │  │ RAG Project │                 │   │
│  │  │ manufacturing│ │ safety      │  │ hr-policies │                 │   │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                 │   │
│  │         │                │                │                         │   │
│  │         ▼                ▼                ▼                         │   │
│  │  ┌────────────────────────────────────────────────────┐            │   │
│  │  │              Embedding Generation                  │            │   │
│  │  │              Chunk Management                      │            │   │
│  │  │              Version Control                       │            │   │
│  │  └────────────────────────┬───────────────────────────┘            │   │
│  │                           │                                         │   │
│  └───────────────────────────┼─────────────────────────────────────────┘   │
│                              │                                              │
│                              │ Atmosphere Knowledge Adapter                 │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      ATMOSPHERE                                      │   │
│  │                                                                     │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │ Knowledge Distribution System                               │   │   │
│  │  │                                                             │   │   │
│  │  │  • Pulls chunks + embeddings from LlamaFarm                 │   │   │
│  │  │  • Distributes to subscribed edge nodes                     │   │   │
│  │  │  • Tracks versions, manages delta sync                      │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  │                           │                                         │   │
│  │         ┌─────────────────┼─────────────────┐                      │   │
│  │         ▼                 ▼                 ▼                      │   │
│  │  ┌───────────┐     ┌───────────┐     ┌───────────┐                │   │
│  │  │ Edge Node │     │ Edge Node │     │ Edge Node │                │   │
│  │  │ (Factory) │     │ (Office)  │     │ (Mobile)  │                │   │
│  │  │           │     │           │     │           │                │   │
│  │  │ mfg ✓     │     │ hr ✓      │     │ safety ✓  │                │   │
│  │  │ safety ✓  │     │ safety ✓  │     │           │                │   │
│  │  └───────────┘     └───────────┘     └───────────┘                │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 LlamaFarm Adapter

```python
class LlamaFarmKnowledgeAdapter:
    """
    Adapter to sync knowledge from LlamaFarm RAG projects
    to Atmosphere's distribution system.
    """
    
    def __init__(self, llamafarm_url: str = "http://localhost:8000"):
        self.client = LlamaFarmClient(llamafarm_url)
    
    async def fetch_domain_manifest(self, domain_id: str) -> Manifest:
        """Get manifest of all chunks in a LlamaFarm RAG project."""
        project = domain_to_project_mapping[domain_id]
        
        # Get chunk list from LlamaFarm
        chunks = await self.client.rag.list_chunks(project)
        
        return Manifest(
            domain_id=domain_id,
            version=await self.get_project_version(project),
            chunks=[
                ChunkRef(id=c.id, version=c.version, checksum=c.checksum)
                for c in chunks
            ]
        )
    
    async def fetch_chunks(
        self, 
        domain_id: str, 
        chunk_ids: List[str]
    ) -> List[Chunk]:
        """Fetch specific chunks with their embeddings."""
        project = domain_to_project_mapping[domain_id]
        
        chunks = []
        for chunk_id in chunk_ids:
            # Get chunk content
            content = await self.client.rag.get_chunk(project, chunk_id)
            
            # Get pre-computed embedding
            embedding = await self.client.rag.get_embedding(project, chunk_id)
            
            chunks.append(Chunk(
                id=chunk_id,
                domain=domain_id,
                content=content.text,
                embedding=embedding.values,
                metadata=content.metadata
            ))
        
        return chunks
    
    async def subscribe_to_updates(self, domain_id: str):
        """Subscribe to real-time updates from LlamaFarm."""
        project = domain_to_project_mapping[domain_id]
        
        async for event in self.client.rag.watch(project):
            if event.type == "chunk_added":
                yield KnowledgeEvent.CHUNK_ADDED(event.chunk_id)
            elif event.type == "chunk_updated":
                yield KnowledgeEvent.CHUNK_UPDATED(event.chunk_id)
            elif event.type == "chunk_deleted":
                yield KnowledgeEvent.CHUNK_DELETED(event.chunk_id)
```

---

## 7. Storage Requirements

### 7.1 Per-Chunk Storage

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CHUNK STORAGE BREAKDOWN                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Component              Size        Notes                                  │
│  ──────────────────────────────────────────────────────────────────────── │
│  Content (text)         ~500 B      Average 512 tokens × ~1 byte/token     │
│  Embedding (768-dim)    3,072 B     768 floats × 4 bytes                   │
│  Metadata               ~200 B      JSON: section, keywords, timestamps    │
│  Index overhead         ~100 B      HNSW index, checksums                  │
│  ──────────────────────────────────────────────────────────────────────── │
│  TOTAL PER CHUNK        ~4 KB                                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Domain Storage Calculator

```python
def calculate_domain_storage(
    num_documents: int,
    avg_doc_size_kb: float,
    chunk_size_tokens: int = 512,
    embedding_dimensions: int = 768
) -> dict:
    """
    Calculate storage requirements for a knowledge domain.
    """
    
    # Estimate chunks
    avg_doc_tokens = avg_doc_size_kb * 1024 / 4  # ~4 bytes per token
    chunks_per_doc = avg_doc_tokens / chunk_size_tokens
    total_chunks = int(num_documents * chunks_per_doc)
    
    # Storage components
    content_bytes = total_chunks * 500  # ~500 bytes avg
    embedding_bytes = total_chunks * embedding_dimensions * 4  # float32
    metadata_bytes = total_chunks * 200
    index_bytes = total_chunks * 100
    
    total_bytes = content_bytes + embedding_bytes + metadata_bytes + index_bytes
    
    return {
        "documents": num_documents,
        "estimated_chunks": total_chunks,
        "content_mb": content_bytes / 1_000_000,
        "embeddings_mb": embedding_bytes / 1_000_000,
        "metadata_mb": metadata_bytes / 1_000_000,
        "index_mb": index_bytes / 1_000_000,
        "total_mb": total_bytes / 1_000_000,
        "total_gb": total_bytes / 1_000_000_000
    }

# Example calculations
examples = {
    "small_domain": calculate_domain_storage(100, 10),    # 100 docs, 10KB avg
    "medium_domain": calculate_domain_storage(1000, 15),  # 1000 docs, 15KB avg
    "large_domain": calculate_domain_storage(10000, 20),  # 10K docs, 20KB avg
}
```

### 7.3 Device Storage Budgets

| Device Class | Typical Storage | Recommended Budget | Max Chunks |
|-------------|-----------------|-------------------|------------|
| ESP32 | 4 MB flash | 1 MB | ~250 |
| Raspberry Pi Zero | 8 GB SD | 500 MB | ~125,000 |
| Raspberry Pi 4 | 32 GB SD | 4 GB | ~1,000,000 |
| Edge Server | 256 GB SSD | 50 GB | ~12,500,000 |
| Mobile Phone | 64-256 GB | 1 GB | ~250,000 |

### 7.4 Storage Tier Configuration

```yaml
# Node storage configuration
storage:
  node_id: factory-floor-node-01
  device_class: raspberry_pi_4
  
  # Total budget
  knowledge_budget_mb: 4096
  
  # Per-domain limits
  domain_limits:
    manufacturing-procedures:
      max_mb: 2048
      max_chunks: 500000
      priority: 1  # Highest priority
    
    safety-protocols:
      max_mb: 1024
      max_chunks: 250000
      priority: 2
    
    general-reference:
      max_mb: 512
      max_chunks: 125000
      priority: 3
  
  # Eviction policy when full
  eviction:
    strategy: lru_by_domain  # Evict least-used within lowest-priority domain
    min_free_mb: 256         # Always keep this much free
```

---

## 8. Offline-First Design

### 8.1 Sync States

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         KNOWLEDGE SYNC STATES                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  State         Description                          Can Query?              │
│  ─────────────────────────────────────────────────────────────────────────│
│  SYNCING       Initial sync in progress             Partial (what's there) │
│  FULL          All subscribed chunks present        Yes, fully             │
│  PARTIAL       Some chunks missing (storage limit)  Yes, with limitations  │
│  STALE         Newer version available              Yes, might be outdated │
│  OFFLINE       No connection, using cached          Yes, cached data       │
│  ERROR         Sync failed, unknown state           Best effort            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 Graceful Degradation

```python
class OfflineFirstRAG:
    """
    RAG implementation that degrades gracefully when offline or stale.
    """
    
    async def query(self, query: str, domain: str) -> RAGResult:
        """Query with graceful degradation."""
        
        domain_state = self.get_domain_state(domain)
        
        # Always try local first
        local_results = await self.search_local(query, domain)
        
        # Determine quality of results
        result = RAGResult(
            chunks=local_results,
            source="local",
            quality=self._assess_quality(domain_state, local_results)
        )
        
        # Add warnings based on state
        if domain_state == DomainState.STALE:
            result.warnings.append(
                f"Knowledge may be outdated (local v{self.local_version} "
                f"vs available v{self.remote_version})"
            )
        
        if domain_state == DomainState.PARTIAL:
            result.warnings.append(
                f"Only {self.local_chunks}/{self.total_chunks} chunks available locally"
            )
        
        if domain_state == DomainState.OFFLINE:
            result.warnings.append(
                "Operating offline with cached knowledge"
            )
        
        # Try to escalate if connected and results are poor
        if (
            self.is_connected() and 
            result.quality < QualityLevel.GOOD and
            domain_state != DomainState.FULL
        ):
            try:
                remote_results = await self.escalate_query(query, domain)
                result = self._merge_results(result, remote_results)
            except NetworkError:
                result.warnings.append("Could not reach remote nodes for better results")
        
        return result
    
    def _assess_quality(
        self, 
        state: DomainState, 
        results: List[ChunkResult]
    ) -> QualityLevel:
        """Assess result quality based on state and scores."""
        
        if not results:
            return QualityLevel.NONE
        
        best_score = max(r.score for r in results)
        
        if state == DomainState.FULL and best_score > 0.85:
            return QualityLevel.EXCELLENT
        elif best_score > 0.75:
            return QualityLevel.GOOD
        elif best_score > 0.60:
            return QualityLevel.FAIR
        else:
            return QualityLevel.POOR
```

### 8.3 Sync Scheduling

```python
class KnowledgeSyncScheduler:
    """
    Schedules knowledge sync based on connectivity and priorities.
    """
    
    def __init__(self, node: AtmosphereNode):
        self.node = node
        self.sync_queue = PriorityQueue()
    
    async def run(self):
        """Main sync loop."""
        while True:
            # Check connectivity
            if not await self.node.is_connected():
                await asyncio.sleep(30)  # Check again in 30s
                continue
            
            # Get next domain to sync
            domain = await self.get_next_sync_target()
            if domain is None:
                await asyncio.sleep(60)  # Nothing to sync
                continue
            
            # Perform sync
            try:
                await self.sync_domain(domain)
            except SyncError as e:
                self.handle_sync_error(domain, e)
            
            # Yield to other operations
            await asyncio.sleep(1)
    
    async def get_next_sync_target(self) -> Optional[str]:
        """Determine which domain needs sync most urgently."""
        
        candidates = []
        
        for domain in self.node.subscribed_domains:
            state = self.node.get_domain_state(domain)
            priority = self.node.get_domain_priority(domain)
            
            score = 0
            
            # Higher score = sync sooner
            if state == DomainState.SYNCING:
                score = 100  # Finish in-progress syncs first
            elif state == DomainState.ERROR:
                score = 90 - (self.get_error_backoff(domain) * 10)
            elif state == DomainState.STALE:
                staleness_hours = self.get_staleness_hours(domain)
                score = 50 + min(staleness_hours, 40)
            elif state == DomainState.PARTIAL:
                coverage = self.get_coverage_percent(domain)
                score = 30 + (100 - coverage) * 0.5
            
            # Apply priority multiplier
            score *= {"high": 1.5, "normal": 1.0, "low": 0.5}[priority]
            
            if score > 0:
                candidates.append((domain, score))
        
        if not candidates:
            return None
        
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]
```

---

## 9. Example: Manufacturing Query Flow

### 9.1 Scenario

A factory floor worker asks their mobile device: **"What's the torque spec for Widget-A assembly bolts?"**

### 9.2 Complete Flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│            EXAMPLE: MANUFACTURING QUERY FLOW                                 │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. USER QUERY                                                               │
│     ─────────────────────────────────────────────────────────────────────   │
│     User speaks: "What's the torque spec for Widget-A assembly bolts?"      │
│                                                                              │
│     Mobile Device (Factory Floor Node)                                       │
│     ┌──────────────────────────────────────────────────────────────────┐    │
│     │ Subscriptions: [manufacturing-procedures, safety-protocols]       │    │
│     │ Domain Status: manufacturing-procedures → FULL (v42)             │    │
│     │ Local Chunks: 5,247                                               │    │
│     └──────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  2. INTENT PROCESSING                                                        │
│     ─────────────────────────────────────────────────────────────────────   │
│     Atmosphere decomposes intent:                                           │
│     • Work Unit 1: Embed query                                              │
│     • Work Unit 2: RAG search (domain: manufacturing-procedures)            │
│     • Work Unit 3: Generate answer with LLM                                 │
│                                                                              │
│  3. KNOWLEDGE QUERY (Local RAG)                                              │
│     ─────────────────────────────────────────────────────────────────────   │
│     Query embedding: [0.234, -0.127, 0.089, ...]                            │
│                                                                              │
│     Local vector search (HNSW index):                                        │
│     ┌───────────────────────────────────────────────────────────────────┐   │
│     │ Rank │ Chunk ID              │ Score │ Preview                    │   │
│     ├──────┼───────────────────────┼───────┼────────────────────────────┤   │
│     │  1   │ mfg-proc-001-chunk-042│ 0.94  │ "...Widget-A bolt torque:  │   │
│     │      │                       │       │  45 N·m ± 2 N·m..."        │   │
│     │  2   │ mfg-proc-001-chunk-043│ 0.87  │ "...calibrated torque      │   │
│     │      │                       │       │  wrench (CAL-001)..."      │   │
│     │  3   │ mfg-proc-002-chunk-017│ 0.72  │ "...assembly sequence      │   │
│     │      │                       │       │  for Widget-A..."          │   │
│     └───────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│     Best score: 0.94 > threshold (0.75) → Use local results ✓              │
│     Escalation: Not needed                                                  │
│     Network: Not used                                                       │
│                                                                              │
│  4. LLM ANSWER GENERATION                                                    │
│     ─────────────────────────────────────────────────────────────────────   │
│     Route to: Local LLM (Llama-3-8B) or escalate to GPU node                │
│                                                                              │
│     Context provided:                                                       │
│     ```                                                                      │
│     [Chunk mfg-proc-001-chunk-042]:                                         │
│     When setting up the assembly line for Widget-A production, ensure        │
│     the following bolt torque specifications are applied:                    │
│     - Main frame bolts: 45 N·m ± 2 N·m                                       │
│     - Motor mount bolts: 35 N·m ± 1 N·m                                      │
│     - Safety guard bolts: 25 N·m ± 1 N·m                                     │
│                                                                              │
│     [Chunk mfg-proc-001-chunk-043]:                                         │
│     CRITICAL: Always use calibrated torque wrench (CAL-001 or CAL-002).      │
│     Verify calibration date before use.                                      │
│     ```                                                                      │
│                                                                              │
│     Generated answer:                                                        │
│     "The torque spec for Widget-A assembly bolts is 45 N·m (±2 N·m)         │
│     for main frame bolts. Motor mount bolts require 35 N·m (±1 N·m)         │
│     and safety guard bolts need 25 N·m (±1 N·m). Remember to use            │
│     calibrated torque wrench CAL-001 or CAL-002."                           │
│                                                                              │
│  5. RESPONSE DELIVERY                                                        │
│     ─────────────────────────────────────────────────────────────────────   │
│     Total latency: ~150ms                                                   │
│     - Embedding: 15ms (local)                                               │
│     - RAG search: 35ms (local HNSW)                                         │
│     - LLM generation: 100ms (local 8B model)                                │
│                                                                              │
│     Network used: None (fully local)                                         │
│     Would work offline: Yes ✓                                               │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 9.3 Alternative: Escalation Scenario

What if the local node didn't have complete knowledge?

```
┌──────────────────────────────────────────────────────────────────────────────┐
│            EXAMPLE: ESCALATION FLOW                                          │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Same query: "What's the torque spec for Widget-A assembly bolts?"          │
│                                                                              │
│  But this time:                                                              │
│  • Mobile device has PARTIAL sync (storage constrained)                     │
│  • Local chunks: 2,000 / 5,247 (most recent procedures prioritized)        │
│  • Widget-A procedure chunk NOT locally present                             │
│                                                                              │
│  Local RAG search:                                                           │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │ Rank │ Chunk ID              │ Score │ Preview                    │      │
│  ├──────┼───────────────────────┼───────┼────────────────────────────┤      │
│  │  1   │ mfg-proc-003-chunk-012│ 0.61  │ "...general torque         │      │
│  │      │                       │       │  guidelines..."            │      │
│  │  2   │ mfg-proc-002-chunk-089│ 0.54  │ "...Widget-B assembly      │      │
│  │      │                       │       │  (not Widget-A)..."        │      │
│  └───────────────────────────────────────────────────────────────────┘      │
│                                                                              │
│  Best score: 0.61 < threshold (0.75) → ESCALATE                             │
│                                                                              │
│  Query routing:                                                              │
│  • Find nodes with manufacturing-procedures domain                          │
│  • Gradient table: factory-hub-01 has FULL sync, 5ms away                   │
│                                                                              │
│  Remote query to factory-hub-01:                                             │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │ Remote RAG search results:                                         │      │
│  │ Rank │ Chunk ID              │ Score │                             │      │
│  │  1   │ mfg-proc-001-chunk-042│ 0.94  │ ← The one we needed!       │      │
│  │  2   │ mfg-proc-001-chunk-043│ 0.87  │                             │      │
│  └───────────────────────────────────────────────────────────────────┘      │
│                                                                              │
│  Merged results:                                                             │
│  • Use remote chunk-042 (0.94) + chunk-043 (0.87)                           │
│  • Discard low-scoring local results                                         │
│                                                                              │
│  Total latency: ~200ms                                                       │
│  - Local search: 35ms                                                        │
│  - Network to hub: 10ms round-trip                                          │
│  - Remote search: 40ms                                                       │
│  - LLM (on hub, has GPU): 115ms                                             │
│                                                                              │
│  Note: 50ms slower than fully local, but correct answer                     │
│                                                                              │
│  BACKGROUND: After query, sync scheduler notes chunk-042 was needed         │
│  but missing. Prioritizes syncing this chunk in next sync window.           │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Security Considerations

### 10.1 Knowledge Boundaries

```yaml
# Domain with security boundaries
domain:
  id: hr-policies
  
  security:
    classification: confidential
    
    # Geographic restrictions
    boundaries:
      - type: region
        allowed: [us-east]
        denied: [eu-*]  # GDPR compliance
    
    # Node restrictions
    node_requirements:
      - encrypted_storage: true
      - secure_boot: true
      - min_security_level: 2
    
    # Access control
    access:
      - role: hr_staff
        permissions: [read, query]
      - role: manager
        permissions: [read, query]
      - role: employee
        permissions: []  # No direct access
```

### 10.2 Chunk-Level Encryption

For sensitive domains, chunks can be encrypted at rest:

```python
class EncryptedChunkStore:
    """
    Stores chunks with encryption.
    Key derived from node identity + domain secret.
    """
    
    def store_chunk(self, chunk: Chunk, domain_key: bytes):
        # Derive chunk-specific key
        chunk_key = derive_key(domain_key, chunk.id)
        
        # Encrypt content and embedding
        encrypted_content = encrypt(chunk.content, chunk_key)
        encrypted_embedding = encrypt(chunk.embedding, chunk_key)
        
        # Store with unencrypted metadata for indexing
        self.db.put(chunk.id, {
            "encrypted_content": encrypted_content,
            "encrypted_embedding": encrypted_embedding,
            "metadata": chunk.metadata,  # Searchable
            "checksum": chunk.checksum
        })
    
    def query_chunk(self, chunk_id: str, domain_key: bytes) -> Chunk:
        data = self.db.get(chunk_id)
        chunk_key = derive_key(domain_key, chunk_id)
        
        return Chunk(
            id=chunk_id,
            content=decrypt(data["encrypted_content"], chunk_key),
            embedding=decrypt(data["encrypted_embedding"], chunk_key),
            metadata=data["metadata"]
        )
```

---

## 11. Implementation Roadmap

### Phase 1: Core Infrastructure (2 weeks)

- [ ] Domain definition schema and parser
- [ ] Chunk data structure and storage
- [ ] Local vector index (HNSW) integration
- [ ] Basic manifest exchange protocol

### Phase 2: LlamaFarm Integration (1 week)

- [ ] LlamaFarm knowledge adapter
- [ ] Chunk fetching with embeddings
- [ ] Version tracking
- [ ] Real-time update subscription

### Phase 3: Sync Protocol (2 weeks)

- [ ] Manifest comparison and diff
- [ ] Delta sync implementation
- [ ] Priority queue for sync scheduling
- [ ] Bandwidth-aware batching

### Phase 4: Query Routing (1 week)

- [ ] Local-first RAG query
- [ ] Escalation logic
- [ ] Result merging
- [ ] Gossip integration for knowledge state

### Phase 5: Offline & Resilience (1 week)

- [ ] Offline query handling
- [ ] Graceful degradation
- [ ] Stale knowledge warnings
- [ ] Auto-sync on reconnect

### Phase 6: Security & Polish (1 week)

- [ ] Domain boundaries
- [ ] Encrypted storage option
- [ ] Access control integration
- [ ] Monitoring and metrics

---

## 12. Metrics & Monitoring

### Key Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| `sync_latency_ms` | Time to sync a domain | < 60s for delta |
| `query_latency_ms` | Time for RAG query | < 100ms local |
| `coverage_percent` | % of domain chunks present | > 95% for high-priority |
| `staleness_hours` | Hours since last sync | < 24h for active domains |
| `escalation_rate` | % of queries requiring escalation | < 10% |
| `offline_query_success` | % of offline queries with good results | > 80% |

### Health Check

```python
async def knowledge_health_check(node: AtmosphereNode) -> HealthReport:
    """Check knowledge system health."""
    
    issues = []
    
    for domain in node.subscribed_domains:
        state = node.get_domain_state(domain)
        
        if state == DomainState.ERROR:
            issues.append(f"Domain {domain} sync failed")
        elif state == DomainState.STALE:
            hours = node.get_staleness_hours(domain)
            if hours > 48:
                issues.append(f"Domain {domain} is {hours}h stale")
        elif state == DomainState.PARTIAL:
            coverage = node.get_coverage_percent(domain)
            if coverage < 50:
                issues.append(f"Domain {domain} only {coverage}% synced")
    
    return HealthReport(
        healthy=len(issues) == 0,
        issues=issues,
        domains={
            d: node.get_domain_state(d)
            for d in node.subscribed_domains
        }
    )
```

---

## Summary

The Knowledge Distribution System enables edge nodes to answer questions locally by:

1. **Selective Replication** — Nodes subscribe to relevant domains only
2. **Pre-computed Embeddings** — No local embedding compute needed
3. **Chunk-level Sync** — Efficient delta updates
4. **Offline-First** — Works without network after initial sync
5. **Intelligent Routing** — Escalates to better nodes when needed

This is how a factory floor device can answer "What's the torque spec?" in 50ms without touching the network — while a headquarters node can answer HR questions that never leave the office.

**Knowledge flows to where it's needed. Queries stay local. The mesh handles the rest.**
