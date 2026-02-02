import React, { useState, useEffect } from 'react';
import { Link, Unlink, RefreshCw, Server, CheckCircle2, XCircle, Activity, Zap, Clock } from 'lucide-react';
import './IntegrationPanel.css';

export const IntegrationPanel = ({ wsData }) => {
  const [integrations, setIntegrations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [testingId, setTestingId] = useState(null);
  const [testResults, setTestResults] = useState({});
  const [customTestPrompt, setCustomTestPrompt] = useState('What is 2+2?');
  const [selectedModel, setSelectedModel] = useState('');
  const [showTestPanel, setShowTestPanel] = useState(false);

  const fetchIntegrations = async () => {
    setLoading(true);
    try {
      const response = await fetch('/v1/integrations');
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
    const interval = setInterval(fetchIntegrations, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    // Update from WebSocket
    if (wsData && wsData.type === 'integration_update') {
      fetchIntegrations();
    }
  }, [wsData]);

  const handleConnect = async (integration) => {
    // TODO: Implement connection logic
    console.log('Connect to:', integration.id);
  };

  const handleDisconnect = async (integration) => {
    // TODO: Implement disconnection logic
    console.log('Disconnect from:', integration.id);
  };

  const handleTest = async (integration, prompt, model) => {
    setTestingId(integration.id);
    
    try {
      const payload = {
        integration_id: integration.id,
        prompt: prompt || customTestPrompt || 'Hello! Can you count to 5?',
      };
      
      if (model) {
        payload.model = model;
      }
      
      const response = await fetch('/v1/integrations/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
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
      console.error('Test failed:', err);
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
                <div className="stat-value">{integration.total_model_count || integration.model_count || 0}</div>
                <div className="stat-label">Total Models</div>
              </div>
              {isLlamaFarm && integration.projects && (
                <div className="stat">
                  <div className="stat-value">{integration.projects.length}</div>
                  <div className="stat-label">Projects</div>
                </div>
              )}
              <div className="stat">
                <div className="stat-value">{integration.capabilities?.length || 0}</div>
                <div className="stat-label">Capabilities</div>
              </div>
              <div className="stat">
                <div className="stat-value">
                  <Activity size={16} className="pulse-icon" />
                </div>
                <div className="stat-label">Active</div>
              </div>
            </div>

            {/* LlamaFarm Projects Section */}
            {isLlamaFarm && integration.projects && integration.projects.length > 0 && (
              <div className="llamafarm-projects">
                <h4 className="section-title">📂 Projects</h4>
                <div className="projects-grid">
                  {integration.projects.map((project, idx) => (
                    <div key={idx} className="project-card">
                      <div className="project-name">{project.name}</div>
                      <div className="project-stats">
                        <span className="project-count">
                          {project.sub_project_count} sub-projects
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

            {/* LlamaFarm Specialized Models Section */}
            {isLlamaFarm && integration.specialized_models && Object.keys(integration.specialized_models).length > 0 && (
              <div className="llamafarm-specialized">
                <h4 className="section-title">🎯 Specialized Models</h4>
                <div className="specialized-grid">
                  {Object.entries(integration.specialized_models).map(([category, info]) => (
                    <div key={category} className={`specialized-card ${category}`}>
                      <div className="specialized-header">
                        <div className="specialized-icon">
                          {category === 'anomaly' && '🔍'}
                          {category === 'classifier' && '🏷️'}
                          {category === 'router' && '🔀'}
                          {category === 'drift' && '📊'}
                        </div>
                        <div className="specialized-name">{category}</div>
                      </div>
                      <div className="specialized-count">{info.count} models</div>
                      {info.samples && info.samples.length > 0 && (
                        <div className="specialized-samples">
                          {info.samples.slice(0, 2).map((sample, idx) => (
                            <div key={idx} className="sample-name">{sample}</div>
                          ))}
                          {info.count > 2 && (
                            <div className="sample-more">+{info.count - 2} more</div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Ollama Models Section */}
            {integration.ollama_models && integration.ollama_models.length > 0 && (
              <div className="integration-models">
                <h4 className="section-title">🦙 Ollama Models ({integration.ollama_model_count})</h4>
                <div className="models-list">
                  {integration.ollama_models.map((model, idx) => (
                    <span key={idx} className="model-tag">{model}</span>
                  ))}
                  {integration.ollama_model_count > integration.ollama_models.length && (
                    <span className="model-tag more">
                      +{integration.ollama_model_count - integration.ollama_models.length} more
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* Regular models for non-LlamaFarm */}
            {!isLlamaFarm && integration.models && integration.models.length > 0 && (
              <div className="integration-models">
                <div className="models-label">Available Models:</div>
                <div className="models-list">
                  {integration.models.map((model, idx) => (
                    <span key={idx} className="model-tag">{model}</span>
                  ))}
                  {integration.model_count > integration.models.length && (
                    <span className="model-tag more">
                      +{integration.model_count - integration.models.length} more
                    </span>
                  )}
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
          {isOnline ? (
            <>
              <button 
                className="action-button test"
                onClick={() => handleTest(integration)}
                disabled={isTesting}
              >
                <Zap size={16} />
                {isTesting ? 'Testing...' : 'Test'}
              </button>
              <button 
                className="action-button disconnect"
                onClick={() => handleDisconnect(integration)}
              >
                <Unlink size={16} />
                Disconnect
              </button>
            </>
          ) : (
            <button 
              className="action-button connect"
              onClick={() => handleConnect(integration)}
            >
              <Link size={16} />
              Connect
            </button>
          )}
        </div>

        {testResult && (
          <div className={`test-result ${testResult.success ? 'success' : 'error'}`}>
            <div className="test-result-header">
              <div className="test-result-status">
                {testResult.success ? (
                  <>
                    <CheckCircle2 size={16} />
                    Test Successful
                  </>
                ) : (
                  <>
                    <XCircle size={16} />
                    Test Failed
                  </>
                )}
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
                <div className="test-response-label">Response:</div>
                <div className="test-response-text">{testResult.response}</div>
                {testResult.model_used && (
                  <div className="test-model">Model: {testResult.model_used}</div>
                )}
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
        
        <button 
          className={`refresh-button ${loading ? 'spinning' : ''}`}
          onClick={fetchIntegrations}
          disabled={loading}
        >
          <RefreshCw size={20} />
          {loading ? 'Scanning...' : 'Refresh'}
        </button>
      </div>

      {lastUpdate && (
        <div className="last-update">
          Last updated: {lastUpdate.toLocaleTimeString()}
        </div>
      )}

      {/* Test Execution Panel */}
      <div className="test-execution-panel">
        <button 
          className="toggle-test-panel"
          onClick={() => setShowTestPanel(!showTestPanel)}
        >
          <Zap size={20} />
          {showTestPanel ? 'Hide' : 'Show'} Test Execution
        </button>
        
        {showTestPanel && (
          <div className="test-form fade-in">
            <h3>Test Execution</h3>
            <div className="form-group">
              <label>Prompt:</label>
              <textarea
                value={customTestPrompt}
                onChange={(e) => setCustomTestPrompt(e.target.value)}
                placeholder="Enter your test prompt..."
                rows={3}
              />
            </div>
            
            <div className="form-group">
              <label>Model (optional):</label>
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
              >
                <option value="">Auto (use default)</option>
                {integrations.flatMap(int => 
                  int.models?.map(model => (
                    <option key={`${int.id}-${model}`} value={model}>
                      {model} ({int.name})
                    </option>
                  )) || []
                )}
              </select>
            </div>
            
            <div className="test-actions">
              {integrations.filter(i => i.connected).map(integration => (
                <button
                  key={integration.id}
                  className="execute-button"
                  onClick={() => handleTest(integration, customTestPrompt, selectedModel)}
                  disabled={testingId === integration.id || !customTestPrompt}
                >
                  {testingId === integration.id ? 'Testing...' : `Execute on ${integration.name}`}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

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
          Atmosphere automatically discovers and connects to local LLM backends:
        </p>
        <ul>
          <li><strong>LlamaFarm</strong> - Multi-model Ollama backend (port 14345)</li>
          <li><strong>Ollama</strong> - Direct Ollama access (port 11434)</li>
          <li><strong>Custom Backends</strong> - Any mDNS-discoverable service</li>
        </ul>
      </div>
    </div>
  );
};
