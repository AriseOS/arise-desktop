#!/usr/bin/env python3
"""
Test 1: Upload Recording to Cloud Backend

This script tests uploading user operations to Cloud Backend.
Backend will:
1. Save recording to filesystem
2. Extract intents in background (async)
3. Add intents to user's Intent Memory Graph

Note: Intent extraction happens asynchronously, so the API returns immediately.
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

CLOUD_BACKEND_URL = "http://localhost:9000"
USER_ID = "default_user"

# Load real operations from coffee_allegro fixture
FIXTURE_PATH = Path(__file__).parent.parent.parent / "fixtures" / "test_data" / "coffee_allegro" / "fixtures" / "user_operations.json"

def load_operations():
    """Load operations from fixture file"""
    if not FIXTURE_PATH.exists():
        print(f"{RED}✗ Fixture file not found: {FIXTURE_PATH}{NC}")
        return None, None

    with open(FIXTURE_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    task_metadata = data.get("task_metadata", {})
    task_description = task_metadata.get("task_description", "")
    operations = data.get("operations", [])

    return task_description, operations


def print_section(title):
    print(f"\n{YELLOW}{'=' * 60}{NC}")
    print(f"{YELLOW}{title:^60}{NC}")
    print(f"{YELLOW}{'=' * 60}{NC}")


def upload_recording():
    """Upload recording to Cloud Backend"""
    print_section("Test 1: Upload Recording")

    # Load operations from fixture
    task_description, operations = load_operations()
    if operations is None:
        return None

    print(f"{GREEN}✓ Loaded fixture data{NC}")
    print(f"  Source: {FIXTURE_PATH.name}")
    print(f"  Operations: {len(operations)}")
    print(f"  Task: {task_description}")
    print()

    payload = {
        "user_id": USER_ID,
        "task_description": task_description,
        "operations": operations
    }

    print(f"{BLUE}→ Uploading to {CLOUD_BACKEND_URL}{NC}")
    print()

    try:
        response = requests.post(
            f"{CLOUD_BACKEND_URL}/api/recordings/upload",
            json=payload,
            timeout=30
        )

        print(f"{GREEN}← Status: {response.status_code}{NC}")

        if response.status_code == 200:
            result = response.json()
            recording_id = result.get("recording_id")

            print(f"{GREEN}✓ Recording uploaded!{NC}")
            print(f"  Recording ID: {recording_id}")
            print()
            print(f"{YELLOW}Background task started:{NC}")
            print(f"  - Extracting intents from operations")
            print(f"  - Adding intents to user's Intent Memory Graph")
            print(f"  - Graph location: ~/.ami/users/{USER_ID}/intent_graph.json")

            return recording_id
        else:
            print(f"{RED}✗ Upload failed{NC}")
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
    print(f"{YELLOW}║  Test 1: Upload Recording to Cloud Backend                ║{NC}")
    print(f"{YELLOW}╚════════════════════════════════════════════════════════════╝{NC}")

    recording_id = upload_recording()
    if not recording_id:
        return 1

    # Success
    print_section("Summary")
    print(f"{GREEN}✓ Recording uploaded successfully!{NC}")
    print(f"\n{BLUE}Recording ID: {recording_id}{NC}")

    print(f"\n{YELLOW}What happens next (in background):{NC}")
    print(f"  1. Cloud Backend extracts intents from operations (LLM)")
    print(f"     - Uses your task_description to generate better intents")
    print(f"  2. Intents are added to user's Intent Memory Graph")
    print(f"  3. Graph is saved to ~/.ami/users/{USER_ID}/intent_graph.json")
    print(f"  4. Each new recording adds more intents to the same graph")

    print(f"\n{YELLOW}Next step:{NC}")
    print(f"  Wait a few seconds, then generate MetaFlow:")
    print(f"  python tests/cloud_backend/manual/2_test_generate_metaflow.py \"Collect coffee products from Allegro\"")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
