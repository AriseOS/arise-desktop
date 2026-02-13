#!/usr/bin/env python3
"""Analyze Memory Data Loss - Code inspection of the data pipeline.

This script analyzes the code to identify where intent_sequences are lost
in the Memory pipeline without requiring actual data.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def print_section(title: str):
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_finding(location: str, issue: str, impact: str):
    """Print a finding."""
    print(f"\n📍 {location}")
    print(f"   Issue: {issue}")
    print(f"   Impact: {impact}")


def analyze_code():
    """Analyze the code to trace data flow."""

    print_section("Memory Data Loss Analysis - Code Inspection")

    # Finding 1: StateManager.get_state() implementation
    print_finding(
        location="src/common/memory/memory/workflow_memory.py:388-406",
        issue=(
            "GraphStateManager.get_state() uses graph_store.get_node() "
            "which only retrieves basic State fields from the State node, "
            "but does NOT traverse the ->has_sequence->IntentSequence edge."
        ),
        impact=(
            "❌ Loses intent_sequences at the Memory layer level. "
            "Even though SurrealDB has get_state_with_sequences() method, "
            "StateManager doesn't use it."
        )
    )

    # Evidence
    print("\n   Evidence:")
    print("   ```python")
    print("   def get_state(self, state_id: str) -> Optional[State]:")
    print("       node = self.graph_store.get_node(")
    print("           label=self.node_label, id_value=state_id, id_key='id'")
    print("       )")
    print("       if node:")
    print("           return State.from_dict(node)")
    print("   ```")
    print("   vs. the available method:")
    print("   ```python")
    print("   def get_state_with_sequences(self, state_id: str):")
    print("       query = '''")
    print("           SELECT *,")
    print("               ->has_sequence->intentsequence AS sequences")
    print("           FROM state:`{state_id}`")
    print("       '''")
    print("   ```")

    # Finding 2: SurrealDB has the right method but it's not used
    print_finding(
        location="src/common/memory/graphstore/surrealdb_graph.py:1567-1606",
        issue=(
            "SurrealDBGraphStore.get_state_with_sequences() EXISTS and correctly "
            "retrieves intent_sequences via graph traversal, but it's NEVER called "
            "by StateManager."
        ),
        impact=(
            "⚠️  The infrastructure is correct but not wired up. "
            "This is an integration issue, not a database issue."
        )
    )

    # Finding 3: State.to_dict() depends on what's in the object
    print_finding(
        location="src/common/memory/ontology/state.py",
        issue=(
            "State.to_dict() serializes whatever fields are in the State object. "
            "If intent_sequences field wasn't loaded from database, it won't be "
            "in the dict."
        ),
        impact=(
            "❌ State serialization propagates the loss forward. "
            "Missing intent_sequences in State object → missing in to_dict() "
            "→ missing in API response."
        )
    )

    # Finding 4: Reasoner uses incomplete State objects
    print_finding(
        location="src/common/memory/reasoner/reasoner.py:612",
        issue=(
            "Reasoner._query_task() L1 CognitivePhrase match calls "
            "memory.get_state(state_id) which returns incomplete State objects. "
            "These incomplete objects are used to build QueryResult."
        ),
        impact=(
            "❌ QueryResult contains incomplete states even at the Reasoner level. "
            "The data loss happens before the API layer."
        )
    )

    # Finding 5: API response just serializes what it receives
    print_finding(
        location="src/cloud_backend/main.py:1613",
        issue=(
            "API endpoint calls result.cognitive_phrase.to_dict() which serializes "
            "the incomplete CognitivePhrase and its incomplete State list. "
            "API can't include data that's not in the QueryResult."
        ),
        impact=(
            "❌ API response is incomplete because QueryResult is incomplete. "
            "This is a downstream effect, not the root cause."
        )
    )

    # Finding 6: MemoryToolkit receives incomplete data
    print_finding(
        location=(
            "src/clients/desktop_app/ami_daemon/base_agent/tools/toolkits/"
            "memory_toolkit.py:382-442"
        ),
        issue=(
            "QueryResult.from_api_response() parses the incomplete API response. "
            "When merging State objects into cognitive_phrase, it creates simplified "
            "dicts with only: id, description, page_url, page_title, domain."
        ),
        impact=(
            "❌ Even more data loss during parsing. The simplified dicts explicitly "
            "omit intent_sequences even if they were present (they aren't)."
        )
    )

    # Evidence
    print("\n   Evidence:")
    print("   ```python")
    print("   phrase_data['states'] = [")
    print("       {'id': s.id, 'description': s.description,")
    print("        'page_url': s.page_url, 'page_title': s.page_title,")
    print("        'domain': s.domain}")
    print("       for s in states")
    print("   ]")
    print("   ```")

    # Finding 7: AMITaskPlanner formatting can't extract what isn't there
    print_finding(
        location=(
            "src/clients/desktop_app/ami_daemon/base_agent/core/"
            "ami_task_planner.py:755-810"
        ),
        issue=(
            "_format_cognitive_phrase() only extracts state.description. "
            "Even if intent_sequences were present, they wouldn't be formatted. "
            "But they're not present anyway due to upstream losses."
        ),
        impact=(
            "❌ workflow_guide ends up with abstract descriptions only, "
            "missing URLs, operations, and intent_sequences."
        )
    )

    # Summary
    print_section("ROOT CAUSE IDENTIFIED")

    print("""
The root cause is at the Memory layer:

🔴 PRIMARY ISSUE: GraphStateManager.get_state() (workflow_memory.py:388-406)
   - Uses graph_store.get_node() instead of get_state_with_sequences()
   - Does NOT retrieve intent_sequences from database
   - Returns incomplete State objects

🟡 SECONDARY ISSUE: MemoryToolkit parsing (memory_toolkit.py:395-407)
   - Creates simplified State dicts that omit intent_sequences
   - Would lose data even if it were retrieved (but it isn't)

🟡 TERTIARY ISSUE: AMITaskPlanner formatting (ami_task_planner.py:755-810)
   - Only extracts state.description
   - Doesn't format intent_sequences even if present
    """)

    print_section("FIX REQUIRED")

    print("""
To fix the data loss, changes are needed in THREE places:

1. ✅ FIX AT SOURCE (REQUIRED):
   File: src/common/memory/memory/workflow_memory.py
   Line: 388-406

   Change GraphStateManager.get_state() to use get_state_with_sequences():

   ```python
   def get_state(self, state_id: str) -> Optional[State]:
       # OLD: node = self.graph_store.get_node(...)
       # NEW:
       if hasattr(self.graph_store, 'get_state_with_sequences'):
           node = self.graph_store.get_state_with_sequences(state_id)
       else:
           node = self.graph_store.get_node(
               label=self.node_label, id_value=state_id, id_key='id'
           )
       if node:
           return State.from_dict(node)
       return None
   ```

2. ⚠️  UPDATE PARSING (RECOMMENDED):
   File: src/clients/desktop_app/ami_daemon/base_agent/tools/toolkits/memory_toolkit.py
   Line: 395-407

   Include intent_sequences when building State dicts:

   ```python
   phrase_data['states'] = [
       {
           'id': s.id,
           'description': s.description,
           'page_url': s.page_url,
           'page_title': s.page_title,
           'domain': s.domain,
           'intent_sequences': s.intent_sequences  # ADD THIS
       }
       for s in states
   ]
   ```

3. ⚠️  ENHANCE FORMATTING (RECOMMENDED):
   File: src/clients/desktop_app/ami_daemon/base_agent/core/ami_task_planner.py
   Line: 755-810

   Include intent_sequences in workflow_guide:

   ```python
   # After extracting state description
   if hasattr(state, 'intent_sequences') and state.intent_sequences:
       lines.append(f"    Available operations:")
       for seq in state.intent_sequences:
           lines.append(f"      - {seq.description}")
   ```
    """)

    print_section("EXPECTED IMPACT")

    print("""
After implementing Fix #1 (the root cause):

✅ Database query will retrieve intent_sequences
✅ State objects will have complete data
✅ QueryResult will include intent_sequences
✅ API response will include intent_sequences
✅ MemoryToolkit will receive complete data
✅ workflow_guide can potentially include operational details

Additional fixes (#2, #3) will ensure the data is properly used once retrieved.
    """)


if __name__ == "__main__":
    analyze_code()
