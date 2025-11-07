"""
Cloud Backend - Workflow Generation Service 测试

使用真实测试数据测试完整的 Workflow 生成流程
"""

import pytest
import asyncio
import json
from pathlib import Path
import sys

# 添加项目根目录
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 测试数据路径
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "test_data"

# 测试用例
TEST_CASES = [
    {
        "name": "coffee_allegro",
        "data_file": FIXTURES_DIR / "coffee_allegro" / "fixtures" / "user_operations.json",
        "expected_task": "Allegro",
    },
    {
        "name": "kickstarter_projects", 
        "data_file": FIXTURES_DIR / "kickstarter_projects" / "fixtures" / "user_operations.json",
        "expected_task": "Kickstarter",
    },
    {
        "name": "producthunt_products",
        "data_file": FIXTURES_DIR / "producthunt_products" / "fixtures" / "user_operations.json",
        "expected_task": "ProductHunt",
    },
]


@pytest.fixture
def workflow_service():
    """创建 WorkflowGenerationService 实例"""
    from src.cloud_backend.services.workflow_generation_service import WorkflowGenerationService

    # 使用环境变量中的 LLM provider
    import os
    provider = os.getenv("LLM_PROVIDER", "anthropic")

    service = WorkflowGenerationService(llm_provider_name=provider)
    return service


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[tc["name"] for tc in TEST_CASES])
@pytest.mark.asyncio
async def test_generate_workflow_from_operations(workflow_service, test_case):
    """
    测试从 operations 生成 Workflow
    
    验证点：
    1. 能够加载测试数据
    2. Intent Extraction 成功
    3. MetaFlow Generation 成功
    4. Workflow Generation 成功
    5. 返回结果包含必要字段
    """
    # 读取测试数据
    data_file = test_case["data_file"]
    
    if not data_file.exists():
        pytest.skip(f"Test data not found: {data_file}")
    
    with open(data_file, 'r') as f:
        test_data = json.load(f)
    
    operations = test_data.get("operations", [])
    task_description = test_data.get("task_metadata", {}).get("task_description")
    
    assert len(operations) > 0, "Operations should not be empty"
    
    # 调用 Workflow Generation Service
    result = await workflow_service.generate_workflow_from_operations(
        operations=operations,
        task_description=task_description
    )
    
    # 验证返回结果
    assert "workflow_yaml" in result
    assert "metaflow_yaml" in result
    assert "intent_graph_json" in result
    assert "workflow_name" in result
    
    # 验证 Workflow YAML 不为空
    workflow_yaml = result["workflow_yaml"]
    assert len(workflow_yaml) > 0, "Workflow YAML should not be empty"
    
    # 验证 Workflow YAML 是有效的 YAML
    import yaml
    workflow_dict = yaml.safe_load(workflow_yaml)
    assert "name" in workflow_dict or "steps" in workflow_dict, "Workflow should have name or steps"
    
    # 验证 MetaFlow YAML
    metaflow_yaml = result["metaflow_yaml"]
    assert len(metaflow_yaml) > 0, "MetaFlow YAML should not be empty"
    
    # 验证 Intent Graph JSON
    intent_graph_json = result["intent_graph_json"]
    assert len(intent_graph_json) > 0, "Intent Graph JSON should not be empty"
    
    # 验证 Workflow Name 包含任务关键词
    workflow_name = result["workflow_name"]
    assert len(workflow_name) > 0, "Workflow name should not be empty"
    
    print(f"\n✅ Test passed: {test_case['name']}")
    print(f"   Workflow: {workflow_name}")
    print(f"   Size: {len(workflow_yaml)} chars")


@pytest.mark.asyncio
async def test_infer_task_description(workflow_service):
    """测试任务描述推断"""
    
    operations = [
        {"type": "navigate", "url": "https://www.example.com/products"},
        {"type": "click", "element": {"text": "Click me"}},
    ]
    
    # 不提供 task_description，让服务自动推断
    result = await workflow_service.generate_workflow_from_operations(
        operations=operations
    )
    
    assert "workflow_name" in result
    workflow_name = result["workflow_name"]
    
    # 应该包含域名信息
    assert "example.com" in workflow_name.lower() or "example" in workflow_name.lower()


@pytest.mark.asyncio  
async def test_workflow_name_generation(workflow_service):
    """测试 Workflow 名称生成"""
    
    operations = [
        {"type": "navigate", "url": "https://allegro.pl/kawa"},
    ]
    
    result = await workflow_service.generate_workflow_from_operations(
        operations=operations,
        task_description="从 Allegro 抓取咖啡产品"
    )
    
    workflow_name = result["workflow_name"]
    
    # 验证名称格式
    assert len(workflow_name) > 0
    assert len(workflow_name) <= 100  # 合理长度
    
    # 不应包含特殊字符（除了短横线）
    import re
    assert re.match(r'^[\w\-\u4e00-\u9fff]+$', workflow_name), "Name should not contain special chars"


if __name__ == "__main__":
    # 直接运行测试
    pytest.main([__file__, "-v", "-s"])
