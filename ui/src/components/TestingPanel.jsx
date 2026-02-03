import React, { useState, useEffect } from 'react';
import { 
  PlayCircle, 
  RefreshCw, 
  Cpu, 
  Wifi, 
  Camera, 
  Mic, 
  MapPin,
  Zap,
  Clock,
  DollarSign,
  CheckCircle,
  XCircle,
  ChevronDown,
  ChevronUp
} from 'lucide-react';

export function TestingPanel() {
  const [nodes, setNodes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState(null);
  const [expandedNodes, setExpandedNodes] = useState({});
  const [testPrompt, setTestPrompt] = useState('Hello! What model are you?');
  const [testResults, setTestResults] = useState({});
  const [testingNode, setTestingNode] = useState(null);

  const fetchNodes = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/mesh/topology');
      if (!response.ok) throw new Error('Failed to fetch nodes');
      const data = await response.json();
      setNodes(data.nodes || []);
    } catch (err) {
      console.error('Error fetching nodes:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNodes();
    const interval = setInterval(fetchNodes, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, []);

  const toggleNode = (nodeId) => {
    setExpandedNodes(prev => ({ ...prev, [nodeId]: !prev[nodeId] }));
  };

  const testLLM = async (nodeId, model = null) => {
    setTestingNode(nodeId);
    const startTime = Date.now();
    
    try {
      const response = await fetch('/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: model || 'llama3.2',
          messages: [{ role: 'user', content: testPrompt }],
          max_tokens: 100
        })
      });
      
      const data = await response.json();
      const latency = Date.now() - startTime;
      
      setTestResults(prev => ({
        ...prev,
        [nodeId]: {
          success: true,
          type: 'llm',
          latency,
          response: data.choices?.[0]?.message?.content || 'No response',
          model: data.model || model,
          tokens: data.usage?.total_tokens
        }
      }));
    } catch (err) {
      setTestResults(prev => ({
        ...prev,
        [nodeId]: { success: false, type: 'llm', error: err.message }
      }));
    } finally {
      setTestingNode(null);
    }
  };

  const testCapability = async (nodeId, capType) => {
    setTestingNode(`${nodeId}-${capType}`);
    const startTime = Date.now();
    
    try {
      let endpoint, body;
      
      switch (capType) {
        case 'camera':
          endpoint = `/api/execute`;
          body = { intent: 'take a photo', target_node: nodeId };
          break;
        case 'location':
          endpoint = `/api/execute`;
          body = { intent: 'get location', target_node: nodeId };
          break;
        default:
          throw new Error(`Unknown capability: ${capType}`);
      }
      
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      
      const data = await response.json();
      const latency = Date.now() - startTime;
      
      setTestResults(prev => ({
        ...prev,
        [`${nodeId}-${capType}`]: {
          success: data.success,
          type: capType,
          latency,
          data: data.data
        }
      }));
    } catch (err) {
      setTestResults(prev => ({
        ...prev,
        [`${nodeId}-${capType}`]: { success: false, type: capType, error: err.message }
      }));
    } finally {
      setTestingNode(null);
    }
  };

  const testPing = async (nodeId) => {
    setTestingNode(`${nodeId}-ping`);
    const startTime = Date.now();
    
    try {
      // Simple ping - just hit the health endpoint through routing
      const response = await fetch('/api/health');
      const latency = Date.now() - startTime;
      
      setTestResults(prev => ({
        ...prev,
        [`${nodeId}-ping`]: { success: true, type: 'ping', latency }
      }));
    } catch (err) {
      setTestResults(prev => ({
        ...prev,
        [`${nodeId}-ping`]: { success: false, type: 'ping', error: err.message }
      }));
    } finally {
      setTestingNode(null);
    }
  };

  const getCapabilityIcon = (cap) => {
    if (cap.includes('llm') || cap.includes('model')) return <Cpu size={14} />;
    if (cap.includes('camera')) return <Camera size={14} />;
    if (cap.includes('voice') || cap.includes('mic')) return <Mic size={14} />;
    if (cap.includes('location') || cap.includes('gps')) return <MapPin size={14} />;
    return <Zap size={14} />;
  };

  return (
    <div className="panel testing-panel">
      <div className="panel-header">
        <h2><PlayCircle size={20} /> Inter-Node Testing</h2>
        <button className="refresh-btn" onClick={fetchNodes} disabled={loading}>
          <RefreshCw size={16} className={loading ? 'spinning' : ''} />
        </button>
      </div>

      <div className="test-prompt-section">
        <label>Test Prompt:</label>
        <input
          type="text"
          value={testPrompt}
          onChange={(e) => setTestPrompt(e.target.value)}
          placeholder="Enter prompt for LLM testing..."
        />
      </div>

      <div className="nodes-list">
        {nodes.map(node => (
          <div key={node.id} className="node-card">
            <div 
              className="node-header"
              onClick={() => toggleNode(node.id)}
            >
              <div className="node-info">
                <div className="node-icon">
                  {node.type === 'llm' ? <Cpu size={20} /> : <Wifi size={20} />}
                </div>
                <div className="node-details">
                  <div className="node-name">
                    {node.name}
                    {node.isLeader && <span className="leader-badge">Leader</span>}
                  </div>
                  <div className="node-id">{node.id}</div>
                </div>
              </div>
              <div className="node-cost">
                <DollarSign size={14} />
                {node.cost?.toFixed(2) || 'N/A'}
              </div>
              <div className="expand-icon">
                {expandedNodes[node.id] ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </div>
            </div>

            {expandedNodes[node.id] && (
              <div className="node-expanded">
                <div className="capabilities-section">
                  <h4>Capabilities</h4>
                  <div className="capability-list">
                    {(node.tools || []).slice(0, 10).map(cap => (
                      <span key={cap} className="capability-tag">
                        {getCapabilityIcon(cap)}
                        {cap}
                      </span>
                    ))}
                    {(node.tools || []).length > 10 && (
                      <span className="capability-tag more">
                        +{node.tools.length - 10} more
                      </span>
                    )}
                  </div>
                </div>

                <div className="test-buttons">
                  <button
                    className="test-btn"
                    onClick={() => testPing(node.id)}
                    disabled={testingNode === `${node.id}-ping`}
                  >
                    {testingNode === `${node.id}-ping` 
                      ? <RefreshCw size={14} className="spinning" />
                      : <Wifi size={14} />
                    }
                    Ping
                  </button>
                  
                  {(node.tools || []).some(t => t.includes('llm') || t.includes('model')) && (
                    <button
                      className="test-btn primary"
                      onClick={() => testLLM(node.id)}
                      disabled={testingNode === node.id}
                    >
                      {testingNode === node.id 
                        ? <RefreshCw size={14} className="spinning" />
                        : <Cpu size={14} />
                      }
                      Test LLM
                    </button>
                  )}
                  
                  {(node.tools || []).some(t => t.includes('camera')) && (
                    <button
                      className="test-btn"
                      onClick={() => testCapability(node.id, 'camera')}
                      disabled={testingNode === `${node.id}-camera`}
                    >
                      <Camera size={14} />
                      Camera
                    </button>
                  )}
                  
                  {(node.tools || []).some(t => t.includes('location')) && (
                    <button
                      className="test-btn"
                      onClick={() => testCapability(node.id, 'location')}
                      disabled={testingNode === `${node.id}-location`}
                    >
                      <MapPin size={14} />
                      Location
                    </button>
                  )}
                </div>

                {/* Test Results */}
                {Object.entries(testResults)
                  .filter(([key]) => key.startsWith(node.id))
                  .map(([key, result]) => (
                    <div key={key} className={`test-result ${result.success ? 'success' : 'error'}`}>
                      <div className="result-header">
                        {result.success 
                          ? <CheckCircle size={16} className="success-icon" />
                          : <XCircle size={16} className="error-icon" />
                        }
                        <span className="result-type">{result.type}</span>
                        {result.latency && (
                          <span className="result-latency">
                            <Clock size={12} /> {result.latency}ms
                          </span>
                        )}
                      </div>
                      {result.success ? (
                        <div className="result-content">
                          {result.type === 'llm' && (
                            <>
                              <div className="model-info">Model: {result.model}</div>
                              <div className="response">{result.response}</div>
                              {result.tokens && (
                                <div className="tokens">Tokens: {result.tokens}</div>
                              )}
                            </>
                          )}
                          {result.type === 'ping' && <span>✓ Node reachable</span>}
                          {result.data && (
                            <pre>{JSON.stringify(result.data, null, 2)}</pre>
                          )}
                        </div>
                      ) : (
                        <div className="result-error">{result.error}</div>
                      )}
                    </div>
                  ))
                }

                {node.costFactors && (
                  <div className="cost-factors">
                    <h4>Cost Factors</h4>
                    <div className="factors-grid">
                      <div className="factor">
                        <span>Battery</span>
                        <span>{(node.costFactors.battery_level * 100).toFixed(0)}%</span>
                      </div>
                      <div className="factor">
                        <span>CPU Load</span>
                        <span>{(node.costFactors.cpu_load * 100).toFixed(0)}%</span>
                      </div>
                      <div className="factor">
                        <span>Memory</span>
                        <span>{(node.costFactors.memory_pressure * 100).toFixed(0)}%</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {nodes.length === 0 && !loading && (
          <div className="empty-state">
            <Wifi size={48} />
            <p>No nodes connected</p>
            <p className="hint">Waiting for mesh peers to connect...</p>
          </div>
        )}
      </div>

      <style>{`
        .testing-panel {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        
        .panel-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        
        .refresh-btn {
          padding: 8px;
          border: 1px solid #333;
          border-radius: 4px;
          background: transparent;
          color: #888;
          cursor: pointer;
        }
        
        .spinning {
          animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        
        .test-prompt-section {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        
        .test-prompt-section label {
          font-size: 12px;
          color: #888;
        }
        
        .test-prompt-section input {
          padding: 10px 12px;
          border: 1px solid #333;
          border-radius: 4px;
          background: transparent;
          color: #fff;
          font-size: 14px;
        }
        
        .nodes-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        
        .node-card {
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid #333;
          border-radius: 8px;
          overflow: hidden;
        }
        
        .node-header {
          display: flex;
          align-items: center;
          padding: 16px;
          cursor: pointer;
          transition: background 0.2s;
        }
        
        .node-header:hover {
          background: rgba(255, 255, 255, 0.02);
        }
        
        .node-info {
          flex: 1;
          display: flex;
          align-items: center;
          gap: 12px;
        }
        
        .node-icon {
          width: 40px;
          height: 40px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(124, 58, 237, 0.2);
          border-radius: 8px;
          color: #a78bfa;
        }
        
        .node-name {
          font-weight: 600;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        
        .leader-badge {
          font-size: 10px;
          padding: 2px 6px;
          background: rgba(76, 175, 80, 0.2);
          color: #4caf50;
          border-radius: 4px;
        }
        
        .node-id {
          font-size: 12px;
          color: #666;
          font-family: monospace;
        }
        
        .node-cost {
          display: flex;
          align-items: center;
          gap: 4px;
          font-size: 14px;
          color: #888;
          margin-right: 16px;
        }
        
        .expand-icon {
          color: #666;
        }
        
        .node-expanded {
          padding: 16px;
          border-top: 1px solid #333;
          background: rgba(0, 0, 0, 0.2);
        }
        
        .capabilities-section {
          margin-bottom: 16px;
        }
        
        .capabilities-section h4 {
          font-size: 12px;
          color: #888;
          margin-bottom: 8px;
        }
        
        .capability-list {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }
        
        .capability-tag {
          display: flex;
          align-items: center;
          gap: 4px;
          font-size: 11px;
          padding: 4px 8px;
          background: rgba(124, 58, 237, 0.2);
          border-radius: 4px;
          color: #a78bfa;
        }
        
        .capability-tag.more {
          background: rgba(255, 255, 255, 0.1);
          color: #888;
        }
        
        .test-buttons {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
          margin-bottom: 16px;
        }
        
        .test-btn {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 8px 12px;
          border: 1px solid #333;
          border-radius: 4px;
          background: transparent;
          color: #888;
          cursor: pointer;
          transition: all 0.2s;
        }
        
        .test-btn:hover:not(:disabled) {
          border-color: #555;
          color: #fff;
        }
        
        .test-btn.primary {
          background: #7c3aed;
          border-color: #7c3aed;
          color: white;
        }
        
        .test-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        
        .test-result {
          padding: 12px;
          border-radius: 4px;
          margin-bottom: 8px;
        }
        
        .test-result.success {
          background: rgba(76, 175, 80, 0.1);
          border: 1px solid rgba(76, 175, 80, 0.3);
        }
        
        .test-result.error {
          background: rgba(244, 67, 54, 0.1);
          border: 1px solid rgba(244, 67, 54, 0.3);
        }
        
        .result-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 8px;
        }
        
        .success-icon { color: #4caf50; }
        .error-icon { color: #f44336; }
        
        .result-type {
          font-weight: 600;
          text-transform: capitalize;
        }
        
        .result-latency {
          display: flex;
          align-items: center;
          gap: 4px;
          font-size: 12px;
          color: #888;
          margin-left: auto;
        }
        
        .result-content {
          font-size: 13px;
        }
        
        .model-info {
          font-size: 12px;
          color: #888;
          margin-bottom: 4px;
        }
        
        .response {
          padding: 8px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 4px;
          white-space: pre-wrap;
        }
        
        .tokens {
          font-size: 11px;
          color: #666;
          margin-top: 4px;
        }
        
        .result-error {
          color: #f44336;
        }
        
        .cost-factors {
          padding-top: 12px;
          border-top: 1px solid #333;
        }
        
        .cost-factors h4 {
          font-size: 12px;
          color: #888;
          margin-bottom: 8px;
        }
        
        .factors-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
        }
        
        .factor {
          display: flex;
          justify-content: space-between;
          font-size: 12px;
          padding: 6px 8px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 4px;
        }
        
        .factor span:first-child {
          color: #888;
        }
        
        .empty-state {
          text-align: center;
          padding: 40px;
          color: #666;
        }
        
        .empty-state svg {
          margin-bottom: 16px;
          opacity: 0.5;
        }
        
        .hint {
          font-size: 12px;
          color: #555;
        }
      `}</style>
    </div>
  );
}
