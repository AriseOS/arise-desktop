"""
Test CDP connection to existing Chrome browser
"""
import asyncio
from browser_use import Agent
from browser_use.browser.profile import BrowserProfile
from browser_use.llm import ChatOpenAI
import os

async def test_cdp():
    print("Testing CDP connection...")

    # Get API key from environment
    api_key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("Error: No API key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY")
        return

    # Create LLM
    llm = ChatOpenAI(
        model='gpt-4o',
        api_key=api_key
    )

    # Test 1: CDP connection with keep_alive
    print("\n=== Test 1: CDP with keep_alive ===")
    try:
        browser_profile = BrowserProfile(
            cdp_url='http://localhost:9222',
            headless=False,
            keep_alive=True,
            disable_security=True
        )

        agent = Agent(
            task='Go to example.com and get the page title',
            llm=llm,
            browser_profile=browser_profile,
            max_actions=5
        )

        result = await agent.run()
        print(f"✅ Test 1 Success: {result}")
    except Exception as e:
        print(f"❌ Test 1 Failed: {e}")
        import traceback
        traceback.print_exc()

    # Test 2: Without CDP (launch new browser)
    print("\n=== Test 2: Without CDP (new browser) ===")
    try:
        agent = Agent(
            task='Go to example.com and get the page title',
            llm=llm,
            max_actions=5
        )

        result = await agent.run()
        print(f"✅ Test 2 Success: {result}")
    except Exception as e:
        print(f"❌ Test 2 Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    print("Make sure Chrome is running with: --remote-debugging-port=9222")
    print("Starting tests...")
    asyncio.run(test_cdp())
