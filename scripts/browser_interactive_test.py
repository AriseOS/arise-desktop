#!/usr/bin/env python3
"""
Interactive Browser Test Script (V4 - Electron CDP)

This script connects to the running Electron app's built-in Chromium via CDP,
then lets you interactively test browser tools (what the LLM can see and do).

Prerequisites:
    - The Electron desktop app must be running (it provides the browser via CDP)

Usage:
    cd /path/to/2ami
    source .venv/bin/activate
    python scripts/browser_interactive_test.py [--cdp-port <port>] [--session-id <id>]

Options:
    --cdp-port <port>       CDP port to connect to (default: auto-detect from 9222+)
    --session-id <id>       Session ID for the toolkit (default: "test-interactive")

Commands:
    visit <url>           - Navigate to URL
    click <ref>           - Click element by ref (e.g., click e1)
    select <ref> <value>  - Select option from dropdown (e.g., select e1 Best Sellers)
    type <ref> <text>     - Type text into element
    enter                 - Press enter
    scroll <up|down> [amount] - Scroll page
    snapshot              - Get page snapshot (what LLM sees)
    tabs                  - Show all tabs info
    switch <tab_id>       - Switch to tab
    new_tab [url]         - Open new tab
    close_tab <tab_id>    - Close tab
    links                 - Get page snapshot with all links
    exec <js_code>        - Execute JavaScript
    back                  - Go back
    forward               - Go forward
    info                  - Get page info (URL, title, viewport)
    status                - Show browser session status
    help                  - Show this help
    quit/exit             - Exit

The script shows exactly what the LLM receives after each action.
"""

import asyncio
import sys
import os
import argparse
import logging
import subprocess
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Enable debug mode by default for interactive testing
os.environ["AMI_DEBUG"] = "1"

# Configure logging to show debug messages
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)

from src.clients.desktop_app.ami_daemon.base_agent.tools.eigent_browser.browser_session import HybridBrowserSession
from src.clients.desktop_app.ami_daemon.base_agent.tools.toolkits.browser_toolkit import BrowserToolkit


def detect_cdp_port(start_port: int = 9222, max_scan: int = 20) -> int | None:
    """Auto-detect CDP port by scanning for a listening Electron process.

    Electron is started with --remote-debugging-port=<port>.
    We scan ports 9222..9242 and check if there's a CDP endpoint.
    """
    import urllib.request
    import json

    for port in range(start_port, start_port + max_scan):
        try:
            # CDP exposes /json/version on the debug port
            url = f"http://127.0.0.1:{port}/json/version"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                data = json.loads(resp.read())
                browser = data.get("Browser", "")
                # Electron's Chromium will show something like "Chrome/xxx"
                if browser:
                    print(f"  Found CDP endpoint at port {port}: {browser}")
                    return port
        except Exception:
            continue
    return None


class InteractiveBrowserTester:
    """Interactive browser testing interface."""

    COMMANDS = [
        "visit", "click", "select", "type", "enter", "scroll",
        "snapshot", "tabs", "switch", "new_tab", "close_tab", "links",
        "exec", "back", "forward", "info", "status", "help",
        "debug_session", "debug_click", "debug_snapshot",
        "quit", "exit", "q"
    ]

    def __init__(self, cdp_port: int, session_id: str = "test-interactive"):
        self.cdp_port = cdp_port
        self.session_id = session_id
        self.session: HybridBrowserSession = None
        self.toolkit: BrowserToolkit = None

        history_file = Path.home() / ".browser_interactive_history"
        self.prompt_session = PromptSession(
            history=FileHistory(str(history_file)),
            auto_suggest=AutoSuggestFromHistory(),
            completer=WordCompleter(self.COMMANDS, ignore_case=True),
        )

    async def setup(self):
        """Connect to Electron's browser via CDP and initialize toolkit."""
        print("\n" + "="*60)
        print("Connecting to Electron browser via CDP...")
        print(f"  CDP port: {self.cdp_port}")
        print(f"  Session ID: {self.session_id}")
        print("="*60 + "\n")

        # Set the env var that HybridBrowserSession expects
        os.environ["BROWSER_CDP_PORT"] = str(self.cdp_port)

        print("Starting daemon session (connecting to Electron CDP)...")
        self.session = await HybridBrowserSession.start_daemon_session()
        print("  Connected to Electron browser")

        # Create toolkit with specified session_id
        self.toolkit = BrowserToolkit(session_id=self.session_id)

        print(f"  Toolkit session: '{self.session_id}'")
        print("Browser ready!")
        print("\nType 'help' for available commands.\n")

    async def cleanup(self):
        """Disconnect from browser (does NOT close Electron)."""
        print("\nDisconnecting from Electron browser...")
        await HybridBrowserSession.stop_daemon_session()
        print("Disconnected.")

    def print_result(self, title: str, result: str):
        """Print result in a formatted box."""
        print("\n" + "="*60)
        print(f"[{title}]")
        print("="*60)
        print(result)
        print("="*60 + "\n")

    async def run_command(self, cmd: str) -> bool:
        """Run a single command. Returns False to exit."""
        cmd = cmd.strip()
        if not cmd:
            return True

        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        try:
            if command in ["quit", "exit", "q"]:
                return False

            elif command == "help":
                print(__doc__)

            elif command == "visit":
                if not args:
                    print("Usage: visit <url>")
                else:
                    url = args if args.startswith("http") else f"https://{args}"
                    print(f"\n>>> Visiting: {url}")
                    result = await self.toolkit.browser_visit_page(url)
                    self.print_result("LLM sees after visit", result)

            elif command == "click":
                if not args:
                    print("Usage: click <ref>  (e.g., click e1)")
                else:
                    print(f"\n>>> Clicking ref={args}")
                    result = await self.toolkit.browser_click(ref=args)
                    self.print_result("LLM sees after click", result)

            elif command == "select":
                select_parts = args.split(maxsplit=1)
                if len(select_parts) < 2:
                    print("Usage: select <ref> <value>  (e.g., select e1 Best Sellers)")
                else:
                    ref, value = select_parts
                    print(f"\n>>> Selecting '{value}' in ref={ref}")
                    result = await self.toolkit.browser_select(value=value, ref=ref)
                    self.print_result("LLM sees after select", result)

            elif command == "type":
                type_parts = args.split(maxsplit=1)
                if len(type_parts) < 2:
                    print("Usage: type <ref> <text>  (e.g., type e1 hello world)")
                else:
                    ref, text = type_parts
                    print(f"\n>>> Typing '{text}' into ref={ref}")
                    result = await self.toolkit.browser_type(ref=ref, text=text)
                    self.print_result("LLM sees after type", result)

            elif command == "enter":
                print(f"\n>>> Pressing Enter")
                result = await self.toolkit.browser_enter()
                self.print_result("LLM sees after enter", result)

            elif command == "scroll":
                scroll_parts = args.split()
                direction = scroll_parts[0] if scroll_parts else "down"
                amount = int(scroll_parts[1]) if len(scroll_parts) > 1 else 300
                print(f"\n>>> Scrolling {direction} by {amount}px")
                result = await self.toolkit.browser_scroll(direction=direction, amount=amount)
                self.print_result("LLM sees after scroll", result)

            elif command == "snapshot":
                print("\n>>> Getting page snapshot")
                result = await self.toolkit.browser_get_page_snapshot()
                self.print_result("LLM sees (page snapshot)", result)

            elif command == "tabs":
                print("\n>>> Getting tab info")
                result = await self.toolkit.browser_get_tab_info()
                self.print_result("LLM sees (tabs)", result)

            elif command == "switch":
                if not args:
                    print("Usage: switch <tab_id>  (e.g., switch tab_1)")
                else:
                    print(f"\n>>> Switching to tab {args}")
                    result = await self.toolkit.browser_switch_tab(tab_id=args)
                    self.print_result("LLM sees after switch_tab", result)

            elif command == "new_tab":
                url = args if args else None
                print(f"\n>>> Opening new tab" + (f" with URL: {url}" if url else ""))
                result = await self.toolkit.browser_new_tab(url=url)
                self.print_result("LLM sees after new_tab", result)

            elif command == "close_tab":
                if not args:
                    print("Usage: close_tab <tab_id>")
                else:
                    print(f"\n>>> Closing tab {args}")
                    result = await self.toolkit.browser_close_tab(tab_id=args)
                    self.print_result("LLM sees after close_tab", result)

            elif command == "links":
                print("\n>>> Getting page snapshot with links")
                result = await self.toolkit.browser_get_page_snapshot(include_links=True)
                self.print_result("LLM sees (links)", result)

            elif command == "exec":
                if not args:
                    print("Usage: exec <javascript_code>")
                else:
                    print(f"\n>>> Executing JS: {args[:50]}...")
                    try:
                        session = await self.toolkit._get_session()
                        page = await session.get_page()
                        result = await page.evaluate(args)
                        self.print_result("JS execution result", str(result))
                    except Exception as e:
                        print(f"  Error: {e}")

            elif command == "back":
                print("\n>>> Going back")
                result = await self.toolkit.browser_back()
                self.print_result("LLM sees after back", result)

            elif command == "forward":
                print("\n>>> Going forward")
                result = await self.toolkit.browser_forward()
                self.print_result("LLM sees after forward", result)

            elif command == "info":
                print("\n>>> Getting page info")
                try:
                    session = await self.toolkit._get_session()
                    page = await session.get_page()
                    url = page.url
                    title = await page.title()
                    viewport = page.viewport_size
                    result = f"URL: {url}\nTitle: {title}\nViewport: {viewport}"
                    self.print_result("Page info", result)
                except Exception as e:
                    print(f"  Error: {e}")

            elif command == "status":
                print("\n>>> Browser session status")
                daemon = HybridBrowserSession.get_daemon_session()
                print(f"  Daemon session: {'Active' if daemon else 'Not running'}")
                print(f"  CDP port: {self.cdp_port}")
                if daemon:
                    browser_connected = daemon._browser and daemon._browser.is_connected()
                    print(f"  Browser connected: {browser_connected}")
                    print(f"  Tab Groups: {len(daemon._tab_groups)}")
                    print(f"  Pages: {len(daemon._pages)}")

            # =========================================================
            # Debug commands
            # =========================================================
            elif command == "debug_session":
                print("\n>>> Debug: Session internal state")
                session = await self.toolkit._get_session()
                print(f"  Session object: {session}")
                print(f"  Session ID: {session._session_id}")
                print(f"  _pages dict: {list(session._pages.keys())}")
                print(f"  _current_tab_id: {session._current_tab_id}")
                print(f"  _page object: {session._page}")
                if session._page:
                    print(f"  _page.url: {session._page.url}")
                    print(f"  _page.is_closed(): {session._page.is_closed()}")
                tab_info = await session.get_tab_info()
                print(f"  get_tab_info(): {tab_info}")

            elif command == "debug_click":
                if not args:
                    print("Usage: debug_click <ref>")
                else:
                    print(f"\n>>> Debug: Raw click on ref={args}")
                    session = await self.toolkit._get_session()
                    print(f"\n  BEFORE click:")
                    print(f"    _current_tab_id: {session._current_tab_id}")
                    print(f"    _pages: {list(session._pages.keys())}")
                    print(f"    _page.url: {session._page.url if session._page else 'None'}")

                    action = {"type": "click", "ref": args}
                    result = await session.exec_action(action)

                    print(f"\n  Raw exec_action result:")
                    print(f"    success: {result.get('success')}")
                    print(f"    message: {result.get('message')}")
                    details = result.get('details', {})
                    print(f"    details.click_method: {details.get('click_method')}")
                    print(f"    details.new_tab_created: {details.get('new_tab_created')}")

                    print(f"\n  AFTER click:")
                    print(f"    _current_tab_id: {session._current_tab_id}")
                    print(f"    _pages: {list(session._pages.keys())}")
                    print(f"    _page.url: {session._page.url if session._page else 'None'}")

            elif command == "debug_snapshot":
                print("\n>>> Debug: Raw snapshot")
                session = await self.toolkit._get_session()
                snapshot = await session.get_snapshot(force_refresh=True)
                print(f"  Length: {len(snapshot)} chars")
                print(f"  First 500 chars:\n{snapshot[:500]}")

            else:
                print(f"Unknown command: {command}")
                print("Type 'help' for available commands.")

        except Exception as e:
            print(f"\nError: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

        return True

    async def run(self):
        """Main interactive loop."""
        await self.setup()

        print("="*60)
        print("Interactive Browser Test (V4 - Electron CDP)")
        print("="*60)
        print("\nThis simulates what the LLM can see and do with the browser.")
        print("Every result shows exactly what would be returned to the LLM.\n")
        print("Features:")
        print("  - Arrow keys: navigate command history (up/down)")
        print("  - Tab: auto-complete commands")
        print("  - History is saved across sessions\n")
        print("Tips:")
        print("  - Use 'status' to see browser session status")
        print("  - Use 'debug_click <ref>' to see raw click results")
        print("  - Use 'debug_session' to see internal tab state")
        print("  - Use 'tabs' to see what LLM knows about tabs\n")

        try:
            while True:
                try:
                    cmd = await self.prompt_session.prompt_async("browser> ")
                    cmd = cmd.strip()
                    if not await self.run_command(cmd):
                        break
                except EOFError:
                    break
                except KeyboardInterrupt:
                    print("\n(Use 'quit' to exit)")
        finally:
            await self.cleanup()


async def main():
    parser = argparse.ArgumentParser(description="Interactive Browser Test (V4 - Electron CDP)")
    parser.add_argument("--cdp-port", "-p", type=int, default=None,
                        help="CDP port to connect to (default: auto-detect)")
    parser.add_argument("--no-debug", action="store_true", help="Disable debug logging")
    parser.add_argument("--session-id", "-s", default="test-interactive",
                        help="Session ID for the toolkit (default: test-interactive)")
    args = parser.parse_args()

    if args.no_debug:
        os.environ["AMI_DEBUG"] = ""
        logging.getLogger().setLevel(logging.INFO)

    # Determine CDP port
    cdp_port = args.cdp_port
    if cdp_port is None:
        print("Auto-detecting CDP port...")
        cdp_port = detect_cdp_port()
        if cdp_port is None:
            print("\nERROR: Could not find a running Electron app with CDP enabled.")
            print("Make sure the desktop app is running first:")
            print("  cd src/clients/desktop_app && npm start")
            print("\nOr specify the port manually:")
            print("  python scripts/browser_interactive_test.py --cdp-port 9222")
            sys.exit(1)
    else:
        print(f"Using specified CDP port: {cdp_port}")

    tester = InteractiveBrowserTester(cdp_port=cdp_port, session_id=args.session_id)
    await tester.run()


if __name__ == "__main__":
    asyncio.run(main())
