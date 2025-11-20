# AutonomousBrowserAgent Specification

**Purpose**: Autonomously navigate and interact with web pages to achieve a goal without pre-defined steps

**When to use**:
- Task has a clear goal but no recorded steps
- MetaFlow node is marked with `(Inferred)` in intent_description
- Task requires exploratory actions (searching, finding information)

**When NOT to use**:
- Steps are known and can be scripted → Use `browser_agent` + `scraper_agent`
- Simple navigation with known URL → Use `browser_agent`
- Data extraction with known xpaths → Use `scraper_agent`

---

## Basic Usage

```yaml
- id: "step-id"
  agent_type: "autonomous_browser_agent"
  name: "Find information"
  description: "Autonomously find target information"
  inputs:
    task: "Find the CEO's LinkedIn profile starting from the company About page"
    max_actions: 20
  outputs:
    result: "task_result"
  timeout: 120
```

---

## Input Parameters

### Required

| Parameter | Type | Description |
|-----------|------|-------------|
| `task` | string | Natural language description of what to accomplish |

### Optional

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_actions` | integer | 20 | Maximum number of actions before stopping |
| `timeout` | integer | 120 | Timeout in seconds |

---

## Task Description Guidelines

### Be Specific About the Goal

**Good**:
```yaml
task: "Find the CEO's LinkedIn profile. Look for team/about pages first, then search for LinkedIn links or names to search on LinkedIn."
```

**Bad**:
```yaml
task: "Find LinkedIn"
```

### Provide Context

**Good**:
```yaml
task: "Starting from the current company page, find the pricing information. Check navigation menu, footer links, or look for 'Pricing' buttons."
```

### Set Reasonable Boundaries

**Good**:
```yaml
task: "Find the contact email on this website. Only search within this domain, do not navigate to external sites."
```

---

## Output Format

```yaml
{
  "success": true,
  "result": "Found CEO LinkedIn: https://linkedin.com/in/john-doe",
  "actions_taken": 8,
  "final_url": "https://linkedin.com/in/john-doe"
}
```

**Output Fields**:
- `success`: Whether the task was completed
- `result`: The found information or completion status
- `actions_taken`: Number of actions performed
- `final_url`: URL where the agent ended up

---

## Usage Scenarios

### Scenario 1: Find Contact Information

**Intent**: "Find company contact email (Inferred)"

**Workflow**:
```yaml
- id: "find-contact"
  agent_type: "autonomous_browser_agent"
  name: "Find contact email"
  description: "Find company contact information"
  inputs:
    task: "Find the company contact email address. Check the Contact page, About page, or footer. Return the email address."
    max_actions: 15
  outputs:
    result: "contact_info"
  timeout: 90
```

### Scenario 2: Find Social Media Links

**Intent**: "Find CEO LinkedIn profile (Inferred)"

**Workflow**:
```yaml
- id: "find-linkedin"
  agent_type: "autonomous_browser_agent"
  name: "Find CEO LinkedIn"
  description: "Find the CEO's LinkedIn profile"
  inputs:
    task: "Find the CEO or founder's LinkedIn profile. First look for Team/About pages to find the CEO name, then search for their LinkedIn link on the page or search LinkedIn directly."
    max_actions: 20
  outputs:
    result: "ceo_linkedin"
  timeout: 120
```

### Scenario 3: Fill Out a Form

**Intent**: "Submit contact form with inquiry (Inferred)"

**Workflow**:
```yaml
- id: "fill-form"
  agent_type: "autonomous_browser_agent"
  name: "Fill contact form"
  description: "Fill and submit the contact form"
  inputs:
    task: "Find the contact form and fill it with: Name='John Doe', Email='john@example.com', Message='I am interested in your enterprise plan'. Then submit the form."
    max_actions: 15
  outputs:
    result: "form_result"
  timeout: 90
```

### Scenario 4: Search for Specific Information

**Intent**: "Find product specifications (Inferred)"

**Workflow**:
```yaml
- id: "find-specs"
  agent_type: "autonomous_browser_agent"
  name: "Find specifications"
  description: "Find detailed product specifications"
  inputs:
    task: "Find the detailed technical specifications for this product. Look for tabs like 'Specifications', 'Tech Specs', or expandable sections. Extract: dimensions, weight, material, and warranty information."
    max_actions: 10
  outputs:
    result: "product_specs"
  timeout: 60
```

---

## When to Use vs Other Agents

### Use autonomous_browser_agent

- "Find the pricing page" (location unknown)
- "Search for reviews of this product"
- "Fill out the registration form"
- "Find the CEO's contact information"

### Use browser_agent + scraper_agent instead

- Navigate to known URL and extract data
- Click known button and extract result
- Any task where steps are recorded/known

---

## Best Practices

### 1. Set Appropriate max_actions

- Simple find task: 10-15 actions
- Complex multi-step task: 20-30 actions
- Don't set too high (wastes resources)

### 2. Provide Starting Context

If the browser is already on a relevant page:

```yaml
task: "Starting from the current product page, find the manufacturer's official website link"
```

### 3. Specify What to Return

```yaml
task: "Find the shipping cost for US orders. Return the cost as a number (e.g., '9.99')"
```

### 4. Set Boundaries

```yaml
task: "Find pricing information. Only check pages within the same domain, do not follow external links."
```

---

## Limitations

- **Non-deterministic**: May take different paths each time
- **Resource intensive**: Uses more tokens and time than deterministic agents
- **May fail**: Complex tasks might not complete within max_actions
- **No guarantee**: Cannot guarantee finding information if it doesn't exist

---

## Error Handling

**Success**:
```yaml
{
  "success": true,
  "result": "Found: $99/month for Pro plan",
  "actions_taken": 12,
  "final_url": "https://example.com/pricing"
}
```

**Failure - Max Actions Reached**:
```yaml
{
  "success": false,
  "result": "Could not find pricing information within 20 actions",
  "actions_taken": 20,
  "final_url": "https://example.com/products"
}
```

**Failure - Task Not Possible**:
```yaml
{
  "success": false,
  "result": "No contact form found on this website",
  "actions_taken": 8,
  "final_url": "https://example.com/about"
}
```

---

## Integration with Other Agents

### After Extraction

Use autonomous agent to find related information:

```yaml
steps:
  - id: "extract-company"
    agent_type: "scraper_agent"
    outputs:
      extracted_data: "company_info"

  - id: "find-linkedin"
    agent_type: "autonomous_browser_agent"
    inputs:
      task: "Find the LinkedIn page for {{company_info.name}}"
    outputs:
      result: "linkedin_url"
```

### Before Storage

Gather additional information before saving:

```yaml
steps:
  - id: "find-contact"
    agent_type: "autonomous_browser_agent"
    inputs:
      task: "Find contact email"
    outputs:
      result: "contact"

  - id: "store"
    agent_type: "storage_agent"
    inputs:
      data:
        company: "{{company_name}}"
        contact: "{{contact}}"
```

---

**Version**: 1.0
**Last Updated**: 2025-11-20
