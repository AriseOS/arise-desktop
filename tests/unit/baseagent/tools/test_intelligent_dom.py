#!/usr/bin/env python3
"""
测试智能DOM提取系统 - 使用browser-use库
该脚本测试browser-use库的DOM提取功能，验证：
1. BrowserSession基础功能
2. DomService DOM提取能力
3. 端到端DOM处理验证
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

from browser_use.browser.session import BrowserSession
from browser_use.browser.profile import BrowserProfile
from browser_use import Tools
from browser_use.tools.views import GoToUrlAction
from browser_use.agent.views import ActionModel
from browser_use.dom.service import DomService


class GoToUrlActionModel(ActionModel):
    go_to_url: GoToUrlAction | None = None

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BrowserUseDOMTester:
    """Browser-Use DOM提取系统测试器"""
    
    def __init__(self):
        """初始化测试器"""
        # 设置用户数据目录
        user_data_dir = os.path.abspath("./data/test_browser_data")
        os.makedirs(user_data_dir, exist_ok=True)
        
        # 创建浏览器配置
        self.profile = BrowserProfile(
            headless=False,  # 显示浏览器便于观察
            user_data_dir=user_data_dir,
            keep_alive=False,  # 测试完成后关闭浏览器
            proxy=None,  # 明确禁用代理避免SOCKS错误
        )
        
        self.browser_session = None
        self.dom_service = None
        self.tools = None
        
        logger.info(f"使用用户数据目录: {user_data_dir}")
    
    def _analyze_dom_elements(self, elements: list, element_type: str = "DOM") -> None:
        """分析DOM元素分布"""
        if not elements:
            logger.info(f"✓ {element_type}元素分析: 没有找到元素")
            return
        
        # 统计节点类型
        node_types = {}
        clickable_count = 0
        visible_count = 0
        
        for element in elements:
            # 根据不同的元素结构处理
            if hasattr(element, 'tag_name'):
                tag = element.tag_name
            elif isinstance(element, dict):
                tag = element.get('tag_name', element.get('nodeName', 'unknown'))
            else:
                tag = str(type(element).__name__)
            
            node_types[tag] = node_types.get(tag, 0) + 1
            
            # 检查可点击性和可见性
            if isinstance(element, dict):
                if element.get('clickable', False) or element.get('is_clickable', False):
                    clickable_count += 1
                if element.get('visible', True) or element.get('is_visible', True):
                    visible_count += 1
        
        logger.info(f"✓ {element_type}元素分布分析:")
        logger.info(f"    总元素数量: {len(elements)}")
        logger.info(f"    可点击元素: {clickable_count}")
        logger.info(f"    可见元素: {visible_count}")
        
        # 显示最常见的标签类型
        if node_types:
            sorted_tags = sorted(node_types.items(), key=lambda x: x[1], reverse=True)[:5]
            logger.info(f"    标签类型分布: {dict(sorted_tags)}")
    
    def _print_element_details(self, index: int, element, element_type: str = "元素") -> None:
        """打印单个元素的详细信息"""
        try:
            # 处理不同类型的元素数据结构
            if hasattr(element, '__dict__'):
                # Pydantic模型或类实例
                element_dict = element.__dict__ if hasattr(element, '__dict__') else {}
                tag = getattr(element, 'tag_name', getattr(element, 'nodeName', 'unknown'))
                node_id = getattr(element, 'node_id', getattr(element, 'nodeId', 'N/A'))
            elif isinstance(element, dict):
                # 字典格式
                element_dict = element
                tag = element.get('tag_name', element.get('nodeName', 'unknown'))
                node_id = element.get('node_id', element.get('nodeId', 'N/A'))
            else:
                # 其他类型
                element_dict = {'raw_data': str(element)}
                tag = str(type(element).__name__)
                node_id = 'N/A'
            
            # 获取文本内容
            text_content = ''
            if hasattr(element, 'text_content'):
                text_content = element.text_content
            elif hasattr(element, 'textContent'):
                text_content = element.textContent
            elif isinstance(element_dict, dict):
                text_content = element_dict.get('text_content', element_dict.get('textContent', ''))
            
            if text_content:
                text_content = text_content.strip()[:50]
            
            # 获取属性信息
            attributes = {}
            if hasattr(element, 'attributes'):
                attributes = element.attributes or {}
            elif isinstance(element_dict, dict):
                attributes = element_dict.get('attributes', {})
            
            class_name = attributes.get('class', '')[:30] if attributes else ''
            element_id = attributes.get('id', '') if attributes else ''
            
            # 获取位置信息
            bounds_info = ""
            if hasattr(element, 'bounds') and element.bounds:
                bounds = element.bounds
                bounds_info = f"位置({bounds.get('x', 0):.0f},{bounds.get('y', 0):.0f}) 尺寸({bounds.get('width', 0):.0f}x{bounds.get('height', 0):.0f})"
            elif isinstance(element_dict, dict) and element_dict.get('bounds'):
                bounds = element_dict['bounds']
                bounds_info = f"位置({bounds.get('x', 0):.0f},{bounds.get('y', 0):.0f}) 尺寸({bounds.get('width', 0):.0f}x{bounds.get('height', 0):.0f})"
            
            # 格式化输出
            clickable_flag = "🔗" if element_dict.get('clickable', element_dict.get('is_clickable', False)) else "📄"
            visible_flag = "👁" if element_dict.get('visible', element_dict.get('is_visible', True)) else "🙈"
            
            logger.info(f"    {index}. {clickable_flag}{visible_flag} <{tag}> NodeID:{node_id}")
            if element_id:
                logger.info(f"       ID: '{element_id}'")
            if class_name:
                logger.info(f"       Class: '{class_name}'")
            if bounds_info:
                logger.info(f"       {bounds_info}")
            if text_content:
                logger.info(f"       Text: '{text_content}{'...' if len(text_content) == 50 else ''}'")
        
        except Exception as e:
            logger.warning(f"    {index}. 解析{element_type}失败: {e}")
    
    async def test_browser_session_initialization(self) -> bool:
        """测试浏览器会话初始化"""
        logger.info("测试1：浏览器会话初始化")
        
        try:
            # 创建浏览器会话
            self.browser_session = BrowserSession(browser_profile=self.profile)
            
            # 启动浏览器
            await self.browser_session.start()
            
            # 创建控制器和DOM服务
            self.tools = Tools()
            self.dom_service = DomService(self.browser_session)
            
            logger.info("✓ 浏览器会话、控制器和DOM服务初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"✗ 浏览器会话初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_simple_page_navigation(self) -> bool:
        """测试简单页面导航"""
        logger.info("测试2：简单页面导航")
        
        try:
            # 使用 Controller 导航到测试页面
            goto_action = {'go_to_url': GoToUrlAction(url="https://example.com")}
            nav_result = await self.tools.act(
                action=GoToUrlActionModel(**goto_action),
                browser_session=self.browser_session
            )
            
            if nav_result.error:
                logger.error(f"✗ 导航失败: {nav_result.error}")
                return False
            
            # 等待页面加载
            await asyncio.sleep(2)
            
            # 获取当前页面URL验证导航成功
            current_url = await self.browser_session.get_current_page_url()
            
            if "example.com" in current_url:
                logger.info(f"✓ 导航成功: {current_url}")
                return True
            else:
                logger.error(f"✗ 导航失败: {current_url}")
                return False
            
        except Exception as e:
            logger.error(f"✗ 页面导航测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_dom_service_extraction(self) -> bool:
        """测试DOM服务提取功能"""
        logger.info("测试3：DOM服务提取功能")
        
        try:
            # 获取DOM状态和可点击元素
            dom_state, enhanced_dom_tree, timing_info = await self.dom_service.get_serialized_dom_tree()
            
            logger.info(f"✓ DOM状态获取成功")
            
            # 分析可点击元素
            if hasattr(dom_state, 'selector_map') and dom_state.selector_map:
                clickable_elements = list(dom_state.selector_map.values())
                logger.info(f"✓ 可点击元素: {len(clickable_elements)} 个")
                logger.info(f"✓ DOM处理时间: {timing_info.get('serialize_dom_tree_total', 0)*1000:.2f}ms")
                self._analyze_dom_elements(clickable_elements, "可点击")
                
                # 显示前3个可点击元素详情
                if clickable_elements:
                    logger.info(f"✓ 前{min(3, len(clickable_elements))}个可点击元素:")
                    for i, element in enumerate(clickable_elements[:3]):
                        self._print_element_details(i+1, element, "可点击元素")
            
            # 获取页面标题和URL
            current_url = await self.browser_session.get_current_page_url()
            logger.info(f"✓ 页面URL: {current_url}")
            
            # 页面标题可以从DOM状态中获取（通过title元素）
            # 不再直接执行JavaScript，使用browser-use提供的API
            try:
                # 通过浏览器会话获取页面URL（已有功能）
                current_url_display = await self.browser_session.get_current_page_url()
                logger.info(f"✓ 当前页面URL: {current_url_display}")
            except Exception as e:
                logger.debug(f"获取页面URL失败: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"✗ DOM服务提取测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_performance_metrics(self) -> bool:
        """测试性能指标"""
        logger.info("测试4：性能指标测试")
        
        try:
            # 记录开始时间
            start_time = time.time()
            
            # 执行DOM提取
            dom_state, enhanced_dom_tree, timing_info = await self.dom_service.get_serialized_dom_tree()
            
            # 计算总时间
            total_time = (time.time() - start_time) * 1000  # 转换为毫秒
            serializer_time = timing_info.get('serialize_dom_tree_total', 0) * 1000
            
            # 统计元素数量
            clickable_count = len(dom_state.selector_map) if hasattr(dom_state, 'selector_map') and dom_state.selector_map else 0
            content_count = 0  # DOMState 主要关注可点击元素
            total_elements = clickable_count
            
            logger.info(f"✓ 性能测试结果:")
            logger.info(f"    总提取时间: {total_time:.2f}ms")
            logger.info(f"    DOM序列化时间: {serializer_time:.2f}ms")
            logger.info(f"    可点击元素数量: {clickable_count}")
            logger.info(f"    内容元素数量: {content_count}")
            logger.info(f"    总元素数量: {total_elements}")
            
            if total_elements > 0:
                logger.info(f"    平均处理时间: {total_time/total_elements:.4f}ms/元素")
            
            # 检查性能等级
            if total_time < 100:
                performance_level = "🚀 极佳"
            elif total_time < 300:
                performance_level = "✅ 良好"
            elif total_time < 500:
                performance_level = "⚡ 合格"
            else:
                performance_level = "⚠️ 需要优化"
                
            logger.info(f"    性能等级: {performance_level} ({total_time:.2f}ms)")
            
            return True
            
        except Exception as e:
            logger.error(f"✗ 性能测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_complex_page_workflow(self) -> bool:
        """测试复杂页面工作流程"""
        logger.info("测试5：复杂页面工作流程测试")
        
        try:
            # 导航到更复杂的页面
            logger.info("  - 导航到复杂页面...")
            goto_action = {'go_to_url': GoToUrlAction(url="https://allegro.pl/")}
            nav_result = await self.tools.act(
                action=GoToUrlActionModel(**goto_action),
                browser_session=self.browser_session
            )
            
            if nav_result.error:
                logger.error(f"  ✗ 导航失败: {nav_result.error}")
                return False
            
            # 等待页面加载
            await asyncio.sleep(3)
            
            # 提取DOM状态 - 使用官方API方法
            logger.info("  - 提取DOM状态...")
            dom_state, enhanced_dom_tree, timing_info = await self.dom_service.get_serialized_dom_tree()
            # 使用JSON格式友好打印DOM信息
            import json
            from pprint import pprint
            
            print("=" * 80)
            print("🌳 DOM Tree (Enhanced)")
            print("=" * 80)
            if hasattr(enhanced_dom_tree, '__json__'):
                dom_tree_json = enhanced_dom_tree.__json__()
                print(json.dumps(dom_tree_json, indent=2, ensure_ascii=False))
            else:
                pprint(enhanced_dom_tree, indent=2, width=120)
            
            print("\n" + "=" * 80)
            print("📄 DOM State (Serialized)")
            print("=" * 80)
            if hasattr(dom_state, '__json__'):
                dom_state_json = dom_state.__json__()
                print(json.dumps(dom_state_json, indent=2, ensure_ascii=False))
            else:
                pprint(dom_state, indent=2, width=120)
            
            # 分析复杂页面的元素分布 - 使用新的数据结构
            clickable_elements = list(dom_state.selector_map.values()) if hasattr(dom_state, 'selector_map') and dom_state.selector_map else []
            # 在新的API中，主要关注可点击元素，内容元素可以从DOM树中获取
            content_elements = []  # 新API主要关注交互元素
            
            logger.info(f"  ✓ 复杂页面DOM提取结果:")
            logger.info(f"      可交互元素: {len(clickable_elements)}")
            logger.info(f"      分析元素: {len(content_elements)}")
            
            # 分析表单元素
            form_elements = []
            for element in clickable_elements:
                tag = ''
                if hasattr(element, 'tag_name'):
                    tag = element.tag_name.lower()
                elif isinstance(element, dict):
                    tag = element.get('tag_name', element.get('nodeName', '')).lower()
                
                if tag in ['input', 'button', 'select', 'textarea']:
                    form_elements.append(element)
            
            logger.info(f"      表单元素: {len(form_elements)}")
            
            # 详细分析表单元素
            if form_elements:
                logger.info(f"  ✓ 表单元素详情:")
                for i, element in enumerate(form_elements[:5]):
                    self._print_element_details(i+1, element, "表单元素")
            else:
                logger.info(f"  - 未找到表单元素")
            
            # 分析可交互元素的文本内容
            text_elements = []
            for element in clickable_elements:
                text_content = ''
                if hasattr(element, 'text_content'):
                    text_content = element.text_content
                elif isinstance(element, dict):
                    text_content = element.get('text_content', '')
                
                if text_content and len(text_content.strip()) > 5:
                    text_elements.append((element, len(text_content.strip())))
            
            if text_elements:
                text_elements.sort(key=lambda x: x[1], reverse=True)  # 按文本长度排序
                logger.info(f"  ✓ 有文本的交互元素: {len(text_elements)}")
                logger.info(f"      平均文本长度: {sum(x[1] for x in text_elements) / len(text_elements):.1f} 字符")
                
                # 显示最长的3个文本元素
                logger.info(f"  ✓ 文本最长的{min(3, len(text_elements))}个交互元素:")
                for i, (element, length) in enumerate(text_elements[:3]):
                    logger.info(f"    {i+1}. 长度: {length} 字符")
                    self._print_element_details(i+1, element, "文本交互元素")
            
            logger.info("✓ 复杂页面工作流程测试完成")
            return True
            
        except Exception as e:
            logger.error(f"✗ 复杂页面工作流程测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def run_all_tests(self) -> bool:
        """运行所有测试"""
        logger.info("开始Browser-Use DOM提取系统测试...")
        logger.info("=" * 60)
        
        tests = [
            self.test_browser_session_initialization,
            self.test_simple_page_navigation,
            self.test_dom_service_extraction,
            self.test_performance_metrics,
            self.test_complex_page_workflow
        ]
        
        passed = 0
        total = len(tests)
        
        for i, test in enumerate(tests, 1):
            logger.info(f"\n[{i}/{total}] 执行测试...")
            try:
                if await test():
                    passed += 1
                    logger.info(f"测试 {i} 通过 ✓")
                else:
                    logger.error(f"测试 {i} 失败 ✗")
            except Exception as e:
                logger.error(f"测试 {i} 异常: {e}")
            
            logger.info("-" * 40)
        
        # 清理资源
        try:
            if self.browser_session:
                await self.browser_session.stop()
                logger.info("浏览器会话清理完成")
        except Exception as e:
            logger.warning(f"资源清理失败: {e}")
        
        # 输出测试结果
        logger.info(f"\n测试结果汇总:")
        logger.info(f"总计: {total} 个测试")
        logger.info(f"通过: {passed} 个测试")
        logger.info(f"失败: {total - passed} 个测试")
        logger.info(f"成功率: {(passed/total)*100:.1f}%")
        
        if passed == total:
            logger.info("🎉 所有测试通过！Browser-Use DOM提取系统运行正常")
            return True
        else:
            logger.warning("⚠️ 部分测试失败，需要进一步调试")
            return False


async def main():
    """主函数"""
    logger.info("Browser-Use DOM提取系统测试启动")
    
    tester = BrowserUseDOMTester()
    success = await tester.run_all_tests()
    
    if success:
        logger.info("测试完成：系统运行正常")
        return 0
    else:
        logger.error("测试完成：发现问题需要修复")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("测试被用户中断")
        sys.exit(130)
    except Exception as e:
        logger.error(f"测试程序异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)