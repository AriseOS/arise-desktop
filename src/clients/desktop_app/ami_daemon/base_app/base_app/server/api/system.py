"""
系统管理API路由
"""
import platform
import sys
import psutil
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query, Request

from ..models.responses import SystemHealthResponse, SystemInfoResponse
from ..core.agent_service import AgentService
from src.common.config_service import ConfigService


system_router = APIRouter()


def get_agent_service(request: Request) -> AgentService:
    """依赖注入：获取Agent服务"""
    if not hasattr(request.app.state, 'agent_service') or not request.app.state.agent_service:
        raise HTTPException(status_code=503, detail="Agent service not available")
    return request.app.state.agent_service


def get_config_service(request: Request) -> ConfigService:
    """依赖注入：获取配置服务"""
    if not hasattr(request.app.state, 'config_service') or not request.app.state.config_service:
        raise HTTPException(status_code=503, detail="Config service not available")
    return request.app.state.config_service


@system_router.get("/health", response_model=SystemHealthResponse)
async def get_system_health(
    agent_service: AgentService = Depends(get_agent_service)
):
    """系统健康检查"""
    try:
        agent_status = agent_service.get_agent_status()
        
        services = {
            "agent": agent_status.get("status", "unknown"),
            "config": "healthy",
            "api": "healthy"
        }
        
        overall_status = "healthy" if all(
            status in ["healthy", "ready"] for status in services.values()
        ) else "unhealthy"
        
        return SystemHealthResponse(
            status=overall_status,
            timestamp=datetime.now().isoformat(),
            services=services,
            uptime=agent_service.start_time
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@system_router.get("/info", response_model=SystemInfoResponse)
async def get_system_info(
    config_service: ConfigService = Depends(get_config_service)
):
    """获取系统信息"""
    try:
        # 获取内存使用情况
        memory = psutil.virtual_memory()
        memory_usage = {
            "total": memory.total,
            "available": memory.available,
            "percent": memory.percent,
            "used": memory.used
        }
        
        return SystemInfoResponse(
            app_name=config_service.get("app.name", "BaseApp"),
            app_version=config_service.get("app.version", "1.0.0"),
            python_version=sys.version,
            platform=platform.platform(),
            memory_usage=memory_usage
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@system_router.get("/config")
async def get_system_config(
    config_service: ConfigService = Depends(get_config_service),
    key: str = Query(None, description="配置键名，支持点分割格式")
):
    """获取系统配置"""
    try:
        if key:
            value = config_service.get(key)
            return {
                "key": key,
                "value": value
            }
        else:
            # 返回所有配置，但隐藏敏感信息
            config = config_service.get_all()
            
            # 隐藏敏感配置
            def hide_sensitive(data, path=""):
                if isinstance(data, dict):
                    result = {}
                    for k, v in data.items():
                        current_path = f"{path}.{k}" if path else k
                        if any(sensitive in current_path.lower() 
                               for sensitive in ["key", "password", "secret", "token"]):
                            result[k] = "***HIDDEN***" if v else None
                        else:
                            result[k] = hide_sensitive(v, current_path)
                    return result
                return data
            
            return hide_sensitive(config)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@system_router.get("/logs")
async def get_system_logs(
    request: Request,
    level: str = Query("INFO", description="日志级别"),
    limit: int = Query(100, ge=1, le=1000, description="日志行数"),
    tail: bool = Query(True, description="是否获取最新日志")
):
    """获取系统日志"""
    try:
        import os
        from pathlib import Path

        # 从配置服务获取日志文件路径
        config_service = get_config_service(request)
        log_file = config_service.get_path("logging.file", create_parent=False)
        
        if not log_file.exists():
            return {
                "logs": [],
                "message": "Log file not found"
            }
        
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 过滤日志级别
        filtered_lines = []
        for line in lines:
            if level.upper() in line or level == "ALL":
                filtered_lines.append(line.strip())
        
        # 获取最新的日志
        if tail:
            filtered_lines = filtered_lines[-limit:]
        else:
            filtered_lines = filtered_lines[:limit]
        
        return {
            "logs": filtered_lines,
            "total": len(filtered_lines),
            "level": level,
            "tail": tail
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))