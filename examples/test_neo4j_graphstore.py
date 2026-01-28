"""Test script for Neo4jGraphStore.

This script tests the Neo4j GraphStore implementation.
Requires a running Neo4j instance.

Usage:
    # Set environment variables
    export NEO4J_URI=neo4j://localhost:7687
    export NEO4J_USER=neo4j
    export NEO4J_PASSWORD=your_password

    # Run tests
    python examples/test_neo4j_graphstore.py
"""

import json
import os
import sys
import uuid
from typing import List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_connection():
    """Test basic connection to Neo4j."""
    print("\n=== Test: Connection ===")

    from src.cloud_backend.memgraph.graphstore import create_graph_store

    try:
        store = create_graph_store("neo4j")
        print(f"✅ Connected successfully")

        stats = store.get_statistics()
        print(f"   Nodes: {stats['num_nodes']}, Edges: {stats['num_edges']}")
        print(f"   Labels: {stats['labels']}")

        store.close()
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


def test_node_crud():
    """Test node CRUD operations."""
    print("\n=== Test: Node CRUD ===")

    from src.cloud_backend.memgraph.graphstore import create_graph_store

    store = create_graph_store("neo4j")

    try:
        # Create
        test_id = f"test_{uuid.uuid4().hex[:8]}"
        store.upsert_node("TestNode", {
            "id": test_id,
            "name": "Test Node",
            "value": 42,
            "tags": ["a", "b"],  # Will be serialized
        })
        print(f"✅ Created node: {test_id}")

        # Read
        node = store.get_node("TestNode", test_id)
        assert node is not None, "Node should exist"
        assert node["name"] == "Test Node"
        assert node["value"] == 42
        print(f"✅ Read node: {node['name']}")

        # Update
        store.upsert_node("TestNode", {
            "id": test_id,
            "name": "Updated Node",
            "value": 100,
        })
        node = store.get_node("TestNode", test_id)
        assert node["name"] == "Updated Node"
        assert node["value"] == 100
        print(f"✅ Updated node: {node['name']}")

        # Query
        nodes = store.query_nodes("TestNode", {"id": test_id})
        assert len(nodes) == 1
        print(f"✅ Queried nodes: {len(nodes)} found")

        # Delete
        deleted = store.delete_node("TestNode", test_id)
        assert deleted
        node = store.get_node("TestNode", test_id)
        assert node is None
        print(f"✅ Deleted node")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        store.close()


def test_relationship_crud():
    """Test relationship CRUD operations."""
    print("\n=== Test: Relationship CRUD ===")

    from src.cloud_backend.memgraph.graphstore import create_graph_store

    store = create_graph_store("neo4j")

    try:
        # Create nodes
        node1_id = f"node1_{uuid.uuid4().hex[:8]}"
        node2_id = f"node2_{uuid.uuid4().hex[:8]}"

        store.upsert_node("TestNode", {"id": node1_id, "name": "Node 1"})
        store.upsert_node("TestNode", {"id": node2_id, "name": "Node 2"})
        print(f"✅ Created nodes: {node1_id}, {node2_id}")

        # Create relationship
        store.upsert_relationship(
            "TestNode", node1_id,
            "TestNode", node2_id,
            "TEST_REL",
            {"weight": 1.5, "type": "test"},
        )
        print(f"✅ Created relationship")

        # Query relationship
        rels = store.query_relationships(
            start_node_label="TestNode",
            start_node_id_value=node1_id,
            rel_type="TEST_REL",
        )
        assert len(rels) == 1
        assert rels[0]["rel"]["weight"] == 1.5
        print(f"✅ Queried relationship: {len(rels)} found")

        # Delete relationship
        deleted = store.delete_relationship(
            "TestNode", node1_id,
            "TestNode", node2_id,
            "TEST_REL",
        )
        assert deleted
        print(f"✅ Deleted relationship")

        # Cleanup nodes
        store.delete_node("TestNode", node1_id)
        store.delete_node("TestNode", node2_id)
        print(f"✅ Cleaned up nodes")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        store.close()


def test_complex_properties():
    """Test serialization of complex properties."""
    print("\n=== Test: Complex Properties ===")

    from src.cloud_backend.memgraph.graphstore import create_graph_store

    store = create_graph_store("neo4j")

    try:
        test_id = f"state_{uuid.uuid4().hex[:8]}"

        # Create node with complex properties
        store.upsert_node("State", {
            "id": test_id,
            "page_url": "https://example.com",
            "page_title": "Test Page",
            "instances": [
                {"url": "https://example.com/1", "timestamp": 1234567890},
                {"url": "https://example.com/2", "timestamp": 1234567900},
            ],
            "intent_sequences": [
                {"description": "Click button", "intents": [{"type": "click", "selector": ".btn"}]},
            ],
            "embedding_vector": [0.1, 0.2, 0.3, 0.4, 0.5],
        })
        print(f"✅ Created node with complex properties")

        # Read and verify
        node = store.get_node("State", test_id)
        assert node is not None
        assert len(node["instances"]) == 2
        assert node["instances"][0]["url"] == "https://example.com/1"
        assert len(node["intent_sequences"]) == 1
        assert node["embedding_vector"] == [0.1, 0.2, 0.3, 0.4, 0.5]
        print(f"✅ Read complex properties correctly")
        print(f"   instances: {len(node['instances'])} items")
        print(f"   intent_sequences: {len(node['intent_sequences'])} items")
        print(f"   embedding_vector: {len(node['embedding_vector'])} dimensions")

        # Cleanup
        store.delete_node("State", test_id)
        print(f"✅ Cleaned up")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        store.close()


def test_batch_operations():
    """Test batch node operations."""
    print("\n=== Test: Batch Operations ===")

    from src.cloud_backend.memgraph.graphstore import create_graph_store

    store = create_graph_store("neo4j")

    try:
        # Batch create
        prefix = f"batch_{uuid.uuid4().hex[:8]}"
        nodes = [
            {"id": f"{prefix}_1", "name": "Batch 1"},
            {"id": f"{prefix}_2", "name": "Batch 2"},
            {"id": f"{prefix}_3", "name": "Batch 3"},
        ]
        store.upsert_nodes("TestNode", nodes)
        print(f"✅ Batch created {len(nodes)} nodes")

        # Verify
        result = store.query_nodes("TestNode")
        batch_nodes = [n for n in result if n["id"].startswith(prefix)]
        assert len(batch_nodes) == 3
        print(f"✅ Verified batch creation: {len(batch_nodes)} nodes")

        # Batch delete
        ids = [f"{prefix}_1", f"{prefix}_2", f"{prefix}_3"]
        deleted = store.delete_nodes("TestNode", ids)
        assert deleted == 3
        print(f"✅ Batch deleted {deleted} nodes")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        store.close()


def test_vector_search():
    """Test vector index and search."""
    print("\n=== Test: Vector Search ===")

    from src.cloud_backend.memgraph.graphstore import create_graph_store

    store = create_graph_store("neo4j")

    try:
        # Create vector index
        store.create_vector_index("State", "embedding_vector", vector_dimensions=5)
        print(f"✅ Created vector index")

        # Create nodes with embeddings
        prefix = f"vec_{uuid.uuid4().hex[:8]}"
        store.upsert_node("State", {
            "id": f"{prefix}_1",
            "name": "Vector 1",
            "embedding_vector": [1.0, 0.0, 0.0, 0.0, 0.0],
        })
        store.upsert_node("State", {
            "id": f"{prefix}_2",
            "name": "Vector 2",
            "embedding_vector": [0.0, 1.0, 0.0, 0.0, 0.0],
        })
        store.upsert_node("State", {
            "id": f"{prefix}_3",
            "name": "Vector 3",
            "embedding_vector": [0.9, 0.1, 0.0, 0.0, 0.0],  # Similar to Vector 1
        })
        print(f"✅ Created nodes with embeddings")

        # Search
        import time
        time.sleep(1)  # Wait for index to update

        results = store.vector_search(
            "State",
            "embedding_vector",
            [1.0, 0.0, 0.0, 0.0, 0.0],  # Query similar to Vector 1
            topk=3,
        )
        print(f"✅ Vector search returned {len(results)} results")

        for node, score in results:
            print(f"   {node['name']}: score={score:.4f}")

        # Cleanup
        store.delete_nodes("State", [f"{prefix}_1", f"{prefix}_2", f"{prefix}_3"])
        store.delete_index("state_embedding_vector")
        print(f"✅ Cleaned up")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        store.close()


def test_workflow_memory_integration():
    """Test integration with WorkflowMemory."""
    print("\n=== Test: WorkflowMemory Integration ===")

    from src.cloud_backend.memgraph.graphstore import create_graph_store
    from src.cloud_backend.memgraph.memory.workflow_memory import WorkflowMemory
    from src.cloud_backend.memgraph.ontology.state import State
    from src.cloud_backend.memgraph.ontology.action import Action

    store = create_graph_store("neo4j")
    store.initialize_schema()

    try:
        memory = WorkflowMemory(store, build_url_index=False)
        print(f"✅ Created WorkflowMemory with Neo4j backend")

        # Create State
        state1 = State(
            page_url="https://example.com/page1",
            page_title="Page 1",
            user_id="test_user",
            session_id="test_session",
        )
        success = memory.create_state(state1)
        assert success
        print(f"✅ Created State: {state1.id}")

        # Create another State
        state2 = State(
            page_url="https://example.com/page2",
            page_title="Page 2",
            user_id="test_user",
            session_id="test_session",
        )
        memory.create_state(state2)
        print(f"✅ Created State: {state2.id}")

        # Create Action
        action = Action(
            source=state1.id,
            target=state2.id,
            type="click",
            description="Click link to page 2",
            user_id="test_user",
        )
        success = memory.create_action(action)
        assert success
        print(f"✅ Created Action: {state1.id} -> {state2.id}")

        # Query
        retrieved = memory.get_state(state1.id)
        assert retrieved is not None
        assert retrieved.page_url == "https://example.com/page1"
        print(f"✅ Retrieved State: {retrieved.page_title}")

        # Export/Import
        data = memory.export_memory()
        assert len(data["states"]) >= 2
        print(f"✅ Exported memory: {len(data['states'])} states, {len(data['actions'])} actions")

        # Cleanup
        memory.delete_state(state1.id)
        memory.delete_state(state2.id)
        print(f"✅ Cleaned up")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        store.close()


def main():
    """Run all tests."""
    print("=" * 60)
    print("Neo4j GraphStore Tests")
    print("=" * 60)

    # Check environment
    uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")

    print(f"\nConfiguration:")
    print(f"  URI: {uri}")
    print(f"  User: {user}")
    print(f"  Password: {'***' if password else '(not set)'}")

    if not password:
        print("\n⚠️  NEO4J_PASSWORD not set. Please set it:")
        print("   export NEO4J_PASSWORD=your_password")
        return

    tests = [
        ("Connection", test_connection),
        ("Node CRUD", test_node_crud),
        ("Relationship CRUD", test_relationship_crud),
        ("Complex Properties", test_complex_properties),
        ("Batch Operations", test_batch_operations),
        ("Vector Search", test_vector_search),
        ("WorkflowMemory Integration", test_workflow_memory_integration),
    ]

    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"❌ {name} crashed: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    passed = sum(1 for _, s in results if s)
    total = len(results)

    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status}: {name}")

    print(f"\nTotal: {passed}/{total} passed")

    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")


if __name__ == "__main__":
    main()
