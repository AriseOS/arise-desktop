# TextAgent Specification

**Purpose**: Process text content using LLM for tasks requiring semantic understanding

**When to use**:
- Task requires language understanding (translation, summarization, analysis)
- Transformation cannot be done by simple code
- Input is text/data, output is semantically processed content

**When NOT to use**:
- Simple data filtering or sorting → Use `code_agent` or `variable`
- Extracting data from web pages → Use `scraper_agent`
- Data format conversion (JSON to CSV) → Use `code_agent`

---

## Basic Usage

```yaml
- id: "step-id"
  agent_type: "text_agent"
  name: "Process text"
  description: "Process text using LLM"
  inputs:
    instruction: "Translate the following text to Chinese"
    data:
      content: "{{source_variable}}"
  outputs:
    result: "processed_result"
  timeout: 60
```

---

## Input Parameters

### Required

| Parameter | Type | Description |
|-----------|------|-------------|
| `instruction` | string | Task instruction describing what to do with the data |
| `data` | object | Input data to process |

### Data Object

The `data` object should contain:

```yaml
data:
  content: "{{variable_name}}"  # The content to process
```

Or with structured data:

```yaml
data:
  content: "{{product_info}}"
  format: "json"  # Optional hint about data format
```

---

## Output Format

```yaml
{
  "result": "Processed content here...",
  "success": true
}
```

The `result` field contains the processed content from the LLM.

---

## Usage Scenarios

### Scenario 1: Translation

**Intent**: "Translate product information to Chinese"

**Workflow**:
```yaml
- id: "translate-products"
  agent_type: "text_agent"
  name: "Translate to Chinese"
  description: "Translate extracted product data to Chinese"
  inputs:
    instruction: "Translate the following product information to Chinese. Maintain the JSON structure and field names, only translate the values."
    data:
      content: "{{product_info}}"
  outputs:
    result: "translated_info"
  timeout: 60
```

### Scenario 2: Summarization

**Intent**: "Summarize the extracted reviews"

**Workflow**:
```yaml
- id: "summarize-reviews"
  agent_type: "text_agent"
  name: "Summarize reviews"
  description: "Create a summary of customer reviews"
  inputs:
    instruction: "Summarize the following customer reviews. Highlight common themes, pros, cons, and overall sentiment. Keep the summary under 200 words."
    data:
      content: "{{all_reviews}}"
  outputs:
    result: "review_summary"
  timeout: 90
```

### Scenario 3: Analysis

**Intent**: "Analyze price distribution"

**Workflow**:
```yaml
- id: "analyze-prices"
  agent_type: "text_agent"
  name: "Analyze prices"
  description: "Analyze the price distribution and patterns"
  inputs:
    instruction: "Analyze the following price data. Provide: 1) Price range (min, max, average), 2) Distribution pattern, 3) Any outliers, 4) Recommendations for a buyer."
    data:
      content: "{{all_prices}}"
  outputs:
    result: "price_analysis"
  timeout: 60
```

### Scenario 4: Content Restructuring

**Intent**: "Convert to markdown table"

**Workflow**:
```yaml
- id: "format-as-table"
  agent_type: "text_agent"
  name: "Format as table"
  description: "Convert product data to markdown table"
  inputs:
    instruction: "Convert the following product data to a markdown table with columns: Name, Price, Rating. Sort by price descending."
    data:
      content: "{{products}}"
  outputs:
    result: "products_table"
  timeout: 45
```

### Scenario 5: Sentiment Analysis

**Intent**: "Analyze sentiment of comments"

**Workflow**:
```yaml
- id: "analyze-sentiment"
  agent_type: "text_agent"
  name: "Sentiment analysis"
  description: "Analyze sentiment of user comments"
  inputs:
    instruction: "Analyze the sentiment of each comment. Return a JSON array with each comment's text and sentiment (positive/negative/neutral) and confidence score."
    data:
      content: "{{comments}}"
  outputs:
    result: "sentiment_results"
  timeout: 60
```

---

## Best Practices

### 1. Clear Instructions

Be specific about what you want:

**Good**:
```yaml
instruction: "Translate the following product names and descriptions to Spanish. Keep price values in original format. Maintain JSON structure."
```

**Bad**:
```yaml
instruction: "Translate this"
```

### 2. Specify Output Format

Tell the LLM what format you need:

```yaml
instruction: "Summarize in bullet points, maximum 5 points"
instruction: "Return as JSON with fields: summary, key_points, sentiment"
instruction: "Keep the original data structure, only translate text values"
```

### 3. Handle Structured Data

When processing JSON or structured data:

```yaml
instruction: "Process the following JSON data. Translate all string values to Chinese but keep field names in English. Preserve the array structure."
```

### 4. Set Appropriate Timeout

- Simple translation: 30-60 seconds
- Summarization: 60-90 seconds
- Complex analysis: 90-120 seconds

---

## Common Patterns

### Translation in Loop

Process each item individually:

```yaml
- id: "loop-items"
  agent_type: "foreach"
  source: "{{items}}"
  item_var: "item"
  steps:
    - id: "extract"
      agent_type: "scraper_agent"
      outputs:
        extracted_data: "item_data"

    - id: "translate"
      agent_type: "text_agent"
      inputs:
        instruction: "Translate to Chinese"
        data:
          content: "{{item_data}}"
      outputs:
        result: "translated_item"
```

### Batch Processing

Process all items at once (more efficient for small datasets):

```yaml
- id: "collect-all"
  # ... collect all items into all_items

- id: "translate-all"
  agent_type: "text_agent"
  inputs:
    instruction: "Translate all items to Chinese. Return as JSON array."
    data:
      content: "{{all_items}}"
  outputs:
    result: "all_translated"
```

---

## Limitations

- **No web access**: Cannot fetch URLs or access external resources
- **No code execution**: Cannot run code; use `code_agent` for that
- **Token limits**: Very large inputs may be truncated
- **Non-deterministic**: Results may vary slightly between runs

---

## Error Handling

**Success**:
```yaml
{
  "result": "Translated content...",
  "success": true
}
```

**Failure**:
```yaml
{
  "result": "",
  "success": false,
  "error": "Failed to process: input too large"
}
```

---

**Version**: 1.0
**Last Updated**: 2025-11-20
