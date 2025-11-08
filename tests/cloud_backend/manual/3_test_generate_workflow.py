#!/usr/bin/env python3
"""
Test 3: Generate Workflow from MetaFlow

This script tests generating Workflow YAML from a MetaFlow.

The script will:
1. Request Cloud Backend to generate Workflow from MetaFlow
2. Download the generated Workflow YAML via HTTP
3. Save to local directory for inspection
"""
import sys
import json
import requests
from pathlib import Path

# Colors
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'

CLOUD_BACKEND_URL = "http://localhost:9000"
USER_ID = "default_user"

# Local download directory
DOWNLOAD_DIR = Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)


def print_section(title):
    print(f"\n{YELLOW}{'=' * 60}{NC}")
    print(f"{YELLOW}{title:^60}{NC}")
    print(f"{YELLOW}{'=' * 60}{NC}")


def get_latest_metaflow_id():
    """Get the most recent metaflow_id from local downloads"""
    print_section("Step 1: Find Latest MetaFlow")

    if not DOWNLOAD_DIR.exists():
        print(f"{RED}✗ No downloads directory found{NC}")
        print(f"\n{YELLOW}Please run test 2 first:{NC}")
        print(f"  python tests/cloud_backend/manual/2_test_generate_metaflow.py")
        return None

    # Find all metaflow directories
    metaflows = sorted(DOWNLOAD_DIR.glob("metaflow_*"), reverse=True, key=lambda p: p.stat().st_mtime)

    if not metaflows:
        print(f"{RED}✗ No metaflow directories found{NC}")
        print(f"\n{YELLOW}Please run test 2 first:{NC}")
        print(f"  python tests/cloud_backend/manual/2_test_generate_metaflow.py")
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

    print(f"{GREEN}✓ Found MetaFlow in local downloads:{NC}")
    print(f"  MetaFlow ID: {metaflow_id}")
    print(f"  Task: {task_description}")

    return metaflow_id


def generate_and_save_workflow(metaflow_id):
    """Generate Workflow from MetaFlow and save to local"""
    print_section("Step 2: Generate Workflow")

    print(f"{BLUE}MetaFlow ID: {metaflow_id}{NC}")
    print(f"{BLUE}User ID: {USER_ID}{NC}")
    print()

    payload = {
        "user_id": USER_ID
    }

    print(f"{BLUE}→ Calling: POST {CLOUD_BACKEND_URL}/api/metaflows/{metaflow_id}/generate_workflow{NC}")
    print(f"{YELLOW}  This will take 30-60 seconds (LLM processing)...{NC}")
    print()

    try:
        response = requests.post(
            f"{CLOUD_BACKEND_URL}/api/metaflows/{metaflow_id}/generate_workflow",
            json=payload,
            timeout=180  # 3 minutes for LLM
        )

        print(f"{GREEN}← Status: {response.status_code}{NC}")

        if response.status_code == 200:
            result = response.json()
            workflow_name = result.get("workflow_name")
            workflow_yaml = result.get("workflow_yaml")

            print(f"{GREEN}✓ Workflow generated!{NC}")
            print(f"  Workflow Name: {workflow_name}")
            print(f"  Size: {len(workflow_yaml)} characters")
            print()

            # Save to local directory
            workflow_dir = DOWNLOAD_DIR / workflow_name
            workflow_dir.mkdir(exist_ok=True)

            yaml_file = workflow_dir / "workflow.yaml"
            with open(yaml_file, 'w', encoding='utf-8') as f:
                f.write(workflow_yaml)

            print(f"{GREEN}✓ Saved to local:{NC}")
            print(f"  {yaml_file}")

            # Display first few lines
            lines = workflow_yaml.split('\n')[:10]
            print(f"\n{BLUE}Preview (first 10 lines):{NC}")
            for line in lines:
                print(f"  {line}")
            if len(workflow_yaml.split('\n')) > 10:
                print("  ...")

            return workflow_name, str(yaml_file)
        else:
            print(f"{RED}✗ Generation failed{NC}")
            print(f"  Response: {response.text}")
            return None, None

    except requests.Timeout:
        print(f"{RED}✗ Request timeout (LLM took too long){NC}")
        return None, None
    except requests.ConnectionError:
        print(f"{RED}✗ Cannot connect to Cloud Backend at {CLOUD_BACKEND_URL}{NC}")
        print(f"\n{YELLOW}Please start Cloud Backend:{NC}")
        print(f"  ./scripts/start_cloud_backend.sh")
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

    # Generate workflow and save to local
    workflow_name, local_file = generate_and_save_workflow(metaflow_id)
    if not workflow_name:
        return 1

    # Success
    print_section("Summary")
    print(f"{GREEN}✓ Workflow generated and saved successfully!{NC}")
    print(f"\n{BLUE}Workflow Name: {workflow_name}{NC}")
    print(f"{BLUE}Local file: {local_file}{NC}")

    print(f"\n{YELLOW}What happened:{NC}")
    print(f"  1. Cloud Backend loaded MetaFlow YAML")
    print(f"  2. WorkflowGenerator generated Workflow YAML (LLM)")
    print(f"  3. Workflow returned in response and saved on server")
    print(f"  4. Saved Workflow to local directory")

    print(f"\n{YELLOW}Next steps:{NC}")
    print(f"  List all workflows:")
    print(f"  python tests/cloud_backend/manual/5_test_list_workflows.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
