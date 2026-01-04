"""
Mem0 Long-term Memory Integration
Provides intelligent memory layer for BaseAgent using mem0 open-source version
"""

import logging
import os
from typing import Any, Dict, List, Optional, Union

try:
    from mem0 import AsyncMemory
except ImportError:
    AsyncMemory = None

# from mem0.configs.base import MemoryConfig


logger = logging.getLogger(__name__)


class Mem0Memory:
    """
    Long-term memory manager using mem0 open-source version
    
    Provides intelligent memory storage and retrieval with semantic search capabilities
    Runs locally without requiring API keys
    """
    
    def __init__(
        self,
        user_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        config_service=None
    ):
        """
        Initialize Mem0 memory client (local version)

        Args:
            user_id: Default user ID for memory operations
            config: Custom configuration for mem0 (vector store, LLM, etc.)
            config_service: 配置服务实例
        """
        if AsyncMemory is None:
            raise ImportError("mem0ai package is required. Install with: pip install mem0ai")

        self.user_id = user_id or "default_user"
        self.config_service = config_service

        # Default configuration for local deployment
        self.config = config or self._get_default_config()

        # Initialize local AsyncMemory client
        try:
            # self._client = AsyncMemory(config=self.config)
            self._client = AsyncMemory()
            logger.info("Initialized Mem0 local memory client")
        except Exception as e:
            logger.error(f"Failed to initialize Mem0 client: {e}")
            raise
    
    def _get_default_config(self) -> Dict[str, Any]:
        """
        Get default configuration for local mem0 deployment
        
        Returns:
            Default configuration dictionary
        """
        # Check for required environment variables
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        
        config = {
            "version": "v1.1"
        }
        
        # LLM configuration (required for mem0)
        if openai_api_key:
            config["llm"] = {
                "provider": "openai",
                "config": {
                    "api_key": openai_api_key,
                    "model": "gpt-4o-mini"  # Default efficient model
                }
            }
            
            # Embedder configuration 
            config["embedder"] = {
                "provider": "openai", 
                "config": {
                    "api_key": openai_api_key,
                    "model": "text-embedding-3-small"
                }
            }
        else:
            logger.warning("OPENAI_API_KEY not found. Mem0 requires an LLM to function.")
        
        # Vector store configuration
        if self.config_service:
            # 从配置服务获取路径
            chroma_path = str(self.config_service.get_path("data.chroma_db"))
        else:
            # 应该总是使用配置服务，这里只是为了防止异常
            chroma_path = "./data/chroma_db"

        config["vector_store"] = {
            "provider": "chroma",
            "config": {
                "collection_name": "mem0_collection",
                "path": chroma_path
            }
        }
        
        return config
    
    async def add_memory(
        self, 
        content: str, 
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Add a memory to long-term storage
        
        Args:
            content: Memory content (conversation or text)
            user_id: User ID (uses default if not provided)
            metadata: Additional metadata for the memory
            
        Returns:
            Memory ID
        """
        user_id = user_id or self.user_id
        
        # Format content as message for mem0
        messages = [{"role": "user", "content": content}]
        
        try:
            result = await self._client.add(
                messages=messages,
                user_id=user_id,
                metadata=metadata
            )
            
            # Extract memory ID from result
            if isinstance(result, dict):
                memory_id = result.get('id', result.get('memory_id', str(result)))
            elif isinstance(result, list) and len(result) > 0:
                memory_id = result[0].get('id', str(result[0]))
            else:
                memory_id = str(result)
            
            logger.info(f"Added memory for user {user_id}: {memory_id}")
            return memory_id
            
        except Exception as e:
            logger.error(f"Error adding memory to mem0: {e}")
            raise
    
    async def search_memories(
        self, 
        query: str, 
        user_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search memories using semantic search
        
        Args:
            query: Search query
            user_id: User ID (uses default if not provided)
            limit: Maximum number of results
            
        Returns:
            List of relevant memories
        """
        user_id = user_id or self.user_id
        
        try:
            result = await self._client.search(
                query=query,
                user_id=user_id,
                limit=limit
            )
            
            # Handle different result formats
            if isinstance(result, dict) and 'results' in result:
                results = result['results']
            elif isinstance(result, list):
                results = result
            else:
                results = []
            
            logger.info(f"Found {len(results)} memories for query: {query}")
            return results
            
        except Exception as e:
            logger.error(f"Error searching memories in mem0: {e}")
            return []
    
    async def get_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific memory by ID
        
        Args:
            memory_id: Memory ID
            
        Returns:
            Memory data or None if not found
        """
        try:
            result = await self._client.get(memory_id=memory_id)
            logger.info(f"Retrieved memory: {memory_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error getting memory from mem0: {e}")
            return None
    
    async def get_all_memories(
        self, 
        user_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get all memories for a user
        
        Args:
            user_id: User ID (uses default if not provided)
            limit: Maximum number of memories to retrieve
            
        Returns:
            List of memories
        """
        user_id = user_id or self.user_id
        
        try:
            results = await self._client.get_all(
                user_id=user_id,
                limit=limit
            )
            
            # Handle different result formats
            if isinstance(results, list):
                memories = results
            else:
                memories = []
            
            logger.info(f"Retrieved {len(memories)} memories for user {user_id}")
            return memories
            
        except Exception as e:
            logger.error(f"Error getting all memories from mem0: {e}")
            return []
    
    async def delete_memory(self, memory_id: str) -> bool:
        """
        Delete a specific memory
        
        Args:
            memory_id: Memory ID
            
        Returns:
            True if deleted successfully
        """
        try:
            await self._client.delete(memory_id=memory_id)
            logger.info(f"Deleted memory: {memory_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting memory from mem0: {e}")
            return False
    
    async def delete_all_memories(self, user_id: Optional[str] = None) -> bool:
        """
        Delete all memories for a user
        
        Args:
            user_id: User ID (uses default if not provided)
            
        Returns:
            True if deleted successfully
        """
        user_id = user_id or self.user_id
        
        try:
            await self._client.delete_all(user_id=user_id)
            logger.info(f"Deleted all memories for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting all memories from mem0: {e}")
            return False
    
    def set_user_id(self, user_id: str) -> None:
        """Set the default user ID"""
        self.user_id = user_id
        logger.debug(f"Set user ID to: {user_id}")
    
    def get_user_id(self) -> str:
        """Get the current user ID"""
        return self.user_id