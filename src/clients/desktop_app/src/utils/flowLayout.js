
/**
 * Layout utility for FlowVisualization
 * Handles both flat (Workflow) and nested (Metaflow) structures
 * Layout: Horizontal (Left-to-Right)
 */

const NODE_WIDTH = 280;
const NODE_HEIGHT = 160;
const HORIZONTAL_GAP = 80; // visual gap between nodes
const VERTICAL_GAP = 80;   // visual gap between stacked nodes

/**
 * Unified processor for steps (handles recursion for loops/groups).
 * HYBRID LAYOUT STRATEGY:
 * - Main Flow: Horizontal (Left-to-Right)
 * - Loop/Nested Flow: Vertical Stack (Top-to-Bottom)
 * 
 * This prevents "Horizontal Explosion" where loops with many steps create an infinitely wide graph.
 * Instead, loops become "Towers", preserving aspect ratio and readability.
 */
const processStepsRecursive = (steps, startX, startY, parentId = null, nodes = [], edges = [], isNested = false, expandedNodeIds = new Set(), onToggleExpand = null) => {
    let currentX = startX;
    let currentY = startY;
    let previousNodeId = null;

    // Track bounds
    let maxX = currentX;
    let maxY = currentY;

    // Constants for Hybrid Layout
    const NESTED_VERTICAL_GAP = 120; // Vertical gap between steps INSIDE a loop
    const NESTED_INDENT = 80;        // Slight indentation for visual hierarchy

    steps.forEach((step, index) => {
        const nodeId = step.id || `step-${Math.random().toString(36).substr(2, 9)}`;

        // Determine Labels
        let label = step.intent_name || step.name || step.type || 'Step';
        let description = step.intent_description || step.description || '';
        const isLoop = step.type === 'loop' || step.agent_type === 'foreach';
        const isBranchStart = step.type === 'branch_start';
        const isBranchEnd = step.type === 'branch_end';

        const isExpanded = expandedNodeIds.has(nodeId);

        if (isLoop) label = `Loop: ${step.item_var || 'Items'}`;
        else if (isBranchStart) label = 'Branch Start';
        else if (isBranchEnd) label = 'Branch End';

        // 1. Add Node
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
                isBranchEnd,
                isExpanded, // Pass expansion state
                onToggleExpand // Pass toggle handler
            },
            position: { x: currentX, y: currentY }
            // parentNode: parentId -- REMOVED: We use absolute positioning. 
            // Setting parentNode would make these coordinates relative, causing double-offset.
        });

        // Update Bounds regarding THIS node
        maxX = Math.max(maxX, currentX + NODE_WIDTH);
        maxY = Math.max(maxY, currentY + NODE_HEIGHT);

        // 2. Connect to Previous
        if (previousNodeId) {
            edges.push({
                id: `e-${previousNodeId}-${nodeId}`,
                source: previousNodeId,
                target: nodeId,
                type: 'smoothstep',
                sourceHandle: isNested ? 'bottom' : 'right', // Nested moves Down, Main moves Right
                targetHandle: isNested ? 'top' : 'left',
                markerEnd: { type: 'arrowclosed' },
                animated: false
            });
        } else if (parentId) {
            // First child of a container
            // Parent (Loop Header) is Horizontal (Main Flow) -> Child is Vertical (Nested)
            // So Parent connects from Bottom/Right -> Child connects from Top/Left?
            // "Vertical Detour" style: Parent Right -> Child Left (but child is shifted down)
            // Or Parent Bottom -> Child Top (Tower style)

            // Let's go with "Tower Style": Loop Header sits on top of the stack.
            edges.push({
                id: `e-${parentId}-${nodeId}`,
                source: parentId,
                target: nodeId,
                type: 'default', // straight/bezier default often better for close proximity than smoothstep
                sourceHandle: 'bottom',
                targetHandle: 'top',
                markerEnd: { type: 'arrowclosed' },
                animated: true,
                label: 'Start Loop'
            });
        }

        // 3. Handle Children (Recursion)
        const children = step.children || step.steps;
        let stepWidth = NODE_WIDTH; // Width of this step block (including its children)

        // CONDITIONAL RECURSION: Only render children if Expanded!
        if (isLoop && !isExpanded) {
            // Collapsed State: Do not process children.
            // The flow continues from THIS node to the next sibling.
            // stepWidth remains NODE_WIDTH.
            // No edges to children are created.
        } else if (children && children.length > 0) {
            // If we are Main Flow, children are essentially a "Tower" hanging off this node.
            // If we are already Nested, children are a "Sub-Tower" (further indented).

            // Position for children:
            // Vertical Stack means they start BELOW this node.
            const childStartX = currentX + NESTED_INDENT;
            const childStartY = currentY + NODE_HEIGHT + NESTED_VERTICAL_GAP;

            // RECURSION: Pass isNested=true to enforce vertical stacking inside
            const childResult = processStepsRecursive(children, childStartX, childStartY, nodeId, nodes, edges, true, expandedNodeIds, onToggleExpand);

            // Update Bounds to encompass the entire child tree
            maxX = Math.max(maxX, childResult.maxX);
            maxY = Math.max(maxY, childResult.maxY);

            // Calculate effective size of this block
            // Even though children are vertical (increasing Y), they might have width (indents).
            // For the Main Flow (Horizontal), we care about how wide this tower became.
            stepWidth = Math.max(NODE_WIDTH, childResult.maxX - currentX + NESTED_INDENT);

            // ---------------------------------------------------------
            // VISUAL GROUP BOX GENERATION
            // ---------------------------------------------------------
            // We want to draw a box around the children we just laid out.
            // Bounds:
            // x: childStartX
            // y: childStartY
            // width: childResult.maxX - childStartX + NODE_WIDTH (approx?) 
            // height: childResult.maxY - childStartY + NODE_HEIGHT

            // Let's optimize the box size:
            // The children stack vertically. 
            // Width is basically NODE_WIDTH + indent drifts? 
            // Let's use the bounds returned by the recursion.

            const PADDING = 24;
            const groupX = childStartX - PADDING;
            const groupY = childStartY - PADDING;
            const groupWidth = (childResult.maxX - childStartX) + NODE_WIDTH + (PADDING * 2);
            // This width calculation assumes children might step right. 
            // In pure vertical stack, childResult.maxX might just be childStartX + NODE_WIDTH.
            // Safe to max it.

            const groupHeight = (childResult.maxY - childStartY) + NODE_HEIGHT + (PADDING * 2);

            nodes.push({
                id: `group-${nodeId}`,
                type: 'group',
                data: { label: label || 'Loop Scope' },
                position: { x: groupX, y: groupY },
                style: { width: groupWidth, height: groupHeight },
                zIndex: -1 // Behind everything
            });
            // ---------------------------------------------------------


            // Connect Last Child back to Parent
            const lastChild = nodes[nodes.length - 1]; // Approximation
            if (lastChild && lastChild.parentNode === nodeId) {
                edges.push({
                    id: `e-${lastChild.id}-${nodeId}`,
                    source: lastChild.id,
                    target: nodeId,
                    type: 'default',
                    markerEnd: { type: 'arrowclosed' },
                    animated: true,
                    style: { strokeDasharray: '5, 5', stroke: '#722ed1', opacity: 0.5 },
                    sourceHandle: 'right',
                    targetHandle: 'right', // Loop back on side
                    label: 'Repeat'
                });
            }
        }

        // 4. Move Cursor for NEXT Sibling
        if (isNested) {
            // If we are inside a loop, siblings stack VERTICALLY
            // We need to move Y down past *this* node (and its descendants!)
            // But wait, `maxY` tracks the deepest point of *this node's tree*.
            // So for the next sibling in a vertical stack, we start at `maxY + GAP`.

            // However, `maxY` is global cumulative. 
            // We need to know the height of JUST this step's branch.
            // `maxY` is accurate because it was updated by recursive children.
            currentY = maxY + NESTED_VERTICAL_GAP;

            // X stays aligned for vertical stack
            // currentX = startX; 
        } else {
            // Main Flow: Siblings move HORIZONTALLY
            // We need to move X past this node's "Tower Width".
            // `maxX` tracks the widest point.
            // But siblings align Top-to-Bottom? No, Main Flow is Left-to-Right.
            // So we move Right.

            // We need to ensure we don't overlap with the children we just drew below.
            // The children are strictly *below*, but they have width (indentation).
            // So we shift X by `stepWidth + GAP`.

            currentX += stepWidth + HORIZONTAL_GAP;
        }

        previousNodeId = nodeId;
    });

    return { maxX, maxY };
};


/**
 * Transform Metaflow data (nested) to ReactFlow nodes and edges
 */
export const transformMetaflowData = (metaflow, expandedNodeIds = new Set(), onToggleExpand = null) => {
    if (!metaflow) return { nodes: [], edges: [] };

    const steps = metaflow.nodes || metaflow.steps || [];
    const nodes = [];
    const edges = [];

    processStepsRecursive(steps, 0, 0, null, nodes, edges, false, expandedNodeIds, onToggleExpand);

    return { nodes, edges };
};

/**
 * Transform Workflow data to ReactFlow nodes and edges
 * Handles both flat lists and potentially nested structures if they exist
 * HORIZONTAL LAYOUT IMPLEMENTATION
 */
export const transformWorkflowData = (workflowData, expandedNodeIds = new Set(), onToggleExpand = null) => {
    if (!workflowData || !workflowData.steps) {
        return { nodes: [], edges: [] };
    }

    // Check nesting
    const hasChildren = workflowData.steps.some(s =>
        (s.children && s.children.length > 0) ||
        (s.steps && s.steps.length > 0)
    );

    if (hasChildren) {
        const nodes = [];
        const edges = [];
        processStepsRecursive(workflowData.steps, 0, 0, null, nodes, edges, false, expandedNodeIds, onToggleExpand);
        return { nodes, edges };
    }

    // Flat List Processor for Horizontal Layout
    const nodes = [];
    const edges = [];
    const steps = workflowData.steps;

    let currentX = 0;
    const startY = 0;

    // Track Y positions per branch (Stacking branches vertically)
    const branchYTracker = {};

    // To properly layout parallel branches, we need to know:
    // 1. Where branches split (Branch Start)
    // 2. Where they merge (Branch End)

    // Current assumption: "branch": "name" property on steps.

    // Map branch names to Y levels
    const branchNames = [...new Set(steps.map(s => s.branch).filter(Boolean))];
    const branchYs = {};
    branchNames.forEach((name, i) => {
        // Base Y + (Index * Gap). Center around 0?
        // Let's stack them: 0, 120, 240...
        // Or centered: -120, 0, 120...
        const offset = (i - (branchNames.length - 1) / 2) * VERTICAL_GAP;
        branchYs[name] = startY + offset;
    });

    steps.forEach((step, index) => {
        let x = currentX;
        let y = startY;

        // Determine Position
        if (step.type === 'branch_start') {
            // Branch Start point
            x = currentX;
            y = startY;
            currentX += HORIZONTAL_GAP * 0.8; // Short gap to branches
        } else if (step.type === 'branch_end') {
            // Merge point
            // Should be to the right of the furthest branch step
            // For simple linear scan, we just increment X
            x = currentX + HORIZONTAL_GAP * 0.5;
            y = startY;
            currentX = x + HORIZONTAL_GAP;
        } else if (step.branch) {
            // It's a branch step
            y = branchYs[step.branch] || startY;

            // X position:
            // Needs to be tracked PER BRANCH?
            // If steps are sequential in the array, we can just increment global X?
            // No, parallel branches should be at generally same X range.

            // Simple Logic: 
            // If previous step was SAME branch, increment X for that branch.
            // If specific per-branch tracking is needed:
            if (!branchYTracker[step.branch]) branchYTracker[step.branch] = currentX;

            x = branchYTracker[step.branch];
            branchYTracker[step.branch] += HORIZONTAL_GAP;

            // Global X needs to keep up with the max X of branches so the Merge point is correct
            if (x >= currentX) currentX = x + HORIZONTAL_GAP * 0.5;

        } else {
            // Normal Main Flow Step
            x = currentX;
            y = startY;
            currentX += HORIZONTAL_GAP;
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

    // Generate Edges (Horizontal: Source Right -> Target Left)
    if (workflowData.connections) {
        workflowData.connections.forEach((conn, i) => {
            edges.push({
                id: `e-${i}`,
                source: conn.from,
                target: conn.to,
                type: 'smoothstep',
                sourceHandle: 'right',
                targetHandle: 'left',
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
                const branches = branchNames; // Use detected branches
                branches.forEach(branchName => {
                    const firstBranchNode = nodes.find(n => n._index > i && (n._branch === branchName));
                    if (firstBranchNode) {
                        edges.push({
                            id: `e-${current.id}-${firstBranchNode.id}`,
                            source: current.id,
                            target: firstBranchNode.id,
                            type: 'smoothstep',
                            sourceHandle: 'right',
                            targetHandle: 'left',
                            markerEnd: { type: 'arrowclosed' }
                        });
                    }
                });
                continue;
            }

            // Branch Nodes -> Branch End
            if (next.data.type === 'branch_end') {
                // Scan last nodes of each branch
                const processedBranches = new Set();
                // Look backwards from branch_end
                for (let j = i; j >= 0; j--) {
                    const prev = nodes[j];
                    if (prev.data.type === 'branch_start') break;
                    if (prev._branch && !processedBranches.has(prev._branch)) {
                        edges.push({
                            id: `e-${prev.id}-${next.id}`,
                            source: prev.id,
                            target: next.id,
                            type: 'smoothstep',
                            sourceHandle: 'right',
                            targetHandle: 'left',
                            markerEnd: { type: 'arrowclosed' }
                        });
                        processedBranches.add(prev._branch);
                    }
                }
                continue;
            }

            // Sequential Connection
            const sameBranch = current._branch === next._branch;
            const noBranch = !current._branch && !next._branch;

            if ((sameBranch || noBranch) && current.data.type !== 'branch_start' && next.data.type !== 'branch_end') {
                edges.push({
                    id: `e-${current.id}-${next.id}`,
                    source: current.id,
                    target: next.id,
                    type: 'smoothstep',
                    sourceHandle: 'right',
                    targetHandle: 'left',
                    markerEnd: { type: 'arrowclosed' }
                });
            }
        }
    }

    return { nodes, edges };
};
