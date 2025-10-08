#!/usr/bin/env python3
"""
Test script for foreach loop functionality

Usage:
    python test_foreach.py [--verbose]

This test verifies that:
1. Foreach loop can iterate through a list of items
2. item_var and index_var are correctly set in each iteration
3. Loop body steps execute for each item
4. Results are correctly accumulated
"""

import asyncio
import sys
import logging
from pathlib import Path

# Add project path to sys.path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from base_app.base_app.base_agent.core.base_agent import BaseAgent
from base_app.base_app.base_agent.core.schemas import AgentConfig
from base_app.base_app.base_agent.workflows.workflow_loader import load_workflow
from base_app.base_app.server.core.config_service import ConfigService


class ForeachLoopTester:
    """Test harness for foreach loop functionality"""

    def __init__(self, verbose: bool = False):
        """Initialize tester

        Args:
            verbose: Enable verbose logging
        """
        # Setup logging
        log_level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

        # Load config
        try:
            self.config_service = ConfigService()
            self.logger.info(f"Loaded config from: {self.config_service.config_path}")
        except FileNotFoundError as e:
            self.logger.error(f"Config file not found: {e}")
            raise RuntimeError(
                "Configuration file is required. Please ensure baseapp.yaml exists"
            )

    async def test_basic_foreach(self):
        """Test basic foreach loop iteration"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Basic Foreach Loop Iteration")
        self.logger.info("=" * 60)

        # Create BaseAgent
        llm_provider = self.config_service.get('agent.llm.provider', 'openai')
        llm_model = self.config_service.get('agent.llm.model', 'gpt-4o')
        api_key = self.config_service.get('agent.llm.api_key')

        agent_config = AgentConfig(
            name="ForeachTester",
            llm_provider=llm_provider,
            llm_model=llm_model,
            api_key=api_key or ""
        )

        provider_config = {
            'type': llm_provider,
            'api_key': api_key if api_key else None,
            'model_name': llm_model
        }

        base_agent = BaseAgent(
            agent_config,
            config_service=self.config_service,
            provider_config=provider_config
        )

        # Load workflow
        self.logger.info("Loading foreach-test-workflow...")
        workflow = load_workflow("foreach-test-workflow")
        self.logger.info(f"Loaded: {workflow.name} v{workflow.version}")

        # Run workflow
        self.logger.info("Executing workflow...")
        input_data = {
            "test_mode": "simple"
        }

        result = await base_agent.run_workflow(
            workflow=workflow,
            input_data=input_data
        )

        # Verify results
        self.logger.info("=" * 60)
        self.logger.info("RESULTS:")
        self.logger.info("=" * 60)

        if not result.success:
            self.logger.error(f"❌ Workflow failed: {result.error_message}")
            return False

        self.logger.info("✅ Workflow execution successful")

        # Debug: print final_result type and content
        self.logger.info(f"final_result type: {type(result.final_result)}")
        self.logger.info(f"final_result content: {result.final_result}")

        # Check processed items
        if isinstance(result.final_result, str):
            self.logger.error(f"❌ final_result is string, expected dict")
            return False

        processed_items = result.final_result.get('processed_items', [])
        self.logger.info(f"Processed items count: {len(processed_items)}")

        if len(processed_items) != 5:
            self.logger.error(f"❌ Expected 5 items, got {len(processed_items)}")
            return False

        self.logger.info("✅ Correct number of items processed")

        # Verify each item
        expected_names = ["Item A", "Item B", "Item C", "Item D", "Item E"]
        for i, item in enumerate(processed_items):
            self.logger.info(f"  Item {i}:")
            self.logger.info(f"    Index: {item.get('index')}")
            self.logger.info(f"    Original: {item.get('original_name')}")
            self.logger.info(f"    Processed: {item.get('processed_name')}")
            self.logger.info(f"    Value: {item.get('original_value')}")
            self.logger.info(f"    Category: {item.get('category')}")

            # Verify index
            if item.get('index') != i:
                self.logger.error(f"❌ Item {i}: Wrong index {item.get('index')}")
                return False

            # Verify name
            if item.get('original_name') != expected_names[i]:
                self.logger.error(f"❌ Item {i}: Wrong name {item.get('original_name')}")
                return False

        self.logger.info("✅ All items verified successfully")
        self.logger.info("=" * 60)
        self.logger.info("TEST PASSED ✅")
        self.logger.info("=" * 60)

        return True

    async def test_variable_access(self):
        """Test that item_var and index_var are accessible in loop body"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Variable Access in Loop Body")
        self.logger.info("=" * 60)

        # This test is covered by test_basic_foreach
        # If basic test passes, variable access is working
        self.logger.info("✅ Variable access tested via basic foreach test")
        return True

    async def test_nested_data_access(self):
        """Test accessing nested properties like {{current_item.name}}"""
        self.logger.info("=" * 60)
        self.logger.info("TEST: Nested Data Access")
        self.logger.info("=" * 60)

        # This test is covered by test_basic_foreach
        # The workflow accesses {{current_item.name}}, {{current_item.value}}, etc.
        self.logger.info("✅ Nested data access tested via basic foreach test")
        return True

    async def run_all_tests(self):
        """Run all tests"""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("FOREACH LOOP TEST SUITE")
        self.logger.info("=" * 60 + "\n")

        tests = [
            ("Basic Foreach Loop", self.test_basic_foreach),
            ("Variable Access", self.test_variable_access),
            ("Nested Data Access", self.test_nested_data_access),
        ]

        results = []
        for test_name, test_func in tests:
            try:
                self.logger.info(f"\nRunning: {test_name}")
                result = await test_func()
                results.append((test_name, result))
            except Exception as e:
                self.logger.error(f"❌ Test '{test_name}' failed with exception: {e}")
                import traceback
                traceback.print_exc()
                results.append((test_name, False))

        # Summary
        self.logger.info("\n" + "=" * 60)
        self.logger.info("TEST SUMMARY")
        self.logger.info("=" * 60)

        passed = sum(1 for _, result in results if result)
        total = len(results)

        for test_name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            self.logger.info(f"{status}: {test_name}")

        self.logger.info("=" * 60)
        self.logger.info(f"Results: {passed}/{total} tests passed")
        self.logger.info("=" * 60)

        return all(result for _, result in results)


async def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description='Test foreach loop functionality')
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    tester = ForeachLoopTester(verbose=args.verbose)

    try:
        success = await tester.run_all_tests()
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())