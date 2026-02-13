"""Test IntentSequence API endpoints."""
import asyncio
import httpx

# Configuration
API_BASE_URL = "http://localhost:9000"
API_KEY = "test_api_key"  # Replace with actual key if needed
USER_ID = "test_user"

async def test_query_action_by_url():
    """Test querying actions by URL."""
    print("=" * 60)
    print("Test 1: Query action by URL")
    print("=" * 60)
    
    # Use a sample URL - replace with an actual URL in your memory
    test_url = "https://www.producthunt.com/"
    
    payload = {
        "user_id": USER_ID,
        "current_state": test_url,
        "target": "",  # Empty for exploration mode
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_BASE_URL}/api/v1/memory/query",
                json=payload,
                headers={"X-Ami-API-Key": API_KEY},
                timeout=30.0,
            )
            print(f"Status: {response.status_code}")
            print(f"Response: {response.json()}")
            return response.status_code == 200
        except Exception as e:
            print(f"Error: {e}")
            return False

async def test_query_state_by_url():
    """Test the new /api/v1/memory/state endpoint."""
    print("\n" + "=" * 60)
    print("Test 2: Query state by URL (new endpoint)")
    print("=" * 60)
    
    test_url = "https://www.producthunt.com/"
    
    payload = {
        "user_id": USER_ID,
        "url": test_url,
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_BASE_URL}/api/v1/memory/state",
                json=payload,
                headers={"X-Ami-API-Key": API_KEY},
                timeout=30.0,
            )
            print(f"Status: {response.status_code}")
            data = response.json()
            print(f"Success: {data.get('success')}")
            if data.get('state'):
                print(f"State ID: {data['state'].get('id')}")
                print(f"State Description: {data['state'].get('description')}")
            if data.get('intent_sequences'):
                print(f"IntentSequences count: {len(data['intent_sequences'])}")
                for seq in data['intent_sequences'][:3]:
                    print(f"  - {seq.get('description', 'No description')}")
            return response.status_code == 200
        except Exception as e:
            print(f"Error: {e}")
            return False

async def test_health():
    """Test if server is running."""
    print("=" * 60)
    print("Test 0: Health check")
    print("=" * 60)
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_BASE_URL}/health", timeout=5.0)
            print(f"Status: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            print(f"Server not running: {e}")
            return False

async def main():
    print("IntentSequence API Tests\n")
    
    # Test 0: Health check
    if not await test_health():
        print("\n[ERROR] Server is not running. Please start the server first:")
        print("  uvicorn src.cloud_backend.main:app --reload")
        return
    
    # Test 1: Query action by URL
    await test_query_action_by_url()
    
    # Test 2: Query state by URL
    await test_query_state_by_url()
    
    print("\n" + "=" * 60)
    print("Tests completed")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
