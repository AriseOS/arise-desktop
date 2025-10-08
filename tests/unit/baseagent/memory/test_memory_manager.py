#!/usr/bin/env python3
"""
Integration tests for MemoryManager

Tests the integration between Variables and KV Storage layers:
- Layer 1 (Variables) operations
- Layer 2 (KV Storage) operations
- Unified API
- User ID management
- Memory statistics
"""

import asyncio
import sys
import tempfile
import logging
from pathlib import Path
from datetime import datetime

# Add project path to sys.path
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from base_app.base_app.base_agent.memory.memory_manager import MemoryManager


class MockConfigService:
    """Mock config service for testing"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_path(self, key: str) -> str:
        return self.db_path


class TestMemoryManager:
    """Test suite for MemoryManager integration"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    async def test_initialization(self):
        """Test MemoryManager initialization"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: MemoryManager Initialization")
        self.logger.info("=" * 60)

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        try:
            # Initialize with config_service
            config_service = MockConfigService(db_path)
            manager = MemoryManager(user_id="test_user", config_service=config_service)

            assert manager.user_id == "test_user", "User ID should be set"
            assert manager.kv_storage is not None, "KV storage should be initialized"
            self.logger.info("✅ MemoryManager initialized successfully")

            # Initialize without config_service
            manager_no_kv = MemoryManager(user_id="test_user2")
            assert manager_no_kv.kv_storage is None, "KV storage should be None without config_service"
            self.logger.info("✅ MemoryManager without KV storage works")

            return True

        finally:
            Path(db_path).unlink(missing_ok=True)

    async def test_variables_operations(self):
        """Test Layer 1 (Variables) operations"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Variables Layer Operations")
        self.logger.info("=" * 60)

        manager = MemoryManager(user_id="test_user")

        # Set variable
        await manager.store_memory("name", "Alice")
        await manager.store_memory("age", 30)
        await manager.store_memory("tags", ["python", "ai"])

        # Get variable
        result = await manager.get_memory("name")
        assert result == "Alice", "Should retrieve string variable"
        result = await manager.get_memory("age")
        assert result == 30, "Should retrieve int variable"
        result = await manager.get_memory("tags")
        assert result == ["python", "ai"], "Should retrieve list variable"
        self.logger.info("✅ Set/Get variables works")

        # Get with default
        result = await manager.get_memory("nonexistent", default="DEFAULT")
        assert result == "DEFAULT", "Should return default for missing variable"
        self.logger.info("✅ Default value works")

        # Delete variable
        success = await manager.delete_memory("name")
        assert success is True, "Delete should return True"
        result = await manager.get_memory("name", default=None)
        assert result is None, "Should return None after deletion"
        self.logger.info("✅ Delete variable works")

        # List variables
        variables = manager.list_keys()
        assert "age" in variables, "Should list existing variables"
        assert "name" not in variables, "Should not list deleted variables"
        self.logger.info(f"✅ List variables works: {variables}")

        # Clear variables
        await manager.clear_memory()
        variables = manager.list_keys()
        assert len(variables) == 0, "Should clear all variables"
        self.logger.info("✅ Clear variables works")

        return True

    async def test_kv_storage_operations(self):
        """Test Layer 2 (KV Storage) operations"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: KV Storage Layer Operations")
        self.logger.info("=" * 60)

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        try:
            config_service = MockConfigService(db_path)
            manager = MemoryManager(user_id="test_user", config_service=config_service)

            # Set data
            test_data = {
                "script": "def extract(): return []",
                "version": "1.0"
            }
            result = await manager.set_data("scraper_script", test_data)
            assert result is True, "Set data should succeed"
            self.logger.info("✅ Set data works")

            # Get data
            retrieved = await manager.get_data("scraper_script")
            assert retrieved == test_data, f"Expected {test_data}, got {retrieved}"
            self.logger.info("✅ Get data works")

            # Get with default
            result = await manager.get_data("nonexistent", default={})
            assert result == {}, "Should return default for missing key"
            self.logger.info("✅ Default value works")

            # Delete data
            result = await manager.delete_data("scraper_script")
            assert result is True, "Delete should succeed"

            retrieved = await manager.get_data("scraper_script", default=None)
            assert retrieved is None, "Data should be deleted"
            self.logger.info("✅ Delete data works")

            # List keys
            await manager.set_data("key1", "value1")
            await manager.set_data("key2", "value2")

            keys = await manager.list_data_keys()
            assert "key1" in keys and "key2" in keys, "Should list stored keys"
            self.logger.info(f"✅ List keys works: {keys}")

            # Clear data
            count = await manager.clear_all_data()
            assert count == 2, f"Expected to delete 2 keys, deleted {count}"

            keys = await manager.list_data_keys()
            assert len(keys) == 0, "Should clear all data"
            self.logger.info("✅ Clear data works")

            return True

        finally:
            Path(db_path).unlink(missing_ok=True)

    async def test_user_isolation(self):
        """Test user isolation across layers"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: User Isolation")
        self.logger.info("=" * 60)

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        try:
            config_service = MockConfigService(db_path)

            # Create managers for different users
            manager1 = MemoryManager(user_id="user1", config_service=config_service)
            manager2 = MemoryManager(user_id="user2", config_service=config_service)

            # Set data for both users
            await manager1.set_data("preferences", {"theme": "dark"})
            await manager2.set_data("preferences", {"theme": "light"})

            # Verify isolation
            pref1 = await manager1.get_data("preferences")
            pref2 = await manager2.get_data("preferences")

            assert pref1 == {"theme": "dark"}, f"User1 data incorrect: {pref1}"
            assert pref2 == {"theme": "light"}, f"User2 data incorrect: {pref2}"
            self.logger.info("✅ User data properly isolated")

            # Clear user1 data
            count = await manager1.clear_all_data()
            assert count == 1, "Should delete user1's data"

            # Verify user2 data remains
            pref2 = await manager2.get_data("preferences")
            assert pref2 == {"theme": "light"}, "User2 data should remain"
            self.logger.info("✅ Clear operation respects user isolation")

            return True

        finally:
            Path(db_path).unlink(missing_ok=True)

    async def test_memory_statistics(self):
        """Test memory statistics reporting"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Memory Statistics")
        self.logger.info("=" * 60)

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        try:
            config_service = MockConfigService(db_path)
            manager = MemoryManager(user_id="test_user", config_service=config_service)

            # Add variables
            await manager.store_memory("var1", "value1")
            await manager.store_memory("var2", "value2")

            # Add KV data
            await manager.set_data("key1", "value1")
            await manager.set_data("key2", "value2")
            await manager.set_data("key3", "value3")

            # Get statistics
            stats = manager.get_memory_stats()

            assert stats["variables_count"] == 2, f"Expected 2 variables, got {stats['variables_count']}"
            assert stats["kv_storage_enabled"] is True, "KV storage should be enabled"

            self.logger.info(f"✅ Memory statistics: {stats}")

            return True

        finally:
            Path(db_path).unlink(missing_ok=True)

    async def test_without_kv_storage(self):
        """Test MemoryManager gracefully handles missing KV storage"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Operation Without KV Storage")
        self.logger.info("=" * 60)

        # Create manager without config_service
        manager = MemoryManager(user_id="test_user")

        # Variables should work
        await manager.store_memory("test", "value")
        result = await manager.get_memory("test")
        assert result == "value", "Variables should work without KV storage"
        self.logger.info("✅ Variables work without KV storage")

        # KV operations should return None/False gracefully
        result = await manager.get_data("key")
        assert result is None, "Get data should return None without KV storage"

        result = await manager.set_data("key", "value")
        assert result is False, "Set data should return False without KV storage"

        keys = await manager.list_data_keys()
        assert keys == [], "List keys should return empty list without KV storage"

        stats = manager.get_memory_stats()
        assert stats["kv_storage_enabled"] is False, "KV storage should be disabled"
        assert stats["variables_count"] >= 0, "Variables count should still work"

        self.logger.info("✅ Gracefully handles missing KV storage")

        return True

    async def test_complex_data_types(self):
        """Test storing complex nested data structures"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Complex Data Types")
        self.logger.info("=" * 60)

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        try:
            config_service = MockConfigService(db_path)
            manager = MemoryManager(user_id="test_user", config_service=config_service)

            # Complex nested structure
            complex_data = {
                "metadata": {
                    "created_at": datetime.now().isoformat(),
                    "version": "2.0",
                    "author": "test_user"
                },
                "content": {
                    "script": "def extract(): return []",
                    "dependencies": ["browser", "playwright"],
                    "config": {
                        "timeout": 30,
                        "headless": True,
                        "retry": 3
                    }
                },
                "results": [
                    {"url": "https://example.com", "status": "success"},
                    {"url": "https://example2.com", "status": "failed"}
                ]
            }

            # Store and retrieve
            await manager.set_data("complex_script", complex_data)
            retrieved = await manager.get_data("complex_script")

            assert retrieved == complex_data, "Complex data should be preserved"
            assert retrieved["metadata"]["version"] == "2.0", "Nested access should work"
            assert len(retrieved["results"]) == 2, "Nested lists should be preserved"

            self.logger.info("✅ Complex nested data structures preserved")

            return True

        finally:
            Path(db_path).unlink(missing_ok=True)

    async def test_variable_and_storage_interaction(self):
        """Test that Variables and KV Storage are independent"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Variables and Storage Independence")
        self.logger.info("=" * 60)

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        try:
            config_service = MockConfigService(db_path)
            manager = MemoryManager(user_id="test_user", config_service=config_service)

            # Same key in both layers
            await manager.store_memory("shared_key", "variable_value")
            await manager.set_data("shared_key", "storage_value")

            # Verify independence
            var_value = await manager.get_memory("shared_key")
            storage_value = await manager.get_data("shared_key")

            assert var_value == "variable_value", "Variable should have its own value"
            assert storage_value == "storage_value", "Storage should have its own value"
            self.logger.info("✅ Variables and Storage are independent")

            # Clear variables should not affect storage
            await manager.clear_memory()
            storage_value = await manager.get_data("shared_key")
            assert storage_value == "storage_value", "Storage should remain after clearing variables"
            self.logger.info("✅ Clearing variables doesn't affect storage")

            # Clear storage should not affect variables (re-add variable)
            await manager.store_memory("shared_key", "variable_value")
            await manager.clear_all_data()
            var_value = await manager.get_memory("shared_key")
            assert var_value == "variable_value", "Variable should remain after clearing storage"
            self.logger.info("✅ Clearing storage doesn't affect variables")

            return True

        finally:
            Path(db_path).unlink(missing_ok=True)

    async def run_all_tests(self):
        """Run all tests"""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("MEMORY MANAGER INTEGRATION TEST SUITE")
        self.logger.info("=" * 60 + "\n")

        tests = [
            ("MemoryManager Initialization", self.test_initialization),
            ("Variables Layer Operations", self.test_variables_operations),
            ("KV Storage Layer Operations", self.test_kv_storage_operations),
            ("User Isolation", self.test_user_isolation),
            ("Memory Statistics", self.test_memory_statistics),
            ("Operation Without KV Storage", self.test_without_kv_storage),
            ("Complex Data Types", self.test_complex_data_types),
            ("Variables and Storage Independence", self.test_variable_and_storage_interaction),
        ]

        results = []
        for test_name, test_func in tests:
            try:
                self.logger.info(f"\nRunning: {test_name}")
                result = await test_func()
                results.append((test_name, result))
            except Exception as e:
                self.logger.error(f"❌ Test '{test_name}' failed with exception: {e}")
                import traceback
                traceback.print_exc()
                results.append((test_name, False))

        # Summary
        self.logger.info("\n" + "=" * 60)
        self.logger.info("TEST SUMMARY")
        self.logger.info("=" * 60)

        passed = sum(1 for _, result in results if result)
        total = len(results)

        for test_name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            self.logger.info(f"{status}: {test_name}")

        self.logger.info("=" * 60)
        self.logger.info(f"Results: {passed}/{total} tests passed")
        self.logger.info("=" * 60)

        return all(result for _, result in results)


async def main():
    """Main function"""
    tester = TestMemoryManager()

    try:
        success = await tester.run_all_tests()
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
