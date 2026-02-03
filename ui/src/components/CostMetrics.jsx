import React, { useState, useEffect, useRef } from 'react';
import { Battery, BatteryCharging, Cpu, HardDrive, Wifi, WifiOff, Gauge, Zap, Clock, RefreshCw } from 'lucide-react';
import './CostMetrics.css';

export const CostMetrics = ({ refreshInterval = 20000 }) => {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [changedFields, setChangedFields] = useState(new Set());
  const prevMetricsRef = useRef(null);

  const detectChanges = (oldMetrics, newMetrics) => {
    if (!oldMetrics || !newMetrics) return new Set();
    
    const changes = new Set();
    
    // Power changes
    if (oldMetrics.power?.plugged_in !== newMetrics.power?.plugged_in) {
      changes.add('power');
    }
    if (Math.abs((oldMetrics.power?.battery_percent || 0) - (newMetrics.power?.battery_percent || 0)) > 2) {
      changes.add('power');
    }
    
    // CPU changes
    if (Math.abs((oldMetrics.compute?.cpu_load || 0) - (newMetrics.compute?.cpu_load || 0)) > 0.05) {
      changes.add('cpu');
    }
    
    // Memory changes
    if (Math.abs((oldMetrics.compute?.memory_percent || 0) - (newMetrics.compute?.memory_percent || 0)) > 2) {
      changes.add('memory');
    }
    
    // GPU changes
    if (Math.abs((oldMetrics.compute?.gpu_load || 0) - (newMetrics.compute?.gpu_load || 0)) > 5) {
      changes.add('gpu');
    }
    
    // Network changes
    if (oldMetrics.network?.is_metered !== newMetrics.network?.is_metered) {
      changes.add('network');
    }
    
    // Cost multiplier changes
    if (Math.abs((oldMetrics.cost_multiplier || 1) - (newMetrics.cost_multiplier || 1)) > 0.1) {
      changes.add('cost');
    }
    
    return changes;
  };

  const fetchMetrics = async () => {
    try {
      const response = await fetch('/api/cost/current');
      if (!response.ok) throw new Error('Failed to fetch metrics');
      const data = await response.json();
      
      // Detect changes from previous metrics
      const changes = detectChanges(prevMetricsRef.current, data);
      if (changes.size > 0) {
        setChangedFields(changes);
        // Clear change indicators after animation
        setTimeout(() => setChangedFields(new Set()), 1500);
      }
      
      prevMetricsRef.current = data;
      setMetrics(data);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      console.error('Cost metrics fetch failed:', err);
      setError(err.message);
      // Use fallback data
      setMetrics({
        power: { on_battery: false, battery_percent: 100, plugged_in: true },
        compute: { cpu_load: 0.15, gpu_load: 0, memory_percent: 45, memory_available_gb: 8 },
        network: { is_metered: false, bandwidth_mbps: null },
        cost_multiplier: 1.0,
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMetrics(); // Initial load
    const interval = setInterval(fetchMetrics, refreshInterval);
    return () => clearInterval(interval);
  }, [refreshInterval]);

  // WebSocket for real-time updates
  useEffect(() => {
    let ws = null;
    
    const connectWs = () => {
      try {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${window.location.host}/api/ws`);
        
        ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === 'cost_update' && msg.factors) {
              const data = {
                node_id: msg.node_id,
                timestamp: msg.timestamp,
                power: {
                  on_battery: msg.factors.on_battery,
                  battery_percent: msg.factors.battery_percent,
                  plugged_in: msg.factors.plugged_in,
                },
                compute: {
                  cpu_load: msg.factors.cpu_load,
                  gpu_load: msg.factors.gpu_load,
                  gpu_estimated: msg.factors.gpu_estimated,
                  memory_percent: msg.factors.memory_percent,
                  memory_available_gb: msg.factors.memory_available_gb,
                },
                network: {
                  bandwidth_mbps: msg.factors.bandwidth_mbps,
                  is_metered: msg.factors.is_metered,
                  latency_ms: msg.factors.latency_ms,
                },
                cost_multiplier: msg.cost,
              };
              
              // Detect and highlight changes
              const changes = detectChanges(prevMetricsRef.current, data);
              if (changes.size > 0) {
                setChangedFields(changes);
                setTimeout(() => setChangedFields(new Set()), 1500);
              }
              
              prevMetricsRef.current = data;
              setMetrics(data);
              setLastUpdated(new Date());
            }
          } catch (e) {
            console.error('Failed to parse WS message:', e);
          }
        };
        
        ws.onerror = () => {
          console.log('WebSocket error, falling back to polling');
        };
        
        ws.onclose = () => {
          // Reconnect after 5 seconds
          setTimeout(connectWs, 5000);
        };
      } catch (e) {
        console.log('WebSocket not available, using polling only');
      }
    };
    
    connectWs();
    
    return () => {
      if (ws) ws.close();
    };
  }, []);

  const formatLastUpdated = () => {
    if (!lastUpdated) return 'Never';
    const seconds = Math.floor((new Date() - lastUpdated) / 1000);
    if (seconds < 5) return 'Just now';
    if (seconds < 60) return `${seconds}s ago`;
    return `${Math.floor(seconds / 60)}m ago`;
  };

  if (loading && !metrics) {
    return (
      <div className="cost-metrics loading">
        <div className="loading-spinner"></div>
      </div>
    );
  }

  const { power, compute, network, cost_multiplier } = metrics || {};

  const getCostColor = (multiplier) => {
    if (multiplier <= 1.2) return '#10b981'; // Green - cheap
    if (multiplier <= 2.0) return '#f59e0b'; // Yellow - moderate
    if (multiplier <= 3.0) return '#f97316'; // Orange - expensive
    return '#ef4444'; // Red - very expensive
  };

  const getLoadColor = (percent) => {
    if (percent < 50) return '#10b981';
    if (percent < 75) return '#f59e0b';
    return '#ef4444';
  };

  const getBatteryIcon = () => {
    if (power?.plugged_in) {
      return <BatteryCharging size={20} className="battery-charging" />;
    }
    return <Battery size={20} />;
  };

  const getBatteryColor = () => {
    if (power?.plugged_in) return '#10b981';
    if (power?.battery_percent > 50) return '#10b981';
    if (power?.battery_percent > 20) return '#f59e0b';
    return '#ef4444';
  };

  return (
    <div className="cost-metrics fade-in">
      <div className="metrics-header">
        <h3>
          <Gauge size={18} />
          Node Health
        </h3>
        <div className="header-right">
          <div className={`cost-badge ${changedFields.has('cost') ? 'pulse-highlight' : ''}`}
            style={{ backgroundColor: getCostColor(cost_multiplier) + '22', color: getCostColor(cost_multiplier) }}
          >
            <Zap size={14} />
            {cost_multiplier?.toFixed(1)}x cost
          </div>
          <div className="last-updated" title={lastUpdated?.toLocaleTimeString()}>
            <Clock size={12} />
            <span>{formatLastUpdated()}</span>
          </div>
        </div>
      </div>

      <div className="metrics-grid">
        {/* Power Status */}
        <div className={`metric-card power-card ${changedFields.has('power') ? 'pulse-highlight' : ''}`}>
          <div className="metric-icon" style={{ color: getBatteryColor() }}>
            {getBatteryIcon()}
          </div>
          <div className="metric-content">
            <div className="metric-label">Power</div>
            <div className="metric-value">
              {power?.plugged_in ? (
                <span className="status-good">Plugged In</span>
              ) : (
                <span style={{ color: getBatteryColor() }}>
                  {power?.battery_percent?.toFixed(0)}%
                </span>
              )}
            </div>
          </div>
          {!power?.plugged_in && (
            <div className="metric-bar">
              <div 
                className="bar-fill battery-bar"
                style={{ 
                  width: `${power?.battery_percent || 0}%`,
                  backgroundColor: getBatteryColor(),
                }}
              />
            </div>
          )}
        </div>

        {/* CPU Load */}
        <div className={`metric-card cpu-card ${changedFields.has('cpu') ? 'pulse-highlight' : ''}`}>
          <div className="metric-icon" style={{ color: getLoadColor(compute?.cpu_load * 100) }}>
            <Cpu size={20} />
          </div>
          <div className="metric-content">
            <div className="metric-label">CPU Load</div>
            <div className="metric-value">
              {((compute?.cpu_load || 0) * 100).toFixed(0)}%
            </div>
          </div>
          <div className="metric-bar">
            <div 
              className="bar-fill"
              style={{ 
                width: `${Math.min((compute?.cpu_load || 0) * 100, 100)}%`,
                backgroundColor: getLoadColor(compute?.cpu_load * 100),
              }}
            />
          </div>
        </div>

        {/* Memory */}
        <div className={`metric-card memory-card ${changedFields.has('memory') ? 'pulse-highlight' : ''}`}>
          <div className="metric-icon" style={{ color: getLoadColor(compute?.memory_percent) }}>
            <HardDrive size={20} />
          </div>
          <div className="metric-content">
            <div className="metric-label">Memory</div>
            <div className="metric-value">
              {compute?.memory_percent?.toFixed(0)}%
              <span className="metric-subvalue">
                ({compute?.memory_available_gb?.toFixed(1)}GB free)
              </span>
            </div>
          </div>
          <div className="metric-bar">
            <div 
              className="bar-fill"
              style={{ 
                width: `${compute?.memory_percent || 0}%`,
                backgroundColor: getLoadColor(compute?.memory_percent),
              }}
            />
          </div>
        </div>

        {/* GPU (if available) */}
        {compute?.gpu_load > 0 && (
          <div className={`metric-card gpu-card ${changedFields.has('gpu') ? 'pulse-highlight' : ''}`}>
            <div className="metric-icon" style={{ color: getLoadColor(compute?.gpu_load) }}>
              <Zap size={20} />
            </div>
            <div className="metric-content">
              <div className="metric-label">
                GPU {compute?.gpu_estimated && <span className="est-badge">est</span>}
              </div>
              <div className="metric-value">
                {compute?.gpu_load?.toFixed(0)}%
              </div>
            </div>
            <div className="metric-bar">
              <div 
                className="bar-fill"
                style={{ 
                  width: `${compute?.gpu_load || 0}%`,
                  backgroundColor: getLoadColor(compute?.gpu_load),
                }}
              />
            </div>
          </div>
        )}

        {/* Network */}
        <div className={`metric-card network-card ${changedFields.has('network') ? 'pulse-highlight' : ''}`}>
          <div className="metric-icon" style={{ color: network?.is_metered ? '#f59e0b' : '#10b981' }}>
            {network?.is_metered ? <WifiOff size={20} /> : <Wifi size={20} />}
          </div>
          <div className="metric-content">
            <div className="metric-label">Network</div>
            <div className="metric-value">
              {network?.is_metered ? (
                <span className="status-warning">Metered</span>
              ) : (
                <span className="status-good">Unmetered</span>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="cost-explanation">
        <div className="explanation-title">Cost Multiplier Breakdown</div>
        <div className="explanation-factors">
          <div className="factor">
            <span className="factor-name">Power:</span>
            <span className="factor-value">{power?.plugged_in ? '1.0x' : (power?.battery_percent > 50 ? '2.0x' : '3.0x')}</span>
          </div>
          <div className="factor">
            <span className="factor-name">CPU:</span>
            <span className="factor-value">{compute?.cpu_load > 0.75 ? '2.0x' : compute?.cpu_load > 0.5 ? '1.6x' : '1.0x'}</span>
          </div>
          <div className="factor">
            <span className="factor-name">Memory:</span>
            <span className="factor-value">{compute?.memory_percent > 90 ? '2.5x' : compute?.memory_percent > 80 ? '1.5x' : '1.0x'}</span>
          </div>
        </div>
      </div>
      
      <div className="refresh-indicator">
        <RefreshCw size={12} className={loading ? 'spin' : ''} />
        <span>Auto-refresh every {refreshInterval / 1000}s</span>
      </div>
    </div>
  );
};

export default CostMetrics;
