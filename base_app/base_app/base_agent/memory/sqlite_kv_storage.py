"""
SQLite KV Storage Implementation
Simple key-value storage using SQLite for persistent data storage
"""

import json
import aiosqlite
from datetime import datetime
from typing import Any, Dict, Optional, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class SQLiteKVStorage:
    """
    SQLite-based Key-Value storage for BaseAgent
    
    Simple KV operations with user-based data isolation
    """
    
    def __init__(self, database_path: str = "./data/agent_kv.db"):
        """Initialize SQLite KV storage"""
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Initialized SQLite KV storage at {self.database_path}")
    
    async def initialize(self):
        """Initialize database schema"""
        async with aiosqlite.connect(str(self.database_path)) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS kv_storage (
                    key TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    value TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (key, user_id)
                )
            """)
            
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_kv_user_id 
                ON kv_storage(user_id)
            """)
            
            await db.commit()
            logger.info(f"Initialized SQLite KV storage schema")
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        user_id: str = "default"
    ) -> bool:
        """
        Store a key-value pair
        
        Args:
            key: Storage key
            value: Value to store (will be JSON serialized)
            user_id: User ID for data isolation
            
        Returns:
            True if stored successfully
        """
        try:
            # JSON serialize the value
            serialized_value = json.dumps(value, ensure_ascii=False)
            now = datetime.now().isoformat()
            
            async with aiosqlite.connect(str(self.database_path)) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO kv_storage 
                    (key, user_id, value, created_at, updated_at)
                    VALUES (?, ?, ?, 
                            COALESCE((SELECT created_at FROM kv_storage WHERE key = ? AND user_id = ?), ?),
                            ?)
                """, (key, user_id, serialized_value, key, user_id, now, now))
                await db.commit()
                
            logger.debug(f"Stored KV pair: {user_id}:{key}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing KV pair {user_id}:{key}: {e}")
            return False
    
    async def get(
        self, 
        key: str, 
        user_id: str = "default", 
        default: Any = None
    ) -> Any:
        """
        Retrieve a value by key
        
        Args:
            key: Storage key
            user_id: User ID for data isolation
            default: Default value if key not found
            
        Returns:
            Stored value or default
        """
        try:
            async with aiosqlite.connect(str(self.database_path)) as db:
                cursor = await db.execute("""
                    SELECT value FROM kv_storage 
                    WHERE key = ? AND user_id = ?
                """, (key, user_id))
                
                row = await cursor.fetchone()
                if not row:
                    logger.debug(f"KV key not found: {user_id}:{key}")
                    return default
                
                # Deserialize JSON value
                value = json.loads(row[0])
                logger.debug(f"Retrieved KV pair: {user_id}:{key}")
                return value
                
        except Exception as e:
            logger.error(f"Error retrieving KV pair {user_id}:{key}: {e}")
            return default
    
    async def delete(self, key: str, user_id: str = "default") -> bool:
        """
        Delete a key-value pair
        
        Args:
            key: Storage key to delete
            user_id: User ID for data isolation
            
        Returns:
            True if deleted successfully
        """
        try:
            async with aiosqlite.connect(str(self.database_path)) as db:
                cursor = await db.execute("""
                    DELETE FROM kv_storage 
                    WHERE key = ? AND user_id = ?
                """, (key, user_id))
                await db.commit()
                
                success = cursor.rowcount > 0
                if success:
                    logger.debug(f"Deleted KV pair: {user_id}:{key}")
                return success
                
        except Exception as e:
            logger.error(f"Error deleting KV pair {user_id}:{key}: {e}")
            return False
    
    async def clear(self, user_id: str = "default") -> int:
        """
        Clear all data for a user
        
        Args:
            user_id: User ID to clear
            
        Returns:
            Number of keys deleted
        """
        try:
            async with aiosqlite.connect(str(self.database_path)) as db:
                cursor = await db.execute("""
                    DELETE FROM kv_storage WHERE user_id = ?
                """, (user_id,))
                await db.commit()
                
                count = cursor.rowcount
                logger.info(f"Cleared {count} KV pairs for user {user_id}")
                return count
                
        except Exception as e:
            logger.error(f"Error clearing data for user {user_id}: {e}")
            return 0
    
    async def keys(self, user_id: str = "default") -> List[str]:
        """
        List all keys for a user
        
        Args:
            user_id: User ID for data isolation
            
        Returns:
            List of keys
        """
        try:
            async with aiosqlite.connect(str(self.database_path)) as db:
                cursor = await db.execute("""
                    SELECT key FROM kv_storage 
                    WHERE user_id = ?
                    ORDER BY updated_at DESC
                """, (user_id,))
                
                rows = await cursor.fetchall()
                keys = [row[0] for row in rows]
                
                logger.debug(f"Listed {len(keys)} keys for user {user_id}")
                return keys
                
        except Exception as e:
            logger.error(f"Error listing keys for user {user_id}: {e}")
            return []