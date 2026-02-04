import React, { useState, useEffect, useCallback } from 'react';
import { 
  Wifi, 
  Globe, 
  Bluetooth, 
  Radio, 
  Activity,
  Check,
  X,
  RefreshCw,
  Users,
  Zap,
  AlertTriangle
} from 'lucide-react';
import './TransportStatus.css';

const API_BASE = import.meta.env.VITE_API_BASE || '';

const TRANSPORTS = [
  { 
    id: 'lan', 
    name: 'LAN', 
    icon: Wifi, 
    color: '#a6e3a1',
    description: 'Local network (fastest)'
  },
  { 
    id: 'relay', 
    name: 'Relay', 
    icon: Globe, 
    color: '#89b4fa',
    description: 'Cloud relay (NAT traversal)'
  },
  { 
    id: 'ble', 
    name: 'BLE', 
    icon: Bluetooth, 
    color: '#cba6f7',
    description: 'Bluetooth Low Energy'
  },
  { 
    id: 'wifi_direct', 
    name: 'WiFi Direct', 
    icon: Radio, 
    color: '#fab387',
    description: 'Peer-to-peer WiFi'
  },
  { 
    id: 'matter', 
    name: 'Matter', 
    icon: Activity, 
    color: '#f9e2af',
    description: 'Smart home protocol'
  },
];

export function TransportStatus({ wsData }) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchStatus = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/transports`);
      if (!response.ok) throw new Error('Failed to fetch transport status');
      const data = await response.json();
      setStatus(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 15000); // Refresh every 15s
    return () => clearInterval(interval);
  }, [fetchStatus]);

  if (loading) {
    return (
      <div className="transport-status loading">
        <RefreshCw className="spin" size={24} />
        <span>Loading transport status...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="transport-status error">
        <AlertTriangle size={24} />
        <span>{error}</span>
        <button onClick={fetchStatus}>Retry</button>
      </div>
    );
  }

  const enabled = status?.enabled || {};
  const transportStatus = status?.status || {};
  const peersByTransport = status?.peers_by_transport || {};

  return (
    <div className="transport-status">
      <div className="transport-header">
        <h3>
          <Zap size={20} />
          Multi-Transport Status
        </h3>
        <button className="refresh-btn" onClick={fetchStatus}>
          <RefreshCw size={16} />
        </button>
      </div>

      <div className="transport-philosophy">
        <span className="philosophy-text">
          Connect ALL • Use BEST • Failover INSTANT
        </span>
      </div>

      <div className="transports-grid">
        {TRANSPORTS.map((transport) => {
          const Icon = transport.icon;
          const isEnabled = enabled[transport.id];
          const state = transportStatus[transport.id];
          const peers = peersByTransport[transport.id] || [];
          const isConnected = state?.state === 'connected' || state?.state === 'active';

          return (
            <div 
              key={transport.id}
              className={`transport-card ${isEnabled ? 'enabled' : 'disabled'} ${isConnected ? 'connected' : ''}`}
            >
              <div 
                className="transport-icon"
                style={{ 
                  backgroundColor: isEnabled ? transport.color + '25' : undefined,
                  borderColor: isConnected ? transport.color : undefined
                }}
              >
                <Icon 
                  size={24} 
                  style={{ color: isEnabled ? transport.color : undefined }}
                />
              </div>

              <div className="transport-info">
                <div className="transport-name">
                  {transport.name}
                  <span className={`status-dot ${isConnected ? 'active' : isEnabled ? 'idle' : 'disabled'}`} />
                </div>
                <div className="transport-desc">{transport.description}</div>
              </div>

              <div className="transport-meta">
                {isEnabled ? (
                  <>
                    <div className="meta-row">
                      <Users size={14} />
                      <span>{peers.length} peers</span>
                    </div>
                    {state?.state && (
                      <div className={`state-badge ${state.state}`}>
                        {state.state === 'connected' || state.state === 'active' ? (
                          <Check size={12} />
                        ) : (
                          <X size={12} />
                        )}
                        {state.state}
                      </div>
                    )}
                  </>
                ) : (
                  <div className="state-badge disabled">
                    <X size={12} />
                    Disabled
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {status?.routing && (
        <div className="routing-breakdown">
          <h4>Transport Routes</h4>
          <div className="routes-by-transport">
            {Object.entries(status.routing).map(([transport, data]) => (
              <div key={transport} className="transport-route-info">
                <span className="transport-label">{transport}</span>
                <span className="route-count">{data.route_count} routes</span>
                <span className="avg-latency">{Math.round(data.avg_latency_ms)}ms avg</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {status?.stats && (
        <div className="transport-stats">
          <div className="stat">
            <span className="stat-value">{status.stats.messages_sent || 0}</span>
            <span className="stat-label">Sent</span>
          </div>
          <div className="stat">
            <span className="stat-value">{status.stats.messages_received || 0}</span>
            <span className="stat-label">Received</span>
          </div>
          <div className="stat">
            <span className="stat-value">{status.stats.failovers || 0}</span>
            <span className="stat-label">Failovers</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default TransportStatus;
