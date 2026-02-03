import React, { useState, useEffect } from 'react';
import { Folder, Play, ChevronRight, RefreshCw, Eye, EyeOff } from 'lucide-react';

export function ProjectsPanel() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedProject, setSelectedProject] = useState(null);
  const [testPrompt, setTestPrompt] = useState('');
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const fetchProjects = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = showAll ? '' : '?discoverable_only=true';
      const response = await fetch(`/api/projects${params}`);
      if (!response.ok) throw new Error('Failed to fetch projects');
      const data = await response.json();
      setProjects(data.projects || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, [showAll]);

  const testProject = async (projectId) => {
    if (!testPrompt.trim()) return;
    
    setTesting(true);
    setTestResult(null);
    
    try {
      const startTime = Date.now();
      const response = await fetch(`/api/projects/${projectId}/invoke`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: testPrompt })
      });
      const data = await response.json();
      const latency = Date.now() - startTime;
      
      setTestResult({
        success: data.success,
        response: data.response,
        latency,
        usage: data.usage
      });
    } catch (err) {
      setTestResult({ success: false, error: err.message });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="panel projects-panel">
      <div className="panel-header">
        <h2><Folder size={20} /> LlamaFarm Projects</h2>
        <div className="header-actions">
          <button 
            className={`toggle-btn ${showAll ? 'active' : ''}`}
            onClick={() => setShowAll(!showAll)}
            title={showAll ? 'Show discoverable only' : 'Show all projects'}
          >
            {showAll ? <Eye size={16} /> : <EyeOff size={16} />}
            {showAll ? 'All' : 'Discoverable'}
          </button>
          <button className="refresh-btn" onClick={fetchProjects} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'spinning' : ''} />
          </button>
        </div>
      </div>

      {error && (
        <div className="error-message">
          {error}
          <p className="error-hint">Make sure LlamaFarm is running on port 14345</p>
        </div>
      )}

      <div className="projects-list">
        {projects.length === 0 && !loading && (
          <div className="empty-state">
            <Folder size={48} />
            <p>No projects found</p>
            <p className="hint">
              {showAll 
                ? 'LlamaFarm has no projects configured'
                : 'No projects in the "discoverable" namespace'}
            </p>
          </div>
        )}

        {projects.map(project => (
          <div 
            key={project.id}
            className={`project-card ${selectedProject?.id === project.id ? 'selected' : ''}`}
            onClick={() => setSelectedProject(project)}
          >
            <div className="project-header">
              <div className="project-name">
                <Folder size={16} />
                {project.name}
              </div>
              <div className={`project-badge ${project.mesh_exposed ? 'exposed' : ''}`}>
                {project.mesh_exposed ? '🌐 Mesh Exposed' : 'Local Only'}
              </div>
            </div>
            
            <div className="project-meta">
              <span className="namespace">{project.namespace || 'default'}</span>
              <span className="type">{project.type}</span>
            </div>
            
            {project.description && (
              <p className="project-description">{project.description}</p>
            )}
            
            {project.system_prompt && (
              <div className="system-prompt">
                <strong>System:</strong> {project.system_prompt}
              </div>
            )}
            
            <div className="project-capabilities">
              {project.capabilities?.map(cap => (
                <span key={cap} className="capability-tag">{cap}</span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {selectedProject && (
        <div className="test-section">
          <h3>Test Project: {selectedProject.name}</h3>
          <div className="test-input">
            <input
              type="text"
              placeholder="Enter a test prompt..."
              value={testPrompt}
              onChange={(e) => setTestPrompt(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && testProject(selectedProject.id)}
            />
            <button 
              onClick={() => testProject(selectedProject.id)}
              disabled={testing || !testPrompt.trim()}
            >
              {testing ? <RefreshCw size={16} className="spinning" /> : <Play size={16} />}
              {testing ? 'Running...' : 'Test'}
            </button>
          </div>
          
          {testResult && (
            <div className={`test-result ${testResult.success ? 'success' : 'error'}`}>
              {testResult.success ? (
                <>
                  <div className="result-header">
                    <span className="status">✅ Success</span>
                    <span className="latency">{testResult.latency}ms</span>
                  </div>
                  <div className="result-content">{testResult.response}</div>
                  {testResult.usage && (
                    <div className="result-usage">
                      Tokens: {testResult.usage.total_tokens || 'N/A'}
                    </div>
                  )}
                </>
              ) : (
                <div className="result-error">❌ {testResult.error}</div>
              )}
            </div>
          )}
        </div>
      )}

      <style>{`
        .projects-panel {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        
        .panel-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        
        .header-actions {
          display: flex;
          gap: 8px;
        }
        
        .toggle-btn, .refresh-btn {
          display: flex;
          align-items: center;
          gap: 4px;
          padding: 6px 12px;
          border: 1px solid #333;
          border-radius: 4px;
          background: transparent;
          color: #888;
          cursor: pointer;
        }
        
        .toggle-btn.active {
          background: rgba(76, 175, 80, 0.2);
          border-color: #4caf50;
          color: #4caf50;
        }
        
        .spinning {
          animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        
        .projects-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
          max-height: 400px;
          overflow-y: auto;
        }
        
        .project-card {
          padding: 16px;
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid #333;
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.2s;
        }
        
        .project-card:hover {
          border-color: #555;
          background: rgba(255, 255, 255, 0.04);
        }
        
        .project-card.selected {
          border-color: #7c3aed;
          background: rgba(124, 58, 237, 0.1);
        }
        
        .project-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
        }
        
        .project-name {
          display: flex;
          align-items: center;
          gap: 8px;
          font-weight: 600;
        }
        
        .project-badge {
          font-size: 12px;
          padding: 2px 8px;
          border-radius: 4px;
          background: rgba(255, 255, 255, 0.1);
        }
        
        .project-badge.exposed {
          background: rgba(76, 175, 80, 0.2);
          color: #4caf50;
        }
        
        .project-meta {
          display: flex;
          gap: 12px;
          font-size: 12px;
          color: #888;
          margin-bottom: 8px;
        }
        
        .project-description {
          font-size: 14px;
          color: #aaa;
          margin-bottom: 8px;
        }
        
        .system-prompt {
          font-size: 12px;
          color: #666;
          padding: 8px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 4px;
          margin-bottom: 8px;
          white-space: pre-wrap;
        }
        
        .project-capabilities {
          display: flex;
          gap: 6px;
          flex-wrap: wrap;
        }
        
        .capability-tag {
          font-size: 11px;
          padding: 2px 6px;
          background: rgba(124, 58, 237, 0.2);
          border-radius: 4px;
          color: #a78bfa;
        }
        
        .empty-state {
          text-align: center;
          padding: 40px;
          color: #666;
        }
        
        .empty-state svg {
          margin-bottom: 16px;
          opacity: 0.5;
        }
        
        .hint {
          font-size: 12px;
          color: #555;
        }
        
        .test-section {
          padding: 16px;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 8px;
        }
        
        .test-section h3 {
          margin-bottom: 12px;
        }
        
        .test-input {
          display: flex;
          gap: 8px;
        }
        
        .test-input input {
          flex: 1;
          padding: 10px 12px;
          border: 1px solid #333;
          border-radius: 4px;
          background: transparent;
          color: #fff;
        }
        
        .test-input button {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 10px 16px;
          background: #7c3aed;
          border: none;
          border-radius: 4px;
          color: white;
          cursor: pointer;
        }
        
        .test-input button:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        
        .test-result {
          margin-top: 12px;
          padding: 12px;
          border-radius: 4px;
        }
        
        .test-result.success {
          background: rgba(76, 175, 80, 0.1);
          border: 1px solid rgba(76, 175, 80, 0.3);
        }
        
        .test-result.error {
          background: rgba(244, 67, 54, 0.1);
          border: 1px solid rgba(244, 67, 54, 0.3);
        }
        
        .result-header {
          display: flex;
          justify-content: space-between;
          margin-bottom: 8px;
        }
        
        .result-content {
          white-space: pre-wrap;
          font-size: 14px;
        }
        
        .result-usage {
          margin-top: 8px;
          font-size: 12px;
          color: #888;
        }
        
        .error-message {
          padding: 12px;
          background: rgba(244, 67, 54, 0.1);
          border: 1px solid rgba(244, 67, 54, 0.3);
          border-radius: 4px;
          color: #f44336;
        }
        
        .error-hint {
          font-size: 12px;
          margin-top: 4px;
          opacity: 0.8;
        }
      `}</style>
    </div>
  );
}
