/**
 * Layout utility for FlowVisualization
 * Handles both flat (Workflow) and nested (Metaflow) structures
 * Layout: Horizontal (Left-to-Right)
 *
 * Supports Workflow v2 format:
 * - 'agent' field for step type (not 'agent_type')
 * - Control flow as keys: 'foreach', 'if', 'while'
 * - Loop body in 'do' field (not 'steps')
 * - Loop variable in 'as' field (not 'item_var')
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
        // Use stable id: prefer step.id, fallback to index-based id (not random!)
        // Random ids break expand/collapse because they change on every render
        const nodeId = step.id || `step-${index}`;

        // Determine Labels
        let label = step.intent_name || step.name || step.type || 'Step';
        let description = step.intent_description || step.description || '';
        // v2 format: 'foreach' in step (control flow as key)
        const isLoop = step.type === 'loop' || 'foreach' in step;
        const isBranchStart = step.type === 'branch_start';
        const isBranchEnd = step.type === 'branch_end';

        const isExpanded = expandedNodeIds.has(nodeId);

        if (isLoop) label = `Loop: ${step.as || step.item_var || 'Items'}`;
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
                type: step.type || step.agent || 'step',  // v2: use 'agent' instead of 'agent_type'
                isLoop,
                isBranchStart,
                isBranchEnd,
                isExpanded, // Pass expansion state
                onToggleExpand // Pass toggle handler
            },
            position: { x: currentX, y: currentY }
        });

        // Update Bounds regarding THIS node
        maxX = Math.max(maxX, currentX + NODE_WIDTH);
        maxY = Math.max(maxY, currentY + NODE_HEIGHT);

        // 2. Connect to Previous
        // Check if we need to connect to previous sibling
        if (previousNodeId) {
            edges.push({
                id: `e-${previousNodeId}-${nodeId}`,
                source: previousNodeId,
                target: nodeId,
                type: 'floating', // Use our smart floating edge
                style: { stroke: '#cbd5e1', strokeWidth: 2 },
                markerEnd: { type: 'arrowclosed', color: '#cbd5e1' }
            });
        } else if (parentId) {
            // First child of a container
            // Use floating edge for parent-child connection too
            edges.push({
                id: `e-${parentId}-${nodeId}`,
                source: parentId,
                target: nodeId,
                type: 'floating',
                markerEnd: { type: 'arrowclosed', color: '#cbd5e1' },
                animated: true,
                style: { stroke: '#cbd5e1', strokeWidth: 2 },
                label: 'Start Loop'
            });
        }

        // 3. Handle Children (Recursion)
        // v2 format: 'do' for loop body, fallback to 'steps' or 'children'
        const children = step.do || step.children || step.steps;
        let stepWidth = NODE_WIDTH; // Width of this step block (including its children)

        // CONDITIONAL RECURSION: Only render children if Expanded!
        if (isLoop && !isExpanded) {
            // Collapsed State: Do not process children.
        } else if (children && children.length > 0) {
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
            stepWidth = Math.max(NODE_WIDTH, childResult.maxX - currentX + NESTED_INDENT);

            // ---------------------------------------------------------
            // VISUAL GROUP BOX GENERATION
            // ---------------------------------------------------------
            const PADDING = 24;
            const groupX = childStartX - PADDING;
            const groupY = childStartY - PADDING;
            const groupWidth = (childResult.maxX - childStartX) + NODE_WIDTH + (PADDING * 2);
            const groupHeight = (childResult.maxY - childStartY) + NODE_HEIGHT + (PADDING * 2);

            nodes.push({
                id: `group-${nodeId}`,
                type: 'group',
                data: { label: label || 'Loop Scope' },
                position: { x: groupX, y: groupY },
                style: { width: groupWidth, height: groupHeight },
                zIndex: -1 // Behind everything
            });

            // Connect Last Child back to Parent
            const lastChild = nodes[nodes.length - 1]; // Approximation
            if (lastChild && lastChild.parentNode === nodeId) {
                // Use floating for loop-back too
                edges.push({
                    id: `e-${lastChild.id}-${nodeId}`,
                    source: lastChild.id,
                    target: nodeId,
                    type: 'floating',
                    markerEnd: { type: 'arrowclosed' },
                    animated: true,
                    style: { strokeDasharray: '5, 5', stroke: '#722ed1', opacity: 0.5 },
                    label: 'Repeat'
                });
            }
        }

        // 4. Move Cursor for NEXT Sibling
        if (isNested) {
            // If we are inside a loop, siblings stack VERTICALLY
            currentY = maxY + NESTED_VERTICAL_GAP;
            // X stays aligned for vertical stack
        } else {
            // Main Flow: Siblings move HORIZONTALLY
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
    console.log("transformMetaflowData input:", metaflow);
    if (!metaflow) return { nodes: [], edges: [] };

    const steps = metaflow.nodes || metaflow.steps || [];
    console.log("transformMetaflowData steps found:", steps.length, steps);

    const nodes = [];
    const edges = [];

    processStepsRecursive(steps, 0, 0, null, nodes, edges, false, expandedNodeIds, onToggleExpand);

    console.log("transformMetaflowData outputs:", { nodes, edges });
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

    // Check nesting (v2 format: 'do' for loop body)
    const hasChildren = workflowData.steps.some(s =>
        (s.do && s.do.length > 0) ||
        (s.then && s.then.length > 0) ||
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

    // Map branch names to Y levels
    const branchNames = [...new Set(steps.map(s => s.branch).filter(Boolean))];
    const branchYs = {};
    branchNames.forEach((name, i) => {
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
            x = currentX + HORIZONTAL_GAP * 0.5;
            y = startY;
            currentX = x + HORIZONTAL_GAP;
        } else if (step.branch) {
            // It's a branch step
            y = branchYs[step.branch] || startY;
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

        // Add Node (v2 format: use 'agent' instead of 'agent_type')
        nodes.push({
            id: step.id || `step-${index}`,
            type: 'custom',
            data: {
                ...step,
                label: step.name || step.intent_name || step.type,
                description: step.description || step.intent_description,
                isLoop: step.type === 'loop' || 'foreach' in step,
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
                type: 'floating',
                markerEnd: { type: 'arrowclosed', color: '#cbd5e1' }
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
                            type: 'floating',
                            markerEnd: { type: 'arrowclosed', color: '#cbd5e1' }
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
                            type: 'floating',
                            markerEnd: { type: 'arrowclosed', color: '#cbd5e1' }
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
                    type: 'floating',
                    style: { stroke: '#cbd5e1', strokeWidth: 2 },
                    markerEnd: { type: 'arrowclosed', color: '#cbd5e1' }
                });
            }
        }
    }

    return { nodes, edges };
};

/**
 * Transform CognitivePhrase data to ReactFlow nodes and edges
 * Creates a horizontal graph: State -> IntentSequence -> State -> ...
 *
 * @param {object} phrase - CognitivePhrase object
 * @param {array} states - Array of State objects
 * @param {array} intentSequences - Array of IntentSequence objects
 * @param {Set} expandedNodeIds - Set of expanded node IDs
 * @param {function} onToggleExpand - Callback to toggle node expansion
 * @returns {object} { nodes, edges }
 */
export const transformCognitivePhraseData = (phrase, states, intentSequences, expandedNodeIds = new Set(), onToggleExpand = null) => {
    if (!phrase || !states || states.length === 0) {
        return { nodes: [], edges: [] };
    }

    const nodes = [];
    const edges = [];

    // Build lookup maps
    const stateById = {};
    states.forEach(s => { stateById[s.id] = s; });

    const seqById = {};
    intentSequences.forEach(seq => { seqById[seq.id] = seq; });

    const PHRASE_NODE_WIDTH = 280;
    const PHRASE_NODE_HEIGHT = 120;
    const SEQ_NODE_WIDTH = 260;
    const SEQ_NODE_HEIGHT = 100;
    const H_GAP = 100;
    const V_GAP = 40;

    let currentX = 0;
    const baseY = 0;

    // Use execution_plan if available, otherwise fall back to state_path
    if (phrase.execution_plan && phrase.execution_plan.length > 0) {
        phrase.execution_plan.forEach((step, stepIndex) => {
            const state = stateById[step.state_id];
            if (!state) return;

            // Add State node
            const stateNodeId = `state-${step.state_id}`;
            nodes.push({
                id: stateNodeId,
                type: 'custom',
                data: {
                    label: state.page_title || state.description || state.page_url || 'Page',
                    description: state.description || state.page_url,
                    type: 'state',
                    nodeType: 'state'
                },
                position: { x: currentX, y: baseY }
            });

            // Connect from previous step's last element
            if (stepIndex > 0) {
                const prevStep = phrase.execution_plan[stepIndex - 1];
                // Find the last element of previous step
                let prevNodeId;
                if (prevStep.navigation_sequence_id) {
                    prevNodeId = `seq-${prevStep.navigation_sequence_id}`;
                } else if (prevStep.in_page_sequence_ids && prevStep.in_page_sequence_ids.length > 0) {
                    prevNodeId = `seq-${prevStep.in_page_sequence_ids[prevStep.in_page_sequence_ids.length - 1]}`;
                } else {
                    prevNodeId = `state-${prevStep.state_id}`;
                }

                edges.push({
                    id: `e-${prevNodeId}-${stateNodeId}`,
                    source: prevNodeId,
                    target: stateNodeId,
                    type: 'floating',
                    animated: true, // Navigation edges are animated
                    style: { stroke: '#10b981', strokeWidth: 2 },
                    markerEnd: { type: 'arrowclosed', color: '#10b981' }
                });
            }

            currentX += PHRASE_NODE_WIDTH + H_GAP;

            // Add in-page IntentSequence nodes (stacked vertically below state)
            let seqY = baseY;
            let lastInPageSeqId = null;

            step.in_page_sequence_ids.forEach((seqId, seqIndex) => {
                const seq = seqById[seqId];
                if (!seq) return;

                const seqNodeId = `seq-${seqId}`;
                const isExpanded = expandedNodeIds.has(seqNodeId);

                nodes.push({
                    id: seqNodeId,
                    type: 'custom',
                    data: {
                        label: seq.description || 'Action Sequence',
                        description: seq.intents?.map(i => i.text || i.type).join(' -> '),
                        type: 'intent_sequence',
                        nodeType: 'intent_sequence',
                        intents: seq.intents,
                        isExpanded,
                        onToggleExpand
                    },
                    position: { x: currentX, y: seqY }
                });

                // Connect State -> first in-page sequence
                if (seqIndex === 0) {
                    edges.push({
                        id: `e-${stateNodeId}-${seqNodeId}`,
                        source: stateNodeId,
                        target: seqNodeId,
                        type: 'floating',
                        style: { stroke: '#3b82f6', strokeWidth: 2 },
                        markerEnd: { type: 'arrowclosed', color: '#3b82f6' }
                    });
                } else if (lastInPageSeqId) {
                    // Connect previous in-page sequence to this one
                    edges.push({
                        id: `e-${lastInPageSeqId}-${seqNodeId}`,
                        source: lastInPageSeqId,
                        target: seqNodeId,
                        type: 'floating',
                        style: { stroke: '#3b82f6', strokeWidth: 2 },
                        markerEnd: { type: 'arrowclosed', color: '#3b82f6' }
                    });
                }

                lastInPageSeqId = seqNodeId;
                seqY += SEQ_NODE_HEIGHT + V_GAP;
            });

            // If there are in-page sequences, advance X
            if (step.in_page_sequence_ids.length > 0) {
                currentX += SEQ_NODE_WIDTH + H_GAP;
            }

            // Add navigation IntentSequence if exists
            if (step.navigation_sequence_id) {
                const navSeq = seqById[step.navigation_sequence_id];
                if (navSeq) {
                    const navSeqNodeId = `seq-${step.navigation_sequence_id}`;
                    const isExpanded = expandedNodeIds.has(navSeqNodeId);

                    nodes.push({
                        id: navSeqNodeId,
                        type: 'custom',
                        data: {
                            label: navSeq.description || 'Navigation',
                            description: navSeq.intents?.map(i => i.text || i.type).join(' -> '),
                            type: 'intent_sequence',
                            nodeType: 'intent_sequence',
                            isNavigation: true,
                            intents: navSeq.intents,
                            isExpanded,
                            onToggleExpand
                        },
                        position: { x: currentX, y: baseY }
                    });

                    // Connect from last in-page sequence or state
                    const sourceId = lastInPageSeqId || stateNodeId;
                    edges.push({
                        id: `e-${sourceId}-${navSeqNodeId}`,
                        source: sourceId,
                        target: navSeqNodeId,
                        type: 'floating',
                        style: { stroke: '#f59e0b', strokeWidth: 2 },
                        markerEnd: { type: 'arrowclosed', color: '#f59e0b' }
                    });

                    currentX += SEQ_NODE_WIDTH + H_GAP;
                }
            }
        });
    } else {
        // Fallback: simple state_path based layout
        phrase.state_path.forEach((stateId, index) => {
            const state = stateById[stateId];
            if (!state) return;

            const stateNodeId = `state-${stateId}`;
            nodes.push({
                id: stateNodeId,
                type: 'custom',
                data: {
                    label: state.page_title || state.description || state.page_url || 'Page',
                    description: state.description || state.page_url,
                    type: 'state',
                    nodeType: 'state'
                },
                position: { x: currentX, y: baseY }
            });

            // Connect to previous state
            if (index > 0) {
                const prevStateId = phrase.state_path[index - 1];
                edges.push({
                    id: `e-state-${prevStateId}-${stateNodeId}`,
                    source: `state-${prevStateId}`,
                    target: stateNodeId,
                    type: 'floating',
                    animated: true,
                    style: { stroke: '#10b981', strokeWidth: 2 },
                    markerEnd: { type: 'arrowclosed', color: '#10b981' }
                });
            }

            currentX += PHRASE_NODE_WIDTH + H_GAP;
        });
    }

    return { nodes, edges };
};

