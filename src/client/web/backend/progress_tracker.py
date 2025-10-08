"""
构建进度追踪器 - 捕获 AgentBuilder 内部日志并实时推送
"""
import logging
import asyncio
import sys
import os
from typing import Optional, Callable, Dict, Any
from datetime import datetime

# 添加 agent_builder 路径以便导入
agent_builder_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../agent_builder'))
sys.path.insert(0, agent_builder_path)


class ProgressTracker:
    """构建进度追踪器 - 捕获真实 AgentBuilder 日志"""
    
    def __init__(self, build_id: str, websocket_manager=None):
        self.build_id = build_id
        self.websocket_manager = websocket_manager
        self.step_counter = 0
        self.current_step = "initializing"
        
        # 捕获所有 AgentBuilder 相关的日志
        self.agent_builder_loggers = [
            "agent_builder.core.agent_builder",
            "agent_builder.core.requirement_parser", 
            "agent_builder.core.agent_designer",
            "agent_builder.core.workflow_builder",
            "agent_builder.core.code_generator"
        ]
        
        # 创建自定义日志处理器来捕获所有相关日志
        self.handlers = []
        for logger_name in self.agent_builder_loggers:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.INFO)
            
            # 移除现有处理器，避免重复
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)
                
            # 添加我们的处理器
            handler = AgentBuilderLogHandler(self)
            logger.addHandler(handler)
            self.handlers.append((logger, handler))
    
    async def log_step(self, step: str, message: str, level: str = "info"):
        """记录构建步骤"""
        self.step_counter += 1
        
        # 格式化消息
        formatted_message = f"🔄 [{step.upper()}] {message}"
        
        print(f"Progress: {formatted_message}")  # 后端日志
        
        # 通过 WebSocket 推送
        if self.websocket_manager:
            progress_data = {
                "type": "progress_update",
                "build_id": self.build_id,
                "step": step,
                "message": formatted_message,
                "level": level,
                "step_number": self.step_counter,
                "timestamp": datetime.utcnow().isoformat()
            }
            await self.websocket_manager.broadcast_build_progress(
                self.build_id, progress_data
            )
    
    def parse_log_message(self, message: str) -> tuple[str, str]:
        """解析日志消息，提取步骤和描述"""
        # 定义步骤映射
        step_patterns = {
            "开始从自然语言描述构建Agent": ("initializing", "🚀 初始化 AgentBuilder"),
            "解析用户需求": ("requirement_parsing", "📝 解析用户需求，识别核心功能和约束"),
            "提取执行步骤": ("step_extraction", "🔍 分析需求，提取执行步骤"),
            "判断Agent类型": ("agent_type_analysis", "🏗️ 分析Agent类型，设计架构"),
            "生成StepAgent规格": ("step_agent_generation", "🤖 生成StepAgent规格和配置"),
            "构建工作流": ("workflow_building", "⚙️ 构建工作流，连接各个步骤"),
            "注册工作流": ("workflow_registration", "📋 注册工作流，完成配置"),
            "生成Python代码": ("code_generation", "💻 生成Python代码，实现业务逻辑"),
            "保存生成的文件": ("file_saving", "📦 保存生成文件，创建元数据"),
            "测试生成的代码": ("testing", "🧪 测试生成的代码，验证语法和功能"),
            "Agent构建完成": ("completed", "🎉 Agent 构建完成！")
        }
        
        # 匹配日志消息中的关键词
        for pattern, (step, description) in step_patterns.items():
            if pattern in message:
                self.current_step = step
                return step, description
        
        # 如果没有匹配到，使用当前步骤
        return self.current_step, message
    
    def cleanup(self):
        """清理资源"""
        for logger, handler in self.handlers:
            logger.removeHandler(handler)
        self.handlers.clear()


class AgentBuilderLogHandler(logging.Handler):
    """自定义日志处理器，用于捕获真实 AgentBuilder 日志"""
    
    def __init__(self, progress_tracker: ProgressTracker):
        super().__init__()
        self.progress_tracker = progress_tracker
    
    def emit(self, record):
        """处理日志记录"""
        try:
            # 格式化日志消息
            message = self.format(record)
            
            # 在控制台显示原始日志
            print(f"🔍 [AgentBuilder] {record.name}: {message}")
            
            # 解析日志消息，获取步骤和描述
            step, description = self.progress_tracker.parse_log_message(message)
            
            # 根据日志级别确定级别
            if record.levelno >= logging.ERROR:
                level = "error"
            elif record.levelno >= logging.WARNING:
                level = "warning"
            else:
                level = "info"
            
            # 在控制台显示解析后的步骤
            print(f"📊 [进度追踪] 步骤: {step}, 描述: {description}")
            
            # 异步发送进度更新
            asyncio.create_task(
                self.progress_tracker.log_step(step, description, level)
            )
            
        except Exception as e:
            # 避免日志处理器本身出错
            print(f"❌ 日志处理器错误: {e}")


def create_progress_tracker(build_id: str, websocket_manager=None) -> ProgressTracker:
    """创建进度追踪器"""
    return ProgressTracker(build_id, websocket_manager)