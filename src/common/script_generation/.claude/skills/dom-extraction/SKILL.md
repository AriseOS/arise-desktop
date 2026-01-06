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

Tools are available at `tools/dom_tools.py`. All commands output reusable code snippets.

### Quick Reference

```bash
# Extract list data - directly use xpath_hint, auto-finds container
python dom_tools.py container "<xpath_hint>" --fields "name:text,url:href"

# Find single/multiple elements by xpath
python dom_tools.py find "<xpath>" --field text
python dom_tools.py find '{"name": "<xpath1>", "price": "<xpath2>"}' --field text

# Search when xpath hints fail
python dom_tools.py search --text "Product" --tag a
python dom_tools.py search --class "product-item"

# Analyze container structure
python dom_tools.py analyze "<xpath>"
```

## Workflow

### Step 1: Read Requirements

```bash
cat requirement.json
```

Identify:
- `user_description` - What user wants ("all products", "the title")
- `output_format` - Expected fields
- `xpath_hints` - Reference xpaths from user's demo

### Step 2: Determine Extraction Type

**List Extraction** - "all", "every", "list", "each" → Use `container` command
**Multi-field Extraction** - Multiple single fields → Use `find` with JSON
**Single-field Extraction** - One field → Use `find` with xpath

### Step 3: Verify and Extract

#### 3a. List Extraction

When extracting a list (products, links, items), use the xpath_hint directly:

```bash
# xpath_hint points to ONE item like: //*[@id='app']/div[4]/div/a[1]
# container command AUTO-FINDS the parent container with multiple children

python dom_tools.py container "//*[@id='app']/div[4]/div/a[1]" --fields "name:text,url:href"
```

Output:
```
  (Auto-adjusted 1 level(s) up: .../a[1] → .../div)
✓ Built virtual container: //*[@id='app']/div[4]/div
  (Found 20 child elements)

Extracted 20 items:
  [1] {"name": "Product A", "url": "/products/1"}
  ...

# Code snippet:
from dom_utils import extract_list
results = extract_list(dom_dict, "//*[@id='app']/div[4]/div", {"name": "text", "url": "href"})
```

**Field Mapping Syntax:**
- `name:text` - Extract text from item (searches recursively)
- `url:href` - Extract href from item
- `title:text:h4` - Extract text from `<h4>` descendant
- `title:text:.title` - Extract text from descendant with class "title"

#### 3b. Multi-field Extraction

When extracting multiple single fields (product details page):

```bash
python dom_tools.py find '{"product_name": "//*[@id=\"app\"]/h1", "price": "//*[@id=\"app\"]/span"}' --field text
```

#### 3c. Single-field Extraction

When extracting just one field:

```bash
python dom_tools.py find "//*[@id='app']/h1" --field text
```

### Step 4: Handle Failures with Search

If xpath hints don't find elements, use `search`:

```bash
# Search by visible text
python dom_tools.py search --text "Product Name"

# Search by class pattern
python dom_tools.py search --class "product-item"

# Combine filters
python dom_tools.py search --text "Buy" --tag button
```

### Step 5: Write Extraction Script

Use the code snippets from tool output:

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
    # Use code snippet from container command
    results = extract_list(dom_dict, "<container_xpath>", {"name": "text", "url": "href"})

    # Make URLs absolute
    for item in results:
        if 'url' in item:
            item['url'] = make_absolute(item['url'])

    return results
```

**IMPORTANT**: Use simple `from dom_tools import ...`. Do NOT use `__file__` or `sys.path` manipulation.

### Step 6: Test

```bash
python extraction_script.py
```

Verify:
- For lists: Item count matches container analysis
- For single/multi: Values are not empty
- URLs are absolute

## Container Auto-Find

The `container` command automatically searches UP the DOM tree to find a container with multiple children:

```bash
# Given xpath_hint pointing to a single item:
python dom_tools.py container "//*[@id='app']/div/a[1]"

# Output shows it auto-adjusted:
#   (Auto-adjusted 1 level(s) up: .../a[1] → .../div)
# ✓ Built virtual container with 20 children
```

This means you can directly use xpath_hints without manually removing the `[1]` index.

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

## Rules

1. **Use dom_utils functions** - Import and use `extract_list`, `extract_single`, `extract_multi`. Don't write custom xpath search functions.

2. **URLs MUST be absolute** - Always convert relative URLs using `urljoin(PAGE_URL, url)`.

3. **Respect container boundaries** - Only extract from the specific container indicated by xpath, not the entire DOM.

4. **Handle missing fields gracefully** - The extract functions already handle missing fields.

## Example: List Extraction

Given requirement with xpath_hint `//*[@id='app']/main/div[4]/div/a[1]`:

```bash
# Use xpath_hint directly - container auto-finds the parent
python dom_tools.py container "//*[@id='app']/main/div[4]/div/a[1]" --fields "name:text,url:href"

# Output:
#   (Auto-adjusted 1 level(s) up)
# ✓ Built virtual container: //*[@id='app']/main/div[4]/div
# Extracted 20 items:
#   [1] {"name": "Product A", "url": "/products/1"}
#   ...
# Code snippet:
# results = extract_list(dom_dict, "...", {...})

# Use the snippet in extraction_script.py
```

## Example: Selector Syntax

When list items have nested structure, use selectors to extract from specific descendants:

```bash
# Item structure: <a href="..."><div><h4>Name</h4><p>Desc</p></div></a>
# Extract name from h4, url from the a itself

python dom_tools.py container "//*[@id='app']/div/a[1]" --fields "name:text:h4,url:href:a"

# Extracted 20 items:
#   [1] {"name": "DeepSeek", "url": "/products/deepseek"}
```

Selector syntax: `output_name:field:selector`
- `name:text:h4` - Find `<h4>` in item tree, extract its text
- `url:href:a` - If item is `<a>`, extract href from it
- `title:text:.title` - Find element with class "title", extract text

## Fallback: grep search

If tools don't find what you need, use grep to explore the DOM:

```bash
# Search by text content
grep -i "product" dom_data.json | head -20

# Search by class
grep -i "product-item" dom_data.json | head -20

# Search by href
grep -i "href" dom_data.json | head -20

# Search for specific xpath pattern
grep -i "div\[4\]/div/a" dom_data.json | head -20
```
