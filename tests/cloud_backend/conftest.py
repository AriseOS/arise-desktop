"""
Cloud Backend 测试配置

Pytest fixtures 和配置
"""

import pytest
import os
import sys
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="session")
def check_llm_api_key():
    """检查 LLM API Key 是否设置"""
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if not anthropic_key and not openai_key:
        pytest.skip("LLM API Key not found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY")
    
    return anthropic_key or openai_key


@pytest.fixture(scope="session")
def test_storage_path(tmp_path_factory):
    """创建临时测试存储路径"""
    return tmp_path_factory.mktemp("ami_test_storage")


def pytest_configure(config):
    """Pytest 配置"""
    # 添加自定义 markers
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
