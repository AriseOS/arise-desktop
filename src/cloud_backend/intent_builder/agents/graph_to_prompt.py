"""
Graph to Prompt Converter

Converts Graph Builder output (StateActionGraph) into a structured prompt
that can be understood by the WorkflowBuilder agent.

Updated for unified memgraph ontology:
- States now contain Intents (operations within state)
- Actions represent state transitions only
- Extracts both Intents and Actions to build complete operation sequence

This module maintains compatibility with the existing intent-based workflow
generation while accepting graph as input instead of intent sequence.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _format_intent_description(intent: Dict[str, Any]) -> str:
    """Format Intent as human-readable description.

    Args:
        intent: Intent dictionary

    Returns:
        Description string
    """
    intent_type = intent.get("type", "")
    text = intent.get("text", "")
    value = intent.get("value", "")

    if intent_type == "click":
        if text:
            return f"Click on '{text}'"
        return "Click element"
    elif intent_type == "input":
        if value:
            return f"Input '{value}'"
        return "Input text"
    elif intent_type == "scroll":
        return "Scroll page"
    else:
        return f"{intent_type.title()} action"


def _format_action_description(action: Dict[str, Any], states: Dict[str, Any]) -> str:
    """Format Action as human-readable description.

    Args:
        action: Action dictionary
        states: States dictionary for URL lookup

    Returns:
        Description string
    """
    action_type = action.get("type", "")
    target_id = action.get("target", "")

    # Get target URL if available
    target_state = states.get(target_id, {})
    target_url = target_state.get("page_url", "")

    if action_type == "Navigate":
        return f"Navigate to {target_url}"
    elif action_type == "ClickLink":
        return f"Click link to navigate to {target_url}"
    elif action_type == "SubmitForm":
        return f"Submit form to {target_url}"
    elif action_type == "Search":
        return f"Search and navigate to {target_url}"
    else:
        return f"{action_type} to {target_url}"


def graph_to_prompt_data(graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert StateActionGraph to prompt data structure.

    The output format is compatible with the existing WorkflowBuilder
    prompt structure, but derived from graph instead of intents.

    Updated for unified memgraph ontology:
    - Extracts Intents from State.intents
    - Processes Actions (state transitions)
    - Builds complete operation sequence

    Args:
        graph: StateActionGraph dictionary from Graph Builder

    Returns:
        Dictionary containing:
        - states: List of state descriptions
        - edges: List of ALL operations (Intents + Actions)
        - path: Recommended execution path
        - operations: Flattened list of all operations for context
    """
    states = graph.get("states", {})
    actions = graph.get("actions", [])  # NEW: renamed from "edges"
    phases = graph.get("phases", [])
    episodes = graph.get("episodes", [])

    # Build state descriptions
    state_list = []
    for state_id, state_data in states.items():
        # Extract intents count from state
        intents = state_data.get("intents", [])
        intent_count = len(intents)

        state_list.append(
            {
                "state_id": state_id,
                "url": state_data.get("page_url", ""),  # NEW: page_url not url
                "page_root": state_data.get("attributes", {}).get("page_root", "main"),
                "description": state_data.get("description", f"Page: {state_data.get('page_url', 'unknown')}"),
                "intent_count": intent_count,
            }
        )

    # Build complete operation list: Intents + Actions
    # We need to interleave them in chronological order
    all_operations = []

    # Collect all Intents from states
    for state_id, state_data in states.items():
        intents = state_data.get("intents", [])
        for intent in intents:
            op = {
                "type": "intent",
                "intent_id": intent.get("id", ""),
                "state_id": state_id,
                "action_type": intent.get("type", ""),  # click, input, scroll
                "timestamp": intent.get("timestamp", 0),
                "description": _format_intent_description(intent),
                "target": {
                    "tag": intent.get("element_tag"),
                    "text": intent.get("text"),
                    "xpath": intent.get("xpath"),
                    "role": intent.get("attributes", {}).get("role"),
                },
                "data": {
                    "value": intent.get("value"),
                    **intent.get("attributes", {}).get("raw_data", {})
                },
            }
            all_operations.append(op)

    # Collect all Actions (state transitions)
    for action in actions:
        op = {
            "type": "action",
            "action_id": action.get("trigger_intent_id", ""),
            "from_state": action.get("source", ""),
            "to_state": action.get("target", ""),
            "action_type": action.get("type", ""),  # Navigate, ClickLink, etc.
            "timestamp": action.get("timestamp", 0),
            "description": _format_action_description(action, states),
            "target": action.get("attributes", {}).get("target_element", {}),
            "data": action.get("attributes", {}).get("data", {}),
        }
        all_operations.append(op)

    # Sort by timestamp to get execution order
    all_operations.sort(key=lambda x: x["timestamp"])

    # Build execution path from sorted operations
    execution_path = []
    for i, op in enumerate(all_operations):
        if op["type"] == "intent":
            step = {
                "step_number": i + 1,
                "type": "intent",
                "state_id": op["state_id"],
                "action_type": op["action_type"],
                "description": op["description"],
            }
        else:  # action
            step = {
                "step_number": i + 1,
                "type": "action",
                "from_state": op["from_state"],
                "to_state": op["to_state"],
                "action_type": op["action_type"],
                "description": op["description"],
            }
        execution_path.append(step)

    # Extract all original events for additional context
    all_events = []
    for episode in episodes:
        events = episode.get("events", [])
        for event in events:
            all_events.append(
                {
                    "type": event.get("type", ""),
                    "url": event.get("url", ""),
                    "target": event.get("target", {}),
                    "data": event.get("data", {}),
                    "timestamp": event.get("timestamp", 0),
                }
            )

    return {
        "states": state_list,
        "edges": all_operations,  # NEW: now includes both Intents and Actions
        "execution_path": execution_path,
        "operations": all_events,  # Original events for context
        "phases": phases,
        "episodes": episodes,
    }


def build_user_prompt_from_graph(
    task_description: str, graph: Dict[str, Any], user_query: Optional[str] = None
) -> str:
    """
    Build user prompt for WorkflowBuilder from graph data.

    Args:
        task_description: User's task description
        graph: StateActionGraph from Graph Builder
        user_query: Optional user query/goal

    Returns:
        Formatted prompt string for LLM
    """
    prompt_data = graph_to_prompt_data(graph)

    states = prompt_data["states"]
    edges = prompt_data["edges"]
    path = prompt_data["execution_path"]

    prompt_parts = []

    # Task description
    prompt_parts.append(f"## Task\n\n{task_description}")

    # User query if provided
    if user_query:
        prompt_parts.append(f"\n## User Goal\n\n{user_query}")

    # State/Action Graph summary
    prompt_parts.append(f"\n## Recorded User Behavior (State/Action Graph)\n")
    prompt_parts.append(f"\nThe user performed the following workflow:\n")
    prompt_parts.append(
        f"- **{len(states)} unique page states** (different URLs/pages)"
    )
    prompt_parts.append(f"- **{len(edges)} actions** (clicks, inputs, navigations)")

    # States
    prompt_parts.append(f"\n### Page States\n")
    for state in states:
        prompt_parts.append(f"- **{state['state_id']}**: {state['url']}")

    # Execution path (step by step)
    prompt_parts.append(f"\n### User's Execution Path\n")
    prompt_parts.append("\nThe user followed this sequence of actions:\n")

    for step in path:
        from_state = step["from_state"]
        to_state = step["to_state"]
        desc = step["description"]

        if from_state == to_state:
            # Self-loop: action within same page
            prompt_parts.append(f"{step['step_number']}. {desc} (on {from_state})")
        else:
            # State transition
            prompt_parts.append(
                f"{step['step_number']}. {desc} ({from_state} → {to_state})"
            )

    # Detailed action information
    prompt_parts.append(f"\n### Action Details\n")
    prompt_parts.append("\nDetailed information for each action:\n")

    for i, edge in enumerate(edges, 1):
        prompt_parts.append(f"\n**Action {i}: {edge['action_type'].upper()}**")
        prompt_parts.append(f"- Description: {edge['description']}")

        target = edge.get("target", {})
        if target:
            prompt_parts.append(f"- Target element:")
            if target.get("xpath"):
                prompt_parts.append(f"  - XPath: {target['xpath']}")
            if target.get("tag"):
                prompt_parts.append(f"  - Tag: {target['tag']}")
            if target.get("role"):
                prompt_parts.append(f"  - Role: {target['role']}")
            if target.get("text"):
                prompt_parts.append(f"  - Text: {target['text']}")
            if target.get("aria"):
                prompt_parts.append(f"  - ARIA: {target['aria']}")

        data = edge.get("data", {})
        if data:
            # Only show relevant data fields
            if "value" in data:
                prompt_parts.append(f"- Input value: {data['value']}")
            if "field_type" in data:
                prompt_parts.append(f"- Field type: {data['field_type']}")

    # Instructions
    prompt_parts.append(f"\n## Your Task\n")
    prompt_parts.append(
        "\nGenerate a Workflow YAML that automates the above user behavior."
    )
    prompt_parts.append("\n**Important guidelines:**")
    prompt_parts.append("1. Follow the EXACT execution path shown above")
    prompt_parts.append(f"2. Preserve all {len(edges)} actions in the correct order")
    prompt_parts.append(
        "3. Use the target element information to create robust locators"
    )
    prompt_parts.append(
        "4. Each action should have preconditions based on the from_state URL"
    )
    prompt_parts.append(
        "5. Navigation actions should verify postconditions based on to_state URL"
    )
    prompt_parts.append(
        "6. For browser_agent interaction_steps, ALWAYS include xpath_hints field with the XPath values provided above"
    )
    prompt_parts.append(
        "\nUse the workflow-generation skill for YAML structure reference."
    )
    prompt_parts.append("Use the agent-specs skill to understand agent capabilities.")
    prompt_parts.append(
        "Use the workflow-validation skill to validate your output before submitting."
    )

    return "\n".join(prompt_parts)
