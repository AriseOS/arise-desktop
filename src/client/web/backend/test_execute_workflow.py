"""
Simple script to test workflow execution
"""
import requests
import time
import json

BASE_URL = "http://localhost:8000"
TEST_USERNAME = "test_user"
TEST_PASSWORD = "test123"
WORKFLOW_NAME = "test-coffee-collection-workflow"


def login():
    """Login and get token"""
    response = requests.post(
        f"{BASE_URL}/api/login",
        json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        return data["access_token"]
    else:
        print(f"❌ Login failed: {response.text}")
        return None


def execute_workflow(token, workflow_name):
    """Execute a workflow"""
    print(f"\n{'='*80}")
    print(f"Executing workflow: {workflow_name}")
    print(f"{'='*80}\n")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    response = requests.post(
        f"{BASE_URL}/api/workflows/{workflow_name}/execute",
        headers=headers
    )
    
    if response.status_code != 200:
        print(f"❌ Failed to execute workflow: {response.text}")
        return None
    
    data = response.json()
    task_id = data['task_id']
    print(f"✅ Workflow execution started")
    print(f"   Task ID: {task_id}")
    print(f"   Status: {data['status']}")
    
    return task_id


def check_status(token, task_id):
    """Check execution status"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    print(f"\n{'='*80}")
    print(f"Checking execution status...")
    print(f"{'='*80}\n")
    
    max_wait = 120  # 2 minutes
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        response = requests.get(
            f"{BASE_URL}/api/workflows/executions/{task_id}",
            headers=headers
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to get status: {response.text}")
            return False
        
        data = response.json()
        execution = data['execution']
        status = execution['status']
        progress = execution.get('progress', 0)
        
        print(f"⏳ Status: {status}, Progress: {progress}%")
        
        if status == 'completed':
            print(f"\n✅ Workflow execution completed!")
            print(f"   Execution time: {execution.get('execution_time_ms', 0)}ms")
            if execution.get('result'):
                print(f"\n📊 Result:")
                print(json.dumps(execution['result'], indent=2))
            return True
        elif status == 'failed':
            print(f"\n❌ Workflow execution failed!")
            print(f"   Error: {execution.get('error_message', 'Unknown error')}")
            return False
        
        time.sleep(5)
    
    print(f"\n⏱️  Timeout waiting for execution to complete")
    return False


def main():
    print("\n🚀 Testing Workflow Execution 🚀\n")
    
    # 1. Login
    print("Step 1: Login...")
    token = login()
    if not token:
        return
    print(f"✅ Logged in successfully")
    
    # 2. Execute workflow
    print("\nStep 2: Execute workflow...")
    task_id = execute_workflow(token, WORKFLOW_NAME)
    if not task_id:
        return
    
    # 3. Check status
    print("\nStep 3: Monitor execution...")
    success = check_status(token, task_id)
    
    if success:
        print("\n🎉 Test completed successfully! 🎉\n")
    else:
        print("\n❌ Test failed\n")


if __name__ == "__main__":
    main()
