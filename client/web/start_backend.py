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
    from backend.config import get_server_config, print_config
    
    # 打印配置信息
    print_config()
    
    import uvicorn
    server_config = get_server_config()
    uvicorn.run("main:app", **server_config)

if __name__ == "__main__":
    main()