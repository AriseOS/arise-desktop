"""
Unit tests for IntentExtractor

Tests the automatic extraction of Intents from User Operations JSON.
"""
import json
import logging
import os
from pathlib import Path

import pytest

from src.intent_builder.extractors.intent_extractor import IntentExtractor
from src.common.llm import AnthropicProvider

# Configure logging to see segmentation details
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    force=True
)


class TestIntentExtractor:
    """End-to-end tests for IntentExtractor"""

    @pytest.fixture
    def user_operations_json(self):
        """Load the real User Operations JSON example"""
        json_path = Path(__file__).parent.parent.parent.parent / "docs/intent_builder/examples/browser-user-operation-tracker-example.json"
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @pytest.mark.asyncio
    async def test_extract_intents_with_real_llm(self, user_operations_json):
        """Test end-to-end intent extraction with real LLM (Anthropic Claude)"""
        # Check if API key is available
        if not os.environ.get("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set, skipping real LLM test")

        # Initialize LLM provider
        llm_provider = AnthropicProvider()
        extractor = IntentExtractor(llm_provider=llm_provider)

        # Extract all operations
        intents = await extractor.extract_intents(
            user_operations_json["operations"],
            task_description="Collect coffee product prices from Allegro",
            source_session_id="session_demo_001"
        )

        print(f"\n{'='*70}")
        print(f"IntentExtractor End-to-End Test (Real LLM)")
        print(f"{'='*70}")
        print(f"\nInput: {len(user_operations_json['operations'])} operations")
        print(f"Output: {len(intents)} intents")
        print(f"LLM Model: {llm_provider.model_name}\n")

        for i, intent in enumerate(intents, 1):
            print(f"Intent {i}:")
            print(f"  ID: {intent.id}")
            print(f"  Description: {intent.description}")
            print(f"  Operations: {len(intent.operations)} steps")
            op_types = [op.type for op in intent.operations]
            print(f"  Operation Types: {' -> '.join(op_types)}")
            print()

        print(f"{'='*70}")
        print(f"✅ Successfully extracted {len(intents)} intents from {len(user_operations_json['operations'])} operations")
        print(f"{'='*70}\n")

        # Basic assertions
        assert len(intents) >= 1, "Should extract at least 1 intent"
        assert all(intent.id.startswith("intent_") for intent in intents), "All intent IDs should start with 'intent_'"
        assert all(intent.description for intent in intents), "All intents should have descriptions"
        assert all(len(intent.operations) > 0 for intent in intents), "All intents should have operations"
        assert all(intent.source_session_id == "session_demo_001" for intent in intents), "All intents should have correct session ID"

        # Verify all operations are covered
        total_ops = sum(len(intent.operations) for intent in intents)
        assert total_ops == len(user_operations_json["operations"]), f"All operations should be covered: {total_ops} != {len(user_operations_json['operations'])}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
