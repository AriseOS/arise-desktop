#!/usr/bin/env python3
"""
测试 AgentCrafter 后端配置
"""
import os
import sys
import tempfile
from pathlib import Path

# 添加backend目录到Python路径
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

def test_default_config():
    """测试默认配置"""
    print("=== 测试默认配置 ===")
    
    # 清除环境变量
    for key in ["DATABASE_URL", "DATABASE_PATH", "BACKEND_HOST", "BACKEND_PORT"]:
        if key in os.environ:
            del os.environ[key]
    
    from backend.config import BackendConfig
    config = BackendConfig()
    
    # 验证默认值
    assert config.host == "0.0.0.0"
    assert config.port == 8000
    assert config.reload == True
    assert "sqlite" in config.database_url
    assert config.database_url.endswith("agentcrafter_users.db")
    
    print("✓ 默认配置测试通过")

def test_environment_config():
    """测试环境变量配置"""
    print("=== 测试环境变量配置 ===")
    
    # 设置环境变量
    os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/test"
    os.environ["BACKEND_HOST"] = "127.0.0.1"
    os.environ["BACKEND_PORT"] = "9000"
    os.environ["BACKEND_RELOAD"] = "false"
    os.environ["LOG_LEVEL"] = "DEBUG"
    
    # 重新导入配置（清除缓存）
    if 'backend.config' in sys.modules:
        del sys.modules['backend.config']
    
    from backend.config import BackendConfig
    config = BackendConfig()
    
    # 验证环境变量生效
    assert config.database_url == "postgresql://test:test@localhost/test"
    assert config.host == "127.0.0.1"
    assert config.port == 9000
    assert config.reload == False
    assert config.log_level == "DEBUG"
    
    print("✓ 环境变量配置测试通过")

def test_database_path_config():
    """测试数据库路径配置"""
    print("=== 测试数据库路径配置 ===")
    
    # 清除DATABASE_URL，设置DATABASE_PATH
    if "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]
    
    # 测试相对路径
    os.environ["DATABASE_PATH"] = "test_data/test.db"
    
    if 'backend.config' in sys.modules:
        del sys.modules['backend.config']
    
    from backend.config import BackendConfig
    config = BackendConfig()
    
    assert "sqlite" in config.database_url
    assert "test_data/test.db" in config.database_url
    
    # 测试绝对路径
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
    
    os.environ["DATABASE_PATH"] = tmp_path
    
    if 'backend.config' in sys.modules:
        del sys.modules['backend.config']
    
    from backend.config import BackendConfig
    config = BackendConfig()
    
    assert config.database_url == f"sqlite:///{tmp_path}"
    
    # 清理
    os.unlink(tmp_path)
    
    print("✓ 数据库路径配置测试通过")

def test_database_config_output():
    """测试数据库配置输出"""
    print("=== 测试数据库配置输出 ===")
    
    # 重置环境
    os.environ["DATABASE_URL"] = "sqlite:///test.db"
    
    if 'backend.config' in sys.modules:
        del sys.modules['backend.config']
    
    from backend.config import BackendConfig
    config = BackendConfig()
    
    db_config = config.get_database_config()
    
    assert "url" in db_config
    assert db_config["url"] == "sqlite:///test.db"
    assert "connect_args" in db_config
    assert db_config["connect_args"]["check_same_thread"] == False
    
    print("✓ 数据库配置输出测试通过")

def test_server_config_output():
    """测试服务器配置输出"""
    print("=== 测试服务器配置输出 ===")
    
    os.environ["BACKEND_HOST"] = "localhost"
    os.environ["BACKEND_PORT"] = "8080"
    os.environ["LOG_LEVEL"] = "WARNING"
    
    if 'backend.config' in sys.modules:
        del sys.modules['backend.config']
    
    from backend.config import BackendConfig
    config = BackendConfig()
    
    server_config = config.get_server_config()
    
    assert server_config["host"] == "localhost"
    assert server_config["port"] == 8080
    assert server_config["log_level"] == "warning"
    
    print("✓ 服务器配置输出测试通过")

def test_jwt_config():
    """测试JWT配置"""
    print("=== 测试JWT配置 ===")
    
    os.environ["SECRET_KEY"] = "test-secret-key"
    
    if 'backend.config' in sys.modules:
        del sys.modules['backend.config']
    
    from backend.config import BackendConfig
    config = BackendConfig()
    
    jwt_config = config.get_jwt_config()
    
    assert jwt_config["secret_key"] == "test-secret-key"
    assert jwt_config["algorithm"] == "HS256"
    assert jwt_config["access_token_expire_minutes"] == 30
    
    print("✓ JWT配置测试通过")

def test_database_integration():
    """测试数据库集成"""
    print("=== 测试数据库集成 ===")
    
    # 使用临时数据库文件
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
    
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}"
    
    # 清除模块缓存
    modules_to_clear = ['backend.config', 'backend.database']
    for module in modules_to_clear:
        if module in sys.modules:
            del sys.modules[module]
    
    try:
        from backend.database import init_db, get_db, User
        from sqlalchemy.orm import Session
        
        # 初始化数据库
        init_db()
        
        # 测试数据库连接
        db_gen = get_db()
        db: Session = next(db_gen)
        
        # 测试创建用户
        test_user = User(
            username="test_user",
            email="test@example.com",
            hashed_password="test_hash"
        )
        db.add(test_user)
        db.commit()
        
        # 测试查询用户
        user = db.query(User).filter(User.username == "test_user").first()
        assert user is not None
        assert user.email == "test@example.com"
        
        db.close()
        
        print("✓ 数据库集成测试通过")
    
    finally:
        # 清理
        os.unlink(tmp_path)

def main():
    """运行所有测试"""
    print("开始测试 AgentCrafter 后端配置...")
    
    try:
        test_default_config()
        test_environment_config()
        test_database_path_config()
        test_database_config_output()
        test_server_config_output()
        test_jwt_config()
        test_database_integration()
        
        print("\n🎉 所有配置测试通过！")
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 测试出错: {e}")
        sys.exit(1)
    
    finally:
        # 清理环境变量
        env_vars = [
            "DATABASE_URL", "DATABASE_PATH", "BACKEND_HOST", 
            "BACKEND_PORT", "BACKEND_RELOAD", "LOG_LEVEL", "SECRET_KEY"
        ]
        for var in env_vars:
            if var in os.environ:
                del os.environ[var]

if __name__ == "__main__":
    main()