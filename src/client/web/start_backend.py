#!/usr/bin/env python3
"""
启动 Agentcrafter 后端服务器
"""
import os
import sys
import subprocess

def main():
    # 获取当前脚本目录
    current_dir = os.path.dirname(__file__)
    backend_dir = os.path.join(current_dir, 'backend')
    
    # 添加backend目录到Python路径
    sys.path.insert(0, backend_dir)
    
    # 切换到后端目录
    os.chdir(backend_dir)
    
    # 检查是否安装了依赖
    try:
        import fastapi
        import uvicorn
        import sqlalchemy
        import passlib
        import jose
    except ImportError:
        print("正在安装依赖...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
    
    # 初始化数据库
    print("初始化数据库...")
    from database import init_db
    init_db()
    
    # 启动服务器
    print("启动后端服务器...")
    
    # Import ConfigService
    sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..', '..', 'base_app')))
    from base_app.server.core.config_service import ConfigService
    
    # Initialize ConfigService
    config_service = ConfigService()
    
    # Print configuration
    print("=" * 60)
    print("AgentCrafter Backend Configuration")
    print("=" * 60)
    print(f"Config file: {config_service.config_path}")
    print(f"Server: {config_service.get('web.server.host')}:{config_service.get('web.server.port')}")
    print(f"Reload: {config_service.get('web.server.reload')}")
    print(f"Data root: {config_service.get('data.root')}")
    print("=" * 60)
    
    # Get server configuration
    server_config = {
        "host": config_service.get('web.server.host', '0.0.0.0'),
        "port": config_service.get('web.server.port', 8000),
        "reload": config_service.get('web.server.reload', True),
        "log_level": config_service.get('logging.level', 'info').lower()
    }
    
    import uvicorn
    uvicorn.run("main:app", **server_config)

if __name__ == "__main__":
    main()