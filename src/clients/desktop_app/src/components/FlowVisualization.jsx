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
import GroupNode from './GroupNode';
import { transformWorkflowData, transformMetaflowData } from '../utils/flowLayout';
import yaml from 'js-yaml';

// Custom node types will be created with onOptimizeScript callback

const nodeTypes = {
    custom: CustomNode,
    group: GroupNode
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

function FlowVisualization({ data, type = 'workflow', onOptimizeScript }) {
    // Create custom node component with onOptimizeScript callback
    const nodeTypes = useMemo(() => ({
        custom: (props) => <CustomNode {...props} onOptimizeScript={onOptimizeScript} />
    }), [onOptimizeScript]);

    const { nodes: initialNodes, edges: initialEdges } = useMemo(() => {
        let parsedData = {};

        // 1. Try to parse Workflow YAML
        if (type === 'workflow') {
            if (data?.workflow_yaml) {
                try {
                    const parsed = yaml.load(data.workflow_yaml);
                    return transformWorkflowData(parsed, expandedNodeIds, onToggleExpand);
                } catch (e) {
                    console.error("YAML Parse Error", e);
                    return { nodes: [], edges: [] };
                }
            } else if (data?.metaflow_yaml) { // Prioritize YAML for Metaflow too
                try {
                    const parsed = yaml.load(data.metaflow_yaml);
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
            return { nodes: [], edges: [] };
        }, [data, expandedNodeIds, onToggleExpand]);

    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

    // Update nodes/edges when data changes
    useEffect(() => {
        let result = { nodes: [], edges: [] };

        if (data && data.workflow_yaml) {
            try {
                const parsed = yaml.load(data.workflow_yaml);
                if (parsed && parsed.steps) {
                    result = transformWorkflowData({ ...data, ...parsed });
                }
            } catch (e) { console.error(e); }
        } else {
            // Fallback if needed, but we want to depend on YAML
            result = transformWorkflowData(data || {});
        }
    } else {
        if(data && data.metaflow_yaml) {
        try {
            const parsed = yaml.load(data.metaflow_yaml);
            result = transformMetaflowData(parsed || {});
        } catch (e) { console.error(e); }
    } else {
        result = transformMetaflowData(data || {});
    }
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
                connectionLineType="smoothstep"
                connectionLineStyle={{ stroke: '#cbd5e1', strokeWidth: 2 }}
                defaultEdgeOptions={{
                    type: 'smoothstep',
                    style: { stroke: '#cbd5e1', strokeWidth: 2 },
                    markerEnd: { type: 'arrowclosed', color: '#cbd5e1' },
                    animated: false,
                }}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                fitView
                nodeTypes={nodeTypes}
                fitViewOptions={{ padding: 0.2, minZoom: 0.5, maxZoom: 1.2 }}
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
