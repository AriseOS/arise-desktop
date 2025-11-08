#!/usr/bin/env python3
"""
Test 4: View Downloaded Workflows

This script shows workflows that have been downloaded to local directory.
Since workflows are automatically downloaded in test 3, this script just
helps you view and inspect the local files.
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


def print_section(title):
    print(f"\n{YELLOW}{'=' * 60}{NC}")
    print(f"{YELLOW}{title:^60}{NC}")
    print(f"{YELLOW}{'=' * 60}{NC}")


def get_latest_workflow_name():
    """Get the most recent workflow name from local downloads"""
    print_section("Step 1: Find Latest Workflow")

    if not DOWNLOAD_DIR.exists():
        print(f"{RED}✗ No downloads directory found{NC}")
        print(f"\n{YELLOW}Please run test 3 first:{NC}")
        print(f"  python tests/cloud_backend/manual/3_test_generate_workflow.py")
        return None

    # Find all workflow directories
    workflows = sorted(DOWNLOAD_DIR.glob("workflow_*"), reverse=True, key=lambda p: p.stat().st_mtime)

    if not workflows:
        print(f"{RED}✗ No workflow directories found{NC}")
        print(f"\n{YELLOW}Please run test 3 first:{NC}")
        print(f"  python tests/cloud_backend/manual/3_test_generate_workflow.py")
        return None

    latest_workflow = workflows[0]
    workflow_name = latest_workflow.name

    print(f"{GREEN}✓ Found Workflow in local downloads:{NC}")
    print(f"  Workflow Name: {workflow_name}")
    print(f"  Path: {latest_workflow}")

    return workflow_name


def view_workflow(workflow_name):
    """View workflow YAML from local directory"""
    print_section("Step 2: View Local Workflow")

    workflow_file = DOWNLOAD_DIR / workflow_name / "workflow.yaml"

    if not workflow_file.exists():
        print(f"{RED}✗ Workflow file not found: {workflow_file}{NC}")
        return None

    print(f"{BLUE}Local file: {workflow_file}{NC}")
    print()

    with open(workflow_file, 'r', encoding='utf-8') as f:
        workflow_yaml = f.read()

    print(f"{GREEN}✓ Workflow loaded from local file!{NC}")
    print(f"  Size: {len(workflow_yaml)} characters")

    return workflow_yaml


def display_workflow(workflow_yaml):
    """Display workflow content preview"""
    print_section("Step 3: Workflow Preview")

    lines = workflow_yaml.split('\n')[:20]

    print(f"{BLUE}First 20 lines:{NC}")
    for line in lines:
        print(f"  {line}")

    if len(workflow_yaml.split('\n')) > 20:
        print("  ...")
        print(f"\n{YELLOW}Total lines: {len(workflow_yaml.split(chr(10)))}{NC}")


def main():
    print(f"{YELLOW}╔════════════════════════════════════════════════════════════╗{NC}")
    print(f"{YELLOW}║  Test 4: View Downloaded Workflows                        ║{NC}")
    print(f"{YELLOW}╚════════════════════════════════════════════════════════════╝{NC}")

    # Get workflow_name from command line or find latest
    if len(sys.argv) > 1:
        workflow_name = sys.argv[1]
        print(f"\n{BLUE}Using provided Workflow Name: {workflow_name}{NC}")
    else:
        workflow_name = get_latest_workflow_name()
        if not workflow_name:
            return 1

    # View workflow
    workflow_yaml = view_workflow(workflow_name)
    if not workflow_yaml:
        return 1

    # Display preview
    display_workflow(workflow_yaml)

    # Success
    print_section("Summary")
    print(f"{GREEN}✓ Workflow viewed successfully!{NC}")
    print(f"\n{BLUE}Workflow Name: {workflow_name}{NC}")
    print(f"{BLUE}Local file: {DOWNLOAD_DIR / workflow_name / 'workflow.yaml'}{NC}")
    print(f"{BLUE}Size: {len(workflow_yaml)} characters{NC}")

    print(f"\n{YELLOW}What happened:{NC}")
    print(f"  1. Found workflow in local downloads directory")
    print(f"  2. Loaded workflow YAML from local file")
    print(f"  3. Displayed preview")

    print(f"\n{YELLOW}Note:{NC}")
    print(f"  Workflows are automatically downloaded in test 3.")
    print(f"  This script just helps you view the local files.")

    print(f"\n{YELLOW}Next step:{NC}")
    print(f"  List all workflows:")
    print(f"  python tests/cloud_backend/manual/5_test_list_workflows.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
