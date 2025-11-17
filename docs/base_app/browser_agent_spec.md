# BrowserAgent Specification

**Purpose**: Navigate to web pages and perform basic interactions without data extraction

**When to use**:
- Intent is pure navigation (no data extraction)
- Intent description contains keywords: "navigate", "enter", "visit", "go to"
- NO extract operations in the intent

**When NOT to use**:
- Intent involves data extraction → Use `scraper_agent` instead
- Intent has extract operations → Use `scraper_agent`

---

## Basic Usage

```yaml
- id: "step-id"
  agent_type: "browser_agent"
  name: "Navigate to page"
  description: "Navigate to target page"
  inputs:
    target_url: "https://example.com"
  outputs:
    result: "nav_result"
  timeout: 30
```

---

## Input Parameters

**Note**: At least one of `target_url` or `interaction_steps` must be provided.

### Optional

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `target_url` | string | - | Target URL to navigate to (if omitted, operations will be performed on current page) |
| `interaction_steps` | array | `[]` | Interaction steps to execute (currently only supports scroll). If `target_url` is provided, steps execute after navigation; otherwise, steps execute on current page. |
| `timeout` | integer | 30 | Timeout in seconds |

---

## Interaction Steps

Currently only supports **scroll** operations.

### Scroll Configuration

```yaml
interaction_steps:
  - action_type: "scroll"
    parameters:
      down: true           # true=scroll down, false=scroll up
      num_pages: 2.0       # Number of pages to scroll (e.g., 2.0 = 2 pages)
```

**Example 1: Navigate and Scroll**
```yaml
- id: "navigate-and-scroll"
  agent_type: "browser_agent"
  inputs:
    target_url: "https://example.com/page"
    interaction_steps:
      - action_type: "scroll"
        parameters:
          down: true
          num_pages: 2.0
```

**Example 2: Scroll Only (on current page)**
```yaml
- id: "scroll-to-load-more"
  agent_type: "browser_agent"
  inputs:
    interaction_steps:
      - action_type: "scroll"
        parameters:
          down: true
          num_pages: 5
```

---

## Output Format

```yaml
{
  "success": true,
  "message": "Successfully navigated to https://example.com",
  "current_url": "https://example.com",
  "steps_executed": 0
}
```

**Output Fields**:
- `success`: Whether navigation was successful
- `message`: Execution message
- `current_url`: Current page URL after navigation
- `steps_executed`: Number of interaction steps executed

---

## Usage Scenarios

### Scenario 1: Simple Navigation

**Intent**: "Navigate to homepage"

**Workflow**:
```yaml
- id: "navigate-home"
  agent_type: "browser_agent"
  description: "Navigate to Allegro homepage"
  inputs:
    target_url: "https://allegro.pl/"
  outputs:
    result: "nav_result"
  timeout: 30
```

### Scenario 2: Multi-step Navigation

**Intent**: Multi-step navigation to establish session (prevent anti-bot detection)

**Workflow**:
```yaml
steps:
  # Step 1: Visit homepage first
  - id: "navigate-homepage"
    agent_type: "browser_agent"
    inputs:
      target_url: "https://example.com/"
    outputs:
      result: "homepage_result"

  # Step 2: Navigate to category page
  - id: "navigate-category"
    agent_type: "browser_agent"
    inputs:
      target_url: "https://example.com/category/coffee"
    outputs:
      result: "category_result"

  # Step 3: Extract data from current page (using scraper_agent)
  - id: "extract-products"
    agent_type: "scraper_agent"
    inputs:
      use_current_page: true  # Use page from previous step
      data_requirements: {...}
```

### Scenario 3: Navigation with Scroll

**Intent**: "Navigate to page and scroll to trigger lazy loading"

**Workflow**:
```yaml
- id: "navigate-and-load"
  agent_type: "browser_agent"
  description: "Navigate and scroll to load more content"
  inputs:
    target_url: "https://example.com/products"
    interaction_steps:
      - action_type: "scroll"
        parameters:
          down: true
          num_pages: 2.0
  outputs:
    result: "nav_result"
  timeout: 45
```

### Scenario 4: Scroll Only on Current Page

**Intent**: "After navigation, scroll to load all products via infinite scroll"

**Workflow**:
```yaml
steps:
  # Step 1: Navigate to page
  - id: "navigate-to-weekly"
    agent_type: "browser_agent"
    inputs:
      target_url: "{{weekly_link.weekly_url}}"
    timeout: 30

  # Step 2: Scroll to load more content (on current page)
  - id: "scroll-to-load-all"
    agent_type: "browser_agent"
    inputs:
      interaction_steps:
        - action_type: "scroll"
          parameters:
            down: true
            num_pages: 5
    timeout: 60
```

---

## Cooperation with ScraperAgent

**Pattern**: BrowserAgent navigates → ScraperAgent extracts

```yaml
steps:
  # BrowserAgent: Navigate to page
  - id: "step1"
    agent_type: "browser_agent"
    inputs:
      target_url: "https://example.com/category"
    outputs:
      result: "nav_result"

  # ScraperAgent: Extract data from current page
  - id: "step2"
    agent_type: "scraper_agent"
    inputs:
      use_current_page: true  # IMPORTANT: Don't navigate again
      data_requirements:
        user_description: "Extract product URLs"
        output_format:
          url: "Product URL"
    outputs:
      extracted_data: "product_urls"
```

**Key Point**: When ScraperAgent follows BrowserAgent, use `use_current_page: true` to avoid redundant navigation.

---

## Browser Session Sharing

**IMPORTANT**: BrowserAgent shares the same browser session with other agents in the workflow.

**Benefits**:
- Cookie/Session state is preserved across agents
- Avoids redundant browser initialization
- Enables proper navigation flow (homepage → category → detail)

**Implementation**:
- All agents get browser session from `AgentContext`
- Navigation state persists between steps
- ScraperAgent can use `use_current_page: true` to leverage BrowserAgent's navigation

---

## Limitations (Current Version)

**NOT Supported**:
- ❌ Click operations
- ❌ Input/form operations
- ❌ Hover operations
- ❌ Wait for specific conditions
- ❌ Data extraction (use ScraperAgent)

**Future Enhancements**:
- Support click operations
- Support input operations
- Support complex interaction sequences

---

## Decision Rules: BrowserAgent vs ScraperAgent

### Use BrowserAgent when:
- ✅ Intent is ONLY navigation
- ✅ Intent description: "navigate", "enter", "visit", "go to"
- ✅ NO extract operations
- ✅ Purpose is to establish session or navigate to a page

### Use ScraperAgent when:
- ✅ Intent includes data extraction
- ✅ Intent has extract operations
- ✅ Intent description: "extract", "collect", "scrape", "get data"
- ✅ Navigation + extraction in same step

**Examples**:

| Intent Description | Agent Type | Reason |
|-------------------|------------|--------|
| "Navigate to Allegro homepage" | `browser_agent` | Pure navigation |
| "Navigate to coffee category through menu" | `browser_agent` | Pure navigation |
| "Extract product URLs from category page" | `scraper_agent` | Has extraction |
| "Visit product detail page and extract title and price" | `scraper_agent` | Navigation + extraction |
| "Scroll to load more products and extract URLs" | `scraper_agent` | Scroll for extraction purpose |
| "Scroll down to view content" (no extraction) | `browser_agent` | Pure interaction |

---

## Error Handling

**Navigation Failure**:
```yaml
{
  "success": false,
  "message": "Navigation failed",
  "error": "Failed to load https://example.com/page: Timeout after 30s",
  "current_url": "",
  "steps_executed": 0
}
```

**Unsupported Action**:
```yaml
{
  "success": false,
  "message": "Navigation failed",
  "error": "Unsupported action type: click",
  "current_url": "",
  "steps_executed": 0
}
```

---

## Example Workflow (Complete)

**Task**: Navigate from homepage to category page, then extract products

```yaml
apiVersion: "agentcrafter.io/v1"
kind: "Workflow"

metadata:
  name: "multi-step-navigation-example"
  description: "Example of BrowserAgent + ScraperAgent cooperation"

steps:
  # Step 1: Navigate to homepage (establish session)
  - id: "navigate-homepage"
    name: "Navigate to homepage"
    agent_type: "browser_agent"
    description: "Navigate to Allegro homepage"
    inputs:
      target_url: "https://allegro.pl/"
    outputs:
      result: "homepage_nav"
    timeout: 30

  # Step 2: Navigate to category page
  - id: "navigate-category"
    name: "Navigate to category"
    agent_type: "browser_agent"
    description: "Navigate to coffee category page"
    inputs:
      target_url: "https://allegro.pl/kategoria/produkty-spozywcze-kawa-74030"
    outputs:
      result: "category_nav"
    timeout: 30

  # Step 3: Extract products from current page
  - id: "extract-products"
    name: "Extract product URLs"
    agent_type: "scraper_agent"
    description: "Extract all product URLs from category page"
    inputs:
      use_current_page: true  # Use page from step 2
      extraction_method: "script"
      data_requirements:
        user_description: "Extract all coffee product URLs"
        output_format:
          url: "Product URL"
        xpath_hints:
          url: "//article//a[@class='product-link']"
    outputs:
      extracted_data: "product_urls"
    timeout: 60
```

---

**Version**: 1.0
**Last Updated**: 2025-11-02
