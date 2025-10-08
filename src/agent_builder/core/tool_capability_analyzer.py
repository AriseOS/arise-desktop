"""
工具能力分析器 - 分析现有工具能力并支持新工具需求识别
"""

import json
import importlib
import inspect
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ToolCapability:
    """工具能力描述"""
    name: str                           # 工具名称
    description: str                    # 工具描述
    category: str                       # 工具分类
    actions: List[str]                  # 支持的动作列表
    action_details: Dict[str, Any]      # 动作详细信息
    implementation_complexity: str      # 实现复杂度: low/medium/high
    dependencies: List[str]             # 依赖列表
    examples: List[Dict[str, Any]]      # 使用示例


@dataclass
class ToolGapAnalysis:
    """工具差距分析"""
    requirement_description: str        # 需求描述
    existing_tools_match: List[str]     # 匹配的现有工具
    capability_gaps: List[str]          # 能力差距
    implementation_suggestion: str      # 实现建议
    estimated_complexity: str          # 预估复杂度
    recommended_approach: str          # 推荐方案


class ToolCapabilityAnalyzer:
    """工具能力分析器"""
    
    def __init__(self):
        self.existing_tools: Dict[str, ToolCapability] = {}
        self._load_existing_tools()
    
    def _load_existing_tools(self):
        """加载现有工具能力"""
        # 这里硬编码现有工具的能力，实际使用时可以动态扫描
        self.existing_tools = {
            "browser_use": ToolCapability(
                name="browser_use",
                description="基于AI的浏览器自动化工具，支持自然语言驱动的网页操作",
                category="automation",
                actions=["navigate", "click", "fill_form", "extract_data", "screenshot", "wait_for_element", "scroll", "execute_task", "get_page_info"],
                action_details={
                    "navigate": {"description": "导航到指定URL", "params": ["url", "wait_until"]},
                    "click": {"description": "点击页面元素", "params": ["selector", "description"]},
                    "fill_form": {"description": "填写表单", "params": ["form_data", "submit"]},
                    "extract_data": {"description": "提取页面数据", "params": ["data_description", "selector"]},
                    "screenshot": {"description": "截取页面截图", "params": ["full_page", "element_selector"]},
                    "wait_for_element": {"description": "等待元素出现", "params": ["selector", "timeout"]},
                    "scroll": {"description": "滚动页面", "params": ["direction", "amount"]},
                    "execute_task": {"description": "执行复杂任务", "params": ["task_description"]},
                    "get_page_info": {"description": "获取页面信息", "params": ["info_type"]}
                },
                implementation_complexity="medium",
                dependencies=["browser-use", "playwright"],
                examples=[
                    {"action": "navigate", "params": {"url": "https://example.com"}},
                    {"action": "extract_data", "params": {"data_description": "提取所有产品名称和价格"}}
                ]
            ),
            "android_use": ToolCapability(
                name="android_use",
                description="Android设备自动化工具",
                category="automation",
                actions=["tap", "swipe", "input_text", "screenshot", "get_element", "wait_for_element"],
                action_details={
                    "tap": {"description": "点击屏幕坐标或元素", "params": ["x", "y", "element_id"]},
                    "swipe": {"description": "滑动屏幕", "params": ["start_x", "start_y", "end_x", "end_y"]},
                    "input_text": {"description": "输入文本", "params": ["text", "element_id"]},
                    "screenshot": {"description": "截取屏幕截图", "params": []},
                    "get_element": {"description": "获取屏幕元素", "params": ["element_description"]},
                    "wait_for_element": {"description": "等待元素出现", "params": ["element_description", "timeout"]}
                },
                implementation_complexity="high",
                dependencies=["android-tools", "adb"],
                examples=[
                    {"action": "tap", "params": {"x": 100, "y": 200}},
                    {"action": "input_text", "params": {"text": "Hello World", "element_id": "edit_text_1"}}
                ]
            ),
            "llm_extract": ToolCapability(
                name="llm_extract",
                description="基于LLM的文本提取和分析工具",
                category="text_processing",
                actions=["extract_entities", "summarize", "classify", "transform"],
                action_details={
                    "extract_entities": {"description": "提取文本中的实体", "params": ["text", "entity_types"]},
                    "summarize": {"description": "文本摘要", "params": ["text", "max_length"]},
                    "classify": {"description": "文本分类", "params": ["text", "categories"]},
                    "transform": {"description": "文本转换", "params": ["text", "transformation_type"]}
                },
                implementation_complexity="low",
                dependencies=["openai", "anthropic"],
                examples=[
                    {"action": "extract_entities", "params": {"text": "John works at Google", "entity_types": ["PERSON", "ORG"]}},
                    {"action": "summarize", "params": {"text": "Long article text...", "max_length": 100}}
                ]
            )
        }
    
    def get_existing_tools_summary(self) -> str:
        """获取现有工具能力摘要"""
        summary = "## 现有工具能力矩阵\n\n"
        
        for tool_name, tool_info in self.existing_tools.items():
            summary += f"### {tool_name}\n"
            summary += f"**分类**: {tool_info.category}\n"
            summary += f"**描述**: {tool_info.description}\n"
            summary += f"**实现复杂度**: {tool_info.implementation_complexity}\n"
            summary += f"**核心能力**: {', '.join(tool_info.actions)}\n"
            summary += f"**依赖**: {', '.join(tool_info.dependencies)}\n\n"
            
            # 添加关键动作详情
            summary += "**关键动作**:\n"
            for action, details in tool_info.action_details.items():
                summary += f"- `{action}`: {details['description']}\n"
            summary += "\n"
        
        return summary
    
    def analyze_tool_requirements(self, step_requirement: str) -> ToolGapAnalysis:
        """分析步骤需求的工具实现方案"""
        # 这里可以集成LLM来进行智能分析
        # 暂时使用简单的关键词匹配
        
        existing_matches = []
        capability_gaps = []
        
        # 简单的关键词匹配分析
        req_lower = step_requirement.lower()
        
        # 检查现有工具匹配
        for tool_name, tool_info in self.existing_tools.items():
            if self._check_tool_match(req_lower, tool_info):
                existing_matches.append(tool_name)
        
        # 分析能力差距
        if not existing_matches:
            if any(keyword in req_lower for keyword in ['web', 'browser', 'website', 'url', 'page']):
                if 'browser_use' not in existing_matches:
                    capability_gaps.append("需要网页操作能力")
            elif any(keyword in req_lower for keyword in ['android', 'mobile', 'app', 'device']):
                if 'android_use' not in existing_matches:
                    capability_gaps.append("需要移动设备操作能力")
            elif any(keyword in req_lower for keyword in ['text', 'extract', 'analyze', 'nlp']):
                if 'llm_extract' not in existing_matches:
                    capability_gaps.append("需要文本处理能力")
            else:
                capability_gaps.append("需要自定义工具实现")
        
        # 生成实现建议
        if existing_matches:
            if len(existing_matches) == 1:
                suggestion = f"直接使用现有工具 {existing_matches[0]}"
                complexity = "low"
                approach = "reuse_existing"
            else:
                suggestion = f"组合使用现有工具: {', '.join(existing_matches)}"
                complexity = "medium"
                approach = "combine_existing"
        else:
            suggestion = "需要实现新的自定义工具"
            complexity = "high"
            approach = "implement_new"
        
        return ToolGapAnalysis(
            requirement_description=step_requirement,
            existing_tools_match=existing_matches,
            capability_gaps=capability_gaps,
            implementation_suggestion=suggestion,
            estimated_complexity=complexity,
            recommended_approach=approach
        )
    
    def _check_tool_match(self, requirement: str, tool_info: ToolCapability) -> bool:
        """检查工具是否匹配需求"""
        # 简单的关键词匹配逻辑
        tool_keywords = (
            tool_info.description.lower() + " " + 
            " ".join(tool_info.actions) + " " + 
            tool_info.category.lower()
        )
        
        # 提取需求中的关键词
        req_keywords = requirement.split()
        
        # 检查匹配度
        matches = sum(1 for keyword in req_keywords if keyword in tool_keywords)
        return matches >= 2 or len(req_keywords) <= 3  # 简单的匹配逻辑
    
    def get_tool_implementation_guidance(self, approach: str, requirement: str) -> str:
        """获取工具实现指导"""
        if approach == "reuse_existing":
            return "直接调用现有工具，配置相应参数即可"
        elif approach == "combine_existing":
            return "设计工具调用链，确保数据在工具间正确传递"
        elif approach == "implement_new":
            return f"""需要实现新工具来满足需求: {requirement}
            
实现建议:
1. 继承BaseTool类
2. 实现必要的抽象方法
3. 定义工具的动作和参数
4. 添加适当的错误处理
5. 编写测试用例"""
        else:
            return "未知的实现方案"