import React, { useState, useEffect } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { Link2, CheckCircle2, AlertCircle, Copy, QrCode, RefreshCw, Smartphone, Wifi, Globe, Radio, XCircle } from 'lucide-react';
import './JoinPanel.css';

export const JoinPanel = () => {
  const [token, setToken] = useState('');
  const [joining, setJoining] = useState(false);
  const [result, setResult] = useState(null);
  const [inviteData, setInviteData] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [showQR, setShowQR] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleJoin = async () => {
    if (!token.trim()) return;

    setJoining(true);
    setResult(null);

    try {
      const response = await fetch('/api/mesh/join', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          token: token.trim(),
          device: {
            device_id: `web-${Date.now()}`,
            public_key: 'web-client',
            name: navigator.userAgent.split(' ').slice(-1)[0],
            hardware_hash: 'web',
          },
          timestamp: Date.now(),
          signature: 'web-client',
        }),
      });

      const data = await response.json();

      if (response.ok && data.success) {
        setResult({
          success: true,
          message: 'Successfully joined mesh network!',
          nodeId: data.mesh_id,
          meshName: data.mesh_name,
          nodeCount: 1,
        });
      } else {
        setResult({
          success: false,
          message: data.error || data.detail || 'Failed to join mesh',
        });
      }
    } catch (err) {
      console.error('Join failed:', err);
      setResult({
        success: false,
        message: `Connection error: ${err.message}`,
      });
    } finally {
      setJoining(false);
    }
  };

  const handleGenerateToken = async () => {
    setGenerating(true);
    try {
      const response = await fetch('/api/mesh/token', {
        method: 'POST',
      });

      const data = await response.json();
      setInviteData({
        token: data.token,
        meshName: data.mesh_name,
        endpoint: data.endpoint,
        endpoints: data.endpoints || { local: data.endpoint },
        networkInfo: data.network_info || {},
        expiresAt: data.expires_at,
        qrData: data.qr_data,
      });
      setShowQR(true);
    } catch (err) {
      console.error('Token generation failed:', err);
      // Generate a fallback invite
      const fallbackToken = 'ATM-' + Array.from({ length: 32 }, () => 
        Math.random().toString(36).charAt(2)
      ).join('').toUpperCase();
      
      const localEndpoint = `ws://${window.location.hostname}:11451`;
      setInviteData({
        token: fallbackToken,
        meshName: 'Local Mesh',
        endpoint: localEndpoint,
        endpoints: { local: localEndpoint },
        networkInfo: { local_ip: window.location.hostname },
        expiresAt: Date.now() / 1000 + 86400,
        qrData: `atmosphere://join?token=${fallbackToken}&mesh=local&endpoints=${encodeURIComponent(JSON.stringify({ local: localEndpoint }))}`,
      });
      setShowQR(true);
    } finally {
      setGenerating(false);
    }
  };

  const copyToClipboard = async (text) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formatExpiration = (timestamp) => {
    const date = new Date(timestamp * 1000);
    const now = new Date();
    const diffHours = Math.round((date - now) / (1000 * 60 * 60));
    if (diffHours > 24) {
      return `${Math.round(diffHours / 24)} days`;
    }
    return `${diffHours} hours`;
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
              placeholder="Paste your invitation token here (ATM-XXXX...)&#10;&#10;Or scan a QR code with the Atmosphere mobile app"
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
            Generate an invitation token or QR code for mobile devices
          </p>

          {!inviteData ? (
            <button 
              onClick={handleGenerateToken} 
              className="generate-button"
              disabled={generating}
            >
              {generating ? (
                <>
                  <RefreshCw size={20} className="spin" />
                  Generating...
                </>
              ) : (
                <>
                  <QrCode size={20} />
                  Generate Invitation
                </>
              )}
            </button>
          ) : (
            <div className="invite-display slide-in">
              {showQR && (
                <div className="qr-section">
                  <div className="qr-container">
                    <QRCodeSVG
                      value={inviteData.qrData}
                      size={200}
                      level="M"
                      includeMargin={true}
                      bgColor="#1a1a2e"
                      fgColor="#ffffff"
                    />
                  </div>
                  <div className="qr-info">
                    <Smartphone size={16} />
                    <span>Scan with Atmosphere app to join</span>
                  </div>
                </div>
              )}
              
              <div className="token-section">
                <div className="token-label">Invitation Token</div>
                <div className="token-box">
                  <code className="token-code">{inviteData.token}</code>
                  <button
                    onClick={() => copyToClipboard(inviteData.token)}
                    className="copy-button"
                    title="Copy to clipboard"
                  >
                    {copied ? <CheckCircle2 size={18} /> : <Copy size={18} />}
                  </button>
                </div>
              </div>

              <div className="invite-details">
                <div className="detail-row">
                  <span className="label">Mesh:</span>
                  <span className="value">{inviteData.meshName}</span>
                </div>
                <div className="detail-row">
                  <span className="label">Expires in:</span>
                  <span className="value">{formatExpiration(inviteData.expiresAt)}</span>
                </div>
              </div>

              {/* Connectivity Status */}
              <div className="connectivity-status">
                <div className="connectivity-header">
                  <span className="label">Connectivity</span>
                </div>
                <div className="connectivity-items">
                  {/* Local Network */}
                  <div className="connectivity-item">
                    <Wifi size={16} className={inviteData.endpoints?.local ? 'status-ok' : 'status-error'} />
                    <span className="connectivity-type">Local Network</span>
                    {inviteData.endpoints?.local ? (
                      <span className="connectivity-value mono">
                        {inviteData.networkInfo?.local_ip || 'Connected'}
                      </span>
                    ) : (
                      <span className="connectivity-value error">Not available</span>
                    )}
                  </div>
                  
                  {/* Public Internet */}
                  <div className="connectivity-item">
                    <Globe size={16} className={inviteData.endpoints?.public ? 'status-ok' : 'status-warn'} />
                    <span className="connectivity-type">Internet</span>
                    {inviteData.endpoints?.public ? (
                      <span className="connectivity-value mono">
                        {inviteData.networkInfo?.public_ip || 'Detected'}
                        <span className="connectivity-note">(port forward required)</span>
                      </span>
                    ) : (
                      <span className="connectivity-value warn">
                        {inviteData.networkInfo?.is_behind_nat ? 'Behind NAT' : 'Not detected'}
                      </span>
                    )}
                  </div>
                  
                  {/* Relay */}
                  <div className="connectivity-item">
                    <Radio size={16} className={inviteData.endpoints?.relay ? 'status-ok' : 'status-disabled'} />
                    <span className="connectivity-type">Relay</span>
                    {inviteData.endpoints?.relay ? (
                      <span className="connectivity-value ok">Available</span>
                    ) : (
                      <span className="connectivity-value disabled">Not configured</span>
                    )}
                  </div>
                </div>
                
                {!inviteData.endpoints?.public && !inviteData.endpoints?.relay && (
                  <div className="connectivity-warning">
                    <AlertCircle size={14} />
                    <span>Only local network connections available. For internet access, configure port forwarding or a relay server.</span>
                  </div>
                )}
              </div>

              <div className="invite-actions">
                <button 
                  onClick={() => setShowQR(!showQR)}
                  className="action-button"
                >
                  <QrCode size={16} />
                  {showQR ? 'Hide QR' : 'Show QR'}
                </button>
                <button 
                  onClick={handleGenerateToken}
                  className="action-button"
                  disabled={generating}
                >
                  <RefreshCw size={16} />
                  New Token
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="info-panel">
        <h3>How it works</h3>
        <ol>
          <li>
            <strong>Generate</strong> - Create an invitation token or QR code
          </li>
          <li>
            <strong>Share</strong> - Send the token or let them scan the QR
          </li>
          <li>
            <strong>Connect</strong> - Their device joins and syncs with the mesh
          </li>
          <li>
            <strong>Collaborate</strong> - Start sharing capabilities and routing intents!
          </li>
        </ol>
        <div className="mobile-hint">
          <Smartphone size={16} />
          <span>Mobile users can scan the QR code with the Atmosphere Android app</span>
        </div>
      </div>
    </div>
  );
};
