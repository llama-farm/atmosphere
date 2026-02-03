import React, { useState, useEffect } from 'react';
import { Link, Unlink, RefreshCw, Server, CheckCircle2, XCircle, Activity, Zap, Clock, Wifi, Cloud } from 'lucide-react';
import './IntegrationPanel.css';

export const IntegrationPanel = ({ wsData }) => {
  const [backends, setBackends] = useState([]);
  const [meshStatus, setMeshStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [testingId, setTestingId] = useState(null);
  const [testResults, setTestResults] = useState({});

  const fetchStatus = async () => {
    setLoading(true);
    try {
      // Get Atmosphere's own status (not LlamaFarm's full catalog)
      const response = await fetch('/api');
      const data = await response.json();
      
      setMeshStatus({
        node_id: data.node_id,
        node_name: data.node_name,
        mesh_id: data.mesh_id,
        mesh_name: data.mesh_name,
        capabilities: data.capabilities || [],
        peers: data.peers || 0,
        running: data.running
      });

      // Get configured backends from Atmosphere config
      const backendsResponse = await fetch('/api/backends');
      const backendsData = await backendsResponse.json();
      setBackends(backendsData.backends || []);
      
      setLastUpdate(new Date());
    } catch (err) {
      console.error('Failed to fetch status:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (wsData && wsData.type === 'status_update') {
      fetchStatus();
    }
  }, [wsData]);

  const handleTest = async (backendId) => {
    setTestingId(backendId);
    try {
      const response = await fetch('/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: 'auto',
          messages: [{ role: 'user', content: 'Hello! Count to 3.' }],
          max_tokens: 50
        }),
      });
      const data = await response.json();
      
      setTestResults(prev => ({
        ...prev,
        [backendId]: {
          success: !data.error,
          response: data.choices?.[0]?.message?.content || data.error,
          timestamp: new Date(),
        }
      }));
    } catch (err) {
      setTestResults(prev => ({
        ...prev,
        [backendId]: {
          success: false,
          error: err.message,
          timestamp: new Date(),
        }
      }));
    } finally {
      setTestingId(null);
    }
  };

  const BackendCard = ({ backend }) => {
    const isOnline = backend.status === 'healthy';
    const testResult = testResults[backend.id];
    const isTesting = testingId === backend.id;

    return (
      <div className={`integration-card ${isOnline ? 'online' : 'offline'}`}>
        <div className="integration-header">
          <div className="integration-icon" style={{ 
            background: isOnline ? 'var(--accent-success)22' : 'var(--accent-error)22'
          }}>
            <Server size={24} color={isOnline ? 'var(--accent-success)' : 'var(--accent-error)'} />
          </div>
          
          <div className="integration-info">
            <h3 className="integration-name">{backend.name || backend.type}</h3>
            <div className="integration-address">{backend.host}:{backend.port}</div>
          </div>

          <div className={`integration-status ${isOnline ? 'healthy' : 'offline'}`}>
            {isOnline ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
            <span>{isOnline ? 'Connected' : 'Offline'}</span>
          </div>
        </div>

        {backend.capabilities && backend.capabilities.length > 0 && (
          <div className="integration-capabilities">
            {backend.capabilities.map((cap, idx) => (
              <span key={idx} className="capability-badge">{cap}</span>
            ))}
          </div>
        )}

        <div className="integration-actions">
          <button 
            className="action-button test"
            onClick={() => handleTest(backend.id)}
            disabled={isTesting || !isOnline}
          >
            <Zap size={16} />
            {isTesting ? 'Testing...' : 'Test'}
          </button>
        </div>

        {testResult && (
          <div className={`test-result ${testResult.success ? 'success' : 'error'}`}>
            <div className="test-result-status">
              {testResult.success ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
              {testResult.success ? 'Success' : 'Failed'}
            </div>
            <div className="test-response-text">
              {testResult.response || testResult.error}
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="integration-panel fade-in">
      <div className="panel-header">
        <div className="header-left">
          <Cloud size={32} />
          <div>
            <h1>Mesh Status</h1>
            <p className="panel-subtitle">Atmosphere node and backends</p>
          </div>
        </div>
        
        <button 
          className={`refresh-button ${loading ? 'spinning' : ''}`}
          onClick={fetchStatus}
          disabled={loading}
        >
          <RefreshCw size={20} />
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {/* Node Status */}
      {meshStatus && (
        <div className="mesh-status-card">
          <div className="mesh-header">
            <Wifi size={24} />
            <div>
              <h2>{meshStatus.node_name || 'Local Node'}</h2>
              <span className="node-id">{meshStatus.node_id}</span>
            </div>
            <div className={`status-badge ${meshStatus.running ? 'online' : 'offline'}`}>
              {meshStatus.running ? 'Online' : 'Offline'}
            </div>
          </div>

          {meshStatus.mesh_name && (
            <div className="mesh-info">
              <span className="mesh-label">Mesh:</span>
              <span className="mesh-name">{meshStatus.mesh_name}</span>
              <span className="mesh-id">({meshStatus.mesh_id})</span>
              <span className="peer-count">{meshStatus.peers} peers</span>
            </div>
          )}

          {meshStatus.capabilities && meshStatus.capabilities.length > 0 && (
            <div className="capabilities-section">
              <h4>Exposed Capabilities</h4>
              <div className="capabilities-list">
                {meshStatus.capabilities.map((cap, idx) => (
                  <span key={idx} className="capability-tag">{cap}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Backends */}
      <div className="section-header">
        <h3><Server size={20} /> Backends</h3>
      </div>

      <div className="integrations-grid">
        {backends.length === 0 ? (
          <div className="empty-state">
            <Server size={48} />
            <p>No backends configured</p>
          </div>
        ) : (
          backends.map(backend => (
            <BackendCard key={backend.id} backend={backend} />
          ))
        )}
      </div>

      {lastUpdate && (
        <div className="last-update">
          Last updated: {lastUpdate.toLocaleTimeString()}
        </div>
      )}
    </div>
  );
};
