#!/usr/bin/env python3
"""
Test 0: Record User Operations in Browser

This test demonstrates browser recording using CDP.
"""
import sys
import requests
import json

# Colors
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'

APP_BACKEND_URL = "http://127.0.0.1:8765"


def print_section(title):
    print(f"\n{YELLOW}{'=' * 60}{NC}")
    print(f"{YELLOW}{title:^60}{NC}")
    print(f"{YELLOW}{'=' * 60}{NC}")


def start_recording():
    """Start CDP recording"""
    print_section("Step 1: Start Recording")

    request_data = {
        "url": "https://www.google.com",
        "title": "Google Coffee Search",
        "description": "Search for coffee on Google",
        "task_metadata": {
            "task_description": "Search for 'coffee' on Google and view results"
        }
    }

    print(f"{BLUE}→ Calling: POST {APP_BACKEND_URL}/api/recording/start{NC}")
    print(f"  Opening browser at: {request_data['url']}")
    print()

    try:
        response = requests.post(
            f"{APP_BACKEND_URL}/api/recording/start",
            json=request_data
        )

        print(f"{GREEN}← Status: {response.status_code}{NC}")

        if response.status_code == 200:
            result = response.json()
            session_id = result.get("session_id")

            print(f"{GREEN}✓ Recording started!{NC}")
            print(f"  Session ID: {session_id}")
            print(f"  URL: {result.get('url')}")

            return session_id
        else:
            print(f"{RED}✗ Failed to start recording{NC}")
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


def stop_recording():
    """Stop recording and save"""
    print_section("Step 2: Stop Recording")

    print(f"{BLUE}→ Calling: POST {APP_BACKEND_URL}/api/recording/stop{NC}")
    print()

    try:
        response = requests.post(f"{APP_BACKEND_URL}/api/recording/stop")

        print(f"{GREEN}← Status: {response.status_code}{NC}")

        if response.status_code == 200:
            result = response.json()

            print(f"{GREEN}✓ Recording stopped!{NC}")
            print(f"  Session ID: {result.get('session_id')}")
            print(f"  Operations: {result.get('operations_count')}")
            print(f"  Saved to: {result.get('local_file_path')}")

            return result.get("session_id")
        else:
            print(f"{RED}✗ Failed to stop recording{NC}")
            print(f"  Response: {response.text}")
            return None

    except Exception as e:
        print(f"{RED}✗ Error: {e}{NC}")
        return None


def main():
    print(f"{YELLOW}╔════════════════════════════════════════════════════════════╗{NC}")
    print(f"{YELLOW}║  Test 0: Record User Operations in Browser                ║{NC}")
    print(f"{YELLOW}╚════════════════════════════════════════════════════════════╝{NC}")

    # Start recording
    session_id = start_recording()
    if not session_id:
        return 1

    print(f"\n{YELLOW}Browser window is open. Please perform the following:{NC}")
    print(f"  1. Search for 'coffee' in Google search box")
    print(f"  2. Press Enter to search")
    print(f"  3. Click on a few search results")
    print(f"\n{YELLOW}Press ENTER when done...{NC}")
    input()

    # Stop recording
    session_id = stop_recording()
    if not session_id:
        return 1

    # Success
    print_section("Summary")
    print(f"{GREEN}✓ Recording completed successfully!{NC}")
    print(f"\n{BLUE}Session ID: {session_id}{NC}")

    print(f"\n{YELLOW}What happened:{NC}")
    print(f"  1. App Backend opened browser with CDP enabled")
    print(f"  2. User operations were recorded")
    print(f"  3. Operations saved to ~/.ami/users/default_user/recordings/{session_id}/")

    print(f"\n{YELLOW}Next step:{NC}")
    print(f"  Upload recording to Cloud Backend:")
    print(f"  python tests/app_backend/manual/1_test_upload.py {session_id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
