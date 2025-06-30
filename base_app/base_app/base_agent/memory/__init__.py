"""
Memory management package for BaseAgent
Provides simple key-value storage with temporary and persistent memory support
Includes optional long-term memory using mem0
"""

from .memory_manager import MemoryManager
from .mem0_memory import Mem0Memory

__all__ = ["MemoryManager", "Mem0Memory"]