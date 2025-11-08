#!/usr/bin/env python3
"""
Test 5: List User Workflows

This script tests listing all workflows for a user.
"""
import sys
import json
import requests

# Colors
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'

CLOUD_BACKEND_URL = "http://localhost:9000"
USER_ID = "default_user"


def print_section(title):
    print(f"\n{YELLOW}{'=' * 60}{NC}")
    print(f"{YELLOW}{title:^60}{NC}")
    print(f"{YELLOW}{'=' * 60}{NC}")


def list_workflows():
    """List all workflows for user"""
    print_section("Test 5: List Workflows")

    print(f"{BLUE}User ID: {USER_ID}{NC}")
    print()

    print(f"{BLUE}→ Calling: GET {CLOUD_BACKEND_URL}/api/workflows?user_id={USER_ID}{NC}")
    print()

    try:
        response = requests.get(
            f"{CLOUD_BACKEND_URL}/api/workflows",
            params={"user_id": USER_ID},
            timeout=30
        )

        print(f"{GREEN}← Status: {response.status_code}{NC}")

        if response.status_code == 200:
            workflows = response.json()

            print(f"{GREEN}✓ Workflows retrieved!{NC}")
            print(f"  Total: {len(workflows)} workflows")
            print()

            if workflows:
                print(f"{BLUE}Workflows:{NC}")
                for i, workflow in enumerate(workflows, 1):
                    workflow_name = workflow.get("name", "Unknown")
                    print(f"  {i}. {workflow_name}")
            else:
                print(f"{YELLOW}No workflows found{NC}")
                print(f"\n{YELLOW}To create a workflow:{NC}")
                print(f"  1. python tests/cloud_backend/manual/1_test_upload_recording.py")
                print(f"  2. python tests/cloud_backend/manual/2_test_generate_metaflow.py")
                print(f"  3. python tests/cloud_backend/manual/3_test_generate_workflow.py")

            return workflows
        else:
            print(f"{RED}✗ Request failed{NC}")
            print(f"  Response: {response.text}")
            return None

    except requests.ConnectionError:
        print(f"{RED}✗ Cannot connect to Cloud Backend at {CLOUD_BACKEND_URL}{NC}")
        print(f"\n{YELLOW}Please start Cloud Backend:{NC}")
        print(f"  ./scripts/start_cloud_backend.sh")
        return None
    except Exception as e:
        print(f"{RED}✗ Error: {e}{NC}")
        return None


def main():
    print(f"{YELLOW}╔════════════════════════════════════════════════════════════╗{NC}")
    print(f"{YELLOW}║  Test 5: List User Workflows                              ║{NC}")
    print(f"{YELLOW}╚════════════════════════════════════════════════════════════╝{NC}")

    workflows = list_workflows()
    if workflows is None:
        return 1

    # Success
    print_section("Summary")
    print(f"{GREEN}✓ Workflow list retrieved successfully!{NC}")
    print(f"\n{BLUE}Total Workflows: {len(workflows)}{NC}")

    print(f"\n{YELLOW}What happened:{NC}")
    print(f"  1. Cloud Backend scanned user's workflows directory")
    print(f"  2. Returned list of all workflow names")
    print(f"  3. Storage location: ~/.ami/users/{USER_ID}/workflows/")

    if workflows:
        print(f"\n{YELLOW}To download a workflow:{NC}")
        print(f"  python tests/cloud_backend/manual/4_test_download_workflow.py <workflow_name>")

    return 0


if __name__ == "__main__":
    sys.exit(main())
