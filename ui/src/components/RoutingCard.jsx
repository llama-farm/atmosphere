import React, { useState, useEffect } from 'react';
import { Brain, Zap, Target, TrendingUp, Activity, Code, Search, MessageSquare } from 'lucide-react';
import './RoutingCard.css';

const COMPLEXITY_COLORS = {
  TRIVIAL: '#4ade80',
  SIMPLE: '#a3e635',
  MODERATE: '#fbbf24',
  COMPLEX: '#f97316',
  EXPERT: '#ec4899',
};

const TASK_ICONS = {
  qa: MessageSquare,
  chat: MessageSquare,
  reasoning: Brain,
  research: Search,
  agentic: Zap,
  code: Code,
  creative: TrendingUp,
};

export const RoutingCard = ({ wsData }) => {
  const [lastRouting, setLastRouting] = useState(null);
  const [testInput, setTestInput] = useState('');
  const [testing, setTesting] = useState(false);

  // Update from WebSocket messages
  useEffect(() => {
    if (wsData?.routing) {
      setLastRouting({
        ...wsData.routing,
        backend: wsData.backend,
        timestamp: Date.now(),
      });
    }
  }, [wsData]);

  const testClassification = async () => {
    if (!testInput.trim()) return;
    setTesting(true);

    try {
      const response = await fetch('/api/intent/classify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: testInput }),
      });
      const data = await response.json();
      setLastRouting({
        ...data.classification,
        text: testInput,
        timestamp: Date.now(),
      });
    } catch (error) {
      console.error('Classification failed:', error);
    } finally {
      setTesting(false);
    }
  };

  const TaskIcon = lastRouting ? (TASK_ICONS[lastRouting.task_type] || Activity) : Activity;

  return (
    <div className="routing-card fade-in">
      <div className="routing-header">
        <Target size={20} className="routing-icon" />
        <h2>Intent Classification</h2>
        <span className="crown-jewel">✨ THE CROWN JEWEL</span>
      </div>

      {/* Test Input */}
      <div className="routing-test">
        <input
          type="text"
          placeholder="Test a prompt (e.g., 'What is quantum entanglement?')"
          value={testInput}
          onChange={(e) => setTestInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && testClassification()}
        />
        <button onClick={testClassification} disabled={testing || !testInput.trim()}>
          {testing ? '...' : 'Test'}
        </button>
      </div>

      {lastRouting ? (
        <div className="routing-result">
          {/* Complexity Badge */}
          <div className="complexity-section">
            <div 
              className="complexity-badge"
              style={{ 
                background: `linear-gradient(135deg, ${COMPLEXITY_COLORS[lastRouting.complexity]}22, ${COMPLEXITY_COLORS[lastRouting.complexity]}44)`,
                borderColor: COMPLEXITY_COLORS[lastRouting.complexity]
              }}
            >
              <span className="complexity-name">{lastRouting.complexity}</span>
              <span className="model-size">{lastRouting.model_size}</span>
            </div>
            
            {/* Confidence Bar */}
            <div className="confidence-bar">
              <div className="confidence-label">Confidence</div>
              <div className="confidence-track">
                <div 
                  className="confidence-fill"
                  style={{ 
                    width: `${(lastRouting.confidence || 0.8) * 100}%`,
                    background: COMPLEXITY_COLORS[lastRouting.complexity]
                  }}
                />
              </div>
              <div className="confidence-value">{Math.round((lastRouting.confidence || 0.8) * 100)}%</div>
            </div>
          </div>

          {/* Details Grid */}
          <div className="routing-details">
            <div className="detail-item">
              <TaskIcon size={16} />
              <span className="detail-label">Task</span>
              <span className="detail-value">{lastRouting.task_type}</span>
            </div>
            
            <div className="detail-item">
              <Brain size={16} />
              <span className="detail-label">Domain</span>
              <span className="detail-value">{lastRouting.domain || 'general'}</span>
            </div>
            
            {lastRouting.backend && (
              <div className="detail-item">
                <Zap size={16} />
                <span className="detail-label">Backend</span>
                <span className="detail-value">{lastRouting.backend}</span>
              </div>
            )}
          </div>

          {/* Requirements */}
          {lastRouting.requirements && (
            <div className="requirements-section">
              <span className="requirements-label">Requirements:</span>
              <div className="requirements-badges">
                {lastRouting.requirements.tools && <span className="req-badge tools">🔧 Tools</span>}
                {lastRouting.requirements.rag && <span className="req-badge rag">📚 RAG</span>}
                {lastRouting.requirements.vision && <span className="req-badge vision">👁️ Vision</span>}
                {lastRouting.requirements.code && <span className="req-badge code">💻 Code</span>}
                {!lastRouting.requirements.tools && !lastRouting.requirements.rag && 
                 !lastRouting.requirements.vision && !lastRouting.requirements.code && (
                  <span className="req-badge none">None</span>
                )}
              </div>
            </div>
          )}

          {/* Timestamp */}
          {lastRouting.timestamp && (
            <div className="routing-timestamp">
              Last updated: {new Date(lastRouting.timestamp).toLocaleTimeString()}
            </div>
          )}
        </div>
      ) : (
        <div className="routing-empty">
          <Target size={48} className="empty-icon" />
          <p>No routing data yet</p>
          <span>Send a chat request or test above to see classification</span>
        </div>
      )}
    </div>
  );
};
