---
name: workflow-optimizations
description: Patterns for handling special interaction cases.
---

# Special Interaction Patterns

## 1. Right-click → Extract Link

When user right-clicked (contextmenu) but intent is to extract links/URLs:
- Don't simulate right-click
- Use `scraper_agent` to extract `href` directly

## 2. Hover Handling

| User Intent | Action |
|-------------|--------|
| Extract data from revealed tooltip | `browser_agent` hover → `scraper_agent` extract |
| Navigate via dropdown menu | `browser_agent` hover + click in `interaction_steps` |
| Just want link URL (element has href) | Skip hover, `scraper_agent` extract href |

## 3. Copy Button → Clipboard Capture

When user clicked a "Copy" button (text contains "Copy", "复制", class contains "copy", "clipboard"):
- Use `browser_agent` click with `outputs: {result: ...}`
- Access clipboard: `{{result.clipboard_content}}`
- Don't use `scraper_agent` for visible text - clipboard may have full/formatted data

```yaml
- id: click-copy
  agent: browser_agent
  inputs:
    interaction_steps:
      - task: "Click copy button"
        xpath_hints:
          btn: "//button[@class='copy']"
  outputs:
    result: copy_result    # Access: {{copy_result.clipboard_content}}
```

## 4. Tab Operations

When recording contains `newtab` or `closetab`:

```yaml
# Open URL in new tab
- task: "Open in new tab"
  action: "new_tab"
  url: "https://example.com"

# Switch tab (0 = first tab)
- task: "Switch to first tab"
  action: "switch_tab"
  tab_index: 0

# Close current tab
- task: "Close tab"
  action: "close_tab"
```
