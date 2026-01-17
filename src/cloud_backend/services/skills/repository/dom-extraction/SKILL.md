---
name: dom-extraction
description: Generate Python extraction scripts from DOM data. Use when you need to extract data from dom_data.json based on user requirements and xpath hints.
---

# DOM Data Extraction

## Goal

Generate a Python script (`extraction_script.py`) that extracts data from a nested DOM dictionary.

## Input Files

- `requirement.json` - Contains `user_description`, `output_format`, `xpath_hints`
- `dom_data.json` - Page DOM as nested JSON dictionary

## DOM Tools

Tools are available at `dom_tools.py` in the current directory.

### Commands

| Command | Purpose | Output |
|---------|---------|--------|
| `find <xpath>` or `find <json>` | Multi-field extraction | value + children + siblings for each xpath |
| `container <xpath> --fields ...` | List extraction | List items array |
| `search --text/--class` | Search elements | Matching elements list |

### Quick Reference

```bash
# Multi-field extraction - shows value + children + siblings
python dom_tools.py find '{"name": "<xpath1>", "price": "<xpath2>"}'

# Single element discovery
python dom_tools.py find "<xpath>"

# List extraction - auto-finds container
python dom_tools.py container "<xpath_hint>" --fields "name:text,url:href"

# Search when xpath hints fail
python dom_tools.py search --text "Product"
python dom_tools.py search --class "product-item"
```

## Workflow by Task Type

### Task 1: List Extraction
> "Extract all products", "all links", "every item"

**One step - use `container` command:**

```bash
# xpath_hint points to ONE item like: //*[@id='app']/div[4]/div/a[1]
# container command AUTO-FINDS the parent container
python dom_tools.py container "//*[@id='app']/div[4]/div/a[1]" --fields "name:text,url:href"
```

Output shows extracted items and code snippet. Use the snippet directly.

---

### Task 2: Multi-field Extraction (Detail Page)
> "Extract product name, price, rating, description"

**Step 1: Use `find` with all xpath_hints**

```bash
python dom_tools.py find '{
  "name": "//*/.../h2",
  "rating": "//*/.../div[1]",
  "description": "//*/.../p[1]"
}'
```

**Step 2: Analyze the output**

The `find` command shows for each xpath:
- **value**: The extracted text/href
- **children**: If it's a container, shows all child elements with data
- **siblings**: Shows sibling elements (for multi-paragraph content)

Example output:
```
============================================================
Field: rating
XPath: //*/.../div[1]
  tag: div
  text: "总评分9.0好评如潮36 猹评"

  ⚠ Container detected - showing children with data:
    [1] .../div/div/div[1]/span[1]
        tag: span, text: "9.0"
    [2] .../div/div/div[1]/span[2]
        tag: span, text: "好评如潮"
    [3] .../div/div/div[2]
        tag: div, text: "36 猹评"

  → To extract specific value, use child xpath like:
     //*/.../div[1]/div/div/div[1]/span[1]

============================================================
Field: description
XPath: //*/.../p[1]
  tag: p
  text: "DeepSeek 是深度求索人工智能..."

  Siblings (2):
    [1] .../p[2]
        tag: p, text: "DeepSeek-R1 作为最新推理模型..."
    [2] .../p[3]
        tag: p, text: "主要功能包括..."
```

**Step 3: Decide based on output**

- **rating** is a container → use child xpath `.../span[1]` to get "9.0"
- **description** has siblings → may need to merge p[1] + p[2] + p[3]

**Step 4: Generate script with corrected xpaths**

---

### Task 3: xpath_hints Not Found

```bash
# Step 1: find returns "not found"
python dom_tools.py find '{"rating": "//*/.../div[999]"}'
# Output: ✗ rating: Not found

# Step 2: Search by text or class
python dom_tools.py search --text "9.0"
python dom_tools.py search --class "rating"

# Step 3: Use found xpath
python dom_tools.py find '{"rating": "//*/.../found-xpath"}'
```

## Decision Tree

```
Start
  │
  ├─ Task is "list extraction"? (all/every/list)
  │    └─ Yes → container command → Done
  │
  └─ Task is "multi-field extraction"?
       │
       └─ Step 1: find with all xpath_hints
            │
            ├─ All are leaf nodes → Generate script → Done
            │
            ├─ Some are containers → Use child xpath from output
            │
            ├─ Some have siblings → Decide if merge needed
            │
            └─ Some not found → search → find again
```

## Writing the Extraction Script

Use code snippets from tool output:

```python
import json
from typing import Dict, List
from urllib.parse import urljoin

from dom_tools import extract_list, extract_single, extract_multi

PAGE_URL = "https://example.com/page"

def make_absolute(url: str) -> str:
    if not url or url.startswith(('http://', 'https://')):
        return url
    return urljoin(PAGE_URL, url)

def extract_data_from_page(dom_dict: Dict) -> List[Dict]:
    # For list extraction:
    results = extract_list(dom_dict, "<container_xpath>", {"name": "text", "url": "href"})

    # OR for multi-field extraction:
    result = extract_multi(dom_dict, {
        "name": "<xpath1>",
        "price": "<xpath2>"
    }, "text")

    # Make URLs absolute
    for item in results:
        if 'url' in item:
            item['url'] = make_absolute(item['url'])

    return results
```

**IMPORTANT**:
1. Use simple `from dom_tools import ...`. Do NOT use `__file__` or `sys.path` manipulation.
2. Do NOT read `dom_data.json` at module level. Put file reading inside `if __name__ == "__main__":` block for testing only.
3. The `extract_data_from_page(dom_dict)` function receives the DOM as a parameter - it should NOT read from files.

**Script structure:**
```python
# Imports and constants at top
from dom_tools import extract_list, extract_single, extract_multi

# Main extraction function - receives DOM as parameter
def extract_data_from_page(dom_dict: Dict) -> List[Dict]:
    # extraction logic here
    return results

# Testing code - only runs when script is executed directly
if __name__ == "__main__":
    with open("dom_data.json") as f:
        data = json.load(f)
    # DOM files use wrapped format: {"url": ..., "dom": {...}}
    dom = data.get("dom", data)
    print(json.dumps(extract_data_from_page(dom), indent=2))
```

## Field Mapping Syntax (for container command)

**Format**: `output_name:field_type` or `output_name:field_type:selector`

| Syntax | Meaning | Example |
|--------|---------|---------|
| `name:text` | Extract text from item itself | Gets direct text content |
| `url:href` | Extract href attribute | Gets link URL |
| `name:text:h4` | Extract text from `<h4>` child | When name is in nested `<h4>` tag |
| `name:text:.title` | Extract text from `.title` child | When name is in element with class "title" |

**Common issue**: If `name:text` returns empty but `url:href` works, the text is likely in a child element. Use selector syntax:

```bash
# Before (empty names):
python dom_tools.py container "<xpath>" --fields "name:text,url:href"
# Output: {"name": "", "url": "/products/1"} ← name is empty!

# After (with selector):
python dom_tools.py container "<xpath>" --fields "name:text:h4,url:href"
# Output: {"name": "Product Name", "url": "/products/1"} ← name from <h4> child
```

**When to use selector**:
- List item is `<a>` tag but name is in nested `<h4>`, `<span>`, or `<div>`
- xpath_hint points to a wrapper element, not the text element directly

## Rules

1. **Use dom_tools functions** - Import and use `extract_list`, `extract_single`, `extract_multi`. Don't write custom xpath search functions.

2. **URLs MUST be absolute** - Always convert relative URLs using `urljoin(PAGE_URL, url)`.

3. **Respect container boundaries** - Only extract from the specific container indicated by xpath.

4. **Trust the `find` output** - If it shows children, use the child xpath. If it shows siblings, consider merging.

5. **Handle None values** - `extract_single` and `extract_multi` return `None` when xpath doesn't match. Always use `(value or "")` before calling `.strip()` or other string methods:
   ```python
   # WRONG - crashes if value is None
   name = data.get("name", "").strip()

   # CORRECT - handles None safely
   name = (data.get("name") or "").strip()
   ```

## DOM Dictionary Format

```json
{
  "tag": "a",
  "class": "product-item group",
  "href": "/products/123",
  "xpath": "//*[@id='app']/div[2]/a[1]",
  "text": "Product Name",
  "children": [...]
}
```

Fields: `tag`, `class`, `href`, `src`, `text`, `xpath`, `children`
