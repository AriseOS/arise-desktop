"""
Test script for ExcelToolkit tools.

Verifies all Excel operations work correctly:
- create_workbook
- write_excel
- read_excel
- update_cell
- get_sheet_names
- export_to_csv

Also tests the proxy compatibility fixes:
- Tool name sanitization (_sanitize_tool_name)
- JSON string auto-deserialization for list/dict params

Usage:
    source .venv/bin/activate
    python scripts/test_excel_toolkit.py
"""

import json
import os
import sys
import shutil
import tempfile
import inspect
import re

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_excel_toolkit():
    """Test all ExcelToolkit tools."""
    from src.clients.desktop_app.ami_daemon.base_agent.tools.toolkits import ExcelToolkit

    work_dir = tempfile.mkdtemp(prefix="test_excel_")
    print(f"Working directory: {work_dir}")

    try:
        toolkit = ExcelToolkit(working_directory=work_dir)
        tools = toolkit.get_tools()
        tool_names = [t.get_function_name() for t in tools]
        print(f"\nAvailable tools: {tool_names}")

        expected_tools = [
            "create_workbook", "read_excel", "write_excel",
            "update_cell", "get_sheet_names", "export_to_csv"
        ]
        for name in expected_tools:
            assert name in tool_names, f"Missing tool: {name}"
        print("  All expected tools present")

        # 1. create_workbook
        print("\n--- Test: create_workbook ---")
        result = toolkit.create_workbook(
            filename="test_report.xlsx",
            sheets=["Data", "Summary"]
        )
        print(f"  Result: {result}")
        assert "successfully" in result.lower(), f"create_workbook failed: {result}"

        # 2. get_sheet_names
        print("\n--- Test: get_sheet_names ---")
        sheets = toolkit.get_sheet_names("test_report.xlsx")
        print(f"  Sheets: {sheets}")
        assert sheets == ["Data", "Summary"], f"Unexpected sheets: {sheets}"

        # 3. write_excel
        print("\n--- Test: write_excel ---")
        data = [
            ["Product A", 100, 29.99],
            ["Product B", 250, 49.99],
            ["Product C", 75, 14.99],
        ]
        headers = ["Product", "Quantity", "Price"]
        result = toolkit.write_excel(
            filepath="test_report.xlsx",
            data=data,
            sheet_name="Data",
            headers=headers,
        )
        print(f"  Result: {result}")
        assert "successfully" in result.lower(), f"write_excel failed: {result}"

        # 4. read_excel
        print("\n--- Test: read_excel ---")
        read_data = toolkit.read_excel("test_report.xlsx", sheet_name="Data")
        print(f"  Read {len(read_data)} rows")
        assert len(read_data) == 4, f"Expected 4 rows (header + 3 data), got {len(read_data)}"
        assert read_data[0] == ["Product", "Quantity", "Price"], f"Header mismatch: {read_data[0]}"
        assert read_data[1] == ["Product A", 100, 29.99], f"Row 1 mismatch: {read_data[1]}"

        # 5. update_cell
        print("\n--- Test: update_cell ---")
        result = toolkit.update_cell(
            filepath="test_report.xlsx",
            row=2, col=2,
            value=150,
            sheet_name="Data"
        )
        print(f"  Result: {result}")
        assert "successfully" in result.lower(), f"update_cell failed: {result}"

        # Verify the update
        read_data = toolkit.read_excel("test_report.xlsx", sheet_name="Data")
        assert read_data[1][1] == 150, f"Cell not updated: {read_data[1][1]}"
        print("  Cell value verified: 150")

        # 6. export_to_csv
        print("\n--- Test: export_to_csv ---")
        result = toolkit.export_to_csv(
            filepath="test_report.xlsx",
            sheet_name="Data"
        )
        print(f"  Result: {result}")
        assert "successfully" in result.lower(), f"export_to_csv failed: {result}"

        # Verify CSV
        csv_path = os.path.join(work_dir, "test_report.csv")
        assert os.path.exists(csv_path), f"CSV file not found: {csv_path}"
        with open(csv_path) as f:
            lines = f.readlines()
        print(f"  CSV has {len(lines)} lines")
        assert len(lines) == 4, f"Expected 4 CSV lines, got {len(lines)}"

        print("\n=== All ExcelToolkit tests PASSED ===")

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def test_tool_name_sanitization():
    """Test _sanitize_tool_name handles proxy-injected tags."""
    from src.clients.desktop_app.ami_daemon.base_agent.core.ami_agent import AMIAgent

    test_cases = [
        ("<tool_call>write_excel", "write_excel"),
        ("<tool_call>create_workbook", "create_workbook"),
        ("write_excel", "write_excel"),  # No change needed
        ("<function>shell_exec", "shell_exec"),
        ("<tool_call><function>foo", "foo"),  # Multiple tags
        ("normal_tool", "normal_tool"),
    ]

    print("\n--- Test: _sanitize_tool_name ---")
    for raw, expected in test_cases:
        result = AMIAgent._sanitize_tool_name(raw)
        assert result == expected, f"sanitize({raw!r}) = {result!r}, expected {expected!r}"
        print(f"  {raw!r:40s} -> {result!r}")

    print("  All sanitization tests PASSED")


def test_json_string_deserialization():
    """Test _is_collection_type for auto-deserializing JSON string params."""
    from src.clients.desktop_app.ami_daemon.base_agent.core.ami_agent import _is_collection_type
    from typing import List, Dict, Optional, Any, Union

    print("\n--- Test: _is_collection_type ---")
    test_cases = [
        (List[str], True),
        (List[List[Any]], True),
        (Dict[str, Any], True),
        (list, True),
        (dict, True),
        (Optional[List[str]], True),
        (str, False),
        (int, False),
        (Optional[str], False),
        (bool, False),
    ]

    for annotation, expected in test_cases:
        result = _is_collection_type(annotation)
        status = "OK" if result == expected else "FAIL"
        print(f"  [{status}] _is_collection_type({annotation}) = {result}")
        assert result == expected, f"Expected {expected} for {annotation}"

    print("  All type check tests PASSED")

    # Test actual JSON deserialization scenario
    print("\n--- Test: JSON string param deserialization scenario ---")

    # Simulate what write_excel's signature looks like
    from src.clients.desktop_app.ami_daemon.base_agent.tools.toolkits import ExcelToolkit
    sig = inspect.signature(ExcelToolkit.write_excel)
    data_param = sig.parameters.get("data")
    headers_param = sig.parameters.get("headers")

    print(f"  write_excel 'data' annotation: {data_param.annotation}")
    print(f"  write_excel 'headers' annotation: {headers_param.annotation}")

    assert _is_collection_type(data_param.annotation), "data should be collection type"
    assert _is_collection_type(headers_param.annotation), "headers should be collection type"

    # Simulate the proxy scenario: arrays passed as JSON strings
    proxy_input = {
        "filepath": "test.xlsx",
        "data": '[["a", "b"], ["c", "d"]]',
        "headers": '["Col1", "Col2"]',
        "sheet_name": "Sheet1",
    }

    # Deserialize as the agent would
    for param_name, param in sig.parameters.items():
        if param_name in proxy_input and isinstance(proxy_input[param_name], str):
            annotation = param.annotation
            if annotation != inspect.Parameter.empty and _is_collection_type(annotation):
                try:
                    parsed = json.loads(proxy_input[param_name])
                    if isinstance(parsed, (list, dict)):
                        proxy_input[param_name] = parsed
                except (json.JSONDecodeError, TypeError):
                    pass

    assert proxy_input["data"] == [["a", "b"], ["c", "d"]], f"data not deserialized: {proxy_input['data']}"
    assert proxy_input["headers"] == ["Col1", "Col2"], f"headers not deserialized: {proxy_input['headers']}"
    assert proxy_input["filepath"] == "test.xlsx", "filepath should remain string"
    assert proxy_input["sheet_name"] == "Sheet1", "sheet_name should remain string"

    print("  JSON string deserialization scenario PASSED")


if __name__ == "__main__":
    print("=" * 60)
    print("ExcelToolkit & Proxy Compatibility Tests")
    print("=" * 60)

    test_excel_toolkit()
    test_tool_name_sanitization()
    test_json_string_deserialization()

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
