---
name: workflow-optimizations
description: Layer 2 workflow optimizations. Use AFTER generating base workflow to apply optimization patterns. Includes click-to-navigate and scroll optimization.
---

# Workflow Optimizations (Layer 2)

## Overview

After generating a base workflow (Layer 1), apply these optimizations to improve reliability.

## Optimization Process

1. Review the generated base workflow
2. Check each optimization pattern below
3. Apply all matching patterns
4. Document what optimizations were applied

## Available Optimizations

| Pattern | When to Apply | Reference |
|---------|---------------|-----------|
| Click-to-Navigate | Click action leads to page change | `references/click_to_navigate.md` |
| Scroll Optimization | Multiple scroll operations | `references/scroll_optimization.md` |

## Quick Patterns

### 1. Click-to-Navigate

**Before** (from recording):
```yaml
- id: "click-product"
  agent_type: "browser_agent"
  inputs:
    interaction_steps:
      - task: "Click product link"
```

**After** (optimized):
```yaml
- id: "navigate-product"
  agent_type: "browser_agent"
  inputs:
    target_url: "{{product.url}}"  # Direct navigation
```

**When to apply**: Click on links/buttons that navigate to a new page.

### 2. Scroll Optimization

**Before** (from recording):
```yaml
- id: "scroll-1"
  agent_type: "browser_agent"
  inputs:
    interaction_steps:
      - action_type: "scroll"
        parameters: {down: true}
- id: "scroll-2"
  agent_type: "browser_agent"
  inputs:
    interaction_steps:
      - action_type: "scroll"
        parameters: {down: true}
```

**After** (optimized):
```yaml
- id: "scroll-page"
  agent_type: "browser_agent"
  inputs:
    interaction_steps:
      - action_type: "scroll"
        parameters:
          down: true
          num_pages: 2  # Combine into one
```

Or for scroll-to-element:
```yaml
- id: "scroll-to-content"
  agent_type: "browser_agent"
  inputs:
    interaction_steps:
      - task: "Scroll to the content section"
        xpath_hints:
          section: "//div[@id='content']"
```

## Applying Optimizations

For each optimization:
1. Check if the pattern matches
2. Read the full reference if needed
3. Transform the workflow accordingly
4. Ensure variables are properly connected

## Output

After applying optimizations, note what was changed:
```
Applied optimizations:
- Click-to-Navigate: Converted 2 click actions to direct navigation
- Scroll Optimization: Consolidated 3 scrolls into one
```
