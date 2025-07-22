#!/usr/bin/env python3
"""
测试 AgentCrafter 后端启动流程
"""
import os
import sys
import tempfile
import subprocess
import time
import requests
from pathlib import Path

def test_backend_startup():
    """测试后端启动流程"""
    print("=== 测试后端启动流程 ===")
    
    # 创建临时数据库
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
    
    # 设置测试环境变量
    env = os.environ.copy()
    env.update({
        "DATABASE_URL": f"sqlite:///{tmp_path}",
        "BACKEND_PORT": "8001",  # 使用不同端口避免冲突
        "BACKEND_RELOAD": "false",  # 禁用热重载以便测试
        "LOG_LEVEL": "ERROR"  # 减少日志输出
    })
    
    # 获取项目路径
    project_root = Path(__file__).parent.parent.parent.parent
    startup_script = Path(__file__).parent / "start_backend.py"
    
    process = None
    try:
        print("启动后端服务器...")
        
        # 启动后端进程
        process = subprocess.Popen(
            [sys.executable, str(startup_script)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(project_root / "agentcrafter")
        )
        
        # 等待服务器启动
        max_wait = 30  # 最多等待30秒
        for i in range(max_wait):
            try:
                response = requests.get("http://localhost:8001/", timeout=1)
                if response.status_code in [200, 404]:  # 404也表示服务器在运行
                    print(f"✓ 后端服务器启动成功 (耗时 {i+1} 秒)")
                    break
            except requests.exceptions.RequestException:
                time.sleep(1)
        else:
            raise Exception("后端服务器启动超时")
        
        # 测试API端点
        try:
            # 测试健康检查端点（如果存在）
            response = requests.get("http://localhost:8001/health", timeout=5)
            if response.status_code == 200:
                print("✓ 健康检查端点正常")
        except requests.exceptions.RequestException:
            print("ℹ 健康检查端点不存在或不可用")
        
        print("✓ 后端启动测试通过")
        
    except Exception as e:
        print(f"❌ 后端启动测试失败: {e}")
        if process:
            stdout, stderr = process.communicate(timeout=5)
            print("STDOUT:", stdout.decode())
            print("STDERR:", stderr.decode())
        raise
    
    finally:
        # 清理进程
        if process:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        
        # 清理临时文件
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

def test_config_validation():
    """测试配置验证"""
    print("=== 测试配置验证 ===")
    
    # 测试无效端口
    env = os.environ.copy()
    env["BACKEND_PORT"] = "invalid_port"
    
    try:
        result = subprocess.run(
            [sys.executable, "-c", 
             "import sys; sys.path.append('backend'); "
             "from config import BackendConfig; BackendConfig()"],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=Path(__file__).parent
        )
        
        # 应该抛出ValueError
        if result.returncode == 0:
            print("⚠ 警告: 无效端口配置未被检测到")
        else:
            print("✓ 无效端口配置被正确检测")
    
    except Exception as e:
        print(f"❌ 配置验证测试失败: {e}")
        raise

def test_database_initialization():
    """测试数据库初始化"""
    print("=== 测试数据库初始化 ===")
    
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        # 设置环境变量
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{tmp_path}"
        
        # 运行数据库初始化
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.append('backend'); "
             "from database import init_db; init_db()"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=Path(__file__).parent
        )
        
        if result.returncode != 0:
            print(f"STDERR: {result.stderr}")
            raise Exception(f"数据库初始化失败: {result.stderr}")
        
        # 验证数据库文件存在
        if not os.path.exists(tmp_path):
            raise Exception("数据库文件未创建")
        
        # 验证数据库文件不为空
        if os.path.getsize(tmp_path) == 0:
            raise Exception("数据库文件为空")
        
        print("✓ 数据库初始化测试通过")
    
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

def main():
    """运行所有启动测试"""
    print("开始测试 AgentCrafter 后端启动...")
    
    try:
        test_config_validation()
        test_database_initialization()
        test_backend_startup()
        
        print("\n🎉 所有启动测试通过！")
        
    except Exception as e:
        print(f"\n❌ 启动测试失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()