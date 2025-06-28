"""
Browser工具使用示例
展示如何使用BrowserTool进行各种浏览器自动化任务
"""
import asyncio
import os
from dotenv import load_dotenv

from tools.browser_use import BrowserTool, BrowserConfig

# 加载环境变量
load_dotenv()


async def example_basic_navigation():
    """基础导航示例"""
    print("🌐 基础导航示例")
    
    config = BrowserConfig(
        headless=True,
        timeout=60
    )
    tool = BrowserTool(config)
    
    await tool.initialize()
    
    try:
        # 导航到网页
        result = await tool.execute("navigate", {"url": "https://httpbin.org"})
        print(f"导航结果: {result.message}")
        
        # 获取页面标题
        result = await tool.execute("get_page_info", {"info_type": "title"})
        print(f"页面标题: {result.data}")
        
    finally:
        await tool.cleanup()


async def example_form_filling():
    """表单填写示例"""
    print("\n📝 表单填写示例")
    
    config = BrowserConfig(headless=True)
    tool = BrowserTool(config)
    
    await tool.initialize()
    
    try:
        # 1. 导航到表单页面
        await tool.execute("navigate", {"url": "https://httpbin.org/forms/post"})
        
        # 2. 填写表单
        form_data = {
            "custname": "张三",
            "custtel": "13800138000", 
            "custemail": "zhangsan@example.com",
            "size": "large"
        }
        
        result = await tool.execute("fill_form", {
            "form_data": form_data,
            "submit": True
        })
        
        print(f"表单填写结果: {result.message}")
        
    finally:
        await tool.cleanup()


async def example_data_extraction():
    """数据提取示例"""
    print("\n📊 数据提取示例")
    
    config = BrowserConfig(headless=True)
    tool = BrowserTool(config)
    
    await tool.initialize()
    
    try:
        # 导航到页面
        await tool.execute("navigate", {"url": "https://quotes.toscrape.com/"})
        
        # 提取引言数据
        result = await tool.execute("extract_data", {
            "target": "all quotes with authors and text",
            "format": "json"
        })
        
        print(f"提取的数据: {result.data}")
        
    finally:
        await tool.cleanup()


async def example_complex_task():
    """复杂任务示例 - 模拟路演信息填写"""
    print("\n🎯 复杂任务示例 - 路演信息填写")
    
    config = BrowserConfig(headless=False)  # 可视化模式便于观察
    tool = BrowserTool(config)
    
    await tool.initialize()
    
    try:
        # 模拟路演助手的复杂任务
        task = """
        1. Navigate to a demo form website (https://httpbin.org/forms/post)
        2. Fill in the form with the following roadshow information:
           - Customer Name: 投资公司A
           - Phone: 021-12345678
           - Email: investor@companya.com
           - Comments: 路演时间安排在2024年1月15日下午2点
        3. Submit the form
        4. Capture the response and extract the submitted data
        """
        
        result = await tool.execute("execute_task", {
            "task": task,
            "max_steps": 10
        })
        
        print(f"复杂任务执行结果: {result.message}")
        print(f"任务数据: {result.data}")
        
    finally:
        await tool.cleanup()


async def example_error_handling():
    """错误处理示例"""
    print("\n⚠️ 错误处理示例")
    
    config = BrowserConfig(
        headless=True,
        timeout=10,  # 短超时时间
        retry_count=2
    )
    tool = BrowserTool(config)
    
    await tool.initialize()
    
    try:
        # 尝试访问不存在的页面
        result = await tool.execute_with_retry("navigate", {
            "url": "https://this-website-does-not-exist-12345.com"
        })
        
        if result.success:
            print("导航成功")
        else:
            print(f"导航失败: {result.message}")
            print(f"执行状态: {result.status}")
        
    finally:
        await tool.cleanup()


async def example_screenshot():
    """截图示例"""
    print("\n📸 截图示例")
    
    config = BrowserConfig(headless=True)
    tool = BrowserTool(config)
    
    await tool.initialize()
    
    try:
        # 导航到页面
        await tool.execute("navigate", {"url": "https://example.com"})
        
        # 截取整页截图
        result = await tool.execute("screenshot", {
            "full_page": True,
            "filename": "example_full_page.png"
        })
        
        print(f"截图结果: {result.message}")
        
    finally:
        await tool.cleanup()


async def example_wait_and_interact():
    """等待和交互示例"""
    print("\n⏳ 等待和交互示例")
    
    config = BrowserConfig(headless=True)
    tool = BrowserTool(config)
    
    await tool.initialize()
    
    try:
        # 导航到页面
        await tool.execute("navigate", {"url": "https://httpbin.org/delay/2"})
        
        # 等待页面加载完成
        await tool.execute("wait_for_element", {
            "description": "page content",
            "timeout": 5000,
            "state": "visible"
        })
        
        # 滚动页面
        await tool.execute("scroll", {
            "direction": "down",
            "amount": 500
        })
        
        print("页面交互完成")
        
    finally:
        await tool.cleanup()


async def demo_workflow():
    """演示完整工作流"""
    print("🚀 Browser工具演示开始\n")
    
    # 检查API Key
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️ 警告: 未设置 OPENAI_API_KEY 环境变量")
        print("某些示例可能无法正常运行")
        print("请在 .env 文件中设置: OPENAI_API_KEY=your_key_here\n")
    
    try:
        # 运行各种示例
        await example_basic_navigation()
        await example_data_extraction()
        await example_form_filling()
        await example_error_handling()
        await example_screenshot()
        await example_wait_and_interact()
        
        # 如果有API Key，运行复杂任务
        if os.getenv("OPENAI_API_KEY"):
            await example_complex_task()
        else:
            print("\n⏭️ 跳过复杂任务示例（需要OPENAI_API_KEY）")
        
    except Exception as e:
        print(f"❌ 演示过程中出现错误: {e}")
    
    print("\n✅ Browser工具演示完成")


if __name__ == "__main__":
    # 运行演示
    asyncio.run(demo_workflow())