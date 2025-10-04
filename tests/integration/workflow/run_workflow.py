#!/usr/bin/env python3
"""
Workflow Test Runner
Run and test workflow YAML files with different configurations

Usage:
    python run_workflow.py <workflow_name> [options]

Examples:
    # Run built-in workflow
    python run_workflow.py user-qa-workflow --input "Hello"

    # Run user workflow
    python run_workflow.py paginated-scraper-workflow --url "https://example.com" --max-pages 2

    # Run with custom config
    python run_workflow.py my-workflow --config config.yaml --verbose
"""

import asyncio
import argparse
import json
import yaml
import sys
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

# Add project path to sys.path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "base_app"))

from base_app.base_agent.core.base_agent import BaseAgent
from base_app.base_agent.core.schemas import AgentConfig, AgentContext
from base_app.base_agent.workflows.workflow_loader import load_workflow, list_workflows
from base_app.base_agent.agents.scraper_agent import ScraperAgent
from base_app.server.core.config_service import ConfigService


class WorkflowTestRunner:
    """Workflow test runner class"""

    def __init__(
        self,
        config_path: Optional[str] = None,
        verbose: bool = False,
        user_id: str = "test_user"
    ):
        """Initialize workflow runner

        Args:
            config_path: Path to config file (optional)
            verbose: Enable verbose logging
            user_id: User ID for memory isolation (default: "test_user")
        """
        # Setup logging
        log_level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

        # Store user_id
        self.user_id = user_id

        # Load configuration
        try:
            if config_path:
                self.config_service = ConfigService(config_path=config_path)
            else:
                self.config_service = ConfigService()
            self.logger.info(f"Loaded config from: {self.config_service.config_path}")
        except FileNotFoundError as e:
            # Config file is required
            self.logger.error(f"Config file not found: {e}")
            raise RuntimeError(
                "Configuration file is required. Please ensure baseapp.yaml exists in base_app/config/ "
                "or set BASEAPP_CONFIG_PATH environment variable"
            )

        self.base_agent = None
        self.context = None

    async def initialize(self, llm_provider: str = None, llm_model: str = None):
        """Initialize BaseAgent and context (only once)

        Args:
            llm_provider: LLM provider (openai, anthropic, etc.)
            llm_model: LLM model name
        """
        # Check if already initialized
        if self.base_agent is not None:
            self.logger.info(f"BaseAgent already initialized for user '{self.user_id}', skipping initialization")
            return

        # Get LLM config from service
        # Use ConfigService's get method to properly handle environment variables
        if not llm_provider:
            llm_provider = self.config_service.get('agent.llm.provider', 'openai')
        if not llm_model:
            llm_model = self.config_service.get('agent.llm.model', 'gpt-4o')
        # Get API key from config - this will handle ${OPENAI_API_KEY} expansion
        api_key = self.config_service.get('agent.llm.api_key')

        # Create BaseAgent
        agent_config = AgentConfig(
            name="WorkflowTestRunner",
            llm_provider=llm_provider,
            llm_model=llm_model,
            api_key=api_key or ""  # AgentConfig requires string, empty is ok
        )

        # Create provider config for BaseAgent
        # Don't pass empty string for api_key, let provider handle env var lookup
        provider_config = {
            'type': llm_provider,
            'api_key': api_key if api_key else None,  # Pass None, not empty string
            'model_name': llm_model
        }

        # Create BaseAgent with user_id for memory isolation
        self.base_agent = BaseAgent(
            agent_config,
            config_service=self.config_service,  # Pass config service
            provider_config=provider_config,
            user_id=self.user_id  # Pass user_id for memory isolation
        )
        self.logger.info(f"Initialized BaseAgent with {llm_provider}/{llm_model} for user '{self.user_id}'")

        # Debug: Check if provider is initialized
        if self.base_agent.provider:
            self.logger.info(f"Provider initialized: {type(self.base_agent.provider).__name__}")
            self.logger.info(f"Provider has API key: {'Yes' if getattr(self.base_agent.provider, 'api_key', None) else 'No'}")
        else:
            self.logger.warning("Provider NOT initialized in BaseAgent")

        # Register required agents if needed
        # ScraperAgent is automatically available through the workflow engine
        self.logger.info("Agent initialization complete")

        # Create context with browser session management
        self.context = AgentContext(
            workflow_id=f"test_workflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            step_id="initial",
            variables={
                "user_id": "test_user",
                "session_id": f"test_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            }
        )

    async def run_workflow(
        self,
        workflow_name: str,
        input_data: Dict[str, Any],
        save_result: bool = False
    ):
        """Run a workflow

        Args:
            workflow_name: Name or path of workflow
            input_data: Input data for workflow
            save_result: Whether to save result to file

        Returns:
            WorkflowResult object
        """
        if not self.base_agent:
            raise RuntimeError("Runner not initialized. Call initialize() first.")

        # Load workflow
        self.logger.info(f"Loading workflow: {workflow_name}")
        try:
            workflow = load_workflow(workflow_name)
            self.logger.info(f"Loaded workflow: {workflow.name} v{workflow.version}")
            self.logger.info(f"Steps: {len(workflow.steps)}")
        except Exception as e:
            self.logger.error(f"Failed to load workflow: {e}")
            raise

        # Run workflow
        self.logger.info("Starting workflow execution...")
        self.logger.info(f"Input data: {json.dumps(input_data, indent=2)}")

        start_time = datetime.now()

        try:
            result = await self.base_agent.run_workflow(
                workflow=workflow,
                input_data=input_data
            )

            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            # Log results
            self.logger.info(f"Workflow completed in {execution_time:.2f} seconds")
            self.logger.info(f"Success: {result.success}")

            if result.success:
                self.logger.info("=== Workflow Output ===")
                self.logger.info(json.dumps(result.final_result, indent=2, ensure_ascii=False))

                # Show step results
                if result.steps:
                    self.logger.info("=== Step Results ===")
                    for i, step in enumerate(result.steps, 1):
                        self.logger.info(f"Step {i}: {step.step_id[:8]} - {step.message}")
            else:
                self.logger.error(f"Workflow failed: {result.error_message}")
                if result.steps:
                    for step in result.steps:
                        if not step.success:
                            self.logger.error(f"  Failed step: {step.step_id[:8]} - {step.message}")

            # Save result if requested
            if save_result:
                result_file = f"workflow_result_{workflow_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                result_data = {
                    "workflow": workflow_name,
                    "input": input_data,
                    "success": result.success,
                    "execution_time": execution_time,
                    "final_result": result.final_result,
                    "error": result.error_message,
                    "steps": [
                        {
                            "id": step.step_id,
                            "success": step.success,
                            "message": step.message,
                            "execution_time": step.execution_time
                        }
                        for step in result.steps
                    ] if result.steps else []
                }

                with open(result_file, 'w', encoding='utf-8') as f:
                    json.dump(result_data, f, indent=2, ensure_ascii=False)

                self.logger.info(f"Result saved to: {result_file}")

            return result

        except Exception as e:
            self.logger.error(f"Workflow execution failed: {e}")
            import traceback
            traceback.print_exc()
            raise

        finally:
            # Cleanup browser session if used
            if self.context._browser_session_manager:
                await self.context._browser_session_manager.cleanup()
                self.logger.info("Browser session cleaned up")

    async def cleanup(self):
        """Cleanup resources"""
        if self.context and self.context._browser_session_manager:
            # Force close all browser sessions
            await self.context._browser_session_manager.close_all_sessions()
            self.logger.info("All browser sessions closed")


def parse_input_data(args) -> Dict[str, Any]:
    """Parse input data from command line arguments

    Args:
        args: Parsed arguments

    Returns:
        Dict of input data
    """
    input_data = {}

    # Parse JSON input
    if args.json:
        try:
            input_data.update(json.loads(args.json))
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON input: {e}")
            sys.exit(1)

    # Parse key-value inputs
    if args.input:
        for item in args.input:
            if '=' in item:
                key, value = item.split('=', 1)
                # Try to parse as JSON first
                try:
                    input_data[key] = json.loads(value)
                except:
                    # Otherwise treat as string
                    input_data[key] = value
            else:
                print(f"Invalid input format: {item} (expected key=value)")
                sys.exit(1)

    # Add specific workflow parameters
    if args.url:
        input_data['target_url'] = args.url
    if args.max_pages:
        input_data['max_pages'] = args.max_pages
    if args.products_per_page:
        input_data['products_per_page'] = args.products_per_page

    return input_data


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Run and test workflow YAML files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        'workflow',
        nargs='?',
        help='Workflow name or path to YAML file'
    )

    # Input options
    input_group = parser.add_argument_group('Input Options')
    input_group.add_argument(
        '--input', '-i',
        action='append',
        help='Input data as key=value pairs (can be used multiple times)'
    )
    input_group.add_argument(
        '--json', '-j',
        help='Input data as JSON string'
    )

    # Workflow-specific options
    workflow_group = parser.add_argument_group('Workflow-specific Options')
    workflow_group.add_argument(
        '--url',
        help='Target URL for scraper workflows'
    )
    workflow_group.add_argument(
        '--max-pages',
        type=int,
        help='Maximum pages to scrape'
    )
    workflow_group.add_argument(
        '--products-per-page',
        type=int,
        help='Products per page for pagination'
    )

    # Configuration options
    config_group = parser.add_argument_group('Configuration Options')
    config_group.add_argument(
        '--config', '-c',
        help='Path to config file'
    )
    config_group.add_argument(
        '--llm-provider',
        help='LLM provider (openai, anthropic, etc.)'
    )
    config_group.add_argument(
        '--llm-model',
        help='LLM model name'
    )
    config_group.add_argument(
        '--user-id',
        default='test_user',
        help='User ID for memory isolation (default: test_user)'
    )

    # Output options
    output_group = parser.add_argument_group('Output Options')
    output_group.add_argument(
        '--save', '-s',
        action='store_true',
        help='Save result to JSON file'
    )
    output_group.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    # Special commands
    parser.add_argument(
        '--list',
        action='store_true',
        help='List available workflows and exit'
    )

    args = parser.parse_args()

    # Handle list command
    if args.list or (not args.workflow and not args.list):
        workflows = list_workflows()
        print("Available Workflows:")
        print("\nBuilt-in Workflows:")
        for wf in workflows['builtin']:
            print(f"  - {wf}")
        print("\nUser Workflows:")
        if workflows['user']:
            for wf in workflows['user']:
                print(f"  - {wf}")
        else:
            print("  (none)")
        return

    # Parse input data
    input_data = parse_input_data(args)

    # Create and run workflow
    runner = WorkflowTestRunner(
        config_path=args.config,
        verbose=args.verbose,
        user_id=args.user_id
    )

    try:
        # Initialize runner
        await runner.initialize(
            llm_provider=args.llm_provider,
            llm_model=args.llm_model
        )

        # Run workflow
        result = await runner.run_workflow(
            workflow_name=args.workflow,
            input_data=input_data,
            save_result=args.save
        )

        # Exit with appropriate code
        sys.exit(0 if result.success else 1)

    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())