---
name: workflow-generation
description: Generate workflows from user's recorded browser actions.
---

# Workflow Generation

## Context: App Environment

Workflows run inside a desktop app. Understanding this environment helps you generate correct workflows:

- **User records browser actions** → converted to intent operations (your input)
- **You generate a workflow YAML** → the app executes it
- **`storage_agent` stores data** → user can view and export data directly in the app UI
- **No export steps needed in workflow** → the app provides export functionality (CSV, Excel, etc.)

This means: use `storage_agent` with `operation: store` to save extracted data. The user will access and export it through the app interface.

## IMPORTANT: Output Contract

**All agents output to `result` key**. Always use `outputs: {result: variable_name}`:

```yaml
# Step 1: Extract data
- id: extract
  agent: scraper_agent
  inputs:
    data_requirements:
      user_description: "Extract products"
      output_format:
        name: "Name"
        url: "URL"
  outputs:
    result: products              # → context.variables["products"] = List[Dict]

# Step 2: Reference in next step's inputs
- id: navigate
  agent: browser_agent
  inputs:
    target_url: "{{products.0.url}}"   # Reference: {{variable_name.field}}
```

**Key points**:
1. `outputs: {result: X}` stores Agent output in variable `X`
2. Reference in inputs: `"{{X}}"` or `"{{X.0.field}}"`
3. **Do NOT use** agent-specific keys like `extracted_data`. Always use `result`.

## Goal

Convert user's recorded browser actions (intent operations) into a replayable Workflow YAML.

**Key principle**: The workflow **replays** the user's recorded actions. Use the available agents to navigate, interact, extract data, and store results.

## Input: Intent Operations

Each intent contains operations. Each operation has:
- `type`: click, scroll, extract, navigate, input, select
- `url`: Page URL when action occurred
- `dom_id`: Hash ID (12 chars) linking to DOM snapshot file, null if no DOM captured
- `element`: Contains `xpath`, `href`, `tagName`, `textContent`

### Using DOM Snapshots

Each operation has a `dom_id` field pointing to the DOM snapshot captured at that URL.
The DOM file is located at `dom_snapshots/{dom_id}.json`.

To generate accurate scripts:
1. Check if operation has `dom_id` (not null)
2. Read the DOM file at `dom_snapshots/{dom_id}.json`
3. Match `element.xpath` in the DOM to find `interactive_index`
4. If element not found in DOM (hover/popup), use fallback strategy

See: `references/recording_format.md` for full format specification.

## Output: Workflow YAML (v2)

```yaml
apiVersion: "ami.io/v2"
name: workflow-name
description: "What this workflow does"

steps:
  - id: step-id
    name: "Human-readable step name"  # REQUIRED - every step must have a name
    agent: agent_type
    inputs: {...}
    outputs:                          # OPTIONAL - omit if no output needed
      result: variable_name
```

**Required step fields**: `id`, `name`, `agent`

**outputs field rules**:
- If step produces output you want to reference later: `outputs: {result: variable_name}`
- If step doesn't need output: **omit the outputs field entirely** (do NOT write `outputs: null`)

## Mapping Rules

| Operation | Workflow Step |
|-----------|---------------|
| click (no href) | `browser_agent` + `interaction_steps` |
| click (with href) | `scraper_agent` extract URL + `browser_agent` navigate |
| extract | `scraper_agent` |
| scroll | `browser_agent` + `interaction_steps` |
| navigate | `browser_agent` + `target_url` |
| summarize/transform text | `text_agent` |
| web search (no specific search recorded) | `tavily_agent` |

### When to use tavily_agent

Use `tavily_agent` when:
- User query requires searching/retrieving information from the web
- BUT the intent operations do NOT show a specific search approach (e.g., no Google search, no website search box interaction recorded)

**Example scenarios:**
- User query: "Search for the latest AI news" + No search operations in intents → Use `tavily_agent`
- User query: "Find top 10 products" + Intent shows user searched on Google → Use recorded browser operations
- User query: "Get recent tech news" + Intent shows user browsed a news website → Use recorded browser operations

```yaml
# When user needs web search but didn't record a specific search method
- id: search-web
  agent: tavily_agent
  inputs:
    operation: search
    query: "AI news"           # Derived from user query
    max_results: 10
    days: 3                    # For recent content
    topic: news                # If searching news
  outputs:
    result: search_results
```

**tavily_agent output structure** - for using results in subsequent steps:

```yaml
# search_results contains:
{
  query: "AI news",
  results: [                          # Array of search results
    {
      title: "Article Title",
      url: "https://example.com/...",
      content: "Snippet text...",     # Page excerpt
      score: 0.95,                    # Relevance score
      published_date: "2024-01-15"    # Optional
    },
    ...
  ],
  answer: "...",                      # Optional: if include_answer=true
  images: [...]                       # Optional: if include_images=true
}

# Common access patterns:
# - "{{search_results.results}}"        → Full results array
# - "{{search_results.results.0.url}}"  → First result's URL
# - "{{search_results.results.0.title}}" → First result's title
# - "{{search_results.answer}}"         → AI-generated answer (if requested)
```

## text_agent

Use `text_agent` for LLM-based text generation or transformation tasks (summarize, translate, analyze, etc.).

**Required field**: `instruction` - MUST be provided, otherwise validation fails.

```yaml
- id: generate-summary
  name: "Generate summary from extracted data"
  agent: text_agent
  inputs:
    instruction: "Summarize the main points"  # REQUIRED - task instruction for LLM
    data:                                      # Optional - input data for context
      content: "{{extracted_text}}"
  outputs:
    result: summary                            # Dict (LLM response)
```

**Common use cases**:
- Summarize extracted content: `instruction: "Summarize this article"`
- Transform data format: `instruction: "Convert to bullet points"`
- Generate descriptions: `instruction: "Write a brief description"`

## Scroll Operations

**CRITICAL**: `browser_agent` does NOT support `instruction` field. Use `interaction_steps` with `task` and `xpath_hints`.

For scroll operations, use `interaction_steps` with empty `xpath_hints`:

```yaml
# Scroll down once
- id: scroll-page
  name: "Scroll down the page"
  agent: browser_agent
  inputs:
    interaction_steps:
      - task: "Scroll down the page"
        xpath_hints: {}       # Empty dict for simple scroll
        text: "down"          # "down" or "up"

# Scroll multiple times (e.g., 3 times to load more content)
- id: scroll-to-load-more
  name: "Scroll down 3 times to load more products"
  agent: browser_agent
  inputs:
    interaction_steps:
      - task: "Scroll down the page"
        xpath_hints: {}
        text: "down"
      - task: "Scroll down the page"
        xpath_hints: {}
        text: "down"
      - task: "Scroll down the page"
        xpath_hints: {}
        text: "down"
```

**Important**:
- Each `interaction_steps` item MUST have `task` (string) and `xpath_hints` (dict)
- For simple scroll: use empty `xpath_hints: {}`
- For scroll to element: provide xpath hints to locate the target element
- `text` field: "down", "up", or pixel amount (e.g., "500")

## Key Rule: Click with href

When click element has href, use **two steps**:

```yaml
# Given operation with element.xpath = "//*[@id=\"app\"]/nav/a[2]"

# Step 1: Extract link URL
- id: extract-link-url
  agent: scraper_agent
  inputs:
    extraction_method: script
    dom_scope: full
    data_requirements:
      user_description: "Extract the link URL"
      output_format:
        url: "Link href"
      xpath_hints:
        url: "//*[@id=\"app\"]/nav/a[2]"  # Use exact xpath from operation
  outputs:
    result: link_info                    # Use "result" key

# Step 2: Navigate
- id: navigate-to-link
  agent: browser_agent
  inputs:
    target_url: "{{link_info.0.url}}"
```

**Do NOT** use `browser_agent` `interaction_steps` for click + navigate.

## Script Generation Integration

After workflow generation, scripts are automatically generated for:
- `browser_agent` with `interaction_steps`: generates `find_element.py`
- `scraper_agent` with `extraction_method: script`: generates `extraction_script.py`

### When Script Generation May Fail

Script generation uses DOM snapshots captured during recording. It may fail when:
1. **Hover/dropdown elements**: The element is inside a hover menu (not visible in initial DOM)
2. **Dynamic content**: The element is loaded after JavaScript execution
3. **Incorrect selectors**: The xpath doesn't match any element in the DOM

### Fallback Strategy

If script generation fails for a step, modify the workflow:

**For hover menu clicks** → Use scraper_agent to extract URL, then browser_agent to navigate:
```yaml
# Instead of: browser_agent click on hover menu item
# Use the xpath from the original operation:
- id: extract-menu-link
  agent: scraper_agent
  inputs:
    extraction_method: script
    data_requirements:
      user_description: "Extract the menu item link URL"
      output_format:
        url: "Menu item href"
      xpath_hints:
        url: "//*[@id=\"app\"]/nav/ul/li[3]/a"  # Use exact xpath from operation
  outputs:
    result: menu_link                           # Use "result" key

- id: navigate-to-target
  agent: browser_agent
  inputs:
    target_url: "{{menu_link.0.url}}"
```

**For dynamic content** → Add explicit navigation or wait steps before extraction.

## Constraints

- `xpath_hints` must be **dict**: `{key: "//xpath"}`, NOT list
- Workflow runs from blank browser - include full path
- Use original URL/href from operation, never simplify
- For loops ("all items", "each product"), use `foreach`
- **NEVER write `outputs: null`** - if a step doesn't need output, simply omit the `outputs` field
- **No export steps needed** - the app handles data export. Do NOT add `storage_agent` with `operation: export` unless user explicitly asks for it. However, if you need to accumulate data across multiple iterations (e.g., in a foreach loop), you MUST use `storage_agent` with `operation: store` to persist each item.

### foreach Syntax

**CRITICAL**: `foreach` value must be a YAML list, NOT a quoted string.

```yaml
# ✅ Variable reference
- foreach: "{{extracted_items}}"
  as: item

# ✅ Literal list - NO QUOTES
- foreach: [1, 2, 3, 4, 5]
  as: page_num

# ❌ WRONG - quotes make it a string, causes runtime error
- foreach: "[1, 2, 3]"
```

## CRITICAL: xpath_hints Rule

**ONLY use xpaths from the operation's `element.xpath` field. NEVER construct or invent new xpaths.**

The `xpath_hints` values MUST come directly from recorded operations. This is critical for script pre-generation to match DOM snapshots.

```yaml
# If operation has element.xpath = "//*[@id=\"app\"]/main/div[2]/a[1]"
xpath_hints:
  url: "//*[@id=\"app\"]/main/div[2]/a[1]"  # Use exact xpath from operation
```

For list extraction, use the xpath from the **first item's operation** (with index like `a[1]`). The script generator will automatically find the container.

## Variable Syntax

```yaml
"{{variable}}"           # Simple reference
"{{object.field}}"       # Object field
"{{list.0.field}}"       # First item of list
```

## Example

**Intent operations**:
```yaml
- type: click
  url: "https://shop.com"
  element:
    xpath: "//*[@id=\"app\"]/nav/a[2]"
    href: "https://shop.com/products"
    textContent: "Products"
- type: click
  url: "https://shop.com/products"
  element:
    xpath: "//*[@id=\"app\"]/main/div[2]/a[1]/h3"
    textContent: "Product A"
```

**Generated workflow**:
```yaml
apiVersion: "ami.io/v2"
name: extract-products
description: "Extract products from shop"

steps:
  - id: extract-products-link
    name: "Extract Products link URL"
    agent: scraper_agent
    inputs:
      extraction_method: script
      dom_scope: full
      data_requirements:
        user_description: "Extract Products link URL"
        output_format:
          url: "Link href"
        xpath_hints:
          url: "//*[@id=\"app\"]/nav/a[2]"  # Use exact xpath from operation
    outputs:
      result: products_link                  # Use "result" key

  - id: navigate-to-products
    name: "Navigate to products page"
    agent: browser_agent
    inputs:
      target_url: "{{products_link.0.url}}"

  - id: extract-products
    name: "Extract product list"
    agent: scraper_agent
    inputs:
      extraction_method: script
      dom_scope: full
      data_requirements:
        user_description: "Extract product list"
        output_format:
          name: "Product name"
          url: "Product URL"
        xpath_hints:
          name: "//*[@id=\"app\"]/main/div[2]/a[1]/h3"  # Use exact xpath from operation
    outputs:
      result: product_list                   # Use "result" key
```
