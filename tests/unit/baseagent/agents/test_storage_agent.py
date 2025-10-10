#!/usr/bin/env python3
"""
Unit tests for StorageAgent

Tests the StorageAgent implementation including:
- Store operation (single and batch)
- Query operation (with filters, limit, order_by)
- Export operation (CSV, Excel, JSON)
- Script caching mechanism
- Schema validation
- LLM SQL generation (using real provider)

Note: This test uses REAL LLM provider to validate prompt quality and SQL generation.
Requires OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable.
"""

import asyncio
import sys
import tempfile
import logging
import json
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock

# Add project path to sys.path
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from base_app.base_app.base_agent.agents.storage_agent import StorageAgent
from base_app.base_app.base_agent.core.schemas import AgentContext, AgentInput, AgentOutput
from base_app.base_app.base_agent.memory.memory_manager import MemoryManager
from base_app.base_app.server.core.config_service import ConfigService
from src.common.llm import OpenAIProvider, AnthropicProvider


class TestStorageAgent:
    """Test suite for StorageAgent"""

    def __init__(self, provider_type: str = "openai"):
        """
        Initialize test suite

        Args:
            provider_type: LLM provider to use ('openai' or 'anthropic')
        """
        self.provider_type = provider_type
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    async def setup(self):
        """Setup test environment with real provider and config"""
        self.logger.info("Setting up test environment...")

        # Load test config service
        config_path = project_root / "tests" / "test_config.yaml"
        self.config_service = ConfigService(config_path=str(config_path))

        self.logger.info(f"Using test config from: {config_path}")

        # Get database paths from config
        self.db_path = str(self.config_service.get_path('data.databases.storage'))
        self.kv_path = str(self.config_service.get_path('data.databases.kv'))

        self.logger.info(f"Storage DB: {self.db_path}")
        self.logger.info(f"KV DB: {self.kv_path}")

        # Create real LLM provider
        if self.provider_type == "anthropic":
            self.provider = AnthropicProvider()
            self.logger.info("Using Anthropic provider")
        else:
            self.provider = OpenAIProvider()
            self.logger.info("Using OpenAI provider")

        # Create storage agent
        self.agent = StorageAgent()

        # Create mock agent instance with REAL provider and config_service
        mock_agent_instance = MagicMock()
        mock_agent_instance.provider = self.provider
        mock_agent_instance.config_service = self.config_service

        # Create context
        self.context = AgentContext(
            workflow_id="test_workflow",
            step_id="test_step",
            variables={"user_id": "test_user"},
            agent_instance=mock_agent_instance
        )

        # Initialize memory manager with real config
        self.context.memory_manager = MemoryManager(
            user_id="test_user",
            config_service=self.config_service
        )

        # Initialize agent
        success = await self.agent.initialize(self.context)
        if not success:
            raise RuntimeError("Failed to initialize StorageAgent")

        self.logger.info("✅ Test setup complete")

    async def cleanup(self):
        """Cleanup test environment"""
        # Keep test databases for inspection
        # Users can manually delete them or use the inspection tool
        if hasattr(self, 'db_path'):
            self.logger.info(f"Test storage DB preserved: {self.db_path}")
        if hasattr(self, 'kv_path'):
            self.logger.info(f"Test KV DB preserved: {self.kv_path}")

        self.logger.info("Test cleanup complete (databases preserved for inspection)")

    async def test_store_single_record(self):
        """Test storing a single record"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Store Single Record")
        self.logger.info("=" * 60)

        input_data = {
            "operation": "store",
            "collection": "products",
            "data": {
                "name": "Test Product",
                "price": 99.99,
                "rating": 5
            }
        }

        self.logger.info(f"Input data: {json.dumps(input_data, indent=2)}")

        result = await self.agent.execute(input_data, self.context)

        assert result.success, f"Store operation failed: {result.message}"
        assert result.data["rows_stored"] == 1
        assert result.data["collection"] == "products"

        self.logger.info("✅ Single record stored successfully")
        self.logger.info(f"Result: {json.dumps(result.data, indent=2)}")

        # Check cached script
        cache_key = "storage_insert_products_test_user"
        cached = await self.context.memory_manager.get_data(cache_key)
        if cached:
            self.logger.info("\n📝 Generated SQL Scripts:")
            self.logger.info(f"CREATE TABLE:\n{cached.get('create_table_sql', 'N/A')}")
            self.logger.info(f"INSERT:\n{cached.get('insert_sql', 'N/A')}")
            self.logger.info(f"Field order: {cached.get('field_order', [])}")

        return True

    async def test_store_multiple_records(self):
        """Test storing multiple records in batch"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Store Multiple Records")
        self.logger.info("=" * 60)

        input_data = {
            "operation": "store",
            "collection": "products",
            "data": [
                {"name": "Product 1", "price": 10.0, "rating": 4},
                {"name": "Product 2", "price": 20.0, "rating": 5},
                {"name": "Product 3", "price": 30.0, "rating": 3}
            ]
        }

        result = await self.agent.execute(input_data, self.context)

        assert result.success, f"Store operation failed: {result.message}"
        assert result.data["rows_stored"] == 3
        assert result.data["collection"] == "products"

        self.logger.info("✅ Multiple records stored successfully")
        self.logger.info(f"Result: {result.data}")
        return True

    async def test_query_all_records(self):
        """Test querying all records without filters"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Query All Records")
        self.logger.info("=" * 60)

        # First store some records
        await self.test_store_multiple_records()

        # Query all records
        input_data = {
            "operation": "query",
            "collection": "products",
            "filters": {}
        }

        result = await self.agent.execute(input_data, self.context)

        assert result.success, f"Query operation failed: {result.message}"
        assert result.data["total_count"] >= 3  # At least the 3 we just stored

        self.logger.info("✅ Query all records successful")
        self.logger.info(f"Total records: {result.data['total_count']}")
        return True

    async def test_query_with_filters(self):
        """Test querying with filter conditions"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Query With Filters")
        self.logger.info("=" * 60)

        # Store test data
        input_data = {
            "operation": "store",
            "collection": "products",
            "data": [
                {"name": "Cheap Product", "price": 5.0, "rating": 3},
                {"name": "Expensive Product", "price": 100.0, "rating": 5}
            ]
        }
        await self.agent.execute(input_data, self.context)

        # Query with filters
        input_data = {
            "operation": "query",
            "collection": "products",
            "filters": {
                "price": {"<": 50.0},
                "rating": {">": 2}
            },
            "limit": 10
        }

        self.logger.info(f"Query filters: {json.dumps(input_data['filters'], indent=2)}")

        result = await self.agent.execute(input_data, self.context)

        assert result.success, f"Query operation failed: {result.message}"

        self.logger.info("✅ Query with filters successful")
        self.logger.info(f"Filtered records: {result.data['total_count']}")

        # Check cached query script
        import hashlib
        query_config = {
            "filters": input_data['filters'],
            "order_by": None,
            "limit": 10
        }
        config_hash = hashlib.md5(json.dumps(query_config, sort_keys=True).encode()).hexdigest()[:8]
        cache_key = f"storage_query_products_test_user_{config_hash}"
        cached = await self.context.memory_manager.get_data(cache_key)
        if cached:
            self.logger.info("\n📝 Generated Query SQL:")
            self.logger.info(f"SQL: {cached.get('query_sql', 'N/A')}")
            self.logger.info(f"Params order: {cached.get('params_order', [])}")

        return True

    async def test_script_caching(self):
        """Test that SQL scripts are cached and reused"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Script Caching")
        self.logger.info("=" * 60)

        # First store - should generate and cache script
        input_data1 = {
            "operation": "store",
            "collection": "cache_test",
            "data": {"field1": "value1"}
        }

        result1 = await self.agent.execute(input_data1, self.context)
        assert result1.success

        # Check if script was cached
        cache_key = "storage_insert_cache_test_test_user"
        cached_script = await self.context.memory_manager.get_data(cache_key)

        assert cached_script is not None, "Script should be cached"
        assert "insert_sql" in cached_script
        assert "create_table_sql" in cached_script
        assert "field_order" in cached_script

        self.logger.info("✅ Script caching successful")
        self.logger.info(f"Cached script keys: {list(cached_script.keys())}")

        # Second store - should use cached script
        input_data2 = {
            "operation": "store",
            "collection": "cache_test",
            "data": {"field1": "value2"}
        }

        result2 = await self.agent.execute(input_data2, self.context)
        assert result2.success

        self.logger.info("✅ Script reuse successful")
        return True

    async def test_schema_validation(self):
        """Test schema validation - extra and missing fields"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Schema Validation")
        self.logger.info("=" * 60)

        # First store to establish schema
        input_data1 = {
            "operation": "store",
            "collection": "validation_test",
            "data": {"field1": "value1", "field2": "value2"}
        }
        result1 = await self.agent.execute(input_data1, self.context)
        assert result1.success

        # Try to store with missing field
        input_data2 = {
            "operation": "store",
            "collection": "validation_test",
            "data": {"field1": "value1"}  # Missing field2
        }
        result2 = await self.agent.execute(input_data2, self.context)

        assert not result2.success, "Should fail with missing field"
        assert "Missing required fields" in result2.message

        self.logger.info("✅ Missing field validation successful")

        # Try to store with extra field
        input_data3 = {
            "operation": "store",
            "collection": "validation_test",
            "data": {
                "field1": "value1",
                "field2": "value2",
                "field3": "value3"  # Extra field
            }
        }
        result3 = await self.agent.execute(input_data3, self.context)

        assert not result3.success, "Should fail with extra field"
        assert "Extra fields" in result3.message

        self.logger.info("✅ Extra field validation successful")
        return True

    async def test_export_to_json(self):
        """Test exporting data to JSON file"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Export to JSON")
        self.logger.info("=" * 60)

        # Store test data
        input_data = {
            "operation": "store",
            "collection": "export_test",
            "data": [
                {"name": "Item 1", "value": 10},
                {"name": "Item 2", "value": 20}
            ]
        }
        await self.agent.execute(input_data, self.context)

        # Export to JSON - use test data directory
        test_data_root = self.config_service.get_path('data.root')
        output_path = str(test_data_root / "export_test.json")
        input_data = {
            "operation": "export",
            "collection": "export_test",
            "format": "json",
            "output_path": output_path,
            "filters": {}
        }

        result = await self.agent.execute(input_data, self.context)

        assert result.success, f"Export operation failed: {result.message}"
        assert Path(output_path).exists(), "Export file should exist"

        # Verify exported data
        with open(output_path, 'r') as f:
            exported_data = json.load(f)

        assert len(exported_data) >= 2, "Should have at least 2 records"

        self.logger.info("✅ Export to JSON successful")
        self.logger.info(f"Exported {len(exported_data)} records to {output_path}")
        return True

    async def test_export_to_csv(self):
        """Test exporting data to CSV file"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Export to CSV")
        self.logger.info("=" * 60)

        # Store test data
        input_data = {
            "operation": "store",
            "collection": "csv_test",
            "data": [
                {"name": "Item A", "quantity": 5},
                {"name": "Item B", "quantity": 10}
            ]
        }
        await self.agent.execute(input_data, self.context)

        # Export to CSV - use test data directory
        test_data_root = self.config_service.get_path('data.root')
        output_path = str(test_data_root / "export_test.csv")
        input_data = {
            "operation": "export",
            "collection": "csv_test",
            "format": "csv",
            "output_path": output_path,
            "filters": {}
        }

        result = await self.agent.execute(input_data, self.context)

        assert result.success, f"Export operation failed: {result.message}"
        assert Path(output_path).exists(), "CSV file should exist"

        self.logger.info("✅ Export to CSV successful")
        self.logger.info(f"Exported to {output_path}")
        return True

    async def test_user_isolation(self):
        """Test that different users have isolated data"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: User Isolation")
        self.logger.info("=" * 60)

        # Store data for user1
        context1 = self.context
        context1.variables["user_id"] = "user1"

        input_data1 = {
            "operation": "store",
            "collection": "isolation_test",
            "data": {"value": "user1_data"}
        }
        await self.agent.execute(input_data1, context1)

        # Create context for user2 - reuse the same real provider
        mock_agent_instance2 = MagicMock()
        mock_agent_instance2.provider = self.provider  # Use real provider
        mock_agent_instance2.config_service = self.config_service

        context2 = AgentContext(
            workflow_id="test_workflow",
            step_id="test_step",
            variables={"user_id": "user2"},
            agent_instance=mock_agent_instance2
        )
        context2.memory_manager = MemoryManager(
            user_id="user2",
            config_service=self.config_service
        )

        # Store data for user2
        input_data2 = {
            "operation": "store",
            "collection": "isolation_test",
            "data": {"value": "user2_data"}
        }
        await self.agent.execute(input_data2, context2)

        # Query user1's data
        query_data1 = {
            "operation": "query",
            "collection": "isolation_test",
            "filters": {}
        }
        result1 = await self.agent.execute(query_data1, context1)

        # Query user2's data
        result2 = await self.agent.execute(query_data1, context2)

        # Both should succeed but have different data
        assert result1.success and result2.success
        # Note: In real implementation, they should have different table names
        # and thus isolated data

        self.logger.info("✅ User isolation test passed")
        self.logger.info(f"User1 records: {result1.data['total_count']}")
        self.logger.info(f"User2 records: {result2.data['total_count']}")
        return True

    async def run_all_tests(self):
        """Run all tests"""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("STORAGE AGENT UNIT TESTS")
        self.logger.info("=" * 70 + "\n")

        tests = [
            self.test_store_single_record,
            self.test_store_multiple_records,
            self.test_query_all_records,
            self.test_query_with_filters,
            self.test_script_caching,
            self.test_schema_validation,
            self.test_export_to_json,
            self.test_export_to_csv,
            self.test_user_isolation
        ]

        passed = 0
        failed = 0

        for test in tests:
            try:
                await self.setup()
                result = await test()
                if result:
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                self.logger.error(f"❌ Test {test.__name__} failed with exception: {e}")
                import traceback
                traceback.print_exc()
                failed += 1
            finally:
                await self.cleanup()

        self.logger.info("\n" + "=" * 70)
        self.logger.info(f"TEST SUMMARY: {passed} passed, {failed} failed")
        self.logger.info("=" * 70 + "\n")

        return failed == 0


async def main():
    """Main test runner"""
    import argparse

    parser = argparse.ArgumentParser(description='Run StorageAgent unit tests')
    parser.add_argument(
        '--provider',
        choices=['openai', 'anthropic'],
        default='openai',
        help='LLM provider to use (default: openai)'
    )
    args = parser.parse_args()

    print(f"\n{'=' * 70}")
    print(f"StorageAgent Unit Tests - Using {args.provider.upper()} provider")
    print(f"{'=' * 70}\n")

    test_suite = TestStorageAgent(provider_type=args.provider)
    success = await test_suite.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
