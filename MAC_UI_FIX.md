# Mac Atmosphere UI Fix - Dynamic Cost Metrics + Real Permissions

**Date:** 2025-01-19  
**Status:** ✅ Implemented

## Summary

Fixed three major issues in the Mac Atmosphere UI:

1. **Cost Metrics not updating dynamically** - Now polls every 20 seconds + WebSocket real-time updates
2. **Cost not broadcast on gossip network** - WebSocket broadcasts cost updates to all connected clients
3. **Permissions not showing actual macOS status** - New `/api/permissions/status` endpoint + "Open Settings" buttons

---

## Changes Made

### 1. CostMetrics.jsx - Dynamic Polling + Visual Indicators

**File:** `ui/src/components/CostMetrics.jsx`

**Changes:**
- Added `lastUpdated` state with timestamp display
- Added `changedFields` tracking for visual change indicators  
- Added WebSocket listener for real-time `cost_update` messages
- Added `pulse-highlight` CSS animation when values change
- Added `detectChanges()` function to identify which metrics changed
- Shows "Last updated: Xs ago" indicator
- Shows "Auto-refresh every 20s" at bottom

**Key Features:**
- Polls `/api/cost/current` every 20 seconds (configurable via `refreshInterval` prop)
- Listens to WebSocket for `cost_update` messages for instant updates
- Visual pulse animation highlights changed metrics
- Reconnects WebSocket automatically on disconnect

### 2. CostMetrics.css - Animation Styles

**File:** `ui/src/components/CostMetrics.css`

**Added:**
- `@keyframes pulse-highlight` - Subtle blue glow animation
- `.pulse-highlight` class for animated elements
- `.header-right` flexbox for cost badge + timestamp
- `.last-updated` styling
- `.refresh-indicator` styling

### 3. routes.py - Backend Fixes

**File:** `atmosphere/api/routes.py`

**Fixed:**
- Changed `create_collector` import to `get_cost_collector` (bug fix)

**Added:**
- `/api/permissions/status` endpoint - Returns macOS permission status for:
  - Camera (via imagesnap test)
  - Microphone (via AVFoundation test)
  - Screen Recording (via screencapture test)
- `/api/permissions/open-settings` endpoint - Opens System Settings to the relevant pane

**WebSocket enhancements:**
- Sends initial `cost_update` on connect
- Broadcasts `cost_update` every 30 seconds to all clients
- Message format:
  ```json
  {
    "type": "cost_update",
    "node_id": "...",
    "cost": 1.2,
    "factors": { ... },
    "timestamp": 1705678901.234
  }
  ```

**Topology endpoint:**
- `/api/mesh/topology` now includes `cost` and `costFactors` for each node
- Fetches peer costs from gossip state if available

### 4. MeshTopology.jsx - Cost Visualization

**File:** `ui/src/components/MeshTopology.jsx`

**Added:**
- `getCostColor()` function - Maps cost multiplier to colors:
  - Green (#10b981): ≤1.2x (cheap)
  - Yellow (#f59e0b): ≤2.0x (moderate)
  - Orange (#f97316): ≤3.0x (expensive)
  - Red (#ef4444): >3.0x (very expensive)
  - Gray (#6b7280): Unknown
- Cost ring around each node (outer circle)
- Dashed ring for unknown cost
- Updated tooltip to show cost details and breakdown
- Legend items for cost levels

### 5. MeshTopology.css - Cost Ring Styles

**File:** `ui/src/components/MeshTopology.css`

**Added:**
- `.legend-divider` - Vertical separator in legend
- `.legend-ring` - Ring style for cost legend
- `.cost-low`, `.cost-moderate`, `.cost-high` - Color variants
- `.cost-ring` - Transition for smooth updates

### 6. ApprovalPanel.jsx - Real Permission Status

**File:** `ui/src/components/ApprovalPanel.jsx`

**Added:**
- `PermissionStatus` component - Shows granted/denied/pending status with icons
- Fetches `/api/permissions/status` on load and every 30 seconds
- Shows macOS permission banner explaining system permissions
- "Open Settings" button for each permission when not granted
- Shows instructions when permission is needed but not granted
- Mode selector only shown when permission is granted

**Permission Status Display:**
- ✅ Granted (green)
- ❌ Denied (red)
- ⚠️ Not Set (yellow)
- ? Unknown (gray)

### 7. ApprovalPanel.css - Permission Styles

**File:** `ui/src/components/ApprovalPanel.css`

**Added:**
- `.macos-permissions-banner` - Blue info banner
- `.permission-controls` - Flex container for status + button
- `.permission-status` variants - granted, denied, pending, unknown
- `.open-settings-btn` - Button to open System Settings
- `.permission-instructions` - Warning box with instructions

---

## Testing

### Test 1: Cost Updates When Unplugging

1. Open Atmosphere UI → Dashboard with Cost Metrics
2. Unplug MacBook from power
3. **Expected:** Battery status updates within 30 seconds
4. **Visual:** Power card should pulse/flash blue when changing

### Test 2: CPU Load Updates

1. Open Activity Monitor or run a CPU-heavy task
2. Watch the CPU Load metric
3. **Expected:** CPU% increases within 20-30 seconds

### Test 3: Mesh Topology Cost Indicators

1. Open Mesh Topology view
2. Look at node rings (outer colored circle)
3. **Expected:** 
   - Green ring = low cost (plugged in, low load)
   - Yellow/Orange ring = moderate/high cost
   - Dashed ring = unknown cost

### Test 4: Permission Status

1. Open Owner Approval panel
2. Expand "Privacy-Sensitive" section
3. **Expected:**
   - Shows current macOS permission status
   - "Open Settings" button appears for non-granted permissions
   - Clicking opens System Settings to correct pane

---

## API Endpoints

### GET /api/cost/current
Returns fresh system metrics (always recollected, not cached).

### GET /api/permissions/status
```json
{
  "platform": "Darwin",
  "permissions": {
    "camera": {
      "status": "granted|denied|not_determined|unknown",
      "settings_url": "x-apple.systempreferences:...",
      "instructions": "System Settings → ..."
    },
    "microphone": { ... },
    "screen_recording": { ... }
  },
  "timestamp": 1705678901.234
}
```

### POST /api/permissions/open-settings?permission=camera
Opens macOS System Settings to the relevant privacy pane.

### WS /api/ws
WebSocket endpoint that broadcasts:
- `mesh_status` on connect
- `cost_update` every 30 seconds
- `ping` for keepalive

---

## Architecture Notes

### Cost Collection
The cost collector (`atmosphere/cost/collector.py`) uses:
- `psutil.sensors_battery()` - Live battery status
- `psutil.getloadavg()` - CPU load average
- `psutil.virtual_memory()` - Memory usage

These are always called fresh on each `/api/cost/current` request - no caching.

### Cost Calculation
Uses `compute_node_cost(factors, WorkRequest())` from `atmosphere/cost/model.py`:
- Takes `NodeCostFactors` and `WorkRequest` as inputs
- Returns a multiplier (1.0 = baseline, higher = more expensive)
- Factors in power state, CPU load, memory pressure, network state

### Cost Gossip
The gossip system (`atmosphere/cost/gossip.py`) handles:
- `NODE_COST_UPDATE` messages
- Staleness tracking (30s for battery, 60s default)
- `CostBroadcaster` for periodic broadcasts

### Permission Checking
On macOS, direct permission checking via TCC database requires root.
Instead, we use capability tests:
- Camera: Try to list capture devices via imagesnap
- Microphone: Try to list audio input devices
- Screen: Try to run screencapture

---

## Future Improvements

1. **Better permission detection** - Use pyobjc for direct TCC queries
2. **Cost history graph** - Show cost over time
3. **Alert on high cost** - Notify when node becomes expensive
4. **Peer cost sync** - Ensure gossip state is properly integrated
