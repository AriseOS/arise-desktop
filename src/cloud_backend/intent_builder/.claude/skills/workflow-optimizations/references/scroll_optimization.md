# Scroll Optimization

## Problem

Recording may capture multiple scroll actions:
- User scrolled multiple times to find content
- User scrolled incrementally to load lazy content
- Redundant scrolls that don't affect extraction

## Solution

Consolidate or eliminate scroll operations based on purpose.

## Scroll Types

### 1. Scroll to Load Content (Lazy Loading)

**Before**:
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

**After** (consolidated):
```yaml
- id: "scroll-to-load"
  agent_type: "browser_agent"
  inputs:
    interaction_steps:
      - action_type: "scroll"
        parameters:
          down: true
          num_pages: 3  # Combined count
```

### 2. Scroll to Specific Element

**Before** (user scrolled to find section):
```yaml
- id: "scroll-down"
  agent_type: "browser_agent"
  inputs:
    interaction_steps:
      - action_type: "scroll"
        parameters: {down: true, num_pages: 2}
```

**After** (direct scroll to element):
```yaml
- id: "scroll-to-section"
  agent_type: "browser_agent"
  inputs:
    interaction_steps:
      - task: "Scroll to the Reviews section"
        xpath_hints:
          section: "//h2[contains(text(), 'Reviews')]"
```

### 3. Unnecessary Scroll (Remove)

If scroll was just to view content but extraction doesn't need it:
- Remove the scroll step entirely
- Scraper can extract from DOM without visual scrolling

## Decision Flow

```
Is scroll needed for extraction?
├── No → Remove scroll step
└── Yes
    ├── Scroll to specific element? → Use scroll-to-element
    └── Scroll to load content? → Consolidate into one scroll with num_pages
```

## Parameters

```yaml
action_type: "scroll"
parameters:
  down: true          # Direction (true=down, false=up)
  num_pages: 3        # Number of viewport heights to scroll
  # OR
  pixels: 500         # Specific pixel amount
```

## Notes

- Scroll-to-element is more reliable than scroll-by-pages
- If extracting from full page, scroll may not be needed (DOM has all content)
- For infinite scroll pages, may need loop with scroll + extract
