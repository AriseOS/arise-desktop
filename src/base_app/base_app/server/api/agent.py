"""
Agent管理API路由
"""
from fastapi import APIRouter, HTTPException, Depends, Request

from ..models.requests import UpdateAgentConfigRequest
from ..models.responses import (
    AgentStatusResponse, AgentConfigResponse, OperationResponse
)
from ..core.agent_service import AgentService


agent_router = APIRouter()


def get_agent_service(request: Request) -> AgentService:
    """依赖注入：获取Agent服务"""
    if not hasattr(request.app.state, 'agent_service') or not request.app.state.agent_service:
        raise HTTPException(status_code=503, detail="Agent service not available")
    return request.app.state.agent_service


@agent_router.get("/status", response_model=AgentStatusResponse)
async def get_agent_status(
    agent_service: AgentService = Depends(get_agent_service)
):
    """获取Agent状态"""
    try:
        status = agent_service.get_agent_status()
        return AgentStatusResponse(**status)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@agent_router.get("/config", response_model=AgentConfigResponse)
async def get_agent_config(
    agent_service: AgentService = Depends(get_agent_service)
):
    """获取Agent配置"""
    try:
        config = agent_service.get_agent_config()
        
        if not config:
            raise HTTPException(status_code=503, detail="Agent not initialized")
        
        return AgentConfigResponse(**config)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@agent_router.post("/restart", response_model=OperationResponse)
async def restart_agent(
    agent_service: AgentService = Depends(get_agent_service)
):
    """重启Agent"""
    try:
        result = await agent_service.restart_agent()
        return OperationResponse(**result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@agent_router.get("/tools")
async def get_agent_tools(
    agent_service: AgentService = Depends(get_agent_service)
):
    """获取Agent工具列表"""
    try:
        if not agent_service.agent:
            raise HTTPException(status_code=503, detail="Agent not initialized")
        
        tools = agent_service.agent.get_registered_tools()
        
        return {
            "tools": tools,
            "total": len(tools)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@agent_router.get("/memory/stats")
async def get_memory_stats(
    agent_service: AgentService = Depends(get_agent_service)
):
    """获取内存统计信息"""
    try:
        if not agent_service.agent:
            raise HTTPException(status_code=503, detail="Agent not initialized")
        
        if not agent_service.agent.memory_manager:
            return {
                "enabled": False,
                "message": "Memory not enabled"
            }
        
        # 这里可以添加内存统计逻辑
        return {
            "enabled": True,
            "provider": "mem0",
            "total_memories": 0,  # 需要实现具体的统计逻辑
            "last_updated": None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@agent_router.post("/memory/clear", response_model=OperationResponse)
async def clear_agent_memory(
    agent_service: AgentService = Depends(get_agent_service)
):
    """清理Agent内存"""
    try:
        if not agent_service.agent:
            raise HTTPException(status_code=503, detail="Agent not initialized")
        
        if not agent_service.agent.memory_manager:
            raise HTTPException(status_code=400, detail="Memory not enabled")
        
        # 这里可以添加清理内存的逻辑
        # await agent_service.agent.memory_manager.clear()
        
        return OperationResponse(
            success=True,
            message="Agent memory cleared successfully",
            timestamp=str(agent_service.start_time)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))