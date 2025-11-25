import React, { useMemo } from 'react';
import ReactFlow, {
    Background,
    Controls,
    MiniMap,
    useNodesState,
    useEdgesState,
    MarkerType,
    ReactFlowProvider,
} from 'reactflow';
import 'reactflow/dist/style.css';
import CustomNode from './CustomNode';
import { transformWorkflowData, transformMetaflowData } from '../utils/flowLayout';
import yaml from 'js-yaml';

const nodeTypes = {
    custom: CustomNode,
};

const nodeColor = (node) => {
    switch (node.data?.type) {
        case 'start':
            return '#52c41a';
        case 'end':
            return '#ff4d4f';
        case 'loop':
        case 'loop_start':
            return '#722ed1'; // Purple for loops
        case 'branch_start':
        case 'branch_end':
            return '#faad14'; // Orange for branches
        default:
            return '#3b82f6'; // Blue for default
    }
};

function FlowVisualization({ data, type = 'workflow' }) {
    const { nodes: initialNodes, edges: initialEdges } = useMemo(() => {
        if (type === 'workflow') {
            // Prefer parsing YAML if available to ensure we get the full nested structure
            let workflowDataToUse = data;
            if (data && data.workflow_yaml) {
                try {
                    const parsed = yaml.load(data.workflow_yaml);
                    if (parsed && parsed.steps) {
                        workflowDataToUse = { ...data, steps: parsed.steps, connections: parsed.connections };
                    }
                } catch (e) {
                    console.error("Failed to parse workflow YAML:", e);
                }
            }
            return transformWorkflowData(workflowDataToUse);
        } else {
            // For Metaflow, we might also want to parse YAML if passed as object with metaflow_yaml
            let metaflowDataToUse = data;
            if (data && data.metaflow_yaml && !data.nodes && !data.steps) {
                try {
                    const parsed = yaml.load(data.metaflow_yaml);
                    metaflowDataToUse = parsed;
                } catch (e) {
                    console.error("Failed to parse metaflow YAML:", e);
                }
            }
            return transformMetaflowData(metaflowDataToUse);
        }
    }, [data, type]);

    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

    // Update nodes/edges when data changes
    React.useEffect(() => {
        let result;
        if (type === 'workflow') {
            result = transformWorkflowData(data);
        } else {
            result = transformMetaflowData(data);
        }
        setNodes(result.nodes);
        setEdges(result.edges);
    }, [data, type, setNodes, setEdges]);

    if (!data) {
        return (
            <div className="empty-state">
                <div className="empty-state-icon">📋</div>
                <div className="empty-state-title">No Data</div>
            </div>
        );
    }

    return (
        <div className="workflow-canvas" style={{ height: '100%', minHeight: '500px' }}>
            <ReactFlowProvider>
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    fitView
                    nodeTypes={nodeTypes}
                    fitViewOptions={{ padding: 0.2, minZoom: 0.5, maxZoom: 1.5 }}
                    minZoom={0.1}
                    maxZoom={2}
                    defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
                >
                    <Controls showInteractive={false} />
                    <MiniMap
                        nodeColor={nodeColor}
                        nodeStrokeWidth={3}
                        zoomable
                        pannable
                        style={{ width: 80, height: 60 }}
                    />
                    <Background variant="dots" gap={12} size={1} />
                </ReactFlow>
            </ReactFlowProvider>
        </div>
    );
}

export default FlowVisualization;
