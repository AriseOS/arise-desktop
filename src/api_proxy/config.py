"""
API Proxy Configuration

Simple wrapper around ConfigService for backward compatibility
"""
from src.api_proxy.core.config_service import get_config as get_config_service


# Export get_config function for backward compatibility
def get_config():
    """Get configuration service instance"""
    return get_config_service()
