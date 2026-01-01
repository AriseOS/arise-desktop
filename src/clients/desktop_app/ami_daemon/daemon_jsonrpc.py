#!/usr/bin/env python3
"""
App Backend Daemon Process
Runs as a persistent process, communicates via JSON-RPC over stdin/stdout
"""
import sys
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any

# Configure logging to stderr only (stdout is for JSON-RPC)
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)-8s [%(name)s] %(message)s',
    stream=sys.stderr
)

# Add project root to sys.path (go up two levels from daemon.py)
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.clients.desktop_app.ami_daemon.core.config_service import get_config
from src.clients.desktop_app.ami_daemon.services.storage_manager import StorageManager
from src.clients.desktop_app.ami_daemon.services.browser_manager import BrowserManager
from src.clients.desktop_app.ami_daemon.services.workflow_executor import WorkflowExecutor
from src.clients.desktop_app.ami_daemon.services.cdp_recorder import CDPRecorder
from src.clients.desktop_app.ami_daemon.services.cloud_client import CloudClient

# Load configuration
config = get_config()

# Global instances (initialized once, persistent across requests)
storage_manager = StorageManager(config.get("storage.base_path"))
browser_manager = None
workflow_executor = None
cdp_recorder = None
cloud_client = None

# Global event loop for async operations
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


async def initialize_services():
    """Initialize all services on daemon startup"""
    global browser_manager, workflow_executor, cdp_recorder, cloud_client

    # Initialize browser manager
    browser_manager = BrowserManager(config_service=config)

    # Initialize workflow executor
    workflow_executor = WorkflowExecutor(storage_manager, browser_manager)

    # Initialize CDP recorder
    cdp_recorder = CDPRecorder(storage_manager, browser_manager)

    # Initialize cloud client
    cloud_client = CloudClient(
        api_url=config.get("cloud.api_url", "https://api.ami.com")
    )

    sys.stderr.write("App Backend daemon initialized successfully\n")
    sys.stderr.flush()


def handle_request(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle JSON-RPC request

    Args:
        method: RPC method name
        params: Method parameters

    Returns:
        Result dictionary
    """
    try:
        # Recording methods
        if method == "start_recording":
            url = params.get("url", "")
            result = loop.run_until_complete(cdp_recorder.start_recording(url))

        elif method == "stop_recording":
            result = loop.run_until_complete(cdp_recorder.stop_recording())

        # Workflow execution methods
        elif method == "execute_workflow":
            workflow_name = params.get("workflow_name", "")
            user_id = params.get("user_id", "default_user")
            result = loop.run_until_complete(
                workflow_executor.execute_workflow_async(user_id, workflow_name)
            )

        elif method == "get_workflow_status":
            task_id = params.get("task_id", "")
            result = workflow_executor.get_task_status(task_id)
            if result is None:
                return {"error": f"Task not found: {task_id}"}

        elif method == "get_workflow_result":
            task_id = params.get("task_id", "")
            result = workflow_executor.get_task_status(task_id)
            if result is None:
                return {"error": f"Task not found: {task_id}"}

        elif method == "list_workflows":
            user_id = params.get("user_id", "default_user")
            workflows = storage_manager.list_workflows(user_id)
            result = {"workflows": workflows}

        else:
            return {"error": f"Unknown method: {method}"}

        return result

    except Exception as e:
        sys.stderr.write(f"Error handling {method}: {str(e)}\n")
        sys.stderr.flush()
        return {"error": str(e)}


def main():
    """Main daemon loop - read JSON-RPC requests from stdin"""
    sys.stderr.write("Starting App Backend daemon...\n")
    sys.stderr.flush()

    # Initialize services
    loop.run_until_complete(initialize_services())

    sys.stderr.write("App Backend daemon ready\n")
    sys.stderr.flush()

    # Main request loop
    for line in sys.stdin:
        try:
            # Parse JSON-RPC request
            request = json.loads(line.strip())
            request_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})

            # Handle request
            result = handle_request(method, params)

            # Build JSON-RPC response
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result
            }

            # Send response to stdout
            print(json.dumps(response), flush=True)

        except json.JSONDecodeError as e:
            # Invalid JSON
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {str(e)}"}
            }
            print(json.dumps(error_response), flush=True)

        except Exception as e:
            # Other errors
            error_response = {
                "jsonrpc": "2.0",
                "id": request.get("id") if "request" in locals() else None,
                "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
            }
            print(json.dumps(error_response), flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.stderr.write("\nDaemon interrupted\n")
        sys.stderr.flush()
    finally:
        # Cleanup
        if browser_manager:
            loop.run_until_complete(browser_manager.cleanup())
        sys.stderr.write("Daemon shutdown complete\n")
        sys.stderr.flush()
