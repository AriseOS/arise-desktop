# Click-to-Navigate Optimization

## Problem

Recording captures user clicks on links/buttons. These clicks are fragile:
- Element selectors may change
- Page structure may be different
- Click may fail due to overlays/popups

## Solution

Replace click-based navigation with direct URL navigation when possible.

## When to Apply

| Intent Type | Has URL? | Action |
|-------------|----------|--------|
| Click on link | Yes (href) | Convert to `target_url` |
| Click on button leading to new page | Yes (from data) | Convert to `target_url` |
| Click on button for action (submit, expand) | No | Keep as click |

## Pattern Recognition

### From Intent Sequence

Look for patterns like:
```json
{
  "type": "click",
  "element": {
    "tag": "a",
    "href": "https://example.com/product/123"
  }
}
```

If element has `href` or the click leads to a URL that was extracted earlier, use direct navigation.

### From User Recording

If user:
1. Extracted a list of URLs
2. Then clicked on items one by one

Convert to:
1. Extract URLs
2. foreach: navigate directly to each URL

## Transformation

### Before (Click-based)
```yaml
- id: "click-product"
  agent_type: "browser_agent"
  inputs:
    interaction_steps:
      - task: "Click the product link"
        xpath_hints:
          link: "//a[@class='product-link']"
```

### After (Direct Navigation)
```yaml
- id: "navigate-product"
  agent_type: "browser_agent"
  inputs:
    target_url: "{{product.url}}"
```

## Benefits

1. **More reliable**: Direct navigation always works
2. **Faster**: No need to find and click element
3. **Cleaner**: Simpler workflow structure

## Exceptions

Keep click action when:
- Button triggers AJAX/dynamic content (not full page navigation)
- Action requires authentication context
- No URL is available for the target
