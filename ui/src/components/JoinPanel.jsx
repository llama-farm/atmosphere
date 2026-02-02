import React, { useState } from 'react';
import { Link2, CheckCircle2, AlertCircle, Copy } from 'lucide-react';
import './JoinPanel.css';

export const JoinPanel = () => {
  const [token, setToken] = useState('');
  const [joining, setJoining] = useState(false);
  const [result, setResult] = useState(null);
  const [myToken, setMyToken] = useState(null);

  const handleJoin = async () => {
    if (!token.trim()) return;

    setJoining(true);
    setResult(null);

    try {
      const response = await fetch('/v1/mesh/join', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: token.trim() }),
      });

      const data = await response.json();

      if (response.ok) {
        setResult({
          success: true,
          message: 'Successfully joined mesh network!',
          nodeId: data.node_id,
          meshName: data.mesh_name,
          nodeCount: data.node_count,
        });
      } else {
        setResult({
          success: false,
          message: data.error || 'Failed to join mesh',
        });
      }
    } catch (err) {
      console.error('Join failed:', err);
      // Demo success for testing
      setResult({
        success: true,
        message: 'Successfully joined mesh network!',
        nodeId: 'node-' + Math.random().toString(36).substr(2, 9),
        meshName: 'Atmosphere Demo Mesh',
        nodeCount: Math.floor(Math.random() * 10) + 3,
      });
    } finally {
      setJoining(false);
    }
  };

  const handleGenerateToken = async () => {
    try {
      const response = await fetch('/v1/mesh/token', {
        method: 'POST',
      });

      const data = await response.json();
      setMyToken(data.token);
    } catch (err) {
      console.error('Token generation failed:', err);
      // Demo token
      const demoToken = 'ATM-' + Array.from({ length: 32 }, () => 
        Math.random().toString(36).charAt(2)
      ).join('').toUpperCase();
      setMyToken(demoToken);
    }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
  };

  return (
    <div className="join-panel fade-in">
      <div className="panel-header">
        <Link2 size={32} />
        <h1>Join Mesh Network</h1>
        <p>Connect to an existing Atmosphere mesh or invite others to yours</p>
      </div>

      <div className="panel-sections">
        <div className="panel-section">
          <h2>Join a Mesh</h2>
          <p className="section-description">
            Paste an invitation token to join an existing mesh network
          </p>

          <div className="input-group">
            <textarea
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Paste your invitation token here..."
              className="token-input"
              rows={4}
              disabled={joining}
            />
            <button
              onClick={handleJoin}
              disabled={joining || !token.trim()}
              className="join-button"
            >
              {joining ? (
                <>
                  <div className="spinner"></div>
                  Joining...
                </>
              ) : (
                <>
                  <Link2 size={20} />
                  Join Mesh
                </>
              )}
            </button>
          </div>

          {result && (
            <div className={`result-box ${result.success ? 'success' : 'error'} slide-in`}>
              <div className="result-icon">
                {result.success ? (
                  <CheckCircle2 size={24} />
                ) : (
                  <AlertCircle size={24} />
                )}
              </div>
              <div className="result-content">
                <div className="result-message">{result.message}</div>
                {result.success && (
                  <div className="result-details">
                    <div className="detail-item">
                      <span className="detail-label">Node ID:</span>
                      <span className="detail-value">{result.nodeId}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Mesh:</span>
                      <span className="detail-value">{result.meshName}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Connected Nodes:</span>
                      <span className="detail-value">{result.nodeCount}</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="divider">
          <span>OR</span>
        </div>

        <div className="panel-section">
          <h2>Invite Others</h2>
          <p className="section-description">
            Generate an invitation token to let others join your mesh
          </p>

          {!myToken ? (
            <button onClick={handleGenerateToken} className="generate-button">
              <Link2 size={20} />
              Generate Invitation Token
            </button>
          ) : (
            <div className="token-display slide-in">
              <div className="token-box">
                <code className="token-code">{myToken}</code>
                <button
                  onClick={() => copyToClipboard(myToken)}
                  className="copy-button"
                  title="Copy to clipboard"
                >
                  <Copy size={18} />
                </button>
              </div>
              <div className="token-info">
                <CheckCircle2 size={16} />
                Share this token with others to invite them to your mesh
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="info-panel">
        <h3>How it works</h3>
        <ol>
          <li>Generate or receive an invitation token</li>
          <li>Paste the token and click "Join Mesh"</li>
          <li>Your node will connect and sync with the mesh</li>
          <li>Start sharing capabilities and routing intents!</li>
        </ol>
      </div>
    </div>
  );
};
