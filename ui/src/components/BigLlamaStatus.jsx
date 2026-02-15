import React from 'react';
import { Cloud, CloudOff, Database, Users, Wifi, WifiOff } from 'lucide-react';
import './BigLlamaStatus.css';

export const BigLlamaStatus = ({ bigLlamaStatus, isConnected }) => {
  if (!isConnected) {
    return (
      <div className="bigllama-panel disconnected">
        <div className="panel-header">
          <CloudOff size={20} />
          <h2>BigLlama</h2>
          <span className="status-badge offline">Offline</span>
        </div>
        <div className="panel-empty">
          <CloudOff size={48} opacity={0.2} />
          <p>Daemon not connected</p>
        </div>
      </div>
    );
  }

  const status = bigLlamaStatus || {};
  const connected = status.connected || false;
  const mode = status.mode || 'unknown'; // 'cloud', 'lan', 'offline'
  const persistentDocs = status.persistent_docs || 0;
  const connectedClients = status.connected_clients || 0;
  const relayUrl = status.relay_url || 'Not configured';
  const peerId = status.peer_id || 'Unknown';

  return (
    <div className="bigllama-panel">
      <div className="panel-header">
        <Cloud size={20} />
        <h2>BigLlama Status</h2>
        <span className={`status-badge ${connected ? 'online' : 'offline'}`}>
          {connected ? `Connected (${mode})` : 'Disconnected'}
        </span>
      </div>

      <div className="bigllama-grid">
        <div className="info-card">
          <div className="info-icon">
            {mode === 'cloud' ? (
              <Cloud size={24} color="#3b82f6" />
            ) : mode === 'lan' ? (
              <Wifi size={24} color="#10b981" />
            ) : (
              <WifiOff size={24} color="#6b7280" />
            )}
          </div>
          <div className="info-content">
            <div className="info-label">Mode</div>
            <div className="info-value">{mode.toUpperCase()}</div>
          </div>
        </div>

        <div className="info-card">
          <div className="info-icon">
            <Database size={24} color="#8b5cf6" />
          </div>
          <div className="info-content">
            <div className="info-label">Persistent Docs</div>
            <div className="info-value">{persistentDocs}</div>
          </div>
        </div>

        <div className="info-card">
          <div className="info-icon">
            <Users size={24} color="#10b981" />
          </div>
          <div className="info-content">
            <div className="info-label">Connected Clients</div>
            <div className="info-value">{connectedClients}</div>
          </div>
        </div>
      </div>

      <div className="bigllama-details">
        <div className="detail-row">
          <span className="detail-label">Peer ID:</span>
          <span className="detail-value">{peerId.substring(0, 16)}...</span>
        </div>
        <div className="detail-row">
          <span className="detail-label">Relay URL:</span>
          <span className="detail-value">{relayUrl}</span>
        </div>
        {status.last_sync && (
          <div className="detail-row">
            <span className="detail-label">Last Sync:</span>
            <span className="detail-value">
              {new Date(status.last_sync).toLocaleString()}
            </span>
          </div>
        )}
      </div>

      {status.error && (
        <div className="bigllama-error">
          <AlertCircle size={16} />
          <span>{status.error}</span>
        </div>
      )}
    </div>
  );
};
