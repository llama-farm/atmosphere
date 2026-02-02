import React, { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import './MeshTopology.css';

export const MeshTopology = ({ wsData }) => {
  const svgRef = useRef(null);
  const [nodes, setNodes] = useState([]);
  const [links, setLinks] = useState([]);
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
        // Create demo data
        const demoNodes = Array.from({ length: 8 }, (_, i) => ({
          id: `node-${i}`,
          name: `Node ${i + 1}`,
          capabilities: [`cap-${i}`, `cap-${i + 1}`],
          status: i % 4 === 0 ? 'leader' : 'active',
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

    // Node circles
    node.append('circle')
      .attr('r', 30)
      .attr('fill', d => {
        switch (d.status) {
          case 'leader': return 'url(#gradient-leader)';
          case 'active': return 'url(#gradient-active)';
          default: return 'url(#gradient-inactive)';
        }
      })
      .attr('stroke', d => {
        switch (d.status) {
          case 'leader': return '#f59e0b';
          case 'active': return '#3b82f6';
          default: return '#6b7280';
        }
      })
      .attr('stroke-width', 2)
      .attr('class', d => d.status === 'leader' ? 'glow-node' : '');

    // Node labels
    node.append('text')
      .text(d => d.name)
      .attr('text-anchor', 'middle')
      .attr('dy', '0.35em')
      .attr('fill', '#f3f4f6')
      .attr('font-size', '12px')
      .attr('font-weight', '600')
      .attr('pointer-events', 'none');

    // Capability count badge
    node.append('circle')
      .attr('cx', 20)
      .attr('cy', -20)
      .attr('r', 12)
      .attr('fill', '#8b5cf6')
      .attr('stroke', '#0a0e1a')
      .attr('stroke-width', 2);

    node.append('text')
      .text(d => d.capabilities.length)
      .attr('x', 20)
      .attr('y', -20)
      .attr('text-anchor', 'middle')
      .attr('dy', '0.35em')
      .attr('fill', '#f3f4f6')
      .attr('font-size', '10px')
      .attr('font-weight', '700')
      .attr('pointer-events', 'none');

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
            <div className="legend-badge"></div>
            <span>Capabilities</span>
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
