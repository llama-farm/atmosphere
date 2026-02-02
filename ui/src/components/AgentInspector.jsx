import React, { useState, useEffect } from 'react';
import { Play, Pause, RefreshCw, Activity } from 'lucide-react';
import './AgentInspector.css';

export const AgentInspector = ({ wsData }) => {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchAgents = async () => {
    try {
      const response = await fetch('/v1/agents');
      const data = await response.json();
      setAgents(data.agents || []);
    } catch (err) {
      console.error('Failed to fetch agents:', err);
      // Demo data
      setAgents([
        { id: 'agent-1', name: 'Vision Agent', status: 'running', capabilities: ['vision', 'ocr'], uptime: 1234567 },
        { id: 'agent-2', name: 'Code Agent', status: 'running', capabilities: ['python', 'javascript'], uptime: 2345678 },
        { id: 'agent-3', name: 'Search Agent', status: 'suspended', capabilities: ['web-search', 'scraping'], uptime: 456789 },
        { id: 'agent-4', name: 'Data Agent', status: 'running', capabilities: ['database', 'analytics'], uptime: 3456789 },
      ]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAgents();
  }, []);

  const handleToggle = async (agentId, currentStatus) => {
    const newStatus = currentStatus === 'running' ? 'suspended' : 'running';
    
    try {
      await fetch(`/v1/agents/${agentId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      });
      
      setAgents(prev => prev.map(agent => 
        agent.id === agentId ? { ...agent, status: newStatus } : agent
      ));
    } catch (err) {
      console.error('Failed to toggle agent:', err);
      // Optimistic update for demo
      setAgents(prev => prev.map(agent => 
        agent.id === agentId ? { ...agent, status: newStatus } : agent
      ));
    }
  };

  const formatUptime = (seconds) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
  };

  if (loading) {
    return (
      <div className="agent-inspector">
        <div className="loading-spinner">
          <RefreshCw className="spin" size={32} />
          <p>Loading agents...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="agent-inspector fade-in">
      <div className="inspector-header">
        <h1>Agent Inspector</h1>
        <button onClick={fetchAgents} className="refresh-button">
          <RefreshCw size={18} />
          Refresh
        </button>
      </div>

      <div className="agent-grid">
        {agents.map(agent => (
          <div key={agent.id} className="agent-card slide-in">
            <div className="agent-header">
              <div className="agent-info">
                <div className="agent-name">{agent.name}</div>
                <div className={`agent-status status-${agent.status}`}>
                  <div className="status-dot"></div>
                  {agent.status}
                </div>
              </div>
              <button
                onClick={() => handleToggle(agent.id, agent.status)}
                className={`control-button ${agent.status === 'running' ? 'pause' : 'play'}`}
                title={agent.status === 'running' ? 'Suspend' : 'Wake'}
              >
                {agent.status === 'running' ? (
                  <Pause size={20} />
                ) : (
                  <Play size={20} />
                )}
              </button>
            </div>

            <div className="agent-stats">
              <div className="stat">
                <Activity size={16} />
                <span>Uptime: {formatUptime(agent.uptime)}</span>
              </div>
              <div className="stat">
                <span className="capability-count">
                  {agent.capabilities.length} capabilities
                </span>
              </div>
            </div>

            <div className="agent-capabilities">
              {agent.capabilities.map((cap, i) => (
                <div key={i} className="capability-tag">
                  {cap}
                </div>
              ))}
            </div>

            {agent.status === 'running' && (
              <div className="agent-activity">
                <div className="activity-bar">
                  <div className="activity-fill pulse"></div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {agents.length === 0 && (
        <div className="empty-state">
          <p>No agents found</p>
        </div>
      )}
    </div>
  );
};
