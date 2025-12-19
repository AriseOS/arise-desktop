#!/usr/bin/env python3
"""
StorageAgent Unit Tests via Daemon API

Tests StorageAgent functionality through daemon API:
1. Simple flat data insertion
2. Nested data structure flattening
3. Cache validation
4. Schema verification

Requirements:
- Daemon must be running (python -m src.app_backend.daemon)
"""

import asyncio
import sys
import logging
import json
import aiosqlite
import aiohttp
from pathlib import Path

# Setup paths
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.app_backend.core.config_service import get_config

API_BASE = "http://127.0.0.1:8765"

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


async def check_daemon():
    """Check if daemon is running"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE}/health", timeout=aiohttp.ClientTimeout(total=2)) as response:
                return response.status == 200
    except:
        return False


async def save_workflow(user_id: str, workflow_name: str, workflow_yaml: str):
    """Save workflow file"""
    workflows_dir = Path.home() / ".ami" / "users" / user_id / "workflows" / workflow_name
    workflows_dir.mkdir(parents=True, exist_ok=True)

    workflow_file = workflows_dir / "workflow.yaml"
    with open(workflow_file, 'w') as f:
        f.write(workflow_yaml)

    logger.info(f"Saved workflow: {workflow_file}")


async def execute_workflow(user_id: str, workflow_name: str, max_wait: int = 30):
    """Execute workflow and wait for completion"""
    async with aiohttp.ClientSession() as session:
        # Execute workflow
        async with session.post(
            f"{API_BASE}/api/workflow/execute",
            json={"workflow_name": workflow_name, "user_id": user_id}
        ) as response:
            if response.status != 200:
                error = await response.text()
                logger.error(f"❌ Workflow execution failed: {error}")
                return False, None

            result = await response.json()
            task_id = result.get('task_id')
            logger.info(f"✅ Workflow started: {task_id}")

        # Poll for completion
        workflow_completed = False
        workflow_status = None
        for i in range(max_wait):
            await asyncio.sleep(1)
            async with session.get(f"{API_BASE}/api/workflow/status/{task_id}") as status_response:
                if status_response.status == 200:
                    status_data = await status_response.json()
                    state = status_data.get('status')

                    if state == 'completed':
                        workflow_completed = True
                        workflow_status = status_data
                        logger.info(f"✅ Workflow completed")
                        break
                    elif state == 'failed':
                        error_msg = status_data.get('error', 'Unknown error')
                        logger.error(f"❌ Workflow failed: {error_msg}")
                        return False, status_data

        if not workflow_completed:
            logger.error(f"❌ Workflow timeout after {max_wait} seconds")
            return False, None

        return True, workflow_status


async def test_simple_flat_data():
    """Test 1: Simple flat data insertion"""
    logger.info("=" * 70)
    logger.info("TEST 1: Simple Flat Data Insertion")
    logger.info("=" * 70)

    test_collection = "test_simple_products"
    user_id = "test_user"
    table_name = f"{test_collection}_{user_id}"

    test_data = [
        {"name": "Product A", "price": 10.99, "stock": 100},
        {"name": "Product B", "price": 25.50, "stock": 50},
        {"name": "Product C", "price": 15.00, "stock": 75}
    ]

    config = get_config()
    storage_db = str(config.get('data.databases.storage'))
    kv_db = str(config.get('data.databases.kv'))

    logger.info(f"\nTest setup:")
    logger.info(f"  Collection: {test_collection}")
    logger.info(f"  User: {user_id}")
    logger.info(f"  Table: {table_name}")
    logger.info(f"  Records: {len(test_data)}")

    # Cleanup
    logger.info(f"\n--- Cleanup ---")
    async with aiosqlite.connect(storage_db) as db:
        await db.execute(f"DROP TABLE IF EXISTS {table_name}")
        await db.commit()

    async with aiosqlite.connect(kv_db) as db:
        cache_key = f"storage_insert_{test_collection}_{user_id}"
        await db.execute("DELETE FROM kv_storage WHERE key = ?", (cache_key,))
        await db.commit()

    logger.info(f"✅ Cleaned up old table and cache")

    # Create workflow
    workflow_name = "test_simple_store"
    workflow_yaml = f"""apiVersion: "ami.io/v1"
kind: "Workflow"

metadata:
  name: "{workflow_name}"
  description: "Test simple data storage"
  version: "1.0.0"

steps:
  - id: store_data
    name: Store simple products
    agent_type: storage_agent
    description: Insert simple product data
    inputs:
      operation: store
      collection: {test_collection}
      data: {json.dumps(test_data)}
    timeout: 30
"""

    await save_workflow(user_id, workflow_name, workflow_yaml)

    # Execute workflow
    logger.info(f"\n--- Execute Workflow ---")
    success, status = await execute_workflow(user_id, workflow_name)

    if not success:
        logger.error(f"❌ TEST 1 FAILED")
        return False

    # Verify table creation
    logger.info(f"\n--- Verify Results ---")
    async with aiosqlite.connect(storage_db) as db:
        # Check table exists
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        ) as cursor:
            table_exists = await cursor.fetchone()

        if not table_exists:
            logger.error(f"❌ Table {table_name} not found!")
            return False

        logger.info(f"✅ Table exists: {table_name}")

        # Get schema
        async with db.execute(f"PRAGMA table_info({table_name})") as cursor:
            columns = await cursor.fetchall()
            logger.info(f"\nTable schema:")
            for col in columns:
                col_id, col_name, col_type, not_null, default_val, pk = col
                logger.info(f"  - {col_name} ({col_type})")

        # Count records
        async with db.execute(f"SELECT COUNT(*) FROM {table_name}") as cursor:
            count = await cursor.fetchone()
            row_count = count[0]

        if row_count != len(test_data):
            logger.error(f"❌ Expected {len(test_data)} rows, got {row_count}")
            return False

        logger.info(f"\n✅ Record count correct: {row_count}")

        # Show data
        async with db.execute(f"SELECT name, price, stock FROM {table_name}") as cursor:
            rows = await cursor.fetchall()
            logger.info(f"\nActual data:")
            for row in rows:
                logger.info(f"  {row}")

    # Verify cache
    logger.info(f"\n--- Verify Cache ---")
    cache_key = f"storage_insert_{test_collection}_{user_id}"
    async with aiosqlite.connect(kv_db) as db:
        async with db.execute(
            "SELECT value FROM kv_storage WHERE key=?",
            (cache_key,)
        ) as cursor:
            cache_row = await cursor.fetchone()

        if not cache_row:
            logger.error(f"❌ Cache not found: {cache_key}")
            return False

        cached_data = json.loads(cache_row[0])
        logger.info(f"✅ Cache exists")
        logger.info(f"  Field order: {cached_data.get('field_order')}")

    logger.info("\n" + "=" * 70)
    logger.info("✅ TEST 1 PASSED")
    logger.info("=" * 70)
    return True


async def test_nested_data_flattening():
    """Test 2: Nested data structure flattening"""
    logger.info("\n" + "=" * 70)
    logger.info("TEST 2: Nested Data Flattening")
    logger.info("=" * 70)

    test_collection = "test_nested_products"
    user_id = "test_user"
    table_name = f"{test_collection}_{user_id}"

    # Nested data structure (like ProductHunt data)
    nested_data = {
        "product": [
            {
                "product_name": "Talo",
                "tagline": "AI translator for calls and events",
                "description": "Real-time voice translation",
                "rating": "5.0",
                "reviews": "6 reviews",
                "followers": "2K followers"
            }
        ],
        "team": [
            {"name": "Max Kudinov", "role": "Building AI translator", "product": "Talo"},
            {"name": "Alexander Kabakov", "role": "Co-Founder", "product": "Talo"}
        ]
    }

    config = get_config()
    storage_db = str(config.get('data.databases.storage'))
    kv_db = str(config.get('data.databases.kv'))

    logger.info(f"\nTest data (nested structure):")
    logger.info(f"  Data keys: {list(nested_data.keys())}")
    logger.info(f"  Product fields: {list(nested_data['product'][0].keys())}")
    logger.info(f"  Team fields: {list(nested_data['team'][0].keys())}")

    # Cleanup
    logger.info(f"\n--- Cleanup ---")
    async with aiosqlite.connect(storage_db) as db:
        await db.execute(f"DROP TABLE IF EXISTS {table_name}")
        await db.commit()

    async with aiosqlite.connect(kv_db) as db:
        cache_key = f"storage_insert_{test_collection}_{user_id}"
        await db.execute("DELETE FROM kv_storage WHERE key = ?", (cache_key,))
        await db.commit()

    logger.info(f"✅ Cleaned up old table and cache")

    # Create workflow
    workflow_name = "test_nested_store"
    workflow_yaml = f"""apiVersion: "ami.io/v1"
kind: "Workflow"

metadata:
  name: "{workflow_name}"
  description: "Test nested data storage"
  version: "1.0.0"

steps:
  - id: store_data
    name: Store nested data
    agent_type: storage_agent
    description: Insert nested product data
    inputs:
      operation: store
      collection: {test_collection}
      data: {json.dumps(nested_data)}
    timeout: 60
"""

    await save_workflow(user_id, workflow_name, workflow_yaml)

    # Execute workflow
    logger.info(f"\n--- Execute Workflow ---")
    success, status = await execute_workflow(user_id, workflow_name, max_wait=60)

    if not success:
        logger.error(f"❌ TEST 2 FAILED")
        return False

    # Verify flattened table
    logger.info(f"\n--- Verify Flattened Table ---")
    async with aiosqlite.connect(storage_db) as db:
        # Check table exists
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        ) as cursor:
            table_exists = await cursor.fetchone()

        if not table_exists:
            logger.error(f"❌ Table {table_name} not found!")
            return False

        logger.info(f"✅ Table exists: {table_name}")

        # Get flattened schema
        async with db.execute(f"PRAGMA table_info({table_name})") as cursor:
            columns = await cursor.fetchall()
            logger.info(f"\nFlattened table schema:")
            for col in columns:
                col_id, col_name, col_type, not_null, default_val, pk = col
                logger.info(f"  - {col_name} ({col_type})")

        # Verify data inserted
        async with db.execute(f"SELECT COUNT(*) FROM {table_name}") as cursor:
            count = await cursor.fetchone()
            row_count = count[0]

        if row_count != 1:
            logger.error(f"❌ Expected 1 row, got {row_count}")
            return False

        logger.info(f"\n✅ Record count correct: {row_count}")

        # Show flattened data
        async with db.execute(f"SELECT * FROM {table_name}") as cursor:
            row = await cursor.fetchone()
            if row:
                logger.info(f"\nFlattened data in table:")
                col_names = [desc[0] for desc in cursor.description]
                for col_name, value in zip(col_names, row):
                    if col_name not in ('id', 'created_at'):
                        display_value = value[:50] + "..." if isinstance(value, str) and len(value) > 50 else value
                        logger.info(f"  {col_name}: {display_value}")

    # Verify cache
    logger.info(f"\n--- Verify Cache ---")
    cache_key = f"storage_insert_{test_collection}_{user_id}"
    async with aiosqlite.connect(kv_db) as db:
        async with db.execute(
            "SELECT value FROM kv_storage WHERE key=?",
            (cache_key,)
        ) as cursor:
            cache_row = await cursor.fetchone()

        if not cache_row:
            logger.error(f"❌ Cache not found: {cache_key}")
            return False

        cached_data = json.loads(cache_row[0])
        logger.info(f"✅ Cache exists")
        logger.info(f"  Field order: {cached_data.get('field_order')}")

    logger.info("\n" + "=" * 70)
    logger.info("✅ TEST 2 PASSED - Nested data successfully flattened!")
    logger.info("=" * 70)
    return True


async def main():
    """Run all tests"""
    logger.info("\n" + "=" * 70)
    logger.info("STORAGE AGENT TESTS (via Daemon API)")
    logger.info("=" * 70 + "\n")

    # Check daemon
    logger.info("Checking daemon status...")
    daemon_running = await check_daemon()

    if not daemon_running:
        logger.error("❌ Daemon is NOT running!")
        logger.error("\nPlease start daemon first:")
        logger.error("  cd /Users/shenyouren/workspace/arise-project/ami/Ami")
        logger.error("  python -m src.app_backend.daemon")
        return False

    logger.info("✅ Daemon is running\n")

    # Run tests
    tests = [
        ("Simple flat data insertion", test_simple_flat_data),
        ("Nested data flattening", test_nested_data_flattening),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            result = await test_func()
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"❌ EXCEPTION in {test_name}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    logger.info("\n" + "=" * 70)
    logger.info(f"TEST SUMMARY: {passed} passed, {failed} failed")
    logger.info("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
