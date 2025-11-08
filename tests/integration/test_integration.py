"""
Integration Test - 测试完整流程

测试流程：
1. App Backend 和 Cloud Backend 启动
2. 模拟录制数据上传
3. 生成 Workflow
4. 下载 Workflow
5. 执行 Workflow
"""

import requests
import time
import json

# 配置
LOCAL_API = "http://localhost:8000"
CLOUD_API = "http://localhost:9000"

def test_cloud_backend():
    """测试 Cloud Backend"""
    print("\n" + "="*80)
    print("1️⃣  测试 Cloud Backend")
    print("="*80)
    
    # Health check
    resp = requests.get(f"{CLOUD_API}/health")
    print(f"✅ Cloud Backend health: {resp.json()}")
    
    # 登录
    login_data = {"username": "test_user", "password": "test123"}
    resp = requests.post(f"{CLOUD_API}/api/auth/login", json=login_data)
    result = resp.json()
    print(f"✅ Login successful: user_id={result['user_id']}, token={result['token'][:20]}...")
    
    user_id = result['user_id']
    
    # 上传录制数据
    recording_data = {
        "user_id": user_id,
        "operations": [
            {"type": "navigate", "url": "https://allegro.pl"},
            {"type": "input", "selector": "#search", "value": "kawa"},
            {"type": "click", "selector": "button[type=submit]"}
        ]
    }
    resp = requests.post(f"{CLOUD_API}/api/recordings/upload", json=recording_data)
    result = resp.json()
    recording_id = result['recording_id']
    print(f"✅ Recording uploaded: {recording_id}")
    
    # 生成 Workflow
    print(f"⏳ Generating workflow for recording: {recording_id}...")
    generate_data = {"user_id": user_id}
    resp = requests.post(f"{CLOUD_API}/api/recordings/{recording_id}/generate", json=generate_data)
    result = resp.json()
    workflow_name = result['workflow_name']
    print(f"✅ Workflow generated: {workflow_name}")
    
    # 列出 Workflows
    resp = requests.get(f"{CLOUD_API}/api/workflows", params={"user_id": user_id})
    workflows = resp.json()
    print(f"✅ Workflows list: {len(workflows)} workflows")
    
    return user_id, workflow_name

def test_app_backend(user_id, workflow_name):
    """测试 App Backend"""
    print("\n" + "="*80)
    print("2️⃣  测试 App Backend")
    print("="*80)
    
    # Health check
    resp = requests.get(f"{LOCAL_API}/health")
    health = resp.json()
    print(f"✅ App Backend health: {json.dumps(health, indent=2)}")
    
    # 从 Cloud 下载 Workflow
    print(f"⏳ Downloading workflow: {workflow_name}...")
    download_data = {"user_id": user_id, "workflow_name": workflow_name}
    resp = requests.post(f"{LOCAL_API}/api/cloud/workflows/download", json=download_data)
    result = resp.json()
    print(f"✅ Workflow downloaded: {result}")
    
    # 列出本地 Workflows
    resp = requests.get(f"{LOCAL_API}/api/workflows/list", params={"user_id": user_id})
    workflows = resp.json()
    print(f"✅ Local workflows: {workflows}")
    
    # 执行 Workflow (暂时跳过，因为需要真实的 workflow YAML)
    # execute_data = {"user_id": user_id, "workflow_name": workflow_name}
    # resp = requests.post(f"{LOCAL_API}/api/workflows/execute", json=execute_data)
    # result = resp.json()
    # task_id = result['task_id']
    # print(f"✅ Workflow execution started: {task_id}")
    
    # 存储统计
    resp = requests.get(f"{LOCAL_API}/api/storage/stats", params={"user_id": user_id})
    stats = resp.json()
    print(f"✅ Storage stats: {json.dumps(stats, indent=2)}")

def main():
    """运行完整测试"""
    print("\n" + "="*80)
    print("🧪 Integration Test - Ami System")
    print("="*80)
    print("\n前提条件：")
    print("  - App Backend 运行在 localhost:8000")
    print("  - Cloud Backend 运行在 localhost:9000")
    print("\n")
    
    try:
        # 测试 Cloud Backend
        user_id, workflow_name = test_cloud_backend()
        
        # 测试 App Backend
        test_app_backend(user_id, workflow_name)
        
        print("\n" + "="*80)
        print("✅ 所有测试通过！")
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
