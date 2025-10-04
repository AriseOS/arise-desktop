#!/usr/bin/env python3
"""
Interactive Storage Database Inspector

Inspect StorageAgent databases interactively:
- View all collections and tables
- View table schemas
- Query data from collections
- View cached SQL scripts
- Export data

Usage:
    python inspect_storage.py
    python inspect_storage.py --config /path/to/test_config.yaml
"""

import asyncio
import sys
import json
import aiosqlite
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# Add project path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "base_app"))

from base_app.server.core.config_service import ConfigService


class StorageInspector:
    """Interactive storage database inspector"""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize inspector with config"""
        if not config_path:
            # Default to test config
            config_path = str(project_root / "tests" / "test_config.yaml")

        self.config_service = ConfigService(config_path=config_path)
        self.storage_db = str(self.config_service.get_path('data.databases.storage'))
        self.kv_db = str(self.config_service.get_path('data.databases.kv'))

        print(f"\n{'=' * 70}")
        print("Storage Database Inspector")
        print(f"{'=' * 70}")
        print(f"Storage DB: {self.storage_db}")
        print(f"KV DB: {self.kv_db}")
        print(f"{'=' * 70}\n")

    async def list_tables(self) -> List[str]:
        """List all tables in storage database and return table names"""
        print("\n📊 Collections (Tables):")
        print("-" * 70)

        if not Path(self.storage_db).exists():
            print("❌ Storage database does not exist")
            return []

        async with aiosqlite.connect(self.storage_db) as db:
            cursor = await db.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)
            tables = await cursor.fetchall()

            if not tables:
                print("  (No collections found)")
                return []

            table_names = []
            for i, (table_name,) in enumerate(tables, 1):
                table_names.append(table_name)

                # Parse collection and user from table name
                # Format: {collection}_{user_id}
                parts = table_name.rsplit('_', 1)
                if len(parts) == 2:
                    collection, user_id = parts
                    display_name = f"{collection} (user: {user_id})"
                else:
                    display_name = table_name

                # Get row count
                cursor = await db.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = (await cursor.fetchone())[0]

                print(f"  [{i}] {table_name}")
                print(f"      {display_name} - {count} rows")

            return table_names

    async def show_schema(self, table_name: str):
        """Show table schema"""
        print(f"\n📋 Schema for: {table_name}")
        print("-" * 70)

        async with aiosqlite.connect(self.storage_db) as db:
            cursor = await db.execute(f"PRAGMA table_info({table_name})")
            columns = await cursor.fetchall()

            if not columns:
                print(f"❌ Table '{table_name}' not found")
                return

            print("\nColumns:")
            for col_id, name, type_, notnull, default, pk in columns:
                pk_marker = " [PK]" if pk else ""
                notnull_marker = " [NOT NULL]" if notnull else ""
                default_marker = f" [DEFAULT: {default}]" if default else ""
                print(f"  - {name}: {type_}{pk_marker}{notnull_marker}{default_marker}")

    async def query_data(self, table_name: str, limit: int = 10):
        """Query data from table"""
        print(f"\n📄 Data from: {table_name} (limit: {limit})")
        print("-" * 70)

        async with aiosqlite.connect(self.storage_db) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT * FROM {table_name} ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            rows = await cursor.fetchall()

            if not rows:
                print("  (No data)")
                return

            # Convert to dicts
            data = [dict(row) for row in rows]

            # Pretty print
            for i, record in enumerate(data, 1):
                print(f"\n  Record {i}:")
                for key, value in record.items():
                    # Truncate long values
                    if isinstance(value, str) and len(value) > 100:
                        value = value[:100] + "..."
                    print(f"    {key}: {value}")

    async def list_cached_scripts(self, pattern: str = "") -> List[str]:
        """List all cached scripts and return script keys"""
        print(f"\n🔧 Cached Scripts{f' (pattern: {pattern})' if pattern else ''}")
        print("-" * 70)

        if not Path(self.kv_db).exists():
            print("❌ KV database does not exist")
            return []

        async with aiosqlite.connect(self.kv_db) as db:
            if pattern:
                cursor = await db.execute("""
                    SELECT key, user_id, created_at, updated_at
                    FROM kv_storage
                    WHERE key LIKE ?
                    ORDER BY updated_at DESC
                """, (f"%{pattern}%",))
            else:
                cursor = await db.execute("""
                    SELECT key, user_id, created_at, updated_at
                    FROM kv_storage
                    ORDER BY updated_at DESC
                """)
            scripts = await cursor.fetchall()

            if not scripts:
                print(f"  (No scripts{f' matching {pattern}' if pattern else ''})")
                return []

            script_keys = []
            for i, (key, user_id, created_at, updated_at) in enumerate(scripts, 1):
                script_keys.append(key)
                script_type = self._get_script_type(key)
                print(f"  [{i}] {key}")
                print(f"      Type: {script_type} | User: {user_id}")
                print(f"      Updated: {updated_at}")

            return script_keys

    async def show_script_detail(self, key: str):
        """Show detailed information for a specific script"""
        print(f"\n🔍 Script Detail: {key}")
        print("-" * 70)

        if not Path(self.kv_db).exists():
            print("❌ KV database does not exist")
            return

        async with aiosqlite.connect(self.kv_db) as db:
            cursor = await db.execute("""
                SELECT user_id, value, created_at, updated_at
                FROM kv_storage
                WHERE key = ?
            """, (key,))
            result = await cursor.fetchone()

            if not result:
                print(f"❌ Script not found: {key}")
                return

            user_id, value_json, created_at, updated_at = result
            print(f"  User: {user_id}")
            print(f"  Created: {created_at}")
            print(f"  Updated: {updated_at}")
            print(f"  Type: {self._get_script_type(key)}")

            try:
                value = json.loads(value_json)

                # Show content based on script type
                if "storage_" in key:
                    # StorageAgent scripts
                    if "insert" in key:
                        if "create_table_sql" in value:
                            print(f"\n  CREATE TABLE SQL:")
                            print(f"  {value['create_table_sql']}")
                        if "insert_sql" in value:
                            print(f"\n  INSERT SQL:")
                            print(f"  {value['insert_sql']}")
                        if "field_order" in value:
                            print(f"\n  Field Order: {value['field_order']}")
                    elif "query" in key:
                        if "query_sql" in value:
                            print(f"\n  QUERY SQL:")
                            print(f"  {value['query_sql']}")
                        if "params_order" in value:
                            print(f"\n  Params Order: {value['params_order']}")
                    elif "export" in key:
                        if "query_sql" in value:
                            print(f"\n  EXPORT SQL:")
                            print(f"  {value['query_sql']}")
                        if "format" in value:
                            print(f"\n  Format: {value['format']}")

                elif "scraper_script_" in key:
                    # ScraperAgent scripts
                    print(f"\n  Python Script:")
                    print(f"  {'-' * 60}")
                    print(value if isinstance(value, str) else json.dumps(value, indent=2))

                else:
                    # Unknown type, show raw JSON
                    print(f"\n  Value:")
                    print(json.dumps(value, indent=2, ensure_ascii=False))

            except json.JSONDecodeError:
                print(f"  ⚠️  Value is not valid JSON")
                print(f"  Raw value: {value_json[:200]}")

    async def delete_script(self, key: str) -> bool:
        """Delete a cached script by key"""
        print(f"\n🗑️  Deleting script: {key}")
        print("-" * 70)

        if not Path(self.kv_db).exists():
            print("❌ KV database does not exist")
            return False

        async with aiosqlite.connect(self.kv_db) as db:
            # Check if exists
            cursor = await db.execute("SELECT key FROM kv_storage WHERE key = ?", (key,))
            if not await cursor.fetchone():
                print(f"❌ Script not found: {key}")
                return False

            # Delete
            await db.execute("DELETE FROM kv_storage WHERE key = ?", (key,))
            await db.commit()
            print(f"✅ Deleted: {key}")
            return True

    async def drop_table(self, table_name: str) -> bool:
        """Drop a table (collection) from storage database"""
        print(f"\n🗑️  Dropping table: {table_name}")
        print("-" * 70)

        if not Path(self.storage_db).exists():
            print("❌ Storage database does not exist")
            return False

        async with aiosqlite.connect(self.storage_db) as db:
            # Check if table exists
            cursor = await db.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name = ?
            """, (table_name,))
            if not await cursor.fetchone():
                print(f"❌ Table not found: {table_name}")
                return False

            # Confirm
            confirm = input(f"⚠️  Are you sure you want to drop '{table_name}'? (yes/no): ").strip().lower()
            if confirm != 'yes':
                print("❌ Cancelled")
                return False

            # Drop table
            await db.execute(f"DROP TABLE {table_name}")
            await db.commit()
            print(f"✅ Dropped: {table_name}")
            return True

    def _get_script_type(self, key: str) -> str:
        """Get script type from key"""
        if "storage_insert" in key:
            return "StorageAgent INSERT"
        elif "storage_query" in key:
            return "StorageAgent QUERY"
        elif "storage_export" in key:
            return "StorageAgent EXPORT"
        elif "scraper_script_" in key:
            return "ScraperAgent Script"
        return "UNKNOWN"

    async def export_table(self, table_name: str, output_file: str):
        """Export table data to JSON file"""
        print(f"\n💾 Exporting: {table_name} → {output_file}")
        print("-" * 70)

        async with aiosqlite.connect(self.storage_db) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(f"SELECT * FROM {table_name}")
            rows = await cursor.fetchall()

            data = [dict(row) for row in rows]

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            print(f"✅ Exported {len(data)} records to {output_file}")

    async def interactive_menu(self):
        """Interactive menu"""
        table_list = []  # Cache table list
        script_list = []  # Cache script list

        while True:
            print("\n" + "=" * 70)
            print("Commands:")
            print("  1. List all collections (tables)")
            print("  2. Show table schema")
            print("  3. Query table data")
            print("  4. Drop table (collection)")
            print("  5. Export table to JSON")
            print("  6. List all cached scripts")
            print("  7. Show script detail")
            print("  8. Delete script")
            print("  9. Show statistics")
            print("  q. Quit")
            print("=" * 70)

            choice = input("\nEnter command: ").strip()

            if choice == '1':
                table_list = await self.list_tables()

            elif choice == '2':
                table = self._prompt_for_table(table_list)
                if table:
                    await self.show_schema(table)

            elif choice == '3':
                table = self._prompt_for_table(table_list)
                if table:
                    limit = input("Limit (default 10): ").strip()
                    limit = int(limit) if limit else 10
                    await self.query_data(table, limit)

            elif choice == '4':
                table = self._prompt_for_table(table_list)
                if table:
                    success = await self.drop_table(table)
                    if success:
                        table_list = []  # Clear cache

            elif choice == '5':
                table = self._prompt_for_table(table_list)
                if table:
                    output = input("Output file path: ").strip()
                    if output:
                        await self.export_table(table, output)

            elif choice == '6':
                pattern = input("Search pattern (press Enter for all): ").strip()
                script_list = await self.list_cached_scripts(pattern)

            elif choice == '7':
                script = self._prompt_for_script(script_list)
                if script:
                    await self.show_script_detail(script)

            elif choice == '8':
                script = self._prompt_for_script(script_list)
                if script:
                    success = await self.delete_script(script)
                    if success:
                        script_list = []  # Clear cache

            elif choice == '9':
                await self.show_statistics()

            elif choice.lower() == 'q':
                print("\nGoodbye!")
                break

            else:
                print("❌ Invalid command")

    def _prompt_for_table(self, table_list: List[str]) -> Optional[str]:
        """Prompt user to select a table by number or name"""
        if not table_list:
            print("⚠️  Please list tables first (command 1)")
            return None

        print("\nSelect table:")
        print("  - Enter table number (e.g., 1, 2, 3)")
        print("  - Or enter full table name")

        choice = input("Table: ").strip()

        # Try as number first
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(table_list):
                return table_list[idx]
            else:
                print(f"❌ Invalid number. Valid range: 1-{len(table_list)}")
                return None

        # Try as table name
        if choice in table_list:
            return choice

        # Try fuzzy match
        for table in table_list:
            if choice in table:
                print(f"✓ Matched: {table}")
                return table

        print(f"❌ Table not found: {choice}")
        return None

    def _prompt_for_script(self, script_list: List[str]) -> Optional[str]:
        """Prompt user to select a script by number or key name"""
        if not script_list:
            print("⚠️  Please list scripts first (command 6)")
            return None

        print("\nSelect script:")
        print("  - Enter script number (e.g., 1, 2, 3)")
        print("  - Or enter full script key")

        choice = input("Script: ").strip()

        # Try as number first
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(script_list):
                return script_list[idx]
            else:
                print(f"❌ Invalid number. Valid range: 1-{len(script_list)}")
                return None

        # Try as script key
        if choice in script_list:
            return choice

        # Try fuzzy match
        for script in script_list:
            if choice in script:
                print(f"✓ Matched: {script}")
                return script

        print(f"❌ Script not found: {choice}")
        return None

    async def show_statistics(self):
        """Show database statistics"""
        print("\n📈 Database Statistics")
        print("-" * 70)

        # Storage DB stats
        if Path(self.storage_db).exists():
            size = Path(self.storage_db).stat().st_size
            print(f"Storage DB Size: {size:,} bytes ({size/1024:.2f} KB)")

            async with aiosqlite.connect(self.storage_db) as db:
                # Count tables
                cursor = await db.execute("""
                    SELECT COUNT(*) FROM sqlite_master
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                """)
                table_count = (await cursor.fetchone())[0]
                print(f"Total Collections: {table_count}")

                # Total rows
                cursor = await db.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                """)
                tables = await cursor.fetchall()
                total_rows = 0
                for (table_name,) in tables:
                    cursor = await db.execute(f"SELECT COUNT(*) FROM {table_name}")
                    total_rows += (await cursor.fetchone())[0]
                print(f"Total Records: {total_rows}")
        else:
            print("Storage DB: Not found")

        print()

        # KV DB stats
        if Path(self.kv_db).exists():
            size = Path(self.kv_db).stat().st_size
            print(f"KV DB Size: {size:,} bytes ({size/1024:.2f} KB)")

            async with aiosqlite.connect(self.kv_db) as db:
                cursor = await db.execute("SELECT COUNT(*) FROM kv_storage")
                count = (await cursor.fetchone())[0]
                print(f"Cached Scripts: {count}")
        else:
            print("KV DB: Not found")


async def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description='Inspect StorageAgent databases')
    parser.add_argument(
        '--config',
        help='Path to config file (default: tests/test_config.yaml)'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List all collections and exit'
    )
    parser.add_argument(
        '--scripts',
        action='store_true',
        help='Show cached scripts and exit'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show statistics and exit'
    )

    args = parser.parse_args()

    inspector = StorageInspector(config_path=args.config)

    # Quick commands
    if args.list:
        await inspector.list_tables()
        return

    if args.scripts:
        await inspector.list_cached_scripts()
        return

    if args.stats:
        await inspector.show_statistics()
        return

    # Interactive mode
    await inspector.interactive_menu()


if __name__ == "__main__":
    asyncio.run(main())
