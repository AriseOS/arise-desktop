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

Use the provided tools in `tools/dom_tools.py` to analyze DOM structure:

```bash
# Find element by exact xpath match (content elements only)
python .claude/skills/dom-extraction/tools/dom_tools.py find "//*[@id='app']/div[4]/div/a[1]"

# Build virtual container from children's xpath prefix
python .claude/skills/dom-extraction/tools/dom_tools.py container "//*[@id='app']/div[4]/div"

# Analyze container structure (supports virtual containers)
python .claude/skills/dom-extraction/tools/dom_tools.py analyze "//*[@id='app']/div[4]/div"

# List children with optional tag filter (supports virtual containers)
python .claude/skills/dom-extraction/tools/dom_tools.py children "//*[@id='app']/div[4]/div" a

# Print element structure with depth limit
python .claude/skills/dom-extraction/tools/dom_tools.py print "//*[@id='app']/div[4]/div/a[1]" 3

# List available fields (text, href, src) in container
python .claude/skills/dom-extraction/tools/dom_tools.py fields "//*[@id='app']/div[4]/div"

# Extract all values of a specific field from container
python .claude/skills/dom-extraction/tools/dom_tools.py extract "//*[@id='app']/div[4]/div" href
python .claude/skills/dom-extraction/tools/dom_tools.py extract "//*[@id='app']/div[4]/div" text
```

### Virtual Containers

Container elements (like `div` wrappers) often don't have their own `xpath` attribute in the DOM data - only content elements (with text, href, etc.) keep their xpath.

When `find` returns "not found", use `container`, `analyze`, or `children` commands which can build a **virtual container** by finding all child elements whose xpath starts with the given prefix.

### Fallback Strategy

If DOM tools don't find what you need, fallback to grep search:

```bash
# Search for text/class patterns
grep -n "product-name\|product-item" dom_data.json | head -20

# Find xpaths containing a pattern
grep -n '"xpath".*div\[4\]' dom_data.json | head -10
```

## Workflow

### Step 1: Read Requirements

```bash
cat requirement.json
```

Identify:
- `user_description` - What user wants to extract ("all products", "the title", etc.)
- `output_format` - Expected fields (`name`, `url`, `price`, etc.)
- `xpath_hints` - Reference xpath from user's demo click

### Step 2: Determine Extraction Type

**Scenario A: Extract List** - User says "all", "every", "list", "each"
**Scenario B: Extract Single** - User says "the title", "get price"

### Step 3: Locate Elements

#### 3a. Try xpath hint first

```bash
python .claude/skills/dom-extraction/tools/dom_tools.py find "<xpath_from_hints>"
```

If found, continue to Step 4.

#### 3b. Fallback: Search with grep

If xpath hint fails (element not found), search dom_data.json manually:

```bash
# Search by text content or class names from output_format
grep -n "product-name\|product-item\|title" dom_data.json | head -20

# Look for patterns that match expected data
grep -n "xpath.*div\[" dom_data.json | head -20
```

Find candidate xpaths, then verify each with the tool:

```bash
python .claude/skills/dom-extraction/tools/dom_tools.py find "<candidate_xpath>"
python .claude/skills/dom-extraction/tools/dom_tools.py print "<candidate_xpath>" 2
```

Repeat until you find the correct element.

### Step 4: Analyze Container (List Scenario)

For list extraction, find and analyze the container. Remove the index suffix `[1]` from the element xpath to get the container xpath:

```bash
# Element xpath: //*[@id='app']/div[4]/div/a[1]
# Container xpath: //*[@id='app']/div[4]/div

# Analyze container structure (automatically builds virtual container if needed)
python .claude/skills/dom-extraction/tools/dom_tools.py analyze "//*[@id='app']/div[4]/div"
```

If `analyze` returns "Container not found", use `container` command explicitly:

```bash
python .claude/skills/dom-extraction/tools/dom_tools.py container "//*[@id='app']/div[4]/div"
```

Check the output:
- `total_children` - Expected count of items
- `by_tag` - Which tag has the most items (usually `a` or `div`)
- `by_class` - Common class patterns
- `sample_child` - Structure of items to extract

**CRITICAL**: The xpath index (e.g., `div[4]`) specifies the EXACT container. Pages may have multiple similar sections. Extract ONLY from the specific container indicated.

### Step 5: Write Extraction Script

Create `extraction_script.py`:

```python
from typing import Dict, List

def extract_data_from_page(dom_dict: Dict) -> List[Dict]:
    """
    Extract data from DOM dictionary.

    Args:
        dom_dict: Page DOM as nested dictionary

    Returns:
        List of extracted data dictionaries
    """
    results = []

    # Your extraction logic here
    # - Navigate to container
    # - Iterate over children
    # - Extract fields from each item

    return results
```

### Step 6: Test and Validate

```bash
python extraction_script.py
```

Verify:
- For lists: Count matches expected from container analysis
- For single: Values are not empty
- URLs are absolute (prepend base URL if needed)

## DOM Dictionary Format

```json
{
  "tag": "a",
  "class": "product-item group",
  "href": "/products/123",
  "xpath": "//*[@id='app']/div[2]/a[1]",
  "text": "Product Name",
  "children": [
    {
      "tag": "div",
      "class": "info",
      "children": [...]
    }
  ]
}
```

Fields: `tag`, `class`, `href`, `src`, `text`, `xpath`, `children`

## Rules

1. **Parse dom_dict directly** - DO NOT convert to HTML or use lxml/BeautifulSoup

2. **URLs MUST be absolute** - This is CRITICAL! Relative URLs will cause navigation failures.

   Always convert relative URLs to absolute using the page URL:
   ```python
   from urllib.parse import urljoin

   PAGE_URL = "https://example.com/category/page"  # From task context

   def make_absolute(url: str) -> str:
       if not url:
           return ""
       if url.startswith(('http://', 'https://')):
           return url
       return urljoin(PAGE_URL, url)

   # Usage in extraction:
   data = {
       "url": make_absolute(node.get('href', '')),
       "image": make_absolute(node.get('src', '')),
   }
   ```

   **NEVER return relative URLs like `/products/xxx` - always prepend the base URL!**

3. **Be robust** - Use partial class matching:
   ```python
   # Good
   if 'product-item' in node.get('class', ''):

   # Bad - exact match fails
   if node.get('class') == 'product-item':
   ```

4. **Handle missing fields gracefully**:
   ```python
   name = node.get('text', '') or ''
   ```

5. **Respect container boundaries** - Only extract from the specific container identified by xpath, not the entire DOM tree.

## Example

Given xpath hint `//*[@id='app']/main/div[4]/div/a[1]`:

```bash
# 1. Find the element (verify xpath hint works)
python .claude/skills/dom-extraction/tools/dom_tools.py find "//*[@id='app']/main/div[4]/div/a[1]"
# ✓ Found element at ...

# 2. Get container xpath by removing the [1] index
# Element: //*[@id='app']/main/div[4]/div/a[1]
# Container: //*[@id='app']/main/div[4]/div

# 3. Analyze container (builds virtual container automatically)
python .claude/skills/dom-extraction/tools/dom_tools.py analyze "//*[@id='app']/main/div[4]/div"
# Result: total_children: 20, by_tag: {"a": 20}

# 4. List children to see their structure
python .claude/skills/dom-extraction/tools/dom_tools.py children "//*[@id='app']/main/div[4]/div" a

# 5. Write script targeting this exact container
```
