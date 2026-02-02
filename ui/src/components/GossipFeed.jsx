import React, { useState, useEffect } from 'react';
import { Radio, Zap, CheckCircle2, XCircle } from 'lucide-react';
import './GossipFeed.css';

export const GossipFeed = ({ wsData }) => {
  const [messages, setMessages] = useState([]);
  const [filter, setFilter] = useState('all'); // all, capabilities, nodes, errors

  useEffect(() => {
    // Add WebSocket messages to feed
    if (wsData && wsData.type === 'gossip') {
      const newMessage = {
        id: Date.now(),
        type: wsData.event_type || 'capability',
        node: wsData.node || 'unknown',
        capability: wsData.capability,
        message: wsData.message || JSON.stringify(wsData),
        timestamp: new Date(),
        success: wsData.success !== false,
      };
      
      setMessages(prev => [newMessage, ...prev.slice(0, 49)]); // Keep last 50
    }
  }, [wsData]);

  // Generate some initial demo messages
  useEffect(() => {
    const demoMessages = [
      { id: 1, type: 'capability', node: 'node-1', capability: 'vision', message: 'Announced vision capability', timestamp: new Date(Date.now() - 10000), success: true },
      { id: 2, type: 'capability', node: 'node-2', capability: 'search', message: 'Announced search capability', timestamp: new Date(Date.now() - 20000), success: true },
      { id: 3, type: 'node', node: 'node-3', message: 'Joined mesh network', timestamp: new Date(Date.now() - 30000), success: true },
      { id: 4, type: 'capability', node: 'node-1', capability: 'ocr', message: 'Announced ocr capability', timestamp: new Date(Date.now() - 40000), success: true },
      { id: 5, type: 'error', node: 'node-4', message: 'Connection timeout', timestamp: new Date(Date.now() - 50000), success: false },
    ];
    
    setMessages(demoMessages);
  }, []);

  const filteredMessages = messages.filter(msg => {
    if (filter === 'all') return true;
    if (filter === 'capabilities') return msg.type === 'capability';
    if (filter === 'nodes') return msg.type === 'node';
    if (filter === 'errors') return !msg.success;
    return true;
  });

  const getIcon = (type, success) => {
    if (!success) return <XCircle size={20} color="#ef4444" />;
    if (type === 'capability') return <Zap size={20} color="#8b5cf6" />;
    if (type === 'node') return <CheckCircle2 size={20} color="#10b981" />;
    return <Radio size={20} color="#3b82f6" />;
  };

  const formatTime = (date) => {
    const now = new Date();
    const diff = Math.floor((now - date) / 1000);
    
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return date.toLocaleTimeString();
  };

  return (
    <div className="gossip-feed fade-in">
      <div className="feed-header">
        <div className="header-content">
          <Radio className="pulse" size={24} />
          <h1>Live Gossip Feed</h1>
        </div>
        
        <div className="feed-filters">
          {['all', 'capabilities', 'nodes', 'errors'].map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`filter-button ${filter === f ? 'active' : ''}`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="feed-container">
        {filteredMessages.length === 0 ? (
          <div className="feed-empty">
            <Radio size={48} />
            <p>No gossip messages yet</p>
            <span>Waiting for network activity...</span>
          </div>
        ) : (
          <div className="feed-list">
            {filteredMessages.map(msg => (
              <div key={msg.id} className={`feed-message slide-in ${!msg.success ? 'error' : ''}`}>
                <div className="message-icon">
                  {getIcon(msg.type, msg.success)}
                </div>
                
                <div className="message-content">
                  <div className="message-header">
                    <span className="message-node">{msg.node}</span>
                    {msg.capability && (
                      <span className="message-capability">{msg.capability}</span>
                    )}
                    <span className="message-time">{formatTime(msg.timestamp)}</span>
                  </div>
                  
                  <div className="message-body">{msg.message}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="feed-stats">
        <div className="stat">
          <span className="stat-value">{messages.length}</span>
          <span className="stat-label">Total Messages</span>
        </div>
        <div className="stat">
          <span className="stat-value">{messages.filter(m => m.type === 'capability').length}</span>
          <span className="stat-label">Capabilities</span>
        </div>
        <div className="stat">
          <span className="stat-value">{messages.filter(m => !m.success).length}</span>
          <span className="stat-label">Errors</span>
        </div>
      </div>
    </div>
  );
};
