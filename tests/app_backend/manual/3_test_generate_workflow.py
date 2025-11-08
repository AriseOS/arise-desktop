#!/usr/bin/env python3
"""
Test 3: Generate Workflow from MetaFlow

This test generates a Workflow YAML from a MetaFlow.
"""
import sys
import requests
import json
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


def get_latest_metaflow_id():
    """Get the most recent metaflow_id from local storage"""
    print_section("Step 1: Find Latest MetaFlow")

    metaflows_path = STORAGE_PATH / "metaflows"

    if not metaflows_path.exists():
        print(f"{RED}✗ No metaflows found at {metaflows_path}{NC}")
        print(f"\n{YELLOW}Please run test 2 first:{NC}")
        print(f"  python tests/app_backend/manual/2_test_generate_metaflow.py")
        return None

    # Find all metaflow directories
    metaflows = sorted(metaflows_path.glob("metaflow_*"), reverse=True, key=lambda p: p.stat().st_mtime)

    if not metaflows:
        print(f"{RED}✗ No metaflow directories found{NC}")
        return None

    latest_metaflow = metaflows[0]
    metaflow_id = latest_metaflow.name

    # Load task description
    task_file = latest_metaflow / "task_description.txt"
    if task_file.exists():
        with open(task_file, 'r', encoding='utf-8') as f:
            task_description = f.read()
    else:
        task_description = "N/A"

    print(f"{GREEN}✓ Found MetaFlow in local storage:{NC}")
    print(f"  MetaFlow ID: {metaflow_id}")
    print(f"  Task: {task_description}")

    return metaflow_id


def generate_workflow(metaflow_id):
    """Generate Workflow via App Backend"""
    print_section("Step 2: Generate Workflow")

    print(f"{BLUE}MetaFlow ID: {metaflow_id}{NC}")
    print()

    request_data = {
        "metaflow_id": metaflow_id,
        "user_id": "default_user"
    }

    print(f"{BLUE}→ Calling: POST {APP_BACKEND_URL}/api/workflows/generate{NC}")
    print(f"{YELLOW}  This will take 30-60 seconds (LLM processing)...{NC}")
    print()

    try:
        response = requests.post(
            f"{APP_BACKEND_URL}/api/workflows/generate",
            json=request_data,
            timeout=180  # 3 minutes for LLM
        )

        print(f"{GREEN}← Status: {response.status_code}{NC}")

        if response.status_code == 200:
            result = response.json()
            workflow_name = result.get("workflow_name")
            local_path = result.get("local_path")

            print(f"{GREEN}✓ Workflow generated and saved!{NC}")
            print(f"  Workflow Name: {workflow_name}")
            print(f"  Local path: {local_path}")

            # Display preview
            if Path(local_path).exists():
                with open(local_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()[:10]
                print(f"\n{BLUE}Preview (first 10 lines):{NC}")
                for line in lines:
                    print(f"  {line.rstrip()}")
                if len(lines) >= 10:
                    print("  ...")

            return workflow_name, local_path
        else:
            print(f"{RED}✗ Generation failed{NC}")
            print(f"  Response: {response.text}")
            return None, None

    except requests.Timeout:
        print(f"{RED}✗ Request timeout (LLM took too long){NC}")
        return None, None
    except requests.ConnectionError:
        print(f"{RED}✗ Cannot connect to App Backend at {APP_BACKEND_URL}{NC}")
        print(f"\n{YELLOW}Please start App Backend:{NC}")
        print(f"  python src/app_backend/daemon.py")
        return None, None
    except Exception as e:
        print(f"{RED}✗ Error: {e}{NC}")
        return None, None


def main():
    print(f"{YELLOW}╔════════════════════════════════════════════════════════════╗{NC}")
    print(f"{YELLOW}║  Test 3: Generate Workflow from MetaFlow                  ║{NC}")
    print(f"{YELLOW}╚════════════════════════════════════════════════════════════╝{NC}")

    # Get metaflow_id from command line or find latest
    if len(sys.argv) > 1:
        metaflow_id = sys.argv[1]
        print(f"\n{BLUE}Using provided MetaFlow ID: {metaflow_id}{NC}")
    else:
        metaflow_id = get_latest_metaflow_id()
        if not metaflow_id:
            return 1

    # Generate workflow
    workflow_name, local_path = generate_workflow(metaflow_id)
    if not workflow_name:
        return 1

    # Success
    print_section("Summary")
    print(f"{GREEN}✓ Workflow generated and saved successfully!{NC}")
    print(f"\n{BLUE}Workflow Name: {workflow_name}{NC}")
    print(f"{BLUE}Local file: {local_path}{NC}")

    print(f"\n{YELLOW}What happened:{NC}")
    print(f"  1. App Backend called Cloud Backend to generate Workflow")
    print(f"  2. Cloud Backend loaded MetaFlow and generated Workflow YAML (LLM)")
    print(f"  3. Workflow returned in response")
    print(f"  4. App Backend saved Workflow to local storage")

    print(f"\n{YELLOW}Next step:{NC}")
    print(f"  Execute this workflow:")
    print(f"  python tests/app_backend/manual/4_test_execute.py {workflow_name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
