"""Script Templates for Claude Agent SDK

These templates are used by Claude Agent to generate scripts.
They provide structure and helper functions that Claude fills in.
"""

# =============================================================================
# Browser Script Templates
# =============================================================================

BROWSER_TEST_OPERATION = '''#!/usr/bin/env python3
"""Test script - Validates find_element.py with xpath parameter

This script:
1. Loads DOM data from dom_data.json
2. Loads xpath from task.json
3. Injects analyze_xpath_hint for testing
4. Calls find_target_element(dom_dict, xpath)
5. Reports success or failure

Usage: python test_operation.py
Exit code: 0 = success, 1 = failure
"""
import json
import sys

def test():
    """Test find_element.py and validate result"""
    # Load DOM (wrapped format: {"url": ..., "dom": {...}})
    try:
        with open("dom_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        if "dom" not in data:
            print("FAILED: Invalid DOM format - missing 'dom' key")
            return False
        dom_dict = data["dom"]
    except Exception as e:
        print(f"FAILED: Cannot load dom_data.json: {e}")
        return False

    # Load task to get sample xpath
    try:
        with open("task.json", "r", encoding="utf-8") as f:
            task_info = json.load(f)
    except Exception as e:
        print(f"FAILED: Cannot load task.json: {e}")
        return False

    # Get sample xpath from xpath_hints
    xpath_hints = task_info.get("xpath_hints", {})
    sample_xpath = list(xpath_hints.values())[0] if xpath_hints else ""

    if not sample_xpath:
        print("WARNING: No xpath_hints in task.json, using empty xpath")

    # Inject analyze_xpath_hint for testing
    # (In production, this is injected by browser_agent's exec environment)
    try:
        sys.path.insert(0, ".claude/skills/element-finder/tools")
        from element_tools import analyze_xpath_hint
    except ImportError as e:
        print(f"FAILED: Cannot import element_tools: {e}")
        return False

    # Import find_element and inject the function
    try:
        import find_element
        find_element.analyze_xpath_hint = analyze_xpath_hint
        from find_element import find_target_element
    except ImportError as e:
        print(f"FAILED: Cannot import find_element.py: {e}")
        return False
    except SyntaxError as e:
        print(f"FAILED: Syntax error in find_element.py: {e}")
        return False

    # Execute find_target_element with xpath parameter
    try:
        result = find_target_element(dom_dict, sample_xpath)
    except TypeError as e:
        # Old signature without xpath parameter
        if "positional argument" in str(e):
            print(f"FAILED: find_target_element() must accept (dom_dict, xpath) parameters")
            return False
        raise
    except Exception as e:
        print(f"FAILED: find_target_element() raised exception: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Validate result structure
    if not isinstance(result, dict):
        print(f"FAILED: find_target_element() must return dict, got {type(result)}")
        return False

    if not result.get("success"):
        error = result.get("error", "Unknown error")
        # "fallback required" is acceptable - means hint didn't find element
        if "fallback" in error.lower():
            print(f"INFO: Script returned fallback required (acceptable)")
            print(f"  This means hint could not find element, LLM fallback will be used")
            return True
        print(f"FAILED: find_target_element() returned failure: {error}")
        return False

    # Validate interactive_index
    interactive_index = result.get("interactive_index")
    if interactive_index is None:
        print("FAILED: Result missing 'interactive_index'")
        return False

    if not isinstance(interactive_index, int):
        print(f"FAILED: interactive_index must be int, got {type(interactive_index)}")
        return False

    # Success!
    element_info = result.get("element_info", {})
    print(f"SUCCESS: Found element")
    print(f"  interactive_index: {interactive_index}")
    print(f"  tag: {element_info.get('tag', 'N/A')}")
    print(f"  text: {element_info.get('text', 'N/A')[:50] if element_info.get('text') else 'N/A'}")
    print(f"  xpath: {sample_xpath[:50]}...")
    return True

if __name__ == "__main__":
    success = test()
    sys.exit(0 if success else 1)
'''


BROWSER_FIND_ELEMENT_TEMPLATE = '''#!/usr/bin/env python3
"""Find target element using hint-based search

This script uses analyze_xpath_hint to find the target element.
The analyze_xpath_hint function is injected by the execution environment.

IMPORTANT:
- Do NOT import analyze_xpath_hint manually - it's injected by browser_agent
- The function signature is: find_target_element(dom_dict, xpath)
- xpath is passed at runtime and may differ each call (e.g., in foreach loops)
"""

def find_target_element(dom_dict: dict, xpath: str) -> dict:
    """Find target element using hint method

    Args:
        dom_dict: DOM dictionary
        xpath: Runtime xpath from xpath_hints (may change each iteration)

    Returns:
        dict with:
        - success: bool
        - interactive_index: int (element index for click/fill operations)
        - element_info: dict with tag, text, xpath, class (for debugging)
        - error: str (if success is False)
    """
    if not xpath:
        return {"success": False, "error": "No xpath provided"}

    # analyze_xpath_hint is injected by browser_agent's exec environment
    # It searches DOM using xpath hint, auto-searches parent levels if needed
    result = analyze_xpath_hint(dom_dict, xpath)

    # Check if hint found an interactive element
    match = result.get('interactive_match')
    if match and match.get('interactive_index') is not None:
        return {
            "success": True,
            "interactive_index": match['interactive_index'],
            "element_info": {
                "tag": match.get("tag"),
                "text": match.get("text", "")[:100],
                "xpath": match.get("xpath"),
                "class": match.get("class")
            }
        }

    # hint could not find element - return error to trigger LLM fallback
    return {
        "success": False,
        "error": "Cannot find interactive element via hint, fallback required",
        "hint_result": result  # Include analysis result for debugging
    }
'''


# =============================================================================
# Claude Agent Prompts
# =============================================================================

BROWSER_AGENT_PROMPT = """# Browser Element Finder Task (Simplified)

## Your Working Directory
You are working in: `{working_dir}`

## Your Task
Create `find_element.py` that uses `analyze_xpath_hint` to find target elements.
{task_details}

## Simplified Workflow

This task uses a **hint-based approach**. You don't need to write complex search logic.

### Step 1: Test the hint command

```bash
python .claude/skills/element-finder/tools/element_tools.py hint "<xpath_from_task>"
```

Check if it finds an interactive element (has `interactive_index`).

### Step 2: Create find_element.py

**If hint FINDS an interactive element**, copy the template directly:

```bash
cp find_element_template.py find_element.py
```

The template already uses `analyze_xpath_hint` - no modifications needed!

**If hint FAILS to find an element**, the template will return a fallback error,
which is acceptable. The system will use LLM fallback mode.

### Step 3: Test

```bash
python test_operation.py
```

Both "SUCCESS" and "fallback required" are acceptable outcomes.

## Key Points

1. **Do NOT write complex search logic** - use the template as-is
2. **analyze_xpath_hint is injected** - don't import it manually
3. **New function signature**: `find_target_element(dom_dict, xpath)`
4. **xpath is runtime parameter** - same script works with different xpath values

## Template Content (find_element_template.py)

The template uses `analyze_xpath_hint(dom_dict, xpath)` which:
- Searches for exact xpath match
- Auto-searches up to 5 parent levels if not found
- Returns the best matching interactive element

## Success Criteria

`python test_operation.py` must exit with code 0.
- "SUCCESS: Found element" = hint found the element
- "INFO: Script returned fallback required" = hint failed, LLM fallback will be used

Both are valid outcomes.
"""


SCRAPER_AGENT_PROMPT = """# Data Extraction Script Generation

Generate `extraction_script.py` to extract data from the webpage DOM.

## Task Context

- **Working Directory**: `{working_dir}`
- **Page URL**: `{page_url}`

## Extraction Requirements

**User Description**: {user_description}

**Output Format (fields to extract)**:
{fields_description}
{sample_description}
{xpath_hints_description}

## Input Files

- `dom_data.json` - Page DOM as nested JSON dictionary

## DOM Tools

`dom_tools.py` is available in the current directory.

| Command | Purpose | Output |
|---------|---------|--------|
| `find <xpath>` or `find <json>` | Multi-field extraction | value + children + siblings |
| `container <xpath> --fields ...` | List extraction | List items array |
| `search --text/--class` | Search elements | Matching elements list |

**IMPORTANT**: Read `.claude/skills/dom-extraction/SKILL.md` for detailed workflow.

## Workflow

### Step 1: Determine Extraction Type
- **List** ("all", "every", "list") → Use `container` command
- **Multi-field** (detail page) → Use `find` with JSON

### Step 2: Execute Based on Type

**For List Extraction (one step):**
```bash
python dom_tools.py container "//*[@id='app']/div[4]/div/a[1]" --fields "name:text,url:href"
```
Container auto-finds parent. Use the output code snippet directly.

**For Multi-field Extraction:**
```bash
python dom_tools.py find '{{"name": "<xpath1>", "rating": "<xpath2>", "description": "<xpath3>"}}'
```

The `find` command returns for each xpath:
- **value**: The extracted text/href
- **children**: If container, shows all child elements with xpath + text
- **siblings**: Shows sibling elements

**Analyze the output:**
- If xpath is a **container** (shows children) → use the child xpath for specific value
- If xpath has **siblings** → decide if content needs merging
- If xpath **not found** → use `search` command

### Step 3: If xpath fails, search
```bash
python dom_tools.py search --text "9.0"
python dom_tools.py search --class "rating"
```

### Step 4: Write Script
Use corrected xpaths based on `find` output:
```python
from dom_tools import extract_list, extract_single, extract_multi
```

### Step 5: Test
```bash
python extraction_script.py
```

## CRITICAL Rules

1. **Use dom_tools functions** - Don't write custom xpath search logic.

2. **Trust `find` output** - If it shows children, use the child xpath. If it shows siblings, consider merging.

3. **URLs MUST be absolute** - Use `make_absolute(url, page_url)` to convert relative URLs.

4. **Respect xpath indices** - `div[4]` means the 4th div. Extract from that specific container.

5. **page_url parameter** - The function receives `page_url` as second parameter. Use it for URL conversion or return it directly if needed.

6. **Handle None values** - `extract_single` and `extract_multi` return `None` when xpath doesn't match. ALWAYS use `(value or "")` before calling `.strip()` or other string methods:
   ```python
   # WRONG - will crash if value is None
   name = data.get("name", "").strip()

   # CORRECT - handles None safely
   name = (data.get("name") or "").strip()
   ```

## Required Script Format

Your `extraction_script.py` MUST follow this exact structure:

```python
import json
from typing import Dict, List
from urllib.parse import urljoin

from dom_tools import extract_list, extract_single, extract_multi


def make_absolute(url: str, page_url: str) -> str:
    \"\"\"Convert relative URL to absolute URL\"\"\"
    if not url or url.startswith(('http://', 'https://')):
        return url
    return urljoin(page_url, url)


def extract_data_from_page(dom_dict: Dict, page_url: str = "") -> List[Dict]:
    \"\"\"Extract data from DOM dictionary.

    Args:
        dom_dict: The page DOM as a nested dictionary
        page_url: Current page URL (use for make_absolute or return directly)

    Returns:
        List of extracted data dictionaries
    \"\"\"
    # YOUR EXTRACTION LOGIC HERE
    # Use extract_list, extract_single, or extract_multi from dom_tools
    results = []

    # Make URLs absolute using page_url parameter
    for item in results:
        if 'url' in item:
            item['url'] = make_absolute(item['url'], page_url)

    return results


# Main entry point - reads dom_data.json and calls extract function
if __name__ == "__main__":
    with open("dom_data.json", "r") as f:
        data = json.load(f)
    # DOM files use wrapped format: {{"url": ..., "dom": {{...}}}}
    if "dom" not in data:
        raise ValueError("Invalid DOM format: missing 'dom' key. Expected wrapped format.")
    page_url = data.get("url", "")
    results = extract_data_from_page(data["dom"], page_url)
    print(json.dumps(results, indent=2, ensure_ascii=False))
```

**IMPORTANT**:
- `extract_data_from_page(dom_dict, page_url)` receives both DOM and current page URL
- Use `page_url` parameter to convert relative URLs via `make_absolute(url, page_url)`
- You can also return `page_url` directly if the user wants the current page URL as output
- File reading (`dom_data.json`) only happens in `if __name__ == "__main__":` block for testing
- DOM files use wrapped format: `{{"url": "...", "dom": {{...}}}}`
"""
