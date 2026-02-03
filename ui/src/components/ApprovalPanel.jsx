import React, { useState, useEffect } from 'react';
import { 
  Shield, Brain, Cpu, Camera, Mic, Monitor, Users, 
  Save, RefreshCw, CheckCircle2, AlertCircle, ChevronDown, ChevronUp,
  Eye, EyeOff, Zap, Lock, ExternalLink, HelpCircle
} from 'lucide-react';
import './ApprovalPanel.css';

// Permission status indicators
const PermissionStatus = ({ status }) => {
  switch (status) {
    case 'granted':
      return (
        <span className="permission-status granted">
          <CheckCircle2 size={14} />
          Granted
        </span>
      );
    case 'denied':
      return (
        <span className="permission-status denied">
          <AlertCircle size={14} />
          Denied
        </span>
      );
    case 'not_determined':
      return (
        <span className="permission-status pending">
          <HelpCircle size={14} />
          Not Set
        </span>
      );
    case 'not_applicable':
      return (
        <span className="permission-status na">
          N/A
        </span>
      );
    default:
      return (
        <span className="permission-status unknown">
          <HelpCircle size={14} />
          Unknown
        </span>
      );
  }
};

export const ApprovalPanel = ({ demoMode = false, onDemoModeChange }) => {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveResult, setSaveResult] = useState(null);
  const [permissions, setPermissions] = useState(null);
  const [permissionsLoading, setPermissionsLoading] = useState(true);
  const [expandedSections, setExpandedSections] = useState({
    models: true,
    hardware: true,
    privacy: true,
    access: false,
    ui: false,
  });

  const fetchConfig = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/approval/config');
      if (!response.ok) throw new Error('Failed to fetch config');
      const data = await response.json();
      setConfig(data);
    } catch (err) {
      console.error('Failed to fetch config:', err);
      // Use defaults
      setConfig({
        models: {
          ollama: { enabled: true, selected: [] },
          llamafarm: { enabled: true, selected: [] },
        },
        hardware: {
          gpu: { enabled: true, max_vram_percent: 80 },
          cpu: { enabled: true, max_cores: null },
        },
        privacy: {
          camera: { enabled: false, mode: 'off' },
          microphone: { enabled: false, mode: 'off' },
          screen: { enabled: false },
        },
        access: {
          mesh_allowlist: [],
          mesh_denylist: [],
          rate_limit: { enabled: false, requests_per_minute: 60 },
        },
      });
    } finally {
      setLoading(false);
    }
  };

  const fetchPermissions = async () => {
    setPermissionsLoading(true);
    try {
      const response = await fetch('/api/permissions/status');
      if (!response.ok) throw new Error('Failed to fetch permissions');
      const data = await response.json();
      setPermissions(data);
    } catch (err) {
      console.error('Failed to fetch permissions:', err);
      setPermissions(null);
    } finally {
      setPermissionsLoading(false);
    }
  };

  const openSettings = async (permission) => {
    try {
      await fetch(`/api/permissions/open-settings?permission=${permission}`, {
        method: 'POST'
      });
      // Refresh permissions after a delay (user might have changed settings)
      setTimeout(fetchPermissions, 2000);
    } catch (err) {
      console.error('Failed to open settings:', err);
    }
  };

  const saveConfig = async () => {
    setSaving(true);
    setSaveResult(null);
    try {
      const response = await fetch('/api/approval/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      
      if (!response.ok) throw new Error('Failed to save');
      setSaveResult({ success: true, message: 'Configuration saved!' });
      setTimeout(() => setSaveResult(null), 3000);
    } catch (err) {
      setSaveResult({ success: false, message: err.message });
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    fetchConfig();
    fetchPermissions();
    
    // Refresh permissions periodically
    const interval = setInterval(fetchPermissions, 30000);
    return () => clearInterval(interval);
  }, []);

  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  const updateConfig = (path, value) => {
    setConfig(prev => {
      const newConfig = JSON.parse(JSON.stringify(prev));
      const parts = path.split('.');
      let current = newConfig;
      for (let i = 0; i < parts.length - 1; i++) {
        current = current[parts[i]];
      }
      current[parts[parts.length - 1]] = value;
      return newConfig;
    });
  };

  if (loading) {
    return (
      <div className="approval-panel loading">
        <div className="loading-spinner"></div>
        <p>Loading configuration...</p>
      </div>
    );
  }

  const cameraPermission = permissions?.permissions?.camera;
  const micPermission = permissions?.permissions?.microphone;
  const screenPermission = permissions?.permissions?.screen_recording;

  return (
    <div className="approval-panel fade-in">
      <div className="panel-header">
        <div className="header-title">
          <Shield size={28} />
          <div>
            <h1>Owner Approval</h1>
            <p>Control what this node shares with the mesh</p>
          </div>
        </div>
        <div className="header-actions">
          <button onClick={() => { fetchConfig(); fetchPermissions(); }} className="action-btn" disabled={loading}>
            <RefreshCw size={18} />
          </button>
          <button onClick={saveConfig} className="save-btn" disabled={saving}>
            {saving ? (
              <>
                <RefreshCw size={18} className="spin" />
                Saving...
              </>
            ) : (
              <>
                <Save size={18} />
                Save Changes
              </>
            )}
          </button>
        </div>
      </div>

      {saveResult && (
        <div className={`save-result ${saveResult.success ? 'success' : 'error'}`}>
          {saveResult.success ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
          {saveResult.message}
        </div>
      )}

      {/* Models Section */}
      <div className="config-section">
        <div className="section-header" onClick={() => toggleSection('models')}>
          <div className="section-title">
            <Brain size={20} />
            <span>Language Models</span>
          </div>
          <div className="section-toggle">
            {expandedSections.models ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
          </div>
        </div>
        
        {expandedSections.models && (
          <div className="section-content">
            <div className="config-item">
              <div className="item-header">
                <label className="toggle-label">
                  <input
                    type="checkbox"
                    checked={config?.models?.ollama?.enabled}
                    onChange={(e) => updateConfig('models.ollama.enabled', e.target.checked)}
                  />
                  <span className="toggle-switch"></span>
                  <span className="toggle-text">Share Ollama Models</span>
                </label>
                <span className="item-hint">Local models via Ollama</span>
              </div>
            </div>
            
            <div className="config-item">
              <div className="item-header">
                <label className="toggle-label">
                  <input
                    type="checkbox"
                    checked={config?.models?.llamafarm?.enabled}
                    onChange={(e) => updateConfig('models.llamafarm.enabled', e.target.checked)}
                  />
                  <span className="toggle-switch"></span>
                  <span className="toggle-text">Share LlamaFarm Projects</span>
                </label>
                <span className="item-hint">Specialized ML models</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Hardware Section */}
      <div className="config-section">
        <div className="section-header" onClick={() => toggleSection('hardware')}>
          <div className="section-title">
            <Cpu size={20} />
            <span>Hardware Resources</span>
          </div>
          <div className="section-toggle">
            {expandedSections.hardware ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
          </div>
        </div>
        
        {expandedSections.hardware && (
          <div className="section-content">
            <div className="config-item">
              <div className="item-header">
                <label className="toggle-label">
                  <input
                    type="checkbox"
                    checked={config?.hardware?.gpu?.enabled}
                    onChange={(e) => updateConfig('hardware.gpu.enabled', e.target.checked)}
                  />
                  <span className="toggle-switch"></span>
                  <span className="toggle-text">Share GPU</span>
                </label>
              </div>
              {config?.hardware?.gpu?.enabled && (
                <div className="slider-control">
                  <label>Max VRAM: {config?.hardware?.gpu?.max_vram_percent}%</label>
                  <input
                    type="range"
                    min="10"
                    max="100"
                    value={config?.hardware?.gpu?.max_vram_percent || 80}
                    onChange={(e) => updateConfig('hardware.gpu.max_vram_percent', parseInt(e.target.value))}
                  />
                </div>
              )}
            </div>
            
            <div className="config-item">
              <div className="item-header">
                <label className="toggle-label">
                  <input
                    type="checkbox"
                    checked={config?.hardware?.cpu?.enabled}
                    onChange={(e) => updateConfig('hardware.cpu.enabled', e.target.checked)}
                  />
                  <span className="toggle-switch"></span>
                  <span className="toggle-text">Share CPU Compute</span>
                </label>
                <span className="item-hint">Allow mesh jobs on CPU</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Privacy Section */}
      <div className="config-section privacy-section">
        <div className="section-header" onClick={() => toggleSection('privacy')}>
          <div className="section-title">
            <Lock size={20} />
            <span>Privacy-Sensitive</span>
            <span className="privacy-badge">Requires explicit consent</span>
          </div>
          <div className="section-toggle">
            {expandedSections.privacy ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
          </div>
        </div>
        
        {expandedSections.privacy && (
          <div className="section-content">
            <div className="privacy-warning">
              <AlertCircle size={16} />
              <span>These capabilities can access sensitive data. Enable only if you trust all mesh participants.</span>
            </div>
            
            {/* macOS Permission Status Banner */}
            {permissions?.platform === 'Darwin' && (
              <div className="macos-permissions-banner">
                <div className="banner-title">
                  <Lock size={16} />
                  macOS Permission Status
                </div>
                <div className="banner-hint">
                  macOS requires system-level permissions for these features. Click "Open Settings" to grant access.
                </div>
              </div>
            )}
            
            {/* Camera */}
            <div className="config-item privacy-item">
              <div className="item-header">
                <label className="toggle-label">
                  <input
                    type="checkbox"
                    checked={config?.privacy?.camera?.enabled}
                    onChange={(e) => updateConfig('privacy.camera.enabled', e.target.checked)}
                  />
                  <span className="toggle-switch danger"></span>
                  <span className="toggle-text">
                    <Camera size={16} />
                    Camera Access
                  </span>
                </label>
                <div className="permission-controls">
                  {cameraPermission && (
                    <>
                      <PermissionStatus status={cameraPermission.status} />
                      {cameraPermission.status !== 'granted' && cameraPermission.status !== 'not_applicable' && (
                        <button 
                          className="open-settings-btn"
                          onClick={() => openSettings('camera')}
                          title={cameraPermission.instructions}
                        >
                          <ExternalLink size={14} />
                          Open Settings
                        </button>
                      )}
                    </>
                  )}
                  {config?.privacy?.camera?.enabled ? (
                    <Eye size={18} className="status-icon enabled" />
                  ) : (
                    <EyeOff size={18} className="status-icon disabled" />
                  )}
                </div>
              </div>
              {config?.privacy?.camera?.enabled && cameraPermission?.status !== 'granted' && (
                <div className="permission-instructions">
                  <AlertCircle size={14} />
                  <span>{cameraPermission?.instructions || 'Grant camera permission in System Settings'}</span>
                </div>
              )}
              {config?.privacy?.camera?.enabled && cameraPermission?.status === 'granted' && (
                <div className="mode-selector">
                  <label>
                    <input
                      type="radio"
                      name="camera-mode"
                      value="snapshot"
                      checked={config?.privacy?.camera?.mode === 'snapshot'}
                      onChange={(e) => updateConfig('privacy.camera.mode', e.target.value)}
                    />
                    Snapshots only
                  </label>
                  <label>
                    <input
                      type="radio"
                      name="camera-mode"
                      value="stream"
                      checked={config?.privacy?.camera?.mode === 'stream'}
                      onChange={(e) => updateConfig('privacy.camera.mode', e.target.value)}
                    />
                    Full streaming
                  </label>
                </div>
              )}
            </div>
            
            {/* Microphone */}
            <div className="config-item privacy-item">
              <div className="item-header">
                <label className="toggle-label">
                  <input
                    type="checkbox"
                    checked={config?.privacy?.microphone?.enabled}
                    onChange={(e) => updateConfig('privacy.microphone.enabled', e.target.checked)}
                  />
                  <span className="toggle-switch danger"></span>
                  <span className="toggle-text">
                    <Mic size={16} />
                    Microphone Access
                  </span>
                </label>
                <div className="permission-controls">
                  {micPermission && (
                    <>
                      <PermissionStatus status={micPermission.status} />
                      {micPermission.status !== 'granted' && micPermission.status !== 'not_applicable' && (
                        <button 
                          className="open-settings-btn"
                          onClick={() => openSettings('microphone')}
                          title={micPermission.instructions}
                        >
                          <ExternalLink size={14} />
                          Open Settings
                        </button>
                      )}
                    </>
                  )}
                  {config?.privacy?.microphone?.enabled ? (
                    <Eye size={18} className="status-icon enabled" />
                  ) : (
                    <EyeOff size={18} className="status-icon disabled" />
                  )}
                </div>
              </div>
              {config?.privacy?.microphone?.enabled && micPermission?.status !== 'granted' && (
                <div className="permission-instructions">
                  <AlertCircle size={14} />
                  <span>{micPermission?.instructions || 'Grant microphone permission in System Settings'}</span>
                </div>
              )}
            </div>
            
            {/* Screen Recording */}
            <div className="config-item privacy-item">
              <div className="item-header">
                <label className="toggle-label">
                  <input
                    type="checkbox"
                    checked={config?.privacy?.screen?.enabled}
                    onChange={(e) => updateConfig('privacy.screen.enabled', e.target.checked)}
                  />
                  <span className="toggle-switch danger"></span>
                  <span className="toggle-text">
                    <Monitor size={16} />
                    Screen Capture
                  </span>
                </label>
                <div className="permission-controls">
                  {screenPermission && (
                    <>
                      <PermissionStatus status={screenPermission.status} />
                      {screenPermission.status !== 'granted' && screenPermission.status !== 'not_applicable' && (
                        <button 
                          className="open-settings-btn"
                          onClick={() => openSettings('screen_recording')}
                          title={screenPermission.instructions}
                        >
                          <ExternalLink size={14} />
                          Open Settings
                        </button>
                      )}
                    </>
                  )}
                  {config?.privacy?.screen?.enabled ? (
                    <Eye size={18} className="status-icon enabled" />
                  ) : (
                    <EyeOff size={18} className="status-icon disabled" />
                  )}
                </div>
              </div>
              {config?.privacy?.screen?.enabled && screenPermission?.status !== 'granted' && (
                <div className="permission-instructions">
                  <AlertCircle size={14} />
                  <span>{screenPermission?.instructions || 'Grant screen recording permission in System Settings'}</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Access Control Section */}
      <div className="config-section">
        <div className="section-header" onClick={() => toggleSection('access')}>
          <div className="section-title">
            <Users size={20} />
            <span>Access Control</span>
          </div>
          <div className="section-toggle">
            {expandedSections.access ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
          </div>
        </div>
        
        {expandedSections.access && (
          <div className="section-content">
            <div className="config-item">
              <div className="item-header">
                <label className="toggle-label">
                  <input
                    type="checkbox"
                    checked={config?.access?.rate_limit?.enabled}
                    onChange={(e) => updateConfig('access.rate_limit.enabled', e.target.checked)}
                  />
                  <span className="toggle-switch"></span>
                  <span className="toggle-text">Enable Rate Limiting</span>
                </label>
              </div>
              {config?.access?.rate_limit?.enabled && (
                <div className="slider-control">
                  <label>Max requests/min: {config?.access?.rate_limit?.requests_per_minute}</label>
                  <input
                    type="range"
                    min="10"
                    max="200"
                    value={config?.access?.rate_limit?.requests_per_minute || 60}
                    onChange={(e) => updateConfig('access.rate_limit.requests_per_minute', parseInt(e.target.value))}
                  />
                </div>
              )}
            </div>
            
            <div className="config-item">
              <div className="item-header">
                <span className="toggle-text">Mesh Allowlist</span>
                <span className="item-hint">Only allow specific mesh IDs (empty = allow all)</span>
              </div>
              <textarea
                className="list-input"
                placeholder="Enter mesh IDs, one per line..."
                value={config?.access?.mesh_allowlist?.join('\n') || ''}
                onChange={(e) => updateConfig('access.mesh_allowlist', e.target.value.split('\n').filter(Boolean))}
              />
            </div>
          </div>
        )}
      </div>

      {/* UI Settings Section */}
      <div className="config-section">
        <div className="section-header" onClick={() => toggleSection('ui')}>
          <div className="section-title">
            <Monitor size={20} />
            <span>UI Settings</span>
          </div>
          <div className="section-toggle">
            {expandedSections.ui ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
          </div>
        </div>
        
        {expandedSections.ui && (
          <div className="section-content">
            <div className="config-item">
              <div className="item-header">
                <label className="toggle-label">
                  <input
                    type="checkbox"
                    checked={demoMode}
                    onChange={(e) => onDemoModeChange?.(e.target.checked)}
                  />
                  <span className="toggle-switch"></span>
                  <span className="toggle-text">Demo Mode</span>
                </label>
                <span className="item-hint">Show sample data in feeds for demonstration</span>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="approval-footer">
        <div className="footer-summary">
          <Zap size={16} />
          <span>
            Sharing: 
            {config?.models?.ollama?.enabled && ' Ollama'}
            {config?.models?.llamafarm?.enabled && ' LlamaFarm'}
            {config?.hardware?.gpu?.enabled && ' GPU'}
            {config?.privacy?.camera?.enabled && ' Camera'}
            {config?.privacy?.microphone?.enabled && ' Mic'}
          </span>
        </div>
      </div>
    </div>
  );
};

export default ApprovalPanel;
