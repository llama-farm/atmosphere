import React, { useState, useEffect, useCallback } from 'react';
import { 
  Route, 
  ArrowRight, 
  Wifi, 
  Radio, 
  Bluetooth, 
  Globe,
  Clock,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Activity,
  Zap,
  AlertCircle
} from 'lucide-react';
import './RoutingTable.css';

const API_BASE = import.meta.env.VITE_API_BASE || '';

const TRANSPORT_ICONS = {
  lan: Wifi,
  relay: Globe,
  ble: Bluetooth,
  wifi_direct: Radio,
  matter: Activity,
};

const TRANSPORT_COLORS = {
  lan: '#a6e3a1',      // Green - local/fast
  relay: '#89b4fa',    // Blue - cloud relay
  ble: '#cba6f7',      // Purple - bluetooth
  wifi_direct: '#fab387', // Orange - wifi direct
  matter: '#f9e2af',   // Yellow - matter protocol
};

export function RoutingTable({ wsData }) {
  const [routes, setRoutes] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState({});
  const [sortBy, setSortBy] = useState('cost'); // cost, hops, latency

  const fetchRoutes = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/routing`);
      if (!response.ok) throw new Error('Failed to fetch routing table');
      const data = await response.json();
      setRoutes(data.routes || []);
      setStats(data.stats);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRoutes();
    const interval = setInterval(fetchRoutes, 10000); // Refresh every 10s
    return () => clearInterval(interval);
  }, [fetchRoutes]);

  const toggleExpand = (dest) => {
    setExpanded(prev => ({ ...prev, [dest]: !prev[dest] }));
  };

  const sortedRoutes = [...routes].sort((a, b) => {
    switch (sortBy) {
      case 'hops': return a.hop_count - b.hop_count;
      case 'latency': return a.latency_ms - b.latency_ms;
      default: return a.cost - b.cost;
    }
  });

  // Group routes by destination
  const routesByDest = sortedRoutes.reduce((acc, route) => {
    if (!acc[route.destination]) {
      acc[route.destination] = [];
    }
    acc[route.destination].push(route);
    return acc;
  }, {});

  const formatLatency = (ms) => {
    if (ms < 10) return `${ms.toFixed(1)}ms`;
    return `${Math.round(ms)}ms`;
  };

  const getCostClass = (cost) => {
    if (cost < 0.3) return 'excellent';
    if (cost < 0.6) return 'good';
    if (cost < 0.9) return 'fair';
    return 'poor';
  };

  const formatTime = (timestamp) => {
    const diff = (Date.now() / 1000) - timestamp;
    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
  };

  if (loading) {
    return (
      <div className="routing-table loading">
        <RefreshCw className="spin" size={24} />
        <span>Loading routing table...</span>
      </div>
    );
  }

  return (
    <div className="routing-table">
      <div className="routing-header">
        <h3>
          <Route size={20} />
          Routing Table
        </h3>
        <div className="routing-controls">
          <select 
            value={sortBy} 
            onChange={(e) => setSortBy(e.target.value)}
            className="sort-select"
          >
            <option value="cost">Sort by Cost</option>
            <option value="hops">Sort by Hops</option>
            <option value="latency">Sort by Latency</option>
          </select>
          <button className="refresh-btn" onClick={fetchRoutes}>
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {error && (
        <div className="routing-error">
          <AlertCircle size={16} />
          {error}
        </div>
      )}

      {stats && (
        <div className="routing-stats">
          <div className="stat-item">
            <span className="stat-value">{stats.total_routes}</span>
            <span className="stat-label">Total Routes</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{stats.active_routes}</span>
            <span className="stat-label">Active</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{stats.unique_destinations}</span>
            <span className="stat-label">Destinations</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{stats.route_lookups}</span>
            <span className="stat-label">Lookups</span>
          </div>
        </div>
      )}

      {Object.keys(routesByDest).length === 0 ? (
        <div className="no-routes">
          <Route size={32} />
          <p>No routes discovered yet</p>
          <small>Routes will appear as peers are discovered</small>
        </div>
      ) : (
        <div className="routes-list">
          {Object.entries(routesByDest).map(([dest, destRoutes]) => {
            const bestRoute = destRoutes[0];
            const hasAlternatives = destRoutes.length > 1;
            const isExpanded = expanded[dest];
            const TransportIcon = TRANSPORT_ICONS[bestRoute.transport] || Globe;

            return (
              <div key={dest} className="route-group">
                <div 
                  className={`route-item best ${hasAlternatives ? 'expandable' : ''}`}
                  onClick={() => hasAlternatives && toggleExpand(dest)}
                >
                  <div 
                    className="transport-indicator"
                    style={{ backgroundColor: TRANSPORT_COLORS[bestRoute.transport] }}
                  >
                    <TransportIcon size={16} />
                  </div>

                  <div className="route-path">
                    <div className="destination">
                      {dest.substring(0, 12)}...
                      {hasAlternatives && (
                        <span className="alt-count">+{destRoutes.length - 1}</span>
                      )}
                    </div>
                    <div className="via">
                      via {bestRoute.next_hop.substring(0, 8)}
                      <ArrowRight size={12} />
                      {bestRoute.transport}
                    </div>
                  </div>

                  <div className="route-metrics">
                    <div className="metric">
                      <span className="metric-value">{bestRoute.hop_count}</span>
                      <span className="metric-label">hops</span>
                    </div>
                    <div className="metric">
                      <span className="metric-value">{formatLatency(bestRoute.latency_ms)}</span>
                      <span className="metric-label">latency</span>
                    </div>
                    <div className={`metric cost ${getCostClass(bestRoute.cost)}`}>
                      <span className="metric-value">{bestRoute.cost.toFixed(2)}</span>
                      <span className="metric-label">cost</span>
                    </div>
                  </div>

                  <div className="route-reliability">
                    <div 
                      className="reliability-bar"
                      style={{ width: `${bestRoute.reliability * 100}%` }}
                    />
                    <span>{Math.round(bestRoute.reliability * 100)}%</span>
                  </div>

                  <div className="route-time">
                    <Clock size={12} />
                    {formatTime(bestRoute.last_updated)}
                  </div>

                  {hasAlternatives && (
                    <div className="expand-icon">
                      {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </div>
                  )}
                </div>

                {isExpanded && (
                  <div className="alternative-routes">
                    {destRoutes.slice(1).map((route, idx) => {
                      const AltIcon = TRANSPORT_ICONS[route.transport] || Globe;
                      return (
                        <div key={idx} className="route-item alt">
                          <div 
                            className="transport-indicator"
                            style={{ backgroundColor: TRANSPORT_COLORS[route.transport] }}
                          >
                            <AltIcon size={14} />
                          </div>

                          <div className="route-path">
                            <div className="via">
                              via {route.next_hop.substring(0, 8)}
                              <ArrowRight size={12} />
                              {route.transport}
                            </div>
                          </div>

                          <div className="route-metrics">
                            <div className="metric">
                              <span className="metric-value">{route.hop_count}</span>
                              <span className="metric-label">hops</span>
                            </div>
                            <div className="metric">
                              <span className="metric-value">{formatLatency(route.latency_ms)}</span>
                            </div>
                            <div className={`metric cost ${getCostClass(route.cost)}`}>
                              <span className="metric-value">{route.cost.toFixed(2)}</span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default RoutingTable;
