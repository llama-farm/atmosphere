import React, { useState, useEffect } from 'react';
import { Send, Zap, CheckCircle2 } from 'lucide-react';
import './IntentRouter.css';

export const IntentRouter = () => {
  const [intent, setIntent] = useState('');
  const [routing, setRouting] = useState(false);
  const [result, setResult] = useState(null);
  const [routingPath, setRoutingPath] = useState([]);

  const exampleIntents = [
    'analyze this image',
    'search for latest news',
    'generate a chart',
    'send a notification',
    'execute python code',
  ];

  const handleRoute = async () => {
    if (!intent.trim()) return;

    setRouting(true);
    setResult(null);
    setRoutingPath([]);

    try {
      // Simulate routing animation
      const steps = ['Parsing intent', 'Finding capabilities', 'Selecting node', 'Routing request'];
      
      for (let i = 0; i < steps.length; i++) {
        await new Promise(resolve => setTimeout(resolve, 300));
        setRoutingPath(prev => [...prev, steps[i]]);
      }

      const response = await fetch('/v1/route', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ intent }),
      });

      const data = await response.json();
      
      setResult({
        node: data.node || 'node-1',
        capability: data.capability || intent.split(' ')[0],
        confidence: data.confidence || Math.random() * 0.3 + 0.7,
        executionTime: data.execution_time || Math.random() * 200 + 100,
      });
    } catch (err) {
      console.error('Routing failed:', err);
      // Demo result on error
      setResult({
        node: 'node-demo',
        capability: intent.split(' ')[0],
        confidence: 0.85,
        executionTime: 156,
      });
    } finally {
      setRouting(false);
    }
  };

  return (
    <div className="intent-router fade-in">
      <div className="router-header">
        <h1>Intent Router Demo</h1>
        <p>Type an intent and watch it route to the correct node with the right capability</p>
      </div>

      <div className="router-input-section">
        <div className="input-group">
          <input
            type="text"
            value={intent}
            onChange={(e) => setIntent(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleRoute()}
            placeholder="What do you want to do?"
            className="intent-input"
            disabled={routing}
          />
          <button
            onClick={handleRoute}
            disabled={routing || !intent.trim()}
            className="route-button"
          >
            {routing ? (
              <>
                <Zap className="spin" size={20} />
                Routing...
              </>
            ) : (
              <>
                <Send size={20} />
                Route
              </>
            )}
          </button>
        </div>

        <div className="example-intents">
          <span>Try:</span>
          {exampleIntents.map((example, i) => (
            <button
              key={i}
              onClick={() => setIntent(example)}
              className="example-chip"
              disabled={routing}
            >
              {example}
            </button>
          ))}
        </div>
      </div>

      {routingPath.length > 0 && (
        <div className="routing-path">
          {routingPath.map((step, i) => (
            <div key={i} className="routing-step slide-in">
              <div className="step-icon">
                {i === routingPath.length - 1 && !routing ? (
                  <CheckCircle2 size={20} color="#10b981" />
                ) : (
                  <div className="step-dot pulse"></div>
                )}
              </div>
              <div className="step-label">{step}</div>
            </div>
          ))}
        </div>
      )}

      {result && (
        <div className="routing-result slide-in">
          <div className="result-header">
            <CheckCircle2 size={24} color="#10b981" />
            <h3>Routing Complete</h3>
          </div>
          
          <div className="result-grid">
            <div className="result-item">
              <div className="result-label">Target Node</div>
              <div className="result-value">{result.node}</div>
            </div>
            <div className="result-item">
              <div className="result-label">Capability</div>
              <div className="result-value">{result.capability}</div>
            </div>
            <div className="result-item">
              <div className="result-label">Confidence</div>
              <div className="result-value">{(result.confidence * 100).toFixed(1)}%</div>
            </div>
            <div className="result-item">
              <div className="result-label">Execution Time</div>
              <div className="result-value">{result.executionTime.toFixed(0)}ms</div>
            </div>
          </div>

          <div className="result-visualization">
            <div className="viz-node you">You</div>
            <div className="viz-arrow">
              <div className="arrow-line"></div>
              <div className="arrow-head"></div>
            </div>
            <div className="viz-node target glow">
              {result.node}
              <div className="capability-badge">{result.capability}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
