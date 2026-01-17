---
name: element-finder
description: Generate find_element.py scripts to locate interactive elements for browser operations.
---

# Element Finder (Simplified)

## Goal

Generate `find_element.py` that uses `analyze_xpath_hint` to find target elements.

**CRITICAL**: Only elements with `interactive_index` can be clicked or filled.

## Key Change

The script now uses the **injected** `analyze_xpath_hint` function:

```python
def find_target_element(dom_dict: dict, xpath: str) -> dict:
    # analyze_xpath_hint is injected by execution environment
    result = analyze_xpath_hint(dom_dict, xpath)
    ...
```

**Important**:
- `analyze_xpath_hint` is injected by browser_agent - do NOT import it
- The function signature is `find_target_element(dom_dict, xpath)`
- `xpath` is passed at runtime and may differ each call (e.g., in foreach loops)

## Input Files

- `task.json` - Task description with xpath hints
- `dom_data.json` - Page DOM as nested JSON dictionary
- `find_element_template.py` - Template that uses analyze_xpath_hint

## Workflow

### Step 1: Read task.json

```bash
cat task.json
```

Get the `xpath_hints` values.

### Step 2: Test with hint command

```bash
python .claude/skills/element-finder/tools/element_tools.py hint "<xpath_from_hints>"
```

Check if it finds an interactive element.

### Step 3: Create find_element.py

**If hint FINDS an element** (has `interactive_index`):

```bash
cp find_element_template.py find_element.py
```

That's it! The template already uses `analyze_xpath_hint`.

**If hint FAILS** (no interactive element found):

Still copy the template - it will return a "fallback required" error,
which triggers LLM fallback mode. This is acceptable.

### Step 4: Test

```bash
python test_operation.py
```

**Both outcomes are valid**:
- "SUCCESS: Found element" = hint found the element
- "INFO: Script returned fallback required" = hint failed, LLM fallback will be used

## Template Content

The template (`find_element_template.py`) contains:

```python
def find_target_element(dom_dict: dict, xpath: str) -> dict:
    if not xpath:
        return {"success": False, "error": "No xpath provided"}

    # analyze_xpath_hint is injected by browser_agent's exec environment
    result = analyze_xpath_hint(dom_dict, xpath)

    match = result.get('interactive_match')
    if match and match.get('interactive_index') is not None:
        return {
            "success": True,
            "interactive_index": match['interactive_index'],
            "element_info": {...}
        }

    return {
        "success": False,
        "error": "Cannot find interactive element via hint, fallback required"
    }
```

## Element Tools (for debugging)

Tools in `tools/element_tools.py`:

```bash
# Analyze xpath hint - RECOMMENDED FIRST STEP
python element_tools.py hint "<xpath>"

# Find element by xpath
python element_tools.py find "<xpath>"

# Search by text
python element_tools.py search "Submit"

# List interactive elements in container
python element_tools.py list "<container_xpath>"

# Search by attribute
python element_tools.py attr "class" "btn-primary"
```

## Fallback Mode

When hint-based search fails, the system enters **LLM fallback mode** and creates a `.fallback_mode` marker file in the working directory.

### Auto-clearing

The `.fallback_mode` marker is automatically cleared when:
- Task description changes
- xpath_hints keys change

This allows the system to retry script-based search when the task changes.

### Manual Reset

If the page structure has changed and you want to retry hint-based search:

```bash
# Delete the fallback marker to force script regeneration
rm .fallback_mode
```

Or delete `find_element.py` and `.fallback_mode` together to start fresh:

```bash
rm -f find_element.py .fallback_mode
```

After clearing, the next execution will:
1. Try hint-based search again
2. If successful, use script mode (faster, no LLM cost)
3. If failed, re-enter fallback mode

## Why This Simplified Approach?

1. **Dynamic xpath support**: Same script works with different xpath values
2. **foreach loop support**: In loops, xpath changes each iteration
3. **Reduced complexity**: No need to write custom search logic
4. **Reliable fallback**: If hint fails, LLM fallback handles complex cases
