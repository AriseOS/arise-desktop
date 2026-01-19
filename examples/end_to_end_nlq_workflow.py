"""
End-to-End: Recording → Memory → NL Query → Workflow Execution

This example demonstrates the complete flow:
1. Record user actions (raw operations)
2. Build StateActionGraph using GraphBuilder (LLM-free)
3. Store to WorkflowMemory
4. User provides natural language query
5. Reasoner retrieves from memory and generates workflow
6. Workflow can be executed

Usage:
    cd /Users/wangz/Workspace/Ami
    PYTHONPATH=. python examples/end_to_end_nlq_workflow.py
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.cloud_backend.graph_builder import GraphBuilder
from src.cloud_backend.memgraph.graphstore.networkx_graph import NetworkXGraph
from src.cloud_backend.memgraph.memory.workflow_memory import WorkflowMemory
from src.cloud_backend.memgraph.reasoner.reasoner import Reasoner


def create_sample_recordings():
    """Create multiple sample recordings simulating different user tasks.

    Returns:
        Dict of recording_name -> operations
    """
    return {
        "form_submission": [
            {
                "type": "navigation",
                "url": "https://example.com/form",
                "timestamp": 1000,
                "target": None,
                "data": {},
            },
            {
                "type": "click",
                "url": "https://example.com/form",
                "timestamp": 2000,
                "target": {
                    "tag": "input",
                    "role": "textbox",
                    "text": "Name",
                    "xpath": "/html/body/form/input[1]",
                },
                "data": {},
            },
            {
                "type": "input",
                "url": "https://example.com/form",
                "timestamp": 3000,
                "target": {
                    "tag": "input",
                    "role": "textbox",
                    "text": "Name",
                    "xpath": "/html/body/form/input[1]",
                },
                "data": {"value": "John Doe"},
            },
            {
                "type": "click",
                "url": "https://example.com/form",
                "timestamp": 4000,
                "target": {
                    "tag": "input",
                    "role": "textbox",
                    "text": "Email",
                    "xpath": "/html/body/form/input[2]",
                },
                "data": {},
            },
            {
                "type": "input",
                "url": "https://example.com/form",
                "timestamp": 5000,
                "target": {
                    "tag": "input",
                    "role": "textbox",
                    "text": "Email",
                    "xpath": "/html/body/form/input[2]",
                },
                "data": {"value": "john@example.com"},
            },
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
        ],
        "login": [
            {
                "type": "navigation",
                "url": "https://example.com/login",
                "timestamp": 10000,
                "target": None,
                "data": {},
            },
            {
                "type": "input",
                "url": "https://example.com/login",
                "timestamp": 11000,
                "target": {
                    "tag": "input",
                    "role": "textbox",
                    "text": "Username",
                    "xpath": "/html/body/form/input[1]",
                },
                "data": {"value": "testuser"},
            },
            {
                "type": "input",
                "url": "https://example.com/login",
                "timestamp": 12000,
                "target": {
                    "tag": "input",
                    "role": "password",
                    "text": "Password",
                    "xpath": "/html/body/form/input[2]",
                },
                "data": {"value": "password123"},
            },
            {
                "type": "click",
                "url": "https://example.com/login",
                "timestamp": 13000,
                "target": {
                    "tag": "button",
                    "role": "button",
                    "text": "Login",
                    "xpath": "/html/body/form/button",
                },
                "data": {},
            },
        ],
    }


async def step1_record_and_store():
    """Step 1: Record actions and store to memory"""
    print("\n" + "=" * 80)
    print("STEP 1: Record → Graph Builder → Memory Storage")
    print("=" * 80)

    recordings = create_sample_recordings()

    # Initialize memory
    graph_store = NetworkXGraph()
    memory = WorkflowMemory(graph_store)

    # Process each recording
    for recording_name, operations in recordings.items():
        print(f"\n📝 Processing recording: {recording_name}")
        print(f"   Operations: {len(operations)}")

        # Build graph using GraphBuilder (LLM-free, deterministic)
        builder = GraphBuilder(
            user_id="demo_user",
            session_id=f"session_{recording_name}"
        )
        graph = builder.build(operations)

        print(f"   Graph built: {len(graph.states)} states, {len(graph.actions)} actions")

        # Store to memory
        for state in graph.states.values():
            success = memory.create_state(state)
            if not success:
                print(f"   ⚠️  Failed to store state {state.id}")

        for action in graph.actions:
            success = memory.create_action(action)
            if not success:
                print(f"   ⚠️  Failed to store action {action.source} → {action.target}")

        print(f"   ✅ Stored {len(graph.states)} states and {len(graph.actions)} actions")

    # Show memory statistics
    all_states = memory.state_manager.list_states()
    all_actions = memory.action_manager.list_actions()
    print(f"\n📊 Memory Statistics:")
    print(f"   Total states: {len(all_states)}")
    print(f"   Total actions: {len(all_actions)}")

    return memory


async def step2_query_with_nl(memory: WorkflowMemory):
    """Step 2: Query memory with natural language using Reasoner"""
    print("\n" + "=" * 80)
    print("STEP 2: Natural Language Query → Reasoner → Workflow")
    print("=" * 80)

    # Note: This requires ANTHROPIC_API_KEY environment variable
    # For demo purposes, we'll show the flow without actual LLM calls
    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        print("\n⚠️  ANTHROPIC_API_KEY not set - showing simulated flow")
        print("   To run with actual LLM, set: export ANTHROPIC_API_KEY=your_key")

        # Simulated query demonstration
        queries = [
            "Fill out the form with user information",
            "Login to the system",
            "Submit the contact form",
        ]

        print("\n📝 Example Queries (would be processed by Reasoner):")
        for i, query in enumerate(queries, 1):
            print(f"   {i}. {query}")

        print("\n💡 Without LLM, we can demonstrate direct memory retrieval:")
        await demo_direct_retrieval(memory)
        return

    # With LLM: Use Reasoner
    print("\n🔥 With ANTHROPIC_API_KEY, you can use Reasoner:")
    print("   reasoner = Reasoner(memory, llm_client, embedding_service)")
    print("   result = reasoner.plan('Fill out the form')")
    print("   ")
    print("   The Reasoner will:")
    print("   1. Check cognitive_phrases for matches")
    print("   2. If no match, decompose into tasks using LLM")
    print("   3. Retrieve relevant states/actions from memory")
    print("   4. Convert to executable workflow")
    print("   ")
    print("   Example queries that would work:")
    queries = [
        "Fill out the form with user information",
        "Login to the system",
    ]
    for i, query in enumerate(queries, 1):
        print(f"      {i}. {query}")


async def demo_direct_retrieval(memory: WorkflowMemory):
    """Demonstrate direct retrieval from memory without LLM"""
    print("\n📊 Direct Memory Retrieval Demo:")

    # Retrieve states by session
    print("\n1️⃣  Retrieve by session:")
    form_states = memory.state_manager.list_states(session_id="session_form_submission")
    login_states = memory.state_manager.list_states(session_id="session_login")

    print(f"   Form submission session: {len(form_states)} states")
    for state in form_states:
        print(f"      - {state.id}: {state.page_url}")
        print(f"        └─ {len(state.intents)} intents")

    print(f"\n   Login session: {len(login_states)} states")
    for state in login_states:
        print(f"      - {state.id}: {state.page_url}")
        print(f"        └─ {len(state.intents)} intents")

    # Show state details
    if form_states:
        print("\n2️⃣  State Details (Form submission):")
        state = form_states[0]
        print(f"   State ID: {state.id}")
        print(f"   URL: {state.page_url}")
        print(f"   Intents:")
        for intent in state.intents[:5]:  # Show first 5
            print(f"      • {intent.type}: {intent.value or intent.text or 'N/A'}")

    # Retrieve by user
    print("\n3️⃣  Retrieve all user's states:")
    user_states = memory.state_manager.list_states(user_id="demo_user")
    print(f"   User 'demo_user' has {len(user_states)} states across all sessions")

    # Show how to get connected actions
    if user_states:
        first_state = user_states[0]
        print(f"\n4️⃣  Connected actions from state {first_state.id}:")
        outgoing = memory.state_manager.get_connected_actions(
            state_id=first_state.id,
            direction="outgoing"
        )
        print(f"   Outgoing actions: {len(outgoing)}")
        for action in outgoing:
            print(f"      → {action.target} ({action.type})")


def step3_workflow_execution():
    """Step 3: Execute the generated workflow"""
    print("\n" + "=" * 80)
    print("STEP 3: Workflow Execution")
    print("=" * 80)

    print("\n🚀 Workflow execution would happen here:")
    print("   1. Workflow JSON/YAML is passed to WorkflowExecutor")
    print("   2. Executor interprets steps and calls appropriate agents")
    print("   3. Browser automation, API calls, etc. are performed")
    print("   4. Results are returned to user")

    print("\n📝 Example workflow structure:")
    example_workflow = {
        "metadata": {
            "name": "Fill Form Workflow",
            "version": "1.0",
            "description": "Automatically fill out the form"
        },
        "steps": [
            {
                "id": "step_1",
                "action": "navigate",
                "params": {"url": "https://example.com/form"}
            },
            {
                "id": "step_2",
                "action": "input",
                "params": {
                    "xpath": "/html/body/form/input[1]",
                    "value": "John Doe"
                }
            },
            {
                "id": "step_3",
                "action": "input",
                "params": {
                    "xpath": "/html/body/form/input[2]",
                    "value": "john@example.com"
                }
            },
            {
                "id": "step_4",
                "action": "click",
                "params": {"xpath": "/html/body/form/button"}
            }
        ]
    }

    print(json.dumps(example_workflow, indent=2))


async def main():
    """Run complete end-to-end demo"""
    print("\n" + "=" * 80)
    print("🎯 End-to-End Demo: Recording → Memory → NL Query → Workflow")
    print("=" * 80)

    print("\nThis demo shows the complete flow:")
    print("1. Record user actions (raw operations)")
    print("2. Build StateActionGraph using GraphBuilder (deterministic, no LLM)")
    print("3. Store States/Intents/Actions to WorkflowMemory")
    print("4. Query memory with natural language using Reasoner")
    print("5. Generate and execute workflow")

    try:
        # Step 1: Record and store
        memory = await step1_record_and_store()

        # Step 2: Query with NL
        await step2_query_with_nl(memory)

        # Step 3: Workflow execution (demo only)
        step3_workflow_execution()

        print("\n" + "=" * 80)
        print("✅ Demo completed successfully!")
        print("=" * 80)

        print("\n🔑 Key Points:")
        print("• Recording → Graph Builder: LLM-free, deterministic")
        print("• Graph → Memory: Direct storage using unified ontology")
        print("• NL Query → Reasoner: LLM-powered semantic matching")
        print("• Memory → Workflow: Automatic workflow generation")
        print("• End-to-end: From recording to execution")

        print("\n📚 Next Steps:")
        print("• Add embedding service for semantic search")
        print("• Implement cognitive phrases for faster retrieval")
        print("• Add workflow execution monitoring")
        print("• Build feedback loop for workflow improvement")

    except Exception as e:
        print(f"\n❌ Demo failed with error:")
        print(f"   {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
