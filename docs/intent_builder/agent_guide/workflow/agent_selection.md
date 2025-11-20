# Agent Type Selection Principles

This document describes how to choose the appropriate agent type when converting MetaFlow nodes to Workflow steps.

## Core Principle

Choose agents based on **what the task fundamentally requires**, not based on keywords in the description.

Each agent has specific capabilities and limitations. Understanding these helps you make the right choice.

## Agent Capabilities Overview

### browser_agent - Browser Control

**Capability**: Control the browser to navigate to URLs and interact with pages (scroll, wait)

**Cannot**: Extract or process data

**Use when**: The task requires moving to a different page or triggering page interactions

**Inputs**: `target_url` for navigation, `interaction_steps` for interactions like scroll

### scraper_agent - Data Extraction

**Capability**: Extract structured data from the current page using scripts or LLM

**Cannot**: Navigate to other pages or perform interactions

**Use when**: The task requires getting data from the page the browser is currently on

**Inputs**: `data_requirements` with extraction specifications

### text_agent - Semantic Text Processing

**Capability**: Process text using LLM for tasks requiring language understanding

**Cannot**: Access web pages or interact with browser

**Use when**: The task requires transforming data in ways that need semantic understanding
- The transformation cannot be done by simple code (not just reformatting or filtering)
- Examples: translating between languages, summarizing content, analyzing patterns/sentiment, generating insights

**Inputs**: `instruction` describing the processing task, `data` containing the content

### autonomous_browser_agent - Exploratory Web Tasks

**Capability**: Autonomously navigate and interact with web pages to achieve a goal

**Cannot**: Work with pre-defined paths; it explores and decides actions itself

**Use when**: The task has a clear goal but no recorded steps to achieve it
- The MetaFlow node is marked with `(Inferred)` in intent_description
- The operations don't provide enough information to construct deterministic steps

**Inputs**: `task` describing the goal, `max_actions` limiting exploration steps

### storage_agent - Data Persistence

**Capability**: Store data to database or export to files

**Cannot**: Process or transform data

**Use when**: The task requires saving extracted data

### variable - Variable Management

**Capability**: Set, append, or manipulate workflow variables

**Cannot**: Process data semantically or access external resources

**Use when**: The task requires simple data operations (initialize lists, append items, set values)

## Decision Framework

When mapping a MetaFlow node to workflow steps, analyze:

### 1. What operations does the node contain?

| Operation Type | Agent Type |
|---------------|------------|
| `navigate` | browser_agent |
| `click` (for navigation) | browser_agent (or extract link + navigate) |
| `scroll` | browser_agent with `interaction_steps` |
| `extract` | scraper_agent |
| `store` | storage_agent |
| `text_process` | text_agent |
| `autonomous_task` | autonomous_browser_agent |

### 2. Does the node require multiple capabilities?

If yes, generate multiple steps in sequence.

**Example**: MetaFlow node with navigate + extract

```yaml
# MetaFlow
operations:
  - type: navigate
    url: "https://example.com"
  - type: extract
    target: "data"

# Workflow: TWO steps
- id: "navigate-to-page"
  agent_type: "browser_agent"
  inputs:
    target_url: "https://example.com"

- id: "extract-data"
  agent_type: "scraper_agent"
  inputs:
    extraction_method: "script"
    data_requirements: ...
```

### 3. Is the node marked as `(Inferred)`?

Check the `intent_description` for the `(Inferred)` marker:

- If it's an autonomous exploration task → `autonomous_browser_agent`
- If it's text processing → `text_agent`

### 4. What is the semantic goal of the intent?

| Goal | Agent Type |
|------|------------|
| Moving to a location | browser_agent |
| Getting data from current location | scraper_agent |
| Transforming data semantically | text_agent |
| Exploring to achieve a goal | autonomous_browser_agent |
| Storing data | storage_agent |

## Important Patterns

### Separation of Concerns

**Critical**: browser_agent handles navigation, scraper_agent handles extraction.

- Never skip navigation steps - they maintain session state
- scraper_agent always works on the current page
- If you need data from a different page, navigate first

### Click → Navigate Pattern

When MetaFlow shows click followed by navigate, generate two steps:

1. **Extract the link** using scraper_agent
2. **Navigate** using browser_agent with the extracted URL

```yaml
# Step 1: Extract link from current page
- id: "extract-link"
  agent_type: "scraper_agent"
  inputs:
    data_requirements:
      xpath_hints:
        url: "//a[@class='target-link']"
  outputs:
    extracted_data: "link_data"

# Step 2: Navigate to extracted URL
- id: "navigate-to-target"
  agent_type: "browser_agent"
  inputs:
    target_url: "{{link_data.url}}"
```

**Why**: The URL may contain dynamic parts (dates, IDs). Extracting it ensures correctness.

### Scroll Operations

Use browser_agent with `interaction_steps`, NOT just `target_url`:

```yaml
# CORRECT - scroll on current page
- id: "scroll-to-load"
  agent_type: "browser_agent"
  inputs:
    interaction_steps:
      - action_type: "scroll"
        parameters:
          down: true
          num_pages: 5

# WRONG - this just navigates, doesn't scroll
- id: "scroll-to-load"
  agent_type: "browser_agent"
  inputs:
    target_url: "{{url}}"
```

If already on the page, do NOT provide `target_url` (would reload and lose state).

### Navigation + Scroll

If you need to navigate AND scroll:

```yaml
- id: "navigate-and-scroll"
  agent_type: "browser_agent"
  inputs:
    target_url: "https://example.com"
    interaction_steps:
      - action_type: "scroll"
        parameters:
          down: true
          num_pages: 3
```

## Common Mistakes

### 1. Using scraper_agent for navigation

**Wrong**: Expecting scraper_agent to navigate
```yaml
- agent_type: "scraper_agent"
  inputs:
    target_path: "https://example.com"  # NO - scraper has no navigation
```

**Correct**: Use browser_agent first
```yaml
- agent_type: "browser_agent"
  inputs:
    target_url: "https://example.com"

- agent_type: "scraper_agent"
  # extracts from current page
```

### 2. Skipping navigation steps

**Wrong**: Jump directly to extraction
```yaml
# Missing navigation!
- agent_type: "scraper_agent"
  # What page are we on?
```

**Correct**: Always navigate first
```yaml
- agent_type: "browser_agent"
  inputs:
    target_url: "{{target_url}}"

- agent_type: "scraper_agent"
```

### 3. Using text_agent for simple operations

**Wrong**: Using text_agent for data filtering
```yaml
- agent_type: "text_agent"
  inputs:
    instruction: "Filter items where price > 100"
```

**Correct**: Use code_agent or variable operations for simple logic

### 4. Using autonomous_browser_agent unnecessarily

**Wrong**: Using autonomous for tasks with known steps
```yaml
- agent_type: "autonomous_browser_agent"
  inputs:
    task: "Click the login button"  # We know the xpath!
```

**Correct**: Use browser_agent with specific action
```yaml
- agent_type: "browser_agent"
  inputs:
    target_url: "{{login_url}}"
```

### 5. Providing target_url when only scrolling

**Wrong**: This navigates instead of scrolling
```yaml
- agent_type: "browser_agent"
  inputs:
    target_url: "{{current_page}}"  # Reloads the page!
```

**Correct**: Only use interaction_steps for scroll
```yaml
- agent_type: "browser_agent"
  inputs:
    interaction_steps:
      - action_type: "scroll"
        parameters:
          down: true
          num_pages: 5
```

## Summary Table

| Task | Agent | Key Input |
|------|-------|-----------|
| Go to URL | browser_agent | `target_url` |
| Scroll page | browser_agent | `interaction_steps` |
| Extract data | scraper_agent | `data_requirements` |
| Translate text | text_agent | `instruction`, `data` |
| Summarize content | text_agent | `instruction`, `data` |
| Find something (no steps) | autonomous_browser_agent | `task`, `max_actions` |
| Save to database | storage_agent | `operation`, `collection`, `data` |
| Set/append variable | variable | `operation`, `data` |
| Loop over list | foreach | `source`, `item_var`, `steps` |
