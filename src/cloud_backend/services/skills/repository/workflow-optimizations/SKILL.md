---
name: workflow-optimizations
description: Optimize generated workflow by reviewing patterns.
---

# Workflow Optimizations

## Goal

你现在要给 workflow 进行优化，理解现实的网络操作，减少不必要的步骤。
下面是一些基本原则。

## Optimization Directions

### 1. Static URL Simplification

If scraper+navigate extracts a static URL (no dates, IDs, or dynamic parts):
- **Can simplify** to direct `target_url` navigation
- Examples of static: `/about`, `/products`, `/contact`
- Examples of dynamic: `/leaderboard/weekly/2026/1`, `/product/12345`
- If the navigation target can be formed by joining the current page URL with a suffix (e.g., `url/suffix`), consider optimizing by directly merging them into the final `target_url`.

```yaml
# Before (scraper + navigate)
- id: extract-about-url
  agent: scraper_agent
  ...
- id: navigate-to-about
  agent: browser_agent
  inputs:
    target_url: "{{about_link.0.url}}"

# After (simplified - only for static URLs!)
- id: navigate-to-about
  agent: browser_agent
  inputs:
    target_url: "https://example.com/about"
```

### 2. Scroll Consolidation

Multiple consecutive scrolls on same page → combine into one.

```yaml
# Before
- id: scroll-1
  agent: browser_agent
  inputs:
    interaction_steps:
      - task: "Scroll down"
- id: scroll-2
  agent: browser_agent
  inputs:
    interaction_steps:
      - task: "Scroll down"

# After
- id: scroll-page
  agent: browser_agent
  inputs:
    interaction_steps:
      - task: "Scroll down to load content"
        xpath_hints:
          body: "//body"
```

### 3. Scroll Before Extract

Scroll followed by extract → usually can remove scroll.
`scraper_agent` gets full DOM, doesn't need element in viewport.

### 4. Right-click (Contextmenu) → Extract Link

When user right-clicked on an element (contextmenu operation):
- Usually means they want the **link URL**, not to actually trigger context menu
- Check the intent description - if it mentions "extract links/URLs", use `scraper_agent`
- Extract the `href` attribute directly from DOM, no need to simulate right-click

```yaml
# User right-clicked on product links with intent "Extract product link URLs"
# DON'T simulate right-click - just extract href

- id: extract-product-links
  agent: scraper_agent
  inputs:
    data_requirements:
      fields:
        - name: url
          type: url
    user_description: "Extract product link URLs"
    xpath_hints:
      url: "//a[@class='product-link']"  # xpath from contextmenu target element
```

### 5. Hover → Extract or Navigate

When user hovered on an element (hover operation with DOM changes):
- Check the intent description to determine the goal:

**A. Hover to extract data from revealed content:**
- Use `browser_agent` to hover → wait → then `scraper_agent` to extract
- The hover is necessary because data is hidden until hover

```yaml
# User hovered on products to reveal prices, intent "Extract prices from hover tooltips"

- id: hover-to-reveal
  agent: browser_agent
  inputs:
    interaction_steps:
      - task: "Hover on product to reveal price tooltip"
        action: hover
        xpath_hints:
          target: "//div[@class='product-item']"

- id: extract-revealed-price
  agent: scraper_agent
  inputs:
    data_requirements:
      fields:
        - name: price
          type: text
    user_description: "Extract price from revealed tooltip"
    xpath_hints:
      price: "//div[@class='tooltip']//span[@class='price']"
```

**B. Hover to navigate via dropdown menu:**
- Use `browser_agent` with hover + click sequence in `interaction_steps`

```yaml
# User hovered on menu to reveal submenu, then clicked, intent "Navigate to settings"

- id: navigate-via-hover-menu
  agent: browser_agent
  inputs:
    interaction_steps:
      - task: "Hover on menu to reveal dropdown"
        action: hover
        xpath_hints:
          menu: "//nav//li[contains(text(), 'Account')]"
      - task: "Click settings link in dropdown"
        action: click
        xpath_hints:
          settings: "//a[contains(text(), 'Settings')]"
```

**C. Hover but just want the link (no DOM needed):**
- If user hovered but intent is "extract links" and element has `href`
- Skip hover, just use `scraper_agent` to extract href directly

```yaml
# User hovered on links but intent is just "Extract navigation links"
# Element already has href - no need to hover

- id: extract-nav-links
  agent: scraper_agent
  inputs:
    data_requirements:
      fields:
        - name: url
          type: url
    xpath_hints:
      url: "//nav//a"  # Direct extraction, no hover needed
```

### 6. Copy Button → Clipboard Capture

When user clicked a "Copy" button (identified by element text or class containing "copy", "clipboard"):
- Use `browser_agent` click with `outputs` to capture clipboard content
- The clipboard content is automatically captured after click
- No need to use `scraper_agent` to extract visible text - clipboard may contain formatted/full data

**Detection signals**:
- `element.textContent` contains: "Copy", "复制", "Copy to clipboard"
- `element.className` contains: "copy", "clipboard"
- Icon buttons next to code blocks, data fields

```yaml
# User clicked copy button, intent "Copy the API key"
# browser_agent captures clipboard automatically

- id: copy-api-key
  name: "Click copy button to get API key"
  agent: browser_agent
  inputs:
    interaction_steps:
      - task: "Click the copy button"
        xpath_hints:
          copy_btn: "//button[@class='copy-btn']"
  outputs:
    result: copy_result              # {success, clipboard_content}

# clipboard_content now contains the copied data
- id: store-api-key
  name: "Store the API key"
  agent: storage_agent
  inputs:
    operation: store
    collection: api_keys
    data:
      key: "{{copy_result.clipboard_content}}"
```

**Why use clipboard instead of scraper**:
- Clipboard may contain more data than visible (e.g., full JSON, complete code)
- Websites often copy formatted data (with proper escaping)
- Some data is generated on-click (e.g., one-time tokens)

## Critical Rule

**Always use original URL/href from intent operations. Never simplify or guess URLs.**

If operation has `href: "/leaderboard/weekly/2026/1"`:
- Use exactly `/leaderboard/weekly/2026/1`
- Do NOT simplify to `/leaderboard/weekly`
