"""
Cloud Backend - API 端点测试

测试所有 Cloud Backend 的 HTTP API
"""

import pytest
import asyncio
import json
from pathlib import Path
import httpx

# 配置
CLOUD_BACKEND_URL = "http://localhost:9000"
TEST_USER_ID = "test_api_user"

# 测试数据
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "test_data"
TEST_DATA_FILE = FIXTURES_DIR / "coffee_allegro" / "fixtures" / "user_operations.json"


@pytest.fixture
def test_data():
    """加载测试数据"""
    if not TEST_DATA_FILE.exists():
        pytest.skip(f"Test data not found: {TEST_DATA_FILE}")
    
    with open(TEST_DATA_FILE, 'r') as f:
        return json.load(f)


@pytest.mark.asyncio
async def test_health_check():
    """测试 Health Check API"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{CLOUD_BACKEND_URL}/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "ok"
        assert data["service"] == "cloud-backend"
        assert "version" in data


@pytest.mark.asyncio
async def test_auth_login():
    """测试登录 API"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{CLOUD_BACKEND_URL}/api/auth/login",
            json={
                "username": "test_user",
                "password": "test_password"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "token" in data
        assert "user_id" in data
        assert data["user_id"] == "test_user"


@pytest.mark.asyncio
async def test_upload_recording(test_data):
    """测试上传录制数据 API"""
    operations = test_data.get("operations", [])
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{CLOUD_BACKEND_URL}/api/recordings/upload",
            json={
                "user_id": TEST_USER_ID,
                "operations": operations
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "recording_id" in data
        recording_id = data["recording_id"]
        assert len(recording_id) > 0


@pytest.mark.asyncio
async def test_full_workflow_api_flow(test_data):
    """
    测试完整的 API 流程
    
    流程：
    1. 上传录制
    2. 生成 Workflow
    3. 下载 Workflow
    4. 列出 Workflows
    """
    operations = test_data.get("operations", [])
    task_description = test_data.get("task_metadata", {}).get("task_description")
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        
        # Step 1: 上传录制
        response = await client.post(
            f"{CLOUD_BACKEND_URL}/api/recordings/upload",
            json={
                "user_id": TEST_USER_ID,
                "operations": operations
            }
        )
        
        assert response.status_code == 200
        recording_id = response.json()["recording_id"]
        print(f"\n✅ Recording uploaded: {recording_id}")
        
        # Step 2: 生成 Workflow
        response = await client.post(
            f"{CLOUD_BACKEND_URL}/api/recordings/{recording_id}/generate",
            json={
                "user_id": TEST_USER_ID,
                "task_description": task_description
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "workflow_name" in data
        assert data["status"] == "success"
        
        workflow_name = data["workflow_name"]
        print(f"✅ Workflow generated: {workflow_name}")
        
        # Step 3: 下载 Workflow
        response = await client.get(
            f"{CLOUD_BACKEND_URL}/api/workflows/{workflow_name}/download",
            params={"user_id": TEST_USER_ID}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "yaml" in data
        workflow_yaml = data["yaml"]
        assert len(workflow_yaml) > 0
        print(f"✅ Workflow downloaded: {len(workflow_yaml)} chars")
        
        # Step 4: 列出 Workflows
        response = await client.get(
            f"{CLOUD_BACKEND_URL}/api/workflows",
            params={"user_id": TEST_USER_ID}
        )
        
        assert response.status_code == 200
        workflows = response.json()
        
        assert isinstance(workflows, list)
        assert len(workflows) > 0
        
        # 应该包含刚才生成的 workflow
        workflow_names = [w["name"] for w in workflows]
        assert workflow_name in workflow_names
        print(f"✅ Listed {len(workflows)} workflows")


@pytest.mark.asyncio
async def test_download_nonexistent_workflow():
    """测试下载不存在的 Workflow"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{CLOUD_BACKEND_URL}/api/workflows/nonexistent-workflow/download",
            params={"user_id": TEST_USER_ID}
        )
        
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_generate_without_user_id(test_data):
    """测试缺少 user_id 的情况"""
    operations = test_data.get("operations", [])
    
    async with httpx.AsyncClient() as client:
        # 上传录制（需要 user_id）
        response = await client.post(
            f"{CLOUD_BACKEND_URL}/api/recordings/upload",
            json={
                "user_id": TEST_USER_ID,
                "operations": operations
            }
        )
        
        recording_id = response.json()["recording_id"]
        
        # 尝试生成但不提供 user_id
        response = await client.post(
            f"{CLOUD_BACKEND_URL}/api/recordings/{recording_id}/generate",
            json={}  # 缺少 user_id
        )
        
        assert response.status_code == 400


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
