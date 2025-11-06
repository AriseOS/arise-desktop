"""
Test script for Workflow Management APIs

This script tests the complete workflow from recording to execution:
1. Create a test recording session
2. Extract intents
3. Generate metaflow
4. Generate workflow
5. Execute workflow
"""
import asyncio
import json
import requests
from datetime import datetime, timezone

BASE_URL = "http://localhost:8000"

# Test credentials
TEST_USERNAME = "test_user"
TEST_PASSWORD = "test123"
TEST_EMAIL = "test@example.com"


class WorkflowAPITester:
    def __init__(self):
        self.token = None
        self.session_id = None
        self.workflow_name = None
        self.task_id = None

    def authenticate(self):
        """Authenticate user (try login first, then register if needed)"""
        print("\n" + "="*80)
        print("Step 1: Authenticate User")
        print("="*80)
        
        # Try login first
        print("Attempting to login...")
        if self.login_user_silent():
            print(f"✅ Logged in successfully")
            print(f"   Token: {self.token[:20]}...")
            return True
        
        # If login fails, try to register
        print("Login failed, attempting to register new user...")
        return self.register_user()
    
    def login_user_silent(self):
        """Try to login without printing errors"""
        response = requests.post(
            f"{BASE_URL}/api/login",
            json={
                "username": TEST_USERNAME,
                "password": TEST_PASSWORD
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            self.token = data["access_token"]
            return True
        return False

    def register_user(self):
        """Register a test user"""
        
        response = requests.post(
            f"{BASE_URL}/api/register",
            json={
                "username": TEST_USERNAME,
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD,
                "full_name": "Test User"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            self.token = data["access_token"]
            print(f"✅ User registered successfully")
            print(f"   Token: {self.token[:20]}...")
            return True
        elif response.status_code == 400:
            # User already exists (check for both English and Chinese error messages)
            response_text = response.text.lower()
            if "already exists" in response_text or "已存在" in response_text or "exist" in response_text:
                print(f"ℹ️  User already exists, trying to login...")
                return self.login_user()
            else:
                print(f"❌ Registration failed: {response.text}")
                return False
        else:
            print(f"❌ Registration failed: {response.text}")
            return False

    def login_user(self):
        """Login and get token"""
        print("\n" + "="*80)
        print("Step 1: Login User")
        print("="*80)
        
        response = requests.post(
            f"{BASE_URL}/api/login",
            json={
                "username": TEST_USERNAME,
                "password": TEST_PASSWORD
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            self.token = data["access_token"]
            print(f"✅ Login successful")
            print(f"   Token: {self.token[:20]}...")
            return True
        else:
            print(f"❌ Login failed: {response.text}")
            return False

    def get_headers(self):
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def create_test_recording(self):
        """Create a test recording with sample operations"""
        print("\n" + "="*80)
        print("Step 2: Create Test Recording")
        print("="*80)
        
        # Start recording
        response = requests.post(
            f"{BASE_URL}/api/recording/start",
            headers=self.get_headers(),
            json={
                "title": "Test Coffee Collection Workflow",
                "description": "Collect coffee products from a sample website"
            }
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to start recording: {response.text}")
            return False
        
        data = response.json()
        self.session_id = data["session_id"]
        print(f"✅ Recording started: {self.session_id}")
        
        # Add sample operations
        sample_operations = [
            {
                "type": "navigate",
                "url": "https://www.example.com/coffee",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            {
                "type": "click",
                "element": {"tag": "button", "text": "Show Products"},
                "url": "https://www.example.com/coffee",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            {
                "type": "extract",
                "data": {"products": ["Coffee A", "Coffee B", "Coffee C"]},
                "url": "https://www.example.com/coffee",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ]
        
        for op in sample_operations:
            response = requests.post(
                f"{BASE_URL}/api/recording/operation",
                headers=self.get_headers(),
                json={
                    "session_id": self.session_id,
                    "operation": op
                }
            )
            
            if response.status_code != 200:
                print(f"❌ Failed to add operation: {response.text}")
                return False
        
        print(f"✅ Added {len(sample_operations)} operations")
        
        # Stop recording
        response = requests.post(
            f"{BASE_URL}/api/recording/stop",
            headers=self.get_headers(),
            json={"session_id": self.session_id}
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to stop recording: {response.text}")
            return False
        
        print(f"✅ Recording stopped")
        return True

    def list_learning_sessions(self):
        """List learning sessions"""
        print("\n" + "="*80)
        print("Step 3: List Learning Sessions")
        print("="*80)
        
        response = requests.get(
            f"{BASE_URL}/api/learning/sessions",
            headers=self.get_headers()
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to list sessions: {response.text}")
            return False
        
        data = response.json()
        print(f"✅ Found {data['total']} learning sessions")
        
        if data['sessions']:
            for session in data['sessions'][:3]:  # Show first 3
                print(f"   - {session['session_id']}: {session['title']} (status: {session['status']})")
        
        return True

    def extract_intents(self):
        """Extract intents from recording"""
        print("\n" + "="*80)
        print("Step 4: Extract Intents")
        print("="*80)
        print(f"⏳ Extracting intents for session: {self.session_id}")
        print("   This may take 30-60 seconds (calling LLM)...")
        
        response = requests.post(
            f"{BASE_URL}/api/learning/extract-intents",
            headers=self.get_headers(),
            json={"session_id": self.session_id}
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to extract intents: {response.text}")
            return False
        
        data = response.json()
        print(f"✅ Extracted {data['intents_count']} intents")
        
        if data['intents']:
            for intent in data['intents'][:3]:  # Show first 3
                print(f"   - {intent['id']}: {intent['description'][:60]}...")
        
        return True

    def generate_metaflow(self):
        """Generate MetaFlow"""
        print("\n" + "="*80)
        print("Step 5: Generate MetaFlow")
        print("="*80)
        print(f"⏳ Generating MetaFlow for session: {self.session_id}")
        print("   This may take 30-60 seconds (calling LLM)...")
        
        response = requests.post(
            f"{BASE_URL}/api/learning/generate-metaflow",
            headers=self.get_headers(),
            json={"session_id": self.session_id}
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to generate metaflow: {response.text}")
            return False
        
        data = response.json()
        print(f"✅ Generated MetaFlow with {data['nodes_count']} nodes")
        print(f"\nMetaFlow YAML preview (first 300 chars):")
        print(data['metaflow_yaml'][:300] + "...")
        
        return True

    def generate_workflow(self):
        """Generate Workflow"""
        print("\n" + "="*80)
        print("Step 6: Generate Workflow")
        print("="*80)
        print(f"⏳ Generating Workflow for session: {self.session_id}")
        print("   This may take 30-90 seconds (calling LLM)...")
        
        response = requests.post(
            f"{BASE_URL}/api/workflows/generate",
            headers=self.get_headers(),
            json={"session_id": self.session_id}
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to generate workflow: {response.text}")
            return False
        
        data = response.json()
        self.workflow_name = data['workflow_name']
        print(f"✅ Generated workflow: {self.workflow_name}")
        print(f"   Overwritten: {data['overwritten']}")
        print(f"\nWorkflow YAML preview (first 300 chars):")
        print(data['workflow_yaml'][:300] + "...")
        
        return True

    def list_workflows(self):
        """List workflows"""
        print("\n" + "="*80)
        print("Step 7: List Workflows")
        print("="*80)
        
        response = requests.get(
            f"{BASE_URL}/api/workflows",
            headers=self.get_headers()
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to list workflows: {response.text}")
            return False
        
        data = response.json()
        print(f"✅ Found {data['total']} workflows")
        
        if data['workflows']:
            for workflow in data['workflows'][:5]:  # Show first 5
                print(f"   - {workflow['workflow_name']}")
                print(f"     Executions: {workflow['execution_count']}, "
                      f"Last: {workflow.get('last_executed_at', 'Never')}")
        
        return True

    def execute_workflow(self):
        """Execute workflow"""
        print("\n" + "="*80)
        print("Step 8: Execute Workflow")
        print("="*80)
        print(f"⏳ Starting execution of workflow: {self.workflow_name}")
        
        response = requests.post(
            f"{BASE_URL}/api/workflows/{self.workflow_name}/execute",
            headers=self.get_headers()
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to execute workflow: {response.text}")
            return False
        
        data = response.json()
        self.task_id = data['task_id']
        print(f"✅ Workflow execution started")
        print(f"   Task ID: {self.task_id}")
        print(f"   Status: {data['status']}")
        
        return True

    def check_execution_status(self):
        """Check execution status"""
        print("\n" + "="*80)
        print("Step 9: Check Execution Status")
        print("="*80)
        print(f"⏳ Checking status for task: {self.task_id}")
        
        import time
        max_wait = 120  # Wait up to 2 minutes
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            response = requests.get(
                f"{BASE_URL}/api/workflows/executions/{self.task_id}",
                headers=self.get_headers()
            )
            
            if response.status_code != 200:
                print(f"❌ Failed to get status: {response.text}")
                return False
            
            data = response.json()
            execution = data['execution']
            status = execution['status']
            progress = execution.get('progress', 0)
            
            print(f"   Status: {status}, Progress: {progress}%")
            
            if status == 'completed':
                print(f"✅ Workflow execution completed!")
                print(f"   Execution time: {execution.get('execution_time_ms', 0)}ms")
                if execution.get('result'):
                    print(f"   Result: {json.dumps(execution['result'], indent=2)}")
                return True
            elif status == 'failed':
                print(f"❌ Workflow execution failed!")
                print(f"   Error: {execution.get('error_message', 'Unknown error')}")
                return False
            
            time.sleep(5)  # Wait 5 seconds before checking again
        
        print(f"⏱️  Timeout waiting for execution to complete")
        return False

    def list_executions(self):
        """List execution history"""
        print("\n" + "="*80)
        print("Step 10: List Execution History")
        print("="*80)
        
        response = requests.get(
            f"{BASE_URL}/api/workflows/{self.workflow_name}/executions",
            headers=self.get_headers()
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to list executions: {response.text}")
            return False
        
        data = response.json()
        print(f"✅ Found {data['total']} executions for workflow '{self.workflow_name}'")
        
        if data['executions']:
            for exec in data['executions'][:5]:  # Show first 5
                print(f"   - {exec['task_id']}")
                print(f"     Status: {exec['status']}, Time: {exec.get('execution_time_ms', 0)}ms")
                print(f"     Started: {exec['started_at']}")
        
        return True

    def run_full_test(self):
        """Run complete test flow"""
        print("\n" + "🚀 " + "="*76 + " 🚀")
        print("   WORKFLOW MANAGEMENT SYSTEM - FULL TEST")
        print("🚀 " + "="*76 + " 🚀\n")
        
        steps = [
            ("Authenticate", self.authenticate),
            ("Create Test Recording", self.create_test_recording),
            ("List Learning Sessions", self.list_learning_sessions),
            ("Extract Intents", self.extract_intents),
            ("Generate MetaFlow", self.generate_metaflow),
            ("Generate Workflow", self.generate_workflow),
            ("List Workflows", self.list_workflows),
            ("Execute Workflow", self.execute_workflow),
            ("Check Execution Status", self.check_execution_status),
            ("List Execution History", self.list_executions),
        ]
        
        for step_name, step_func in steps:
            try:
                if not step_func():
                    print(f"\n❌ Test failed at step: {step_name}")
                    return False
            except Exception as e:
                print(f"\n❌ Exception in step '{step_name}': {e}")
                import traceback
                traceback.print_exc()
                return False
        
        print("\n" + "🎉 " + "="*76 + " 🎉")
        print("   ALL TESTS PASSED!")
        print("🎉 " + "="*76 + " 🎉\n")
        
        return True


def main():
    """Main test function"""
    print("Starting Workflow Management API tests...")
    print(f"Backend URL: {BASE_URL}")
    
    # Check if backend is running
    try:
        response = requests.get(f"{BASE_URL}/api/health")
        if response.status_code != 200:
            print(f"❌ Backend is not healthy: {response.text}")
            return
    except Exception as e:
        print(f"❌ Cannot connect to backend at {BASE_URL}")
        print(f"   Please start the backend first: cd src/client/web/backend && python main.py")
        return
    
    print(f"✅ Backend is running\n")
    
    # Run tests
    tester = WorkflowAPITester()
    tester.run_full_test()


if __name__ == "__main__":
    main()
