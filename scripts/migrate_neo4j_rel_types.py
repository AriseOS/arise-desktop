#!/usr/bin/env python3
"""Neo4j Relationship Type Migration Script

This script migrates existing Neo4j relationships from UPPERCASE to lowercase.
Run this after deploying the relationship type normalization fix.

Usage:
    python scripts/migrate_neo4j_rel_types.py

Before running:
    1. Make sure Neo4j is running
    2. Update connection settings below if needed
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Neo4j connection settings
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "your_password"  # CHANGE THIS!


def migrate_relationship_types():
    """Migrate all uppercase relationships to lowercase."""

    try:
        from neo4j import GraphDatabase

        print("\n" + "="*60)
        print("Neo4j Relationship Type Migration")
        print("="*60)

        # Connect to Neo4j
        print(f"\nConnecting to Neo4j at {NEO4J_URI}...")
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

        with driver.session() as session:
            # Check current state
            print("\n1. Checking current relationship types...")
            result = session.run("CALL db.relationshipTypes()")
            current_types = [record["relationshipType"] for record in result]
            print(f"   Found {len(current_types)} relationship types:")
            for rel_type in sorted(current_types):
                print(f"     - {rel_type}")

            # Find uppercase relationships
            uppercase_types = [t for t in current_types if t.isupper() or t != t.lower()]

            if not uppercase_types:
                print("\n✅ No uppercase relationship types found. Database is already normalized.")
                return

            print(f"\n2. Found {len(uppercase_types)} uppercase types to migrate:")
            for rel_type in uppercase_types:
                # Count relationships
                result = session.run(f"MATCH ()-[r:{rel_type}]->() RETURN count(r) AS count")
                count = result.single()["count"]
                print(f"   - {rel_type}: {count} relationships")

            # Confirm migration
            print("\n" + "="*60)
            response = input("Proceed with migration? (yes/no): ").strip().lower()
            if response != "yes":
                print("Migration cancelled.")
                return

            # Migrate each uppercase type to lowercase
            print("\n3. Migrating relationships...")
            for old_type in uppercase_types:
                new_type = old_type.lower()

                print(f"\n   Migrating {old_type} → {new_type}...")

                # Use apoc.do.when if available, otherwise use manual approach
                try:
                    # Try using APOC procedure (faster)
                    result = session.run(f"""
                        MATCH (a)-[r:{old_type}]->(b)
                        WITH a, r, b
                        CALL apoc.create.relationship(a, '{new_type}', {{}}, b) YIELD rel
                        DELETE r
                        RETURN count(*) AS migrated
                    """)
                    count = result.single()["migrated"]
                    print(f"     ✅ Migrated {count} relationships (using APOC)")

                except Exception:
                    # Fallback: Manual migration (slower but works without APOC)
                    result = session.run(f"""
                        MATCH (a)-[r:{old_type}]->(b)
                        WITH a, r, b
                        CREATE (a)-[r2:{new_type}]->(b)
                        SET r2 = r
                        WITH r
                        DELETE r
                        RETURN count(*) AS migrated
                    """)
                    count = result.single()["migrated"]
                    print(f"     ✅ Migrated {count} relationships (manual)")

            # Verify migration
            print("\n4. Verifying migration...")
            result = session.run("CALL db.relationshipTypes()")
            new_types = [record["relationshipType"] for record in result]
            print(f"   Current relationship types ({len(new_types)}):")
            for rel_type in sorted(new_types):
                print(f"     - {rel_type}")

            # Check for remaining uppercase types
            remaining_upper = [t for t in new_types if t.isupper() or t != t.lower()]
            if remaining_upper:
                print(f"\n   ⚠️  Warning: {len(remaining_upper)} uppercase types still exist:")
                for rel_type in remaining_upper:
                    print(f"     - {rel_type}")
            else:
                print("\n   ✅ All relationship types are now lowercase!")

        driver.close()

        print("\n" + "="*60)
        print("✅ Migration completed successfully!")
        print("="*60 + "\n")

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def clear_database():
    """Alternative: Clear all data and start fresh."""

    try:
        from neo4j import GraphDatabase

        print("\n" + "="*60)
        print("⚠️  DANGER: Clear Entire Database")
        print("="*60)
        print("\nThis will DELETE ALL nodes and relationships!")
        print("Only use this for development/testing databases.\n")

        response = input("Type 'DELETE ALL DATA' to confirm: ").strip()
        if response != "DELETE ALL DATA":
            print("Cancelled.")
            return

        print("\nConnecting to Neo4j...")
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

        with driver.session() as session:
            print("Deleting all data...")
            result = session.run("MATCH (n) DETACH DELETE n")
            summary = result.consume()
            print(f"✅ Deleted {summary.counters.nodes_deleted} nodes")
            print(f"✅ Deleted {summary.counters.relationships_deleted} relationships")

        driver.close()
        print("\n✅ Database cleared. You can now start fresh with lowercase relationships.\n")

    except Exception as e:
        print(f"\n❌ Failed to clear database: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate Neo4j relationship types to lowercase")
    parser.add_argument("--clear", action="store_true", help="Clear entire database (development only)")
    args = parser.parse_args()

    if args.clear:
        clear_database()
    else:
        migrate_relationship_types()
