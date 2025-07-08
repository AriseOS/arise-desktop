"""
简单的 Browser Tool 使用示例测试
演示如何调用 browser tool 的基本 API
"""
import asyncio
import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 导入 browser tool
try:
    from base_app.base_agent.tools.browser_use import BrowserTool, BrowserConfig
except ImportError as e:
    print(f"❌ 无法导入 BrowserTool: {e}")
    print("请检查项目路径是否正确")
    sys.exit(1)


async def test_browser_tool_basic():
    """基本的 browser tool 使用测试"""
    print("🌐 开始测试 Browser Tool 基本功能...")
    
    # 检查 API Key
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  未设置 OPENAI_API_KEY 环境变量")
        print("请设置: export OPENAI_API_KEY='your-api-key'")
        return
    
    # 1. 创建配置
    config = BrowserConfig(
        headless=True,  # 无头模式
        timeout=30,     # 超时时间
        llm_model="gpt-4o",  # 使用的模型
        # llm_api_key="your-api-key-here"  # 如果需要的话
    )
    
    # 2. 创建工具实例
    tool = BrowserTool(config)
    
    try:
        # 3. 初始化工具
        print("🔧 正在初始化 Browser Tool...")
        init_result = await tool.initialize()
        print(f"初始化结果: {init_result}")
        
        # 4. 测试导航功能
        print("\n📍 测试导航功能...")
        nav_result = await tool.execute("navigate", {
            "url": "https://httpbin.org"
        })
        print(f"导航结果: {nav_result.success}")
        print(f"导航消息: {nav_result.message}")
        
        # 5. 测试获取页面信息
        print("\n📄 测试获取页面信息...")
        info_result = await tool.execute("get_page_info", {
            "info_type": "title"
        })
        print(f"页面信息结果: {info_result.success}")
        print(f"页面信息: {info_result.data}")
        
        # 6. 测试执行自然语言任务
        print("\n🤖 测试执行自然语言任务...")
        task_result = await tool.execute("execute_task", {
            "task": "Get the page title and URL"
        })
        print(f"任务执行结果: {task_result.success}")
        print(f"任务结果: {task_result.data}")
        
        # 7. 测试表单填写（模拟）
        print("\n📝 测试表单填写...")
        form_result = await tool.execute("fill_form", {
            "form_data": {
                "username": "testuser",
                "email": "test@example.com"
            },
            "submit": False
        })
        print(f"表单填写结果: {form_result.success}")
        print(f"表单填写消息: {form_result.message}")
        
        # 8. 测试点击操作
        print("\n🖱️ 测试点击操作...")
        click_result = await tool.execute("click", {
            "description": "search button"
        })
        print(f"点击结果: {click_result.success}")
        print(f"点击消息: {click_result.message}")
        
        print("\n✅ 所有测试完成！")
        
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # 9. 清理资源
        print("\n🧹 清理资源...")
        cleanup_result = await tool.cleanup()
        print(f"清理结果: {cleanup_result}")


def test_browser_tool_config():
    """测试 browser tool 配置"""
    print("\n⚙️ 测试配置功能...")
    
    # 默认配置
    default_config = BrowserConfig()
    print(f"默认配置 - 无头模式: {default_config.headless}")
    print(f"默认配置 - 浏览器类型: {default_config.browser_type}")
    print(f"默认配置 - 视窗大小: {default_config.viewport_width}x{default_config.viewport_height}")
    print(f"默认配置 - LLM模型: {default_config.llm_model}")
    
    # 自定义配置
    custom_config = BrowserConfig(
        headless=False,
        browser_type="firefox",
        viewport_width=1280,
        viewport_height=720,
        llm_model="gpt-3.5-turbo"
    )
    print(f"自定义配置 - 无头模式: {custom_config.headless}")
    print(f"自定义配置 - 浏览器类型: {custom_config.browser_type}")
    print(f"自定义配置 - 视窗大小: {custom_config.viewport_width}x{custom_config.viewport_height}")
    print(f"自定义配置 - LLM模型: {custom_config.llm_model}")


def test_browser_tool_metadata():
    """测试 browser tool 元数据"""
    print("\n📋 测试元数据...")
    
    tool = BrowserTool()
    metadata = tool.metadata
    
    print(f"工具名称: {metadata.name}")
    print(f"工具描述: {metadata.description}")
    print(f"工具版本: {metadata.version}")
    print(f"工具作者: {metadata.author}")
    print(f"工具标签: {metadata.tags}")
    print(f"工具类别: {metadata.category}")
    
    # 测试可用动作
    actions = tool.get_available_actions()
    print(f"可用动作: {actions}")
    
    # 测试动作模式
    for action in actions[:3]:  # 只显示前3个
        schema = tool.get_schema(action)
        print(f"{action} 模式: {schema}")


async def test_browser_tool_validation():
    """测试参数验证"""
    print("\n✅ 测试参数验证...")
    
    tool = BrowserTool()
    
    # 测试有效参数
    valid_params = [
        ("navigate", {"url": "https://example.com"}),
        ("fill_form", {"form_data": {"name": "test"}}),
        ("execute_task", {"task": "click submit button"}),
        ("get_page_info", {"info_type": "title"}),
        ("click", {"description": "login button"}),
    ]
    
    for action, params in valid_params:
        result = await tool.validate_params(action, params)
        print(f"{action} 参数 {params} 验证结果: {result}")
    
    # 测试无效参数
    invalid_params = [
        ("navigate", {}),  # 缺少必需的 url
        ("fill_form", {}),  # 缺少必需的 form_data
        ("execute_task", {}),  # 缺少必需的 task
        ("invalid_action", {}),  # 不存在的动作
    ]
    
    for action, params in invalid_params:
        result = await tool.validate_params(action, params)
        print(f"{action} 参数 {params} 验证结果: {result}")


async def main():
    """主函数"""
    print("🚀 Browser Tool 简单测试开始\n")
    print("=" * 60)
    
    # 测试配置
    test_browser_tool_config()
    
    # 测试元数据
    test_browser_tool_metadata()
    
    # 测试参数验证
    await test_browser_tool_validation()
    
    # 测试基本功能
    await test_browser_tool_basic()
    
    print("\n" + "=" * 60)
    print("🎉 Browser Tool 测试完成！")
    
    print("\n💡 使用说明:")
    print("1. 如果要运行实际的浏览器操作，需要设置 OPENAI_API_KEY 环境变量")
    print("2. 修改配置中的 llm_api_key 参数来使用你的 API 密钥")
    print("3. 根据需要调整 headless 模式和其他配置参数")


if __name__ == "__main__":
    # 运行测试
    asyncio.run(main())