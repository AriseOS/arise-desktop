# Script Generation Module

Reusable script generation for browser automation and data extraction.

## Purpose

This module extracts script generation logic from BaseApp agents so it can be shared with:
- **BaseApp agents** (BrowserAgent, ScraperAgent) during workflow execution
- **Cloud Backend** (Intent Builder) for pre-generating scripts during workflow creation

## Architecture

```
User Recording + DOM Snapshot
         ↓
┌─────────────────────────────────────────────┐
│         Script Generation                    │
│  ┌─────────────────────────────────────┐    │
│  │   BrowserScriptGenerator            │    │
│  │   - generate_find_element()         │    │
│  │   - Input: task, dom_dict           │    │
│  │   - Output: find_element.py         │    │
│  └─────────────────────────────────────┘    │
│  ┌─────────────────────────────────────┐    │
│  │   ScraperScriptGenerator            │    │
│  │   - generate_extraction_script()    │    │
│  │   - Input: requirement, dom_dict    │    │
│  │   - Output: extraction_script.py    │    │
│  └─────────────────────────────────────┘    │
│              ↓ Uses                          │
│      ClaudeAgentProvider                     │
│      (Claude Agent SDK)                      │
└─────────────────────────────────────────────┘
         ↓
Generated Python Scripts
```

## Key Files

| File | Purpose |
|------|---------|
| `browser_script_generator.py` | Generates find_element.py for click/fill operations |
| `scraper_script_generator.py` | Generates extraction_script.py for data extraction |
| `templates.py` | Reusable script templates and Claude prompts |
| `types.py` | Data types: ScriptGenerationResult, BrowserTask, ScraperRequirement |

## Usage

### Generate Browser Script (find_element.py)

```python
from src.common.script_generation import BrowserScriptGenerator, BrowserTask

generator = BrowserScriptGenerator()
result = await generator.generate(
    task=BrowserTask(
        task="Click the login button",
        operation="click",
        xpath_hints={"target": "//*[@id='login']"}
    ),
    dom_dict={...},  # From DOMExtractor.extract_dom_dict()
    working_dir=Path("/tmp/workspace"),
    api_key="sk-..."
)

if result.success:
    print(result.script_content)
```

### Generate Scraper Script (extraction_script.py)

```python
from src.common.script_generation import ScraperScriptGenerator, ScraperRequirement

generator = ScraperScriptGenerator()
result = await generator.generate(
    requirement=ScraperRequirement(
        user_description="Extract product list",
        output_format={"name": "Product name", "price": "Price"},
        xpath_hints={"name": "//*[@class='product-name']"}
    ),
    dom_dict={...},
    working_dir=Path("/tmp/workspace"),
    api_key="sk-..."
)

if result.success:
    print(result.script_content)
```

## DOM Format

Both generators expect `dom_dict` in the format produced by `DOMExtractor.extract_dom_dict()`:

```json
{
  "tag": "div",
  "text": "Hello",
  "xpath": "/html/body/div",
  "interactive_index": 1,
  "class": "container",
  "children": [...]
}
```

## Dependencies

- `src.common.llm.ClaudeAgentProvider` - Claude Agent SDK wrapper
- No browser runtime required - works with pre-captured DOM data

## Integration Points

### BaseApp (Execution Time)
- `BrowserAgent` uses `BrowserScriptGenerator` when DOM changes
- `ScraperAgent` uses `ScraperScriptGenerator` for script mode

### Cloud Backend (Pre-generation)
- Intent Builder uses generators with DOM snapshots from recording
- Scripts saved to workflow directory before user downloads
