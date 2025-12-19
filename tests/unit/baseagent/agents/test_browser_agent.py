#!/usr/bin/env python3
"""
Unit tests for BrowserAgent

Tests BrowserAgent functionality through workflow execution:
- Multi-step navigation
- Browser session preservation
- BrowserAgent + ScraperAgent cooperation
- Scroll interactions

Note: Tests use BaseAgent + workflow YAML approach to avoid circular import issues.
"""

import asyncio
import sys
import logging
import yaml
from pathlib import Path
from unittest.mock import MagicMock

# Add project path to sys.path
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from base_app.base_app.base_agent.core.base_agent import BaseAgent
from base_app.base_app.server.core.config_service import ConfigService
from base_app.base_app.base_agent.workflows.workflow_loader import load_workflow


class TestBrowserAgent:
    """Test suite for BrowserAgent using workflow-based approach"""

    def __init__(self):
        """Initialize test suite"""
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.workflow_dir = project_root / "tests" / "workflows" / "browser_agent_test"

    async def setup(self):
        """Setup test environment"""
        self.logger.info("Setting up test environment...")

        # Load test config service
        config_path = project_root / "src" / "base_app" / "config" / "baseapp.yaml"
        self.config_service = ConfigService(config_path=str(config_path))

        self.logger.info(f"Using config from: {config_path}")
        self.logger.info("✅ Test setup complete")

    async def cleanup(self):
        """Cleanup test environment"""
        self.logger.info("Test cleanup complete")

    async def test_multi_navigation_workflow(self):
        """Test multiple BrowserAgent navigation steps

        This workflow tests:
        1. Navigate to homepage
        2. Navigate to category page
        3. Navigate with scroll interaction

        Expected: All navigation steps execute successfully
        """
        self.logger.info("=" * 60)
        self.logger.info("TEST: Multi-Navigation Workflow")
        self.logger.info("=" * 60)

        workflow_file = self.workflow_dir / "multi_navigation_workflow.yaml"

        # Load workflow using workflow_loader
        workflow = load_workflow(str(workflow_file))

        # Create BaseAgent
        agent = BaseAgent(
            config_service=self.config_service,
            user_id="test_user_browser_agent"
        )

        # Execute workflow
        result = await agent.run_workflow(
            workflow,
            input_data={"test_mode": True}
        )

        # Verify results
        if not result.success:
            self.logger.error(f"Workflow execution failed: {result.error}")
            self.logger.error(f"Final result: {result.final_result}")
            return False

        assert result.final_result is not None

        # Check that final_result is a dict (not error string)
        if not isinstance(result.final_result, dict):
            self.logger.error(f"Expected dict result, got {type(result.final_result)}: {result.final_result}")
            return False

        # Check that we have navigation results
        navigation_results = result.final_result.get('navigation_results', [])
        assert len(navigation_results) >= 3, "Should have at least 3 navigation results"

        self.logger.info("✅ Multi-navigation workflow completed successfully")
        self.logger.info(f"   Final URL: {result.final_result.get('final_url')}")
        self.logger.info(f"   Navigation steps: {len(navigation_results)}")
        return True

    async def test_browser_scraper_cooperation(self):
        """Test BrowserAgent + ScraperAgent cooperation

        This workflow tests:
        1. BrowserAgent: Navigate to homepage (establish session)
        2. BrowserAgent: Navigate to category page
        3. ScraperAgent: Extract data from current page (use_current_page=true)

        Expected:
        - All steps execute successfully
        - ScraperAgent uses page from BrowserAgent without re-navigation
        - Product URLs are extracted
        """
        self.logger.info("=" * 60)
        self.logger.info("TEST: BrowserAgent + ScraperAgent Cooperation")
        self.logger.info("=" * 60)

        workflow_file = self.workflow_dir / "browser_scraper_cooperation_workflow.yaml"

        # Load workflow using workflow_loader
        workflow = load_workflow(str(workflow_file))

        # Create BaseAgent
        agent = BaseAgent(
            config_service=self.config_service,
            user_id="test_user_cooperation"
        )

        # Execute workflow
        result = await agent.run_workflow(
            workflow,
            input_data={"max_products": 5}
        )

        # Verify results
        if not result.success:
            self.logger.error(f"Workflow execution failed: {result.error}")
            self.logger.error(f"Final result: {result.final_result}")
            return False

        assert result.final_result is not None

        # Check that final_result is a dict (not error string)
        if not isinstance(result.final_result, dict):
            self.logger.error(f"Expected dict result, got {type(result.final_result)}: {result.final_result}")
            return False

        # Check that we extracted product URLs
        product_urls = result.final_result.get('product_urls', [])
        assert len(product_urls) > 0, "Should have extracted at least one product URL"
        assert len(product_urls) <= 5, "Should not exceed max_products limit"

        # Verify URL format
        for product in product_urls:
            assert 'url' in product, "Each product should have a 'url' field"
            assert product['url'].startswith('http'), "URL should be valid"

        self.logger.info("✅ Browser-Scraper cooperation workflow completed successfully")
        self.logger.info(f"   Extracted {len(product_urls)} product URLs")
        self.logger.info(f"   Sample URL: {product_urls[0]['url']}")
        return True

    async def test_navigation_session_preservation(self):
        """Test that browser session is preserved across navigation steps

        This test verifies that:
        - Multiple BrowserAgent steps share the same session
        - Cookies and session state persist
        - ScraperAgent can use the session from BrowserAgent
        """
        self.logger.info("=" * 60)
        self.logger.info("TEST: Navigation Session Preservation")
        self.logger.info("=" * 60)

        workflow_file = self.workflow_dir / "browser_scraper_cooperation_workflow.yaml"

        # Load workflow using workflow_loader
        workflow = load_workflow(str(workflow_file))

        # Create BaseAgent
        agent = BaseAgent(
            config_service=self.config_service,
            user_id="test_user_session"
        )

        # Execute workflow
        result = await agent.run_workflow(
            workflow,
            input_data={"max_products": 3}
        )

        # If workflow succeeds, it means session was preserved
        # (otherwise navigation would fail or ScraperAgent wouldn't find the page)
        assert result.success, "Session preservation failed - workflow did not complete"

        self.logger.info("✅ Session preservation test passed")
        return True

    async def test_workflow_yaml_validation(self):
        """Validate workflow YAML structure"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Workflow YAML Validation")
        self.logger.info("=" * 60)

        # Test multi-navigation workflow
        workflow_file = self.workflow_dir / "multi_navigation_workflow.yaml"
        with open(workflow_file, 'r') as f:
            workflow = yaml.safe_load(f)

        assert workflow['apiVersion'] == "ami.io/v1"
        assert workflow['kind'] == "Workflow"
        assert 'metadata' in workflow
        assert 'steps' in workflow

        steps = workflow['steps']
        assert len(steps) >= 3, "Should have at least 3 navigation steps"

        # Check that first 3 steps are browser_agent
        for i in range(3):
            assert steps[i]['agent_type'] == 'browser_agent', f"Step {i+1} should be browser_agent"

        self.logger.info("✅ multi_navigation_workflow.yaml structure is valid")

        # Test cooperation workflow
        workflow_file = self.workflow_dir / "browser_scraper_cooperation_workflow.yaml"
        with open(workflow_file, 'r') as f:
            workflow = yaml.safe_load(f)

        assert workflow['apiVersion'] == "ami.io/v1"
        assert workflow['kind'] == "Workflow"

        steps = workflow['steps']
        assert len(steps) >= 3

        # Step 1 & 2: BrowserAgent
        assert steps[0]['agent_type'] == 'browser_agent'
        assert steps[1]['agent_type'] == 'browser_agent'

        # Step 3: ScraperAgent with use_current_page
        assert steps[2]['agent_type'] == 'scraper_agent'
        assert steps[2]['inputs']['use_current_page'] == True, "ScraperAgent should use current page"

        self.logger.info("✅ browser_scraper_cooperation_workflow.yaml structure is valid")
        return True

    async def run_all_tests(self):
        """Run all tests"""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("BROWSER AGENT UNIT TESTS")
        self.logger.info("=" * 70 + "\n")

        tests = [
            ("YAML Validation", self.test_workflow_yaml_validation, False),  # Fast test, no browser
            ("Multi-Navigation", self.test_multi_navigation_workflow, True),  # Slow test, needs browser
            ("Browser-Scraper Cooperation", self.test_browser_scraper_cooperation, True),  # Slow test
            ("Session Preservation", self.test_navigation_session_preservation, True),  # Slow test
        ]

        passed = 0
        failed = 0
        skipped = 0

        for test_name, test_func, needs_browser in tests:
            try:
                await self.setup()

                # Skip slow tests by default (can be run with --slow flag)
                if needs_browser and not run_slow_tests:
                    self.logger.info(f"⊘ Skipping slow test: {test_name} (use --slow to run)")
                    skipped += 1
                    continue

                result = await test_func()
                if result:
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                self.logger.error(f"❌ Test {test_name} failed with exception: {e}")
                import traceback
                traceback.print_exc()
                failed += 1
            finally:
                await self.cleanup()

        self.logger.info("\n" + "=" * 70)
        self.logger.info(f"TEST SUMMARY: {passed} passed, {failed} failed, {skipped} skipped")
        self.logger.info("=" * 70 + "\n")

        return failed == 0


async def main():
    """Main test runner"""
    import argparse

    parser = argparse.ArgumentParser(description='Run BrowserAgent unit tests')
    parser.add_argument(
        '--slow',
        action='store_true',
        help='Run slow tests (requires actual browser)'
    )
    args = parser.parse_args()

    global run_slow_tests
    run_slow_tests = args.slow

    print(f"\n{'=' * 70}")
    print(f"BrowserAgent Unit Tests")
    if run_slow_tests:
        print(f"Mode: Full tests (including browser-based tests)")
    else:
        print(f"Mode: Fast tests only (use --slow for browser tests)")
    print(f"{'=' * 70}\n")

    test_suite = TestBrowserAgent()
    success = await test_suite.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
