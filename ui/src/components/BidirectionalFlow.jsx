import React, { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import { Camera, ArrowUp, ArrowDown, Brain, Zap, Wrench } from 'lucide-react';
import './BidirectionalFlow.css';

export const BidirectionalFlow = ({ events = [], onEventComplete }) => {
  const svgRef = useRef(null);
  const [activeFlows, setActiveFlows] = useState([]);

  // Demo flow for visualization
  useEffect(() => {
    if (!svgRef.current) return;

    const svg = d3.select(svgRef.current);
    const width = svgRef.current.clientWidth || 600;
    const height = svgRef.current.clientHeight || 400;

    svg.selectAll('*').remove();

    // Define positions
    const positions = {
      capability: { x: width * 0.15, y: height * 0.5 },
      mesh: { x: width * 0.5, y: height * 0.15 },
      agent: { x: width * 0.85, y: height * 0.5 },
    };

    // Create main group
    const g = svg.append('g');

    // Add gradient definitions
    const defs = svg.append('defs');

    // Trigger gradient (orange - going UP)
    const triggerGradient = defs.append('linearGradient')
      .attr('id', 'trigger-gradient')
      .attr('gradientUnits', 'userSpaceOnUse')
      .attr('x1', positions.capability.x)
      .attr('y1', positions.capability.y)
      .attr('x2', positions.mesh.x)
      .attr('y2', positions.mesh.y);
    triggerGradient.append('stop').attr('offset', '0%').attr('stop-color', '#f97316');
    triggerGradient.append('stop').attr('offset', '100%').attr('stop-color', '#fb923c');

    // Tool gradient (blue - going DOWN)
    const toolGradient = defs.append('linearGradient')
      .attr('id', 'tool-gradient')
      .attr('gradientUnits', 'userSpaceOnUse')
      .attr('x1', positions.agent.x)
      .attr('y1', positions.agent.y)
      .attr('x2', positions.capability.x)
      .attr('y2', positions.capability.y);
    toolGradient.append('stop').attr('offset', '0%').attr('stop-color', '#3b82f6');
    toolGradient.append('stop').attr('offset', '100%').attr('stop-color', '#60a5fa');

    // Draw arrow marker for trigger (UP)
    defs.append('marker')
      .attr('id', 'arrow-trigger')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 8)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', '#f97316');

    // Draw arrow marker for tool (DOWN)
    defs.append('marker')
      .attr('id', 'arrow-tool')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 8)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', '#3b82f6');

    // Glow filter
    const filter = defs.append('filter')
      .attr('id', 'glow')
      .attr('x', '-50%')
      .attr('y', '-50%')
      .attr('width', '200%')
      .attr('height', '200%');
    filter.append('feGaussianBlur')
      .attr('stdDeviation', '3')
      .attr('result', 'coloredBlur');
    const feMerge = filter.append('feMerge');
    feMerge.append('feMergeNode').attr('in', 'coloredBlur');
    feMerge.append('feMergeNode').attr('in', 'SourceGraphic');

    // Draw static paths (curved)
    // Path: Capability → Mesh (trigger path)
    const triggerPath = g.append('path')
      .attr('d', `M${positions.capability.x},${positions.capability.y} 
                  Q${(positions.capability.x + positions.mesh.x) / 2},${positions.capability.y - 80}
                  ${positions.mesh.x},${positions.mesh.y}`)
      .attr('fill', 'none')
      .attr('stroke', 'url(#trigger-gradient)')
      .attr('stroke-width', 2)
      .attr('stroke-dasharray', '8,4')
      .attr('opacity', 0.4)
      .attr('class', 'flow-path trigger-path');

    // Path: Mesh → Agent
    const meshAgentPath = g.append('path')
      .attr('d', `M${positions.mesh.x},${positions.mesh.y}
                  Q${(positions.mesh.x + positions.agent.x) / 2},${positions.mesh.y + 80}
                  ${positions.agent.x},${positions.agent.y}`)
      .attr('fill', 'none')
      .attr('stroke', 'var(--border-color)')
      .attr('stroke-width', 2)
      .attr('stroke-dasharray', '8,4')
      .attr('opacity', 0.3);

    // Path: Agent → Capability (tool path - going back)
    const toolPath = g.append('path')
      .attr('d', `M${positions.agent.x},${positions.agent.y + 30}
                  Q${width * 0.5},${height * 0.85}
                  ${positions.capability.x},${positions.capability.y + 30}`)
      .attr('fill', 'none')
      .attr('stroke', 'url(#tool-gradient)')
      .attr('stroke-width', 2)
      .attr('stroke-dasharray', '8,4')
      .attr('opacity', 0.4)
      .attr('class', 'flow-path tool-path');

    // Draw nodes
    // Capability node
    const capNode = g.append('g')
      .attr('transform', `translate(${positions.capability.x},${positions.capability.y})`)
      .attr('class', 'flow-node');

    capNode.append('circle')
      .attr('r', 45)
      .attr('fill', 'var(--bg-tertiary)')
      .attr('stroke', '#10b981')
      .attr('stroke-width', 3);

    capNode.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', '-0.5em')
      .attr('fill', '#10b981')
      .attr('font-size', '24px')
      .text('📷');

    capNode.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', '1.5em')
      .attr('fill', 'var(--text-primary)')
      .attr('font-size', '12px')
      .attr('font-weight', '600')
      .text('Capability');

    // Mesh node
    const meshNode = g.append('g')
      .attr('transform', `translate(${positions.mesh.x},${positions.mesh.y})`)
      .attr('class', 'flow-node');

    meshNode.append('circle')
      .attr('r', 40)
      .attr('fill', 'var(--bg-tertiary)')
      .attr('stroke', '#8b5cf6')
      .attr('stroke-width', 3);

    meshNode.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', '-0.5em')
      .attr('fill', '#8b5cf6')
      .attr('font-size', '24px')
      .text('🌐');

    meshNode.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', '1.5em')
      .attr('fill', 'var(--text-primary)')
      .attr('font-size', '12px')
      .attr('font-weight', '600')
      .text('Mesh');

    // Agent node
    const agentNode = g.append('g')
      .attr('transform', `translate(${positions.agent.x},${positions.agent.y})`)
      .attr('class', 'flow-node');

    agentNode.append('circle')
      .attr('r', 45)
      .attr('fill', 'var(--bg-tertiary)')
      .attr('stroke', '#3b82f6')
      .attr('stroke-width', 3);

    agentNode.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', '-0.5em')
      .attr('fill', '#3b82f6')
      .attr('font-size', '24px')
      .text('🤖');

    agentNode.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', '1.5em')
      .attr('fill', 'var(--text-primary)')
      .attr('font-size', '12px')
      .attr('font-weight', '600')
      .text('Agent');

    // Labels for flow directions
    g.append('text')
      .attr('x', (positions.capability.x + positions.mesh.x) / 2 - 20)
      .attr('y', positions.capability.y - 80)
      .attr('fill', '#f97316')
      .attr('font-size', '11px')
      .attr('font-weight', '600')
      .text('TRIGGER ↑');

    g.append('text')
      .attr('x', width * 0.5)
      .attr('y', height * 0.85 + 20)
      .attr('text-anchor', 'middle')
      .attr('fill', '#3b82f6')
      .attr('font-size', '11px')
      .attr('font-weight', '600')
      .text('← TOOL CALL →');

    // Animation function for flowing particles
    const animateParticle = (path, color, isReverse = false) => {
      const pathNode = path.node();
      const pathLength = pathNode.getTotalLength();

      const particle = g.append('circle')
        .attr('r', 6)
        .attr('fill', color)
        .attr('filter', 'url(#glow)')
        .attr('class', 'flow-particle');

      const startOffset = isReverse ? pathLength : 0;
      const endOffset = isReverse ? 0 : pathLength;

      const animate = () => {
        particle
          .attr('opacity', 1)
          .transition()
          .duration(2000)
          .ease(d3.easeLinear)
          .attrTween('transform', () => {
            return (t) => {
              const offset = isReverse ? pathLength * (1 - t) : pathLength * t;
              const point = pathNode.getPointAtLength(offset);
              return `translate(${point.x},${point.y})`;
            };
          })
          .on('end', () => {
            particle.attr('opacity', 0);
            setTimeout(animate, 1000 + Math.random() * 2000);
          });
      };

      setTimeout(animate, Math.random() * 2000);
    };

    // Start particle animations
    animateParticle(triggerPath, '#f97316', false);
    animateParticle(toolPath, '#3b82f6', false);

    // Add second set of particles with delay
    setTimeout(() => {
      animateParticle(triggerPath, '#fb923c', false);
      animateParticle(toolPath, '#60a5fa', false);
    }, 1500);

  }, []);

  return (
    <div className="bidirectional-flow fade-in">
      <div className="flow-header">
        <h2>Bidirectional Flow</h2>
        <div className="flow-legend">
          <div className="legend-item">
            <ArrowUp size={14} color="#f97316" />
            <span>Triggers (PUSH)</span>
          </div>
          <div className="legend-item">
            <ArrowDown size={14} color="#3b82f6" />
            <span>Tools (PULL)</span>
          </div>
        </div>
      </div>

      <div className="flow-canvas">
        <svg ref={svgRef} width="100%" height="100%" />
      </div>

      <div className="flow-info">
        <div className="info-card trigger-info">
          <div className="info-icon">
            <Zap size={20} />
          </div>
          <div className="info-content">
            <div className="info-title">PUSH (Triggers)</div>
            <div className="info-desc">Capability fires events into the mesh when something happens</div>
          </div>
        </div>
        <div className="info-card tool-info">
          <div className="info-icon">
            <Wrench size={20} />
          </div>
          <div className="info-content">
            <div className="info-title">PULL (Tools)</div>
            <div className="info-desc">Agent calls capability tools to get data or perform actions</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default BidirectionalFlow;
