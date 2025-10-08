#!/usr/bin/env python3
"""
Simple DOM extraction test - opens a URL and prints all DOM information
"""

import asyncio
import json
import os
import sys
from pprint import pprint
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../src'))

from browser_use.browser.session import BrowserSession
from browser_use.browser.profile import BrowserProfile
from browser_use import Tools
from browser_use.tools.views import GoToUrlAction
from browser_use.agent.views import ActionModel
from browser_use.dom.service import DomService
from base_app.base_app.base_agent.tools.browser_use.dom_extractor import (
    extract_dom_dict, extract_llm_view, format_dict_as_text, DOMExtractor
)
from base_app.base_app.server.core.config_service import ConfigService


class GoToUrlActionModel(ActionModel):
    go_to_url: GoToUrlAction | None = None


async def simple_dom_test():
    """Simple test: open URL and print DOM information"""

    print("=== Simple DOM Test ===")

    # Load configuration - ConfigService will automatically find config file
    try:
        config_service = ConfigService()
        print(f"Loaded config from: {config_service.config_path}")
    except FileNotFoundError:
        # If no config found, use default paths
        print("No config file found, using default configuration")
        config_service = None

    # Get browser user data directory
    if config_service:
        user_data_dir = str(config_service.get("data.browser_data", "~/claude/browser_data"))
        # Expand ~ in path
        user_data_dir = os.path.expanduser(user_data_dir)
    else:
        # Use default path
        user_data_dir = os.path.expanduser("~/claude/browser_data")

    print(f"User data directory: {user_data_dir}")
    
    # Create browser profile
    profile = BrowserProfile(
        headless=False,
        user_data_dir=user_data_dir,
        keep_alive=True,
        proxy=None,
    )
    
    browser_session = None
    
    try:
        print("Starting browser...")
        
        # Create browser session
        browser_session = BrowserSession(browser_profile=profile)
        await browser_session.start()
        
        # Create tools and DOM service
        tools = Tools()
        dom_service = DomService(browser_session)
        
        print("Browser started successfully!")
        
        # Navigate to Allegro coffee category page
        # test_url = "https://allegro.pl/kategoria/kawa-kawa-mielona-74033"
        # test_url = "https://allegro.pl/oferta/kawa-mielona-lavazza-qualita-oro-250g-17837534792"
        test_url = "http://baidu.com"
        print(f"Navigating to {test_url}...")
        
        goto_action = {'go_to_url': GoToUrlAction(url=test_url)}
        nav_result = await tools.act(
            action=GoToUrlActionModel(**goto_action),
            browser_session=browser_session
        )
        
        if nav_result.error:
            print(f"Navigation failed: {nav_result.error}")
            return
        
        print("Navigation successful!")

        # Wait for page to load using BrowserStateRequestEvent
        print("Waiting for page to load...")
        from browser_use.browser.events import BrowserStateRequestEvent
        event = browser_session.event_bus.dispatch(
            BrowserStateRequestEvent(
                include_dom=True,
                include_screenshot=False,
                include_recent_events=False
            )
        )
        browser_state = await event.event_result(raise_if_any=True, raise_if_none=False)
        print("✅ Page stability complete")

        # Get DOM information from DOMWatchdog cache
        print("\n=== Testing New DOM API ===")
        enhanced_dom_tree = browser_session._dom_watchdog.enhanced_dom_tree
        if enhanced_dom_tree is None:
            raise RuntimeError("DOM tree is None after BrowserStateRequestEvent - page may have failed to load")
        
        # Print current URL
        current_url = await browser_session.get_current_page_url()
        print(f"Current URL: {current_url}")
        
        # Test unified DOM extraction API
        print("\n" + "=" * 80)
        print("🔍 NEW DOM API TEST")
        print("=" * 80)
        
        # Create DOM extractor
        extractor = DOMExtractor()
        
        # Get visible elements DOM
        visible_dom, _ = extractor.serialize_accessible_elements_custom(enhanced_dom_tree, include_non_visible=False)
        
        # Extract visible elements as dictionary
        visible_dict = extract_dom_dict(visible_dom)
        
        # Count elements
        def count_elements(node, counts=None):
            if counts is None:
                counts = {"interactive": 0, "text": 0, "total": 0}
            
            if isinstance(node, dict):
                counts["total"] += 1
                if "interactive_index" in node:
                    counts["interactive"] += 1
                if node.get("tag") == "text":
                    counts["text"] += 1
                
                for child in node.get("children", []):
                    count_elements(child, counts)
            
            return counts
        
        element_counts = count_elements(visible_dict)
        
        print(f"\n📊 Visible Elements Summary:")
        print(f"   Total elements: {element_counts['total']}")
        print(f"   Interactive elements: {element_counts['interactive']}")
        print(f"   Text elements: {element_counts['text']}")
        
        # Show LLM view (meaningful elements only)
        llm_view = extract_llm_view(visible_dict)
        meaningful_elements = json.loads(llm_view) if llm_view != "[]" else []
        
        print(f"\n🤖 LLM View Summary:")
        print(f"   Meaningful elements: {len(meaningful_elements)}")
        print(f"   Compact JSON: {llm_view}")
        
        # Show first few meaningful elements in detail
        if meaningful_elements:
            print(f"\n📝 First 5 Meaningful Elements:")
            for i, element in enumerate(meaningful_elements[:5]):
                print(f"   [{i+1}] {element}")
        
        print("\n=== New DOM API test completed ===")
        
    except Exception as e:
        print(f"Test error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up
        if browser_session:
            try:
                await browser_session.stop()
                print("Browser session closed")
            except Exception as e:
                print(f"Error closing browser: {e}")


if __name__ == "__main__":
    print("Starting simple DOM test...")
    asyncio.run(simple_dom_test())
