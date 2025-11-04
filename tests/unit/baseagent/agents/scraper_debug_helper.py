#!/usr/bin/env python3
"""
ScraperAgent Debug Helper - DOM collection and script generation with Claude SDK

Usage:
  # Collect DOM data
  python scraper_debug_helper.py --mode dom --url "https://allegro.pl/oferta/some-product" --name "product_page"

  # Generate script using Claude Agent SDK (multi-turn iterative generation)
  python scraper_debug_helper.py --mode generate --name "product_page" --requirement-type product_detail

  # Execute generated script
  python scraper_debug_helper.py --mode exec --name "product_page" --requirement-type product_detail

  # List available data
  python scraper_debug_helper.py --mode list

The script uses Claude Agent SDK for iterative script generation and testing,
matching the new ScraperAgent implementation.
"""

import asyncio
import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../src'))

from base_app.base_app.server.core.config_service import ConfigService

# DOM collection imports
from browser_use.browser.session import BrowserSession
from browser_use.browser.profile import BrowserProfile
from browser_use import Tools
from browser_use.tools.views import GoToUrlAction, ScrollAction
from browser_use.agent.views import ActionModel
from browser_use.dom.service import DomService
from base_app.base_app.base_agent.tools.browser_use.dom_extractor import (
    extract_dom_dict, extract_llm_view, DOMExtractor
)

# Script generation imports
from common.llm import ClaudeAgentProvider


class GoToUrlActionModel(ActionModel):
    go_to_url: GoToUrlAction | None = None


class ScrollActionModel(ActionModel):
    scroll: ScrollAction | None = None


class ScraperDebugHelper:
    """Debug helper that uses ScraperAgent's exact logic"""

    def __init__(self, data_dir: str = None, config_service=None):
        if config_service:
            # Use config service to get data directory
            self.data_dir = config_service.get_path("data.debug")
            self.config_service = config_service
        else:
            # Load test configuration
            test_config_path = Path(__file__).parent.parent.parent.parent / "test_config.yaml"
            self.config_service = ConfigService(config_path=str(test_config_path))
            self.data_dir = self.config_service.get_path("data.debug")
        
        # Default data requirements from test_scraper_agent_with_script.py
        self.default_data_requirements = {
            "product_detail": {
                "user_description": "从商品详情页面提取基本商品信息，用于价格监控和商品分析",
                "output_format": {
                    "product_name": "完整的商品名称",
                    "price": "商品总价格（包含货币符号，不是单价）",
                    "sales_count_30d": "最近30天销售数量"
                },
                "sample_data": [{
                    "product_name": "Kawa mielona 100% Arabica Świeżo palona Brazylia Santos 250g",
                    "price": "25,00 zł",
                    "sales_count_30d": "323"
                }]
            },
            "product_list": {
                "user_description": "从商品列表页面提取多个商品的关键信息，重点获取商品链接以便后续处理",
                "output_format": {
                    "product_name": "商品名称",
                    "price": "商品价格",
                    "href": "商品详情页链接（完整URL）",
                    "seller_name": "卖家名称"
                },
                "sample_data": []
            },
            "url_list": {
                "user_description": "提取页面中所有商品的URL链接",
                "output_format": {
                    "url": "商品详情页完整URL"
                },
                "sample_data": [
                    {"url": "https://allegro.pl/oferta/example-product-123"}
                ]
            },
            "workflow_url_list": {
                "user_description": "Extract all coffee product URLs from the product listing",
                "output_format": {
                    "url": "Product URL"
                },
                "sample_data": [
                    {"url": "https://allegro.pl/oferta/kawa-ziarnista-1kg-brazylia-santos-swiezo-palona-100-arabica-tommy-cafe-12786896326"},
                    {"url": "https://allegro.pl/oferta/example-product-2"}
                ]
            },
            # Workflow Scenario 3: Allegro product detail extraction (converted from LLM to script mode for testing)
            "allegro_product_detail": {
                "user_description": "Extract coffee product details including name, price, and purchase statistics",
                "output_format": {
                    "title": "Product title",
                    "price": "Product price",
                    "purchases": "Number of recent purchases"
                },
                "sample_data": {
                    "title": "Kawa ziarnista 1kg BRAZYLIA Santos Świeżo Palona 100% ARABICA Tommy Cafe",
                    "price": "69,50 zł",
                    "purchases": "3 308 osób kupiło ostatnio"
                },
                "xpath_hints": {
                    "title": "//*[@id=\"showproduct-left-column-wrapper\"]/div/div[1]/div/div/div/div/div/div[1]/div/div/div[1]/div/h1",
                    "price": "//*[@id=\"showproduct-right-column-wrapper\"]/div/div[1]/div/div/div[2]/div/div/div/div/div/section/div[1]/div[1]",
                    "purchases": "//*[@id=\"showproduct-left-column-wrapper\"]/div/div[1]/div/div/div/div/div/div[1]/div/div/div[1]/div/div[2]/div/div[1]/div/div[2]"
                }
            },
            # Workflow Scenario 4: Amazon product detail extraction (converted from LLM to script mode for testing)
            "amazon_product_detail": {
                "user_description": "Extract coffee product information including product name and customer ratings",
                "output_format": {
                    "title": "Product title",
                    "ratings": "Customer ratings count"
                },
                "sample_data": {
                    "title": "Lavazza House Blend Perfetto Ground Coffee 12oz Bag, Medium Roast, Full-bodied, Intensity 3/5, 100% Arabica, Ideal for Drip Brewers, (Pack of 1) - Package May Vary",
                    "ratings": "8,168 ratings"
                },
                "xpath_hints": {
                    "title": "//*[@id=\"productTitle\"]",
                    "ratings": "//*[@id=\"acrCustomerReviewText\"]"
                }
            }
        }
    
    async def collect_dom(self, url: str, name: str):
        """Collect DOM data from URL and save directly to workspace for Claude SDK

        This creates a workspace directory with:
        - dom_data.json: DOM structure in dict format (for Claude to explore)
        - metadata.json: URL, collection time, and other metadata
        """

        print(f"=== DOM Collection for '{name}' ===")
        print(f"URL: {url}")

        # Create workspace directory
        import hashlib
        workspace_key = f"dom_{name}_{hashlib.md5(url.encode()).hexdigest()[:8]}"
        workspace_dir = self.data_dir / "workspaces" / workspace_key
        workspace_dir.mkdir(parents=True, exist_ok=True)

        print(f"📁 Workspace: {workspace_dir}")

        # Browser setup - get user data dir from config
        user_data_dir = str(self.config_service.get_path("data.browser_data"))

        profile = BrowserProfile(
            headless=False,
            user_data_dir=user_data_dir,
            keep_alive=True,
            minimum_wait_page_load_time=2.0,
            wait_for_network_idle_page_load_time=3.0,
        )

        browser_session = None

        try:
            print("Starting browser...")
            browser_session = BrowserSession(browser_profile=profile)
            await browser_session.start()

            tools = Tools()

            # Navigate
            print(f"Navigating to {url}...")
            goto_action = {'go_to_url': GoToUrlAction(url=url)}
            nav_result = await tools.act(
                action=GoToUrlActionModel(**goto_action),
                browser_session=browser_session
            )

            if nav_result.error:
                print(f"Navigation failed: {nav_result.error}")
                return False

            # Wait for page to fully load
            print("Waiting 5 seconds for page to fully load...")
            await asyncio.sleep(5)

            # Wait for page stability
            print("Waiting for page stability...")
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

            # Extract DOM
            print("Extracting DOM data...")
            enhanced_dom = browser_session._dom_watchdog.enhanced_dom_tree
            if enhanced_dom is None:
                raise RuntimeError("DOM tree is None - page may have failed to load")

            current_url = await browser_session.get_current_page_url()

            # Use ScraperAgent's DOM extraction logic
            extractor = DOMExtractor()

            # Get full DOM (all elements - used for script generation)
            full_dom, _ = extractor.serialize_accessible_elements_custom(
                enhanced_dom, include_non_visible=True
            )

            # Convert to dict format (this is what Claude SDK will use)
            dom_dict = extract_dom_dict(full_dom)

            print(f"📊 DOM dict size: {len(json.dumps(dom_dict))} chars")

            # Save DOM data to workspace
            dom_file = workspace_dir / "dom_data.json"
            with open(dom_file, 'w', encoding='utf-8') as f:
                json.dump(dom_dict, f, indent=2, ensure_ascii=False)

            print(f"✅ DOM data saved: {dom_file.name} ({dom_file.stat().st_size} bytes)")

            # Save metadata
            metadata = {
                "name": name,
                "url": url,
                "current_url": current_url,
                "collection_time": datetime.now().isoformat(),
                "workspace_key": workspace_key,
                "dom_scope": "full"  # Always use full for generation to capture all fields
            }

            metadata_file = workspace_dir / "metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            print(f"✅ Metadata saved: {metadata_file.name}")

            print(f"\n📦 Workspace ready for script generation:")
            print(f"   Location: {workspace_dir}")
            print(f"   Files: dom_data.json, metadata.json")

            return True

        except Exception as e:
            print(f"❌ DOM collection error: {e}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            if browser_session:
                try:
                    await browser_session.stop()
                    print("Browser session closed")
                except Exception as e:
                    print(f"Error closing browser: {e}")
    
    async def generate_script_with_claude_sdk(self, name: str, requirement_type: str = "product_detail"):
        """Generate script using Claude Agent SDK

        Reads DOM data from workspace and generates script with iterative testing.
        """
        print(f"=== Script Generation with Claude SDK for '{name}' ===")
        print(f"Requirement type: {requirement_type}")
        print(f"🤖 Using Claude Agent SDK for iterative generation and testing")

        # Find workspace for this name
        workspaces_dir = self.data_dir / "workspaces"
        if not workspaces_dir.exists():
            print(f"❌ No workspaces found. Run --mode dom first.")
            return False

        # Find matching workspace
        workspace_pattern = f"dom_{name}_*"
        matching_workspaces = list(workspaces_dir.glob(workspace_pattern))

        if not matching_workspaces:
            print(f"❌ No workspace found for '{name}'")
            print(f"   Searched for: {workspace_pattern}")
            print(f"   In directory: {workspaces_dir}")
            print(f"\nAvailable workspaces:")
            for ws in workspaces_dir.iterdir():
                if ws.is_dir():
                    print(f"   - {ws.name}")
            return False

        # Use the most recent workspace
        workspace_dir = sorted(matching_workspaces)[-1]
        print(f"📁 Using workspace: {workspace_dir.name}")

        # Check required files
        dom_file = workspace_dir / "dom_data.json"
        metadata_file = workspace_dir / "metadata.json"

        if not dom_file.exists():
            print(f"❌ dom_data.json not found in workspace")
            return False

        try:
            # Load DOM data
            with open(dom_file, 'r', encoding='utf-8') as f:
                dom_dict = json.load(f)

            print(f"✅ Loaded DOM data: {len(json.dumps(dom_dict))} chars")

            # Load metadata if available
            if metadata_file.exists():
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                print(f"✅ Loaded metadata: {metadata.get('url', 'N/A')}")

            # Get data requirements
            if requirement_type not in self.default_data_requirements:
                print(f"❌ Unknown requirement type: {requirement_type}")
                print(f"Available types: {list(self.default_data_requirements.keys())}")
                return False

            data_requirements = self.default_data_requirements[requirement_type]

            # Create script generation workspace in the same directory
            print(f"📝 Adding requirement.json to workspace...")

            requirement_file = workspace_dir / "requirement.json"
            requirement_file.write_text(
                json.dumps(data_requirements, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )

            print(f"✅ Requirement file saved: {requirement_file.stat().st_size} bytes")

            # Build Claude SDK prompt (same as ScraperAgent)
            user_description = data_requirements.get('user_description', '')
            output_format = data_requirements.get('output_format', {})
            sample_data = data_requirements.get('sample_data', [])
            xpath_hints = data_requirements.get('xpath_hints', {})

            fields_description = "\n".join([f"- {name}: {desc}" for name, desc in output_format.items()])

            sample_description = ""
            if sample_data:
                sample_description = f"\n\nExpected output example:\n{json.dumps(sample_data, indent=2, ensure_ascii=False)}"

            xpath_hints_description = ""
            if xpath_hints:
                hints_list = "\n".join([f"- {name}: {xpath}" for name, xpath in xpath_hints.items()])
                xpath_hints_description = f"\n\nXPath hints from user demo (reference only):\n{hints_list}"

            prompt = f"""# Web Scraping Script Generation Task

## Working Directory Structure

You are working in: `{workspace_dir}`

**Files available:**
- `requirement.json` - Data extraction requirements
- `dom_data.json` - DOM structure of the webpage (JSON format)

**Files to create:**
- `extraction_script.py` - Main extraction script

## Task Overview

Generate a Python script that extracts data from a webpage DOM structure according to user requirements.

## Step 1: Read Input Files

First, read the input files to understand the requirements:
- Read `requirement.json` to see what data needs to be extracted
- Read `dom_data.json` to understand the webpage structure (use Grep/Read tools to explore)

## Step 2: Understand DOM Structure

The DOM data is in JSON format with this structure:
```python
{{
    "tag": "div",           # HTML tag name
    "text": "content",      # Text content
    "class": "item",        # CSS class
    "href": "url",          # Link URL
    "xpath": "/html/...",   # XPath location
    "children": [...]       # Nested children
}}
```

Use Grep to search for specific patterns in dom_data.json, for example:
- Search for class names: grep -i '"class".*product' dom_data.json
- Search for specific tags: grep -i '"tag".*"h2"' dom_data.json

## Step 3: Data Extraction Requirements

**User Description:** {user_description}

**Fields to extract:**
{fields_description}{sample_description}{xpath_hints_description}

## Step 4: Generate extraction_script.py

Create a file named `extraction_script.py` with this function:

```python
def extract_data_from_page(serialized_dom, dom_dict) -> List[Dict[str, Any]]:
    \"\"\"
    Extract data from DOM structure

    Args:
        serialized_dom: SerializedDOMTree object (browser-use library)
        dom_dict: DOM structure as nested dictionary

    Returns:
        List of dictionaries, each containing extracted fields
    \"\"\"
    # Your implementation here
    pass
```

**Requirements:**
1. Function must be named `extract_data_from_page`
2. Parameters: `serialized_dom` and `dom_dict`
3. Return type: `List[Dict[str, Any]]`
4. Include proper error handling
5. Use recursive traversal of dom_dict to find target elements
6. Handle cases where elements might not exist

**CRITICAL - Code Robustness Requirements:**

⚠️ **DO NOT hardcode numeric thresholds or specific values that depend on sample data:**

❌ **BAD Examples (overfitting to sample data):**
```python
# DON'T hardcode text length limits based on sample
if len(text) > 50:  # ❌ Assumes description is always long

# DON'T hardcode minimum element counts based on sample
if len(a_tags) >= 3:  # ❌ Assumes always have 3+ links

# DON'T hardcode specific domain names from sample
if 'tobenone.com' in href:  # ❌ Only works for one website

# DON'T hardcode specific city/country names from sample
if any(keyword in text for keyword in ['Hong Kong', 'USA']):  # ❌ Misses other locations
```

✅ **GOOD Examples (generic and flexible):**
```python
# Use flexible text matching
if text and text.strip():  # ✅ Any non-empty text

# Accept any number of elements
for a_tag in a_tags:  # ✅ Works with 1 or many links

# Use general patterns
if 'http' in href or any(domain in href for domain in ['facebook', 'twitter', 'instagram', 'youtube']):  # ✅ Generic patterns

# Use structural patterns for location
if ',' in text and len(text) < 100:  # ✅ Matches "City, Country" pattern
```

**Key Principles:**
1. **sample_data is just ONE example** - your script must work for OTHER pages with DIFFERENT content
2. **Avoid magic numbers** - text lengths, element counts, specific values vary across pages
3. **Use structural patterns** - look for class names, tag structures, not specific text values
4. **Be permissive, not restrictive** - prefer "accept if exists" over "reject if doesn't match exact criteria"

**Common patterns:**
- For list extraction: Find repeating container elements, extract fields from each
- For single item: Navigate to specific element and extract fields
- Use XPath hints as reference, but adapt to actual DOM structure

## Step 5: Test and Validate

After generating the script:
1. Create a test file `test_script.py` that:
   - Loads dom_data.json
   - Calls extract_data_from_page() with the DOM data
   - Validates output format matches requirements
   - Prints extracted data

2. Run the test: `python test_script.py`

3. If errors occur:
   - Analyze the error message
   - Fix the extraction_script.py
   - Re-run the test
   - Repeat until test passes

## Step 6: Final Verification

Ensure:
- extraction_script.py exists and is syntactically correct
- Test passes without errors
- Output data matches expected format from requirement.json

---

**Important Notes:**
- This is a sample page - the script should work on pages with similar structure but different content
- Use flexible selectors (class names, patterns) rather than hardcoded values
- Handle missing elements gracefully (return empty list or skip items)
- The DOM structure in dom_data.json represents the actual webpage HTML structure

Start by reading requirement.json and dom_data.json to understand the task!
"""

            # Initialize Claude Agent Provider
            print("🚀 Initializing Claude Agent SDK...")
            claude_provider = ClaudeAgentProvider(config_service=self.config_service)

            # Run Claude SDK
            max_iterations = self.config_service.get("claude_agent.default_max_iterations", 50)
            print(f"🔄 Running Claude SDK (max {max_iterations} iterations)...")

            result = await claude_provider.run_task(
                prompt=prompt,
                working_dir=workspace_dir,
                max_iterations=max_iterations
            )

            # Check result
            if not result.success:
                error_msg = f"Claude SDK failed after {result.iterations} iterations: {result.error}"
                print(f"❌ {error_msg}")
                return False

            print(f"✅ Claude SDK completed successfully in {result.iterations} iterations")

            # Read generated script
            script_file = workspace_dir / "extraction_script.py"
            if not script_file.exists():
                print(f"❌ extraction_script.py not found in {workspace_dir}")
                return False

            script_content = script_file.read_text(encoding='utf-8')
            print(f"✅ Script loaded: {len(script_content)} chars")

            # Update metadata with generation info
            if metadata_file.exists():
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            else:
                metadata = {}

            metadata.update({
                "script_generated": True,
                "generation_time": datetime.now().isoformat(),
                "requirement_type": requirement_type,
                "iterations": result.iterations
            })

            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            # Print summary
            print("\n" + "=" * 80)
            print("📊 GENERATION SUMMARY")
            print("=" * 80)
            print(f"✅ Success: {result.success}")
            print(f"🔄 Iterations: {result.iterations}")
            print(f"📁 Workspace: {workspace_dir}")
            print(f"📝 Files generated:")
            print(f"   - extraction_script.py")
            print(f"   - test_script.py (if created by Claude)")
            print(f"   - requirement.json")
            print(f"   - metadata.json (updated)")
            print(f"\n💡 To execute: python scraper_debug_helper.py --mode exec --name {name} --requirement-type {requirement_type}")

            return True

        except Exception as e:
            print(f"❌ Claude SDK generation error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def list_data(self):
        """List available workspaces and their status"""
        print("=== Available Workspaces ===")

        workspaces_dir = self.data_dir / "workspaces"
        if not workspaces_dir.exists():
            print("No workspaces found. Use --mode dom to collect DOM data first.")
            return

        workspaces = list(workspaces_dir.glob("dom_*"))

        if not workspaces:
            print("No workspaces found. Use --mode dom to collect DOM data first.")
            return

        print(f"\n📁 Found {len(workspaces)} workspace(s):\n")

        for workspace in sorted(workspaces):
            metadata_file = workspace / "metadata.json"
            dom_file = workspace / "dom_data.json"
            script_file = workspace / "extraction_script.py"
            requirement_file = workspace / "requirement.json"

            # Parse name from workspace key
            parts = workspace.name.split('_')
            name = parts[1] if len(parts) > 1 else "unknown"

            print(f"  📦 {name} ({workspace.name})")

            # Read metadata
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    print(f"     URL: {metadata.get('url', 'N/A')}")
                    print(f"     Collected: {metadata.get('collection_time', 'N/A')[:19]}")

                    if metadata.get('script_generated'):
                        print(f"     ✅ Script generated ({metadata.get('iterations', '?')} iterations)")
                        print(f"        Type: {metadata.get('requirement_type', 'N/A')}")
                        print(f"        Time: {metadata.get('generation_time', 'N/A')[:19]}")
                    else:
                        print(f"     ⏳ No script generated yet")
                except Exception as e:
                    print(f"     ⚠️  Error reading metadata: {e}")

            # Check files
            files_status = []
            if dom_file.exists():
                files_status.append("dom_data.json")
            if requirement_file.exists():
                files_status.append("requirement.json")
            if script_file.exists():
                files_status.append("extraction_script.py")

            if files_status:
                print(f"     Files: {', '.join(files_status)}")

            print()

        print(f"📋 Available requirement types:")
        for req_type, req_data in self.default_data_requirements.items():
            print(f"  • {req_type}: {req_data['user_description']}")
    
    async def execute_script(self, name: str, script_file_path: str = None, requirement_type: str = "product_detail", dom_scope: str = "partial", max_items: int = 0):
        """Execute a generated script from workspace"""

        print(f"=== Script Execution for '{name}' ===")
        print(f"Max items: {max_items if max_items > 0 else 'unlimited'}")

        # Find workspace
        if script_file_path:
            script_file = Path(script_file_path)
            workspace_dir = script_file.parent
        else:
            workspaces_dir = self.data_dir / "workspaces"
            workspace_pattern = f"dom_{name}_*"
            matching_workspaces = list(workspaces_dir.glob(workspace_pattern))

            if not matching_workspaces:
                print(f"❌ No workspace found for '{name}'")
                return False

            workspace_dir = sorted(matching_workspaces)[-1]
            script_file = workspace_dir / "extraction_script.py"

        print(f"📁 Workspace: {workspace_dir.name}")

        # Check files exist
        dom_file = workspace_dir / "dom_data.json"

        if not script_file.exists():
            print(f"❌ Script not found: {script_file}")
            print(f"   Run --mode generate first")
            return False

        if not dom_file.exists():
            print(f"❌ DOM data not found: {dom_file}")
            return False

        try:
            # Load data
            with open(dom_file, 'r', encoding='utf-8') as f:
                dom_dict = json.load(f)

            with open(script_file, 'r', encoding='utf-8') as f:
                script_content = f.read()

            print(f"✅ Loaded files")
            print(f"🚀 Executing script...")

            # Execute
            script_namespace = globals().copy()
            exec(script_content, script_namespace, script_namespace)

            extract_data_from_page = script_namespace.get('extract_data_from_page')
            if not extract_data_from_page:
                print("❌ Missing extract_data_from_page function")
                return False

            result_data = extract_data_from_page(None, dom_dict)

            # Format result
            if isinstance(result_data, list):
                limited_data = result_data[:max_items] if max_items > 0 else result_data
                result = {"success": True, "data": limited_data, "total_count": len(limited_data), "error": None}
            else:
                result = {"success": True, "data": result_data, "total_count": 1 if result_data else 0, "error": None}

            # Display results
            print("\n" + "=" * 60)
            print("📊 EXECUTION RESULTS")
            print("=" * 60)

            if result.get("success"):
                print(f"✅ Success: {result['total_count']} items extracted")
                if result['data']:
                    print(f"\n📋 Sample data (first 3 items):")
                    for i, item in enumerate(result['data'][:3], 1):
                        print(f"[{i}] {json.dumps(item, indent=2, ensure_ascii=False)}")
                    if len(result['data']) > 3:
                        print(f"... and {len(result['data']) - 3} more items")

            print(f"\n📄 Full result:")
            print(json.dumps(result, indent=2, ensure_ascii=False))

            return result.get("success", False)

        except Exception as e:
            print(f"❌ Execution failed: {e}")
            import traceback
            traceback.print_exc()
            return False




async def main():
    parser = argparse.ArgumentParser(description='ScraperAgent Debug Helper - Claude SDK Integration')
    parser.add_argument('--mode', choices=['dom', 'generate', 'exec', 'list'], required=True,
                       help='dom: collect DOM data, generate: create script with Claude SDK, exec: execute script, list: show data')
    parser.add_argument('--url', help='URL for DOM collection')
    parser.add_argument('--name', help='Test data name')
    parser.add_argument('--requirement-type', choices=['product_detail', 'product_list', 'url_list', 'workflow_url_list', 'allegro_product_detail', 'amazon_product_detail'],
                       default='product_detail', help='Type of data requirements to use')
    parser.add_argument('--dom-scope', choices=['partial', 'full'], default='partial',
                       help='DOM scope for script execution (generation always uses partial)')
    parser.add_argument('--script-file', help='Specific script file to execute (optional)')
    parser.add_argument('--max-items', type=int, default=0, help='Maximum items to extract (0 = unlimited)')

    args = parser.parse_args()

    helper = ScraperDebugHelper()

    if args.mode == 'list':
        helper.list_data()
        return

    if args.mode == 'dom':
        if not args.url or not args.name:
            print("❌ --url and --name required for DOM collection")
            return

        success = await helper.collect_dom(args.url, args.name)
        print("✅ DOM collection completed" if success else "❌ DOM collection failed")

    elif args.mode == 'generate':
        if not args.name:
            print("❌ --name required for script generation")
            return

        success = await helper.generate_script_with_claude_sdk(args.name, args.requirement_type)
        print("✅ Script generation completed" if success else "❌ Script generation failed")

    elif args.mode == 'exec':
        if not args.name:
            print("❌ --name required for script execution")
            return

        success = await helper.execute_script(
            args.name,
            args.script_file,
            args.requirement_type,
            args.dom_scope,
            args.max_items
        )
        print("✅ Script execution completed" if success else "❌ Script execution failed")


if __name__ == "__main__":
    asyncio.run(main())
