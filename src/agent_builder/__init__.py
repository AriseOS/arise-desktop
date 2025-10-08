"""
AgentBuilder - 智能Agent生成系统

基于自然语言描述自动生成BaseAgent兼容的Python代码和工作流配置。
使用先进的LLM技术和Context Engineering原则，实现成本效益最优化的Agent构建。
"""

from .core.schemas import (
    ParsedRequirement,
    StepDesign,
    ToolCapability,
    ToolGapAnalysis,
    LLMConfig,
    GeneratedCode,
    AgentMetadata
)

from .core.requirement_parser import RequirementParser
from .core.tool_capability_analyzer import ToolCapabilityAnalyzer
from .core.agent_designer import AgentDesigner
from .core.workflow_builder import WorkflowBuilder
from .core.code_generator import CodeGenerator
from .core.agent_builder import AgentBuilder, build_agent, AgentBuildError

__version__ = "1.0.0"
__author__ = "AgentCrafter Team"
__description__ = "智能Agent生成系统 - 从自然语言到可执行的AI Agent"

# 便捷导入
__all__ = [
    # 核心类
    "AgentBuilder",
    "RequirementParser", 
    "AgentDesigner",
    "WorkflowBuilder",
    "CodeGenerator",
    "ToolCapabilityAnalyzer",
    
    # 数据结构
    "ParsedRequirement",
    "StepDesign", 
    "ToolCapability",
    "ToolGapAnalysis",
    "LLMConfig",
    "GeneratedCode",
    "AgentMetadata",
    
    # 便捷函数
    "build_agent",
    
    # 异常
    "AgentBuildError",
]


def get_version():
    """获取版本信息"""
    return __version__


def get_info():
    """获取系统信息"""
    return {
        "name": "AgentBuilder",
        "version": __version__,
        "description": __description__,
        "author": __author__,
        "capabilities": [
            "自然语言需求解析",
            "智能Agent类型判断", 
            "工具能力分析",
            "工作流自动构建",
            "Python代码生成",
            "BaseAgent集成"
        ],
        "supported_llm_providers": ["openai", "anthropic"],
        "supported_agent_types": ["text", "tool", "code", "custom"]
    }


# 模块级别的便捷函数
async def quick_build(description: str, api_key: str, provider: str = "openai") -> dict:
    """
    快速构建Agent的便捷函数
    
    Args:
        description: 自然语言需求描述
        api_key: LLM API密钥
        provider: LLM提供商，默认openai
        
    Returns:
        构建结果字典
    """
    return await build_agent(
        user_description=description,
        llm_provider=provider,
        api_key=api_key,
        output_dir="./generated_agents"
    )


# 版本兼容性检查
def check_compatibility():
    """检查依赖兼容性"""
    try:
        import pydantic
        import yaml
        import asyncio
        
        # 检查pydantic版本
        pydantic_version = pydantic.__version__
        if not pydantic_version.startswith('2.'):
            return False, f"需要pydantic >= 2.0.0，当前版本: {pydantic_version}"
            
        return True, "依赖检查通过"
        
    except ImportError as e:
        return False, f"缺少依赖包: {e}"


# 初始化时进行兼容性检查
_compatibility_ok, _compatibility_msg = check_compatibility()
if not _compatibility_ok:
    import warnings
    warnings.warn(f"AgentBuilder兼容性警告: {_compatibility_msg}", UserWarning)


# 使用示例
"""
基本使用:

```python
import asyncio
from agent_builder import build_agent

async def main():
    result = await build_agent(
        description="创建一个智能问答助手",
        api_key="your-api-key",
        provider="openai"
    )
    
    if result["success"]:
        print(f"Agent创建成功: {result['files']['agent_file']}")
    else:
        print("创建失败")

asyncio.run(main())
```

高级使用:

```python
from agent_builder import AgentBuilder, LLMConfig

llm_config = LLMConfig(
    provider="anthropic",
    model="claude-3-sonnet-20240229", 
    api_key="your-key"
)

builder = AgentBuilder(llm_config)

result = await builder.build_agent_from_description(
    "创建一个数据分析专家",
    output_dir="./my_agents",
    agent_name="data_expert"
)
```
"""