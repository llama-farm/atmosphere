import React, { useState, useEffect } from 'react';
import { CapabilityCard } from './CapabilityCard';
import { Search, RefreshCw, Filter, Layers } from 'lucide-react';
import './Capabilities.css';

export const Capabilities = () => {
  const [capabilities, setCapabilities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');

  const fetchCapabilities = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/capabilities');
      if (!response.ok) throw new Error('Failed to fetch capabilities');
      const data = await response.json();
      
      // Transform API response to match CapabilityCard format
      const transformed = data.map(cap => ({
        id: cap.id,
        type: guessCapabilityType(cap.label, cap.handler),
        status: 'online',
        triggers: cap.triggers || [],
        tools: cap.models?.length ? cap.models : [cap.handler],
        nodeId: 'local',
        lastSeen: new Date().toISOString(),
        description: cap.description,
        label: cap.label,
      }));
      
      setCapabilities(transformed);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch capabilities:', err);
      setError(err.message);
      // Use demo data
      setCapabilities([
        {
          id: 'chat-llm',
          type: 'llm',
          status: 'online',
          triggers: [],
          tools: ['chat', 'complete', 'embed'],
          nodeId: 'local',
          lastSeen: new Date().toISOString(),
          label: 'Chat LLM',
        },
        {
          id: 'anomaly-detector',
          type: 'sensor/camera',
          status: 'online',
          triggers: ['anomaly_detected'],
          tools: ['detect', 'score'],
          nodeId: 'local',
          lastSeen: new Date().toISOString(),
          label: 'Anomaly Detector',
        },
        {
          id: 'classifier',
          type: 'llm',
          status: 'online',
          triggers: [],
          tools: ['classify', 'predict'],
          nodeId: 'local',
          lastSeen: new Date().toISOString(),
          label: 'Classifier',
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const guessCapabilityType = (label, handler) => {
    const lower = (label + ' ' + handler).toLowerCase();
    if (lower.includes('camera') || lower.includes('vision') || lower.includes('image')) return 'sensor/camera';
    if (lower.includes('voice') || lower.includes('audio') || lower.includes('speech')) return 'sensor/voice';
    if (lower.includes('llm') || lower.includes('chat') || lower.includes('complete')) return 'llm';
    if (lower.includes('search') || lower.includes('query')) return 'search';
    if (lower.includes('tool') || lower.includes('action')) return 'tool';
    return 'default';
  };

  useEffect(() => {
    fetchCapabilities();
  }, []);

  const filteredCapabilities = capabilities.filter(cap => {
    const matchesFilter = filter === 'all' || 
      (filter === 'triggers' && cap.triggers.length > 0) ||
      (filter === 'tools' && cap.tools.length > 0) ||
      (filter === 'llm' && cap.type === 'llm') ||
      (filter === 'sensors' && cap.type.startsWith('sensor/'));
    
    const matchesSearch = !search || 
      cap.id.toLowerCase().includes(search.toLowerCase()) ||
      cap.label?.toLowerCase().includes(search.toLowerCase()) ||
      cap.type.toLowerCase().includes(search.toLowerCase());
    
    return matchesFilter && matchesSearch;
  });

  const filterOptions = [
    { id: 'all', label: 'All' },
    { id: 'triggers', label: 'Has Triggers' },
    { id: 'tools', label: 'Has Tools' },
    { id: 'llm', label: 'LLM' },
    { id: 'sensors', label: 'Sensors' },
  ];

  return (
    <div className="capabilities-page fade-in">
      <div className="page-header">
        <div className="header-title">
          <Layers size={28} />
          <div>
            <h1>Capabilities</h1>
            <p>All available capabilities in the mesh</p>
          </div>
        </div>
        <button onClick={fetchCapabilities} className="refresh-btn" disabled={loading}>
          <RefreshCw size={18} className={loading ? 'spin' : ''} />
          Refresh
        </button>
      </div>

      <div className="capabilities-controls">
        <div className="search-box">
          <Search size={18} />
          <input
            type="text"
            placeholder="Search capabilities..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        
        <div className="filter-group">
          <Filter size={16} />
          {filterOptions.map(opt => (
            <button
              key={opt.id}
              className={`filter-btn ${filter === opt.id ? 'active' : ''}`}
              onClick={() => setFilter(opt.id)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="capabilities-stats">
        <div className="stat">
          <span className="stat-value">{capabilities.length}</span>
          <span className="stat-label">Total</span>
        </div>
        <div className="stat">
          <span className="stat-value">{capabilities.filter(c => c.triggers.length > 0).length}</span>
          <span className="stat-label">With Triggers</span>
        </div>
        <div className="stat">
          <span className="stat-value">{capabilities.filter(c => c.tools.length > 0).length}</span>
          <span className="stat-label">With Tools</span>
        </div>
        <div className="stat">
          <span className="stat-value">{capabilities.filter(c => c.status === 'online').length}</span>
          <span className="stat-label">Online</span>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <span>⚠️ {error} - showing demo data</span>
        </div>
      )}

      {loading ? (
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <p>Loading capabilities...</p>
        </div>
      ) : filteredCapabilities.length === 0 ? (
        <div className="empty-state">
          <Layers size={48} />
          <h3>No capabilities found</h3>
          <p>Try adjusting your filters or search query</p>
        </div>
      ) : (
        <div className="capabilities-grid">
          {filteredCapabilities.map(cap => (
            <CapabilityCard key={cap.id} capability={cap} />
          ))}
        </div>
      )}
    </div>
  );
};

export default Capabilities;
