#!/usr/bin/env python3
"""
Test 2: Generate MetaFlow from User's Intent Memory Graph

This script tests generating MetaFlow from user's accumulated Intent Graph.
The MetaFlowGenerator will filter relevant intents based on task_description.

The script will:
1. Request Cloud Backend to generate MetaFlow
2. Download the generated MetaFlow YAML via HTTP
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


def generate_and_save_metaflow(task_description):
    """Generate MetaFlow from user's Intent Graph and save to local"""
    print_section("Generate MetaFlow")

    print(f"{BLUE}User ID: {USER_ID}{NC}")
    print(f"{BLUE}Task: {task_description}{NC}")
    print()

    payload = {
        "task_description": task_description
    }

    print(f"{BLUE}→ Calling: POST {CLOUD_BACKEND_URL}/api/users/{USER_ID}/generate_metaflow{NC}")
    print(f"{YELLOW}  This will take 30-60 seconds (LLM processing)...{NC}")
    print()

    try:
        response = requests.post(
            f"{CLOUD_BACKEND_URL}/api/users/{USER_ID}/generate_metaflow",
            json=payload,
            timeout=180  # 3 minutes for LLM
        )

        print(f"{GREEN}← Status: {response.status_code}{NC}")

        if response.status_code == 200:
            result = response.json()
            metaflow_id = result.get("metaflow_id")
            metaflow_yaml = result.get("metaflow_yaml")
            task_desc = result.get("task_description", "")

            print(f"{GREEN}✓ MetaFlow generated!{NC}")
            print(f"  MetaFlow ID: {metaflow_id}")

            if metaflow_yaml:
                print(f"  Size: {len(metaflow_yaml)} characters")
            else:
                print(f"{RED}  ✗ Warning: metaflow_yaml is None!{NC}")
                print(f"{YELLOW}  Response keys: {list(result.keys())}{NC}")
                print(f"{YELLOW}  This might mean Cloud Backend needs to be restarted to load new code.{NC}")
                return None, None
            print()

            # Save to local directory
            metaflow_dir = DOWNLOAD_DIR / metaflow_id
            metaflow_dir.mkdir(exist_ok=True)

            yaml_file = metaflow_dir / "metaflow.yaml"
            with open(yaml_file, 'w', encoding='utf-8') as f:
                f.write(metaflow_yaml)

            if task_desc:
                task_file = metaflow_dir / "task_description.txt"
                with open(task_file, 'w', encoding='utf-8') as f:
                    f.write(task_desc)

            print(f"{GREEN}✓ Saved to local:{NC}")
            print(f"  {yaml_file}")

            return metaflow_id, str(yaml_file)
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
    print(f"{YELLOW}║  Test 2: Generate MetaFlow from Intent Graph              ║{NC}")
    print(f"{YELLOW}╚════════════════════════════════════════════════════════════╝{NC}")

    # Get task description from command line or use default
    if len(sys.argv) > 1:
        task_description = " ".join(sys.argv[1:])
    else:
        task_description = "Collect coffee product information from Allegro including product name, price, and sales count"
        print(f"\n{YELLOW}No task description provided, using default:{NC}")
        print(f"  \"{task_description}\"")
        print(f"\n{YELLOW}Usage:{NC}")
        print(f"  python {sys.argv[0]} \"Your task description here\"")

    # Generate MetaFlow and save to local
    metaflow_id, local_file = generate_and_save_metaflow(task_description)
    if not metaflow_id:
        return 1

    # Success
    print_section("Summary")
    print(f"{GREEN}✓ MetaFlow generated and saved successfully!{NC}")
    print(f"\n{BLUE}MetaFlow ID: {metaflow_id}{NC}")
    print(f"{BLUE}Local file: {local_file}{NC}")

    print(f"\n{YELLOW}What happened:{NC}")
    print(f"  1. Cloud Backend loaded user's Intent Memory Graph")
    print(f"  2. MetaFlowGenerator filtered relevant intents for: \"{task_description}\"")
    print(f"  3. Generated MetaFlow YAML and returned in response")
    print(f"  4. Saved MetaFlow to local directory")

    print(f"\n{YELLOW}Next step:{NC}")
    print(f"  Generate Workflow from this MetaFlow:")
    print(f"  python tests/cloud_backend/manual/3_test_generate_workflow.py {metaflow_id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
