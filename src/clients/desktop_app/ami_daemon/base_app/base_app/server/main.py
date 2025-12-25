"""
BaseApp FastAPI 服务器主入口
"""
import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.common.config_service import ConfigService
from .core.agent_service import AgentService
from .api.chat import chat_router
from .api.agent import agent_router
from .api.system import system_router




@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理

    注意：BaseApp 现在作为库使用，配置应该由调用方（app_backend）提供
    如果需要独立运行 BaseApp（仅用于测试），需要从 app_backend 的配置加载
    """
    # 启动时初始化服务
    try:
        # 从 app_backend 加载配置
        from src.clients.desktop_app.ami_daemon.core.config_service import get_config
        config_service = get_config()

        # 初始化Agent服务
        agent_service = AgentService(config_service)

        # 异步初始化存储和Agent
        await agent_service.initialize()

        # 设置应用状态
        app.state.config_service = config_service
        app.state.agent_service = agent_service

        logging.info("BaseApp services initialized successfully")

        yield

    except Exception as e:
        logging.error(f"Failed to initialize BaseApp: {e}")
        sys.exit(1)

    finally:
        # 关闭时清理资源
        if hasattr(app.state, 'agent_service') and app.state.agent_service:
            await app.state.agent_service.shutdown()
        logging.info("BaseApp services shutdown completed")


def create_app(config_path: str = None) -> FastAPI:
    """创建FastAPI应用"""
    
    app = FastAPI(
        title="BaseApp API",
        description="BaseApp - AI Agent Assistant",
        version="1.0.0",
        lifespan=lifespan
    )
    
    # 配置CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # React开发服务器
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 注册API路由
    app.include_router(chat_router, prefix="/api/v1/chat", tags=["Chat"])
    app.include_router(agent_router, prefix="/api/v1/agent", tags=["Agent"])
    app.include_router(system_router, prefix="/api/v1/system", tags=["System"])
    
    # 静态文件服务（如果有前端文件）
    static_dir = Path(__file__).parent.parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    
    # 健康检查端点
    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "service": "BaseApp",
            "version": "1.0.0"
        }
    
    # 根路径
    @app.get("/")
    async def root():
        return {
            "message": "Welcome to BaseApp API",
            "docs": "/docs",
            "health": "/health"
        }
    
    return app


def setup_logging(config_service: ConfigService = None, level: str = "INFO"):
    """设置日志"""
    # 从配置文件获取日志设置
    if config_service:
        log_level = config_service.get("logging.level", level)
        log_file = config_service.get("logging.file", "./logs/baseapp.log")
    else:
        log_level = level
        log_file = "./logs/baseapp.log"
    
    # 确保日志目录存在
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file)
        ]
    )


def run_server(
    host: str = None,
    port: int = None,
    config_path: str = None,
    log_level: str = "INFO",
    reload: bool = False
):
    """运行服务器"""
    
    try:
        # 初始化配置服务
        config_service = ConfigService(config_path)
        
        # 从配置文件获取主机和端口，如果参数未指定
        if host is None:
            host = config_service.get("app.host", "0.0.0.0")
        if port is None:
            port = config_service.get("app.port", 8000)
        
        # 使用配置文件设置日志
        setup_logging(config_service, log_level)
        
        # 创建应用
        app = create_app(config_path)
    except Exception as e:
        # 如果配置失败，使用默认日志记录错误
        setup_logging(None, log_level)
        logging.error(f"Failed to initialize server: {e}")
        raise
    
    # 运行服务器
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level.lower(),
        reload=reload
    )


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="BaseApp Server")
    parser.add_argument("--host", default=None, help="Host to bind")
    parser.add_argument("--port", type=int, default=None, help="Port to bind")
    parser.add_argument("--config", help="Config file path")
    parser.add_argument("--log-level", default="INFO", help="Log level")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    
    args = parser.parse_args()
    
    run_server(
        host=args.host,
        port=args.port,
        config_path=args.config,
        log_level=args.log_level,
        reload=args.reload
    )