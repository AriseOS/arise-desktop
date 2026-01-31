#!/usr/bin/env python3
"""
Interactive Browser Test Script

This script allows you to test browser tools interactively,
simulating what the LLM can see and do.

Usage:
    cd /path/to/2ami
    python scripts/browser_interactive_test.py [--headless]

Commands:
    visit <url>           - Navigate to URL
    click <ref>           - Click element by ref (e.g., click e1)
    click_text <text>     - Click element by text
    select <ref> <value>  - Select option from dropdown (e.g., select e1 Best Sellers)
    type <ref> <text>     - Type text into element
    enter [ref]           - Press enter (optionally on element)
    scroll <up|down> [amount] - Scroll page
    snapshot              - Get page snapshot (what LLM sees)
    tabs                  - Show all tabs info
    switch <tab_id>       - Switch to tab
    new_tab [url]         - Open new tab
    close_tab <tab_id>    - Close tab
    links [ref1,ref2,...] - Get links info
    console               - View console logs
    exec <js_code>        - Execute JavaScript
    back                  - Go back
    forward               - Go forward
    help                  - Show this help
    quit/exit             - Exit

Debug commands:
    debug_session         - Show raw session info
    debug_click <ref>     - Show raw click result (bypassing toolkit)

The script shows exactly what the LLM receives after each action.
"""

import asyncio
import sys
import os
import argparse
import logging
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


class InteractiveBrowserTester:
    """Interactive browser testing interface."""

    # Available commands for auto-completion
    COMMANDS = [
        "visit", "click", "click_text", "select", "type", "enter", "scroll",
        "snapshot", "tabs", "switch", "new_tab", "close_tab", "links",
        "console", "exec", "back", "forward", "info", "help",
        "debug_session", "debug_click", "debug_snapshot",
        "raw_click", "raw_ctrl_click",
        "quit", "exit", "q"
    ]

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.session: HybridBrowserSession = None
        self.toolkit: BrowserToolkit = None

        # Setup prompt_toolkit with history and auto-completion
        history_file = Path.home() / ".browser_interactive_history"
        self.prompt_session = PromptSession(
            history=FileHistory(str(history_file)),
            auto_suggest=AutoSuggestFromHistory(),
            completer=WordCompleter(self.COMMANDS, ignore_case=True),
        )

    async def setup(self):
        """Initialize browser session and toolkit."""
        print("\n" + "="*60)
        print("Starting browser session...")
        print(f"  Headless: {self.headless}")
        print("="*60 + "\n")

        # Create browser session
        self.session = HybridBrowserSession(
            headless=self.headless,
            stealth=True,
        )

        # Ensure browser is started
        await self.session.ensure_browser()

        # Create toolkit with session
        self.toolkit = BrowserToolkit(session=self.session)

        print("Browser ready!")
        print("\nType 'help' for available commands.\n")

    async def cleanup(self):
        """Close browser session."""
        if self.session:
            print("\nClosing browser...")
            await self.session.close()
            print("Browser closed.")

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

            elif command == "click_text":
                if not args:
                    print("Usage: click_text <text>")
                else:
                    print(f"\n>>> Clicking text='{args}'")
                    result = await self.toolkit.browser_click(element_text=args)
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
                    result = await self.toolkit.browser_type(input_text=text, ref=ref)
                    self.print_result("LLM sees after type", result)

            elif command == "enter":
                ref = args if args else None
                print(f"\n>>> Pressing Enter" + (f" on ref={ref}" if ref else ""))
                result = await self.toolkit.browser_enter(ref=ref)
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
                refs = [r.strip() for r in args.split(",")] if args else []
                print(f"\n>>> Getting links info for refs: {refs if refs else 'all'}")
                result = await self.toolkit.browser_get_page_links(refs=refs)
                self.print_result("LLM sees (links)", result)

            elif command == "console":
                print("\n>>> Getting console logs")
                result = await self.toolkit.browser_console_view()
                self.print_result("LLM sees (console)", result)

            elif command == "exec":
                if not args:
                    print("Usage: exec <javascript_code>")
                else:
                    print(f"\n>>> Executing JS: {args[:50]}...")
                    result = await self.toolkit.browser_console_exec(code=args)
                    self.print_result("LLM sees after exec", result)

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
                result = await self.toolkit.browser_get_page_info()
                self.print_result("LLM sees (page info)", result)

            # Debug commands - show raw internal state
            elif command == "debug_session":
                print("\n>>> Debug: Session internal state")
                print(f"  Session object: {self.session}")
                print(f"  _pages dict: {list(self.session._pages.keys())}")
                print(f"  _current_tab_id: {self.session._current_tab_id}")
                print(f"  _page object: {self.session._page}")
                if self.session._page:
                    print(f"  _page.url: {self.session._page.url}")
                    print(f"  _page.is_closed(): {self.session._page.is_closed()}")
                tab_info = await self.session.get_tab_info()
                print(f"  get_tab_info(): {tab_info}")
                current = await self.session.get_current_tab_id()
                print(f"  get_current_tab_id(): {current}")

            elif command == "debug_click":
                if not args:
                    print("Usage: debug_click <ref>")
                else:
                    print(f"\n>>> Debug: Raw click on ref={args}")
                    print("  (This bypasses BrowserToolkit and calls session.exec_action directly)")

                    # Show state before click
                    print(f"\n  BEFORE click:")
                    print(f"    _current_tab_id: {self.session._current_tab_id}")
                    print(f"    _pages: {list(self.session._pages.keys())}")
                    print(f"    _page.url: {self.session._page.url if self.session._page else 'None'}")

                    # Execute click
                    action = {"type": "click", "ref": args}
                    result = await self.session.exec_action(action)

                    # Show raw result
                    print(f"\n  Raw exec_action result:")
                    print(f"    success: {result.get('success')}")
                    print(f"    message: {result.get('message')}")
                    details = result.get('details', {})
                    print(f"    details.click_method: {details.get('click_method')}")
                    print(f"    details.new_tab_created: {details.get('new_tab_created')}")
                    print(f"    details.new_tab_index: {details.get('new_tab_index')}")
                    print(f"    details.strategies_tried: {details.get('strategies_tried')}")

                    # Show state after click
                    print(f"\n  AFTER click:")
                    print(f"    _current_tab_id: {self.session._current_tab_id}")
                    print(f"    _pages: {list(self.session._pages.keys())}")
                    print(f"    _page.url: {self.session._page.url if self.session._page else 'None'}")

            elif command == "debug_snapshot":
                print("\n>>> Debug: Raw snapshot")
                snapshot = await self.session.get_snapshot(force_refresh=True)
                print(f"  Length: {len(snapshot)} chars")
                print(f"  First 500 chars:\n{snapshot[:500]}")

            elif command == "raw_click":
                # Direct Playwright click without Ctrl modifier
                if not args:
                    print("Usage: raw_click <ref>")
                else:
                    print(f"\n>>> Raw Playwright click on ref={args} (NO Ctrl modifier)")
                    page = self.session._page
                    selector = f"[aria-ref='{args}']"

                    # Get URL before
                    url_before = page.url
                    print(f"  URL before: {url_before}")

                    # Direct click without any modifiers
                    element = page.locator(selector).first
                    count = await element.count()
                    print(f"  Element found: {count > 0}")

                    if count > 0:
                        await element.click()  # Normal click, no modifiers, no force
                        url_after = page.url
                        print(f"  URL after: {url_after}")
                        print(f"  URL changed: {url_before != url_after}")

            elif command == "raw_ctrl_click":
                # Direct Playwright click WITH Ctrl modifier
                if not args:
                    print("Usage: raw_ctrl_click <ref>")
                else:
                    print(f"\n>>> Raw Playwright click on ref={args} (WITH Ctrl modifier)")
                    page = self.session._page
                    selector = f"[aria-ref='{args}']"

                    # Get URL before
                    url_before = page.url
                    print(f"  URL before: {url_before}")

                    # Direct click WITH Ctrl modifier
                    element = page.locator(selector).first
                    count = await element.count()
                    print(f"  Element found: {count > 0}")

                    if count > 0:
                        await element.click(modifiers=["ControlOrMeta"])
                        url_after = page.url
                        print(f"  URL after: {url_after}")
                        print(f"  URL changed: {url_before != url_after}")

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
        print("Interactive Browser Test")
        print("="*60)
        print("\nThis simulates what the LLM can see and do with the browser.")
        print("Every result shows exactly what would be returned to the LLM.\n")
        print("Features:")
        print("  - Arrow keys: navigate command history (up/down) and edit (left/right)")
        print("  - Tab: auto-complete commands")
        print("  - History is saved across sessions\n")
        print("Tips:")
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
    parser = argparse.ArgumentParser(description="Interactive Browser Test")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--no-debug", action="store_true", help="Disable debug logging")
    args = parser.parse_args()

    if args.no_debug:
        os.environ["AMI_DEBUG"] = ""
        logging.getLogger().setLevel(logging.INFO)

    tester = InteractiveBrowserTester(headless=args.headless)
    await tester.run()


if __name__ == "__main__":
    asyncio.run(main())
