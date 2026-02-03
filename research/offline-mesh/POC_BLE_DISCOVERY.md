# Proof of Concept: BLE Mesh Discovery

**Purpose:** Minimal implementation to test BLE-based Atmosphere node discovery.

---

## Goal

Create a simple Android app that:
1. Advertises itself as an Atmosphere mesh node via BLE
2. Scans for other Atmosphere nodes
3. Displays discovered peers in real-time

This validates the core BLE discovery mechanism before building the full mesh transport.

---

## Implementation

### 1. Project Setup (Android)

```gradle
// app/build.gradle
android {
    compileSdk 34
    
    defaultConfig {
        minSdk 23  // BLE advertising requires API 21+
        targetSdk 34
    }
}

dependencies {
    implementation 'androidx.core:core-ktx:1.12.0'
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'com.google.android.material:material:1.11.0'
}
```

### 2. Permissions

```xml
<!-- AndroidManifest.xml -->
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    
    <!-- Bluetooth permissions -->
    <uses-permission android:name="android.permission.BLUETOOTH" />
    <uses-permission android:name="android.permission.BLUETOOTH_ADMIN" />
    <uses-permission android:name="android.permission.BLUETOOTH_SCAN" />
    <uses-permission android:name="android.permission.BLUETOOTH_ADVERTISE" />
    <uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
    
    <!-- Location for BLE scanning (required on older Android) -->
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
    
    <uses-feature android:name="android.hardware.bluetooth_le" android:required="true" />
    
    <application ...>
        <service android:name=".AtmosphereBleDiscoveryService" 
                 android:exported="false" />
    </application>
</manifest>
```

### 3. BLE Discovery Service

```kotlin
// AtmosphereBleDiscoveryService.kt
package com.atmosphere.poc

import android.app.Service
import android.bluetooth.*
import android.bluetooth.le.*
import android.content.Context
import android.content.Intent
import android.os.Binder
import android.os.IBinder
import android.os.ParcelUuid
import android.util.Log
import java.util.*

class AtmosphereBleDiscoveryService : Service() {
    
    companion object {
        private const val TAG = "AtmosphereBLE"
        
        // Atmosphere Mesh Service UUID
        val ATMOSPHERE_SERVICE_UUID: UUID = 
            UUID.fromString("A7M0MESH-0001-0000-0000-000000000001")
        
        // Generate unique node ID
        fun generateNodeId(): String = UUID.randomUUID().toString().take(8)
    }
    
    private val binder = LocalBinder()
    
    private lateinit var bluetoothManager: BluetoothManager
    private var bluetoothAdapter: BluetoothAdapter? = null
    private var advertiser: BluetoothLeAdvertiser? = null
    private var scanner: BluetoothLeScanner? = null
    
    private val nodeId = generateNodeId()
    private val discoveredPeers = mutableMapOf<String, DiscoveredPeer>()
    
    var onPeerDiscovered: ((DiscoveredPeer) -> Unit)? = null
    var onPeerLost: ((String) -> Unit)? = null
    
    inner class LocalBinder : Binder() {
        fun getService(): AtmosphereBleDiscoveryService = this@AtmosphereBleDiscoveryService
    }
    
    override fun onBind(intent: Intent): IBinder = binder
    
    override fun onCreate() {
        super.onCreate()
        bluetoothManager = getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        bluetoothAdapter = bluetoothManager.adapter
        
        if (bluetoothAdapter == null) {
            Log.e(TAG, "Bluetooth not supported")
            stopSelf()
            return
        }
    }
    
    fun startDiscovery() {
        startAdvertising()
        startScanning()
    }
    
    fun stopDiscovery() {
        stopAdvertising()
        stopScanning()
    }
    
    // ========== ADVERTISING ==========
    
    private fun startAdvertising() {
        advertiser = bluetoothAdapter?.bluetoothLeAdvertiser
        
        if (advertiser == null) {
            Log.e(TAG, "BLE advertising not supported")
            return
        }
        
        val settings = AdvertiseSettings.Builder()
            .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
            .setConnectable(false)  // Just discovery for now
            .setTimeout(0)  // Advertise indefinitely
            .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_HIGH)
            .build()
        
        // Include our node ID in the service data
        val serviceData = nodeId.toByteArray(Charsets.UTF_8)
        
        val data = AdvertiseData.Builder()
            .addServiceUuid(ParcelUuid(ATMOSPHERE_SERVICE_UUID))
            .addServiceData(ParcelUuid(ATMOSPHERE_SERVICE_UUID), serviceData)
            .setIncludeDeviceName(false)  // Save space
            .setIncludeTxPowerLevel(false)
            .build()
        
        advertiser?.startAdvertising(settings, data, advertiseCallback)
        Log.i(TAG, "Started advertising as node: $nodeId")
    }
    
    private fun stopAdvertising() {
        advertiser?.stopAdvertising(advertiseCallback)
        Log.i(TAG, "Stopped advertising")
    }
    
    private val advertiseCallback = object : AdvertiseCallback() {
        override fun onStartSuccess(settingsInEffect: AdvertiseSettings) {
            Log.i(TAG, "Advertising started successfully")
        }
        
        override fun onStartFailure(errorCode: Int) {
            val error = when (errorCode) {
                ADVERTISE_FAILED_ALREADY_STARTED -> "Already started"
                ADVERTISE_FAILED_DATA_TOO_LARGE -> "Data too large"
                ADVERTISE_FAILED_FEATURE_UNSUPPORTED -> "Feature unsupported"
                ADVERTISE_FAILED_INTERNAL_ERROR -> "Internal error"
                ADVERTISE_FAILED_TOO_MANY_ADVERTISERS -> "Too many advertisers"
                else -> "Unknown error: $errorCode"
            }
            Log.e(TAG, "Advertising failed: $error")
        }
    }
    
    // ========== SCANNING ==========
    
    private fun startScanning() {
        scanner = bluetoothAdapter?.bluetoothLeScanner
        
        if (scanner == null) {
            Log.e(TAG, "BLE scanner not available")
            return
        }
        
        val filter = ScanFilter.Builder()
            .setServiceUuid(ParcelUuid(ATMOSPHERE_SERVICE_UUID))
            .build()
        
        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .setReportDelay(0)  // Report immediately
            .build()
        
        scanner?.startScan(listOf(filter), settings, scanCallback)
        Log.i(TAG, "Started scanning for Atmosphere peers")
    }
    
    private fun stopScanning() {
        scanner?.stopScan(scanCallback)
        Log.i(TAG, "Stopped scanning")
    }
    
    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            handleScanResult(result)
        }
        
        override fun onBatchScanResults(results: MutableList<ScanResult>) {
            results.forEach { handleScanResult(it) }
        }
        
        override fun onScanFailed(errorCode: Int) {
            val error = when (errorCode) {
                SCAN_FAILED_ALREADY_STARTED -> "Already started"
                SCAN_FAILED_APPLICATION_REGISTRATION_FAILED -> "App registration failed"
                SCAN_FAILED_FEATURE_UNSUPPORTED -> "Feature unsupported"
                SCAN_FAILED_INTERNAL_ERROR -> "Internal error"
                else -> "Unknown error: $errorCode"
            }
            Log.e(TAG, "Scan failed: $error")
        }
    }
    
    private fun handleScanResult(result: ScanResult) {
        val serviceData = result.scanRecord
            ?.getServiceData(ParcelUuid(ATMOSPHERE_SERVICE_UUID))
            ?: return
        
        val peerNodeId = String(serviceData, Charsets.UTF_8)
        
        // Don't discover ourselves
        if (peerNodeId == nodeId) return
        
        val address = result.device.address
        val rssi = result.rssi
        val now = System.currentTimeMillis()
        
        val existing = discoveredPeers[peerNodeId]
        val peer = DiscoveredPeer(
            nodeId = peerNodeId,
            macAddress = address,
            rssi = rssi,
            lastSeen = now
        )
        
        discoveredPeers[peerNodeId] = peer
        
        if (existing == null) {
            Log.i(TAG, "Discovered new peer: $peerNodeId (RSSI: $rssi)")
            onPeerDiscovered?.invoke(peer)
        } else {
            // Update existing peer
            Log.d(TAG, "Updated peer: $peerNodeId (RSSI: $rssi)")
        }
    }
    
    fun getDiscoveredPeers(): List<DiscoveredPeer> = discoveredPeers.values.toList()
    
    fun getNodeId(): String = nodeId
    
    override fun onDestroy() {
        stopDiscovery()
        super.onDestroy()
    }
}

data class DiscoveredPeer(
    val nodeId: String,
    val macAddress: String,
    val rssi: Int,
    val lastSeen: Long
)
```

### 4. Main Activity

```kotlin
// MainActivity.kt
package com.atmosphere.poc

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView

class MainActivity : AppCompatActivity() {
    
    private var bleService: AtmosphereBleDiscoveryService? = null
    private var bound = false
    
    private lateinit var statusText: TextView
    private lateinit var nodeIdText: TextView
    private lateinit var peersRecycler: RecyclerView
    private lateinit var startButton: Button
    
    private val peersAdapter = PeersAdapter()
    
    private val serviceConnection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName, service: IBinder) {
            val binder = service as AtmosphereBleDiscoveryService.LocalBinder
            bleService = binder.getService()
            bound = true
            
            nodeIdText.text = "My Node ID: ${bleService?.getNodeId()}"
            
            bleService?.onPeerDiscovered = { peer ->
                runOnUiThread {
                    peersAdapter.addOrUpdatePeer(peer)
                }
            }
        }
        
        override fun onServiceDisconnected(name: ComponentName) {
            bleService = null
            bound = false
        }
    }
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        
        statusText = findViewById(R.id.statusText)
        nodeIdText = findViewById(R.id.nodeIdText)
        peersRecycler = findViewById(R.id.peersRecycler)
        startButton = findViewById(R.id.startButton)
        
        peersRecycler.layoutManager = LinearLayoutManager(this)
        peersRecycler.adapter = peersAdapter
        
        startButton.setOnClickListener {
            if (checkPermissions()) {
                toggleDiscovery()
            } else {
                requestPermissions()
            }
        }
        
        // Bind to service
        Intent(this, AtmosphereBleDiscoveryService::class.java).also { intent ->
            bindService(intent, serviceConnection, Context.BIND_AUTO_CREATE)
        }
    }
    
    private var isDiscovering = false
    
    private fun toggleDiscovery() {
        if (isDiscovering) {
            bleService?.stopDiscovery()
            startButton.text = "Start Discovery"
            statusText.text = "Stopped"
            isDiscovering = false
        } else {
            bleService?.startDiscovery()
            startButton.text = "Stop Discovery"
            statusText.text = "Discovering..."
            isDiscovering = true
        }
    }
    
    private fun checkPermissions(): Boolean {
        val permissions = mutableListOf<String>()
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            permissions.add(Manifest.permission.BLUETOOTH_SCAN)
            permissions.add(Manifest.permission.BLUETOOTH_ADVERTISE)
            permissions.add(Manifest.permission.BLUETOOTH_CONNECT)
        } else {
            permissions.add(Manifest.permission.ACCESS_FINE_LOCATION)
        }
        
        return permissions.all { 
            ActivityCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED 
        }
    }
    
    private fun requestPermissions() {
        val permissions = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            arrayOf(
                Manifest.permission.BLUETOOTH_SCAN,
                Manifest.permission.BLUETOOTH_ADVERTISE,
                Manifest.permission.BLUETOOTH_CONNECT
            )
        } else {
            arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
        }
        
        ActivityCompat.requestPermissions(this, permissions, 1)
    }
    
    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (grantResults.all { it == PackageManager.PERMISSION_GRANTED }) {
            toggleDiscovery()
        }
    }
    
    override fun onDestroy() {
        if (bound) {
            unbindService(serviceConnection)
            bound = false
        }
        super.onDestroy()
    }
}
```

### 5. Simple Layout

```xml
<!-- res/layout/activity_main.xml -->
<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical"
    android:padding="16dp">
    
    <TextView
        android:id="@+id/nodeIdText"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:text="My Node ID: ..."
        android:textSize="16sp"
        android:textStyle="bold" />
    
    <TextView
        android:id="@+id/statusText"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:text="Ready"
        android:layout_marginTop="8dp" />
    
    <Button
        android:id="@+id/startButton"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:text="Start Discovery"
        android:layout_marginTop="16dp" />
    
    <TextView
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:text="Discovered Peers:"
        android:textStyle="bold"
        android:layout_marginTop="24dp" />
    
    <androidx.recyclerview.widget.RecyclerView
        android:id="@+id/peersRecycler"
        android:layout_width="match_parent"
        android:layout_height="0dp"
        android:layout_weight="1"
        android:layout_marginTop="8dp" />
    
</LinearLayout>
```

### 6. Peers Adapter

```kotlin
// PeersAdapter.kt
package com.atmosphere.poc

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView

class PeersAdapter : RecyclerView.Adapter<PeersAdapter.ViewHolder>() {
    
    private val peers = mutableListOf<DiscoveredPeer>()
    
    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val nodeIdText: TextView = view.findViewById(R.id.peerNodeId)
        val rssiText: TextView = view.findViewById(R.id.peerRssi)
        val addressText: TextView = view.findViewById(R.id.peerAddress)
    }
    
    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_peer, parent, false)
        return ViewHolder(view)
    }
    
    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val peer = peers[position]
        holder.nodeIdText.text = "Node: ${peer.nodeId}"
        holder.rssiText.text = "RSSI: ${peer.rssi} dBm"
        holder.addressText.text = peer.macAddress
    }
    
    override fun getItemCount() = peers.size
    
    fun addOrUpdatePeer(peer: DiscoveredPeer) {
        val index = peers.indexOfFirst { it.nodeId == peer.nodeId }
        if (index >= 0) {
            peers[index] = peer
            notifyItemChanged(index)
        } else {
            peers.add(peer)
            notifyItemInserted(peers.size - 1)
        }
    }
}
```

```xml
<!-- res/layout/item_peer.xml -->
<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    android:orientation="vertical"
    android:padding="12dp"
    android:background="?attr/selectableItemBackground">
    
    <TextView
        android:id="@+id/peerNodeId"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:textSize="16sp"
        android:textStyle="bold" />
    
    <TextView
        android:id="@+id/peerRssi"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:textSize="14sp" />
    
    <TextView
        android:id="@+id/peerAddress"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:textSize="12sp"
        android:textColor="#888888" />
    
</LinearLayout>
```

---

## Testing

### What You Need
- 2+ Android devices with BLE support
- Android 6.0+ (API 23+)

### Test Steps

1. **Install** the POC app on both devices
2. **Grant** Bluetooth/Location permissions
3. **Tap** "Start Discovery" on both devices
4. **Verify** each device sees the other's node ID
5. **Check** RSSI values change with distance
6. **Move** devices apart and verify discovery still works

### Expected Results

| Distance | Expected RSSI | Discovery |
|----------|---------------|-----------|
| < 1m | -30 to -50 dBm | ✅ Instant |
| 1-5m | -50 to -70 dBm | ✅ Fast |
| 5-10m | -70 to -85 dBm | ✅ Works |
| 10-20m | -85 to -95 dBm | ⚠️ May drop |
| > 20m | < -95 dBm | ❌ Unreliable |

---

## Next Steps After POC

Once basic discovery works:

1. **Add connection** - Establish GATT connection between peers
2. **Add messaging** - Send/receive data over BLE
3. **Add multi-hop** - Route messages through intermediate nodes
4. **Port to iOS** - Implement CoreBluetooth version
5. **Cross-platform test** - Android ↔ iOS discovery

---

## Troubleshooting

### "Advertising failed: Feature unsupported"
- Device doesn't support BLE advertising
- Some older/cheaper devices lack this feature

### "Scan failed: App registration failed"
- Too many apps scanning simultaneously
- Restart Bluetooth or reboot device

### Peers not discovered
- Ensure both devices have Bluetooth ON
- Check permissions are granted
- Verify BLE is not being blocked by power saving mode

### RSSI always very low
- Check for interference (WiFi routers, microwaves)
- Metal objects between devices block BLE
