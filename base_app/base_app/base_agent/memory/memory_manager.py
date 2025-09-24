"""
Memory Manager for BaseAgent
Provides simple key-value storage with temporary and persistent memory support
Includes optional long-term memory using mem0
"""

import logging
from typing import Any, Dict, Optional, Set, List

from .mem0_memory import Mem0Memory
from .sqlite_kv_storage import SQLiteKVStorage

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Memory manager for BaseAgent
    
    Provides three types of storage:
    - variables: temporary storage (cleared on restart)
    - long_term_memory: intelligent persistent storage using mem0 (optional)
    - kv_storage: simple persistent key-value storage using SQLite
    """
    
    def __init__(
        self,
        enable_long_term_memory: bool = False,
        enable_kv_storage: bool = True,
        user_id: Optional[str] = None,
        mem0_config: Optional[Dict[str, Any]] = None,
        kv_storage_path: Optional[str] = None,
        config_service=None
    ):
        """
        Initialize the memory manager

        Args:
            enable_long_term_memory: Whether to enable mem0 long-term memory (local version)
            enable_kv_storage: Whether to enable SQLite KV storage
            user_id: User ID for memory isolation
            mem0_config: Custom configuration for mem0 (vector store, LLM, etc.)
            kv_storage_path: Path for SQLite KV database
            config_service: 配置服务实例
        """
        self.variables: Dict[str, Any] = {}  # Temporary variables
        self.user_id = user_id or "default"
        self.config_service = config_service

        # Long-term memory (optional, local version)
        self.long_term_memory: Optional[Mem0Memory] = None
        if enable_long_term_memory:
            try:
                self.long_term_memory = Mem0Memory(
                    user_id=user_id,
                    config=mem0_config,
                    config_service=config_service
                )
                logger.info("Long-term memory (mem0 local) enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize long-term memory: {e}")

        # KV Storage (SQLite-based persistent storage)
        self.kv_storage: Optional[SQLiteKVStorage] = None
        if enable_kv_storage and config_service:
            try:
                # 使用配置服务
                self.kv_storage = SQLiteKVStorage(config_service=config_service)
                logger.info("KV storage (SQLite) enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize KV storage: {e}")
        
        logger.debug("MemoryManager initialized")
    
    async def store_memory(
        self, 
        key: str, 
        value: Any
    ) -> None:
        """
        Store data in temporary memory
        
        Args:
            key: Storage key
            value: Value to store
            
        Note:
            All data is stored as temporary variables. For persistent storage,
            use the long-term memory methods (add_long_term_memory).
        """
        self.variables[key] = value
        logger.debug(f"Stored temporary variable: {key}")
    
    async def get_memory(self, key: str, default: Any = None) -> Any:
        """
        Get data from temporary memory
        
        Args:
            key: Storage key
            default: Default value if key not found
            
        Returns:
            Stored value or default
            
        Note:
            Only searches temporary variables. For persistent data,
            use long-term memory search methods.
        """
        if key in self.variables:
            logger.debug(f"Retrieved from variables: {key}")
            return self.variables[key]
        
        logger.debug(f"Key not found, returning default: {key}")
        return default
    
    async def delete_memory(self, key: str) -> bool:
        """
        Delete data from temporary memory
        
        Args:
            key: Storage key to delete
            
        Returns:
            True if key was found and deleted, False otherwise
        """
        if key in self.variables:
            del self.variables[key]
            logger.debug(f"Deleted from variables: {key}")
            return True
        
        logger.debug(f"Key not found for deletion: {key}")
        return False
    
    async def clear_memory(self) -> None:
        """
        Clear all temporary memory
        
        Note:
            This only clears temporary variables. To clear persistent data,
            use clear_long_term_memory() method.
        """
        variables_count = len(self.variables)
        self.variables.clear()
        logger.info(f"Cleared {variables_count} temporary variables")
    
    def list_keys(self) -> Set[str]:
        """
        List all keys in temporary memory
        
        Returns:
            Set of variable keys
            
        Note:
            This only lists temporary variables. For persistent data,
            use get_all_long_term_memories() method.
        """
        return set(self.variables.keys())
    
    def get_memory_stats(self) -> Dict[str, int]:
        """
        Get memory usage statistics
        
        Returns:
            Dictionary with memory statistics
        """
        return {
            "variables_count": len(self.variables),
            "long_term_memory_enabled": self.is_long_term_memory_enabled(),
            "kv_storage_enabled": self.is_kv_storage_enabled()
        }
    
    def has_key(self, key: str) -> bool:
        """
        Check if key exists in temporary variables
        
        Args:
            key: Key to check
            
        Returns:
            True if key exists, False otherwise
            
        Note:
            This only checks temporary variables. For persistent data,
            use search_long_term_memory() method.
        """
        return key in self.variables
    
    # ==================== Long-term Memory Methods ====================
    
    async def add_long_term_memory(
        self, 
        content: str, 
        user_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Add content to long-term memory
        
        Args:
            content: Memory content to store
            user_id: User ID (optional, uses default if not provided)
            
        Returns:
            Memory ID if successful, None otherwise
        """
        if not self.long_term_memory:
            logger.warning("Long-term memory not enabled")
            return None
        
        try:
            memory_id = await self.long_term_memory.add_memory(content, user_id)
            logger.info(f"Added long-term memory: {memory_id}")
            return memory_id
        except Exception as e:
            logger.error(f"Error adding long-term memory: {e}")
            return None
    
    async def search_long_term_memory(
        self, 
        query: str, 
        user_id: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search long-term memories using semantic search
        
        Args:
            query: Search query
            user_id: User ID (optional)
            limit: Maximum number of results
            
        Returns:
            List of relevant memories
        """
        if not self.long_term_memory:
            logger.warning("Long-term memory not enabled")
            return []
        
        try:
            results = await self.long_term_memory.search_memories(query, user_id, limit)
            logger.info(f"Found {len(results)} long-term memories for query: {query}")
            return results
        except Exception as e:
            logger.error(f"Error searching long-term memory: {e}")
            return []
    
    async def get_all_long_term_memories(
        self, 
        user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all long-term memories for a user
        
        Args:
            user_id: User ID (optional)
            
        Returns:
            List of memories
        """
        if not self.long_term_memory:
            logger.warning("Long-term memory not enabled")
            return []
        
        try:
            results = await self.long_term_memory.get_all_memories(user_id)
            logger.info(f"Retrieved {len(results)} long-term memories")
            return results
        except Exception as e:
            logger.error(f"Error getting long-term memories: {e}")
            return []
    
    async def delete_long_term_memory(self, memory_id: str) -> bool:
        """
        Delete a specific long-term memory
        
        Args:
            memory_id: Memory ID to delete
            
        Returns:
            True if deleted successfully
        """
        if not self.long_term_memory:
            logger.warning("Long-term memory not enabled")
            return False
        
        try:
            success = await self.long_term_memory.delete_memory(memory_id)
            if success:
                logger.info(f"Deleted long-term memory: {memory_id}")
            return success
        except Exception as e:
            logger.error(f"Error deleting long-term memory: {e}")
            return False
    
    async def clear_long_term_memory(self, user_id: Optional[str] = None) -> bool:
        """
        Clear all long-term memories for a user
        
        Args:
            user_id: User ID (optional)
            
        Returns:
            True if cleared successfully
        """
        if not self.long_term_memory:
            logger.warning("Long-term memory not enabled")
            return False
        
        try:
            success = await self.long_term_memory.delete_all_memories(user_id)
            if success:
                logger.info("Cleared all long-term memories")
            return success
        except Exception as e:
            logger.error(f"Error clearing long-term memory: {e}")
            return False
    
    def is_long_term_memory_enabled(self) -> bool:
        """Check if long-term memory is enabled"""
        return self.long_term_memory is not None
    
    def set_user_id(self, user_id: str) -> None:
        """Set user ID for long-term memory"""
        if self.long_term_memory:
            self.long_term_memory.set_user_id(user_id)
            logger.info(f"Set user ID for long-term memory: {user_id}")
    
    def get_user_id(self) -> Optional[str]:
        """Get current user ID for long-term memory"""
        if self.long_term_memory:
            return self.long_term_memory.get_user_id()
        return self.user_id
    
    # ==================== KV Storage Methods ====================
    
    async def set_data(
        self, 
        key: str, 
        value: Any, 
        user_id: Optional[str] = None
    ) -> bool:
        """
        Store data in persistent KV storage
        
        Args:
            key: Storage key
            value: Value to store
            user_id: User ID (optional, uses default if not provided)
            
        Returns:
            True if stored successfully
        """
        if not self.kv_storage:
            logger.warning("KV storage not enabled")
            return False
        
        try:
            user_id = user_id or self.user_id
            success = await self.kv_storage.set(key, value, user_id)
            if success:
                logger.info(f"Stored data in KV storage: {key}")
            return success
        except Exception as e:
            logger.error(f"Error storing data in KV storage: {e}")
            return False
    
    async def get_data(
        self, 
        key: str, 
        default: Any = None,
        user_id: Optional[str] = None
    ) -> Any:
        """
        Retrieve data from persistent KV storage
        
        Args:
            key: Storage key
            default: Default value if key not found
            user_id: User ID (optional, uses default if not provided)
            
        Returns:
            Stored value or default
        """
        if not self.kv_storage:
            logger.warning("KV storage not enabled")
            return default
        
        try:
            user_id = user_id or self.user_id
            value = await self.kv_storage.get(key, user_id, default)
            if value is not default:
                logger.info(f"Retrieved data from KV storage: {key}")
            else:
                logger.debug(f"Key not found in KV storage: {key}")
            return value
        except Exception as e:
            logger.error(f"Error retrieving data from KV storage: {e}")
            return default
    
    async def delete_data(
        self, 
        key: str, 
        user_id: Optional[str] = None
    ) -> bool:
        """
        Delete data from persistent KV storage
        
        Args:
            key: Storage key to delete
            user_id: User ID (optional, uses default if not provided)
            
        Returns:
            True if deleted successfully
        """
        if not self.kv_storage:
            logger.warning("KV storage not enabled")
            return False
        
        try:
            user_id = user_id or self.user_id
            success = await self.kv_storage.delete(key, user_id)
            if success:
                logger.info(f"Deleted data from KV storage: {key}")
            return success
        except Exception as e:
            logger.error(f"Error deleting data from KV storage: {e}")
            return False
    
    async def clear_all_data(self, user_id: Optional[str] = None) -> int:
        """
        Clear all data from persistent KV storage for a user
        
        Args:
            user_id: User ID (optional, uses default if not provided)
            
        Returns:
            Number of keys deleted
        """
        if not self.kv_storage:
            logger.warning("KV storage not enabled")
            return 0
        
        try:
            user_id = user_id or self.user_id
            count = await self.kv_storage.clear(user_id)
            if count > 0:
                logger.info(f"Cleared {count} items from KV storage")
            return count
        except Exception as e:
            logger.error(f"Error clearing KV storage: {e}")
            return 0
    
    async def list_data_keys(self, user_id: Optional[str] = None) -> List[str]:
        """
        List all keys in persistent KV storage for a user
        
        Args:
            user_id: User ID (optional, uses default if not provided)
            
        Returns:
            List of keys
        """
        if not self.kv_storage:
            logger.warning("KV storage not enabled")
            return []
        
        try:
            user_id = user_id or self.user_id
            keys = await self.kv_storage.keys(user_id)
            logger.info(f"Listed {len(keys)} keys from KV storage")
            return keys
        except Exception as e:
            logger.error(f"Error listing keys from KV storage: {e}")
            return []
    
    async def initialize_storage(self) -> None:
        """Initialize storage backends"""
        if self.kv_storage:
            try:
                await self.kv_storage.initialize()
                logger.info("KV storage initialized")
            except Exception as e:
                logger.error(f"Failed to initialize KV storage: {e}")
    
    def is_kv_storage_enabled(self) -> bool:
        """Check if KV storage is enabled"""
        return self.kv_storage is not None