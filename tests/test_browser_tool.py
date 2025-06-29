"""
Browser工具测试用例
"""
import pytest
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

from tools.browser_use import BrowserTool, BrowserConfig
from tools.base_tool import ToolStatus, ToolResult


class TestBrowserTool:
    """Browser工具测试类"""
    
    @pytest.fixture
    def browser_config(self):
        """创建测试配置"""
        return BrowserConfig(
            headless=True,
            timeout=30,
            llm_model="gpt-4o",
            llm_api_key="test-api-key"
        )
    
    @pytest.fixture
    def browser_tool(self, browser_config):
        """创建Browser工具实例"""
        return BrowserTool(browser_config)
    
    def test_metadata(self, browser_tool):
        """测试工具元数据"""
        metadata = browser_tool.metadata
        assert metadata.name == "browser_use"
        assert "浏览器自动化" in metadata.description
        assert "automation" in metadata.tags
    
    def test_available_actions(self, browser_tool):
        """测试可用动作列表"""
        actions = browser_tool.get_available_actions()
        expected_actions = [
            "navigate", "click", "fill_form", "extract_data",
            "screenshot", "wait_for_element", "scroll", 
            "execute_task", "get_page_info"
        ]
        for action in expected_actions:
            assert action in actions
    
    def test_action_schemas(self, browser_tool):
        """测试动作模式定义"""
        # 测试 navigate 动作
        navigate_schema = browser_tool.get_schema("navigate")
        assert navigate_schema["type"] == "object"
        assert "url" in navigate_schema["properties"]
        assert "url" in navigate_schema["required"]
        
        # 测试 fill_form 动作
        form_schema = browser_tool.get_schema("fill_form")
        assert "form_data" in form_schema["properties"]
        assert "form_data" in form_schema["required"]
    
    @pytest.mark.asyncio
    async def test_validate_params(self, browser_tool):
        """测试参数验证"""
        # 有效参数
        assert await browser_tool.validate_params("navigate", {"url": "https://example.com"})
        assert await browser_tool.validate_params("fill_form", {"form_data": {"name": "test"}})
        
        # 无效参数 - 缺少必需参数
        assert not await browser_tool.validate_params("navigate", {})
        assert not await browser_tool.validate_params("fill_form", {"submit": True})
        
        # 不存在的动作
        assert not await browser_tool.validate_params("invalid_action", {})
    
    @pytest.mark.asyncio
    @patch('tools.browser_use.browser_tool.ChatOpenAI')
    async def test_initialize(self, mock_chat_openai, browser_tool):
        """测试工具初始化"""
        mock_llm = MagicMock()
        mock_chat_openai.return_value = mock_llm
        
        result = await browser_tool.initialize()
        assert result is True
        assert browser_tool.llm == mock_llm
        assert browser_tool.status == ToolStatus.IDLE
        
        # 验证 ChatOpenAI 被正确调用
        mock_chat_openai.assert_called_once_with(
            model="gpt-4o",
            api_key="test-api-key",
            base_url=None
        )
    
    @pytest.mark.asyncio
    async def test_cleanup(self, browser_tool):
        """测试资源清理"""
        # 模拟当前agent
        browser_tool.current_agent = MagicMock()
        
        result = await browser_tool.cleanup()
        assert result is True
        assert browser_tool.current_agent is None
    
    @pytest.mark.asyncio
    @patch('tools.browser_use.browser_tool.Agent')
    async def test_execute_task(self, mock_agent_class, browser_tool):
        """测试执行自然语言任务"""
        # 模拟初始化
        browser_tool.llm = MagicMock()
        
        # 模拟 Agent 实例
        mock_agent = AsyncMock()
        mock_agent.run.return_value = "Task completed successfully"
        mock_agent_class.return_value = mock_agent
        
        # 执行任务
        result = await browser_tool.execute("execute_task", {
            "task": "Navigate to google.com and search for python"
        })
        
        assert result.success is True
        assert "Task completed successfully" in str(result.data["result"])
        assert result.status == ToolStatus.SUCCESS
        
        # 验证 Agent 被正确创建和调用
        mock_agent_class.assert_called_once_with(
            task="Navigate to google.com and search for python",
            llm=browser_tool.llm,
            max_actions=20
        )
        mock_agent.run.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_navigate(self, browser_tool):
        """测试导航动作"""
        with patch.object(browser_tool, '_execute_task', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = ToolResult(success=True, message="导航成功")
            
            result = await browser_tool.execute("navigate", {"url": "https://example.com"})
            
            assert result.success is True
            mock_execute.assert_called_once_with({"task": "Navigate to https://example.com"})
    
    @pytest.mark.asyncio
    async def test_execute_fill_form(self, browser_tool):
        """测试表单填写动作"""
        with patch.object(browser_tool, '_execute_task', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = ToolResult(success=True, message="表单填写成功")
            
            form_data = {"username": "testuser", "password": "testpass"}
            result = await browser_tool.execute("fill_form", {
                "form_data": form_data,
                "submit": True
            })
            
            assert result.success is True
            # 验证任务描述包含表单数据和提交指令
            call_args = mock_execute.call_args[0][0]
            assert "testuser" in call_args["task"]
            assert "submit" in call_args["task"]
    
    @pytest.mark.asyncio
    async def test_execute_extract_data(self, browser_tool):
        """测试数据提取动作"""
        with patch.object(browser_tool, '_execute_task', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = ToolResult(success=True, data={"title": "Example"})
            
            result = await browser_tool.execute("extract_data", {
                "target": "page title",
                "format": "json"
            })
            
            assert result.success is True
            call_args = mock_execute.call_args[0][0]
            assert "page title" in call_args["task"]
            assert "json" in call_args["task"]
    
    @pytest.mark.asyncio
    async def test_execute_invalid_action(self, browser_tool):
        """测试无效动作"""
        result = await browser_tool.execute("invalid_action", {})
        assert result.success is False
        assert result.status == ToolStatus.ERROR
        assert "参数验证失败" in result.message
    
    @pytest.mark.asyncio
    async def test_execute_with_retry(self, browser_tool):
        """测试重试机制"""
        # 模拟初始化
        browser_tool.llm = MagicMock()
        
        call_count = 0
        
        async def mock_execute(action, params, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:  # 前两次失败
                return ToolResult(success=False, message="Temporary failure")
            else:  # 第三次成功
                return ToolResult(success=True, message="Success")
        
        # 替换execute方法
        browser_tool.execute = mock_execute
        
        # 配置重试
        browser_tool.config.retry_count = 3
        browser_tool.config.retry_delay = 0.1
        
        result = await browser_tool.execute_with_retry("test_action", {})
        
        assert result.success is True
        assert call_count == 3  # 确认重试了3次
    
    def test_action_to_task_conversion(self, browser_tool):
        """测试动作到任务的转换"""
        # 测试点击动作转换
        task = browser_tool._action_to_task("click", {"description": "login button"})
        assert "Click on login button" == task
        
        # 测试滚动动作转换
        task = browser_tool._action_to_task("scroll", {"direction": "down", "amount": 300})
        assert "Scroll down by 300 pixels" == task
        
        # 测试等待元素动作转换
        task = browser_tool._action_to_task("wait_for_element", {
            "description": "loading spinner", 
            "state": "hidden"
        })
        assert "Wait for loading spinner to be hidden" == task


class TestBrowserConfig:
    """Browser配置测试类"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = BrowserConfig()
        assert config.headless is True
        assert config.browser_type == "chromium"
        assert config.viewport_width == 1920
        assert config.viewport_height == 1080
        assert config.llm_model == "gpt-4o"
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = BrowserConfig(
            headless=False,
            browser_type="firefox",
            viewport_width=1280,
            viewport_height=720,
            llm_model="gpt-3.5-turbo",
            timeout=60
        )
        assert config.headless is False
        assert config.browser_type == "firefox"
        assert config.viewport_width == 1280
        assert config.viewport_height == 720
        assert config.llm_model == "gpt-3.5-turbo"
        assert config.timeout == 60


# 集成测试（需要真实的API Key和网络连接）
class TestBrowserToolIntegration:
    """Browser工具集成测试（可选）"""
    
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="需要设置 OPENAI_API_KEY 环境变量"
    )
    @pytest.mark.asyncio
    async def test_real_browser_task(self):
        """真实浏览器任务测试（需要API Key）"""
        config = BrowserConfig(
            headless=True,
            timeout=60
        )
        tool = BrowserTool(config)
        
        # 初始化工具
        await tool.initialize()
        
        try:
            # 执行简单的导航任务
            result = await tool.execute("execute_task", {
                "task": "Navigate to httpbin.org and get the page title"
            })
            
            assert result.success is True
            assert "result" in result.data
            
        finally:
            # 清理资源
            await tool.cleanup()


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])