# Atmosphere Phone Test Plan

## Pre-Flight Checklist

### Mac Server
- [ ] Server running on :11451 (`curl localhost:11451/health`)
- [ ] LlamaFarm healthy on :14345 (`curl localhost:14345/health`)
- [ ] Universal Runtime healthy (3 models loaded)
- [ ] 1 discoverable project registered (llama-expert-14)

### QR Code Ready
```bash
cd ~/clawd && python3 generate_invite.py && open /tmp/atmosphere_invite2.png
```

### Android APK
```bash
adb install -r ~/clawd/projects/atmosphere-android/app/build/outputs/apk/debug/app-debug.apk
```

---

## Test Sequence

### Test 1: Fresh Connect
1. Clear app data if needed: Settings → Apps → Atmosphere → Clear Data
2. Open Atmosphere app
3. Go to **Mesh** tab
4. Tap **Join Mesh**
5. Scan QR code
6. **Expected**: Connected via LOCAL (not relay) - same network

### Test 2: Cost Dashboard
1. Go to **Home** tab
2. **Expected**: See "Routing Costs" card with:
   - Local device cost (should be ~1.0 if charging on WiFi)
   - Peer costs should appear (Mac cost)

### Test 3: Auto-Reconnect (THE BIG ONE)
1. **Kill the app** (swipe away)
2. Wait 5 seconds
3. **Reopen the app**
4. **Expected**: App should auto-reconnect WITHOUT scanning QR
5. Check **Home** tab - should show "Connected"

### Test 4: Background Reconnect
1. Press Home button (don't kill app)
2. Wait 30 seconds
3. Return to app
4. **Expected**: Still connected or auto-reconnected

### Test 5: Inference with Semantic Router
1. Go to **Test** tab
2. Tap **Math** quick test ("What is 2+2?")
3. **Expected**: 
   - Response appears
   - **Semantic Router** card shows:
     - Method: KEYWORD or EMBEDDING
     - Score: >0.5
     - Capability routed to
4. Check Mac terminal for: `🎯 INTENT: TRIVIAL (qa) → tiny (<1B)`

### Test 6: Complex Inference
1. In **Test** tab, use Custom Prompt:
   - "Research the impact of AI on healthcare"
2. **Expected**:
   - Response (may take longer)
   - Mac terminal shows: `🎯 INTENT: EXPERT (research) → xlarge (14B+)`

### Test 7: LAN vs Relay Preference
1. While connected, check server logs
2. **Expected**: Connection from `192.168.x.x` (local IP), NOT relay

### Test 8: Cost Updates via Gossip
1. On Mac, check: `curl localhost:11451/api/cost/current`
2. On phone, check Home tab
3. **Expected**: Mac cost should appear in peer costs

---

## Known Limitations (For Now)

1. **BLE/Matter fallover** - Not implemented yet
2. **Gossip UI visibility** - Cost propagation works but not shown in detail
3. **Model selection by complexity** - Classification logged but not used for selection yet

---

## Troubleshooting

### App won't auto-reconnect
Check Android logs:
```bash
adb logcat -s AtmosphereViewModel | grep -i "reconnect\|mesh\|token"
```

If you see `TOKEN_INVALID`, credentials may be corrupted. Clear app data and re-scan.

### Shows Relay instead of Local
Check invitation endpoints:
```bash
python3 generate_invite.py
# Look for: "local": "ws://192.168.x.x:11451"
```

Make sure Mac and phone are on same WiFi network.

### No cost displayed
Check if CostCollector is running:
```bash
adb logcat -s CostCollector
```

---

## Success Criteria

✅ Fresh connect works via local network
✅ Cost dashboard shows local + peer costs  
✅ **Auto-reconnect works after app kill**
✅ Background resume reconnects
✅ Inference works with semantic router visibility
✅ Intent classification logged on Mac
