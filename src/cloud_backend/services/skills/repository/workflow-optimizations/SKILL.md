---
name: workflow-optimizations
description: Optional patterns for optimizing generated workflows.
---

# Workflow Optimizations

These are **optional** patterns. The default behavior is to replay user's recorded actions faithfully.

## 1. URL Navigation Optimization

**Can simplify** (use direct `target_url`):
- Static paths: `/about`, `/products`, `/contact`
- Concatenated URLs: `base_url + "/settings"` → just use full URL

**Cannot simplify** (must extract via `scraper_agent`):
- URLs with dates: `/leaderboard/weekly/2026/3`
- URLs with IDs: `/product/12345`, `/user/abc123`
- URLs that may change between runs

```yaml
# Static URL - can simplify to direct navigation
- id: go-to-about
  agent: browser_agent
  inputs:
    target_url: "https://example.com/about"

# Dynamic URL - must extract first
- id: extract-product-url
  agent: scraper_agent
  inputs:
    data_requirements:
      user_description: "Extract product URL"
      output_format:
        url: "Product link"
      xpath_hints:
        url: "//a[@class='product']"
  outputs:
    result: product_link

- id: navigate-to-product
  agent: browser_agent
  inputs:
    target_url: "{{product_link.0.url}}"
```

## 2. Scroll Consolidation

Multiple consecutive scrolls → combine into one step with multiple scroll actions.

## 3. Scroll Before Extract

Scroll followed by extract → usually remove scroll.
`scraper_agent` gets full DOM, doesn't need element in viewport.

## 4. Right-click → Extract Link

When user right-clicked (contextmenu) but intent says "extract links/URLs":
- Don't simulate right-click
- Use `scraper_agent` to extract `href` directly

## 5. Hover Handling

| Intent | Action |
|--------|--------|
| Extract data from revealed tooltip | `browser_agent` hover → `scraper_agent` extract |
| Navigate via dropdown menu | `browser_agent` hover + click in `interaction_steps` |
| Just want link URL (element has href) | Skip hover, `scraper_agent` extract href |

## 6. Copy Button → Clipboard Capture

When user clicked a "Copy" button:
- Use `browser_agent` click with `outputs: {result: ...}`
- Access clipboard: `{{result.clipboard_content}}`
- Don't use `scraper_agent` for visible text - clipboard may have full data
