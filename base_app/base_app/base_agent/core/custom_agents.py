"""
Custom Agent classes for user-defined agents
自定义Agent类，用于用户自定义的Agent实现
"""
import logging
from typing import Any, Dict, List, Optional

from ..agents.base_agent import BaseStepAgent, AgentMetadata
from .schemas import (
    AgentCapability, AgentContext, 
    TextAgentInput, TextAgentOutput,
    ToolAgentInput, ToolAgentOutput,
    CodeAgentInput, CodeAgentOutput
)

logger = logging.getLogger(__name__)


class CustomTextAgent(BaseStepAgent):
    """自定义文本Agent"""
    
    def __init__(self, 
                 name: str, 
                 system_prompt: str, 
                 response_style: str = "professional", 
                 max_length: int = 500,
                 temperature: float = 0.7,
                 model_name: str = None):
        """
        初始化自定义文本Agent
        
        Args:
            name: Agent名称
            system_prompt: 系统提示词
            response_style: 响应风格
            max_length: 最大响应长度
            temperature: 温度参数
            model_name: 模型名称
        """
        metadata = AgentMetadata(
            name=name,
            description=f"自定义文本Agent: {name}",
            capabilities=[AgentCapability.TEXT_GENERATION],
            input_schema={
                "question": {"type": "string", "required": True, "description": "用户问题或请求"},
                "context_data": {"type": "object", "required": False, "description": "上下文数据"},
                "response_style": {"type": "string", "required": False, "description": "响应风格"},
                "max_length": {"type": "integer", "required": False, "description": "最大长度"},
                "language": {"type": "string", "required": False, "description": "语言"}
            },
            output_schema={
                "success": {"type": "boolean", "description": "是否成功"},
                "answer": {"type": "string", "description": "生成的回答"},
                "word_count": {"type": "integer", "description": "字数"},
                "error_message": {"type": "string", "description": "错误信息"}
            }
        )
        super().__init__(metadata)
        
        self.system_prompt = system_prompt
        self.response_style = response_style
        self.max_length = max_length
        self.temperature = temperature
        self.model_name = model_name
        self.provider = None
        
        logger.info(f"创建自定义文本Agent: {name}")
    
    async def initialize(self, context: AgentContext) -> bool:
        """初始化自定义Text Agent"""
        try:
            if not context.agent_instance:
                logger.error("BaseAgent实例未提供")
                return False
            
            # 从BaseAgent获取provider
            self.provider = context.agent_instance.provider
            if not self.provider:
                logger.error("Provider未设置")
                return False
            
            self.is_initialized = True
            logger.info(f"自定义文本Agent初始化成功: {self.metadata.name}")
            return True
            
        except Exception as e:
            logger.error(f"自定义文本Agent初始化失败: {e}")
            return False
    
    async def execute(self, input_data: Any, context: AgentContext) -> Any:
        """执行自定义文本生成"""
        try:
            if not self.is_initialized:
                await self.initialize(context)
            
            # 处理输入数据
            if isinstance(input_data, str):
                question = input_data
                context_data = {}
            elif isinstance(input_data, dict):
                question = input_data.get("question", str(input_data))
                context_data = input_data.get("context_data", {})
            else:
                question = str(input_data)
                context_data = {}
            
            # 构建消息
            messages = [
                {"role": "system", "content": self.system_prompt}
            ]
            
            # 如果有上下文数据，添加到用户消息中
            user_message = question
            if context_data:
                context_str = "\n".join([f"{k}: {v}" for k, v in context_data.items()])
                user_message = f"上下文信息:\n{context_str}\n\n用户问题: {question}"
            
            messages.append({"role": "user", "content": user_message})
            
            # 调用LLM生成文本
            response = await self.provider.generate_text(
                messages,
                max_tokens=self.max_length,
                temperature=self.temperature
            )
            
            # 处理响应
            if response:
                word_count = len(response.replace(" ", ""))  # 简单的字数统计
                
                result = TextAgentOutput(
                    success=True,
                    answer=response,
                    word_count=word_count
                )
                
                logger.debug(f"自定义文本Agent执行成功: {self.metadata.name}")
                return result
            else:
                logger.error("LLM返回空响应")
                return TextAgentOutput(
                    success=False,
                    answer="",
                    word_count=0,
                    error_message="LLM返回空响应"
                )
                
        except Exception as e:
            logger.error(f"自定义文本Agent执行失败: {e}")
            return TextAgentOutput(
                success=False,
                answer="",
                word_count=0,
                error_message=str(e)
            )
    
    async def validate_input(self, input_data: Any) -> bool:
        """验证输入数据"""
        try:
            if isinstance(input_data, str):
                return len(input_data.strip()) > 0
            elif isinstance(input_data, dict):
                return "question" in input_data or len(str(input_data).strip()) > 0
            else:
                return len(str(input_data).strip()) > 0
        except Exception:
            return False
    
    def update_system_prompt(self, new_prompt: str) -> None:
        """更新系统提示词"""
        self.system_prompt = new_prompt
        logger.info(f"更新系统提示词: {self.metadata.name}")
    
    def update_response_style(self, new_style: str) -> None:
        """更新响应风格"""
        self.response_style = new_style
        logger.info(f"更新响应风格: {self.metadata.name} -> {new_style}")


class CustomToolAgent(BaseStepAgent):
    """自定义工具Agent"""
    
    def __init__(self, 
                 name: str, 
                 available_tools: List[str], 
                 tool_selection_strategy: str = "best_match", 
                 confidence_threshold: float = 0.8,
                 max_tool_calls: int = 3):
        """
        初始化自定义工具Agent
        
        Args:
            name: Agent名称
            available_tools: 可用工具列表
            tool_selection_strategy: 工具选择策略
            confidence_threshold: 置信度阈值
            max_tool_calls: 最大工具调用次数
        """
        metadata = AgentMetadata(
            name=name,
            description=f"自定义工具Agent: {name}",
            capabilities=[AgentCapability.TOOL_CALLING],
            input_schema={
                "task_description": {"type": "string", "required": True, "description": "任务描述"},
                "context_data": {"type": "object", "required": False, "description": "上下文数据"},
                "constraints": {"type": "array", "required": False, "description": "约束条件"},
                "allowed_tools": {"type": "array", "required": False, "description": "允许的工具"},
                "confidence_threshold": {"type": "number", "required": False, "description": "置信度阈值"}
            },
            output_schema={
                "success": {"type": "boolean", "description": "是否成功"},
                "result": {"type": "object", "description": "执行结果"},
                "tool_used": {"type": "string", "description": "使用的工具"},
                "action_taken": {"type": "string", "description": "执行的动作"},
                "confidence": {"type": "number", "description": "置信度"},
                "reasoning": {"type": "string", "description": "推理过程"},
                "error_message": {"type": "string", "description": "错误信息"}
            }
        )
        super().__init__(metadata)
        
        self.available_tools = available_tools
        self.tool_selection_strategy = tool_selection_strategy
        self.confidence_threshold = confidence_threshold
        self.max_tool_calls = max_tool_calls
        self.tools_registry = None
        
        logger.info(f"创建自定义工具Agent: {name}, 工具: {available_tools}")
    
    async def initialize(self, context: AgentContext) -> bool:
        """初始化自定义Tool Agent"""
        try:
            if not context.agent_instance:
                logger.error("BaseAgent实例未提供")
                return False
            
            # 从BaseAgent获取tools_registry
            self.tools_registry = context.agent_instance.tools
            if not self.tools_registry:
                logger.error("工具注册表未设置")
                return False
            
            # 检查工具是否可用
            unavailable_tools = []
            for tool_name in self.available_tools:
                if tool_name not in self.tools_registry:
                    unavailable_tools.append(tool_name)
            
            if unavailable_tools:
                logger.warning(f"以下工具不可用: {unavailable_tools}")
                # 从可用工具列表中移除不可用的工具
                self.available_tools = [t for t in self.available_tools if t not in unavailable_tools]
            
            if not self.available_tools:
                logger.error("没有可用的工具")
                return False
            
            self.is_initialized = True
            logger.info(f"自定义工具Agent初始化成功: {self.metadata.name}")
            return True
            
        except Exception as e:
            logger.error(f"自定义工具Agent初始化失败: {e}")
            return False
    
    async def execute(self, input_data: Any, context: AgentContext) -> Any:
        """执行自定义工具调用"""
        try:
            if not self.is_initialized:
                await self.initialize(context)
            
            # 处理输入数据
            if isinstance(input_data, str):
                task_description = input_data
                context_data = {}
                constraints = []
            elif isinstance(input_data, dict):
                task_description = input_data.get("task_description", str(input_data))
                context_data = input_data.get("context_data", {})
                constraints = input_data.get("constraints", [])
            else:
                task_description = str(input_data)
                context_data = {}
                constraints = []
            
            # 选择工具
            selected_tool = await self._select_tool(task_description, context_data)
            
            if not selected_tool:
                return ToolAgentOutput(
                    success=False,
                    result=None,
                    tool_used="",
                    action_taken="",
                    confidence=0.0,
                    reasoning="未找到合适的工具",
                    error_message="没有可用的工具来完成此任务"
                )
            
            # 调用工具
            tool_result = await self._call_tool(selected_tool, task_description, context_data, context)
            
            if tool_result:
                return ToolAgentOutput(
                    success=tool_result.success,
                    result=tool_result.data,
                    tool_used=selected_tool,
                    action_taken="execute",
                    confidence=0.9,  # 可以根据实际情况调整
                    reasoning=f"选择了工具 {selected_tool} 来完成任务: {task_description}",
                    error_message=tool_result.error_message if not tool_result.success else None
                )
            else:
                return ToolAgentOutput(
                    success=False,
                    result=None,
                    tool_used=selected_tool,
                    action_taken="execute",
                    confidence=0.0,
                    reasoning="工具调用失败",
                    error_message="工具执行失败"
                )
                
        except Exception as e:
            logger.error(f"自定义工具Agent执行失败: {e}")
            return ToolAgentOutput(
                success=False,
                result=None,
                tool_used="",
                action_taken="",
                confidence=0.0,
                reasoning="执行异常",
                error_message=str(e)
            )
    
    async def _select_tool(self, task_description: str, context_data: Dict[str, Any]) -> Optional[str]:
        """选择合适的工具"""
        # 简单的工具选择逻辑，可以根据需要扩展
        # 这里使用最简单的策略：返回第一个可用的工具
        for tool_name in self.available_tools:
            if tool_name in self.tools_registry:
                tool = self.tools_registry[tool_name]
                # 检查工具是否健康
                if hasattr(tool, 'status') and tool.status.value == 'ready':
                    return tool_name
        
        # 如果没有准备好的工具，返回第一个可用的工具
        for tool_name in self.available_tools:
            if tool_name in self.tools_registry:
                return tool_name
        
        return None
    
    async def _call_tool(self, tool_name: str, task_description: str, context_data: Dict[str, Any], context: AgentContext):
        """调用工具"""
        try:
            # 构建工具调用参数
            tool_params = {
                "task": task_description,
                "context": context_data
            }
            
            # 调用BaseAgent的use_tool方法
            result = await context.agent_instance.use_tool(tool_name, "execute", tool_params)
            return result
            
        except Exception as e:
            logger.error(f"工具调用失败: {tool_name}, 错误: {e}")
            return None
    
    async def validate_input(self, input_data: Any) -> bool:
        """验证输入数据"""
        try:
            if isinstance(input_data, str):
                return len(input_data.strip()) > 0
            elif isinstance(input_data, dict):
                return "task_description" in input_data or len(str(input_data).strip()) > 0
            else:
                return len(str(input_data).strip()) > 0
        except Exception:
            return False
    
    def add_tool(self, tool_name: str) -> None:
        """添加工具到可用列表"""
        if tool_name not in self.available_tools:
            self.available_tools.append(tool_name)
            logger.info(f"添加工具: {tool_name} 到 {self.metadata.name}")
    
    def remove_tool(self, tool_name: str) -> None:
        """从可用列表中移除工具"""
        if tool_name in self.available_tools:
            self.available_tools.remove(tool_name)
            logger.info(f"移除工具: {tool_name} 从 {self.metadata.name}")


class CustomCodeAgent(BaseStepAgent):
    """自定义代码Agent"""
    
    def __init__(self, 
                 name: str, 
                 language: str = "python", 
                 allowed_libraries: List[str] = None, 
                 code_template: str = "",
                 execution_timeout: int = 30):
        """
        初始化自定义代码Agent
        
        Args:
            name: Agent名称
            language: 编程语言
            allowed_libraries: 允许的库列表
            code_template: 代码模板
            execution_timeout: 执行超时时间
        """
        metadata = AgentMetadata(
            name=name,
            description=f"自定义代码Agent: {name}",
            capabilities=[AgentCapability.CODE_EXECUTION],
            input_schema={
                "task_description": {"type": "string", "required": True, "description": "任务描述"},
                "input_data": {"type": "object", "required": False, "description": "输入数据"},
                "expected_output_format": {"type": "string", "required": False, "description": "期望输出格式"},
                "constraints": {"type": "array", "required": False, "description": "约束条件"},
                "libraries_allowed": {"type": "array", "required": False, "description": "允许的库"}
            },
            output_schema={
                "success": {"type": "boolean", "description": "是否成功"},
                "result": {"type": "object", "description": "执行结果"},
                "code_generated": {"type": "string", "description": "生成的代码"},
                "execution_info": {"type": "object", "description": "执行信息"},
                "stdout": {"type": "string", "description": "标准输出"},
                "stderr": {"type": "string", "description": "错误输出"},
                "error_message": {"type": "string", "description": "错误信息"}
            }
        )
        super().__init__(metadata)
        
        self.language = language
        self.allowed_libraries = allowed_libraries or []
        self.code_template = code_template
        self.execution_timeout = execution_timeout
        self.provider = None
        
        logger.info(f"创建自定义代码Agent: {name}, 语言: {language}")
    
    async def initialize(self, context: AgentContext) -> bool:
        """初始化自定义Code Agent"""
        try:
            if not context.agent_instance:
                logger.error("BaseAgent实例未提供")
                return False
            
            # 从BaseAgent获取provider
            self.provider = context.agent_instance.provider
            if not self.provider:
                logger.error("Provider未设置")
                return False
            
            self.is_initialized = True
            logger.info(f"自定义代码Agent初始化成功: {self.metadata.name}")
            return True
            
        except Exception as e:
            logger.error(f"自定义代码Agent初始化失败: {e}")
            return False
    
    async def execute(self, input_data: Any, context: AgentContext) -> Any:
        """执行自定义代码生成"""
        try:
            if not self.is_initialized:
                await self.initialize(context)
            
            # 处理输入数据
            if isinstance(input_data, str):
                task_description = input_data
                data_input = {}
                expected_output = ""
                constraints = []
            elif isinstance(input_data, dict):
                task_description = input_data.get("task_description", str(input_data))
                data_input = input_data.get("input_data", {})
                expected_output = input_data.get("expected_output_format", "")
                constraints = input_data.get("constraints", [])
            else:
                task_description = str(input_data)
                data_input = {}
                expected_output = ""
                constraints = []
            
            # 构建代码生成提示
            prompt = self._build_code_generation_prompt(
                task_description, data_input, expected_output, constraints
            )
            
            messages = [
                {"role": "system", "content": f"你是一个专业的{self.language}程序员，请生成高质量、安全的代码。"},
                {"role": "user", "content": prompt}
            ]
            
            # 生成代码
            response = await self.provider.generate_text(messages, max_tokens=1000)
            
            if response:
                # 提取代码（简单实现，实际可能需要更复杂的处理）
                code = self._extract_code_from_response(response)
                
                # 验证代码安全性
                if not self._validate_code_security(code):
                    return CodeAgentOutput(
                        success=False,
                        result=None,
                        code_generated=code,
                        error_message="代码安全检查失败"
                    )
                
                return CodeAgentOutput(
                    success=True,
                    result={"generated_code": code, "language": self.language},
                    code_generated=code,
                    execution_info={
                        "language": self.language,
                        "libraries": self.allowed_libraries,
                        "template_used": bool(self.code_template)
                    }
                )
            else:
                return CodeAgentOutput(
                    success=False,
                    result=None,
                    code_generated="",
                    error_message="LLM返回空响应"
                )
                
        except Exception as e:
            logger.error(f"自定义代码Agent执行失败: {e}")
            return CodeAgentOutput(
                success=False,
                result=None,
                code_generated="",
                error_message=str(e)
            )
    
    def _build_code_generation_prompt(self, task_description: str, data_input: Dict[str, Any], 
                                    expected_output: str, constraints: List[str]) -> str:
        """构建代码生成提示"""
        prompt_parts = [
            f"请根据以下任务描述生成{self.language}代码：",
            f"任务描述：{task_description}",
        ]
        
        if data_input:
            prompt_parts.append(f"输入数据：{data_input}")
        
        if expected_output:
            prompt_parts.append(f"期望输出格式：{expected_output}")
        
        if self.allowed_libraries:
            prompt_parts.append(f"只能使用以下库：{', '.join(self.allowed_libraries)}")
        
        if constraints:
            prompt_parts.append(f"约束条件：{'; '.join(constraints)}")
        
        prompt_parts.extend([
            "要求：",
            "1. 代码应该是完整可执行的",
            "2. 包含必要的错误处理",
            "3. 添加适当的注释",
            "4. 遵循最佳实践"
        ])
        
        if self.code_template:
            prompt_parts.append(f"代码模板：\n{self.code_template}")
        
        prompt_parts.append("请生成代码：")
        
        return "\n\n".join(prompt_parts)
    
    def _extract_code_from_response(self, response: str) -> str:
        """从LLM响应中提取代码"""
        # 简单的代码提取逻辑
        # 寻找代码块标记
        if "```" in response:
            # 提取代码块
            parts = response.split("```")
            if len(parts) >= 3:
                # 通常第二个部分是代码
                code_part = parts[1]
                # 移除语言标识符
                lines = code_part.split('\n')
                if lines and lines[0].strip().lower() in ['python', 'py', 'javascript', 'js', 'java', 'c++', 'cpp']:
                    code = '\n'.join(lines[1:])
                else:
                    code = code_part
                return code.strip()
        
        # 如果没有代码块标记，返回整个响应
        return response.strip()
    
    def _validate_code_security(self, code: str) -> bool:
        """验证代码安全性"""
        # 简单的安全检查
        dangerous_patterns = [
            'import os', 'import sys', 'import subprocess', 'import shutil',
            'exec(', 'eval(', '__import__', 'open(', 'file(',
            'input(', 'raw_input(', 'compile(', 'reload('
        ]
        
        code_lower = code.lower()
        
        # 检查是否包含危险模式
        for pattern in dangerous_patterns:
            if pattern in code_lower:
                # 如果库在允许列表中，则允许
                if pattern.startswith('import '):
                    library = pattern.split(' ')[1]
                    if library in self.allowed_libraries:
                        continue
                logger.warning(f"代码包含潜在危险模式: {pattern}")
                return False
        
        return True
    
    async def validate_input(self, input_data: Any) -> bool:
        """验证输入数据"""
        try:
            if isinstance(input_data, str):
                return len(input_data.strip()) > 0
            elif isinstance(input_data, dict):
                return "task_description" in input_data or len(str(input_data).strip()) > 0
            else:
                return len(str(input_data).strip()) > 0
        except Exception:
            return False
    
    def add_library(self, library: str) -> None:
        """添加允许的库"""
        if library not in self.allowed_libraries:
            self.allowed_libraries.append(library)
            logger.info(f"添加库: {library} 到 {self.metadata.name}")
    
    def remove_library(self, library: str) -> None:
        """移除允许的库"""
        if library in self.allowed_libraries:
            self.allowed_libraries.remove(library)
            logger.info(f"移除库: {library} 从 {self.metadata.name}")
    
    def update_code_template(self, template: str) -> None:
        """更新代码模板"""
        self.code_template = template
        logger.info(f"更新代码模板: {self.metadata.name}")