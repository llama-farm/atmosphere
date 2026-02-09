# Message Type Audit Report

**Date:** 2026-02-07
**Issue:** Message type format mismatch between Mac and Android breaking gossip sync

## Root Cause
Mac was using dot notation (`capability.announce`) while Android expected underscore (`capability_announce`).

## Message Types Comparison

| Message Type | Mac Format | Android Format | Status |
|--------------|------------|----------------|--------|
| capability announce | `capability_announce` | `capability_announce` | ✅ Fixed |
| capability request | `capability_request` | `capability_request` | ✅ Fixed |
| capability response | `capability_response` | `capability_response` | ✅ Fixed |
| llm response | `llm_response` | `llm_response` | ✅ Match |
| inference request | `inference_request` | `inference_request` | ✅ Match |
| peer joined | `peer_joined` | `peer_joined` | ✅ Match |
| peer left | `peer_left` | `peer_left` | ✅ Match |

## Files Modified

### Mac (atmosphere/)
- `atmosphere/core/gossip.py` - Changed constants to use underscore:
  - `GOSSIP_MSG_ANNOUNCE = "capability_announce"`
  - `GOSSIP_MSG_REQUEST = "capability_request"`
  - `GOSSIP_MSG_RESPONSE = "capability_response"`

### Android (atmosphere-android/)
- `network/MeshConnection.kt` - Added `capability_announce` to accepted formats

## Prevention
- Always use **underscore** notation for message types
- When adding new message types, check both codebases
- Keep this audit updated

## Standard: Use Underscore Convention
```
✅ capability_announce
✅ inference_request
✅ llm_response
❌ capability.announce  (don't use)
❌ inference.request    (don't use)
```
