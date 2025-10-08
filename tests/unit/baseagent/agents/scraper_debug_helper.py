#!/usr/bin/env python3
"""
ScraperAgent Debug Helper - DOM collection and script generation

Usage:
  # Collect DOM data
  python scraper_debug_helper.py --mode dom --url "https://allegro.pl/oferta/some-product" --name "product_page"

  # Generate script using ScraperAgent's logic
  python scraper_debug_helper.py --mode generate --name "product_page"

The script uses the exact same data_requirements format and LLM prompts as ScraperAgent.
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
from common.llm import AnthropicProvider


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
            }
        }
    
    async def collect_dom(self, url: str, name: str):
        """Collect DOM data from URL"""

        print(f"=== DOM Collection for '{name}' ===")
        print(f"URL: {url}")

        # Browser setup - get user data dir from config
        user_data_dir = str(self.config_service.get_path("data.browser_data"))
        
        profile = BrowserProfile(
            headless=False,
            user_data_dir=user_data_dir,
            keep_alive=True,
        )
        
        browser_session = None
        
        try:
            print("Starting browser...")
            browser_session = BrowserSession(browser_profile=profile)
            await browser_session.start()
            
            tools = Tools()
            dom_service = DomService(browser_session)
            
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

            # Wait for page stability using BrowserStateRequestEvent (same as ScraperAgent fix)
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

            # Extract DOM (same as ScraperAgent) - use DOMWatchdog cache
            print("Extracting DOM data...")
            enhanced_dom = browser_session._dom_watchdog.enhanced_dom_tree
            if enhanced_dom is None:
                raise RuntimeError("DOM tree is None after BrowserStateRequestEvent - page may have failed to load")
            
            current_url = await browser_session.get_current_page_url()
            
            # Use ScraperAgent's DOM extraction logic
            extractor = DOMExtractor()
            
            # Get partial DOM (visible elements only, like ScraperAgent default)
            partial_dom, _ = extractor.serialize_accessible_elements_custom(
                enhanced_dom, include_non_visible=False
            )
            
            # Get full DOM for comparison
            full_dom, _ = extractor.serialize_accessible_elements_custom(
                enhanced_dom, include_non_visible=True
            )
            
            # Convert to dict format
            partial_dict = extract_dom_dict(partial_dom)
            full_dict = extract_dom_dict(full_dom)
            
            # Generate LLM views
            partial_llm_view = extract_llm_view(partial_dict)
            full_llm_view = extract_llm_view(full_dict)
            
            # Save all DOM data (same format as ScraperAgent would use)
            dom_data = {
                "name": name,
                "url": url,
                "current_url": current_url,
                "collection_time": datetime.now().isoformat(),
                "serialized_dom": serialized_dom,
                "enhanced_dom": enhanced_dom,
                "partial_scope": {
                    "target_dom": partial_dom,
                    "dom_dict": partial_dict,
                    "llm_view": partial_llm_view
                },
                "full_scope": {
                    "target_dom": full_dom,
                    "dom_dict": full_dict,
                    "llm_view": full_llm_view
                },
                "timing": timing
            }
            
            # Save to file
            output_file = self.data_dir / f"{name}_dom.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(dom_data, f, indent=2, ensure_ascii=False, default=str)
            
            print(f"✅ DOM data saved to: {output_file}")
            print(f"📊 Partial elements: {len(str(partial_dict))} chars")
            print(f"📊 Full elements: {len(str(full_dict))} chars")
            
            meaningful_partial = json.loads(partial_llm_view) if partial_llm_view != "[]" else []
            meaningful_full = json.loads(full_llm_view) if full_llm_view != "[]" else []
            print(f"🤖 Meaningful partial: {len(meaningful_partial)} elements")
            print(f"🤖 Meaningful full: {len(meaningful_full)} elements")
            
            return True
            
        except Exception as e:
            print(f"DOM collection error: {e}")
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
    
    async def generate_script(self, name: str, requirement_type: str = "product_detail"):
        """Generate script using ScraperAgent's exact logic and prompts

        Note: Script generation ALWAYS uses partial DOM (matching ScraperAgent v5.0 token optimization)
        """

        print(f"=== Script Generation for '{name}' ===")
        print(f"Requirement type: {requirement_type}")
        print(f"⚡ Token Optimization: Always using PARTIAL DOM for script generation")

        # Load DOM data
        dom_file = self.data_dir / f"{name}_dom.json"
        if not dom_file.exists():
            print(f"❌ DOM data not found: {dom_file}")
            print("Run with --mode dom first to collect DOM data")
            return False

        try:
            with open(dom_file, 'r', encoding='utf-8') as f:
                dom_data = json.load(f)

            print(f"✅ Loaded DOM data from: {dom_file}")

            # Get data requirements (same as test_scraper_agent_with_script.py)
            if requirement_type not in self.default_data_requirements:
                print(f"❌ Unknown requirement type: {requirement_type}")
                print(f"Available types: {list(self.default_data_requirements.keys())}")
                return False

            data_requirements = self.default_data_requirements[requirement_type]

            # ALWAYS use partial DOM for script generation (token optimization)
            dom_info = dom_data['partial_scope']

            target_dom = dom_info['target_dom']
            dom_dict = dom_info['dom_dict']
            llm_view = dom_info['llm_view']

            print(f"Using PARTIAL DOM for generation (saves 50-80% tokens)")
            print(f"LLM view length: {len(llm_view)} chars")
            
            # Build DOM analysis (same structure as ScraperAgent)
            dom_analysis = {
                'serialized_dom': target_dom,
                'dom_dict': dom_dict,
                'llm_view': llm_view,
                'dom_config': {
                    'dom_scope': 'partial'  # Always partial for generation
                }
            }

            # Call ScraperAgent's exact LLM generation function
            print("Calling ScraperAgent's LLM generation logic...")
            script_content = await self._generate_extraction_script_with_llm(
                dom_analysis,
                data_requirements,
                []  # interaction_steps
            )

            # Save script
            timestamp = int(datetime.now().timestamp())
            script_file = self.data_dir / f"{name}_script_{requirement_type}_{timestamp}.py"
            
            with open(script_file, 'w', encoding='utf-8') as f:
                f.write(f"# Generated script for '{name}'\n")
                f.write(f"# Requirement type: {requirement_type}\n")
                f.write(f"# Generation DOM: partial (token optimization)\n")
                f.write(f"# Execution DOM: can use partial or full\n")
                f.write(f"# Generated at: {datetime.now().isoformat()}\n")
                f.write("# Data requirements:\n")
                # Fix: Add # to each line of JSON
                json_str = json.dumps(data_requirements, indent=2, ensure_ascii=False)
                for line in json_str.split('\n'):
                    f.write(f"# {line}\n")
                f.write("# " + "=" * 70 + "\n\n")
                f.write(script_content)

            print(f"✅ Script saved to: {script_file}")

            # Print for manual testing
            print("\n" + "=" * 80)
            print("🔧 MANUAL TESTING DATA")
            print("=" * 80)

            print(f"\n📋 Data Requirements:")
            print(json.dumps(data_requirements, indent=2, ensure_ascii=False))

            print(f"\n📝 Generated Script:")
            print("-" * 50)
            print(script_content)

            print(f"\n🤖 LLM View (first 1000 chars):")
            print("-" * 50)
            print(llm_view[:1000] + ("..." if len(llm_view) > 1000 else ""))

            print(f"\n🧪 Manual Test Commands:")
            print("-" * 50)
            print("# 1. Load DOM data (can test with partial or full)")
            print(f"import json")
            print(f"dom_data = json.load(open('{dom_file}'))")
            print(f"# Use partial DOM:")
            print(f"dom_dict = dom_data['partial_scope']['dom_dict']")
            print(f"serialized_dom = dom_data['partial_scope']['target_dom']")
            print(f"# OR use full DOM:")
            print(f"# dom_dict = dom_data['full_scope']['dom_dict']")
            print(f"# serialized_dom = dom_data['full_scope']['target_dom']")
            print("")
            print("# 2. Execute script")
            print(f"exec(open('{script_file}').read())")
            print("")
            print("# 3. Test extraction")
            print("result = execute_extraction(serialized_dom, dom_dict, 10)")
            print("print(json.dumps(result, indent=2, ensure_ascii=False))")
            
            return True
            
        except Exception as e:
            print(f"Script generation error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _generate_extraction_script_with_llm(self, 
                                                 dom_analysis: dict, 
                                                 data_requirements: dict,
                                                 interaction_steps: list) -> str:
        """ScraperAgent's exact LLM generation function (copy from scraper_agent.py)"""
        
        try:
            llm_view = dom_analysis['llm_view']
            
            # Parse data_requirements (same as ScraperAgent)
            user_description = data_requirements.get('user_description', '')
            output_format = data_requirements.get('output_format', {})
            sample_data = data_requirements.get('sample_data', [])
            
            # Build field descriptions
            fields_description = ""
            for field_name, field_desc in output_format.items():
                fields_description += f"- {field_name}: {field_desc}\n"
            
            # Build sample descriptions
            sample_description = ""
            if sample_data and len(sample_data) > 0:
                sample_description = f"\n\n参考样例数据，用户给出的当前页面期望的结果：\n{json.dumps(sample_data, indent=2, ensure_ascii=False)}"
            
            # Simplified scraper prompt - clear instructions with minimal examples
            prompt = f"""
## 第一步：理解DOM遍历
DOM是嵌套字典结构，每个元素包含：
- tag: HTML标签名
- text: 文本内容
- class: CSS类名
- href: 链接地址
- xpath: XPath路径
- children: 子元素数组

遍历方法：递归访问 node.get('children', [])

## 第二步：任务分析和策略选择
判断任务类型：
- **精准提取**：提取特定字段（如商品详情页的标题、价格）
- **模式提取**：提取重复数据（如搜索结果列表、商品列表）

定位策略（优先级）：
1. **Class定位**（首选）- 通过CSS类名，灵活适应单个/多个元素
2. **XPath定位** - 精确路径定位
3. **内容特征定位** - 通过href/text等内容匹配

**跨DOM数据提取策略**：当数据分散在多个相邻元素中时：
1. 先定位到任意一个目标数据元素（通过class或内容）
2. 向上查找该元素的父容器
3. 遍历父容器的所有子元素，收集并组合数据

关键函数示例：
```python
def find_parent_by_xpath(node, levels_up=1):
    # 根据xpath向上查找父容器
    xpath = node.get('xpath', '')
    if not xpath:
        return None
    # XPath向上查找：移除最后N级路径
    parts = xpath.split('/')
    if len(parts) > levels_up:
        parent_xpath = '/'.join(parts[:-levels_up])
        return find_by_xpath(dom_dict, parent_xpath)
    return None

def collect_scattered_data(container_node):
    # 在容器内收集所有子元素的文本
    texts = []
    if container_node and 'children' in container_node:
        for child in container_node.get('children', []):
            if isinstance(child, dict):
                text = child.get('text', '').strip()
                if text:
                    texts.append(text)
    return ''.join(texts)
```

## 第三步：理解具体需求
用户需求：{user_description}

输出字段说明：
{fields_description}{sample_description}

**重要**：这是样例页面，生成的脚本要能适用于内容不同但结构相似的其他页面。

## DOM结构：
{llm_view}

## 要求：
请生成 extract_data_from_page(serialized_dom, dom_dict) 函数：
- 返回: List[Dict[str, Any]]
- 包含错误处理
- 只返回Python代码，不要解释文字
- 根据DOM结构和用户需求选择最合适的策略
"""
            llm_provider = AnthropicProvider()
            response = await llm_provider.generate_response(
                system_prompt="""你是网页数据提取专家。根据提供的三步指导，分析DOM结构生成提取脚本。优先使用Class定位，确保跨页面兼容性。只返回Python代码，不要解释。""",
                user_prompt=prompt
            )
            
            return self._extract_and_wrap_code(response)
            
        except Exception as e:
            print(f"LLM script generation failed: {e}")
            raise Exception(f"LLM script generation failed: {e}")
    
    def _extract_and_wrap_code(self, response: str) -> str:
        """ScraperAgent's exact code extraction and wrapping logic"""
        # Extract code blocks
        if "```python" in response:
            start = response.find("```python") + 9
            end = response.find("```", start)
            code = response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            code = response[start:end].strip()
        else:
            code = response.strip()
        
        # ScraperAgent's exact wrapper
        return f'''
import json
import logging
from typing import List, Dict, Any
from pathlib import Path

{code}

def execute_extraction(serialized_dom, dom_dict, max_items: int = 100):
    """Execute data extraction wrapper function"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Extract all available data
        all_data = extract_data_from_page(serialized_dom, dom_dict)
        
        # Apply quantity limit at wrapper level
        if isinstance(all_data, list):
            limited_data = all_data[:max_items] if max_items > 0 else all_data
            return {{
                "success": True,
                "data": limited_data,
                "total_count": len(limited_data),
                "error": None
            }}
        else:
            return {{
                "success": True,
                "data": all_data,
                "total_count": 1 if all_data else 0,
                "error": None
            }}
    except Exception as e:
        logger.error("Data extraction failed: " + str(e))
        return {{
            "success": False,
            "data": [],
            "total_count": 0,
            "error": str(e)
        }}
'''
    
    def list_data(self):
        """List available DOM data and generated scripts"""
        print("=== Available Data ===")
        
        # List DOM data
        dom_files = list(self.data_dir.glob("*_dom.json"))
        script_files = list(self.data_dir.glob("*_script_*.py"))
        
        if dom_files:
            print("\n📁 DOM Data:")
            for dom_file in dom_files:
                name = dom_file.stem.replace("_dom", "")
                try:
                    with open(dom_file, 'r', encoding='utf-8') as f:
                        dom_data = json.load(f)
                    print(f"  • {name}")
                    print(f"    URL: {dom_data.get('current_url', 'N/A')}")
                    print(f"    Time: {dom_data.get('collection_time', 'N/A')}")
                except Exception as e:
                    print(f"  • {name} (error reading: {e})")
        
        if script_files:
            print("\n📜 Generated Scripts:")
            for script_file in script_files:
                print(f"  • {script_file.name}")
        
        if not dom_files and not script_files:
            print("No data found. Use --mode dom to collect DOM data first.")
        
        print(f"\n📋 Available requirement types:")
        for req_type, req_data in self.default_data_requirements.items():
            print(f"  • {req_type}: {req_data['user_description']}")
    
    async def execute_script(self, name: str, script_file_path: str = None, requirement_type: str = "product_detail", dom_scope: str = "partial", max_items: int = 10):
        """Execute a generated script

        Args:
            name: Test data name
            script_file_path: Specific script file path (optional)
            requirement_type: Type of requirement (for finding script)
            dom_scope: DOM scope for execution ('partial' or 'full')
            max_items: Maximum items to extract
        """

        print(f"=== Script Execution for '{name}' ===")
        print(f"Execution DOM scope: {dom_scope}")
        print(f"Max items: {max_items}")

        # Find script file
        if script_file_path:
            script_file = Path(script_file_path)
        else:
            # Find the most recent script file matching criteria (no dom_scope in filename anymore)
            pattern = f"{name}_script_{requirement_type}_*.py"
            script_files = sorted(self.data_dir.glob(pattern), reverse=True)
            if not script_files:
                print(f"❌ No script files found matching pattern: {pattern}")
                print("Available scripts:")
                all_scripts = list(self.data_dir.glob(f"{name}_script_*.py"))
                for script in all_scripts:
                    print(f"  • {script.name}")
                return False
            script_file = script_files[0]

        # Load cached DOM data
        dom_file = self.data_dir / f"{name}_dom.json"
        if not dom_file.exists():
            print(f"❌ DOM data not found: {dom_file}")
            return False
        
        try:
            # Load files
            with open(dom_file, 'r', encoding='utf-8') as f:
                dom_data = json.load(f)
            
            with open(script_file, 'r', encoding='utf-8') as f:
                script_content = f.read()
            
            print(f"✅ Loaded script: {script_file.name}")
            print(f"✅ Loaded DOM data: {dom_file.name}")
            
            # Get DOM data for specified scope
            scope_data = dom_data[f'{dom_scope}_scope']
            serialized_dom = scope_data['target_dom']
            dom_dict = scope_data['dom_dict']
            
            print(f"🚀 Executing script...")
            
            # Fixed execution - use shared namespace for all functions
            script_namespace = globals().copy()
            exec(script_content, script_namespace, script_namespace)
            
            # Get the function from the execution environment
            execute_extraction = script_namespace.get('execute_extraction')
            if not execute_extraction:
                print("❌ Script missing execute_extraction function")
                return False
            
            result = execute_extraction(serialized_dom, dom_dict, max_items)
            
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
            else:
                print(f"❌ Failed: {result.get('error', 'Unknown error')}")
            
            print(f"\n📄 Full result:")
            print(json.dumps(result, indent=2, ensure_ascii=False))

            return result.get("success", False)

        except Exception as e:
            print(f"❌ Execution failed: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    parser = argparse.ArgumentParser(description='ScraperAgent Debug Helper')
    parser.add_argument('--mode', choices=['dom', 'generate', 'exec', 'list'], required=True,
                       help='dom: collect DOM data, generate: create script, exec: execute script, list: show data')
    parser.add_argument('--url', help='URL for DOM collection')
    parser.add_argument('--name', help='Test data name')
    parser.add_argument('--requirement-type', choices=['product_detail', 'product_list', 'url_list'],
                       default='product_detail', help='Type of data requirements to use')
    parser.add_argument('--dom-scope', choices=['partial', 'full'], default='partial',
                       help='DOM scope for script execution (generation always uses partial)')
    parser.add_argument('--script-file', help='Specific script file to execute (optional)')
    parser.add_argument('--max-items', type=int, default=10, help='Maximum items to extract')
    
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

        success = await helper.generate_script(args.name, args.requirement_type)
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
