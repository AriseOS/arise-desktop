"""
最简单的浏览器测试脚本
只打开浏览器，不做任何自动化操作，让用户手动测试
使用browser-use库进行浏览器控制
"""
import asyncio
import os
from pathlib import Path

from browser_use.browser.session import BrowserSession
from browser_use.browser.profile import BrowserProfile
from browser_use import Tools
from browser_use.tools.views import GoToUrlAction
from browser_use.agent.views import ActionModel


class GoToUrlActionModel(ActionModel):
    go_to_url: GoToUrlAction | None = None


async def simple_browser_test():
    """最简单的浏览器测试"""
    
    print("=== 简单浏览器测试 (使用 browser-use) ===")
    print("这个脚本只会打开浏览器，不会进行任何自动化操作")
    print("你可以手动操作浏览器测试是否会被封")
    print()
    
    # 确定用户数据目录
    user_data_dir = os.path.expanduser("~/.data/test_browser_data")
    print(f"用户数据目录: {user_data_dir}")
    
    # 确保目录存在
    Path(user_data_dir).mkdir(parents=True, exist_ok=True)
    print(f"目录是否存在: {os.path.exists(user_data_dir)}")
    print()
    
    # 创建浏览器配置
    profile = BrowserProfile(
        headless=False,  # 有头模式
        user_data_dir=user_data_dir,  # 使用持久化用户数据
        keep_alive=True,  # 保持浏览器运行
        chrome_instance_id="simple_test",  # 唯一实例ID
        proxy=None,  # 明确禁用代理
    )
    
    try:
        print("正在启动浏览器...")
        
        # 创建浏览器会话
        browser_session = BrowserSession(browser_profile=profile)
        
        # 启动浏览器
        await browser_session.start()
        print("浏览器已启动成功！")
        
        # 创建工具实例
        tools = Tools()
        
        # 导航到 example.com
        print("正在导航到 example.com...")
        example_action = {'go_to_url': GoToUrlAction(url="https://example.com")}
        nav_result = await tools.act(
            action=GoToUrlActionModel(**example_action),
            browser_session=browser_session
        )
        
        if nav_result.error:
            print(f"导航失败: {nav_result.error}")
            return
        print("导航成功！")
        
        # 等待页面加载
        print("等待页面加载...")
        await asyncio.sleep(2)
        
        # 获取页面内容 - 使用 DomService
        print("\n=== 获取页面内容 (使用 DomService) ===")
        
        try:
            from browser_use.dom.service import DomService
            
            # 创建 DomService 实例
            dom_service = DomService(browser_session)
            
            # 获取序列化的DOM树
            print("正在获取DOM结构...")
            serialized_dom_state, enhanced_dom_tree, timing_info = await dom_service.get_serialized_dom_tree()
            
            print(f"DOM获取完成，耗时: {timing_info}")
            print(f"页面元素总数: {len(serialized_dom_state.selector_map)}")
            
            # 显示页面基本信息
            print("\n=== 页面基本信息 ===")
            print(f"当前URL: {await browser_session.get_current_page_url()}")
            
            # 从DOM中提取页面标题
            if enhanced_dom_tree.children_nodes:
                for child in enhanced_dom_tree.children_nodes:
                    if child.node_name.upper() == 'HTML':
                        for html_child in child.children_nodes or []:
                            if html_child.node_name.upper() == 'HEAD':
                                for head_child in html_child.children_nodes or []:
                                    if head_child.node_name.upper() == 'TITLE':
                                        title_text = head_child.children_nodes[0].node_value if head_child.children_nodes else None
                                        print(f"页面标题: {title_text}")
                                        break
                                break
                        break
            
            # 显示可交互元素
            print(f"\n=== 可交互元素 (前10个) ===")
            count = 0
            for idx, element in serialized_dom_state.selector_map.items():
                if count >= 10:
                    break
                    
                if element.is_visible and element.tag_name:
                    tag_info = f"[{idx}] {element.tag_name.upper()}"
                    if element.attributes:
                        if 'id' in element.attributes:
                            tag_info += f" id='{element.attributes['id']}'"
                        if 'class' in element.attributes:
                            tag_info += f" class='{element.attributes['class'][:50]}'"
                        if element.tag_name.upper() == 'A' and 'href' in element.attributes:
                            tag_info += f" href='{element.attributes['href'][:50]}'"
                    
                    # 添加文本内容
                    text_content = ""
                    if element.children_nodes:
                        for child in element.children_nodes:
                            if child.node_value:
                                text_content += child.node_value.strip()[:100]
                    if text_content:
                        tag_info += f" 文本: '{text_content}'"
                    
                    print(f"  {tag_info}")
                    count += 1
            
            # 显示页面文本内容摘要
            print(f"\n=== 页面文本内容摘要 ===")
            text_content = ""
            
            def extract_text_from_node(node):
                nonlocal text_content
                if node.node_value and node.node_value.strip():
                    text_content += node.node_value.strip() + " "
                
                if node.children_nodes:
                    for child in node.children_nodes:
                        extract_text_from_node(child)
            
            extract_text_from_node(enhanced_dom_tree)
            
            # 清理和限制文本长度
            text_content = " ".join(text_content.split())  # 标准化空格
            if text_content:
                print(f"页面主要文本内容:")
                print(text_content[:1000] + ("..." if len(text_content) > 1000 else ""))
            else:
                print("未找到文本内容")
                    
        except Exception as e:
            print(f"获取DOM内容失败: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n=== 测试完成 ===")
        print("浏览器将保持打开状态，你可以继续手动操作")
        print("按 Ctrl+C 结束程序...")
        
        try:
            # 使用异步等待而不是阻塞的 input()
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n用户中断，正在清理资源...")
        except Exception as e:
            print(f"\n程序异常: {e}")
        
    except Exception as e:
        print(f"测试出错: {e}")
        import traceback
        traceback.print_exc()
    
    print("测试结束")


if __name__ == "__main__":
    print("开始简单浏览器测试...")
    print("注意: 需要安装 browser-use 和相关依赖")
    print()
    
    asyncio.run(simple_browser_test())
