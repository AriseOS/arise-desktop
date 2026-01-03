# Text Agent

**Agent Type**: `text_agent`

## What It Does

Uses LLM to generate or transform text. Good for summarizing, translating, formatting, or answering questions.

## Input Parameters

```yaml
inputs:
  instruction: "What to do"    # Required: Task description
  content: "{{input_data}}"    # Optional: Data to process
```

## Output

Output keys match what you specify in `outputs`. The LLM returns structured JSON.

```yaml
outputs:
  summary: "summary_result"     # Maps LLM output key to variable
  keywords: "keywords_result"
```

## Examples

### Summarize Content

```yaml
- id: "summarize"
  name: "Summarize Article"
  agent_type: "text_agent"
  inputs:
    instruction: "Summarize this article in 2-3 sentences"
    content: "{{article_text}}"
  outputs:
    summary: "article_summary"
```

### Extract Keywords

```yaml
- id: "extract-keywords"
  name: "Extract Keywords"
  agent_type: "text_agent"
  inputs:
    instruction: "Extract 5 main keywords from this text"
    content: "{{document}}"
  outputs:
    keywords: "document_keywords"
```

### Format Data

```yaml
- id: "format-report"
  name: "Format Report"
  agent_type: "text_agent"
  inputs:
    instruction: "Format this data as a readable report with sections"
    content: "{{raw_data}}"
  outputs:
    report: "formatted_report"
```

## When to Use

- Summarizing scraped content
- Translating text
- Reformatting data for output
- Answering questions about extracted data
- Generating descriptions from structured data
