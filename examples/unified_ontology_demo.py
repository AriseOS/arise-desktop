"""
Unified Ontology Demo - End-to-End Example

This example demonstrates the complete flow from recording to memory storage
using the unified memgraph ontology.

Flow:
1. Load raw recording operations
2. Build StateActionGraph using GraphBuilder (LLM-free)
3. Store States (with Intents) and Actions to WorkflowMemory
4. Query and retrieve from memory

Usage:
    # Run from project root directory
    cd /Users/wangz/Workspace/Ami
    PYTHONPATH=. python examples/unified_ontology_demo.py
"""

import json
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.cloud_backend.graph_builder import GraphBuilder
from src.cloud_backend.memgraph.graphstore.networkx_graph import NetworkXGraph
from src.cloud_backend.memgraph.memory.workflow_memory import WorkflowMemory


def create_sample_recording():
    """Create a sample recording for demonstration.

    Returns:
        List of operation dictionaries simulating a browser recording
    """
    # Simulate a user workflow: Form submission, then navigating to another page, and clicking a button
    operations = [
        # Navigate to form page
        {
            "type": "navigation",
            "url": "https://example.com/form",
            "timestamp": 1000,
            "target": None,
            "data": {},
        },
        # Click on name field
        {
            "type": "click",
            "url": "https://example.com/form",
            "timestamp": 2000,
            "target": {
                "tag": "input",
                "role": "textbox",
                "text": "",
                "xpath": "/html/body/form/input[1]",
            },
            "data": {"field_type": "text"},
        },
        # Type name
        {
            "type": "input",
            "url": "https://example.com/form",
            "timestamp": 3000,
            "target": {
                "tag": "input",
                "role": "textbox",
                "text": "",
                "xpath": "/html/body/form/input[1]",
            },
            "data": {"value": "John Doe", "field_type": "text"},
        },
        # Click on email field
        {
            "type": "click",
            "url": "https://example.com/form",
            "timestamp": 4000,
            "target": {
                "tag": "input",
                "role": "textbox",
                "text": "",
                "xpath": "/html/body/form/input[2]",
            },
            "data": {"field_type": "email"},
        },
        # Type email
        {
            "type": "input",
            "url": "https://example.com/form",
            "timestamp": 5000,
            "target": {
                "tag": "input",
                "role": "textbox",
                "text": "",
                "xpath": "/html/body/form/input[2]",
            },
            "data": {"value": "john@example.com", "field_type": "email"},
        },
        # Click submit button (causes navigation) - this will create an Action
        {
            "type": "click",
            "url": "https://example.com/form",
            "timestamp": 6000,
            "target": {
                "tag": "button",
                "role": "button",
                "text": "Submit",
                "xpath": "/html/body/form/button",
            },
            "data": {},
        },
        # Navigate to success page (this is the state transition)
        {
            "type": "navigation",
            "url": "https://example.com/success",
            "timestamp": 7000,
            "target": None,
            "data": {},
        },
        # Click on a link in success page to go to dashboard
        {
            "type": "click",
            "url": "https://example.com/success",
            "timestamp": 8000,
            "target": {
                "tag": "a",
                "role": "link",
                "text": "Go to Dashboard",
                "xpath": "/html/body/a",
            },
            "data": {},
        },
        # Navigate to dashboard
        {
            "type": "navigation",
            "url": "https://example.com/dashboard",
            "timestamp": 9000,
            "target": None,
            "data": {},
        },
    ]
    return operations


def demo_graph_building():
    """Demonstrate building a StateActionGraph from recording."""
    print("\n" + "=" * 70)
    print("STEP 1: Build StateActionGraph from Recording")
    print("=" * 70)

    # Create sample recording
    operations = create_sample_recording()
    print(f"\n📊 Input: {len(operations)} raw operations")

    # Build graph
    builder = GraphBuilder(user_id="demo_user", session_id="demo_session")
    graph = builder.build(operations)

    # Display results
    print(f"\n✅ Output:")
    print(f"   - States: {len(graph.states)}")
    print(f"   - Actions: {len(graph.actions)}")

    # Show states with intents
    print(f"\n📍 States:")
    for state_id, state in graph.states.items():
        print(f"   {state_id}: {state.page_url}")
        print(f"      └─ {len(state.intents)} intents:")
        for intent in state.intents:
            print(f"         • {intent.type}: {intent.text or intent.value or 'N/A'}")

    # Show actions
    print(f"\n🔀 Actions (State Transitions):")
    for action in graph.actions:
        print(f"   {action.source} → {action.target}")
        print(f"      └─ Type: {action.type}")

    return graph


def demo_memory_storage(graph):
    """Demonstrate storing graph to WorkflowMemory."""
    print("\n" + "=" * 70)
    print("STEP 2: Store to WorkflowMemory")
    print("=" * 70)

    # Create memory
    graph_store = NetworkXGraph()
    memory = WorkflowMemory(graph_store)

    # Store states (with intents)
    print(f"\n💾 Storing {len(graph.states)} states...")
    for state in graph.states.values():
        success = memory.create_state(state)
        if success:
            print(f"   ✓ Stored {state.id}: {state.page_url} ({len(state.intents)} intents)")
        else:
            print(f"   ✗ Failed to store {state.id}")

    # Store actions
    print(f"\n💾 Storing {len(graph.actions)} actions...")
    for action in graph.actions:
        success = memory.create_action(action)
        if success:
            print(f"   ✓ Stored {action.source} → {action.target} ({action.type})")
        else:
            print(f"   ✗ Failed to store action")

    print(f"\n✅ Storage complete!")
    return memory


def demo_memory_query(memory):
    """Demonstrate querying from WorkflowMemory."""
    print("\n" + "=" * 70)
    print("STEP 3: Query from WorkflowMemory")
    print("=" * 70)

    # Query all states
    print(f"\n🔍 Query: List all states")
    states = memory.state_manager.list_states()
    print(f"   Found {len(states)} states:")
    for state in states:
        print(f"   - {state.id}: {state.page_url}")
        print(f"     └─ {len(state.intents)} intents")

    # Query all actions
    print(f"\n🔍 Query: List all actions")
    actions = memory.action_manager.list_actions()
    print(f"   Found {len(actions)} actions:")
    for action in actions:
        print(f"   - {action.source} → {action.target} ({action.type})")

    # Query by session
    print(f"\n🔍 Query: States in session 'demo_session'")
    session_states = memory.state_manager.list_states(session_id="demo_session")
    print(f"   Found {len(session_states)} states")

    # Query connected actions for first state
    if states:
        first_state = states[0]
        print(f"\n🔍 Query: Actions from state {first_state.id}")
        connected_actions = memory.state_manager.get_connected_actions(
            state_id=first_state.id, direction="outgoing"
        )
        print(f"   Found {len(connected_actions)} outgoing actions:")
        for action in connected_actions:
            print(f"   - {action.source} → {action.target} ({action.type})")


def demo_export_to_dict(graph):
    """Demonstrate exporting graph to dictionary."""
    print("\n" + "=" * 70)
    print("STEP 4: Export to Dictionary/JSON")
    print("=" * 70)

    graph_dict = graph.to_dict()

    print(f"\n📦 Exported graph structure:")
    print(f"   - states: {len(graph_dict['states'])} items")
    print(f"   - actions: {len(graph_dict['actions'])} items")
    print(f"   - phases: {len(graph_dict['phases'])} items")
    print(f"   - episodes: {len(graph_dict['episodes'])} items")

    # Show sample state with intents
    if graph_dict["states"]:
        first_state_id = list(graph_dict["states"].keys())[0]
        first_state = graph_dict["states"][first_state_id]
        print(f"\n📄 Sample state structure (JSON):")
        print(json.dumps(first_state, indent=2, ensure_ascii=False)[:500] + "...")

    return graph_dict


def main():
    """Run complete demo."""
    print("\n" + "=" * 70)
    print("🎯 Unified Ontology Demo - Complete Flow")
    print("=" * 70)
    print("\nThis demo shows:")
    print("1. Recording → StateActionGraph (LLM-free)")
    print("2. StateActionGraph → WorkflowMemory (direct storage)")
    print("3. Query and retrieve from memory")
    print("4. Export to dict/JSON")

    try:
        # Step 1: Build graph
        graph = demo_graph_building()

        # Step 2: Store to memory
        memory = demo_memory_storage(graph)

        # Step 3: Query from memory
        demo_memory_query(memory)

        # Step 4: Export to dict
        graph_dict = demo_export_to_dict(graph)

        print("\n" + "=" * 70)
        print("✅ Demo completed successfully!")
        print("=" * 70)
        print("\nKey points:")
        print("• graph_builder directly outputs memgraph ontology")
        print("• No adapter needed - States contain Intents")
        print("• Actions are state transitions only (no self-loops)")
        print("• Direct compatibility with WorkflowMemory")

    except Exception as e:
        print(f"\n❌ Demo failed with error:")
        print(f"   {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
