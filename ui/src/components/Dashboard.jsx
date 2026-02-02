import React, { useState, useEffect } from 'react';
import { Activity, Wifi, Zap, Users } from 'lucide-react';
import './Dashboard.css';

export const Dashboard = ({ wsData }) => {
  const [stats, setStats] = useState({
    connectedNodes: 0,
    totalCapabilities: 0,
    activeAgents: 0,
    meshHealth: 100,
  });

  const [recentActivity, setRecentActivity] = useState([]);

  useEffect(() => {
    // Fetch initial stats
    fetch('/v1/mesh/status')
      .then(res => res.json())
      .then(data => {
        setStats({
          connectedNodes: data.nodes?.length || 0,
          totalCapabilities: data.capabilities?.length || 0,
          activeAgents: data.active_agents || 0,
          meshHealth: data.health || 100,
        });
      })
      .catch(err => console.error('Failed to fetch mesh status:', err));
  }, []);

  useEffect(() => {
    // Update activity from WebSocket
    if (wsData) {
      setRecentActivity(prev => [
        {
          id: Date.now(),
          type: wsData.type,
          message: wsData.message || JSON.stringify(wsData),
          timestamp: new Date().toLocaleTimeString(),
        },
        ...prev.slice(0, 9) // Keep last 10 items
      ]);
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

      <div className="activity-panel">
        <h2>Recent Activity</h2>
        <div className="activity-list">
          {recentActivity.length === 0 ? (
            <div className="activity-empty">No recent activity</div>
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
