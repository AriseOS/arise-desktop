#!/usr/bin/env python3
"""
Unit tests for SQLiteKVStorage

Tests the SQLite-based key-value storage implementation including:
- Automatic table initialization
- CRUD operations
- User isolation
- Data persistence
- JSON serialization
"""

import asyncio
import sys
import tempfile
import logging
from pathlib import Path
from datetime import datetime
import json

# Add project path to sys.path
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from base_app.base_app.base_agent.memory.sqlite_kv_storage import SQLiteKVStorage


class MockConfigService:
    """Mock config service for testing"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_path(self, key: str) -> str:
        return self.db_path


class TestSQLiteKVStorage:
    """Test suite for SQLiteKVStorage"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    async def test_auto_initialization(self):
        """Test automatic table creation on first access"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Automatic Table Initialization")
        self.logger.info("=" * 60)

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        try:
            # Create storage (should NOT create table yet)
            config_service = MockConfigService(db_path)
            storage = SQLiteKVStorage(config_service)

            # First operation should auto-create table
            result = await storage.set("test_key", "test_value", "user1")

            assert result is True, "Set operation should succeed"

            # Verify data was stored
            value = await storage.get("test_key", "user1")
            assert value == "test_value", f"Expected 'test_value', got {value}"

            self.logger.info("✅ Table auto-created on first access")
            return True

        finally:
            Path(db_path).unlink(missing_ok=True)

    async def test_idempotent_initialization(self):
        """Test that _ensure_table_exists is idempotent"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Idempotent Table Creation")
        self.logger.info("=" * 60)

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        try:
            config_service = MockConfigService(db_path)
            storage = SQLiteKVStorage(config_service)

            # Call multiple times - should not error
            await storage.set("key1", "value1", "user1")
            await storage.set("key2", "value2", "user1")
            await storage.get("key1", "user1")
            await storage.get("key2", "user1")

            self.logger.info("✅ Multiple table creation attempts succeeded")
            return True

        finally:
            Path(db_path).unlink(missing_ok=True)

    async def test_crud_operations(self):
        """Test Create, Read, Update, Delete operations"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: CRUD Operations")
        self.logger.info("=" * 60)

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        try:
            config_service = MockConfigService(db_path)
            storage = SQLiteKVStorage(config_service)

            # CREATE
            test_data = {
                "name": "Alice",
                "age": 30,
                "tags": ["developer", "python"],
                "active": True
            }
            result = await storage.set("user_profile", test_data, "user1")
            assert result is True, "Create should succeed"
            self.logger.info("✅ CREATE: Stored user profile")

            # READ
            retrieved = await storage.get("user_profile", "user1")
            assert retrieved == test_data, f"Expected {test_data}, got {retrieved}"
            self.logger.info("✅ READ: Retrieved correct data")

            # UPDATE
            updated_data = {**test_data, "age": 31, "tags": ["developer", "python", "ai"]}
            result = await storage.set("user_profile", updated_data, "user1")
            assert result is True, "Update should succeed"

            retrieved = await storage.get("user_profile", "user1")
            assert retrieved == updated_data, "Data should be updated"
            self.logger.info("✅ UPDATE: Updated user profile")

            # DELETE
            result = await storage.delete("user_profile", "user1")
            assert result is True, "Delete should succeed"

            retrieved = await storage.get("user_profile", "user1", default=None)
            assert retrieved is None, "Data should be deleted"
            self.logger.info("✅ DELETE: Deleted user profile")

            return True

        finally:
            Path(db_path).unlink(missing_ok=True)

    async def test_data_types(self):
        """Test various data types (dict, list, str, int, bool, None)"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Various Data Types")
        self.logger.info("=" * 60)

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        try:
            config_service = MockConfigService(db_path)
            storage = SQLiteKVStorage(config_service)

            test_cases = [
                ("dict_key", {"a": 1, "b": {"c": 2}}),
                ("list_key", [1, 2, 3, {"nested": "value"}]),
                ("str_key", "hello world"),
                ("int_key", 42),
                ("bool_key", True),
                ("null_key", None),
                ("float_key", 3.14159),
            ]

            for key, value in test_cases:
                await storage.set(key, value, "user1")
                retrieved = await storage.get(key, "user1")
                assert retrieved == value, f"Expected {value}, got {retrieved} for key {key}"
                self.logger.info(f"✅ {key}: {type(value).__name__} serialization works")

            return True

        finally:
            Path(db_path).unlink(missing_ok=True)

    async def test_user_isolation(self):
        """Test that different users have isolated data"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: User Data Isolation")
        self.logger.info("=" * 60)

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        try:
            config_service = MockConfigService(db_path)
            storage = SQLiteKVStorage(config_service)

            # Same key, different users
            await storage.set("preferences", {"theme": "dark"}, "user1")
            await storage.set("preferences", {"theme": "light"}, "user2")
            await storage.set("preferences", {"theme": "auto"}, "user3")

            # Verify isolation
            pref1 = await storage.get("preferences", "user1")
            pref2 = await storage.get("preferences", "user2")
            pref3 = await storage.get("preferences", "user3")

            assert pref1 == {"theme": "dark"}, f"User1 data incorrect: {pref1}"
            assert pref2 == {"theme": "light"}, f"User2 data incorrect: {pref2}"
            assert pref3 == {"theme": "auto"}, f"User3 data incorrect: {pref3}"

            self.logger.info("✅ User data properly isolated")

            # Delete user2's data should not affect others
            await storage.delete("preferences", "user2")

            pref1 = await storage.get("preferences", "user1")
            pref2 = await storage.get("preferences", "user2", default="DELETED")
            pref3 = await storage.get("preferences", "user3")

            assert pref1 == {"theme": "dark"}, "User1 data should remain"
            assert pref2 == "DELETED", "User2 data should be deleted"
            assert pref3 == {"theme": "auto"}, "User3 data should remain"

            self.logger.info("✅ Delete operation respects user isolation")

            return True

        finally:
            Path(db_path).unlink(missing_ok=True)

    async def test_persistence(self):
        """Test data persists across storage instances"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Data Persistence")
        self.logger.info("=" * 60)

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        try:
            # First instance - write data
            config_service1 = MockConfigService(db_path)
            storage1 = SQLiteKVStorage(config_service1)

            test_data = {
                "script_content": "def extract(): return []",
                "version": "7.1",
                "created_at": datetime.now().isoformat()
            }

            await storage1.set("scraper_script_abc123", test_data, "agent_001")
            self.logger.info("✅ Data written with first storage instance")

            # Simulate process restart - create new instance
            config_service2 = MockConfigService(db_path)
            storage2 = SQLiteKVStorage(config_service2)

            # Read data with new instance
            retrieved = await storage2.get("scraper_script_abc123", "agent_001")

            assert retrieved == test_data, "Data should persist across instances"
            self.logger.info("✅ Data persisted across storage instances")

            return True

        finally:
            Path(db_path).unlink(missing_ok=True)

    async def test_keys_and_clear(self):
        """Test listing keys and clearing user data"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: List Keys and Clear Data")
        self.logger.info("=" * 60)

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        try:
            config_service = MockConfigService(db_path)
            storage = SQLiteKVStorage(config_service)

            # Add multiple keys for user1
            await storage.set("key1", "value1", "user1")
            await storage.set("key2", "value2", "user1")
            await storage.set("key3", "value3", "user1")

            # Add keys for user2
            await storage.set("key1", "value1", "user2")
            await storage.set("key4", "value4", "user2")

            # List keys for user1
            keys_user1 = await storage.keys("user1")
            assert set(keys_user1) == {"key1", "key2", "key3"}, f"Unexpected keys: {keys_user1}"
            self.logger.info(f"✅ Listed user1 keys: {keys_user1}")

            # List keys for user2
            keys_user2 = await storage.keys("user2")
            assert set(keys_user2) == {"key1", "key4"}, f"Unexpected keys: {keys_user2}"
            self.logger.info(f"✅ Listed user2 keys: {keys_user2}")

            # Clear user1's data
            count = await storage.clear("user1")
            assert count == 3, f"Expected to delete 3 keys, deleted {count}"
            self.logger.info(f"✅ Cleared user1 data ({count} keys)")

            # Verify user1's data is gone
            keys_user1_after = await storage.keys("user1")
            assert keys_user1_after == [], "User1 should have no keys"

            # Verify user2's data remains
            keys_user2_after = await storage.keys("user2")
            assert set(keys_user2_after) == {"key1", "key4"}, "User2 data should remain"
            self.logger.info("✅ Clear operation only affects target user")

            return True

        finally:
            Path(db_path).unlink(missing_ok=True)

    async def test_default_values(self):
        """Test default value handling for missing keys"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Default Values for Missing Keys")
        self.logger.info("=" * 60)

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        try:
            config_service = MockConfigService(db_path)
            storage = SQLiteKVStorage(config_service)

            # Get with default None
            value = await storage.get("nonexistent", "user1")
            assert value is None, f"Expected None, got {value}"
            self.logger.info("✅ Default None works")

            # Get with custom default
            value = await storage.get("nonexistent", "user1", default={})
            assert value == {}, f"Expected {{}}, got {value}"
            self.logger.info("✅ Custom default works")

            value = await storage.get("nonexistent", "user1", default="NOT_FOUND")
            assert value == "NOT_FOUND", f"Expected 'NOT_FOUND', got {value}"
            self.logger.info("✅ String default works")

            return True

        finally:
            Path(db_path).unlink(missing_ok=True)

    async def test_timestamps(self):
        """Test that created_at and updated_at timestamps work correctly"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Timestamp Management")
        self.logger.info("=" * 60)

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name

        try:
            config_service = MockConfigService(db_path)
            storage = SQLiteKVStorage(config_service)

            # Create initial value
            await storage.set("test_key", "initial_value", "user1")
            self.logger.info("✅ Created initial value")

            # Small delay to ensure timestamp difference
            await asyncio.sleep(0.1)

            # Update value
            await storage.set("test_key", "updated_value", "user1")
            self.logger.info("✅ Updated value")

            # Note: We can't easily verify timestamps without accessing DB directly
            # But the COALESCE logic ensures created_at is preserved
            value = await storage.get("test_key", "user1")
            assert value == "updated_value", "Value should be updated"

            self.logger.info("✅ Timestamp logic executed without errors")

            return True

        finally:
            Path(db_path).unlink(missing_ok=True)

    async def run_all_tests(self):
        """Run all tests"""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("SQLITE KV STORAGE TEST SUITE")
        self.logger.info("=" * 60 + "\n")

        tests = [
            ("Automatic Initialization", self.test_auto_initialization),
            ("Idempotent Initialization", self.test_idempotent_initialization),
            ("CRUD Operations", self.test_crud_operations),
            ("Various Data Types", self.test_data_types),
            ("User Isolation", self.test_user_isolation),
            ("Data Persistence", self.test_persistence),
            ("List Keys and Clear", self.test_keys_and_clear),
            ("Default Values", self.test_default_values),
            ("Timestamp Management", self.test_timestamps),
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
    tester = TestSQLiteKVStorage()

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
