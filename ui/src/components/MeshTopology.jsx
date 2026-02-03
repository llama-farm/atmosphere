import React, { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import { Camera, Mic, Brain, Search, Eye, Wrench, Zap, ArrowUp, ArrowDown } from 'lucide-react';
import './MeshTopology.css';

// Capability type icons and colors
const CAPABILITY_TYPES = {
  'sensor/camera': { icon: '📷', color: '#10b981', label: 'Camera' },
  'sensor/voice': { icon: '🎤', color: '#f97316', label: 'Voice' },
  'llm': { icon: '🧠', color: '#8b5cf6', label: 'LLM' },
  'search': { icon: '🔍', color: '#3b82f6', label: 'Search' },
  'vision': { icon: '👁', color: '#ec4899', label: 'Vision' },
  'tool': { icon: '🔧', color: '#6b7280', label: 'Tool' },
  'default': { icon: '⚡', color: '#f59e0b', label: 'Capability' },
};

const STATUS_COLORS = {
  online: '#10b981',
  busy: '#f59e0b',
  degraded: '#ef4444',
  offline: '#6b7280',
  leader: '#f59e0b',
  active: '#3b82f6',
};

export const MeshTopology = ({ wsData }) => {
  const svgRef = useRef(null);
  const [nodes, setNodes] = useState([]);
  const [links, setLinks] = useState([]);
  const [hoveredNode, setHoveredNode] = useState(null);
  const simulationRef = useRef(null);

  useEffect(() => {
    // Fetch initial mesh topology
    fetch('/v1/mesh/topology')
      .then(res => res.json())
      .then(data => {
        const nodeData = data.nodes?.map((node, i) => ({
          id: node.id || `node-${i}`,
          name: node.name || `Node ${i + 1}`,
          capabilities: node.capabilities || [],
          capabilityTypes: node.capabilityTypes || [],
          triggers: node.triggers || [],
          tools: node.tools || [],
          status: node.status || 'active',
          x: Math.random() * 800,
          y: Math.random() * 600,
        })) || [];

        const linkData = data.connections?.map(conn => ({
          source: conn.from,
          target: conn.to,
          strength: conn.strength || 1,
        })) || [];

        setNodes(nodeData);
        setLinks(linkData);
      })
      .catch(err => {
        console.error('Failed to fetch topology:', err);
        // Create demo data with capability types
        const capTypes = ['sensor/camera', 'sensor/voice', 'llm', 'search', 'vision', 'tool'];
        const demoNodes = Array.from({ length: 8 }, (_, i) => ({
          id: `node-${i}`,
          name: `Node ${i + 1}`,
          capabilities: [`cap-${i}`, `cap-${i + 1}`],
          capabilityTypes: [capTypes[i % capTypes.length]],
          triggers: i % 2 === 0 ? ['motion_detected', 'sound_detected'] : ['query_complete'],
          tools: i % 3 === 0 ? ['get_frame', 'get_history'] : ['execute', 'search'],
          status: i % 4 === 0 ? 'leader' : i % 5 === 0 ? 'busy' : 'active',
          x: Math.random() * 800,
          y: Math.random() * 600,
        }));

        const demoLinks = Array.from({ length: 12 }, (_, i) => ({
          source: `node-${Math.floor(Math.random() * 8)}`,
          target: `node-${Math.floor(Math.random() * 8)}`,
          strength: Math.random(),
        }));

        setNodes(demoNodes);
        setLinks(demoLinks);
      });
  }, []);

  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return;

    const svg = d3.select(svgRef.current);
    const width = svgRef.current.clientWidth;
    const height = svgRef.current.clientHeight;

    // Clear previous content
    svg.selectAll('*').remove();

    // Create container group
    const g = svg.append('g');

    // Add zoom behavior
    const zoom = d3.zoom()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });

    svg.call(zoom);

    // Create force simulation
    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(d => d.id).distance(150))
      .force('charge', d3.forceManyBody().strength(-400))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(60));

    simulationRef.current = simulation;

    // Create links
    const link = g.append('g')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('class', 'mesh-link')
      .attr('stroke', '#374151')
      .attr('stroke-width', d => Math.max(1, d.strength * 3))
      .attr('stroke-opacity', 0.6);

    // Create nodes
    const node = g.append('g')
      .selectAll('g')
      .data(nodes)
      .join('g')
      .attr('class', 'mesh-node')
      .call(d3.drag()
        .on('start', dragstarted)
        .on('drag', dragged)
        .on('end', dragended));

    // Node circles with status-based styling
    node.append('circle')
      .attr('r', 30)
      .attr('fill', d => {
        switch (d.status) {
          case 'leader': return 'url(#gradient-leader)';
          case 'busy': return 'url(#gradient-busy)';
          case 'active': return 'url(#gradient-active)';
          default: return 'url(#gradient-inactive)';
        }
      })
      .attr('stroke', d => STATUS_COLORS[d.status] || '#6b7280')
      .attr('stroke-width', 2)
      .attr('class', d => d.status === 'leader' ? 'glow-node' : '');

    // Capability type icon (emoji) in center
    node.append('text')
      .text(d => {
        const capType = d.capabilityTypes?.[0] || 'default';
        return CAPABILITY_TYPES[capType]?.icon || CAPABILITY_TYPES.default.icon;
      })
      .attr('text-anchor', 'middle')
      .attr('dy', '-0.1em')
      .attr('font-size', '18px')
      .attr('pointer-events', 'none');

    // Node labels below
    node.append('text')
      .text(d => d.name)
      .attr('text-anchor', 'middle')
      .attr('dy', '2.8em')
      .attr('fill', '#f3f4f6')
      .attr('font-size', '10px')
      .attr('font-weight', '600')
      .attr('pointer-events', 'none');

    // Trigger badge (orange, top-left) - PUSH
    node.filter(d => d.triggers?.length > 0)
      .append('circle')
      .attr('cx', -22)
      .attr('cy', -22)
      .attr('r', 10)
      .attr('fill', '#f97316')
      .attr('stroke', '#0a0e1a')
      .attr('stroke-width', 2)
      .attr('class', 'badge-trigger');

    node.filter(d => d.triggers?.length > 0)
      .append('text')
      .text(d => d.triggers.length)
      .attr('x', -22)
      .attr('y', -22)
      .attr('text-anchor', 'middle')
      .attr('dy', '0.35em')
      .attr('fill', '#fff')
      .attr('font-size', '8px')
      .attr('font-weight', '700')
      .attr('pointer-events', 'none');

    // Tool badge (blue, top-right) - PULL
    node.filter(d => d.tools?.length > 0)
      .append('circle')
      .attr('cx', 22)
      .attr('cy', -22)
      .attr('r', 10)
      .attr('fill', '#3b82f6')
      .attr('stroke', '#0a0e1a')
      .attr('stroke-width', 2)
      .attr('class', 'badge-tool');

    node.filter(d => d.tools?.length > 0)
      .append('text')
      .text(d => d.tools.length)
      .attr('x', 22)
      .attr('y', -22)
      .attr('text-anchor', 'middle')
      .attr('dy', '0.35em')
      .attr('fill', '#fff')
      .attr('font-size', '8px')
      .attr('font-weight', '700')
      .attr('pointer-events', 'none');

    // Hover tooltip
    const tooltip = d3.select('body').append('div')
      .attr('class', 'mesh-tooltip')
      .style('opacity', 0)
      .style('position', 'absolute')
      .style('background', 'var(--bg-secondary)')
      .style('border', '1px solid var(--border-color)')
      .style('border-radius', '8px')
      .style('padding', '12px')
      .style('pointer-events', 'none')
      .style('z-index', 1000);

    node.on('mouseover', (event, d) => {
      const capType = d.capabilityTypes?.[0] || 'default';
      const typeInfo = CAPABILITY_TYPES[capType] || CAPABILITY_TYPES.default;
      
      tooltip.transition().duration(200).style('opacity', 1);
      tooltip.html(`
        <div style="font-weight: 700; margin-bottom: 6px;">${d.name}</div>
        <div style="font-size: 12px; color: ${typeInfo.color}; margin-bottom: 4px;">
          ${typeInfo.icon} ${typeInfo.label}
        </div>
        <div style="font-size: 11px; color: #9ca3af;">
          Status: <span style="color: ${STATUS_COLORS[d.status]}">${d.status}</span>
        </div>
        <div style="font-size: 11px; color: #f97316; margin-top: 4px;">
          ↑ ${d.triggers?.length || 0} triggers
        </div>
        <div style="font-size: 11px; color: #3b82f6;">
          ↓ ${d.tools?.length || 0} tools
        </div>
      `)
        .style('left', (event.pageX + 10) + 'px')
        .style('top', (event.pageY - 10) + 'px');
    })
    .on('mouseout', () => {
      tooltip.transition().duration(500).style('opacity', 0);
    });

    // Add gradients
    const defs = svg.append('defs');

    const gradientLeader = defs.append('linearGradient')
      .attr('id', 'gradient-leader')
      .attr('x1', '0%')
      .attr('y1', '0%')
      .attr('x2', '100%')
      .attr('y2', '100%');
    gradientLeader.append('stop').attr('offset', '0%').attr('stop-color', '#f59e0b');
    gradientLeader.append('stop').attr('offset', '100%').attr('stop-color', '#ef4444');

    const gradientActive = defs.append('linearGradient')
      .attr('id', 'gradient-active')
      .attr('x1', '0%')
      .attr('y1', '0%')
      .attr('x2', '100%')
      .attr('y2', '100%');
    gradientActive.append('stop').attr('offset', '0%').attr('stop-color', '#3b82f6');
    gradientActive.append('stop').attr('offset', '100%').attr('stop-color', '#8b5cf6');

    const gradientBusy = defs.append('linearGradient')
      .attr('id', 'gradient-busy')
      .attr('x1', '0%')
      .attr('y1', '0%')
      .attr('x2', '100%')
      .attr('y2', '100%');
    gradientBusy.append('stop').attr('offset', '0%').attr('stop-color', '#f59e0b');
    gradientBusy.append('stop').attr('offset', '100%').attr('stop-color', '#d97706');

    const gradientInactive = defs.append('linearGradient')
      .attr('id', 'gradient-inactive')
      .attr('x1', '0%')
      .attr('y1', '0%')
      .attr('x2', '100%')
      .attr('y2', '100%');
    gradientInactive.append('stop').attr('offset', '0%').attr('stop-color', '#374151');
    gradientInactive.append('stop').attr('offset', '100%').attr('stop-color', '#1f2937');

    // Update positions on each tick
    simulation.on('tick', () => {
      link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);

      node.attr('transform', d => `translate(${d.x},${d.y})`);
    });

    // Drag functions
    function dragstarted(event, d) {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      d.fx = d.x;
      d.fy = d.y;
    }

    function dragged(event, d) {
      d.fx = event.x;
      d.fy = event.y;
    }

    function dragended(event, d) {
      if (!event.active) simulation.alphaTarget(0);
      d.fx = null;
      d.fy = null;
    }

    // Cleanup
    return () => {
      simulation.stop();
      d3.selectAll('.mesh-tooltip').remove();
    };
  }, [nodes, links]);

  return (
    <div className="mesh-topology fade-in">
      <div className="topology-header">
        <h1>Mesh Topology</h1>
        <div className="topology-legend">
          <div className="legend-item">
            <div className="legend-circle leader"></div>
            <span>Leader</span>
          </div>
          <div className="legend-item">
            <div className="legend-circle active"></div>
            <span>Active</span>
          </div>
          <div className="legend-item">
            <div className="legend-circle busy"></div>
            <span>Busy</span>
          </div>
          <div className="legend-item">
            <div className="legend-badge trigger"></div>
            <span>Triggers (↑)</span>
          </div>
          <div className="legend-item">
            <div className="legend-badge tool"></div>
            <span>Tools (↓)</span>
          </div>
        </div>
      </div>
      <div className="topology-canvas">
        <svg ref={svgRef} width="100%" height="100%"></svg>
      </div>
      <div className="topology-hint">
        Drag nodes to reposition • Scroll to zoom • Click to inspect
      </div>
    </div>
  );
};
