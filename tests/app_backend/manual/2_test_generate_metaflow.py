#!/usr/bin/env python3
"""
Test 2: Generate MetaFlow from Intent Memory Graph

This test generates a MetaFlow from the user's cumulative Intent Graph.
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


def generate_metaflow(task_description):
    """Generate MetaFlow via App Backend"""
    print_section("Generate MetaFlow")

    print(f"{BLUE}Task: {task_description}{NC}")
    print()

    request_data = {
        "task_description": task_description,
        "user_id": "default_user"
    }

    print(f"{BLUE}→ Calling: POST {APP_BACKEND_URL}/api/metaflows/generate{NC}")
    print(f"{YELLOW}  This will take 30-60 seconds (LLM processing)...{NC}")
    print()

    try:
        response = requests.post(
            f"{APP_BACKEND_URL}/api/metaflows/generate",
            json=request_data,
            timeout=180  # 3 minutes for LLM
        )

        print(f"{GREEN}← Status: {response.status_code}{NC}")

        if response.status_code == 200:
            result = response.json()
            metaflow_id = result.get("metaflow_id")
            local_path = result.get("local_path")

            print(f"{GREEN}✓ MetaFlow generated and saved!{NC}")
            print(f"  MetaFlow ID: {metaflow_id}")
            print(f"  Local path: {local_path}")

            return metaflow_id, local_path
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
    print(f"{YELLOW}║  Test 2: Generate MetaFlow from Intent Graph              ║{NC}")
    print(f"{YELLOW}╚════════════════════════════════════════════════════════════╝{NC}")

    # Get task description from command line or use default
    if len(sys.argv) > 1:
        task_description = " ".join(sys.argv[1:])
    else:
        task_description = "Search for coffee on Google"
        print(f"\n{YELLOW}No task description provided, using default:{NC}")
        print(f"  \"{task_description}\"")
        print(f"\n{YELLOW}Usage:{NC}")
        print(f"  python {sys.argv[0]} \"Your task description here\"")

    # Generate MetaFlow
    metaflow_id, local_path = generate_metaflow(task_description)
    if not metaflow_id:
        return 1

    # Success
    print_section("Summary")
    print(f"{GREEN}✓ MetaFlow generated and saved successfully!{NC}")
    print(f"\n{BLUE}MetaFlow ID: {metaflow_id}{NC}")
    print(f"{BLUE}Local file: {local_path}{NC}")

    print(f"\n{YELLOW}What happened:{NC}")
    print(f"  1. App Backend called Cloud Backend to generate MetaFlow")
    print(f"  2. Cloud Backend filtered relevant intents from Intent Graph")
    print(f"  3. Generated MetaFlow YAML and returned in response")
    print(f"  4. App Backend saved MetaFlow to local storage")

    print(f"\n{YELLOW}Next step:{NC}")
    print(f"  Generate Workflow from this MetaFlow:")
    print(f"  python tests/app_backend/manual/3_test_generate_workflow.py {metaflow_id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
