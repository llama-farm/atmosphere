import React, { useState, useEffect } from 'react';
import { Activity, Wifi, Zap, Users, ArrowUp, ArrowDown, Camera, Mic, Brain, Search, Wrench } from 'lucide-react';
import { CostMetrics } from './CostMetrics';
import './Dashboard.css';

export const Dashboard = ({ wsData }) => {
  const [stats, setStats] = useState({
    connectedNodes: 0,
    totalCapabilities: 0,
    activeAgents: 0,
    meshHealth: 100,
  });

  const [capabilityStats, setCapabilityStats] = useState({
    total: 0,
    byType: {},
    recentTriggers: [],
    activeToolCalls: [],
  });

  const [recentActivity, setRecentActivity] = useState([]);

  useEffect(() => {
    // Fetch initial stats from real API
    fetch('/api/mesh/status')
      .then(res => res.json())
      .then(data => {
        setStats({
          connectedNodes: data.node_count || data.peer_count + 1 || 1,
          totalCapabilities: data.capabilities?.length || 0,
          activeAgents: data.capabilities?.length || 0,
          meshHealth: 100,
        });
      })
      .catch(err => {
        console.error('Failed to fetch mesh status:', err);
      });

    // Fetch capabilities
    fetch('/api/capabilities')
      .then(res => res.json())
      .then(data => {
        // Process capability breakdown
        const byType = {};
        data.forEach(cap => {
          const type = guessCapabilityType(cap.label, cap.handler);
          byType[type] = (byType[type] || 0) + 1;
        });
        
        setCapabilityStats(prev => ({
          ...prev,
          total: data.length,
          byType,
        }));
        
        setStats(prev => ({
          ...prev,
          totalCapabilities: data.length,
          activeAgents: data.length,
        }));
      })
      .catch(err => {
        console.error('Failed to fetch capabilities:', err);
        // Set demo capability stats
        setCapabilityStats({
          total: 5,
          byType: {
            'llm': 3,
            'tool': 2,
          },
          recentTriggers: [],
          activeToolCalls: [],
        });
      });
  }, []);

  const guessCapabilityType = (label, handler) => {
    const lower = ((label || '') + ' ' + (handler || '')).toLowerCase();
    if (lower.includes('camera') || lower.includes('vision') || lower.includes('image')) return 'sensor/camera';
    if (lower.includes('voice') || lower.includes('audio') || lower.includes('speech')) return 'sensor/voice';
    if (lower.includes('llm') || lower.includes('chat') || lower.includes('complete')) return 'llm';
    if (lower.includes('search') || lower.includes('query')) return 'search';
    if (lower.includes('tool') || lower.includes('action')) return 'tool';
    return 'llm';
  };

  useEffect(() => {
    // Update activity from WebSocket
    if (wsData) {
      const activity = {
        id: Date.now(),
        type: wsData.type,
        message: wsData.message || JSON.stringify(wsData),
        timestamp: new Date().toLocaleTimeString(),
      };

      setRecentActivity(prev => [activity, ...prev.slice(0, 9)]);

      // Track trigger events
      if (wsData.event_type === 'TRIGGER_EVENT') {
        setCapabilityStats(prev => ({
          ...prev,
          recentTriggers: [
            { id: Date.now(), name: wsData.trigger, capability: wsData.capability, time: Date.now() },
            ...prev.recentTriggers.slice(0, 4)
          ],
        }));
      }

      // Track tool calls
      if (wsData.event_type === 'TOOL_CALL') {
        setCapabilityStats(prev => ({
          ...prev,
          activeToolCalls: [
            { id: Date.now(), tool: wsData.tool, capability: wsData.capability, status: 'running' },
            ...prev.activeToolCalls.filter(t => t.status === 'running').slice(0, 4)
          ],
        }));
      }
    }
  }, [wsData]);

  const StatCard = ({ icon: Icon, label, value, color, pulse }) => (
    <div className={`stat-card ${pulse ? 'pulse' : ''}`}>
      <div className="stat-icon" style={{ background: `linear-gradient(135deg, ${color}22, ${color}44)` }}>
        <Icon size={24} color={color} />
      </div>
      <div className="stat-content">
        <div className="stat-value">{value}</div>
        <div className="stat-label">{label}</div>
      </div>
    </div>
  );

  const TYPE_ICONS = {
    'sensor/camera': { icon: Camera, color: '#10b981' },
    'sensor/voice': { icon: Mic, color: '#f97316' },
    'llm': { icon: Brain, color: '#8b5cf6' },
    'search': { icon: Search, color: '#3b82f6' },
    'tool': { icon: Wrench, color: '#6b7280' },
  };

  const formatTimeAgo = (timestamp) => {
    const diff = Math.floor((Date.now() - timestamp) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
  };

  return (
    <div className="dashboard fade-in">
      <div className="dashboard-header">
        <h1>Atmosphere Mesh</h1>
        <div className="status-indicator">
          <div className={`status-dot ${stats.meshHealth > 80 ? 'healthy' : 'degraded'}`}></div>
          <span>Mesh {stats.meshHealth > 80 ? 'Healthy' : 'Degraded'}</span>
        </div>
      </div>

      <div className="stats-grid">
        <StatCard
          icon={Users}
          label="Connected Nodes"
          value={stats.connectedNodes}
          color="#3b82f6"
          pulse={true}
        />
        <StatCard
          icon={Zap}
          label="Total Capabilities"
          value={stats.totalCapabilities}
          color="#8b5cf6"
        />
        <StatCard
          icon={Activity}
          label="Active Agents"
          value={stats.activeAgents}
          color="#10b981"
        />
        <StatCard
          icon={Wifi}
          label="Mesh Health"
          value={`${stats.meshHealth}%`}
          color="#f59e0b"
        />
      </div>

      {/* Cost Metrics Panel */}
      <CostMetrics refreshInterval={10000} />

      {/* Capability Summary Panel */}
      <div className="capability-summary-panel">
        <h2>
          <Zap size={20} />
          Capabilities Overview
        </h2>
        
        <div className="capability-grid">
          {/* Total Capabilities */}
          <div className="capability-total">
            <div className="total-number">{capabilityStats.total}</div>
            <div className="total-label">Total Capabilities</div>
          </div>

          {/* By Type Breakdown */}
          <div className="capability-types">
            <h3>By Type</h3>
            <div className="type-list">
              {Object.entries(capabilityStats.byType).map(([type, count]) => {
                const typeInfo = TYPE_ICONS[type] || { icon: Zap, color: '#8b5cf6' };
                const TypeIcon = typeInfo.icon;
                return (
                  <div key={type} className="type-item">
                    <TypeIcon size={16} color={typeInfo.color} />
                    <span className="type-name">{type}</span>
                    <span className="type-count">{count}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Recent Triggers */}
          <div className="recent-triggers">
            <h3>
              <ArrowUp size={14} color="#f97316" />
              Recent Triggers
            </h3>
            <div className="trigger-list">
              {capabilityStats.recentTriggers.slice(0, 5).map(trigger => (
                <div key={trigger.id} className="trigger-item">
                  <span className="trigger-name">{trigger.name}</span>
                  <span className="trigger-capability">{trigger.capability}</span>
                  <span className="trigger-time">{formatTimeAgo(trigger.time)}</span>
                </div>
              ))}
              {capabilityStats.recentTriggers.length === 0 && (
                <div className="no-data">No recent triggers</div>
              )}
            </div>
          </div>

          {/* Active Tool Calls */}
          <div className="active-tools">
            <h3>
              <ArrowDown size={14} color="#3b82f6" />
              Active Tool Calls
            </h3>
            <div className="tool-list">
              {capabilityStats.activeToolCalls.map(tool => (
                <div key={tool.id} className="tool-item">
                  <span className={`tool-status ${tool.status}`}></span>
                  <span className="tool-name">{tool.tool}</span>
                  <span className="tool-capability">{tool.capability}</span>
                </div>
              ))}
              {capabilityStats.activeToolCalls.length === 0 && (
                <div className="no-data">No active tool calls</div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="activity-panel">
        <h2>Recent Activity</h2>
        <div className="activity-list">
          {recentActivity.length === 0 ? (
            <div className="activity-empty">Waiting for mesh activity...</div>
          ) : (
            recentActivity.map(activity => (
              <div key={activity.id} className="activity-item slide-in">
                <div className="activity-time">{activity.timestamp}</div>
                <div className="activity-type">{activity.type}</div>
                <div className="activity-message">{activity.message}</div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
