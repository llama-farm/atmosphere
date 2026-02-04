import React, { useState, useEffect, useCallback } from 'react';
import { 
  Network, 
  Wifi, 
  Radio, 
  Bluetooth, 
  ChevronRight,
  Check,
  X,
  Trash2,
  RefreshCw,
  Star,
  Clock,
  Users,
  Globe
} from 'lucide-react';
import './MeshManager.css';

const API_BASE = import.meta.env.VITE_API_BASE || '';

export function MeshManager({ wsData }) {
  const [meshes, setMeshes] = useState([]);
  const [activeMeshId, setActiveMeshId] = useState(null);
  const [currentMeshId, setCurrentMeshId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchMeshes = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/meshes`);
      if (!response.ok) throw new Error('Failed to fetch meshes');
      const data = await response.json();
      setMeshes(data.meshes || []);
      setActiveMeshId(data.active_mesh_id);
      setCurrentMeshId(data.current_mesh_id);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMeshes();
    const interval = setInterval(fetchMeshes, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, [fetchMeshes]);

  const activateMesh = async (meshId) => {
    try {
      const response = await fetch(`${API_BASE}/api/meshes/${meshId}/activate`, {
        method: 'POST',
      });
      if (!response.ok) throw new Error('Failed to activate mesh');
      fetchMeshes();
    } catch (err) {
      setError(err.message);
    }
  };

  const forgetMesh = async (meshId) => {
    if (!confirm('Are you sure you want to forget this mesh?')) return;
    
    try {
      const response = await fetch(`${API_BASE}/api/meshes/${meshId}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error('Failed to forget mesh');
      fetchMeshes();
    } catch (err) {
      setError(err.message);
    }
  };

  const formatTime = (timestamp) => {
    if (!timestamp) return 'Never';
    const date = new Date(timestamp * 1000);
    return date.toLocaleString();
  };

  if (loading) {
    return (
      <div className="mesh-manager loading">
        <RefreshCw className="spin" size={24} />
        <span>Loading saved meshes...</span>
      </div>
    );
  }

  return (
    <div className="mesh-manager">
      <div className="mesh-manager-header">
        <h3>
          <Network size={20} />
          Saved Meshes
        </h3>
        <button className="refresh-btn" onClick={fetchMeshes}>
          <RefreshCw size={16} />
        </button>
      </div>

      {error && (
        <div className="mesh-error">
          <X size={16} />
          {error}
        </div>
      )}

      {meshes.length === 0 ? (
        <div className="no-meshes">
          <Globe size={32} />
          <p>No saved meshes yet</p>
          <small>Join or create a mesh to get started</small>
        </div>
      ) : (
        <div className="mesh-list">
          {meshes.map((mesh) => (
            <div 
              key={mesh.mesh_id}
              className={`mesh-item ${mesh.is_active ? 'active' : ''} ${mesh.is_connected ? 'connected' : ''}`}
            >
              <div className="mesh-icon">
                {mesh.is_connected ? (
                  <Wifi className="connected-icon" size={24} />
                ) : mesh.is_active ? (
                  <Star className="active-icon" size={24} />
                ) : (
                  <Network size={24} />
                )}
              </div>
              
              <div className="mesh-info">
                <div className="mesh-name">
                  {mesh.mesh_name}
                  {mesh.is_founder && <span className="founder-badge">Founder</span>}
                </div>
                <div className="mesh-id">{mesh.mesh_id.substring(0, 16)}...</div>
                <div className="mesh-meta">
                  <span className="meta-item">
                    <Users size={12} />
                    {mesh.peer_count} peers
                  </span>
                  <span className="meta-item">
                    <Clock size={12} />
                    {formatTime(mesh.last_connected)}
                  </span>
                </div>
              </div>

              <div className="mesh-status">
                {mesh.is_connected ? (
                  <span className="status-badge connected">
                    <Check size={12} /> Connected
                  </span>
                ) : mesh.is_active ? (
                  <span className="status-badge active">
                    <Star size={12} /> Active
                  </span>
                ) : (
                  <span className="status-badge inactive">Saved</span>
                )}
              </div>

              <div className="mesh-actions">
                {!mesh.is_active && (
                  <button 
                    className="action-btn activate"
                    onClick={() => activateMesh(mesh.mesh_id)}
                    title="Set as active mesh"
                  >
                    <Star size={16} />
                  </button>
                )}
                <button 
                  className="action-btn forget"
                  onClick={() => forgetMesh(mesh.mesh_id)}
                  title="Forget this mesh"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default MeshManager;
