import React, { useState, useEffect } from 'react';
import { Radio, Zap, CheckCircle2, XCircle, ArrowUp, ArrowDown, Wifi, Heart } from 'lucide-react';
import './GossipFeed.css';

// Message type configurations
const MESSAGE_TYPES = {
  CAPABILITY_AVAILABLE: { color: '#10b981', label: 'Available', icon: Zap },
  CAPABILITY_HEARTBEAT: { color: '#6b7280', label: 'Heartbeat', icon: Heart },
  TRIGGER_EVENT: { color: '#f97316', label: 'Trigger', icon: ArrowUp, animated: true },
  TOOL_CALL: { color: '#3b82f6', label: 'Tool Call', icon: ArrowDown },
  capability: { color: '#8b5cf6', label: 'Capability', icon: Zap },
  node: { color: '#10b981', label: 'Node', icon: CheckCircle2 },
  error: { color: '#ef4444', label: 'Error', icon: XCircle },
};

export const GossipFeed = ({ wsData, demoMode = false }) => {
  const [messages, setMessages] = useState([]);
  const [filter, setFilter] = useState('all'); // all, capabilities, nodes, triggers, tools, errors

  useEffect(() => {
    // Add WebSocket messages to feed
    if (wsData && wsData.type === 'gossip') {
      const newMessage = {
        id: Date.now(),
        type: wsData.event_type || 'capability',
        node: wsData.node || 'unknown',
        capability: wsData.capability,
        trigger: wsData.trigger,
        tool: wsData.tool,
        message: wsData.message || JSON.stringify(wsData),
        timestamp: new Date(),
        success: wsData.success !== false,
      };
      
      setMessages(prev => [newMessage, ...prev.slice(0, 49)]); // Keep last 50
    }
  }, [wsData]);

  // Only load demo messages if demoMode is enabled
  useEffect(() => {
    if (!demoMode) {
      // Start with empty feed in production mode
      return;
    }
    
    const demoMessages = [
      { id: 1, type: 'TRIGGER_EVENT', node: 'camera-1', capability: 'front-door', trigger: 'motion_detected', message: 'Motion detected at front door', timestamp: new Date(Date.now() - 5000), success: true },
      { id: 2, type: 'TOOL_CALL', node: 'agent-1', capability: 'front-door', tool: 'get_frame', message: 'Agent requested camera frame', timestamp: new Date(Date.now() - 8000), success: true },
      { id: 3, type: 'CAPABILITY_AVAILABLE', node: 'node-1', capability: 'vision', message: 'Announced vision capability', timestamp: new Date(Date.now() - 10000), success: true },
      { id: 4, type: 'CAPABILITY_HEARTBEAT', node: 'node-2', capability: 'search', message: 'Heartbeat from search capability', timestamp: new Date(Date.now() - 15000), success: true },
      { id: 5, type: 'TRIGGER_EVENT', node: 'voice-1', capability: 'alexa', trigger: 'wake_word', message: 'Wake word detected', timestamp: new Date(Date.now() - 20000), success: true },
      { id: 6, type: 'capability', node: 'node-2', capability: 'search', message: 'Announced search capability', timestamp: new Date(Date.now() - 25000), success: true },
      { id: 7, type: 'node', node: 'node-3', message: 'Joined mesh network', timestamp: new Date(Date.now() - 30000), success: true },
      { id: 8, type: 'TOOL_CALL', node: 'agent-2', capability: 'llm', tool: 'generate', message: 'Agent called LLM generate', timestamp: new Date(Date.now() - 35000), success: true },
      { id: 9, type: 'capability', node: 'node-1', capability: 'ocr', message: 'Announced ocr capability', timestamp: new Date(Date.now() - 40000), success: true },
      { id: 10, type: 'error', node: 'node-4', message: 'Connection timeout', timestamp: new Date(Date.now() - 50000), success: false },
    ];
    
    setMessages(demoMessages);
  }, [demoMode]);

  const filteredMessages = messages.filter(msg => {
    if (filter === 'all') return true;
    if (filter === 'capabilities') return msg.type === 'capability' || msg.type === 'CAPABILITY_AVAILABLE' || msg.type === 'CAPABILITY_HEARTBEAT';
    if (filter === 'nodes') return msg.type === 'node';
    if (filter === 'triggers') return msg.type === 'TRIGGER_EVENT';
    if (filter === 'tools') return msg.type === 'TOOL_CALL';
    if (filter === 'errors') return !msg.success;
    return true;
  });

  const getIcon = (type, success) => {
    if (!success) return <XCircle size={20} color="#ef4444" />;
    
    const msgType = MESSAGE_TYPES[type];
    if (msgType) {
      const IconComponent = msgType.icon;
      return <IconComponent size={20} color={msgType.color} />;
    }
    
    return <Radio size={20} color="#3b82f6" />;
  };

  const getTypeLabel = (type) => {
    return MESSAGE_TYPES[type]?.label || type;
  };

  const isAnimated = (type) => {
    return MESSAGE_TYPES[type]?.animated || false;
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
          {['all', 'capabilities', 'triggers', 'tools', 'nodes', 'errors'].map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`filter-button ${filter === f ? 'active' : ''} filter-${f}`}
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
              <div key={msg.id} className={`feed-message slide-in ${!msg.success ? 'error' : ''} ${isAnimated(msg.type) ? 'animated-message' : ''} type-${msg.type.toLowerCase().replace(/_/g, '-')}`}>
                <div className={`message-icon ${isAnimated(msg.type) ? 'pulse-icon' : ''}`}>
                  {getIcon(msg.type, msg.success)}
                </div>
                
                <div className="message-content">
                  <div className="message-header">
                    <span className="message-node">{msg.node}</span>
                    <span className={`message-type-badge type-${msg.type.toLowerCase().replace(/_/g, '-')}`}>
                      {getTypeLabel(msg.type)}
                    </span>
                    {msg.capability && (
                      <span className="message-capability">{msg.capability}</span>
                    )}
                    {msg.trigger && (
                      <span className="message-trigger">↑ {msg.trigger}</span>
                    )}
                    {msg.tool && (
                      <span className="message-tool">↓ {msg.tool}</span>
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
