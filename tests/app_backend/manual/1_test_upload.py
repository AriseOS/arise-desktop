#!/usr/bin/env python3
"""
Test 1: Upload Recording to Cloud Backend

This test uploads a local recording to Cloud Backend for intent extraction.
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


def get_latest_session_id():
    """Get the most recent session_id from local storage"""
    print_section("Step 1: Find Latest Recording")

    recordings_path = STORAGE_PATH / "recordings"

    if not recordings_path.exists():
        print(f"{RED}✗ No recordings found at {recordings_path}{NC}")
        print(f"\n{YELLOW}Please run test 0 first:{NC}")
        print(f"  python tests/app_backend/manual/0_test_recording.py")
        return None

    # Find all recording directories
    recordings = sorted(recordings_path.glob("session_*"), reverse=True, key=lambda p: p.stat().st_mtime)

    if not recordings:
        print(f"{RED}✗ No recording directories found{NC}")
        return None

    latest_recording = recordings[0]
    session_id = latest_recording.name

    # Load operations to get count
    ops_file = latest_recording / "operations.json"
    if ops_file.exists():
        with open(ops_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            ops_count = len(data.get("operations", []))
    else:
        ops_count = 0

    print(f"{GREEN}✓ Found Recording:{NC}")
    print(f"  Session ID: {session_id}")
    print(f"  Operations: {ops_count}")
    print(f"  Path: {latest_recording}")

    return session_id


def upload_recording(session_id, task_description):
    """Upload recording to Cloud Backend"""
    print_section("Step 2: Upload to Cloud Backend")

    print(f"{BLUE}Session ID: {session_id}{NC}")
    print(f"{BLUE}Task: {task_description}{NC}")
    print()

    request_data = {
        "session_id": session_id,
        "task_description": task_description,
        "user_id": "default_user"
    }

    print(f"{BLUE}→ Calling: POST {APP_BACKEND_URL}/api/recordings/upload{NC}")
    print()

    try:
        response = requests.post(
            f"{APP_BACKEND_URL}/api/recordings/upload",
            json=request_data
        )

        print(f"{GREEN}← Status: {response.status_code}{NC}")

        if response.status_code == 200:
            result = response.json()
            recording_id = result.get("recording_id")

            print(f"{GREEN}✓ Recording uploaded!{NC}")
            print(f"  Recording ID: {recording_id}")
            print()
            print(f"{YELLOW}Background task started on Cloud Backend:{NC}")
            print(f"  - Extracting intents from operations")
            print(f"  - Adding intents to user's Intent Memory Graph")

            return recording_id
        else:
            print(f"{RED}✗ Upload failed{NC}")
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


def main():
    print(f"{YELLOW}╔════════════════════════════════════════════════════════════╗{NC}")
    print(f"{YELLOW}║  Test 1: Upload Recording to Cloud Backend                ║{NC}")
    print(f"{YELLOW}╚════════════════════════════════════════════════════════════╝{NC}")

    # Get session_id from command line or find latest
    if len(sys.argv) > 1:
        session_id = sys.argv[1]
        print(f"\n{BLUE}Using provided Session ID: {session_id}{NC}")

        # Get task description from command line
        if len(sys.argv) > 2:
            task_description = " ".join(sys.argv[2:])
        else:
            task_description = "Search for coffee on Google"
            print(f"{YELLOW}No task description provided, using default:{NC}")
            print(f"  \"{task_description}\"")
    else:
        session_id = get_latest_session_id()
        if not session_id:
            return 1

        task_description = "Search for coffee on Google"
        print(f"\n{YELLOW}Using default task description:{NC}")
        print(f"  \"{task_description}\"")

    print(f"\n{YELLOW}Usage:{NC}")
    print(f"  python {sys.argv[0]} <session_id> \"Your task description here\"")
    print()

    # Upload recording
    recording_id = upload_recording(session_id, task_description)
    if not recording_id:
        return 1

    # Success
    print_section("Summary")
    print(f"{GREEN}✓ Recording uploaded successfully!{NC}")
    print(f"\n{BLUE}Recording ID: {recording_id}{NC}")

    print(f"\n{YELLOW}What happened:{NC}")
    print(f"  1. App Backend loaded operations from local storage")
    print(f"  2. Uploaded to Cloud Backend with task description")
    print(f"  3. Cloud Backend started intent extraction (async)")

    print(f"\n{YELLOW}Next step:{NC}")
    print(f"  Wait a few seconds for intent extraction, then generate MetaFlow:")
    print(f"  python tests/app_backend/manual/2_test_generate_metaflow.py \"{task_description}\"")

    return 0


if __name__ == "__main__":
    sys.exit(main())
