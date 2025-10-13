#!/usr/bin/env python3
"""
Storage Inspector - Unified Management for StorageAgent and ScraperAgent Caches

This tool manages both storage data and agent caches:

1. Collection Management (StorageAgent Data):
   - Collections: logical name (e.g., "daily_products")
   - Physical table: {collection}_{user_id}
   - View, query, and clear collections

2. Storage Cache Management (StorageAgent Scripts):
   - Cache format: storage_{operation}_{collection}_{user_id}[_{hash}]
   - View, inspect, and delete storage SQL caches

3. Scraper Script Cache Management (ScraperAgent Scripts):
   - Cache format: scraper_script_{hash}
   - View script details, data requirements, DOM config
   - Delete individual or clear all scraper scripts

Usage:
    # Interactive mode (recommended)
    python inspect_storage.py

    # Collection management
    python inspect_storage.py --list-collections
    python inspect_storage.py --export-collection daily_products --user default_user
    python inspect_storage.py --export-collection daily_products -o /path/to/output.csv --limit 100
    python inspect_storage.py --clear-collection daily_products --user default_user

    # Storage cache management
    python inspect_storage.py --list-cache

    # Scraper script management
    python inspect_storage.py --list-scripts
    python inspect_storage.py --show-script scraper_script_abc123
    python inspect_storage.py --export-script scraper_script_abc123
    python inspect_storage.py --export-script scraper_script_abc123 -o /path/to/output.py
    python inspect_storage.py --clear-scripts

    # Statistics
    python inspect_storage.py --stats
"""

import asyncio
import sys
import json
import aiosqlite
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# Add project path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from base_app.base_app.server.core.config_service import ConfigService


class StorageAgentInspector:
    """
    Inspector tool aligned with StorageAgent's logic

    Key Concepts (matching storage_agent.py):
    - Collection: Logical name (e.g., "daily_products")
    - Table: Physical name = {collection}_{user_id}
    - Cache: storage_{operation}_{collection}_{user_id}[_{hash}]
    """

    def __init__(self, config_path: Optional[str] = None):
        """Initialize inspector with config"""
        if not config_path:
            config_path = str(project_root / "tests" / "test_config.yaml")

        self.config_service = ConfigService(config_path=config_path)
        self.storage_db = str(self.config_service.get_path('data.databases.storage'))
        self.kv_db = str(self.config_service.get_path('data.databases.kv'))

        print(f"\n{'=' * 80}")
        print("Storage Inspector - StorageAgent & ScraperAgent Cache Management")
        print(f"{'=' * 80}")
        print(f"Storage DB:  {self.storage_db}")
        print(f"KV Cache DB: {self.kv_db}")
        print(f"{'=' * 80}\n")

    # ============================================================================
    # SECTION 1: Collection Management (Aligned with StorageAgent)
    # ============================================================================

    async def list_collections(self) -> List[Tuple[str, str, str]]:
        """
        List all collections (matching storage_agent's view)

        Returns:
            List of (collection_name, user_id, table_name) tuples
        """
        print("\n📦 Collections (StorageAgent View):")
        print("-" * 80)

        if not Path(self.storage_db).exists():
            print("  ℹ️  Storage database does not exist yet")
            return []

        collections = []

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

            for i, (table_name,) in enumerate(tables, 1):
                # Parse: {collection}_{user_id}
                parts = table_name.rsplit('_', 1)
                if len(parts) == 2:
                    collection, user_id = parts
                else:
                    collection = table_name
                    user_id = "unknown"

                # Get row count
                cursor = await db.execute(f"SELECT COUNT(*) FROM {table_name}")
                row_count = (await cursor.fetchone())[0]

                # Get cached schema status
                cache_key = f"storage_insert_{collection}_{user_id}"
                has_cache = await self._check_cache_exists(cache_key)
                cache_status = "✅" if has_cache else "❌"

                collections.append((collection, user_id, table_name))

                print(f"  [{i}] Collection: {collection}")
                print(f"      User: {user_id} | Table: {table_name}")
                print(f"      Rows: {row_count} | Schema Cache: {cache_status}")
                print()

        return collections

    async def show_collection_detail(self, collection: str, user_id: str = "default_user"):
        """
        Show collection details (matching storage_agent's perspective)

        Shows:
        - Table schema (from storage.db)
        - Cached schema (from kv.db)
        - Recent data samples
        - All related cache entries
        """
        table_name = f"{collection}_{user_id}"

        print(f"\n📋 Collection Detail: {collection} (user: {user_id})")
        print(f"Physical Table: {table_name}")
        print("-" * 80)

        # 1. Table Schema (from storage.db)
        if not Path(self.storage_db).exists():
            print("❌ Storage database does not exist")
            return

        async with aiosqlite.connect(self.storage_db) as db:
            # Check if table exists
            cursor = await db.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name = ?
            """, (table_name,))

            if not await cursor.fetchone():
                print(f"❌ Collection not found: {collection}")
                return

            # Show schema
            print("\n1️⃣  Table Schema (storage.db):")
            cursor = await db.execute(f"PRAGMA table_info({table_name})")
            columns = await cursor.fetchall()

            for col_id, name, type_, notnull, default, pk in columns:
                markers = []
                if pk:
                    markers.append("PRIMARY KEY")
                if notnull:
                    markers.append("NOT NULL")
                if default:
                    markers.append(f"DEFAULT {default}")

                marker_str = f" [{', '.join(markers)}]" if markers else ""
                print(f"   - {name}: {type_}{marker_str}")

            # Show row count
            cursor = await db.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = (await cursor.fetchone())[0]
            print(f"\n   Total Records: {row_count}")

            # Show sample data
            if row_count > 0:
                print("\n   Recent Records (latest 3):")
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    f"SELECT * FROM {table_name} ORDER BY created_at DESC LIMIT 3"
                )
                rows = await cursor.fetchall()

                for i, row in enumerate(rows, 1):
                    print(f"\n   Record {i}:")
                    for key in row.keys():
                        value = row[key]
                        if isinstance(value, str) and len(value) > 80:
                            value = value[:80] + "..."
                        print(f"     {key}: {value}")

        # 2. Cached Schema (from kv.db)
        cache_key = f"storage_insert_{collection}_{user_id}"
        cached_schema = await self._get_cached_schema(cache_key)

        print(f"\n2️⃣  Cached Schema (kv.db):")
        if cached_schema:
            print(f"   Cache Key: {cache_key}")
            print(f"   Field Order: {cached_schema.get('field_order', [])}")
            print(f"\n   CREATE TABLE SQL:")
            print(f"   {cached_schema.get('create_table_sql', 'N/A')}")
            print(f"\n   INSERT SQL:")
            print(f"   {cached_schema.get('insert_sql', 'N/A')}")
        else:
            print(f"   ❌ No cached schema found (cache key: {cache_key})")

        # 3. All related cache entries
        print(f"\n3️⃣  All Related Cache Entries:")
        related_caches = await self._find_related_caches(collection, user_id)

        if related_caches:
            for cache_key, cache_info in related_caches.items():
                operation_type = self._parse_cache_operation(cache_key)
                print(f"   - {cache_key}")
                print(f"     Type: {operation_type}")
                print(f"     Updated: {cache_info['updated_at']}")
        else:
            print(f"   (No cache entries for this collection)")

    async def clear_collection(self, collection: str, user_id: str = "default_user", confirm: bool = True) -> bool:
        """
        Clear collection completely (aligned with storage_agent logic)

        This removes:
        1. Physical table: {collection}_{user_id}
        2. All cache entries: storage_*_{collection}_{user_id}*

        This ensures the next store will create a fresh schema.
        """
        table_name = f"{collection}_{user_id}"

        print(f"\n🧹 Clear Collection: {collection} (user: {user_id})")
        print(f"   Physical table: {table_name}")
        print("-" * 80)

        # Confirm
        if confirm:
            response = input(f"⚠️  This will delete:\n"
                           f"   - Table: {table_name}\n"
                           f"   - All cache: storage_*_{collection}_{user_id}*\n"
                           f"   Continue? (yes/no): ").strip().lower()
            if response != 'yes':
                print("❌ Cancelled")
                return False

        success = True
        deleted_items = []

        # 1. Drop table
        if Path(self.storage_db).exists():
            async with aiosqlite.connect(self.storage_db) as db:
                cursor = await db.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name = ?
                """, (table_name,))

                if await cursor.fetchone():
                    await db.execute(f"DROP TABLE {table_name}")
                    await db.commit()
                    deleted_items.append(f"Table: {table_name}")
                    print(f"  ✅ Dropped table: {table_name}")
                else:
                    print(f"  ℹ️  Table not found: {table_name}")

        # 2. Delete all related cache entries
        if Path(self.kv_db).exists():
            related_caches = await self._find_related_caches(collection, user_id)

            if related_caches:
                async with aiosqlite.connect(self.kv_db) as db:
                    for cache_key in related_caches.keys():
                        await db.execute("DELETE FROM kv_storage WHERE key = ?", (cache_key,))
                        deleted_items.append(f"Cache: {cache_key}")
                        print(f"  ✅ Deleted cache: {cache_key}")
                    await db.commit()
            else:
                print(f"  ℹ️  No cache entries found")

        if deleted_items:
            print(f"\n✅ Collection '{collection}' cleared successfully!")
            print(f"   Deleted {len(deleted_items)} items")
        else:
            print(f"\n⚠️  Collection '{collection}' does not exist")

        return success

    async def query_collection_data(
        self,
        collection: str,
        user_id: str = "default_user",
        limit: int = 10,
        filters: Optional[Dict] = None
    ):
        """Query data from collection (simple version, matching storage_agent view)"""
        table_name = f"{collection}_{user_id}"

        print(f"\n📄 Query Collection: {collection} (user: {user_id})")
        print(f"   Limit: {limit}")
        print("-" * 80)

        if not Path(self.storage_db).exists():
            print("❌ Storage database does not exist")
            return

        async with aiosqlite.connect(self.storage_db) as db:
            # Check if table exists
            cursor = await db.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name = ?
            """, (table_name,))

            if not await cursor.fetchone():
                print(f"❌ Collection not found: {collection}")
                return

            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT * FROM {table_name} ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            rows = await cursor.fetchall()

            if not rows:
                print("  (No data)")
                return

            print(f"\nFound {len(rows)} records:\n")
            for i, row in enumerate(rows, 1):
                print(f"Record {i}:")
                for key in row.keys():
                    value = row[key]
                    if isinstance(value, str) and len(value) > 100:
                        value = value[:100] + "..."
                    print(f"  {key}: {value}")
                print()

    async def export_collection_to_csv(
        self,
        collection: str,
        user_id: str = "default_user",
        output_path: Optional[str] = None,
        limit: Optional[int] = None
    ) -> Optional[str]:
        """Export collection data to CSV file
        
        Args:
            collection: Collection name
            user_id: User ID (default: "default_user")
            output_path: Custom output path (optional, defaults to ./{collection}_{user_id}.csv)
            limit: Maximum number of rows to export (None = all)
            
        Returns:
            Path to exported CSV file, or None if failed
        """
        import csv
        
        table_name = f"{collection}_{user_id}"
        
        print(f"\n📤 Export Collection to CSV: {collection} (user: {user_id})")
        print("-" * 80)
        
        if not Path(self.storage_db).exists():
            print("❌ Storage database does not exist")
            return None
        
        # Generate output path if not specified
        if not output_path:
            output_path = f"./{collection}_{user_id}.csv"
        
        output_file = Path(output_path)
        
        async with aiosqlite.connect(self.storage_db) as db:
            # Check if table exists
            cursor = await db.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name = ?
            """, (table_name,))
            
            if not await cursor.fetchone():
                print(f"❌ Collection not found: {collection}")
                return None
            
            # Get total count
            cursor = await db.execute(f"SELECT COUNT(*) FROM {table_name}")
            total_count = (await cursor.fetchone())[0]
            
            if total_count == 0:
                print("⚠️  Collection is empty, no data to export")
                return None
            
            print(f"  Total records: {total_count}")
            if limit:
                print(f"  Export limit: {limit}")
                export_count = min(total_count, limit)
            else:
                print(f"  Export limit: ALL")
                export_count = total_count
            
            # Query data
            db.row_factory = aiosqlite.Row
            if limit:
                cursor = await db.execute(
                    f"SELECT * FROM {table_name} ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
            else:
                cursor = await db.execute(f"SELECT * FROM {table_name} ORDER BY created_at DESC")
            
            rows = await cursor.fetchall()
            
            if not rows:
                print("⚠️  No data to export")
                return None
            
            # Write to CSV
            try:
                with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                    # Get column names from first row
                    fieldnames = rows[0].keys()
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    
                    # Write header
                    writer.writeheader()
                    
                    # Write data rows
                    for row in rows:
                        writer.writerow(dict(row))
                
                print(f"\n✅ Export successful!")
                print(f"   File: {output_file.absolute()}")
                print(f"   Rows: {len(rows)}")
                print(f"   Columns: {len(fieldnames)}")
                print(f"   Size: {output_file.stat().st_size:,} bytes")
                
                # Show column names
                print(f"\n   Columns:")
                for col in fieldnames:
                    print(f"     • {col}")
                
                return str(output_file.absolute())
                
            except Exception as e:
                print(f"❌ Failed to write CSV: {e}")
                return None

    # ============================================================================
    # SECTION 2: Storage Cache Management (StorageAgent Scripts)
    # ============================================================================

    async def list_all_caches(self, pattern: str = "") -> List[str]:
        """
        List all cache entries (organized by collection)

        Cache key format: storage_{operation}_{collection}_{user_id}[_{hash}]
        """
        print(f"\n🔧 Cache Entries{f' (pattern: {pattern})' if pattern else ''}:")
        print("-" * 80)

        if not Path(self.kv_db).exists():
            print("  ℹ️  KV cache database does not exist yet")
            return []

        cache_keys = []

        async with aiosqlite.connect(self.kv_db) as db:
            if pattern:
                cursor = await db.execute("""
                    SELECT key, user_id, created_at, updated_at
                    FROM kv_storage
                    WHERE key LIKE ?
                    ORDER BY key
                """, (f"%{pattern}%",))
            else:
                cursor = await db.execute("""
                    SELECT key, user_id, created_at, updated_at
                    FROM kv_storage
                    WHERE key LIKE 'storage_%'
                    ORDER BY key
                """)

            caches = await cursor.fetchall()

            if not caches:
                print(f"  (No cache entries{f' matching {pattern}' if pattern else ''})")
                return []

            # Group by collection
            by_collection = {}
            for key, user_id, created_at, updated_at in caches:
                parsed = self._parse_cache_key(key)
                if parsed:
                    collection_key = f"{parsed['collection']}_{parsed['user_id']}"
                    if collection_key not in by_collection:
                        by_collection[collection_key] = []
                    by_collection[collection_key].append({
                        'key': key,
                        'operation': parsed['operation'],
                        'updated_at': updated_at
                    })
                    cache_keys.append(key)

            # Display grouped by collection
            for i, (collection_key, entries) in enumerate(by_collection.items(), 1):
                print(f"\n  [{i}] Collection: {collection_key}")
                for entry in entries:
                    op_type = self._parse_cache_operation(entry['key'])
                    print(f"      - {op_type}: {entry['key']}")
                    print(f"        Updated: {entry['updated_at']}")

        return cache_keys

    async def show_cache_detail(self, cache_key: str):
        """Show detailed cache content"""
        print(f"\n🔍 Cache Detail: {cache_key}")
        print("-" * 80)

        if not Path(self.kv_db).exists():
            print("❌ KV cache database does not exist")
            return

        async with aiosqlite.connect(self.kv_db) as db:
            cursor = await db.execute("""
                SELECT user_id, value, created_at, updated_at
                FROM kv_storage
                WHERE key = ?
            """, (cache_key,))

            result = await cursor.fetchone()

            if not result:
                print(f"❌ Cache not found: {cache_key}")
                return

            user_id, value_json, created_at, updated_at = result
            parsed = self._parse_cache_key(cache_key)

            print(f"User: {user_id}")
            print(f"Created: {created_at}")
            print(f"Updated: {updated_at}")
            if parsed:
                print(f"Collection: {parsed['collection']}")
                print(f"Operation: {parsed['operation']}")

            try:
                value = json.loads(value_json)
                print(f"\nCache Content:")
                print(json.dumps(value, indent=2, ensure_ascii=False))
            except json.JSONDecodeError:
                print(f"⚠️  Value is not valid JSON")
                print(f"Raw: {value_json[:200]}")

    async def delete_cache(self, cache_key: str, confirm: bool = True) -> bool:
        """Delete a specific cache entry"""
        print(f"\n🗑️  Delete Cache: {cache_key}")
        print("-" * 80)

        if confirm:
            response = input(f"⚠️  Delete this cache? (yes/no): ").strip().lower()
            if response != 'yes':
                print("❌ Cancelled")
                return False

        if not Path(self.kv_db).exists():
            print("❌ KV cache database does not exist")
            return False

        async with aiosqlite.connect(self.kv_db) as db:
            cursor = await db.execute("SELECT key FROM kv_storage WHERE key = ?", (cache_key,))
            if not await cursor.fetchone():
                print(f"❌ Cache not found: {cache_key}")
                return False

            await db.execute("DELETE FROM kv_storage WHERE key = ?", (cache_key,))
            await db.commit()
            print(f"✅ Deleted: {cache_key}")
            return True

    # ============================================================================
    # SECTION 3: Scraper Script Cache Management (ScraperAgent Scripts)
    # ============================================================================

    async def list_scraper_scripts(self) -> List[str]:
        """
        List all scraper script caches

        Script key format: scraper_script_{hash}
        """
        print(f"\n🤖 Scraper Script Cache:")
        print("-" * 80)

        if not Path(self.kv_db).exists():
            print("  ℹ️  KV cache database does not exist yet")
            return []

        script_keys = []

        async with aiosqlite.connect(self.kv_db) as db:
            cursor = await db.execute("""
                SELECT key, user_id, created_at, updated_at
                FROM kv_storage
                WHERE key LIKE 'scraper_script_%'
                ORDER BY updated_at DESC
            """)

            scripts = await cursor.fetchall()

            if not scripts:
                print(f"  (No scraper script caches)")
                return []

            for i, (key, user_id, created_at, updated_at) in enumerate(scripts, 1):
                script_keys.append(key)
                script_hash = key.replace('scraper_script_', '')
                print(f"\n  [{i}] Script: {script_hash}")
                print(f"      Key: {key}")
                print(f"      User: {user_id}")
                print(f"      Updated: {updated_at}")

        return script_keys

    async def show_scraper_script_detail(self, script_key: str, export_to_file: bool = False):
        """Show detailed scraper script content
        
        Args:
            script_key: Script key to show
            export_to_file: If True, export script to a .py file
        """
        print(f"\n🔍 Scraper Script Detail: {script_key}")
        print("-" * 80)

        if not Path(self.kv_db).exists():
            print("❌ KV cache database does not exist")
            return

        async with aiosqlite.connect(self.kv_db) as db:
            cursor = await db.execute("""
                SELECT user_id, value, created_at, updated_at
                FROM kv_storage
                WHERE key = ?
            """, (script_key,))

            result = await cursor.fetchone()

            if not result:
                print(f"❌ Script not found: {script_key}")
                return

            user_id, value_json, created_at, updated_at = result

            print(f"User: {user_id}")
            print(f"Created: {created_at}")
            print(f"Updated: {updated_at}")

            try:
                script_data = json.loads(value_json)
                
                # Show metadata
                print(f"\n📋 Metadata:")
                print(f"  Version: {script_data.get('version', 'N/A')}")
                print(f"  Created At: {script_data.get('created_at', 'N/A')}")
                
                # Show DOM config
                dom_config = script_data.get('dom_config', {})
                if dom_config:
                    print(f"\n🌳 DOM Configuration:")
                    print(f"  Generation Scope: {dom_config.get('generation_dom_scope', 'N/A')}")
                    print(f"  Execution Scope: {dom_config.get('execution_dom_scope', 'N/A')}")
                
                # Show data requirements
                data_req = script_data.get('data_requirements', {})
                if data_req:
                    print(f"\n📊 Data Requirements:")
                    user_desc = data_req.get('user_description', '')
                    if user_desc:
                        print(f"  Description: {user_desc}")
                    
                    output_format = data_req.get('output_format', {})
                    if output_format:
                        print(f"  Fields:")
                        for field, desc in output_format.items():
                            print(f"    - {field}: {desc}")
                
                # Show script content
                script_content = script_data.get('script_content', '')
                if script_content:
                    lines = script_content.split('\n')
                    print(f"\n📝 Script Content ({len(lines)} lines, {len(script_content)} chars):")
                    
                    if export_to_file:
                        # Export to file
                        output_file = await self._export_script_to_file(
                            script_key, script_data, script_content
                        )
                        print(f"  ✅ Exported to: {output_file}")
                    else:
                        print(f"  Preview (first 20 lines):")
                        print("-" * 80)
                        for i, line in enumerate(lines[:20], 1):
                            print(f"  {i:3d} | {line}")
                        if len(lines) > 20:
                            print(f"  ... ({len(lines) - 20} more lines)")
                        print("-" * 80)
                        print(f"\n  💡 Tip: Use --export-script to save full content to file")
                
            except json.JSONDecodeError as e:
                print(f"⚠️  Value is not valid JSON: {e}")
                print(f"Raw (first 200 chars): {value_json[:200]}")

    async def delete_scraper_script(self, script_key: str, confirm: bool = True) -> bool:
        """Delete a scraper script cache"""
        print(f"\n🗑️  Delete Scraper Script: {script_key}")
        print("-" * 80)

        if confirm:
            response = input(f"⚠️  Delete this script cache? (yes/no): ").strip().lower()
            if response != 'yes':
                print("❌ Cancelled")
                return False

        if not Path(self.kv_db).exists():
            print("❌ KV cache database does not exist")
            return False

        async with aiosqlite.connect(self.kv_db) as db:
            cursor = await db.execute("SELECT key FROM kv_storage WHERE key = ?", (script_key,))
            if not await cursor.fetchone():
                print(f"❌ Script not found: {script_key}")
                return False

            await db.execute("DELETE FROM kv_storage WHERE key = ?", (script_key,))
            await db.commit()
            print(f"✅ Deleted: {script_key}")
            return True

    async def clear_all_scraper_scripts(self, confirm: bool = True) -> bool:
        """Clear all scraper script caches"""
        print(f"\n🧹 Clear All Scraper Scripts")
        print("-" * 80)

        if not Path(self.kv_db).exists():
            print("❌ KV cache database does not exist")
            return False

        # Count scripts first
        async with aiosqlite.connect(self.kv_db) as db:
            cursor = await db.execute("""
                SELECT COUNT(*) FROM kv_storage
                WHERE key LIKE 'scraper_script_%'
            """)
            count = (await cursor.fetchone())[0]

            if count == 0:
                print("  ℹ️  No scraper scripts to delete")
                return True

            print(f"  Found {count} scraper script(s)")

            if confirm:
                response = input(f"⚠️  Delete all {count} scraper scripts? (yes/no): ").strip().lower()
                if response != 'yes':
                    print("❌ Cancelled")
                    return False

            await db.execute("DELETE FROM kv_storage WHERE key LIKE 'scraper_script_%'")
            await db.commit()
            print(f"✅ Deleted {count} scraper script(s)")
            return True

    async def export_scraper_script(self, script_key: str, output_path: Optional[str] = None) -> Optional[str]:
        """Export scraper script to a Python file
        
        Args:
            script_key: Script key to export
            output_path: Custom output path (optional, defaults to current directory)
            
        Returns:
            Path to exported file, or None if failed
        """
        if not Path(self.kv_db).exists():
            print("❌ KV cache database does not exist")
            return None

        async with aiosqlite.connect(self.kv_db) as db:
            cursor = await db.execute("""
                SELECT value FROM kv_storage WHERE key = ?
            """, (script_key,))

            result = await cursor.fetchone()

            if not result:
                print(f"❌ Script not found: {script_key}")
                return None

            try:
                script_data = json.loads(result[0])
                script_content = script_data.get('script_content', '')
                
                if not script_content:
                    print("❌ Script content is empty")
                    return None

                return await self._export_script_to_file(
                    script_key, script_data, script_content, output_path
                )

            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse script data: {e}")
                return None

    # ============================================================================
    # Helper Methods
    # ============================================================================

    async def _export_script_to_file(
        self, 
        script_key: str, 
        script_data: Dict, 
        script_content: str,
        output_path: Optional[str] = None
    ) -> str:
        """Export script content to a Python file with metadata header
        
        Args:
            script_key: Script key
            script_data: Full script data dictionary
            script_content: Script content string
            output_path: Custom output path (optional)
            
        Returns:
            Path to exported file
        """
        # Determine output file path
        if output_path:
            output_file = Path(output_path)
        else:
            # Default: current directory with script key as filename
            script_hash = script_key.replace('scraper_script_', '')
            output_file = Path.cwd() / f"{script_hash}.py"

        # Build file content with metadata header
        lines = []
        lines.append('"""')
        lines.append(f'Exported Scraper Script: {script_key}')
        lines.append('')
        
        # Metadata
        lines.append('Metadata:')
        lines.append(f'  Version: {script_data.get("version", "N/A")}')
        lines.append(f'  Created: {script_data.get("created_at", "N/A")}')
        
        # DOM config
        dom_config = script_data.get('dom_config', {})
        if dom_config:
            lines.append('')
            lines.append('DOM Configuration:')
            lines.append(f'  Generation Scope: {dom_config.get("generation_dom_scope", "N/A")}')
            lines.append(f'  Execution Scope: {dom_config.get("execution_dom_scope", "N/A")}')
        
        # Data requirements
        data_req = script_data.get('data_requirements', {})
        if data_req:
            lines.append('')
            lines.append('Data Requirements:')
            user_desc = data_req.get('user_description', '')
            if user_desc:
                lines.append(f'  Description: {user_desc}')
            
            output_format = data_req.get('output_format', {})
            if output_format:
                lines.append('  Fields:')
                for field, desc in output_format.items():
                    lines.append(f'    - {field}: {desc}')
        
        lines.append('"""')
        lines.append('')
        
        # Add script content
        lines.append(script_content)
        
        # Write to file
        output_file.write_text('\n'.join(lines), encoding='utf-8')
        
        return str(output_file.absolute())

    async def _check_cache_exists(self, cache_key: str) -> bool:
        """Check if a cache key exists"""
        if not Path(self.kv_db).exists():
            return False

        async with aiosqlite.connect(self.kv_db) as db:
            cursor = await db.execute(
                "SELECT key FROM kv_storage WHERE key = ?",
                (cache_key,)
            )
            return await cursor.fetchone() is not None

    async def _get_cached_schema(self, cache_key: str) -> Optional[Dict]:
        """Get cached schema for a collection"""
        if not Path(self.kv_db).exists():
            return None

        async with aiosqlite.connect(self.kv_db) as db:
            cursor = await db.execute(
                "SELECT value FROM kv_storage WHERE key = ?",
                (cache_key,)
            )
            result = await cursor.fetchone()

            if result:
                try:
                    return json.loads(result[0])
                except json.JSONDecodeError:
                    return None
            return None

    async def _find_related_caches(self, collection: str, user_id: str) -> Dict[str, Dict]:
        """Find all cache entries related to a collection"""
        if not Path(self.kv_db).exists():
            return {}

        related = {}
        pattern = f"storage_%_{collection}_{user_id}%"

        async with aiosqlite.connect(self.kv_db) as db:
            cursor = await db.execute("""
                SELECT key, created_at, updated_at, value
                FROM kv_storage
                WHERE key LIKE ?
            """, (pattern,))

            rows = await cursor.fetchall()

            for key, created_at, updated_at, value in rows:
                related[key] = {
                    'created_at': created_at,
                    'updated_at': updated_at,
                    'value': value
                }

        return related

    def _parse_cache_key(self, cache_key: str) -> Optional[Dict[str, str]]:
        """
        Parse cache key into components

        Format: storage_{operation}_{collection}_{user_id}[_{hash}]
        Examples:
        - storage_insert_daily_products_default_user
        - storage_query_daily_products_default_user_abc123
        """
        if not cache_key.startswith('storage_'):
            return None

        parts = cache_key.split('_', 3)
        if len(parts) < 4:
            return None

        # parts[0] = 'storage'
        # parts[1] = operation (insert/query/export)
        # parts[2] = first part of collection name
        # parts[3] = rest (collection_user_id[_hash])

        operation = parts[1]

        # Parse collection and user_id from remainder
        remainder = parts[2] + '_' + parts[3]

        # Try to split by last occurrence of _{user_id}
        # Assume user_id doesn't contain '_'
        remainder_parts = remainder.rsplit('_', 1)
        if len(remainder_parts) == 2:
            potential_collection, potential_user = remainder_parts

            # Check if there's a hash suffix
            if '_' in potential_user:
                user_parts = potential_user.split('_', 1)
                user_id = user_parts[0]
                hash_suffix = user_parts[1]
            else:
                user_id = potential_user
                hash_suffix = None

            return {
                'operation': operation,
                'collection': potential_collection,
                'user_id': user_id,
                'hash': hash_suffix
            }

        return None

    def _parse_cache_operation(self, cache_key: str) -> str:
        """Get human-readable operation type from cache key"""
        if 'storage_insert' in cache_key:
            return "INSERT Schema"
        elif 'storage_query' in cache_key:
            return "QUERY SQL"
        elif 'storage_export' in cache_key:
            return "EXPORT SQL"
        return "UNKNOWN"

    async def show_statistics(self):
        """Show database statistics"""
        print("\n📈 Statistics:")
        print("-" * 80)

        # Storage DB
        if Path(self.storage_db).exists():
            size = Path(self.storage_db).stat().st_size
            print(f"Storage DB: {size:,} bytes ({size/1024:.2f} KB)")

            async with aiosqlite.connect(self.storage_db) as db:
                cursor = await db.execute("""
                    SELECT COUNT(*) FROM sqlite_master
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                """)
                table_count = (await cursor.fetchone())[0]
                print(f"Collections: {table_count}")

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
            print("Storage DB: Not created yet")

        print()

        # KV Cache DB
        if Path(self.kv_db).exists():
            size = Path(self.kv_db).stat().st_size
            print(f"KV Cache DB: {size:,} bytes ({size/1024:.2f} KB)")

            async with aiosqlite.connect(self.kv_db) as db:
                # Storage cache entries
                cursor = await db.execute("""
                    SELECT COUNT(*) FROM kv_storage
                    WHERE key LIKE 'storage_%'
                """)
                storage_count = (await cursor.fetchone())[0]
                print(f"Storage Cache Entries: {storage_count}")

                # Scraper script entries
                cursor = await db.execute("""
                    SELECT COUNT(*) FROM kv_storage
                    WHERE key LIKE 'scraper_script_%'
                """)
                scraper_count = (await cursor.fetchone())[0]
                print(f"Scraper Script Entries: {scraper_count}")

                # Total cache entries
                cursor = await db.execute("SELECT COUNT(*) FROM kv_storage")
                total_count = (await cursor.fetchone())[0]
                print(f"Total Cache Entries: {total_count}")
        else:
            print("KV Cache DB: Not created yet")

    # ============================================================================
    # Interactive Menu
    # ============================================================================

    async def interactive_menu(self):
        """Interactive menu (aligned with storage_agent concepts)"""
        while True:
            print("\n" + "=" * 80)
            print("Storage Agent Inspector")
            print("=" * 80)
            print("\n📦 COLLECTION MANAGEMENT (Data):")
            print("  1. List all collections")
            print("  2. Show collection detail")
            print("  3. Query collection data")
            print("  4. Export collection to CSV")
            print("  5. Clear collection (table + cache)")
            print("\n🔧 STORAGE CACHE MANAGEMENT (StorageAgent):")
            print("  6. List storage cache entries")
            print("  7. Show storage cache detail")
            print("  8. Delete storage cache entry")
            print("\n🤖 SCRAPER SCRIPT CACHE MANAGEMENT (ScraperAgent):")
            print("  9. List scraper scripts")
            print("  10. Show scraper script detail")
            print("  11. Export scraper script to file")
            print("  12. Delete scraper script")
            print("  13. Clear all scraper scripts")
            print("\n📈 STATISTICS:")
            print("  14. Show statistics")
            print("\n  q. Quit")
            print("=" * 80)

            choice = input("\nCommand: ").strip()

            if choice == '1':
                await self.list_collections()

            elif choice == '2':
                collection = input("Collection name: ").strip()
                if collection:
                    user_id = input("User ID (default: default_user): ").strip() or "default_user"
                    await self.show_collection_detail(collection, user_id)

            elif choice == '3':
                collection = input("Collection name: ").strip()
                if collection:
                    user_id = input("User ID (default: default_user): ").strip() or "default_user"
                    limit = input("Limit (default: 10): ").strip()
                    limit = int(limit) if limit else 10
                    await self.query_collection_data(collection, user_id, limit)

            elif choice == '4':
                collection = input("Collection name: ").strip()
                if collection:
                    user_id = input("User ID (default: default_user): ").strip() or "default_user"
                    output_path = input("Output path (Enter for ./{collection}_{user_id}.csv): ").strip() or None
                    limit_input = input("Limit rows (Enter for ALL): ").strip()
                    limit = int(limit_input) if limit_input else None
                    result = await self.export_collection_to_csv(collection, user_id, output_path, limit)
                    if result:
                        print(f"\n💾 File saved: {result}")

            elif choice == '5':
                collection = input("Collection name: ").strip()
                if collection:
                    user_id = input("User ID (default: default_user): ").strip() or "default_user"
                    await self.clear_collection(collection, user_id)

            elif choice == '6':
                pattern = input("Search pattern (Enter for all): ").strip()
                await self.list_all_caches(pattern)

            elif choice == '7':
                cache_key = input("Cache key: ").strip()
                if cache_key:
                    await self.show_cache_detail(cache_key)

            elif choice == '8':
                cache_key = input("Cache key: ").strip()
                if cache_key:
                    await self.delete_cache(cache_key)

            elif choice == '9':
                await self.list_scraper_scripts()

            elif choice == '10':
                script_key = input("Script key: ").strip()
                if script_key:
                    await self.show_scraper_script_detail(script_key)

            elif choice == '11':
                script_key = input("Script key: ").strip()
                if script_key:
                    output_path = input("Output path (Enter for current dir): ").strip() or None
                    result = await self.export_scraper_script(script_key, output_path)
                    if result:
                        print(f"✅ Exported to: {result}")

            elif choice == '12':
                script_key = input("Script key: ").strip()
                if script_key:
                    await self.delete_scraper_script(script_key)

            elif choice == '13':
                await self.clear_all_scraper_scripts()

            elif choice == '14':
                await self.show_statistics()

            elif choice.lower() == 'q':
                print("\nGoodbye!")
                break

            else:
                print("❌ Invalid command")


async def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Storage Agent Inspector (Aligned with StorageAgent)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode
  python inspect_storage.py

  # Collection management
  python inspect_storage.py --list-collections
  python inspect_storage.py --clear-collection daily_products --user default_user

  # Storage cache management
  python inspect_storage.py --list-cache

  # Scraper script management
  python inspect_storage.py --list-scripts
  python inspect_storage.py --show-script scraper_script_abc123
  python inspect_storage.py --export-script scraper_script_abc123
  python inspect_storage.py --export-script scraper_script_abc123 -o /path/to/output.py
  python inspect_storage.py --delete-script scraper_script_abc123
  python inspect_storage.py --clear-scripts

  # Statistics
  python inspect_storage.py --stats
        """
    )

    parser.add_argument('--config', help='Config file path')
    
    # Collection management
    parser.add_argument('--list-collections', action='store_true', help='List all collections')
    parser.add_argument('--export-collection', metavar='NAME', help='Export collection to CSV')
    parser.add_argument('--clear-collection', metavar='NAME', help='Clear collection (table + cache)')
    parser.add_argument('--limit', type=int, metavar='N', help='Limit rows for export (default: all)')
    
    # Storage cache management
    parser.add_argument('--list-cache', action='store_true', help='List storage cache entries')
    
    # Scraper script management
    parser.add_argument('--list-scripts', action='store_true', help='List scraper scripts')
    parser.add_argument('--show-script', metavar='KEY', help='Show scraper script detail')
    parser.add_argument('--export-script', metavar='KEY', help='Export scraper script to file')
    parser.add_argument('--output', '-o', metavar='PATH', help='Output path for exported script')
    parser.add_argument('--delete-script', metavar='KEY', help='Delete scraper script')
    parser.add_argument('--clear-scripts', action='store_true', help='Clear all scraper scripts')
    
    # Other options
    parser.add_argument('--user', default='default_user', help='User ID (default: default_user)')
    parser.add_argument('--stats', action='store_true', help='Show statistics')

    args = parser.parse_args()

    inspector = StorageAgentInspector(config_path=args.config)

    # Quick commands
    if args.list_collections:
        await inspector.list_collections()
        return

    if args.export_collection:
        result = await inspector.export_collection_to_csv(
            args.export_collection, 
            args.user, 
            output_path=args.output,
            limit=args.limit
        )
        if result:
            print(f"\n✅ Collection exported successfully to: {result}")
        return

    if args.list_cache:
        await inspector.list_all_caches()
        return

    if args.stats:
        await inspector.show_statistics()
        return

    if args.clear_collection:
        await inspector.clear_collection(args.clear_collection, args.user, confirm=True)
        return

    if args.list_scripts:
        await inspector.list_scraper_scripts()
        return

    if args.show_script:
        await inspector.show_scraper_script_detail(args.show_script)
        return

    if args.export_script:
        result = await inspector.export_scraper_script(args.export_script, args.output)
        if result:
            print(f"\n✅ Script exported successfully to: {result}")
        return

    if args.delete_script:
        await inspector.delete_scraper_script(args.delete_script, confirm=True)
        return

    if args.clear_scripts:
        await inspector.clear_all_scraper_scripts(confirm=True)
        return

    # Interactive mode
    await inspector.interactive_menu()


if __name__ == "__main__":
    asyncio.run(main())
