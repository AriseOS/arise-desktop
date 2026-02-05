"""Prompt 模块基类

定义统一的 Prompt 接口，用于所有 LLM 交互的提示词管理。

设计原则：
1. 输入输出明确定义
2. 包含解析和验证逻辑
3. 支持示例和测试
4. 易于维护和扩展
"""

import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar

# 定义泛型类型
TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class PromptTemplate:
    """Prompt 模板类

    提供模板字符串的格式化功能
    """

    def __init__(self, template: str, variables: List[str]):
        """初始化模板

        Args:
            template: 模板字符串，使用 {variable} 作为占位符
            variables: 变量名列表
        """
        self.template = template
        self.variables = variables

    def format(self, **kwargs) -> str:
        """格式化模板

        Args:
            **kwargs: 变量值

        Returns:
            格式化后的字符串
        """
        # 验证所有必需变量都提供了
        missing = set(self.variables) - set(kwargs.keys())
        if missing:
            raise ValueError(f"Missing required variables: {missing}")

        return self.template.format(**kwargs)

    def validate_variables(self, **kwargs) -> bool:
        """验证变量

        Args:
            **kwargs: 变量值

        Returns:
            是否有效
        """
        return set(self.variables).issubset(set(kwargs.keys()))


class PromptInput:
    """Prompt 输入数据基类"""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典

        Returns:
            字典表示
        """
        return self.__dict__

    def validate(self) -> bool:
        """验证输入数据

        Returns:
            是否有效
        """
        return True


class PromptOutput:
    """Prompt 输出数据基类"""

    def __init__(self, raw_response: str, parsed_data: Dict[str, Any]):
        self.raw_response = raw_response
        self.parsed_data = parsed_data
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典

        Returns:
            字典表示
        """
        return {
            "raw_response": self.raw_response,
            "parsed_data": self.parsed_data,
            "timestamp": self.timestamp.isoformat(),
        }

    def validate(self) -> bool:
        """验证输出数据

        Returns:
            是否有效
        """
        return self.parsed_data is not None


class BasePrompt(ABC, Generic[TInput, TOutput]):
    """Prompt 基类

    所有 Prompt 模块的抽象基类
    """

    def __init__(self, prompt_name: str, version: str = "1.0"):
        """初始化 Prompt

        Args:
            prompt_name: Prompt 名称
            version: 版本号
        """
        self.prompt_name = prompt_name
        self.version = version
        self.template: Optional[PromptTemplate] = None

    @abstractmethod
    def build_prompt(self, input_data: TInput) -> str:
        """构建 LLM prompt

        Args:
            input_data: 输入数据

        Returns:
            构建的 prompt 字符串
        """

    @abstractmethod
    def parse_response(self, llm_response: str) -> TOutput:
        """解析 LLM 响应

        Args:
            llm_response: LLM 原始响应

        Returns:
            解析后的输出数据
        """

    @abstractmethod
    def validate_input(self, input_data: TInput) -> bool:
        """验证输入数据

        Args:
            input_data: 输入数据

        Returns:
            是否有效
        """

    @abstractmethod
    def validate_output(self, output_data: TOutput) -> bool:
        """验证输出数据

        Args:
            output_data: 输出数据

        Returns:
            是否有效
        """

    def get_system_prompt(self) -> str:
        """获取系统提示

        Returns:
            系统提示字符串
        """
        return "You are a professional AI assistant."

    def get_examples(self) -> List[Dict[str, Any]]:
        """获取示例

        Returns:
            示例列表
        """
        return []

    def clean_json_response(self, response: str) -> str:
        """清理 JSON 响应

        移除 markdown 代码块等多余内容

        Args:
            response: 原始响应

        Returns:
            清理后的 JSON 字符串
        """
        response = response.strip()

        # 移除 markdown 代码块
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            if end != -1:
                response = response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            if end != -1:
                response = response[start:end].strip()

        # 查找 JSON 对象
        start_idx = response.find("{")
        end_idx = response.rfind("}")

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            response = response[start_idx : end_idx + 1]

        return response

    def parse_json_response(self, response: str) -> Dict[str, Any]:
        """解析 JSON 响应

        Args:
            response: 响应字符串

        Returns:
            解析后的字典

        Raises:
            ValueError: JSON 解析失败
        """
        cleaned = self.clean_json_response(response)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse JSON response: {e}\nResponse: {cleaned}"
            ) from e

    def format_list_items(self, items: List[Any], indent: int = 2) -> str:
        """格式化列表项

        Args:
            items: 项目列表
            indent: 缩进空格数

        Returns:
            格式化后的字符串
        """
        indent_str = " " * indent
        lines = []
        for i, item in enumerate(items, 1):
            if isinstance(item, dict):
                item_str = json.dumps(item, ensure_ascii=False, indent=2)
                lines.append(f"{indent_str}{i}. {item_str}")
            else:
                lines.append(f"{indent_str}{i}. {item}")
        return "\n".join(lines)

    def get_metadata(self) -> Dict[str, Any]:
        """获取 Prompt 元数据

        Returns:
            元数据字典
        """
        return {
            "prompt_name": self.prompt_name,
            "version": self.version,
            "has_template": self.template is not None,
            "examples_count": len(self.get_examples()),
        }


class PromptRegistry:
    """Prompt 注册表

    管理所有 Prompt 实例
    """

    def __init__(self):
        self._prompts: Dict[str, BasePrompt] = {}

    def register(self, prompt: BasePrompt) -> None:
        """注册 Prompt

        Args:
            prompt: Prompt 实例
        """
        self._prompts[prompt.prompt_name] = prompt

    def get(self, prompt_name: str) -> Optional[BasePrompt]:
        """获取 Prompt

        Args:
            prompt_name: Prompt 名称

        Returns:
            Prompt 实例，如果不存在则返回 None
        """
        return self._prompts.get(prompt_name)

    def list_prompts(self) -> List[str]:
        """列出所有注册的 Prompt

        Returns:
            Prompt 名称列表
        """
        return list(self._prompts.keys())

    def get_all_metadata(self) -> Dict[str, Dict[str, Any]]:
        """获取所有 Prompt 的元数据

        Returns:
            Prompt 名称到元数据的映射
        """
        return {name: prompt.get_metadata() for name, prompt in self._prompts.items()}


# 全局注册表实例
prompt_registry = PromptRegistry()


__all__ = [
    "PromptTemplate",
    "PromptInput",
    "PromptOutput",
    "BasePrompt",
    "PromptRegistry",
    "prompt_registry",
]
