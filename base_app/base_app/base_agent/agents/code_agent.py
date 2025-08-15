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
    AgentContext, AgentInput, AgentOutput
)


class CodeAgent(BaseStepAgent):
    """代码生成执行Agent"""
    
    def __init__(self, code_type: str = "python"):
        metadata = AgentMetadata(
            name=f"code_agent_{code_type}",
            description=f"代码生成和执行Agent，支持{code_type}代码",
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
        
        self.provider = context.agent_instance.provider
        self.is_initialized = True
        return True
    
    async def validate_input(self, input_data: Any) -> bool:
        """验证输入数据"""
        if isinstance(input_data, AgentInput):
            return True
        if isinstance(input_data, dict):
            return "instruction" in input_data
        return False
    
    async def execute(self, input_data: Any, context: AgentContext) -> AgentOutput:
        """执行代码生成和执行"""
        try:
            # 确保输入是AgentInput类型
            if isinstance(input_data, dict):
                agent_input = AgentInput(**input_data)
            else:
                agent_input = input_data
            
            # 从AgentInput解析代码生成参数
            code_params = self._parse_code_params(agent_input)
            
            # Step 1: LLM生成代码
            generated_code = await self._generate_code(code_params, context)
            
            # Step 2: 代码安全检查
            if not await self._is_code_safe(generated_code, code_params, context):
                return AgentOutput(
                    success=False,
                    data={
                        "code_generated": generated_code,
                        "error_message": "生成的代码不安全"
                    },
                    message="代码安全检查失败"
                )
            
            # Step 3: 执行代码
            if self.code_type == "python":
                return await self._execute_python_code(generated_code, code_params, context)
            else:
                return AgentOutput(
                    success=False,
                    data={},
                    message=f"不支持的代码类型: {self.code_type}"
                )
                
        except Exception as e:
            if context.logger:
                context.logger.error(f"代码执行失败: {str(e)}")
            
            return AgentOutput(
                success=False,
                data={},
                message=f"代码执行失败: {str(e)}"
            )
    
    def _parse_code_params(self, agent_input: AgentInput) -> Dict[str, Any]:
        """从AgentInput解析代码生成参数"""
        return {
            "task_description": agent_input.instruction,
            "input_data": agent_input.data.get("input_data", {}),
            "expected_output_format": agent_input.metadata.get("expected_output_format", "any"),
            "constraints": agent_input.metadata.get("constraints", []),
            "libraries_allowed": agent_input.metadata.get("libraries_allowed", ["json", "math", "datetime", "re"])
        }
    
    async def _generate_code(self, code_params: Dict[str, Any], context: AgentContext) -> str:
        """LLM生成代码"""
        code_prompt = f"""
任务描述: {code_params['task_description']}
输入数据: {code_params['input_data']}
期望输出格式: {code_params['expected_output_format']}
约束条件: {code_params.get('constraints', [])}
允许的库: {code_params.get('libraries_allowed', [])}

请生成Python代码来完成这个任务。

要求：
1. 代码应该是完整可执行的
2. 使用提供的输入数据
3. 返回指定格式的结果
4. 只使用允许的库
5. 遵守所有约束条件
6. 将最终结果赋值给变量 'result'

请只返回Python代码，不要包含解释或其他文本：
"""
        
        try:
            response = await self.provider.generate_response(
                system_prompt="你是一个专业的Python代码生成专家。请根据要求生成安全、高效的Python代码。",
                user_prompt=code_prompt
            )
            
            # 清理响应，提取代码
            code = self._extract_code_from_response(response)
            
            if context.logger:
                context.logger.info(f"生成的代码: {code}")
            
            return code
            
        except Exception as e:
            if context.logger:
                context.logger.error(f"代码生成失败: {str(e)}")
            raise e
    
    def _extract_code_from_response(self, response: str) -> str:
        """从LLM响应中提取代码"""
        response = response.strip()
        
        # 如果包含代码块标记，提取其中的代码
        if "```python" in response:
            start = response.find("```python") + 9
            end = response.find("```", start)
            if end != -1:
                return response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            if end != -1:
                return response[start:end].strip()
        
        return response
    
    async def _is_code_safe(self, code: str, code_params: Dict[str, Any], context: AgentContext) -> bool:
        """检查代码安全性"""
        try:
            # 解析AST检查危险操作
            tree = ast.parse(code)
            
            # 检查不允许的操作
            dangerous_names = {
                'exec', 'eval', 'compile', 'open', '__import__', 
                'input', 'raw_input', 'file', 'execfile', 'reload'
            }
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id in dangerous_names:
                    if context.logger:
                        context.logger.warning(f"代码包含危险操作: {node.id}")
                    return False
                
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name not in code_params.get('libraries_allowed', []):
                            if context.logger:
                                context.logger.warning(f"代码导入了不允许的库: {alias.name}")
                            return False
                
                if isinstance(node, ast.ImportFrom):
                    if node.module and node.module not in code_params.get('libraries_allowed', []):
                        if context.logger:
                            context.logger.warning(f"代码导入了不允许的库: {node.module}")
                        return False
            
            return True
            
        except SyntaxError as e:
            if context.logger:
                context.logger.error(f"代码语法错误: {str(e)}")
            return False
        except Exception as e:
            if context.logger:
                context.logger.error(f"代码安全检查失败: {str(e)}")
            return False
    
    async def _execute_python_code(
        self, 
        code: str, 
        code_params: Dict[str, Any], 
        context: AgentContext
    ) -> AgentOutput:
        """执行Python代码"""
        
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        try:
            # 准备执行环境
            exec_globals = {
                '__builtins__': {
                    'len': len, 'str': str, 'int': int, 'float': float, 'bool': bool,
                    'list': list, 'dict': dict, 'tuple': tuple, 'set': set,
                    'min': min, 'max': max, 'sum': sum, 'abs': abs, 'round': round,
                    'range': range, 'enumerate': enumerate, 'zip': zip,
                    'print': print, 'type': type, 'isinstance': isinstance
                }
            }
            
            # 添加允许的库
            for lib in code_params.get('libraries_allowed', []):
                if lib == 'json':
                    exec_globals['json'] = json
                elif lib == 'math':
                    import math
                    exec_globals['math'] = math
                elif lib == 'datetime':
                    import datetime
                    exec_globals['datetime'] = datetime
                elif lib == 're':
                    import re
                    exec_globals['re'] = re
            
            # 添加输入数据到执行环境
            exec_globals['input_data'] = code_params['input_data']
            
            exec_locals = {}
            
            # 重定向输出
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                exec(code, exec_globals, exec_locals)
            
            # 获取结果
            result = exec_locals.get('result', None)
            stdout_content = stdout_capture.getvalue()
            stderr_content = stderr_capture.getvalue()
            
            return AgentOutput(
                success=True,
                data={
                    "result": result,
                    "code_generated": code,
                    "execution_info": {
                        "stdout": stdout_content,
                        "stderr": stderr_content,
                        "variables": list(exec_locals.keys())
                    }
                },
                message="代码执行成功"
            )
            
        except Exception as e:
            stderr_content = stderr_capture.getvalue()
            if context.logger:
                context.logger.error(f"代码执行异常: {str(e)}")
            
            return AgentOutput(
                success=False,
                data={
                    "code_generated": code,
                    "execution_info": {
                        "stdout": stdout_capture.getvalue(),
                        "stderr": stderr_content,
                        "error": str(e)
                    }
                },
                message=f"代码执行失败: {str(e)}"
            )