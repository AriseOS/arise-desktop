"""
Code Agent - 代码生成和执行Agent
"""
import ast
import io
import sys
import json
from contextlib import redirect_stdout, redirect_stderr
from typing import Any, Dict, List

from .base_agent import BaseStepAgent, AgentMetadata
from ..core.schemas import (
    AgentCapability, AgentContext,
    CodeAgentInput, CodeAgentOutput
)


class CodeAgent(BaseStepAgent):
    """代码生成执行Agent"""
    
    def __init__(self, code_type: str = "python"):
        metadata = AgentMetadata(
            name=f"code_agent_{code_type}",
            description=f"代码生成和执行Agent，支持{code_type}代码的智能生成、安全执行和结果返回",
            capabilities=[AgentCapability.CODE_EXECUTION, AgentCapability.DATA_PROCESSING],
            input_schema={
                "task_description": {"type": "string", "required": True},
                "input_data": {"type": "any", "required": True},
                "expected_output_format": {"type": "string", "required": True},
                "constraints": {"type": "array", "required": False},
                "libraries_allowed": {"type": "array", "required": False}
            },
            output_schema={
                "success": {"type": "boolean"},
                "result": {"type": "any"},
                "code_generated": {"type": "string"},
                "execution_info": {"type": "object"},
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
                "error_message": {"type": "string"}
            }
        )
        super().__init__(metadata)
        self.code_type = code_type
        self.provider = None
    
    async def initialize(self, context: AgentContext) -> bool:
        """初始化Code Agent"""
        if not context.agent_instance:
            return False
        
        # 验证Provider是否可用
        if not hasattr(context.agent_instance, 'provider') or not context.agent_instance.provider:
            if context.logger:
                context.logger.error("Provider不可用")
            return False
        
        # 验证代码执行环境
        if self.code_type == "python":
            try:
                import ast
                self.provider = context.agent_instance.provider
                self.is_initialized = True
                return True
            except ImportError:
                if context.logger:
                    context.logger.error("Python AST模块不可用")
                return False
        
        return False
    
    async def validate_input(self, input_data: Any) -> bool:
        """验证输入数据"""
        if isinstance(input_data, CodeAgentInput):
            return True
        if not isinstance(input_data, dict):
            return False
        required_fields = ["task_description", "input_data", "expected_output_format"]
        return all(field in input_data for field in required_fields)
    
    async def execute(self, input_data: Any, context: AgentContext) -> CodeAgentOutput:
        """执行代码生成和执行"""
        try:
            # 解析输入
            if isinstance(input_data, dict):
                code_input = CodeAgentInput(**input_data)
            else:
                code_input = input_data
            
            # Step 1: LLM生成代码
            generated_code = await self._generate_code(code_input, context)
            
            # Step 2: 代码安全检查
            if not await self._is_code_safe(generated_code, code_input, context):
                return CodeAgentOutput(
                    success=False,
                    result=None,
                    code_generated=generated_code,
                    execution_info={},
                    stdout="",
                    stderr="",
                    error_message="生成的代码不安全"
                )
            
            # Step 3: 执行代码
            if self.code_type == "python":
                return await self._execute_python_code(generated_code, code_input, context)
            else:
                raise ValueError(f"不支持的代码类型: {self.code_type}")
                
        except Exception as e:
            if context.logger:
                context.logger.error(f"代码执行失败: {str(e)}")
            
            return CodeAgentOutput(
                success=False,
                result=None,
                code_generated="",
                execution_info={},
                stdout="",
                stderr="",
                error_message=str(e)
            )
    
    async def _generate_code(self, input_data: CodeAgentInput, context: AgentContext) -> str:
        """LLM生成代码"""
        code_prompt = f"""
任务描述: {input_data.task_description}
输入数据: {input_data.input_data}
期望输出格式: {input_data.expected_output_format}
约束条件: {input_data.constraints}
允许使用的库: {input_data.libraries_allowed}

请生成Python代码来完成这个任务。要求：
1. 代码要能处理给定的输入数据
2. 输出格式要符合期望
3. 只使用允许的库
4. 代码要安全，不能有恶意操作
5. 最后要将结果赋值给变量'result'
6. 输入数据已经定义在变量'input_data'中

只返回Python代码，不要解释：
```python
# 你的代码
```
"""
        
        response = await self.provider.generate_response(
            system_prompt="你是一个专业的Python代码生成器。请严格按照要求生成安全、有效的Python代码。",
            user_prompt=code_prompt
        )
        
        # 提取代码块
        content = response.strip()
        if "```python" in content:
            code = content.split("```python")[1].split("```")[0].strip()
        elif "```" in content:
            code = content.split("```")[1].strip()
        else:
            code = content
        
        return code
    
    async def _is_code_safe(self, code: str, input_data: CodeAgentInput, context: AgentContext) -> bool:
        """代码安全检查"""
        try:
            # 解析AST
            tree = ast.parse(code)
            
            # 检查危险操作
            dangerous_nodes = []
            for node in ast.walk(tree):
                # 检查导入（只在有限制时检查）
                if isinstance(node, ast.Import) and input_data.libraries_allowed:
                    for alias in node.names:
                        if alias.name not in input_data.libraries_allowed:
                            dangerous_nodes.append(f"未授权的导入: {alias.name}")
                
                if isinstance(node, ast.ImportFrom) and input_data.libraries_allowed:
                    if node.module not in input_data.libraries_allowed:
                        dangerous_nodes.append(f"未授权的导入: {node.module}")
                
                # 检查危险函数调用
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ['exec', 'eval', 'open', '__import__']:
                            dangerous_nodes.append(f"危险函数调用: {node.func.id}")
                    elif isinstance(node.func, ast.Attribute):
                        if node.func.attr in ['system', 'popen', 'spawn']:
                            dangerous_nodes.append(f"危险方法调用: {node.func.attr}")
            
            if dangerous_nodes:
                if context.logger:
                    context.logger.warning(f"代码安全检查失败: {dangerous_nodes}")
                return False
            
            return True
            
        except SyntaxError as e:
            if context.logger:
                context.logger.error(f"代码语法错误: {str(e)}")
            return False
    
    async def _execute_python_code(
        self, 
        code: str, 
        input_data: CodeAgentInput, 
        context: AgentContext
    ) -> CodeAgentOutput:
        """执行Python代码"""
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        try:
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                # 编译代码
                compiled_code = compile(code, '<string>', 'exec')
                
                # 准备执行环境
                globals_dict = {
                    '__builtins__': {
                        'print': print,
                        'len': len,
                        'str': str,
                        'int': int,
                        'float': float,
                        'bool': bool,
                        'list': list,
                        'dict': dict,
                        'tuple': tuple,
                        'set': set,
                        'range': range,
                        'enumerate': enumerate,
                        'zip': zip,
                        'sum': sum,
                        'max': max,
                        'min': min,
                        'abs': abs,
                        'round': round,
                        'sorted': sorted,
                        'reversed': reversed,
                        '__import__': __import__,  # 允许import
                    }
                }
                
                # 添加允许的库
                for lib in input_data.libraries_allowed:
                    try:
                        if lib == 're':
                            import re
                            globals_dict['re'] = re
                        elif lib == 'json':
                            import json
                            globals_dict['json'] = json
                        elif lib == 'math':
                            import math
                            globals_dict['math'] = math
                        elif lib == 'collections':
                            import collections
                            globals_dict['collections'] = collections
                        elif lib == 'datetime':
                            import datetime
                            globals_dict['datetime'] = datetime
                    except ImportError:
                        pass
                
                # 添加输入数据
                locals_dict = {'input_data': input_data.input_data}
                
                # 执行代码
                exec(compiled_code, globals_dict, locals_dict)
                
                # 获取结果
                result = locals_dict.get('result', None)
                
            return CodeAgentOutput(
                success=True,
                result=result,
                code_generated=code,
                execution_info={
                    "locals_vars": list(locals_dict.keys()),
                    "execution_time": 0  # 这里可以添加实际的执行时间测量
                },
                stdout=stdout_capture.getvalue(),
                stderr=stderr_capture.getvalue()
            )
            
        except Exception as e:
            return CodeAgentOutput(
                success=False,
                result=None,
                code_generated=code,
                execution_info={},
                stdout=stdout_capture.getvalue(),
                stderr=stderr_capture.getvalue(),
                error_message=str(e)
            )