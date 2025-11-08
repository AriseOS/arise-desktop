#!/usr/bin/env python3
"""
Python test client for HTTP daemon
"""
import requests
import time
import json

# Colors
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'

BASE_URL = "http://127.0.0.1:8765"


def print_section(title):
    print(f"\n{YELLOW}═══ {title} {'═' * (50 - len(title))}{NC}")


def print_request(method, url, data=None):
    print(f"{BLUE}→ {method} {url}{NC}")
    if data:
        print(f"  Body: {json.dumps(data, indent=2)}")


def print_response(response):
    try:
        data = response.json()
        print(f"{GREEN}← Status: {response.status_code}{NC}")
        print(f"  {json.dumps(data, indent=2)}")
        return data
    except:
        print(f"{RED}← Status: {response.status_code}{NC}")
        print(f"  {response.text}")
        return None


def main():
    print(f"{YELLOW}╔════════════════════════════════════════╗{NC}")
    print(f"{YELLOW}║  HTTP Daemon Test (Python)             ║{NC}")
    print(f"{YELLOW}╚════════════════════════════════════════╝{NC}")

    # Test 1: Health check
    print_section("Health Check")
    print_request("GET", f"{BASE_URL}/health")
    response = requests.get(f"{BASE_URL}/health")
    data = print_response(response)

    if data and data.get("browser_ready"):
        print(f"{GREEN}✓ Browser is ready{NC}")
    else:
        print(f"{YELLOW}⚠ Browser may not be ready{NC}")

    # Test 2: List workflows
    print_section("List Workflows")
    print_request("GET", f"{BASE_URL}/api/workflows")
    response = requests.get(f"{BASE_URL}/api/workflows", params={"user_id": "default_user"})
    data = print_response(response)

    if data:
        workflows = data.get("workflows", [])
        print(f"Found {len(workflows)} workflow(s)")

    # Test 3: Start recording
    print_section("Start Recording")
    request_data = {
        "url": "https://www.google.com",
        "title": "Test Recording",
        "description": "Testing HTTP API from Python",
        "task_metadata": {
            "user_intent": "I want to search for 'coffee machine' on Google and click the first result",
            "expected_outcome": "Navigate to first search result page",
            "notes": "This is a test recording"
        }
    }
    print_request("POST", f"{BASE_URL}/api/recording/start", request_data)
    response = requests.post(f"{BASE_URL}/api/recording/start", json=request_data)
    data = print_response(response)

    if data and "session_id" in data:
        session_id = data["session_id"]
        print(f"\n{GREEN}✓ Recording started{NC}")
        print(f"  Session ID: {session_id}")
        print(f"\n{YELLOW}Browser window should be open. Perform some actions...{NC}")
        print("Press ENTER when done...")
        input()

        # Test 4: Stop recording
        print_section("Stop Recording")
        print_request("POST", f"{BASE_URL}/api/recording/stop")
        response = requests.post(f"{BASE_URL}/api/recording/stop")
        data = print_response(response)

        if data:
            print(f"\n{GREEN}✓ Recording stopped{NC}")
            print(f"  Operations: {data.get('operations_count')}")
            print(f"  Saved to: {data.get('local_file_path')}")
    else:
        print(f"{RED}✗ Failed to start recording{NC}")

    # Test 5: List workflows again
    print_section("List Workflows (final)")
    print_request("GET", f"{BASE_URL}/api/workflows")
    response = requests.get(f"{BASE_URL}/api/workflows", params={"user_id": "default_user"})
    data = print_response(response)

    print(f"\n{GREEN}╔════════════════════════════════════════╗{NC}")
    print(f"{GREEN}║  Tests Complete                        ║{NC}")
    print(f"{GREEN}╚════════════════════════════════════════╝{NC}\n")


if __name__ == "__main__":
    try:
        main()
    except requests.ConnectionError:
        print(f"\n{RED}✗ Cannot connect to daemon at {BASE_URL}{NC}")
        print(f"Make sure the daemon is running:")
        print(f"  ./scripts/start_http_daemon.sh")
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted by user{NC}")
