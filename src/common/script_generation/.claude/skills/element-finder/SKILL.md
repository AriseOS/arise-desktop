---
name: element-finder
description: Generate find_element.py scripts to locate interactive elements for browser operations.
---

# Element Finder

## Goal

Generate `find_element.py` that finds the target element and returns its `interactive_index`.

**CRITICAL**: Only elements with `interactive_index` can be clicked or filled.

## Input Files

- `task.json` - Task description with xpath hints
- `dom_data.json` - Page DOM as nested JSON dictionary

## Element Tools

Use the provided tools in `tools/element_tools.py` to find elements:

```bash
# Find element by xpath, check if it has interactive_index
python .claude/skills/element-finder/tools/element_tools.py find "//*[@id='app']/button[1]"

# Search by text keyword (also searches aria-label, placeholder)
python .claude/skills/element-finder/tools/element_tools.py search "New mail"
python .claude/skills/element-finder/tools/element_tools.py search "Submit"

# List all interactive elements in a container
python .claude/skills/element-finder/tools/element_tools.py list "//*[@id='app']/div[2]"

# Search by specific attribute
python .claude/skills/element-finder/tools/element_tools.py attr "aria-label" "Send message"
python .claude/skills/element-finder/tools/element_tools.py attr "class" "btn-primary"
python .claude/skills/element-finder/tools/element_tools.py attr "placeholder" "Enter email"

# Analyze xpath hint from recording, find best match
python .claude/skills/element-finder/tools/element_tools.py hint "//*[@id='root']/header/button[2]"

# Print element structure
python .claude/skills/element-finder/tools/element_tools.py print "//*[@id='app']/div[1]" 2
```

## Workflow

### Step 1: Read task.json

```bash
cat task.json
```

Identify:
- `task` - What action to perform ("Click the New mail button")
- `xpath_hints` - Reference xpath from user's recording
- `text` - Text to input (for fill operations)

### Step 2: Analyze xpath hint

If xpath_hints is provided, use the hint command:

```bash
python .claude/skills/element-finder/tools/element_tools.py hint "<xpath_from_hints>"
```

This will:
1. Check if exact xpath exists and is interactive
2. Find alternatives if not
3. Return best matching `interactive_index`

### Step 3: Search if hint fails

If hint doesn't find the element, search by keywords from the task:

```bash
# Extract keywords from task description
# e.g., task = "Click the 'New mail' button"

python .claude/skills/element-finder/tools/element_tools.py search "New mail"
python .claude/skills/element-finder/tools/element_tools.py search "mail"
```

### Step 4: Write find_element.py

Create `find_element.py` based on what you found:

```python
import json
from typing import Dict

def find_target_element(dom_dict: dict) -> dict:
    """Find target element and return its interactive_index"""

    def search_recursive(node: dict, condition_fn):
        if condition_fn(node):
            return node
        for child in node.get('children', []):
            result = search_recursive(child, condition_fn)
            if result:
                return result
        return None

    # Search strategy based on what tools found
    def condition(n):
        text = (n.get('text', '') or '').lower()
        has_index = n.get('interactive_index') is not None
        # Match by text content
        return 'new mail' in text and has_index

    element = search_recursive(dom_dict, condition)

    if not element:
        return {"success": False, "error": "Target element not found"}

    if element.get('interactive_index') is None:
        return {"success": False, "error": "Element not interactive"}

    return {
        "success": True,
        "interactive_index": element['interactive_index'],
        "element_info": {
            "tag": element.get("tag"),
            "text": (element.get("text") or "")[:100],
            "xpath": element.get("xpath"),
            "class": element.get("class")
        }
    }
```

### Step 5: Test

```bash
python test_operation.py
```

Must print "SUCCESS" and exit with code 0.

## Search Strategies

### By Text Content
```python
def condition(n):
    text = (n.get('text', '') or '').lower()
    return 'submit' in text and n.get('interactive_index') is not None
```

### By aria-label
```python
def condition(n):
    aria = (n.get('aria-label', '') or '').lower()
    return 'new message' in aria and n.get('interactive_index') is not None
```

### By Class
```python
def condition(n):
    cls = (n.get('class', '') or '').lower()
    return 'editorclass' in cls and n.get('interactive_index') is not None
```

### By Placeholder (for input fields)
```python
def condition(n):
    ph = (n.get('placeholder', '') or '').lower()
    return 'email' in ph and n.get('interactive_index') is not None
```

## Multi-language Support

Handle both Chinese and English:
```python
keywords = ['new mail', '新邮件', 'compose', '写邮件']
def condition(n):
    text = (n.get('text', '') or '').lower()
    return any(kw in text for kw in keywords) and n.get('interactive_index') is not None
```

## Common Issues

### Element found but not interactive
- The element exists but has no `interactive_index`
- Solution: Look for parent or child that IS interactive
- Use: `python element_tools.py list "<parent_xpath>"`

### xpath hint doesn't match
- Page structure may have changed
- Solution: Use `search` or `attr` to find by content instead of xpath
- Use: `python element_tools.py search "<button_text>"`

### Multiple matches
- Multiple elements match the criteria
- Solution: Add more specific conditions (combine text + class + aria-label)

## Fallback: grep search

If tools don't find what you need:

```bash
# Search by text content
grep -i "new mail" dom_data.json | head -20

# Search by aria-label
grep -i "aria-label" dom_data.json | head -20

# Search for interactive elements
grep -i "interactive_index" dom_data.json | head -20
```
