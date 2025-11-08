#!/usr/bin/env python3
"""
Test 2: Generate Workflow from Recording

This script tests the complete workflow generation process via App Backend daemon.
The daemon handles all steps internally:
1. Load recording from local storage
2. Upload to Cloud Backend
3. Generate MetaFlow (LLM)
4. Generate Workflow YAML (LLM)
5. Download and save workflow

Prerequisites:
1. App Backend daemon running on http://localhost:8765
2. Cloud Backend running on http://localhost:9000
3. LLM API key configured (ANTHROPIC_API_KEY or OPENAI_API_KEY)
4. Recording data exists (run 1_test_recording.py first)

Flow:
1. Load latest recording session_id from local storage
2. Call daemon's /api/workflow/generate endpoint
3. Daemon handles Cloud Backend communication internally
4. Verify workflow was saved locally
"""
import json
import requests
from pathlib import Path

# Colors
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'

DAEMON_URL = "http://localhost:8765"
STORAGE_PATH = Path.home() / "ami" / "users" / "default_user"


def print_section(title):
    print(f"\n{YELLOW}{'=' * 60}{NC}")
    print(f"{YELLOW}{title:^60}{NC}")
    print(f"{YELLOW}{'=' * 60}{NC}")


def get_latest_session_id():
    """Get the most recent recording session_id"""
    print_section("Step 1: Get Latest Recording")

    recordings_path = STORAGE_PATH / "recordings"

    if not recordings_path.exists():
        print(f"{RED}✗ No recordings found at {recordings_path}{NC}")
        print(f"\n{YELLOW}Please run test 1 first:{NC}")
        print(f"  python tests/app_backend/1_test_recording.py")
        return None

    # Find all session directories
    sessions = sorted(recordings_path.glob("session_*"), reverse=True)

    if not sessions:
        print(f"{RED}✗ No session directories found{NC}")
        return None

    latest_session = sessions[0]
    session_id = latest_session.name

    # Load to verify it exists
    operations_file = latest_session / "operations.json"
    if not operations_file.exists():
        print(f"{RED}✗ operations.json not found in {latest_session}{NC}")
        return None

    with open(operations_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"{GREEN}✓ Found recording:{NC}")
    print(f"  Session ID: {session_id}")
    print(f"  Operations: {data.get('operations_count')}")

    if 'task_metadata' in data:
        print(f"  Task Metadata:")
        for key, value in data['task_metadata'].items():
            print(f"    - {key}: {value}")

    return session_id


def generate_workflow(session_id, user_description=None):
    """Generate workflow via daemon API"""
    print_section("Step 2: Generate Workflow via Daemon")

    print(f"{BLUE}Session ID: {session_id}{NC}")

    # Use provided description or default
    title = "Test Workflow"
    description = user_description or "Automated workflow from recording"

    print(f"{BLUE}Title: {title}{NC}")
    print(f"{BLUE}Description: {description}{NC}")
    print()

    payload = {
        "session_id": session_id,
        "title": title,
        "description": description,
        "user_id": "default_user"
    }

    print(f"{BLUE}→ Calling daemon: POST {DAEMON_URL}/api/workflow/generate{NC}")
    print(f"{YELLOW}  This will take 30-120 seconds (LLM processing)...{NC}")
    print(f"{YELLOW}  Daemon will: upload recording → generate workflow → download and save{NC}")
    print()

    try:
        response = requests.post(
            f"{DAEMON_URL}/api/workflow/generate",
            json=payload,
            timeout=180  # 3 minutes for LLM
        )

        print(f"{GREEN}← Status: {response.status_code}{NC}")

        if response.status_code == 200:
            result = response.json()
            print(f"{GREEN}✓ Workflow generated!{NC}")
            print(f"  Workflow Name: {result.get('workflow_name')}")
            print(f"  Local Path: {result.get('local_path')}")
            return result
        else:
            print(f"{RED}✗ Generation failed{NC}")
            print(f"  Response: {response.text}")
            return None

    except requests.Timeout:
        print(f"{RED}✗ Request timeout (LLM took too long){NC}")
        return None
    except requests.ConnectionError:
        print(f"{RED}✗ Cannot connect to daemon at {DAEMON_URL}{NC}")
        print(f"\n{YELLOW}Please start the daemon:{NC}")
        print(f"  ./scripts/start_app_backend.sh")
        return None
    except Exception as e:
        print(f"{RED}✗ Error: {e}{NC}")
        return None


def verify_workflow(workflow_name):
    """Verify workflow was saved locally"""
    print_section("Step 3: Verify Workflow")

    workflow_path = STORAGE_PATH / "workflows" / workflow_name / "workflow.yaml"

    print(f"{BLUE}→ Checking: {workflow_path}{NC}")

    if workflow_path.exists():
        print(f"{GREEN}✓ Workflow file exists!{NC}")

        # Read and display first few lines
        with open(workflow_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()[:10]

        print(f"\n{BLUE}Preview (first 10 lines):{NC}")
        for line in lines:
            print(f"  {line.rstrip()}")

        if len(lines) >= 10:
            print("  ...")

        return True
    else:
        print(f"{RED}✗ Workflow file not found{NC}")
        return False


def main():
    import sys

    print(f"{YELLOW}╔════════════════════════════════════════════════════════════╗{NC}")
    print(f"{YELLOW}║  Test 2: Generate Workflow from Recording                 ║{NC}")
    print(f"{YELLOW}╚════════════════════════════════════════════════════════════╝{NC}")

    # Step 1: Get latest recording session_id
    session_id = get_latest_session_id()
    if not session_id:
        return 1

    # Step 2: Generate workflow
    # User can provide custom description as command line argument
    user_description = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None

    result = generate_workflow(session_id, user_description)
    if not result:
        return 1

    workflow_name = result.get('workflow_name')

    # Step 3: Verify workflow
    if not verify_workflow(workflow_name):
        return 1

    # Success
    print_section("Summary")
    print(f"{GREEN}✓ All steps completed successfully!{NC}")
    print(f"\n{BLUE}Workflow Name: {workflow_name}{NC}")
    print(f"{BLUE}Workflow Path: {STORAGE_PATH / 'workflows' / workflow_name / 'workflow.yaml'}{NC}")

    print(f"\n{YELLOW}What happened internally:{NC}")
    print(f"  1. Daemon loaded recording from local storage")
    print(f"  2. Daemon uploaded recording to Cloud Backend")
    print(f"  3. Cloud Backend generated workflow (MetaFlow → Workflow YAML) using LLM")
    print(f"  4. Daemon downloaded workflow YAML from Cloud Backend")
    print(f"  5. Daemon saved workflow locally")

    print(f"\n{YELLOW}Next step:{NC}")
    print(f"  Execute the workflow:")
    print(f"  curl -X POST {DAEMON_URL}/api/workflow/execute \\")
    print(f"    -H 'Content-Type: application/json' \\")
    print(f"    -d '{{\"workflow_name\": \"{workflow_name}\", \"user_id\": \"default_user\"}}'")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
