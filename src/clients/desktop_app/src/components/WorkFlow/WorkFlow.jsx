/**
 * WorkFlow Component
 *
 * Multi-agent workflow visualization using React Flow.
 * Displays agents as nodes in a horizontal scrollable canvas.
 *
 * Features:
 * - Horizontal scrolling with wheel and navigation buttons
 * - Agent nodes with expandable details
 * - Edit mode for drag-and-drop layout
 * - Viewport clamping to prevent over-scrolling
 *
 * Ported from Eigent's WorkFlow component.
 */

import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import {
  ReactFlow,
  useNodesState,
  useReactFlow,
  ReactFlowProvider,
  PanOnScrollMode,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import WorkFlowNode from './WorkFlowNode';
import Icon from '../Icons';

// Node type mapping for React Flow
const nodeTypes = {
  agentNode: WorkFlowNode,
};

// Default agent configurations
const DEFAULT_AGENTS = [
  {
    agent_id: 'browser_agent',
    name: 'Browser Agent',
    type: 'browser',
    tools: ['Search Toolkit', 'Browser Toolkit', 'Screenshot Toolkit'],
    tasks: [],
    status: 'idle',
  },
  {
    agent_id: 'developer_agent',
    name: 'Developer Agent',
    type: 'coder',
    tools: ['Terminal Toolkit', 'Code Toolkit', 'Deploy Toolkit'],
    tasks: [],
    status: 'idle',
  },
  {
    agent_id: 'document_agent',
    name: 'Document Agent',
    type: 'document',
    tools: ['File Toolkit', 'Excel Toolkit', 'PPT Toolkit'],
    tasks: [],
    status: 'idle',
  },
];

// Node dimensions
const NODE_WIDTH_COLLAPSED = 320;
const NODE_WIDTH_EXPANDED = 640;
const NODE_SPACING = 20;
const NODE_Y_POSITION = 16;
const VIEWPORT_ANIMATION_DURATION = 300;

function WorkFlowInner({
  agents = [],
  activeAgentId = null,
  currentTools = {},
  toolkitEventsByAgent = {},
  screenshotsByAgent = {},
  showDefaultAgents = true,
  isEditMode: externalEditMode = null,
  onAgentClick,
  onEditModeChange,
}) {
  const containerRef = useRef(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [isEditMode, setIsEditMode] = useState(false);
  const [isAnimating, setIsAnimating] = useState(false);
  const { setViewport, getViewport } = useReactFlow();

  // Sync edit mode with external control
  useEffect(() => {
    if (externalEditMode !== null) {
      setIsEditMode(externalEditMode);
    }
  }, [externalEditMode]);

  // Track container width
  useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        setContainerWidth(containerRef.current.clientWidth);
      }
    };

    updateWidth();
    window.addEventListener('resize', updateWidth);
    return () => window.removeEventListener('resize', updateWidth);
  }, []);

  // Calculate total width of all nodes
  const totalNodesWidth = useMemo(() => {
    if (!nodes.length) return 0;

    const widths = nodes.map((node) =>
      node.data.isExpanded ? NODE_WIDTH_EXPANDED : NODE_WIDTH_COLLAPSED
    );
    const spacing = Math.max(nodes.length - 1, 0) * NODE_SPACING;

    return widths.reduce((sum, width) => sum + width, 0) + spacing + 32; // padding
  }, [nodes]);

  // Calculate minimum viewport X (prevent scrolling past content)
  const minViewportX = useMemo(() => {
    if (!containerWidth) return 0;
    const contentWidth = Math.max(totalNodesWidth, containerWidth);
    return Math.min(0, containerWidth - contentWidth);
  }, [containerWidth, totalNodesWidth]);

  // Clamp viewport X to valid range
  const clampViewportX = useCallback(
    (x) => Math.min(0, Math.max(minViewportX, x)),
    [minViewportX]
  );

  // Handle node expansion change
  const handleExpandChange = useCallback(
    (nodeId, isExpanded) => {
      setNodes((prev) => {
        if (isEditMode) {
          // In edit mode, just update expansion state
          return prev.map((node) => ({
            ...node,
            data: {
              ...node.data,
              isExpanded: node.id === nodeId ? isExpanded : node.data.isExpanded,
            },
          }));
        } else {
          // In view mode, recalculate positions
          let currentX = 8;
          return prev.map((node) => {
            const updatedExpanded = node.id === nodeId ? isExpanded : node.data.isExpanded;
            const nodeWidth = updatedExpanded ? NODE_WIDTH_EXPANDED : NODE_WIDTH_COLLAPSED;
            const newPosition = { x: currentX, y: NODE_Y_POSITION };
            currentX += nodeWidth + NODE_SPACING;

            return {
              ...node,
              position: newPosition,
              data: {
                ...node.data,
                isExpanded: updatedExpanded,
              },
            };
          });
        }
      });
    },
    [setNodes, isEditMode]
  );

  // Reset node positions (for exiting edit mode)
  const resetNodePositions = useCallback(() => {
    setNodes((prev) => {
      let currentX = 8;
      return prev.map((node) => {
        const nodeWidth = node.data.isExpanded ? NODE_WIDTH_EXPANDED : NODE_WIDTH_COLLAPSED;
        const newPosition = { x: currentX, y: NODE_Y_POSITION };
        currentX += nodeWidth + NODE_SPACING;

        return {
          ...node,
          position: newPosition,
        };
      });
    });
  }, [setNodes]);

  // Update nodes when agents change
  useEffect(() => {
    setNodes((prev) => {
      // Merge default agents with provided agents
      const baseAgents = showDefaultAgents
        ? DEFAULT_AGENTS.filter(
            (defaultAgent) => !agents.find((a) => a.type === defaultAgent.type)
          )
        : [];
      const allAgents = [...baseAgents, ...agents];

      return allAgents.map((agent, index) => {
        const existingNode = prev.find((n) => n.id === agent.agent_id);
        const isExpanded = existingNode?.data?.isExpanded || false;
        const nodeWidth = isExpanded ? NODE_WIDTH_EXPANDED : NODE_WIDTH_COLLAPSED;

        return {
          id: agent.agent_id,
          type: 'agentNode',
          position: existingNode && isEditMode
            ? existingNode.position
            : { x: index * (NODE_WIDTH_COLLAPSED + NODE_SPACING) + 8, y: NODE_Y_POSITION },
          data: {
            agent,
            isExpanded,
            isActive: agent.agent_id === activeAgentId,
            currentTool: currentTools[agent.agent_id],
            toolkitEvents: toolkitEventsByAgent[agent.agent_id] || [],
            screenshots: screenshotsByAgent[agent.agent_id] || [],
            onExpandChange: handleExpandChange,
            onClick: () => onAgentClick && onAgentClick(agent),
          },
        };
      });
    });

    // Reset positions if not in edit mode
    if (!isEditMode) {
      resetNodePositions();
    }
  }, [
    agents,
    activeAgentId,
    currentTools,
    toolkitEventsByAgent,
    screenshotsByAgent,
    showDefaultAgents,
    isEditMode,
    handleExpandChange,
    onAgentClick,
    setNodes,
    resetNodePositions,
  ]);

  // Reset positions when exiting edit mode
  useEffect(() => {
    if (!isEditMode) {
      resetNodePositions();
      setViewport({ x: 0, y: 0, zoom: 1 }, { duration: VIEWPORT_ANIMATION_DURATION });
    }
  }, [isEditMode, resetNodePositions, setViewport]);

  // Handle wheel scroll (horizontal in view mode)
  useEffect(() => {
    const container = document.querySelector('.workflow-container .react-flow__pane');
    if (!container) return;

    const onWheel = (e) => {
      if (!isEditMode && e.deltaY !== 0) {
        e.preventDefault();
        const { x, y, zoom } = getViewport();
        const nextX = clampViewportX(x - e.deltaY);
        setViewport({ x: nextX, y, zoom }, { duration: 0 });
      }
    };

    container.addEventListener('wheel', onWheel, { passive: false });
    return () => container.removeEventListener('wheel', onWheel);
  }, [getViewport, setViewport, isEditMode, clampViewportX]);

  // Move viewport by delta
  const moveViewport = useCallback(
    (dx) => {
      if (isAnimating) return;

      const viewport = getViewport();
      setIsAnimating(true);

      const newX = clampViewportX(viewport.x + dx);
      setViewport(
        { x: newX, y: viewport.y, zoom: viewport.zoom },
        { duration: VIEWPORT_ANIMATION_DURATION }
      );

      setTimeout(() => setIsAnimating(false), VIEWPORT_ANIMATION_DURATION);
    },
    [isAnimating, getViewport, setViewport, clampViewportX]
  );

  // Toggle edit mode
  const handleToggleEditMode = useCallback(() => {
    const newEditMode = !isEditMode;
    setIsEditMode(newEditMode);

    if (newEditMode) {
      // Enter edit mode - zoom out
      setViewport({ x: 0, y: 0, zoom: 0.6 }, { duration: VIEWPORT_ANIMATION_DURATION });
    }

    if (onEditModeChange) {
      onEditModeChange(newEditMode);
    }
  }, [isEditMode, setViewport, onEditModeChange]);

  // Handle viewport move (clamp X)
  const handleMove = useCallback(
    (event, viewport) => {
      if (!isEditMode) {
        const clampedX = clampViewportX(viewport.x);
        if (clampedX !== viewport.x) {
          setViewport({ ...viewport, x: clampedX });
        }
      }
    },
    [isEditMode, clampViewportX, setViewport]
  );

  return (
    <div className="workflow-component">
      {/* Header */}
      <div className="workflow-header">
        <div className="workflow-header-left">
          <span className="workflow-icon">🤖</span>
          <span className="workflow-title">AI Workforce</span>
          <span className="workflow-count">{nodes.length} agents</span>
        </div>
        <div className="workflow-header-right">
          {/* Edit mode toggle */}
          <button
            className={`workflow-btn ${isEditMode ? 'active' : ''}`}
            onClick={handleToggleEditMode}
            title={isEditMode ? 'Exit Edit Mode' : 'Enter Edit Mode'}
          >
            <Icon name="edit" size={16} />
          </button>

          {/* Navigation buttons */}
          <div className="workflow-nav">
            <button
              className="nav-btn"
              onClick={() => moveViewport(200)}
              disabled={isAnimating}
              title="Scroll Left"
            >
              <Icon name="chevronLeft" size={16} />
            </button>
            <button
              className="nav-btn"
              onClick={() => moveViewport(-200)}
              disabled={isAnimating}
              title="Scroll Right"
            >
              <Icon name="chevronRight" size={16} />
            </button>
          </div>
        </div>
      </div>

      {/* React Flow Canvas */}
      <div className="workflow-container" ref={containerRef}>
        <ReactFlow
          nodes={nodes}
          edges={[]}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onMove={handleMove}
          proOptions={{ hideAttribution: true }}
          zoomOnScroll={isEditMode}
          zoomOnPinch={isEditMode}
          zoomOnDoubleClick={isEditMode}
          panOnDrag={isEditMode}
          panOnScroll={!isEditMode}
          nodesDraggable={isEditMode}
          panOnScrollMode={PanOnScrollMode.Horizontal}
          minZoom={0.3}
          maxZoom={1.5}
          fitView={false}
          defaultViewport={{ x: 0, y: 0, zoom: 1 }}
        />
      </div>

      {/* Edit mode indicator */}
      {isEditMode && (
        <div className="edit-mode-indicator">
          <span>Edit Mode</span>
          <span className="hint">Drag nodes to rearrange</span>
        </div>
      )}
    </div>
  );
}

// Wrapper component with ReactFlowProvider
function WorkFlow(props) {
  return (
    <ReactFlowProvider>
      <WorkFlowInner {...props} />
    </ReactFlowProvider>
  );
}

export default WorkFlow;
