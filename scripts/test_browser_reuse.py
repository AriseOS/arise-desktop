#!/usr/bin/env python3
"""
Browser Reuse Verification Script

This script tests various browser reuse scenarios to verify the V3 implementation:

1. Daemon mode reuse - Multiple sessions share daemon's browser
2. Non-daemon mode reuse - Primary session sharing
3. BrowserLauncher reuse - Reusing existing Chrome process
4. Lock file persistence - Browser survives daemon restart

Usage:
    cd /path/to/2ami
    source .venv/bin/activate
    python scripts/test_browser_reuse.py [scenario]

Scenarios:
    all              - Run all tests (default)
    daemon           - Test daemon session reuse
    non_daemon       - Test non-daemon primary session reuse
    launcher         - Test BrowserLauncher existing Chrome reuse
    lock_file        - Test lock file persistence across restarts
"""

import asyncio
import sys
import os
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

from src.clients.desktop_app.ami_daemon.base_agent.tools.eigent_browser.browser_session import HybridBrowserSession
from src.clients.desktop_app.ami_daemon.base_agent.tools.toolkits.browser_toolkit import BrowserToolkit


def print_header(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_result(success: bool, message: str):
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"  {status}: {message}")


def print_info(message: str):
    print(f"  ℹ️  {message}")


async def test_daemon_reuse():
    """Test Scenario 1: Multiple sessions share daemon's browser"""
    print_header("Scenario 1: Daemon Session Reuse")

    user_data_dir = str(Path.home() / ".ami" / "test-browser-profile")

    try:
        # Start daemon session
        print_info("Starting daemon session...")
        daemon = await HybridBrowserSession.start_daemon_session(
            config={
                "browser": {
                    "headless": True,
                    "user_data_dir": user_data_dir,
                }
            }
        )

        daemon_browser_id = id(daemon._browser)
        daemon_context_id = id(daemon._context)
        print_info(f"Daemon browser ID: {daemon_browser_id}")
        print_info(f"Daemon context ID: {daemon_context_id}")

        # Create first task session
        print_info("Creating task session 1...")
        session1 = HybridBrowserSession(
            session_id="task-001",
            headless=True,
        )
        await session1.ensure_browser()

        session1_browser_id = id(session1._browser)
        session1_context_id = id(session1._context)
        print_info(f"Session 1 browser ID: {session1_browser_id}")
        print_info(f"Session 1 context ID: {session1_context_id}")

        # Verify browser reuse
        browser_reused = daemon_browser_id == session1_browser_id
        context_reused = daemon_context_id == session1_context_id
        print_result(browser_reused, f"Browser object reused: {browser_reused}")
        print_result(context_reused, f"Context object reused: {context_reused}")

        # Create second task session
        print_info("Creating task session 2...")
        session2 = HybridBrowserSession(
            session_id="task-002",
            headless=True,
        )
        await session2.ensure_browser()

        session2_browser_id = id(session2._browser)
        print_info(f"Session 2 browser ID: {session2_browser_id}")

        # Verify second session also reuses
        browser_reused_2 = daemon_browser_id == session2_browser_id
        print_result(browser_reused_2, f"Session 2 also reuses daemon browser: {browser_reused_2}")

        # Verify each session has its own page
        session1_pages = len(session1._pages)
        session2_pages = len(session2._pages)
        print_result(session1_pages > 0, f"Session 1 has pages: {session1_pages}")
        print_result(session2_pages > 0, f"Session 2 has pages: {session2_pages}")

        # Cleanup
        await HybridBrowserSession.stop_daemon_session(force=True)
        print_info("Daemon session stopped")

        return browser_reused and context_reused and browser_reused_2

    except Exception as e:
        print_result(False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_non_daemon_reuse():
    """Test Scenario 2: Primary session sharing (non-daemon mode)"""
    print_header("Scenario 2: Non-Daemon Primary Session Reuse")

    # Ensure no daemon session
    if HybridBrowserSession._daemon_session:
        await HybridBrowserSession.stop_daemon_session(force=True)

    # Clear primary session
    HybridBrowserSession._primary_session = None
    # Clear instance registry
    HybridBrowserSession._instances.clear()

    user_data_dir = str(Path.home() / ".ami" / "test-browser-profile-2")

    try:
        # Create first session (should become primary)
        print_info("Creating first session (should become primary)...")
        session1 = HybridBrowserSession(
            session_id="standalone-001",
            headless=True,
            user_data_dir=user_data_dir,
        )
        await session1.ensure_browser()

        is_primary = HybridBrowserSession._primary_session is session1
        print_result(is_primary, f"Session 1 registered as primary: {is_primary}")

        session1_browser_id = id(session1._browser)
        print_info(f"Session 1 browser ID: {session1_browser_id}")

        # Create second session (should reuse primary's browser)
        print_info("Creating second session (should reuse primary's browser)...")
        session2 = HybridBrowserSession(
            session_id="standalone-002",
            headless=True,
            user_data_dir=user_data_dir,
        )
        await session2.ensure_browser()

        session2_browser_id = id(session2._browser)
        print_info(f"Session 2 browser ID: {session2_browser_id}")

        browser_reused = session1_browser_id == session2_browser_id
        print_result(browser_reused, f"Browser reused by session 2: {browser_reused}")

        # Verify both have their own pages
        session1_pages = len(session1._pages)
        session2_pages = len(session2._pages)
        print_result(session1_pages > 0, f"Session 1 has pages: {session1_pages}")
        print_result(session2_pages > 0, f"Session 2 has pages: {session2_pages}")

        # Test that pages are different
        session1_page_ids = set(id(p) for p in session1._pages.values())
        session2_page_ids = set(id(p) for p in session2._pages.values())
        pages_different = session1_page_ids.isdisjoint(session2_page_ids)
        print_result(pages_different, f"Each session has its own pages: {pages_different}")

        # Cleanup
        await session1.close()
        await session2.close()
        print_info("Sessions closed")

        return is_primary and browser_reused and pages_different

    except Exception as e:
        print_result(False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_browser_launcher_reuse():
    """Test Scenario 3: BrowserLauncher reusing existing Chrome"""
    print_header("Scenario 3: BrowserLauncher Existing Chrome Reuse")

    from src.clients.desktop_app.ami_daemon.base_agent.tools.eigent_browser.browser_launcher import BrowserLauncher

    user_data_dir = str(Path.home() / ".ami" / "test-browser-profile-3")

    try:
        # Launch first browser
        print_info("Launching first browser...")
        launcher1 = BrowserLauncher(
            headless=True,
            user_data_dir=user_data_dir,
        )
        cdp_url1 = await launcher1.launch()
        print_info(f"First browser CDP URL: {cdp_url1}")
        print_info(f"First browser PID: {launcher1.browser_pid}")
        print_info(f"First browser reused existing: {launcher1._reused_existing}")

        first_pid = launcher1.browser_pid
        first_reused = launcher1._reused_existing

        # Create second launcher with same user_data_dir
        # This should detect and reuse the existing Chrome
        print_info("Creating second launcher (should reuse existing Chrome)...")
        launcher2 = BrowserLauncher(
            headless=True,
            user_data_dir=user_data_dir,
        )
        cdp_url2 = await launcher2.launch()
        print_info(f"Second browser CDP URL: {cdp_url2}")
        print_info(f"Second browser PID: {launcher2.browser_pid}")
        print_info(f"Second browser reused existing: {launcher2._reused_existing}")

        second_pid = launcher2.browser_pid
        second_reused = launcher2._reused_existing

        # Verify reuse
        print_result(second_reused, f"Second launcher detected existing Chrome: {second_reused}")

        same_pid = first_pid == second_pid
        print_result(same_pid, f"Same PID used: {first_pid} == {second_pid}")

        same_url = cdp_url1 == cdp_url2
        print_result(same_url, f"Same CDP URL: {same_url}")

        # Cleanup - close the browser
        await launcher1.close()
        print_info("Browser closed")

        return second_reused and same_pid

    except Exception as e:
        print_result(False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_lock_file_persistence():
    """Test Scenario 4: Lock file persistence across daemon restart"""
    print_header("Scenario 4: Lock File Persistence")

    user_data_dir = str(Path.home() / ".ami" / "test-browser-profile-4")
    lock_file = Path.home() / ".ami" / "browser.lock"

    # Ensure clean state
    if HybridBrowserSession._daemon_session:
        await HybridBrowserSession.stop_daemon_session(force=True)
    if lock_file.exists():
        lock_file.unlink()

    try:
        # Start daemon session
        print_info("Starting daemon session (first time)...")
        daemon1 = await HybridBrowserSession.start_daemon_session(
            config={
                "browser": {
                    "headless": True,
                    "user_data_dir": user_data_dir,
                    "close_on_daemon_exit": False,  # Keep browser running
                }
            }
        )

        first_pid = HybridBrowserSession._browser_pid
        first_cdp_url = HybridBrowserSession._cdp_url
        print_info(f"First daemon PID: {first_pid}")
        print_info(f"First daemon CDP URL: {first_cdp_url}")

        # Check lock file exists
        lock_exists = lock_file.exists()
        print_result(lock_exists, f"Lock file created: {lock_exists}")

        if lock_exists:
            import json
            lock_data = json.loads(lock_file.read_text())
            print_info(f"Lock file content: {lock_data}")

        # Stop daemon (but keep browser running)
        print_info("Stopping daemon (keeping browser running)...")
        await HybridBrowserSession.stop_daemon_session(force=False)

        # Verify lock file still exists
        lock_still_exists = lock_file.exists()
        print_result(lock_still_exists, f"Lock file persisted: {lock_still_exists}")

        # Clear state
        HybridBrowserSession._daemon_session = None
        HybridBrowserSession._browser_pid = None
        HybridBrowserSession._cdp_url = None

        # Restart daemon - should reconnect to existing browser
        print_info("Restarting daemon (should reconnect to existing browser)...")
        daemon2 = await HybridBrowserSession.start_daemon_session(
            config={
                "browser": {
                    "headless": True,
                    "user_data_dir": user_data_dir,
                }
            }
        )

        second_pid = HybridBrowserSession._browser_pid
        second_cdp_url = HybridBrowserSession._cdp_url
        print_info(f"Second daemon PID: {second_pid}")
        print_info(f"Second daemon CDP URL: {second_cdp_url}")

        # Verify same browser was reused
        same_pid = first_pid == second_pid
        print_result(same_pid, f"Same browser PID: {first_pid} == {second_pid}")

        same_url = first_cdp_url == second_cdp_url
        print_result(same_url, f"Same CDP URL: {same_url}")

        # Cleanup - force close browser this time
        await HybridBrowserSession.stop_daemon_session(force=True)
        print_info("Daemon stopped (browser closed)")

        return lock_exists and same_pid

    except Exception as e:
        print_result(False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        # Cleanup on error
        try:
            await HybridBrowserSession.stop_daemon_session(force=True)
        except:
            pass
        return False


async def test_toolkit_reuse():
    """Test Scenario 5: BrowserToolkit reuses daemon session"""
    print_header("Scenario 5: BrowserToolkit Daemon Reuse")

    user_data_dir = str(Path.home() / ".ami" / "test-browser-profile-5")

    try:
        # Start daemon session
        print_info("Starting daemon session...")
        daemon = await HybridBrowserSession.start_daemon_session(
            config={
                "browser": {
                    "headless": True,
                    "user_data_dir": user_data_dir,
                }
            }
        )

        daemon_browser_id = id(daemon._browser)
        print_info(f"Daemon browser ID: {daemon_browser_id}")

        # Create toolkit (simulating agent usage)
        print_info("Creating BrowserToolkit (simulating agent)...")
        toolkit = BrowserToolkit(
            session_id="agent-task-001",
            headless=True,
        )

        # Use toolkit to visit a page (this will trigger session creation)
        print_info("Using toolkit to visit a page...")
        result = await toolkit.browser_visit_page("https://example.com")

        # Get the session that toolkit created
        toolkit_session = await toolkit._get_session()
        toolkit_browser_id = id(toolkit_session._browser)
        print_info(f"Toolkit session browser ID: {toolkit_browser_id}")

        # Verify browser reuse
        browser_reused = daemon_browser_id == toolkit_browser_id
        print_result(browser_reused, f"Toolkit reuses daemon browser: {browser_reused}")

        # Verify page was created
        has_page = toolkit_session._page is not None
        print_result(has_page, f"Toolkit session has page: {has_page}")

        # Verify visit worked
        visit_success = "example.com" in result.lower() or "Example Domain" in result
        print_result(visit_success, f"Visit successful: {visit_success}")

        # Cleanup
        await HybridBrowserSession.stop_daemon_session(force=True)
        print_info("Daemon session stopped")

        return browser_reused and has_page

    except Exception as e:
        print_result(False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run browser reuse tests"""
    print("\n" + "=" * 70)
    print("  BROWSER REUSE VERIFICATION TESTS")
    print("=" * 70)

    # Parse arguments
    scenario = sys.argv[1] if len(sys.argv) > 1 else "all"

    results = {}

    if scenario in ["all", "daemon"]:
        results["daemon"] = await test_daemon_reuse()

    if scenario in ["all", "non_daemon"]:
        results["non_daemon"] = await test_non_daemon_reuse()

    if scenario in ["all", "launcher"]:
        results["launcher"] = await test_browser_launcher_reuse()

    if scenario in ["all", "lock_file"]:
        results["lock_file"] = await test_lock_file_persistence()

    if scenario in ["all", "toolkit"]:
        results["toolkit"] = await test_toolkit_reuse()

    # Print summary
    print_header("TEST SUMMARY")
    all_passed = True
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("  🎉 All tests passed!")
    else:
        print("  ⚠️  Some tests failed!")
    print()

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
