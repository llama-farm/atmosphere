import React, { useState, useEffect, useRef } from 'react';
import { Eye, Upload, Image as ImageIcon, Download, Zap, AlertCircle, CheckCircle } from 'lucide-react';
import './VisionPanel.css';

function VisionPanel() {
  const [selectedImage, setSelectedImage] = useState(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [detectionResults, setDetectionResults] = useState(null);
  const [isDetecting, setIsDetecting] = useState(false);
  const [error, setError] = useState(null);
  const [availableModels, setAvailableModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState('general_coco');
  const [detectionHistory, setDetectionHistory] = useState([]);
  
  const canvasRef = useRef(null);
  const fileInputRef = useRef(null);

  // Load available models on mount
  useEffect(() => {
    loadAvailableModels();
  }, []);

  // Draw bounding boxes when detection results change
  useEffect(() => {
    if (selectedImage && detectionResults && canvasRef.current) {
      drawBoundingBoxes();
    }
  }, [selectedImage, detectionResults]);

  const loadAvailableModels = async () => {
    try {
      const response = await fetch('/api/vision/models');
      const data = await response.json();
      setAvailableModels(data.models || []);
    } catch (err) {
      console.error('Failed to load models:', err);
    }
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file && file.type.startsWith('image/')) {
      setSelectedFile(file);
      const reader = new FileReader();
      reader.onload = (e) => {
        setSelectedImage(e.target.result);
        setDetectionResults(null);
        setError(null);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) {
      setSelectedFile(file);
      const reader = new FileReader();
      reader.onload = (e) => {
        setSelectedImage(e.target.result);
        setDetectionResults(null);
        setError(null);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
  };

  const runDetection = async () => {
    if (!selectedFile) {
      setError('No image selected');
      return;
    }

    setIsDetecting(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('model_id', selectedModel);
      formData.append('confidence_threshold', '0.25');

      const response = await fetch('/api/vision/detect', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        throw new Error(`Detection failed: ${response.statusText}`);
      }

      const result = await response.json();
      setDetectionResults(result);
      
      // Add to history
      const historyEntry = {
        timestamp: new Date().toISOString(),
        model: selectedModel,
        detections: result.detections || [],
        inference_time_ms: result.inference_time_ms || 0
      };
      setDetectionHistory(prev => [historyEntry, ...prev].slice(0, 10));

    } catch (err) {
      setError(err.message);
      console.error('Detection error:', err);
    } finally {
      setIsDetecting(false);
    }
  };

  const drawBoundingBoxes = () => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const img = new Image();
    
    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;
      ctx.drawImage(img, 0, 0);

      if (detectionResults && detectionResults.detections) {
        detectionResults.detections.forEach((detection, idx) => {
          const bbox = detection.bbox;
          const color = `hsl(${(idx * 137.5) % 360}, 70%, 50%)`;
          
          // Draw rectangle
          ctx.strokeStyle = color;
          ctx.lineWidth = 3;
          ctx.strokeRect(bbox.x1, bbox.y1, bbox.x2 - bbox.x1, bbox.y2 - bbox.y1);
          
          // Draw label background
          ctx.fillStyle = color;
          const label = `${detection.class_name} ${(detection.confidence * 100).toFixed(0)}%`;
          const textWidth = ctx.measureText(label).width;
          ctx.fillRect(bbox.x1, bbox.y1 - 25, textWidth + 10, 25);
          
          // Draw label text
          ctx.fillStyle = 'white';
          ctx.font = '16px sans-serif';
          ctx.fillText(label, bbox.x1 + 5, bbox.y1 - 7);
        });
      }
    };
    
    img.src = selectedImage;
  };

  return (
    <div className="vision-panel">
      <div className="vision-header">
        <Eye className="vision-icon" />
        <h2>Vision Detection</h2>
      </div>

      <div className="vision-content">
        {/* Model selector and status */}
        <div className="vision-controls">
          <div className="model-selector">
            <label>Model:</label>
            <select 
              value={selectedModel} 
              onChange={(e) => setSelectedModel(e.target.value)}
              disabled={isDetecting}
            >
              <option value="general_coco">General COCO (80 classes)</option>
              <option value="military_aircraft">Military Aircraft (10 classes)</option>
            </select>
          </div>
          
          <div className="model-info">
            {availableModels.length > 0 && (
              <span className="model-count">
                <CheckCircle size={16} />
                {availableModels.length} models available
              </span>
            )}
          </div>
        </div>

        {/* Upload area */}
        <div 
          className="upload-area"
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onClick={() => fileInputRef.current?.click()}
        >
          {selectedImage ? (
            <div className="image-preview">
              <canvas ref={canvasRef} />
            </div>
          ) : (
            <div className="upload-prompt">
              <ImageIcon size={48} />
              <p>Drag & drop an image or click to browse</p>
              <p className="upload-hint">Supports JPG, PNG, JPEG</p>
            </div>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleFileSelect}
            style={{ display: 'none' }}
          />
        </div>

        {/* Detect button */}
        {selectedImage && (
          <button
            className="detect-button"
            onClick={runDetection}
            disabled={isDetecting}
          >
            {isDetecting ? (
              <>
                <div className="spinner" />
                Detecting...
              </>
            ) : (
              <>
                <Zap size={16} />
                Detect Objects
              </>
            )}
          </button>
        )}

        {/* Error message */}
        {error && (
          <div className="error-message">
            <AlertCircle size={16} />
            {error}
          </div>
        )}

        {/* Detection results */}
        {detectionResults && (
          <div className="detection-results">
            <h3>Detection Results</h3>
            <div className="results-summary">
              <div className="result-stat">
                <span className="stat-label">Objects Found:</span>
                <span className="stat-value">{detectionResults.detections?.length || 0}</span>
              </div>
              <div className="result-stat">
                <span className="stat-label">Inference Time:</span>
                <span className="stat-value">{detectionResults.inference_time_ms?.toFixed(0) || 0}ms</span>
              </div>
              <div className="result-stat">
                <span className="stat-label">Model:</span>
                <span className="stat-value">{detectionResults.model_id || selectedModel}</span>
              </div>
            </div>

            {detectionResults.detections && detectionResults.detections.length > 0 && (
              <div className="detections-list">
                <h4>Detected Objects:</h4>
                {detectionResults.detections.map((det, idx) => (
                  <div key={idx} className="detection-item">
                    <span className="detection-class">{det.class_name}</span>
                    <span className="detection-confidence">
                      {(det.confidence * 100).toFixed(1)}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Detection history */}
        {detectionHistory.length > 0 && (
          <div className="detection-history">
            <h3>Recent Detections</h3>
            <div className="history-list">
              {detectionHistory.map((entry, idx) => (
                <div key={idx} className="history-item">
                  <div className="history-time">
                    {new Date(entry.timestamp).toLocaleTimeString()}
                  </div>
                  <div className="history-details">
                    <span>{entry.detections.length} objects</span>
                    <span className="history-model">{entry.model}</span>
                    <span className="history-time-ms">{entry.inference_time_ms}ms</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Available models section */}
        <div className="models-section">
          <h3>Available Models</h3>
          <div className="models-list">
            {availableModels.length === 0 ? (
              <p className="no-models">No models available</p>
            ) : (
              availableModels.map((model, idx) => (
                <div key={idx} className="model-card">
                  <div className="model-header">
                    <span className="model-name">{model.name || model.model_id}</span>
                    <button 
                      className="download-button"
                      onClick={() => window.location.href = `/api/vision/models/${model.model_id}/download`}
                      title="Download model"
                    >
                      <Download size={16} />
                    </button>
                  </div>
                  <div className="model-info-grid">
                    <div className="model-info-item">
                      <span className="info-label">Classes:</span>
                      <span className="info-value">{model.num_classes || model.classes?.length}</span>
                    </div>
                    <div className="model-info-item">
                      <span className="info-label">Input Size:</span>
                      <span className="info-value">{model.input_size?.[0] || model.input_size}×{model.input_size?.[1] || model.input_size}</span>
                    </div>
                    <div className="model-info-item">
                      <span className="info-label">Format:</span>
                      <span className="info-value">{model.format || 'onnx'}</span>
                    </div>
                    <div className="model-info-item">
                      <span className="info-label">Size:</span>
                      <span className="info-value">{model.file_size_mb || 0}MB</span>
                    </div>
                  </div>
                  {model.description && (
                    <p className="model-description">{model.description}</p>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default VisionPanel;
