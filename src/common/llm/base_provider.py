"""
Base LLM Provider abstract class
"""

from abc import ABC, abstractmethod
from typing import Optional


class BaseProvider(ABC):
    """
    Abstract base class for LLM providers
    """
    
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        """
        Initialize the provider
        
        Args:
            api_key: API key for the service
            model_name: Default model name to use
        """
        self.api_key = api_key
        self.model_name = model_name
        self._client = None
    
    @abstractmethod
    async def _initialize_client(self) -> None:
        """
        Initialize the specific SDK client
        Should be implemented by each provider
        """
        pass
    
    @abstractmethod
    async def generate_response(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> str:
        """
        Generate a response using the LLM
        
        Args:
            system_prompt: System instruction for the LLM
            user_prompt: User's input prompt
            
        Returns:
            Generated response text
        """
        pass
    
    def get_model_name(self) -> Optional[str]:
        """Get the current model name"""
        return self.model_name
    
    def set_model_name(self, model_name: str) -> None:
        """Set the model name"""
        self.model_name = model_name