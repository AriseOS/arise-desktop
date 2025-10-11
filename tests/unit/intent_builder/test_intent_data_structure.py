"""
Unit tests for Intent data structure and generation from User Operations

This test uses the real User Operations JSON example to test Intent generation.
"""
import json
from datetime import datetime
from pathlib import Path

import pytest

from src.intent_builder.core.intent import Intent, Operation, generate_intent_id


class TestIntentDataStructure:
    """Test Intent basic data structure"""

    def test_generate_intent_id(self):
        """Test intent ID generation from description"""
        description = "Navigate to Allegro homepage"
        intent_id = generate_intent_id(description)

        assert intent_id.startswith("intent_")
        assert len(intent_id) == 15  # "intent_" + 8 chars hash

        # Same description should generate same ID
        intent_id2 = generate_intent_id(description)
        assert intent_id == intent_id2

        # Different description should generate different ID
        intent_id3 = generate_intent_id("Different description")
        assert intent_id != intent_id3

    def test_operation_creation(self):
        """Test Operation creation"""
        op = Operation(
            type="navigate",
            timestamp=1757730777260,
            url="https://allegro.pl/",
            page_title="Allegro - Strona Główna",
            element={},
            data={}
        )

        assert op.type == "navigate"
        assert op.url == "https://allegro.pl/"
        assert op.page_title == "Allegro - Strona Główna"

    def test_operation_with_element_data(self):
        """Test Operation with DOM element data"""
        op = Operation(
            type="click",
            url="https://allegro.pl/",
            element={
                "xpath": "//div[2]/div[1]/button",
                "tagName": "BUTTON",
                "textContent": "Coffee",
                "href": "https://allegro.pl/coffee"
            },
            data={
                "button": 0,
                "clientX": 100,
                "clientY": 200
            }
        )

        assert op.element["tagName"] == "BUTTON"
        assert op.element["textContent"] == "Coffee"
        assert op.data["clientX"] == 100

    def test_intent_create(self):
        """Test Intent.create() factory method"""
        operations = [
            Operation(type="navigate", url="https://example.com")
        ]

        intent = Intent.create(
            description="Navigate to example homepage",
            operations=operations,
            source_session_id="session_001"
        )

        assert intent.id.startswith("intent_")
        assert intent.description == "Navigate to example homepage"
        assert len(intent.operations) == 1
        assert intent.source_session_id == "session_001"
        assert isinstance(intent.created_at, datetime)

    def test_intent_validation(self):
        """Test Intent validation"""
        operations = [Operation(type="navigate", url="https://example.com")]

        # Empty description should raise error
        with pytest.raises(ValueError, match="description cannot be empty"):
            Intent(
                id="intent_12345678",
                description="",
                operations=operations,
                created_at=datetime.now(),
                source_session_id="session_001"
            )

        # Empty operations should raise error
        with pytest.raises(ValueError, match="at least one operation"):
            Intent(
                id="intent_12345678",
                description="Test intent",
                operations=[],
                created_at=datetime.now(),
                source_session_id="session_001"
            )

        # Invalid ID format should raise error
        with pytest.raises(ValueError, match="Invalid intent ID format"):
            Intent(
                id="wrong_format",
                description="Test intent",
                operations=operations,
                created_at=datetime.now(),
                source_session_id="session_001"
            )

    def test_intent_serialization(self):
        """Test Intent to_dict() and from_dict()"""
        operations = [
            Operation(
                type="navigate",
                url="https://example.com",
                page_title="Example",
                element={"xpath": "//div"},
                data={"key": "value"}
            )
        ]

        intent = Intent.create(
            description="Test intent",
            operations=operations,
            source_session_id="session_001"
        )

        # Serialize
        data = intent.to_dict()
        assert data["id"] == intent.id
        assert data["description"] == "Test intent"
        assert len(data["operations"]) == 1
        assert data["operations"][0]["type"] == "navigate"

        # Deserialize
        restored = Intent.from_dict(data)
        assert restored.id == intent.id
        assert restored.description == intent.description
        assert len(restored.operations) == 1
        assert restored.operations[0].type == "navigate"
        assert restored.operations[0].url == "https://example.com"


class TestIntentFromUserOperations:
    """Test Intent generation from real User Operations JSON"""

    @pytest.fixture
    def user_operations_json(self):
        """Load the real User Operations JSON example"""
        json_path = Path(__file__).parent.parent.parent.parent / "docs/intent_builder/examples/browser-user-operation-tracker-example.json"
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def test_load_user_operations(self, user_operations_json):
        """Test that we can load the User Operations JSON"""
        assert "session_info" in user_operations_json
        assert "operations" in user_operations_json
        assert user_operations_json["session_info"]["total_operations"] == 16
        assert len(user_operations_json["operations"]) == 16

    def test_extract_single_navigation_intent(self, user_operations_json):
        """Test extracting a simple navigation intent"""
        # Operation at index 1: navigate to allegro.pl
        nav_op = user_operations_json["operations"][1]

        operation = Operation(
            type=nav_op["type"],
            timestamp=nav_op.get("timestamp"),
            url=nav_op.get("url"),
            page_title=nav_op.get("page_title"),
            element=nav_op.get("element", {}),
            data=nav_op.get("data", {})
        )

        intent = Intent.create(
            description="Navigate to Allegro e-commerce website homepage",
            operations=[operation],
            source_session_id="session_demo_001"
        )

        assert intent.description == "Navigate to Allegro e-commerce website homepage"
        assert len(intent.operations) == 1
        assert intent.operations[0].type == "navigate"
        assert intent.operations[0].url == "https://allegro.pl/"

        print(f"\n✅ Generated Intent ID: {intent.id}")
        print(f"   Description: {intent.description}")
        print(f"   Operations: {len(intent.operations)}")

    def test_extract_menu_navigation_intent(self, user_operations_json):
        """Test extracting menu navigation intent (click -> click -> navigate)"""
        # Operations 2-4: click menu button -> click coffee link -> navigate
        ops_data = user_operations_json["operations"][2:5]

        operations = [
            Operation(
                type=op["type"],
                timestamp=op.get("timestamp"),
                url=op.get("url"),
                page_title=op.get("page_title"),
                element=op.get("element", {}),
                data=op.get("data", {})
            )
            for op in ops_data
        ]

        intent = Intent.create(
            description="Navigate to coffee category page through menu",
            operations=operations,
            source_session_id="session_demo_001"
        )

        assert len(intent.operations) == 3
        assert intent.operations[0].type == "click"
        assert intent.operations[1].type == "click"
        assert intent.operations[1].element.get("textContent") == "Kawy"
        assert intent.operations[2].type == "navigate"

        print(f"\n✅ Generated Intent ID: {intent.id}")
        print(f"   Description: {intent.description}")
        print(f"   Operations: click -> click (Kawy) -> navigate")

    def test_extract_data_extraction_intent(self, user_operations_json):
        """Test extracting data extraction intent (navigate -> select -> copy -> select -> copy)"""
        # Operations 6-12: navigate to product page, extract title and price
        ops_data = user_operations_json["operations"][6:13]

        operations = [
            Operation(
                type=op["type"],
                timestamp=op.get("timestamp"),
                url=op.get("url"),
                page_title=op.get("page_title"),
                element=op.get("element", {}),
                data=op.get("data", {})
            )
            for op in ops_data
        ]

        intent = Intent.create(
            description="Visit product detail page and extract product title and price",
            operations=operations,
            source_session_id="session_demo_001"
        )

        # Analyze operations
        operation_types = [op.type for op in intent.operations]
        assert operation_types == ["navigate", "click", "select", "copy_action", "click", "select", "copy_action"]

        # Check extracted data
        copy_ops = [op for op in intent.operations if op.type == "copy_action"]
        assert len(copy_ops) == 2

        # First copy: product title
        title_data = copy_ops[0].data.get("copiedText")
        assert "Kawa ziarnista" in title_data
        assert "BRAZYLIA Santos" in title_data

        # Second copy: price
        price_data = copy_ops[1].data.get("copiedText")
        assert "69,50" in price_data  # Price contains "69,50" (ignore whitespace variations)

        print(f"\n✅ Generated Intent ID: {intent.id}")
        print(f"   Description: {intent.description}")
        print(f"   Operations: {' -> '.join(operation_types)}")
        print(f"   Extracted Title: {title_data[:50]}...")
        print(f"   Extracted Price: {price_data}")

    def test_full_workflow_intents(self, user_operations_json):
        """Test generating all intents for the complete workflow"""
        # Intent 1: Initial navigation (operation 1)
        intent1 = Intent.create(
            description="Navigate to Allegro e-commerce website homepage",
            operations=[
                Operation(
                    type=user_operations_json["operations"][1]["type"],
                    timestamp=user_operations_json["operations"][1].get("timestamp"),
                    url=user_operations_json["operations"][1].get("url"),
                    page_title=user_operations_json["operations"][1].get("page_title"),
                    element=user_operations_json["operations"][1].get("element", {}),
                    data=user_operations_json["operations"][1].get("data", {})
                )
            ],
            source_session_id="session_demo_001"
        )

        # Intent 2: Menu navigation (operations 2-4)
        intent2_ops = [
            Operation(
                type=op["type"],
                timestamp=op.get("timestamp"),
                url=op.get("url"),
                page_title=op.get("page_title"),
                element=op.get("element", {}),
                data=op.get("data", {})
            )
            for op in user_operations_json["operations"][2:5]
        ]
        intent2 = Intent.create(
            description="Navigate to coffee category page through menu",
            operations=intent2_ops,
            source_session_id="session_demo_001"
        )

        # Intent 3: Click product link (operations 5-6)
        intent3_ops = [
            Operation(
                type=op["type"],
                timestamp=op.get("timestamp"),
                url=op.get("url"),
                page_title=op.get("page_title"),
                element=op.get("element", {}),
                data=op.get("data", {})
            )
            for op in user_operations_json["operations"][5:7]
        ]
        intent3 = Intent.create(
            description="Click on product link to view details",
            operations=intent3_ops,
            source_session_id="session_demo_001"
        )

        # Intent 4: Extract product data (operations 7-12)
        intent4_ops = [
            Operation(
                type=op["type"],
                timestamp=op.get("timestamp"),
                url=op.get("url"),
                page_title=op.get("page_title"),
                element=op.get("element", {}),
                data=op.get("data", {})
            )
            for op in user_operations_json["operations"][7:13]
        ]
        intent4 = Intent.create(
            description="Extract product title and price information",
            operations=intent4_ops,
            source_session_id="session_demo_001"
        )

        # Verify all intents
        all_intents = [intent1, intent2, intent3, intent4]

        print("\n" + "="*60)
        print("Generated Intents from User Operations:")
        print("="*60)

        for i, intent in enumerate(all_intents, 1):
            print(f"\nIntent {i}:")
            print(f"  ID: {intent.id}")
            print(f"  Description: {intent.description}")
            print(f"  Operations: {len(intent.operations)} steps")
            print(f"  Types: {' -> '.join([op.type for op in intent.operations])}")

        assert len(all_intents) == 4
        assert all(intent.id.startswith("intent_") for intent in all_intents)
        assert all(len(intent.operations) > 0 for intent in all_intents)

        print("\n" + "="*60)
        print(f"✅ Successfully generated {len(all_intents)} intents from User Operations")
        print("="*60)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
