"""
Core data structures for AgentBuilder
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from datetime import datetime


@dataclass
class ParsedRequirement:
    """解析后的需求"""
    original_text: str                    # 原始需求文本
    agent_purpose: str                    # Agent目的
    process_steps: List['StepDesign']     # 执行步骤
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class StepDesign:
    """步骤设计"""
    step_id: str                         # 步骤ID
    name: str                            # 步骤名称
    description: str                     # 步骤描述
    agent_type: str                      # Agent类型：text/tool/code/custom
    agent_config: Dict[str, Any] = field(default_factory=dict)  # Agent配置参数
    
    def __post_init__(self):
        # 验证agent_type
        valid_types = ['text', 'tool', 'code', 'custom']
        if self.agent_type not in valid_types:
            raise ValueError(f"Invalid agent_type: {self.agent_type}. Must be one of {valid_types}")


@dataclass
class AgentMetadata:
    """Agent元数据"""
    name: str                            # Agent名称
    description: str                     # Agent描述
    capabilities: List[str]              # 能力列表
    interface: Dict[str, Any] = field(default_factory=dict)  # 接口定义
    cost_analysis: str = "unknown"       # 成本分析
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class GeneratedCode:
    """生成的代码"""
    main_agent_code: str                 # 主Agent类代码
    workflow_config: str                 # 工作流配置文件
    metadata: AgentMetadata              # Agent元数据
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class LLMConfig:
    """LLM配置"""
    provider: str = "openai"             # LLM提供商
    model: str = "gpt-4"                 # 模型名称
    temperature: float = 0.7             # 温度参数
    max_tokens: int = 2000               # 最大token数
    api_key: Optional[str] = None        # API密钥