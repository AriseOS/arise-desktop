
/**
 * Layout utility for FlowVisualization
 * Handles both flat (Workflow) and nested (Metaflow) structures
 */

const NODE_WIDTH = 280;
const NODE_HEIGHT = 100;
const VERTICAL_GAP = 120;
const HORIZONTAL_GAP = 350;

/**
 * Unified processor for steps (handles recursion for loops/groups)
 */
const processStepsRecursive = (steps, startX, startY, parentId = null, nodes = [], edges = []) => {
    let currentY = startY;
    let previousNodeId = null;

    const currentX = startX;

    steps.forEach((step, index) => {
        const nodeId = step.id || `step-${Math.random().toString(36).substr(2, 9)}`;

        // Determine Node Type and Label
        let type = 'custom';
        let label = step.intent_name || step.name || step.type || 'Step';
        let description = step.intent_description || step.description || '';

        // Check for loop (agent_type: foreach OR type: loop)
        const isLoop = step.type === 'loop' || step.agent_type === 'foreach';
        const isBranchStart = step.type === 'branch_start';
        const isBranchEnd = step.type === 'branch_end';

        if (isLoop) {
            type = 'custom';
            label = `Loop: ${step.item_var || 'Items'}`;
        } else if (isBranchStart) {
            label = 'Branch Start';
        } else if (isBranchEnd) {
            label = 'Branch End';
        }

        // 1. Add the current node
        nodes.push({
            id: nodeId,
            type: 'custom',
            data: {
                ...step,
                label,
                description,
                type: step.type || step.agent_type || 'step',
                isLoop,
                isBranchStart,
                isBranchEnd
            },
            position: { x: currentX, y: currentY },
            parentNode: parentId
        });

        // 2. Connect to previous node
        if (previousNodeId) {
            edges.push({
                id: `e-${previousNodeId}-${nodeId}`,
                source: previousNodeId,
                target: nodeId,
                type: 'smoothstep',
                markerEnd: { type: 'arrowclosed' },
                animated: false
            });
        } else if (parentId) {
            // Connect Loop Node (parentId) to First Child (nodeId)
            edges.push({
                id: `e-${parentId}-${nodeId}`,
                source: parentId,
                target: nodeId,
                type: 'smoothstep',
                markerEnd: { type: 'arrowclosed' },
                animated: true,
                label: 'Start Loop'
            });
        }

        currentY += VERTICAL_GAP;

        // 3. Handle Children (Recursion for Loops)
        // Support both 'children' (Metaflow/Generic) and 'steps' (Workflow 'foreach')
        const children = step.children || step.steps;

        if (children && children.length > 0) {
            // Indent children
            const childStartX = currentX + 50;
            const childResult = processStepsRecursive(children, childStartX, currentY, nodeId, nodes, edges);

            currentY = childResult.maxY;

            // Connect last child back to Loop Node to show cycle
            // We need to find the last node added by the recursive call that is at the top level of that recursion
            // Actually, the last node in the 'nodes' array is the last descendant.
            // We want to connect the last step of the loop back to the loop start.

            // Let's find the last node that was added.
            const lastDescendant = nodes[nodes.length - 1];

            if (lastDescendant && lastDescendant.id !== nodeId) {
                edges.push({
                    id: `e-${lastDescendant.id}-${nodeId}`,
                    source: lastDescendant.id,
                    target: nodeId,
                    type: 'default',
                    markerEnd: { type: 'arrowclosed' },
                    animated: true,
                    style: { strokeDasharray: '5, 5', stroke: '#722ed1' },
                    sourceHandle: 'bottom',
                    targetHandle: 'top', // Connect to top of loop node to complete cycle visually
                    label: 'Repeat'
                });
            }

            // The "Next" node after the loop will connect from the Loop Node (as "Done")
            // This means previousNodeId for the next iteration of THIS loop should be the Loop Node.
            previousNodeId = nodeId;

        } else {
            previousNodeId = nodeId;
        }
    });

    return { maxY: currentY };
};


/**
 * Transform Metaflow data (nested) to ReactFlow nodes and edges
 */
export const transformMetaflowData = (metaflow) => {
    if (!metaflow) return { nodes: [], edges: [] };

    const steps = metaflow.nodes || metaflow.steps || [];
    const nodes = [];
    const edges = [];

    processStepsRecursive(steps, 0, 0, null, nodes, edges);

    return { nodes, edges };
};

/**
 * Transform Workflow data to ReactFlow nodes and edges
 * Handles both flat lists and potentially nested structures if they exist
 */
export const transformWorkflowData = (workflowData) => {
    // Debug logging
    console.log('transformWorkflowData input:', workflowData);

    if (!workflowData || !workflowData.steps) {
        console.warn('No steps found in workflowData');
        return { nodes: [], edges: [] };
    }

    // Check if it's a flat list or nested
    // Check for 'children' OR 'steps' inside steps (for foreach)
    const hasChildren = workflowData.steps.some(s =>
        (s.children && s.children.length > 0) ||
        (s.steps && s.steps.length > 0)
    );

    console.log('hasChildren detected:', hasChildren);

    if (hasChildren) {
        // Use recursive processor
        const nodes = [];
        const edges = [];
        processStepsRecursive(workflowData.steps, 0, 0, null, nodes, edges);
        return { nodes, edges };
    }

    // Fallback to Flat List Processor (improved)
    const nodes = [];
    const edges = [];
    const steps = workflowData.steps;

    let currentY = 0;
    const startX = 0;

    // Identify branch blocks
    let branchStartIndex = -1;
    let branchEndIndex = -1;

    steps.forEach((step, index) => {
        if (step.type === 'branch_start') branchStartIndex = index;
        if (step.type === 'branch_end') branchEndIndex = index;
    });

    // Helper to get X position
    const getX = (branch) => {
        if (!branch) return startX;
        if (branch.includes('allegro')) return startX - HORIZONTAL_GAP / 2;
        if (branch.includes('amazon')) return startX + HORIZONTAL_GAP / 2;
        return startX;
    };

    // Track Y positions per branch to avoid overlap
    const branchYTracker = {};

    steps.forEach((step, index) => {
        let x = startX;
        let y = currentY;

        // Determine X and Y
        if (step.type === 'branch_start') {
            y = currentY;
            currentY += VERTICAL_GAP;
        } else if (step.type === 'branch_end') {
            // Find max Y of branches
            const maxY = Math.max(...Object.values(branchYTracker), currentY);
            y = maxY + VERTICAL_GAP;
            currentY = y + VERTICAL_GAP;
        } else if (step.branch) {
            x = getX(step.branch);
            const baseY = branchYTracker[step.branch] || currentY;
            y = baseY;
            branchYTracker[step.branch] = y + VERTICAL_GAP;
        } else {
            y = currentY;
            currentY += VERTICAL_GAP;
        }

        // Add Node
        nodes.push({
            id: step.id || `step-${index}`,
            type: 'custom',
            data: {
                ...step,
                label: step.name || step.intent_name || step.type,
                description: step.description || step.intent_description,
                isLoop: step.type === 'loop' || step.agent_type === 'foreach',
                isBranchStart: step.type === 'branch_start',
                isBranchEnd: step.type === 'branch_end'
            },
            position: { x, y },
            _index: index,
            _branch: step.branch
        });
    });

    // Generate Edges
    if (workflowData.connections) {
        workflowData.connections.forEach((conn, i) => {
            edges.push({
                id: `e-${i}`,
                source: conn.from,
                target: conn.to,
                type: 'smoothstep',
                markerEnd: { type: 'arrowclosed' }
            });
        });
    } else {
        // Auto-generate edges for flat list
        for (let i = 0; i < nodes.length - 1; i++) {
            const current = nodes[i];
            const next = nodes[i + 1];

            // Branch Start -> First Node of Branches
            if (current.data.type === 'branch_start') {
                const branches = current.data.branches || ['allegro', 'amazon'];
                branches.forEach(branchName => {
                    const firstBranchNode = nodes.find(n => n._index > i && (n._branch === branchName || n._branch?.includes(branchName)));
                    if (firstBranchNode) {
                        edges.push({
                            id: `e-${current.id}-${firstBranchNode.id}`,
                            source: current.id,
                            target: firstBranchNode.id,
                            type: 'smoothstep',
                            markerEnd: { type: 'arrowclosed' }
                        });
                    }
                });
                continue;
            }

            // Branch Nodes -> Branch End
            if (next.data.type === 'branch_end') {
                // Connect last node of each branch to branch_end
                // Scan backwards from branch_end
                const connectedBranches = new Set();
                for (let j = i; j >= 0; j--) {
                    const node = nodes[j];
                    if (node.data.type === 'branch_start') break;
                    if (node._branch && !connectedBranches.has(node._branch)) {
                        edges.push({
                            id: `e-${node.id}-${next.id}`,
                            source: node.id,
                            target: next.id,
                            type: 'smoothstep',
                            markerEnd: { type: 'arrowclosed' }
                        });
                        connectedBranches.add(node._branch);
                    }
                }
                continue;
            }

            // Sequential Connection
            // Only connect if same branch or transitioning from/to non-branch (excluding branch_start/end handled above)
            const sameBranch = current._branch === next._branch;
            const noBranch = !current._branch && !next._branch;

            if ((sameBranch || noBranch) && current.data.type !== 'branch_start' && next.data.type !== 'branch_end') {
                edges.push({
                    id: `e-${current.id}-${next.id}`,
                    source: current.id,
                    target: next.id,
                    type: 'smoothstep',
                    markerEnd: { type: 'arrowclosed' }
                });
            }
        }
    }

    return { nodes, edges };
};
