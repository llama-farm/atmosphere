import React, { useState } from 'react';
import { ChevronDown, ChevronUp, ArrowUp, ArrowDown, Camera, Mic, Brain, Search, Eye, Wrench, Zap } from 'lucide-react';
import './CapabilityCard.css';

const CAPABILITY_ICONS = {
  'sensor/camera': Camera,
  'sensor/voice': Mic,
  'llm': Brain,
  'search': Search,
  'vision': Eye,
  'tool': Wrench,
  'default': Zap,
};

const STATUS_COLORS = {
  online: '#10b981',
  busy: '#f59e0b',
  degraded: '#ef4444',
  offline: '#6b7280',
};

export const CapabilityCard = ({ capability }) => {
  const [expanded, setExpanded] = useState(false);
  
  const {
    id,
    type = 'default',
    status = 'online',
    triggers = [],
    tools = [],
    nodeId,
    lastSeen,
  } = capability;

  const IconComponent = CAPABILITY_ICONS[type] || CAPABILITY_ICONS.default;
  const statusColor = STATUS_COLORS[status] || STATUS_COLORS.offline;

  const formatLastSeen = (timestamp) => {
    if (!timestamp) return 'Unknown';
    const diff = Math.floor((Date.now() - new Date(timestamp).getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
  };

  return (
    <div className={`capability-card ${expanded ? 'expanded' : ''} status-${status}`}>
      <div className="capability-header" onClick={() => setExpanded(!expanded)}>
        <div className="capability-icon-wrapper">
          <div className="capability-icon" style={{ backgroundColor: `${statusColor}22` }}>
            <IconComponent size={24} color={statusColor} />
          </div>
          <div 
            className="status-indicator" 
            style={{ backgroundColor: statusColor }}
            title={status}
          />
        </div>

        <div className="capability-info">
          <div className="capability-id">{id}</div>
          <div className="capability-type">{type}</div>
          {nodeId && <div className="capability-node">Node: {nodeId}</div>}
        </div>

        <div className="capability-badges">
          {triggers.length > 0 && (
            <div className="badge badge-trigger" title="Push triggers">
              <ArrowUp size={12} />
              <span>{triggers.length}</span>
            </div>
          )}
          {tools.length > 0 && (
            <div className="badge badge-tool" title="Pull tools">
              <ArrowDown size={12} />
              <span>{tools.length}</span>
            </div>
          )}
        </div>

        <div className="expand-icon">
          {expanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
        </div>
      </div>

      {expanded && (
        <div className="capability-details slide-in">
          {triggers.length > 0 && (
            <div className="detail-section">
              <div className="detail-header">
                <ArrowUp size={14} color="#f97316" />
                <span>Triggers (PUSH)</span>
              </div>
              <div className="detail-list">
                {triggers.map((trigger, idx) => (
                  <div key={idx} className="detail-item trigger-item">
                    <Zap size={12} />
                    <span>{trigger}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {tools.length > 0 && (
            <div className="detail-section">
              <div className="detail-header">
                <ArrowDown size={14} color="#3b82f6" />
                <span>Tools (PULL)</span>
              </div>
              <div className="detail-list">
                {tools.map((tool, idx) => (
                  <div key={idx} className="detail-item tool-item">
                    <Wrench size={12} />
                    <span>{tool}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {lastSeen && (
            <div className="detail-footer">
              Last seen: {formatLastSeen(lastSeen)}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default CapabilityCard;
