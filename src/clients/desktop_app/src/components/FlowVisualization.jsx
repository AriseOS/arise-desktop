import React, { useMemo, useState, useCallback, useEffect } from 'react';
import ReactFlow, {
    useNodesState,
    useEdgesState,
    Controls,
    Background,
    MiniMap
} from 'reactflow';
import 'reactflow/dist/style.css';
import CustomNode from './CustomNode';
import GroupNode from './GroupNode';
import SimpleFloatingEdge from './SimpleFloatingEdge';
import { transformWorkflowData, transformMetaflowData } from '../utils/flowLayout';
import yaml from 'js-yaml';

const nodeTypes = {
    custom: CustomNode,
    group: GroupNode
};

const edgeTypes = {
    floating: SimpleFloatingEdge,
};

const FlowVisualization = ({ data, type = 'workflow' }) => {
    // State for Collapsible Loops
    const [expandedNodeIds, setExpandedNodeIds] = useState(new Set());

    const onToggleExpand = useCallback((nodeId) => {
        setExpandedNodeIds(prev => {
            const next = new Set(prev);
            if (next.has(nodeId)) {
                next.delete(nodeId);
            } else {
                next.add(nodeId);
            }
            return next;
        });
    }, []);

    // Transform data to ReactFlow format
    const { nodes: computedNodes, edges: computedEdges } = useMemo(() => {
        // Unified parsing logic
        if (data?.workflow_yaml) {
            try {
                const parsed = yaml.load(data.workflow_yaml);
                // Version check: reject v1 format
                if (parsed.apiVersion === 'ami.io/v1' || parsed.kind === 'Workflow') {
                    console.error("v1 格式已不再支持，请将 workflow 升级到 v2 格式");
                    return { nodes: [], edges: [] };
                }
                return transformWorkflowData(parsed, expandedNodeIds, onToggleExpand);
            } catch (e) {
                console.error("YAML Parse Error", e);
                return { nodes: [], edges: [] };
            }
        } else if (data?.metaflow_yaml) {
            try {
                const parsed = yaml.load(data.metaflow_yaml);
                // Version check: reject v1 format
                if (parsed.apiVersion === 'ami.io/v1' || parsed.kind === 'Workflow') {
                    console.error("v1 格式已不再支持，请将 workflow 升级到 v2 格式");
                    return { nodes: [], edges: [] };
                }
                return transformMetaflowData(parsed, expandedNodeIds, onToggleExpand);
            } catch (e) {
                console.error("Metaflow YAML Parse Error", e);
                return { nodes: [], edges: [] };
            }
        }
        else if (data?.workflow) {
            return transformWorkflowData(data.workflow, expandedNodeIds, onToggleExpand);
        } else if (data?.metaflow) {
            return transformMetaflowData(data.metaflow, expandedNodeIds, onToggleExpand);
        }

        // Fallback: If data is the object itself (not wrapped)
        if (type === 'workflow') {
            return transformWorkflowData(data, expandedNodeIds, onToggleExpand);
        } else if (type === 'metaflow') {
            return transformMetaflowData(data, expandedNodeIds, onToggleExpand);
        }

        return { nodes: [], edges: [] };
    }, [data, expandedNodeIds, onToggleExpand]);

    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);

    // Sync state when computed data changes
    useEffect(() => {
        setNodes(computedNodes);
        setEdges(computedEdges);
    }, [computedNodes, computedEdges, setNodes, setEdges]);


    return (
        <div style={{ width: '100%', height: '100%', background: '#f8fafc' }}>
            <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                edgeTypes={edgeTypes}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                connectionLineType="smoothstep"
                connectionLineStyle={{ stroke: '#cbd5e1', strokeWidth: 2 }}
                defaultEdgeOptions={{
                    type: 'smoothstep',
                    style: { stroke: '#cbd5e1', strokeWidth: 2 },
                    markerEnd: { type: 'arrowclosed', color: '#cbd5e1' },
                    animated: false,
                }}
                fitView
                fitViewOptions={{ padding: 0.2, minZoom: 0.5, maxZoom: 1.2 }}
                minZoom={0.1}
            >
                <Background color="#e2e8f0" gap={16} />
                <Controls />
                <MiniMap
                    nodeColor={(node) => {
                        return node.type === 'group' ? '#e2e8f0' : '#fff';
                    }}
                    style={{
                        height: 120,
                        backgroundColor: "rgba(255, 255, 255, 0.9)",
                        border: "1px solid #e2e8f0",
                        borderRadius: "8px"
                    }}
                />
            </ReactFlow>
        </div>
    );
};

export default FlowVisualization;
