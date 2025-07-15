"""
Agent 构建服务 - 集成 AgentBuilder 功能
"""
import sys
import os
import asyncio
import uuid
import json
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

# 添加 agent_builder 路径
agent_builder_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../agent_builder'))
sys.path.insert(0, agent_builder_path)

print(f"AgentBuilder 路径: {agent_builder_path}")
print(f"路径是否存在: {os.path.exists(agent_builder_path)}")

# 导入真实的 AgentBuilder
from core.agent_builder import AgentBuilder, build_agent
from core.schemas import LLMConfig
print("✅ AgentBuilder 导入成功")
from database import AgentBuildSession, GeneratedAgent
from progress_tracker import create_progress_tracker


class AgentBuildService:
    """Agent 构建服务"""
    
    def __init__(self):
        self.websocket_manager = None  # 将在运行时注入
        print("🚀 AgentBuildService 初始化中...")
        
        # 确认使用真实的 AgentBuilder
        print(f"✅ 使用真实的 AgentBuilder: {AgentBuilder}")
        print(f"✅ 使用真实的 LLMConfig: {LLMConfig}")
        
        # 默认LLM配置 - 实际使用时需要从环境变量获取
        self.default_llm_config = LLMConfig(
            provider="openai",
            model="gpt-4o", 
            api_key=os.getenv("OPENAI_API_KEY", "your-openai-key"),
            temperature=0.7
        )
        print("✅ AgentBuildService 初始化完成")
        self.output_base_dir = os.path.join(os.path.dirname(__file__), "../generated_agents")
        os.makedirs(self.output_base_dir, exist_ok=True)
    
    def set_websocket_manager(self, manager):
        """设置 WebSocket 管理器"""
        self.websocket_manager = manager
    
    async def start_agent_build(
        self, 
        user_id: int, 
        description: str, 
        agent_name: Optional[str] = None,
        db: Session = None
    ) -> Dict[str, Any]:
        """
        开始构建 Agent
        
        Args:
            user_id: 用户ID
            description: 需求描述
            agent_name: 可选的Agent名称
            db: 数据库会话
            
        Returns:
            构建信息字典
        """
        # 生成唯一的构建ID
        build_id = str(uuid.uuid4())
        
        # 创建构建会话记录
        build_session = AgentBuildSession(
            build_id=build_id,
            user_id=user_id,
            description=description,
            agent_name=agent_name,
            status="building",
            current_step="initializing",
            progress_message="正在初始化Agent构建..."
        )
        
        if db:
            db.add(build_session)
            db.commit()
        
        # 启动异步构建任务
        asyncio.create_task(self._build_agent_async(build_id, user_id, description, agent_name))
        
        return {
            "build_id": build_id,
            "status": "building",
            "message": "Agent构建已启动"
        }
    
    async def _build_agent_async(
        self, 
        build_id: str, 
        user_id: int, 
        description: str, 
        agent_name: Optional[str] = None
    ):
        """
        异步执行Agent构建
        """
        from database import SessionLocal
        db = SessionLocal()
        progress_tracker = None
        
        try:
            print(f"🚀 开始构建 Agent - Build ID: {build_id}")
            print(f"📝 用户描述: {description}")
            print(f"👤 用户ID: {user_id}")
            
            # 创建进度追踪器
            progress_tracker = create_progress_tracker(build_id, self.websocket_manager)
            
            print(f"✅ 进度追踪器已创建")
            
            # 创建AgentBuilder实例
            builder = AgentBuilder(self.default_llm_config)
            print(f"✅ AgentBuilder 实例已创建")
            
            # 构建输出目录
            agent_output_dir = os.path.join(
                self.output_base_dir, 
                f"user_{user_id}", 
                f"build_{build_id}"
            )
            os.makedirs(agent_output_dir, exist_ok=True)
            
            # 调用真实的AgentBuilder构建Agent
            result = await builder.build_agent_from_description(
                user_description=description,
                output_dir=agent_output_dir,
                agent_name=agent_name or f"agent_{build_id[:8]}"
            )
            
            if result["success"]:
                # 构建成功
                await self._handle_build_success(db, build_id, user_id, result)
            else:
                # 构建失败
                await self._handle_build_failure(
                    db, build_id, "Agent构建失败", result.get("error", "未知错误")
                )
                
        except Exception as e:
            # 处理异常
            await self._handle_build_failure(db, build_id, "构建过程中发生异常", str(e))
            
        finally:
            if progress_tracker:
                progress_tracker.cleanup()
            db.close()
    
    async def _update_build_progress(
        self, 
        db: Session, 
        build_id: str, 
        step: str, 
        message: str
    ):
        """更新构建进度"""
        build_session = db.query(AgentBuildSession).filter(
            AgentBuildSession.build_id == build_id
        ).first()
        
        if build_session:
            build_session.current_step = step
            build_session.progress_message = message
            build_session.updated_at = datetime.utcnow()
            db.commit()
            
            # 通过 WebSocket 广播进度更新
            if self.websocket_manager:
                progress_message = {
                    "type": "progress_update",
                    "build_id": build_id,
                    "step": step,
                    "message": message,
                    "timestamp": datetime.utcnow().isoformat()
                }
                await self.websocket_manager.broadcast_build_progress(build_id, progress_message)
    
    async def _handle_build_success(
        self, 
        db: Session, 
        build_id: str, 
        user_id: int, 
        result: Dict[str, Any]
    ):
        """处理构建成功"""
        # 生成Agent ID
        agent_id = str(uuid.uuid4())
        
        # 更新构建会话状态
        build_session = db.query(AgentBuildSession).filter(
            AgentBuildSession.build_id == build_id
        ).first()
        
        if build_session:
            build_session.status = "completed"
            build_session.current_step = "completed"
            build_session.progress_message = "Agent构建完成"
            build_session.result_data = json.dumps(result)
            build_session.completed_at = datetime.utcnow()
            
            # 创建生成的Agent记录
            agent_info = result.get("agent_info", {})
            workflow_info = result.get("workflow_info", {})
            files = result.get("files", {})
            
            generated_agent = GeneratedAgent(
                agent_id=agent_id,
                build_session_id=build_id,
                user_id=user_id,
                name=agent_info.get("name", f"Agent_{build_id[:8]}"),
                description=agent_info.get("description", "Generated Agent"),
                capabilities=json.dumps(agent_info.get("capabilities", [])),
                workflow_data=json.dumps(workflow_info),
                code_path=files.get("agent_file"),
                workflow_path=files.get("workflow_file"),
                metadata_path=files.get("metadata_file"),
                cost_analysis=agent_info.get("cost_analysis", "unknown"),
                status="active"
            )
            
            db.add(generated_agent)
            db.commit()
    
    async def _handle_build_failure(
        self, 
        db: Session, 
        build_id: str, 
        error_message: str, 
        details: str
    ):
        """处理构建失败"""
        build_session = db.query(AgentBuildSession).filter(
            AgentBuildSession.build_id == build_id
        ).first()
        
        if build_session:
            build_session.status = "failed"
            build_session.current_step = "failed"
            build_session.progress_message = error_message
            build_session.error_message = details
            build_session.completed_at = datetime.utcnow()
            db.commit()
    
    def get_build_status(self, build_id: str, db: Session) -> Optional[Dict[str, Any]]:
        """获取构建状态"""
        build_session = db.query(AgentBuildSession).filter(
            AgentBuildSession.build_id == build_id
        ).first()
        
        if not build_session:
            return None
        
        return {
            "build_id": build_session.build_id,
            "status": build_session.status,
            "current_step": build_session.current_step,
            "progress_message": build_session.progress_message,
            "error_message": build_session.error_message,
            "created_at": build_session.created_at.isoformat(),
            "updated_at": build_session.updated_at.isoformat(),
            "completed_at": build_session.completed_at.isoformat() if build_session.completed_at else None
        }
    
    def get_generated_agent(self, agent_id: str, user_id: int, db: Session) -> Optional[Dict[str, Any]]:
        """获取生成的Agent信息"""
        agent = db.query(GeneratedAgent).filter(
            GeneratedAgent.agent_id == agent_id,
            GeneratedAgent.user_id == user_id,
            GeneratedAgent.status == "active"
        ).first()
        
        if not agent:
            return None
        
        return {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "description": agent.description,
            "capabilities": json.loads(agent.capabilities) if agent.capabilities else [],
            "workflow_data": json.loads(agent.workflow_data) if agent.workflow_data else {},
            "cost_analysis": agent.cost_analysis,
            "created_at": agent.created_at.isoformat()
        }
    
    def list_user_agents(self, user_id: int, db: Session) -> list:
        """列出用户的所有Agent"""
        agents = db.query(GeneratedAgent).filter(
            GeneratedAgent.user_id == user_id,
            GeneratedAgent.status == "active"
        ).order_by(GeneratedAgent.created_at.desc()).all()
        
        return [
            {
                "agent_id": agent.agent_id,
                "name": agent.name,
                "description": agent.description,
                "cost_analysis": agent.cost_analysis,
                "created_at": agent.created_at.isoformat()
            }
            for agent in agents
        ]


# 全局服务实例
agent_build_service = AgentBuildService()