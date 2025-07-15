"""
WorkflowBuilder - 将AgentBuilder的StepDesign转换为BaseAgent兼容的Workflow
"""

import json
import yaml
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from .schemas import StepDesign, LLMConfig


class WorkflowBuilder:
    """工作流组装器 - 将steps组合成BaseAgent兼容的Workflow"""
    
    def __init__(self):
        pass
    
    async def build_workflow(self, steps: List[StepDesign], agent_specs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        构建工作流 - 集成BaseAgent的工作流引擎
        - 将steps组合成完整的Workflow
        - 配置步骤间的数据流转和依赖关系
        - 生成YAML格式的工作流配置
        """
        
        # 生成工作流基本信息
        workflow_name = f"generated_workflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 构建基础元数据
        workflow_config = {
            "apiVersion": "agentcrafter.io/v1",
            "kind": "Workflow",
            "metadata": {
                "name": workflow_name,
                "description": f"AgentBuilder自动生成的工作流，包含{len(steps)}个步骤",
                "version": "1.0.0",
                "author": "AgentBuilder",
                "tags": ["agent-builder", "auto-generated"],
                "created_at": datetime.now().isoformat()
            }
        }
        
        # 分析步骤并构建输入输出schema
        inputs, outputs = self._build_io_schemas(steps)
        workflow_config["inputs"] = inputs
        workflow_config["outputs"] = outputs
        
        # 全局配置
        workflow_config["config"] = {
            "max_execution_time": 600,
            "enable_parallel": False,  # 默认顺序执行
            "enable_cache": True,
            "timeout_strategy": "fail_fast"
        }
        
        # 构建工作流步骤
        workflow_steps = []
        dependencies = {}
        
        for i, step in enumerate(steps):
            step_config = self._build_step_config(step, i, agent_specs)
            workflow_steps.append(step_config)
            
            # 构建依赖关系（顺序执行）
            if i > 0:
                dependencies[step.step_id] = [steps[i-1].step_id]
        
        workflow_config["steps"] = workflow_steps
        
        # 执行策略配置
        workflow_config["execution"] = {
            "dependencies": dependencies,
            "flow_control": {
                "early_exit": {
                    "condition": "false",  # 默认不早期退出
                    "description": "不使用早期退出"
                },
                "loops": [],
                "branch_merge": {
                    "strategy": "collect_all",
                    "timeout": 300
                }
            }
        }
        
        # 错误处理配置
        workflow_config["error_handling"] = {
            "global_strategy": "fail_gracefully",
            "fallback_response": "抱歉，工作流执行遇到问题，请检查配置或联系技术支持。"
        }
        
        # 监控配置
        workflow_config["monitoring"] = {
            "enable_step_timing": True,
            "enable_variable_tracking": True,
            "log_level": "INFO",
            "metrics": [
                "step_execution_time",
                "total_execution_time", 
                "success_rate"
            ]
        }
        
        # 缓存配置
        workflow_config["caching"] = {
            "enable": True,
            "ttl": 3600,
            "cache_key_fields": ["user_input"],
            "exclude_fields": ["user_id"]
        }
        
        return workflow_config
    
    def _build_io_schemas(self, steps: List[StepDesign]) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """构建输入输出schema"""
        
        # 默认输入schema
        inputs = {
            "user_input": {
                "type": "string",
                "description": "用户输入",
                "required": True
            },
            "user_id": {
                "type": "string",
                "description": "用户ID",
                "required": False,
                "default": "anonymous"
            }
        }
        
        # 分析步骤的期望输入，添加额外输入字段
        for step in steps:
            expected_input = step.agent_config.get('expected_input', '')
            if expected_input and expected_input != '用户的自然语言输入':
                # 为特殊输入需求添加字段
                input_key = f"{step.name.lower().replace(' ', '_')}_input"
                if input_key not in inputs:
                    inputs[input_key] = {
                        "type": "string",
                        "description": expected_input,
                        "required": False
                    }
        
        # 默认输出schema
        outputs = {
            "final_response": {
                "type": "string", 
                "description": "最终响应结果"
            },
            "execution_summary": {
                "type": "object",
                "description": "执行摘要信息"
            }
        }
        
        return inputs, outputs
    
    def _build_step_config(self, step: StepDesign, index: int, agent_specs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """构建单个步骤的配置"""
        
        # 查找对应的agent规格
        agent_spec = None
        for spec in agent_specs:
            if spec.get('step_id') == step.step_id:
                agent_spec = spec
                break
        
        # 基础步骤配置
        step_config = {
            "id": step.step_id,
            "name": step.name,
            "agent_type": step.agent_type,
            "description": step.description,
            "agent_instruction": step.description,
            "timeout": 120,
            "retry_count": 1
        }
        
        # 根据Agent类型配置特定参数
        if step.agent_type == "text":
            step_config.update(self._build_text_agent_config(step, agent_spec))
        elif step.agent_type == "tool":
            step_config.update(self._build_tool_agent_config(step, agent_spec))
        elif step.agent_type == "code":
            step_config.update(self._build_code_agent_config(step, agent_spec))
        elif step.agent_type == "custom":
            step_config.update(self._build_custom_agent_config(step, agent_spec))
        
        # 构建输入输出映射
        step_config["inputs"] = self._build_step_inputs(step, index)
        step_config["outputs"] = self._build_step_outputs(step, index)
        
        # 条件执行（如果有）
        if step.agent_config.get('condition'):
            step_config["condition"] = {
                "expression": step.agent_config['condition'],
                "description": f"步骤{step.name}的执行条件"
            }
        
        return step_config
    
    def _build_text_agent_config(self, step: StepDesign, agent_spec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """构建Text Agent配置"""
        
        config = {
            "text": {
                "response_style": "professional",
                "max_length": 500,
                "language": "zh"
            }
        }
        
        # 从agent_config获取参数
        if step.agent_config.get('key_parameters'):
            params = step.agent_config['key_parameters']
            if 'temperature=' in params:
                # 解析temperature参数（简单解析）
                temp_str = params.split('temperature=')[1].split()[0]
                try:
                    temperature = float(temp_str)
                    config["text"]["temperature"] = temperature
                except:
                    pass
        
        return config
    
    def _build_tool_agent_config(self, step: StepDesign, agent_spec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """构建Tool Agent配置"""
        
        # 获取工具列表
        existing_tools = step.agent_config.get('existing_tools', [])
        tool_approach = step.agent_config.get('tool_approach', 'reuse_existing')
        
        # 基础工具配置
        available_tools = ["browser_use", "android_use", "llm_extract"]
        
        if existing_tools:
            # 使用指定的工具
            allowed_tools = [tool for tool in existing_tools if tool in available_tools]
        else:
            # 默认允许所有工具
            allowed_tools = available_tools
        
        config = {
            "tools": {
                "allowed": allowed_tools,
                "fallback": allowed_tools[:1] if allowed_tools else ["browser_use"],
                "confidence_threshold": 0.8,
                "max_tools_per_step": 3
            }
        }
        
        # 如果需要新工具实现，添加注释
        if tool_approach == 'implement_new':
            config["tools"]["_note"] = f"需要实现新工具: {step.agent_config.get('new_tool_requirements', '')}"
        
        return config
    
    def _build_code_agent_config(self, step: StepDesign, agent_spec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """构建Code Agent配置"""
        
        config = {
            "code": {
                "allowed_libraries": ["pandas", "numpy", "matplotlib", "requests", "json", "re"],
                "expected_output_format": step.agent_config.get('expected_output', '分析结果'),
                "execution_timeout": 60,
                "memory_limit_mb": 512
            },
            "constraints": [
                "不能执行危险操作",
                "不能访问敏感数据", 
                "执行时间不超过60秒"
            ]
        }
        
        return config
    
    def _build_custom_agent_config(self, step: StepDesign, agent_spec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """构建Custom Agent配置"""
        
        config = {
            "custom": {
                "agent_class": "CustomAgent",
                "implementation_required": True
            }
        }
        
        # 如果有agent规格，添加详细配置
        if agent_spec and agent_spec.get('specification'):
            spec = agent_spec['specification']
            config["custom"].update({
                "agent_name": spec.get('agent_name', 'CustomAgent'),
                "required_capabilities": spec.get('required_capabilities', []),
                "tool_requirements": spec.get('tool_requirements', []),
                "implementation_guidance": spec.get('implementation_guidance', {})
            })
        
        return config
    
    def _build_step_inputs(self, step: StepDesign, index: int) -> Dict[str, Any]:
        """构建步骤输入配置"""
        
        # 基础输入
        inputs = {
            "task_description": "{{user_input}}"
        }
        
        # 第一个步骤直接使用用户输入
        if index == 0:
            inputs["context_data"] = {
                "user_input": "{{user_input}}",
                "user_id": "{{user_id}}"
            }
        else:
            # 后续步骤可能需要前面步骤的结果
            inputs["context_data"] = {
                "user_input": "{{user_input}}",
                "user_id": "{{user_id}}",
                "previous_results": "{{previous_step_result}}"
            }
        
        return inputs
    
    def _build_step_outputs(self, step: StepDesign, index: int) -> Dict[str, Any]:
        """构建步骤输出配置"""
        
        expected_output = step.agent_config.get('expected_output', '处理结果')
        
        outputs = {
            "result": f"step_{index}_result",
            "step_name": step.name,
            "execution_time": f"step_{index}_time"
        }
        
        # 根据Agent类型添加特定输出
        if step.agent_type == "tool":
            outputs.update({
                "tool_used": f"step_{index}_tool",
                "confidence": f"step_{index}_confidence"
            })
        elif step.agent_type == "code":
            outputs.update({
                "code_generated": f"step_{index}_code",
                "execution_info": f"step_{index}_exec_info"
            })
        
        return outputs
    
    async def register_workflow(self, workflow: Dict[str, Any]) -> str:
        """
        注册工作流 - 集成BaseAgent的注册系统
        - 将Workflow注册到BaseAgent系统
        - 配置工作流的元数据和生命周期
        """
        
        workflow_name = workflow["metadata"]["name"]
        
        # 生成YAML格式的工作流文件
        yaml_content = yaml.dump(workflow, default_flow_style=False, allow_unicode=True)
        
        # 在实际使用时，这里应该调用BaseAgent的workflow注册接口
        # 现在返回模拟的注册结果
        
        return {
            "workflow_id": workflow_name,
            "registration_status": "success", 
            "yaml_content": yaml_content,
            "file_path": f"workflows/generated/{workflow_name}.yaml",
            "steps_count": len(workflow.get("steps", [])),
            "estimated_execution_time": self._estimate_execution_time(workflow)
        }
    
    def _estimate_execution_time(self, workflow: Dict[str, Any]) -> int:
        """估算工作流执行时间（秒）"""
        
        steps = workflow.get("steps", [])
        total_time = 0
        
        for step in steps:
            # 根据Agent类型估算执行时间
            agent_type = step.get("agent_type", "text")
            if agent_type == "text":
                total_time += 10  # Text处理大约10秒
            elif agent_type == "tool":
                total_time += 30  # 工具调用大约30秒
            elif agent_type == "code":
                total_time += 45  # 代码执行大约45秒
            elif agent_type == "custom":
                total_time += 60  # 自定义Agent大约60秒
            else:
                total_time += 20  # 默认20秒
        
        return total_time
    
    def save_workflow_yaml(self, workflow: Dict[str, Any], file_path: str) -> None:
        """保存工作流为YAML文件"""
        
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(workflow, f, default_flow_style=False, allow_unicode=True)
    
    def validate_workflow(self, workflow: Dict[str, Any]) -> List[str]:
        """验证工作流配置"""
        
        errors = []
        
        # 检查必需字段
        required_fields = ["apiVersion", "kind", "metadata", "steps"]
        for field in required_fields:
            if field not in workflow:
                errors.append(f"缺少必需字段: {field}")
        
        # 检查步骤配置
        steps = workflow.get("steps", [])
        if not steps:
            errors.append("工作流必须包含至少一个步骤")
        
        step_ids = []
        for i, step in enumerate(steps):
            step_id = step.get("id")
            if not step_id:
                errors.append(f"步骤 {i} 缺少ID")
            elif step_id in step_ids:
                errors.append(f"步骤ID重复: {step_id}")
            else:
                step_ids.append(step_id)
            
            # 检查Agent类型
            agent_type = step.get("agent_type")
            if agent_type not in ["text", "tool", "code", "custom"]:
                errors.append(f"步骤 {step_id} 的Agent类型无效: {agent_type}")
        
        return errors
    
    def get_workflow_summary(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """获取工作流摘要信息"""
        
        steps = workflow.get("steps", [])
        agent_types = {}
        
        for step in steps:
            agent_type = step.get("agent_type", "unknown")
            agent_types[agent_type] = agent_types.get(agent_type, 0) + 1
        
        return {
            "name": workflow.get("metadata", {}).get("name", "unknown"),
            "description": workflow.get("metadata", {}).get("description", ""),
            "total_steps": len(steps),
            "agent_type_distribution": agent_types,
            "estimated_execution_time": self._estimate_execution_time(workflow),
            "complexity_score": self._calculate_complexity_score(workflow)
        }
    
    def _calculate_complexity_score(self, workflow: Dict[str, Any]) -> str:
        """计算工作流复杂度分数"""
        
        steps = workflow.get("steps", [])
        score = 0
        
        # 基于步骤数量
        score += len(steps) * 10
        
        # 基于Agent类型复杂度
        for step in steps:
            agent_type = step.get("agent_type", "text")
            if agent_type == "text":
                score += 5
            elif agent_type == "tool":
                score += 15
            elif agent_type == "code":
                score += 20
            elif agent_type == "custom":
                score += 30
        
        # 基于条件执行
        conditional_steps = sum(1 for step in steps if step.get("condition"))
        score += conditional_steps * 10
        
        # 返回复杂度等级
        if score < 50:
            return "low"
        elif score < 100:
            return "medium"
        elif score < 200:
            return "high"
        else:
            return "very_high"