"""Test MemoryToolkit query_page_operations."""
import asyncio
import sys
sys.path.insert(0, '/Users/shenyouren/workspace/2ami')

from src.clients.desktop_app.ami_daemon.base_agent.tools.toolkits.memory_toolkit import (
    MemoryToolkit,
)

# Configuration - update these with your actual values
API_BASE_URL = "http://localhost:9000"
API_KEY = "test_api_key"  # Replace with actual key
USER_ID = "test_user"

async def test_query_page_operations():
    """Test query_page_operations tool."""
    print("=" * 60)
    print("Test: MemoryToolkit.query_page_operations")
    print("=" * 60)
    
    toolkit = MemoryToolkit(
        memory_api_base_url=API_BASE_URL,
        ami_api_key=API_KEY,
        user_id=USER_ID,
    )
    
    print(f"Toolkit available: {toolkit.is_available()}")
    
    # Test with a sample URL
    test_url = "https://www.producthunt.com/"
    print(f"\nQuerying operations for: {test_url}")
    
    try:
        result = await toolkit.query_page_operations(test_url)
        print(f"\nResult:\n{result if result else '(no operations found)'}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

async def test_get_tools():
    """Test get_tools returns valid FunctionTool."""
    print("\n" + "=" * 60)
    print("Test: MemoryToolkit.get_tools")
    print("=" * 60)
    
    toolkit = MemoryToolkit(
        memory_api_base_url=API_BASE_URL,
        ami_api_key=API_KEY,
        user_id=USER_ID,
    )
    
    tools = toolkit.get_tools()
    print(f"Number of tools: {len(tools)}")
    
    for tool in tools:
        print(f"\nTool: {tool.name}")
        print(f"  Description: {tool.description[:80]}...")
        print(f"  Parameters: {tool.parameters}")
        print(f"  Function: {tool.func}")

async def main():
    print("MemoryToolkit Tests\n")
    
    await test_get_tools()
    await test_query_page_operations()
    
    print("\n" + "=" * 60)
    print("Tests completed")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
