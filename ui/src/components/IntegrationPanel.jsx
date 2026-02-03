import React, { useState, useEffect } from 'react';
import { Link, Unlink, RefreshCw, Server, CheckCircle2, XCircle, Activity, Zap, Clock, Wifi, Cloud, Filter } from 'lucide-react';
import './IntegrationPanel.css';

export const IntegrationPanel = ({ wsData }) => {
  const [integrations, setIntegrations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [testingId, setTestingId] = useState(null);
  const [testResults, setTestResults] = useState({});
  const [showAllProjects, setShowAllProjects] = useState(false); // Default: filtered view

  const fetchIntegrations = async () => {
    setLoading(true);
    try {
      // Use filtered endpoint (only "discoverable" namespace by default)
      const url = showAllProjects ? '/api/integrations?all=true' : '/api/integrations';
      const response = await fetch(url);
      const data = await response.json();
      setIntegrations(data.integrations || []);
      setLastUpdate(new Date(data.timestamp * 1000));
    } catch (err) {
      console.error('Failed to fetch integrations:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIntegrations();
    const interval = setInterval(fetchIntegrations, 30000);
    return () => clearInterval(interval);
  }, [showAllProjects]);

  useEffect(() => {
    if (wsData && wsData.type === 'integration_update') {
      fetchIntegrations();
    }
  }, [wsData]);

  const handleTest = async (integration, prompt) => {
    setTestingId(integration.id);
    
    try {
      const response = await fetch('/v1/integrations/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          integration_id: integration.id,
          prompt: prompt || 'Hello! Can you count to 3?',
        }),
      });

      const data = await response.json();
      
      setTestResults(prev => ({
        ...prev,
        [integration.id]: {
          success: data.success,
          response: data.response,
          error: data.error,
          latency_ms: data.latency_ms,
          model_used: data.model_used,
          timestamp: new Date(),
        }
      }));
    } catch (err) {
      setTestResults(prev => ({
        ...prev,
        [integration.id]: {
          success: false,
          error: err.message,
          timestamp: new Date(),
        }
      }));
    } finally {
      setTestingId(null);
    }
  };

  const IntegrationCard = ({ integration }) => {
    const isOnline = integration.status === 'healthy' && integration.connected;
    const statusColor = isOnline ? 'var(--accent-success)' : 'var(--accent-error)';
    const isTesting = testingId === integration.id;
    const testResult = testResults[integration.id];
    const isLlamaFarm = integration.id === 'llamafarm';

    return (
      <div className={`integration-card ${isOnline ? 'online' : 'offline'} ${isLlamaFarm ? 'llamafarm' : ''}`}>
        <div className="integration-header">
          <div className="integration-icon" style={{ 
            background: `linear-gradient(135deg, ${statusColor}22, ${statusColor}44)` 
          }}>
            <Server size={28} color={statusColor} />
          </div>
          
          <div className="integration-info">
            <h3 className="integration-name">{integration.name}</h3>
            <div className="integration-address">{integration.address}</div>
          </div>

          <div className={`integration-status ${isOnline ? 'healthy' : 'offline'}`}>
            {isOnline ? (
              <>
                <CheckCircle2 size={20} />
                <span>Healthy</span>
              </>
            ) : (
              <>
                <XCircle size={20} />
                <span>Offline</span>
              </>
            )}
          </div>
        </div>

        {isOnline && (
          <>
            <div className="integration-stats">
              <div className="stat">
                <div className="stat-value">{integration.model_count || 0}</div>
                <div className="stat-label">Models</div>
              </div>
              {isLlamaFarm && integration.projects && (
                <div className="stat">
                  <div className="stat-value">{integration.projects.length}</div>
                  <div className="stat-label">Namespaces</div>
                </div>
              )}
              <div className="stat">
                <div className="stat-value">{integration.capabilities?.length || 0}</div>
                <div className="stat-label">Capabilities</div>
              </div>
            </div>

            {/* LlamaFarm Projects/Namespaces */}
            {isLlamaFarm && integration.projects && integration.projects.length > 0 && (
              <div className="llamafarm-projects">
                <h4 className="section-title">
                  📂 {showAllProjects ? 'All Namespaces' : 'Exposed Namespace'}
                </h4>
                <div className="projects-grid">
                  {integration.projects.map((project, idx) => (
                    <div key={idx} className="project-card">
                      <div className="project-name">{project.name}</div>
                      <div className="project-stats">
                        <span className="project-count">
                          {project.sub_project_count} projects
                        </span>
                      </div>
                      {project.sub_projects && project.sub_projects.length > 0 && (
                        <div className="sub-projects">
                          {project.sub_projects.slice(0, 3).map((sub, subIdx) => (
                            <span key={subIdx} className="sub-project-tag">{sub}</span>
                          ))}
                          {project.sub_project_count > 3 && (
                            <span className="sub-project-tag more">+{project.sub_project_count - 3}</span>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {integration.capabilities && integration.capabilities.length > 0 && (
              <div className="integration-capabilities">
                {integration.capabilities.map((cap, idx) => (
                  <span key={idx} className="capability-badge">{cap}</span>
                ))}
              </div>
            )}
          </>
        )}

        <div className="integration-actions">
          {isOnline && (
            <button 
              className="action-button test"
              onClick={() => handleTest(integration)}
              disabled={isTesting}
            >
              <Zap size={16} />
              {isTesting ? 'Testing...' : 'Test'}
            </button>
          )}
        </div>

        {testResult && (
          <div className={`test-result ${testResult.success ? 'success' : 'error'}`}>
            <div className="test-result-header">
              <div className="test-result-status">
                {testResult.success ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
                {testResult.success ? 'Test Successful' : 'Test Failed'}
              </div>
              {testResult.latency_ms && (
                <div className="test-latency">
                  <Clock size={14} />
                  {testResult.latency_ms.toFixed(0)}ms
                </div>
              )}
            </div>
            
            {testResult.success ? (
              <div className="test-response">
                <div className="test-response-text">{testResult.response}</div>
              </div>
            ) : (
              <div className="test-error">{testResult.error}</div>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="integration-panel fade-in">
      <div className="panel-header">
        <div className="header-left">
          <Server size={32} />
          <div>
            <h1>Integrations</h1>
            <p className="panel-subtitle">Connected backends and services</p>
          </div>
        </div>
        
        <div className="header-actions">
          <button 
            className={`filter-button ${showAllProjects ? 'active' : ''}`}
            onClick={() => setShowAllProjects(!showAllProjects)}
            title={showAllProjects ? 'Showing all namespaces' : 'Showing only discoverable namespace'}
          >
            <Filter size={18} />
            {showAllProjects ? 'All' : 'Filtered'}
          </button>
          
          <button 
            className={`refresh-button ${loading ? 'spinning' : ''}`}
            onClick={fetchIntegrations}
            disabled={loading}
          >
            <RefreshCw size={20} />
            {loading ? 'Scanning...' : 'Refresh'}
          </button>
        </div>
      </div>

      {!showAllProjects && (
        <div className="filter-notice">
          <Filter size={16} />
          Showing only <strong>discoverable</strong> namespace (mesh-exposed capabilities)
        </div>
      )}

      {lastUpdate && (
        <div className="last-update">
          Last updated: {lastUpdate.toLocaleTimeString()}
        </div>
      )}

      <div className="integrations-grid">
        {integrations.length === 0 ? (
          <div className="empty-state">
            <Server size={64} />
            <h3>No integrations discovered</h3>
            <p>Start LlamaFarm or Ollama to see available backends</p>
          </div>
        ) : (
          integrations.map(integration => (
            <IntegrationCard key={integration.id} integration={integration} />
          ))
        )}
      </div>

      <div className="integration-info-panel">
        <h3>About Integrations</h3>
        <p>
          Atmosphere discovers local LLM backends and exposes their capabilities to the mesh.
          By default, only the <strong>discoverable</strong> namespace is shown.
        </p>
        <ul>
          <li><strong>Filtered View</strong> - Only mesh-exposed capabilities</li>
          <li><strong>All View</strong> - Full LlamaFarm catalog (for debugging)</li>
        </ul>
      </div>
    </div>
  );
};
