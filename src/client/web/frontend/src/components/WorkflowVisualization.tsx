import React, { useCallback } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  Edge,
  Node,
  NodeTypes,
  ReactFlowProvider,
  MarkerType,
} from 'reactflow';
import 'reactflow/dist/style.css';
import './WorkflowNode.css'; // 引入自定义样式
import CustomNode from './CustomNode';
import { Button } from 'antd';

// 定义节点类型
interface WorkflowNode extends Node {
  data: { 
    label: string;
    description?: string;
    type?: string;
    [key: string]: any;
  };
}

// 定义边类型
interface WorkflowEdge extends Edge {
  label?: string;
}

interface WorkflowVisualizationProps {
  workflowData: any; // 根据实际的数据结构调整类型
}

// 定义自定义节点类型
const nodeTypes: NodeTypes = {
  custom: CustomNode,
};

const WorkflowVisualization: React.FC<WorkflowVisualizationProps> = ({ workflowData }) => {
  // 转换workflowData为ReactFlow所需的节点和边
  const { nodes: initialNodes, edges: initialEdges } = transformWorkflowData(workflowData);
  
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const onConnect = useCallback(
    (params: Connection | Edge) => setEdges((eds) => addEdge({...params, markerEnd: { type: MarkerType.ArrowClosed }}, eds)),
    [setEdges]
  );

  // 处理节点数据更新
  const handleNodeUpdate = useCallback((id: string, data: any) => {
    setNodes((nds) =>
      nds.map((node) => {
        if (node.id === id) {
          return { ...node, data: { ...node.data, ...data } };
        }
        return node;
      })
    );
  }, [setNodes]);

  // 为边添加箭头标记
  const edgesWithMarkers = edges.map(edge => ({
    ...edge,
    markerEnd: { type: MarkerType.ArrowClosed }
  }));

  return (
    <div style={{ height: '100%', width: '100%' }}>
      <ReactFlowProvider>
        <ReactFlow
          nodes={nodes}
          edges={edgesWithMarkers}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          fitView
          nodeTypes={nodeTypes}
          connectionMode="loose"
          deleteKeyCode={['Delete', 'Backspace']}
        >
          <Controls />
          <MiniMap nodeColor={nodeColor} />
          <Background variant="dots" gap={12} size={1} />
        </ReactFlow>
      </ReactFlowProvider>
    </div>
  );
};

// 根据节点类型设置不同颜色
const nodeColor = (node: Node) => {
  switch (node.data?.type) {
    case 'start':
      return '#52c41a'; // 绿色
    case 'end':
      return '#ff4d4f'; // 红色
    default:
      return '#3b82f6'; // 蓝色
  }
};

// 转换工作流数据为节点和边
const transformWorkflowData = (workflowData: any): { nodes: WorkflowNode[]; edges: WorkflowEdge[] } => {
  if (!workflowData || !workflowData.steps) {
    return { nodes: [], edges: [] };
  }

  const nodes: WorkflowNode[] = [];
  const edges: WorkflowEdge[] = [];

  // 创建节点
  workflowData.steps.forEach((step: any, index: number) => {
    // 根据节点类型设置特殊样式
    let className = '';
    if (step.type === 'start') {
      className = 'start-node';
    } else if (step.type === 'end') {
      className = 'end-node';
    }

    nodes.push({
      id: step.id || `step-${index}`,
      type: 'custom', // 使用自定义节点类型
      data: { 
        label: step.name || step.type || `Step ${index + 1}`,
        description: step.description || '',
        type: step.type || '',
        ...step // 保留所有其他属性
      },
      position: { x: (index % 3) * 300, y: Math.floor(index / 3) * 150 }, // 网格布局
      className: className,
    });
  });

  // 创建连接边（如果有connections字段）
  if (workflowData.connections) {
    workflowData.connections.forEach((connection: any, index: number) => {
      edges.push({
        id: `e-${index}`,
        source: connection.from,
        target: connection.to,
      });
    });
  } else {
    // 否则按顺序连接节点
    for (let i = 0; i < nodes.length - 1; i++) {
      edges.push({
        id: `e${i}-${i + 1}`,
        source: nodes[i].id,
        target: nodes[i + 1].id,
      });
    }
  }

  return { nodes, edges };
};

export default WorkflowVisualization;