#!/usr/bin/env python3
"""
Test 4: Execute Workflow

This test executes a generated workflow and monitors its progress.
"""
import sys
import requests
import json
import time
from pathlib import Path

# Colors
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'

APP_BACKEND_URL = "http://127.0.0.1:8765"
STORAGE_PATH = Path.home() / ".ami" / "users" / "default_user"


def print_section(title):
    print(f"\n{YELLOW}{'=' * 60}{NC}")
    print(f"{YELLOW}{title:^60}{NC}")
    print(f"{YELLOW}{'=' * 60}{NC}")


def get_latest_workflow_name():
    """Get the most recent workflow_name from local storage"""
    print_section("Step 1: Find Latest Workflow")

    workflows_path = STORAGE_PATH / "workflows"

    if not workflows_path.exists():
        print(f"{RED}✗ No workflows found at {workflows_path}{NC}")
        print(f"\n{YELLOW}Please run test 3 first:{NC}")
        print(f"  python tests/app_backend/manual/3_test_generate_workflow.py")
        return None

    # Find all workflow directories
    workflows = sorted(workflows_path.glob("workflow_*"), reverse=True, key=lambda p: p.stat().st_mtime)

    if not workflows:
        print(f"{RED}✗ No workflow directories found{NC}")
        return None

    latest_workflow = workflows[0]
    workflow_name = latest_workflow.name

    print(f"{GREEN}✓ Found Workflow in local storage:{NC}")
    print(f"  Workflow Name: {workflow_name}")
    print(f"  Path: {latest_workflow}")

    return workflow_name


def execute_workflow(workflow_name):
    """Execute workflow via App Backend"""
    print_section("Step 2: Execute Workflow")

    print(f"{BLUE}Workflow Name: {workflow_name}{NC}")
    print()

    request_data = {
        "workflow_name": workflow_name,
        "user_id": "default_user"
    }

    print(f"{BLUE}→ Calling: POST {APP_BACKEND_URL}/api/workflow/execute{NC}")
    print()

    try:
        response = requests.post(
            f"{APP_BACKEND_URL}/api/workflow/execute",
            json=request_data
        )

        print(f"{GREEN}← Status: {response.status_code}{NC}")

        if response.status_code == 200:
            result = response.json()
            task_id = result.get("task_id")
            status = result.get("status")

            print(f"{GREEN}✓ Workflow execution started!{NC}")
            print(f"  Task ID: {task_id}")
            print(f"  Status: {status}")

            return task_id
        else:
            print(f"{RED}✗ Execution failed{NC}")
            print(f"  Response: {response.text}")
            return None

    except requests.ConnectionError:
        print(f"{RED}✗ Cannot connect to App Backend at {APP_BACKEND_URL}{NC}")
        print(f"\n{YELLOW}Please start App Backend:{NC}")
        print(f"  python src/app_backend/daemon.py")
        return None
    except Exception as e:
        print(f"{RED}✗ Error: {e}{NC}")
        return None


def monitor_workflow(task_id):
    """Monitor workflow execution progress"""
    print_section("Step 3: Monitor Execution")

    print(f"{BLUE}Task ID: {task_id}{NC}")
    print()

    try:
        while True:
            response = requests.get(f"{APP_BACKEND_URL}/api/workflow/status/{task_id}")

            if response.status_code == 200:
                result = response.json()
                status = result.get("status")
                progress = result.get("progress", 0)
                current_step = result.get("current_step", 0)
                total_steps = result.get("total_steps", 0)
                message = result.get("message", "")
                error = result.get("error")

                # Display progress
                print(f"\r{BLUE}Status: {status:10} | Progress: {progress:3}% | Step: {current_step}/{total_steps} | {message[:40]:<40}{NC}", end="")

                # Check if completed
                if status == "completed":
                    print()  # New line
                    print(f"\n{GREEN}✓ Workflow completed successfully!{NC}")
                    final_result = result.get("result")
                    if final_result:
                        print(f"\n{BLUE}Final Result:{NC}")
                        print(f"  {json.dumps(final_result, indent=2)}")
                    return True

                elif status == "failed":
                    print()  # New line
                    print(f"\n{RED}✗ Workflow execution failed{NC}")
                    if error:
                        print(f"  Error: {error}")
                    return False

                # Wait before next poll
                time.sleep(1)

            elif response.status_code == 404:
                print(f"\n{RED}✗ Task not found: {task_id}{NC}")
                return False
            else:
                print(f"\n{RED}✗ Failed to get status{NC}")
                print(f"  Response: {response.text}")
                return False

    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Monitoring interrupted by user{NC}")
        print(f"{YELLOW}Task is still running in background{NC}")
        return False
    except Exception as e:
        print(f"\n{RED}✗ Error: {e}{NC}")
        return False


def main():
    print(f"{YELLOW}╔════════════════════════════════════════════════════════════╗{NC}")
    print(f"{YELLOW}║  Test 4: Execute Workflow                                 ║{NC}")
    print(f"{YELLOW}╚════════════════════════════════════════════════════════════╝{NC}")

    # Get workflow_name from command line or find latest
    if len(sys.argv) > 1:
        workflow_name = sys.argv[1]
        print(f"\n{BLUE}Using provided Workflow Name: {workflow_name}{NC}")
    else:
        workflow_name = get_latest_workflow_name()
        if not workflow_name:
            return 1

    # Execute workflow
    task_id = execute_workflow(workflow_name)
    if not task_id:
        return 1

    # Monitor progress
    success = monitor_workflow(task_id)

    # Summary
    print_section("Summary")
    if success:
        print(f"{GREEN}✓ Workflow executed successfully!{NC}")
        print(f"\n{BLUE}Workflow: {workflow_name}{NC}")
        print(f"{BLUE}Task ID: {task_id}{NC}")

        print(f"\n{YELLOW}What happened:{NC}")
        print(f"  1. App Backend loaded workflow from local storage")
        print(f"  2. Executed workflow using browser automation")
        print(f"  3. Completed all steps successfully")
    else:
        print(f"{RED}✗ Workflow execution failed or was interrupted{NC}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
