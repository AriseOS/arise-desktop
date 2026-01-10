---
name: scraper-fix
description: Fix scraper extraction issues when fields are missing or data is not extracted correctly. Use when user mentions missing fields, extraction errors, data not being extracted, or field-related problems.
---

# Scraper Fix Skill

## Goal

Fix extraction issues in scraper scripts when user reports:
- Missing fields in extracted data
- Empty values
- Wrong data extracted
- Script errors

## Working Directory Structure

You are working in a session directory that contains a copy of the workflow:

```
./                              # Session working directory
├── workflow.yaml               # Workflow definition
├── metadata.json
├── dom_snapshots/              # Global DOM snapshots for all pages
│   ├── url_index.json          # URL to DOM file mapping
│   └── {url_hash}.json         # DOM snapshot files (wrapped format)
└── {step_id}/                  # Step directories
    └── scraper_script_{hash}/  # Scraper script directory
        ├── extraction_script.py
        ├── dom_tools.py
        ├── requirement.json
        └── dom_data.json       # DOM for this step (copied from dom_snapshots)
```

### Finding DOM by URL

When user mentions a specific URL (e.g., "https://watcha.cn/products/contract-maker"), find the corresponding DOM:

1. **Read `dom_snapshots/url_index.json`** to find the mapping:
```json
[
  {"url": "https://watcha.cn/products/contract-maker", "file": "abc123.json", "step_id": "extract-product-info"}
]
```

2. **Load the DOM file** from `dom_snapshots/{file}`:
```bash
cat dom_snapshots/abc123.json | python -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d['dom'], indent=2)[:2000])"
```

3. **Or use dom_tools.py** with the URL's DOM:
```bash
# Copy the relevant DOM to a step directory first
cp dom_snapshots/abc123.json {step_id}/scraper_script_xxx/dom_data.json
cd {step_id}/scraper_script_xxx
python dom_tools.py search --text "效率工具"
```

## Workflow

### Step 1: Identify the Problem

Ask user or infer from context:
- Which step has extraction issues?
- What fields are missing/wrong?
- Which page/URL is affected?

**If user provides a specific URL**, immediately look up the DOM:
```bash
# Find the DOM file for the URL
cat dom_snapshots/url_index.json
# Look for the entry matching the user's URL, then read that DOM file
```

### Step 2: Locate Scraper Script

1. Read `workflow.yaml` to find the step with issues
2. Look for `scraper_agent` steps - they have script directories under `{step_id}/scraper_script_*`
3. Navigate to the script directory

```bash
# List step directories
ls -la

# Find scraper script directories
find . -type d -name "scraper_script_*"
```

### Step 3: Analyze Current State

Read these files in the script directory:

1. **requirement.json** - Original extraction requirements
   - `user_description`: What user wanted to extract
   - `output_format`: Expected field names and descriptions
   - `xpath_hints`: XPath hints from recording (may be outdated)

2. **extraction_script.py** - Current extraction script
   - Check `extract_data_from_page()` function
   - Look for hardcoded xpaths that may be wrong

3. **dom_data.json** - DOM for this step (pre-copied from dom_snapshots)
   - Use this to find correct xpaths
   - Load via `dom_tools.py` commands

4. **If URL-specific DOM needed** - Find via url_index.json:
   ```bash
   # Check url_index.json for the specific URL
   cat dom_snapshots/url_index.json
   # Copy the matching DOM file to work with dom_tools.py
   ```

### Step 4: Debug with dom_tools.py

The `dom_tools.py` in each script directory provides debugging commands:

```bash
cd {step_id}/scraper_script_{hash}

# Test single xpath
python dom_tools.py find '{"field_name": "//xpath/to/test"}'

# Test container extraction (for lists)
python dom_tools.py container "//item/xpath" --fields "name:text,url:href"

# Search for text content
python dom_tools.py search --text "Expected Text"

# Search by class name
python dom_tools.py search --class "product-item"
```

### Step 5: Fix the Script

Modify `extraction_script.py` based on findings:

1. Update xpaths to match current DOM structure
2. Handle edge cases (missing elements, null values)
3. Add fallback selectors if needed

**Important Rules:**
- Keep the function signature: `def extract_data_from_page(dom_dict: Dict) -> List[Dict]`
- Use `from dom_tools import extract_list, extract_single, extract_multi`
- Make URLs absolute using `urljoin(PAGE_URL, url)`
- Do NOT read dom_data.json at module level

### Step 6: Test the Fix

```bash
cd {step_id}/scraper_script_{hash}

# Run the script directly (uses dom_data.json for testing)
python extraction_script.py
```

Verify:
- All required fields are present
- Values are correct types
- URLs are absolute
- No errors in output

## Common Issues and Solutions

### Issue: Field is empty or missing

**Cause**: XPath points to wrong element or element structure changed.

**Solution**:
```bash
# Find where the text actually is
python dom_tools.py search --text "Expected Value"

# Or find by class
python dom_tools.py search --class "field-class"
```

### Issue: List extraction returns empty

**Cause**: Container xpath doesn't match list items.

**Solution**:
```bash
# Test container command with known item xpath
python dom_tools.py container "//known/item/xpath" --fields "name:text"
```

### Issue: Nested field extraction

**Cause**: Field is inside a nested element.

**Solution**:
```bash
# find command shows children when element is a container
python dom_tools.py find '{"field": "//parent/xpath"}'
# Output shows child xpaths - use the specific child xpath
```

### Issue: Multiple paragraphs for description

**Cause**: Content spans multiple sibling elements.

**Solution**:
```bash
# find command shows siblings
python dom_tools.py find '{"desc": "//p[1]"}'
# Output shows p[2], p[3] etc - merge in script:
# description = " ".join([extract_single(dom, xpath, "text") for xpath in [p1, p2, p3]])
```

## Reference: dom_tools Functions

```python
from dom_tools import extract_list, extract_single, extract_multi

# Extract list of items from container
items = extract_list(dom_dict, "//container/xpath", {
    "name": "text",      # Get text from item
    "url": "href",       # Get href attribute
    "name": "text:h4"    # Get text from h4 child element
})

# Extract single value
value = extract_single(dom_dict, "//element/xpath", "text")

# Extract multiple fields at once
data = extract_multi(dom_dict, {
    "title": "//h1",
    "price": "//span[@class='price']"
}, "text")
```

## Notes

- After fixing, the session will sync `extraction_script.py` back to the original workflow
- Only modify files in the script directory, not the DOM snapshots
- If DOM structure has fundamentally changed, user may need to re-record
