import React, { useState, useEffect } from 'react';
import { Download, Upload, File, CheckCircle2, XCircle, Loader, RefreshCw } from 'lucide-react';
import { useDaemon } from '../hooks/useDaemon';
import './BlobTransfer.css';

export const BlobTransfer = () => {
  const { isConnected } = useDaemon();
  const [transfers, setTransfers] = useState([]);
  const [availableBlobs, setAvailableBlobs] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchBlobStatus = async () => {
    if (!isConnected) {
      setLoading(false);
      return;
    }

    try {
      // Fetch active transfers
      const transfersRes = await fetch('http://localhost:11462/api/blobs/transfers');
      if (transfersRes.ok) {
        const transfersData = await transfersRes.json();
        setTransfers(transfersData.transfers || []);
      }

      // Fetch available blobs
      const blobsRes = await fetch('http://localhost:11462/api/blobs/available');
      if (blobsRes.ok) {
        const blobsData = await blobsRes.json();
        setAvailableBlobs(blobsData.blobs || []);
      }
    } catch (err) {
      console.error('Failed to fetch blob status:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBlobStatus();
    const interval = setInterval(fetchBlobStatus, 2000); // Refresh every 2s for active transfers
    return () => clearInterval(interval);
  }, [isConnected]);

  const formatBytes = (bytes) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

  const formatSpeed = (bytesPerSec) => {
    if (!bytesPerSec) return '';
    return `${formatBytes(bytesPerSec)}/s`;
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'complete':
      case 'completed':
        return '#10b981';
      case 'failed':
      case 'error':
        return '#ef4444';
      case 'downloading':
      case 'uploading':
      case 'in_progress':
        return '#3b82f6';
      default:
        return '#6b7280';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'complete':
      case 'completed':
        return <CheckCircle2 size={20} color="#10b981" />;
      case 'failed':
      case 'error':
        return <XCircle size={20} color="#ef4444" />;
      case 'downloading':
        return <Download size={20} color="#3b82f6" className="pulse" />;
      case 'uploading':
        return <Upload size={20} color="#3b82f6" className="pulse" />;
      default:
        return <Loader size={20} color="#6b7280" className="spin" />;
    }
  };

  if (!isConnected) {
    return (
      <div className="blob-transfer fade-in">
        <div className="blob-header">
          <h3>Blob Transfer</h3>
        </div>
        <div className="daemon-offline">
          <File size={48} opacity={0.3} />
          <p>Daemon offline</p>
          <span>Connect to daemon to view blob transfers</span>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="blob-transfer fade-in">
        <div className="blob-header">
          <h3>Blob Transfer</h3>
        </div>
        <div className="blob-loading">
          <Loader className="spin" size={32} />
          <p>Loading blob status...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="blob-transfer fade-in">
      <div className="blob-header">
        <h3>
          <File size={20} />
          Blob Transfer
        </h3>
        <button className="refresh-btn" onClick={fetchBlobStatus}>
          <RefreshCw size={16} />
        </button>
      </div>

      {/* Active Transfers */}
      {transfers.length > 0 && (
        <div className="blob-section">
          <h4>Active Transfers</h4>
          <div className="transfers-list">
            {transfers.map((transfer, idx) => (
              <div key={idx} className="transfer-item">
                <div className="transfer-icon">
                  {getStatusIcon(transfer.status)}
                </div>
                <div className="transfer-info">
                  <div className="transfer-filename">{transfer.filename || transfer.blob_id}</div>
                  <div className="transfer-details">
                    <span>{transfer.peer_name || transfer.peer_id?.substring(0, 8)}</span>
                    <span>{formatBytes(transfer.bytes_transferred || 0)} / {formatBytes(transfer.total_bytes || 0)}</span>
                    <span>{formatSpeed(transfer.speed)}</span>
                  </div>
                  {transfer.progress !== undefined && (
                    <div className="transfer-progress">
                      <div 
                        className="progress-bar"
                        style={{ 
                          width: `${transfer.progress * 100}%`,
                          backgroundColor: getStatusColor(transfer.status)
                        }}
                      />
                    </div>
                  )}
                </div>
                <div className="transfer-status" style={{ color: getStatusColor(transfer.status) }}>
                  {transfer.status}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Available Blobs */}
      <div className="blob-section">
        <h4>Available Blobs ({availableBlobs.length})</h4>
        {availableBlobs.length === 0 ? (
          <div className="empty-state">
            <File size={32} opacity={0.3} />
            <p>No blobs available</p>
          </div>
        ) : (
          <div className="blobs-grid">
            {availableBlobs.map((blob, idx) => (
              <div key={idx} className="blob-item">
                <File size={24} />
                <div className="blob-info">
                  <div className="blob-name">{blob.name || blob.id}</div>
                  <div className="blob-meta">
                    <span>{formatBytes(blob.size)}</span>
                    {blob.mime_type && <span>{blob.mime_type}</span>}
                    {blob.node_id && <span>{blob.node_id.substring(0, 8)}</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {transfers.length === 0 && availableBlobs.length === 0 && (
        <div className="empty-state">
          <File size={48} opacity={0.3} />
          <p>No active transfers or blobs</p>
          <span>Blob transfers will appear here</span>
        </div>
      )}
    </div>
  );
};

export default BlobTransfer;
