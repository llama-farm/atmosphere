import React, { useState, useEffect, useCallback } from 'react';
import { 
  Bluetooth, 
  Smartphone, 
  Laptop, 
  Check, 
  X, 
  RefreshCw, 
  Loader2,
  Shield,
  Link2,
  Zap
} from 'lucide-react';
import './BlePairingPanel.css';

const API_BASE = import.meta.env.VITE_API_BASE || '';

export function BlePairingPanel({ wsData }) {
  const [pairingState, setPairingState] = useState(null);
  const [nearbyDevices, setNearbyDevices] = useState([]);
  const [activeCode, setActiveCode] = useState(null);
  const [peerName, setPeerName] = useState('');
  const [isScanning, setIsScanning] = useState(false);
  const [error, setError] = useState(null);

  // Fetch pairing state from API
  const fetchPairingState = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/ble/pairing`);
      if (!response.ok) return;
      
      const data = await response.json();
      setPairingState(data.state);
      
      if (data.state === 'CODE_DISPLAY' && data.code) {
        setActiveCode(data.code);
        setPeerName(data.peer_name || 'Unknown Device');
      } else {
        setActiveCode(null);
      }
      
      if (data.nearby_devices) {
        setNearbyDevices(data.nearby_devices);
      }
    } catch (err) {
      // Pairing endpoint may not exist yet
      console.debug('Pairing state fetch failed:', err);
    }
  }, []);

  // Scan for nearby devices
  const startScan = useCallback(async () => {
    setIsScanning(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/ble/scan`, {
        method: 'POST'
      });
      if (!response.ok) throw new Error('Scan failed');
      
      const data = await response.json();
      setNearbyDevices(data.devices || []);
    } catch (err) {
      setError('Failed to scan for devices');
    } finally {
      setIsScanning(false);
    }
  }, []);

  // Initiate pairing with a device
  const initiatePairing = useCallback(async (deviceId, deviceName) => {
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/ble/pair`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: deviceId, device_name: deviceName })
      });
      if (!response.ok) throw new Error('Failed to initiate pairing');
      
      // Pairing initiated, state will update via polling
      await fetchPairingState();
    } catch (err) {
      setError(`Pairing failed: ${err.message}`);
    }
  }, [fetchPairingState]);

  // Confirm the code matches
  const confirmCode = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/ble/confirm`, {
        method: 'POST'
      });
      if (!response.ok) throw new Error('Confirmation failed');
      
      await fetchPairingState();
    } catch (err) {
      setError('Failed to confirm code');
    }
  }, [fetchPairingState]);

  // Reject the pairing
  const rejectPairing = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/api/ble/reject`, { method: 'POST' });
      setActiveCode(null);
      setPeerName('');
      await fetchPairingState();
    } catch (err) {
      console.error('Reject failed:', err);
    }
  }, [fetchPairingState]);

  // Poll for pairing state
  useEffect(() => {
    fetchPairingState();
    const interval = setInterval(fetchPairingState, 2000);
    return () => clearInterval(interval);
  }, [fetchPairingState]);

  // Handle WebSocket updates
  useEffect(() => {
    if (wsData?.event_type === 'BLE_PAIRING_CODE') {
      setActiveCode(wsData.code);
      setPeerName(wsData.peer_name || 'Unknown Device');
    } else if (wsData?.event_type === 'BLE_PAIRING_COMPLETE') {
      setActiveCode(null);
      setPeerName('');
      fetchPairingState();
    }
  }, [wsData, fetchPairingState]);

  const formatCode = (code) => {
    if (!code) return ['', ''];
    // Split 6-digit code into two groups of 3
    return [code.substring(0, 3), code.substring(3, 6)];
  };

  const [codeTop, codeBottom] = formatCode(activeCode);

  return (
    <div className="ble-pairing-panel">
      <div className="pairing-header">
        <h3>
          <Bluetooth size={20} />
          BLE Proximity Pairing
        </h3>
        <button 
          className="scan-btn" 
          onClick={startScan}
          disabled={isScanning}
        >
          {isScanning ? (
            <Loader2 size={16} className="spin" />
          ) : (
            <RefreshCw size={16} />
          )}
          {isScanning ? 'Scanning...' : 'Scan'}
        </button>
      </div>

      {error && (
        <div className="pairing-error">
          <X size={16} />
          {error}
        </div>
      )}

      {/* Active Pairing Code Display */}
      {activeCode && (
        <div className="pairing-code-display">
          <div className="code-header">
            <Shield size={24} className="shield-icon" />
            <span>Verify Pairing Code</span>
          </div>
          
          <div className="code-peer-name">
            <Smartphone size={16} />
            {peerName}
          </div>
          
          <div className="code-digits">
            <div className="code-row">
              {codeTop.split('').map((digit, i) => (
                <span key={`top-${i}`} className="code-digit">{digit}</span>
              ))}
            </div>
            <div className="code-row">
              {codeBottom.split('').map((digit, i) => (
                <span key={`bottom-${i}`} className="code-digit">{digit}</span>
              ))}
            </div>
          </div>
          
          <p className="code-instruction">
            Confirm this code matches on the other device
          </p>
          
          <div className="code-actions">
            <button className="confirm-btn" onClick={confirmCode}>
              <Check size={18} />
              Codes Match
            </button>
            <button className="reject-btn" onClick={rejectPairing}>
              <X size={18} />
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Nearby Devices List */}
      {!activeCode && (
        <div className="nearby-devices">
          <h4>
            <Zap size={16} />
            Nearby Atmosphere Nodes
          </h4>
          
          {nearbyDevices.length === 0 ? (
            <div className="no-devices">
              <Bluetooth size={32} className="muted" />
              <p>No devices found</p>
              <span>Make sure Bluetooth is enabled on nearby devices</span>
            </div>
          ) : (
            <div className="device-list">
              {nearbyDevices.map((device) => (
                <div key={device.id} className="device-item">
                  <div className="device-icon">
                    {device.platform === 'android' || device.platform === 'ios' ? (
                      <Smartphone size={24} />
                    ) : (
                      <Laptop size={24} />
                    )}
                  </div>
                  <div className="device-info">
                    <span className="device-name">{device.name || 'Unknown'}</span>
                    <span className="device-meta">
                      {device.rssi && `${device.rssi} dBm • `}
                      {device.platform || 'Unknown platform'}
                    </span>
                  </div>
                  <button 
                    className="pair-btn"
                    onClick={() => initiatePairing(device.id, device.name)}
                  >
                    <Link2 size={16} />
                    Pair
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Pairing State Indicator */}
      {pairingState && pairingState !== 'IDLE' && pairingState !== 'CODE_DISPLAY' && (
        <div className={`pairing-state ${pairingState.toLowerCase()}`}>
          {pairingState === 'INITIATING' && (
            <>
              <Loader2 size={16} className="spin" />
              Initiating pairing...
            </>
          )}
          {pairingState === 'EXCHANGING' && (
            <>
              <Loader2 size={16} className="spin" />
              Exchanging credentials...
            </>
          )}
          {pairingState === 'COMPLETED' && (
            <>
              <Check size={16} />
              Pairing complete!
            </>
          )}
          {pairingState === 'FAILED' && (
            <>
              <X size={16} />
              Pairing failed
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default BlePairingPanel;
