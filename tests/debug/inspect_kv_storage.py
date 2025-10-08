#!/usr/bin/env python3
"""
KV Storage Inspector - 直接检查数据库内容
检查表结构、所有存储的键值对、以及特定key的详细信息
"""

import asyncio
import sys
import json
import aiosqlite
from pathlib import Path
from datetime import datetime

# Add project path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

try:
    from base_app.base_app.server.core.config_service import ConfigService
    CONFIG_SERVICE_AVAILABLE = True
except ImportError:
    CONFIG_SERVICE_AVAILABLE = False
    print("Warning: ConfigService not available, use --db to specify database path")


async def inspect_database(db_path: str):
    """检查数据库的完整状态"""
    print("=" * 70)
    print(f"KV Storage Inspector")
    print("=" * 70)
    print(f"Database: {db_path}")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 70)
    print()

    # Check if database file exists
    if not Path(db_path).exists():
        print(f"❌ 数据库文件不存在: {db_path}")
        return

    print(f"✅ 数据库文件存在，大小: {Path(db_path).stat().st_size} bytes")
    print()

    try:
        async with aiosqlite.connect(db_path) as db:
            # 1. Check if table exists
            print("1️⃣  检查表结构")
            print("-" * 70)

            cursor = await db.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='kv_storage'
            """)
            table = await cursor.fetchone()

            if not table:
                print("❌ 表 'kv_storage' 不存在")
                print()

                # Show all tables
                cursor = await db.execute("""
                    SELECT name FROM sqlite_master WHERE type='table'
                """)
                tables = await cursor.fetchall()
                print(f"数据库中的所有表: {[t[0] for t in tables]}")
                return

            print("✅ 表 'kv_storage' 存在")
            print()

            # 2. Show table schema
            print("2️⃣  表结构")
            print("-" * 70)
            cursor = await db.execute("PRAGMA table_info(kv_storage)")
            columns = await cursor.fetchall()

            for col in columns:
                col_id, name, type_, notnull, default, pk = col
                pk_marker = " [PRIMARY KEY]" if pk else ""
                notnull_marker = " [NOT NULL]" if notnull else ""
                print(f"  {name}: {type_}{pk_marker}{notnull_marker}")
            print()

            # 3. Show indexes
            print("3️⃣  索引")
            print("-" * 70)
            cursor = await db.execute("""
                SELECT name, sql FROM sqlite_master
                WHERE type='index' AND tbl_name='kv_storage'
            """)
            indexes = await cursor.fetchall()

            if indexes:
                for idx_name, idx_sql in indexes:
                    print(f"  {idx_name}")
                    if idx_sql:
                        print(f"    {idx_sql}")
            else:
                print("  (无索引)")
            print()

            # 4. Count total records
            print("4️⃣  数据统计")
            print("-" * 70)
            cursor = await db.execute("SELECT COUNT(*) FROM kv_storage")
            total_count = (await cursor.fetchone())[0]
            print(f"  总记录数: {total_count}")

            # Count by user_id
            cursor = await db.execute("""
                SELECT user_id, COUNT(*)
                FROM kv_storage
                GROUP BY user_id
            """)
            user_counts = await cursor.fetchall()

            print(f"  按用户统计:")
            for user_id, count in user_counts:
                print(f"    {user_id}: {count} 条记录")
            print()

            # 5. List all keys
            print("5️⃣  所有存储的键")
            print("-" * 70)
            cursor = await db.execute("""
                SELECT key, user_id, created_at, updated_at,
                       LENGTH(value) as value_length
                FROM kv_storage
                ORDER BY updated_at DESC
            """)
            rows = await cursor.fetchall()

            if rows:
                for key, user_id, created_at, updated_at, value_len in rows:
                    print(f"  Key: {key}")
                    print(f"    User ID: {user_id}")
                    print(f"    Created: {created_at}")
                    print(f"    Updated: {updated_at}")
                    print(f"    Value Length: {value_len} bytes")
                    print()
            else:
                print("  (无数据)")
            print()

            # 6. Show specific scraper script keys
            print("6️⃣  查找 scraper_script 相关的键")
            print("-" * 70)
            cursor = await db.execute("""
                SELECT key, user_id, value, created_at, updated_at
                FROM kv_storage
                WHERE key LIKE 'scraper_script_%'
                ORDER BY updated_at DESC
            """)
            script_rows = await cursor.fetchall()

            if script_rows:
                for key, user_id, value_json, created_at, updated_at in script_rows:
                    print(f"  🔑 Key: {key}")
                    print(f"     User: {user_id}")
                    print(f"     Created: {created_at}")
                    print(f"     Updated: {updated_at}")

                    # Try to parse JSON value
                    try:
                        value_data = json.loads(value_json)
                        print(f"     Value keys: {list(value_data.keys())}")

                        # Show script length if present
                        if 'script_content' in value_data:
                            script_len = len(value_data['script_content'])
                            print(f"     Script length: {script_len} characters")

                        # Show version and dom_config
                        if 'version' in value_data:
                            print(f"     Version: {value_data['version']}")

                        if 'dom_config' in value_data:
                            print(f"     DOM config: {value_data['dom_config']}")

                        # Show data requirements
                        if 'data_requirements' in value_data:
                            req = value_data['data_requirements']
                            if isinstance(req, dict):
                                print(f"     Data requirements:")
                                print(f"       Description: {req.get('user_description', 'N/A')}")
                                print(f"       Fields: {list(req.get('output_format', {}).keys())}")

                    except json.JSONDecodeError:
                        print(f"     ⚠️  Value is not valid JSON")
                        print(f"     Raw value (first 200 chars): {value_json[:200]}")

                    print()
            else:
                print("  (未找到 scraper_script 相关键)")
            print()

            # 7. Raw data dump (first 3 records)
            print("7️⃣  原始数据示例 (最近3条)")
            print("-" * 70)
            cursor = await db.execute("""
                SELECT key, user_id, value, created_at, updated_at
                FROM kv_storage
                ORDER BY updated_at DESC
                LIMIT 3
            """)
            sample_rows = await cursor.fetchall()

            for i, (key, user_id, value_json, created_at, updated_at) in enumerate(sample_rows, 1):
                print(f"  Record {i}:")
                print(f"    Key: {key}")
                print(f"    User ID: {user_id}")
                print(f"    Created: {created_at}")
                print(f"    Updated: {updated_at}")
                print(f"    Value (first 300 chars):")
                print(f"    {value_json[:300]}...")
                print()

    except Exception as e:
        print(f"❌ 检查数据库时出错: {e}")
        import traceback
        traceback.print_exc()


async def search_specific_key(db_path: str, search_key: str):
    """搜索特定的key"""
    print()
    print("=" * 70)
    print(f"🔍 搜索特定键: {search_key}")
    print("=" * 70)
    print()

    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("""
                SELECT key, user_id, value, created_at, updated_at
                FROM kv_storage
                WHERE key = ?
            """, (search_key,))

            row = await cursor.fetchone()

            if row:
                key, user_id, value_json, created_at, updated_at = row
                print(f"✅ 找到键: {key}")
                print(f"   User ID: {user_id}")
                print(f"   Created: {created_at}")
                print(f"   Updated: {updated_at}")
                print()

                try:
                    value_data = json.loads(value_json)
                    print("   完整数据:")
                    print(json.dumps(value_data, indent=2, ensure_ascii=False))
                except json.JSONDecodeError:
                    print("   原始数据 (不是有效的JSON):")
                    print(f"   {value_json}")
            else:
                print(f"❌ 未找到键: {search_key}")

                # Try fuzzy search
                cursor = await db.execute("""
                    SELECT key FROM kv_storage
                    WHERE key LIKE ?
                """, (f"%{search_key}%",))

                similar = await cursor.fetchall()
                if similar:
                    print()
                    print("   相似的键:")
                    for (similar_key,) in similar:
                        print(f"     - {similar_key}")

    except Exception as e:
        print(f"❌ 搜索失败: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description='检查 KV Storage 数据库内容')
    parser.add_argument(
        '--db',
        help='数据库文件路径 (如果不指定，从配置文件读取)'
    )
    parser.add_argument(
        '--key',
        help='搜索特定的key'
    )
    parser.add_argument(
        '--config',
        help='配置文件路径'
    )

    args = parser.parse_args()

    # Get database path
    if args.db:
        db_path = args.db
    else:
        if not CONFIG_SERVICE_AVAILABLE:
            print("ConfigService 不可用，请使用 --db 参数指定数据库路径")
            print()
            print("示例:")
            print("  python tests/debug/inspect_kv_storage.py --db base_app/data/databases/kv_storage.db")
            sys.exit(1)

        try:
            config_service = ConfigService(config_path=args.config)
            db_path = config_service.get_path("data.databases.kv")
            print(f"从配置文件读取数据库路径: {db_path}")
            print()
        except Exception as e:
            print(f"无法从配置读取数据库路径: {e}")
            print("请使用 --db 参数指定数据库路径")
            sys.exit(1)

    # Run inspection
    await inspect_database(str(db_path))

    # Search specific key if provided
    if args.key:
        await search_specific_key(str(db_path), args.key)


if __name__ == "__main__":
    asyncio.run(main())
