# Android APK Build Report

**Generated:** 2026-02-07 01:28 CST  
**Build Status:** ✅ **SUCCESS**

---

## Build Summary

| Property | Value |
|----------|-------|
| Build Type | Debug |
| Build Result | SUCCESS |
| Tasks Executed | 3 executed, 59 up-to-date |
| Build Time | ~4s (from cache) |

---

## APK Details

| Property | Value |
|----------|-------|
| **Location** | `~/clawd/projects/atmosphere-android/app/build/outputs/apk/debug/app-debug.apk` |
| **Size** | 1.2 GB |
| **Build Timestamp** | Feb 7 01:28:11 2026 |

> **Note:** The large APK size (1.2GB) is expected due to bundled ML models in the assets.

---

## Verified Changes

### 1. Token Parsing in AtmosphereViewModel ✅

**File:** `app/src/main/kotlin/com/llamafarm/atmosphere/viewmodel/AtmosphereViewModel.kt`

Token parsing now extracts `mesh_id` from multiple paths:
- ✅ `tokenObject.mesh_id` - Direct from token object
- ✅ Root level `mesh_id` - Direct JSON root
- ✅ `token.mesh_id` - Nested v1 format
- ✅ `mesh.id` / `mesh.mesh_id` - Mesh object format
- ✅ `m.id` / `m.i` - v2 short format
- ✅ `mesh_name` / `mesh.name` / `m.n` - Mesh name variants

### 2. BLE UUIDs ✅

**File:** `app/src/main/kotlin/com/llamafarm/atmosphere/transport/BleTransport.kt`

Correct Atmosphere Mesh Service UUIDs configured:
| UUID | Value |
|------|-------|
| MESH_SERVICE_UUID | `A7A05F30-0001-4000-8000-00805F9B34FB` |
| TX_CHAR_UUID | `A7A05F30-0002-4000-8000-00805F9B34FB` |
| RX_CHAR_UUID | `A7A05F30-0003-4000-8000-00805F9B34FB` |
| INFO_CHAR_UUID | `A7A05F30-0004-4000-8000-00805F9B34FB` |
| MESH_ID_CHAR_UUID | `A7A05F30-0005-4000-8000-00805F9B34FB` |
| CCCD_UUID | `00002902-0000-1000-8000-00805F9B34FB` |

---

## Warnings

### Gradle Plugin Warning (Non-blocking)
```
WARNING: We recommend using a newer Android Gradle plugin to use compileSdk = 35
Android Gradle plugin (8.2.2) was tested up to compileSdk = 34.
```

**Resolution:** Add to `gradle.properties`:
```
android.suppressUnsupportedCompileSdk=35
```

---

## Full APK Path

```
/Users/robthelen/clawd/projects/atmosphere-android/app/build/outputs/apk/debug/app-debug.apk
```

---

## Next Steps

1. Install on device: `adb install -r app-debug.apk`
2. Test token scanning with QR codes
3. Verify BLE mesh discovery works with Mac counterpart
