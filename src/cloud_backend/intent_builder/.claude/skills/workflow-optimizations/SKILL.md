---
name: workflow-optimizations
description: Optimize generated workflow by reviewing patterns.
---

# Workflow Optimizations

## Goal

Review generated workflow and apply optimizations where appropriate.

## Optimization Directions

### 1. Static URL Simplification

If scraper+navigate extracts a static URL (no dates, IDs, or dynamic parts):
- **Can simplify** to direct `target_url` navigation
- Examples of static: `/about`, `/products`, `/contact`
- Examples of dynamic: `/leaderboard/weekly/2026/1`, `/product/12345`

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

## Critical Rule

**Always use original URL/href from intent operations. Never simplify or guess URLs.**

If operation has `href: "/leaderboard/weekly/2026/1"`:
- Use exactly `/leaderboard/weekly/2026/1`
- Do NOT simplify to `/leaderboard/weekly`
