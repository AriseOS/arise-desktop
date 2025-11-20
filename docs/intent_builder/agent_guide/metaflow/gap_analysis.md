# Gap Analysis - Inferred Node Generation

This document describes how to analyze the gap between recorded operations and user query to generate inferred nodes.

## Core Principle

The recorded operations represent what the user demonstrated (the "how").
The user_query represents what the user wants to achieve (the "what").

**Your task**: Analyze if there's a gap between what was demonstrated and what is expected.

```
Gap = Expected Result (from user_query) - Demonstrated Capability (from operations)
```

If a gap exists, you must generate inferred nodes to bridge it.

## Analysis Process

### Step 1: Identify What Recorded Operations Produce

- What is the final output? (e.g., raw product data in English)
- What form is the data in? (list, single object, text)

### Step 2: Identify What User Query Expects

- What does the user want as the end result? (e.g., translated product data)
- Is there any transformation implied?

### Step 3: Identify Sub-goals Without Recorded Steps

- Does the user_query mention a task that has no corresponding operations?
- Would this task require exploratory actions?

### Step 4: Generate Inferred Nodes

- Mark them with `(Inferred)` in intent_description
- Use appropriate operation types
- Place them at the correct position in the flow

## Types of Gaps

### A. Data Transformation Gap

**When to detect**: The user_query implies that extracted data needs semantic-level processing that requires language understanding.

**Signs**:
- The recorded operations extract data, but the query expects transformed data
- The transformation requires understanding meaning (not just reformatting)

**Examples of semantic transformations**:
- Translation between languages
- Summarization of content
- Analysis of patterns or trends
- Sentiment analysis
- Content restructuring

**Generated Node**:
```yaml
- id: node_inferred_process
  intent_id: inferred_text_process
  intent_name: "ProcessData"
  intent_description: "Process extracted data as specified (Inferred)"
  operations:
    - type: text_process
      params:
        source: "{{extracted_data}}"
  outputs:
    processed_data: "processed_data"
```

### B. Unrecorded Sub-goal Gap

**When to detect**: The user_query describes a sub-goal that has no corresponding recorded operations.

**Signs**:
- A task is mentioned but there are no operations showing how to do it
- The task would require exploring/searching on web pages
- Cannot be done with fixed URLs or xpaths from the recording

**Generated Node**:
```yaml
- id: node_inferred_autonomous
  intent_id: inferred_autonomous
  intent_name: "CompleteTask"
  intent_description: "Achieve the unrecorded goal (Inferred)"
  operations:
    - type: autonomous_task
      params:
        goal: "description of what to achieve"
  outputs:
    result: "task_result"
```

### C. Loop Requirement Gap

**When to detect**: The user query indicates processing "all" items, but only a single item was demonstrated.

**Signs**:
- Keywords like "all", "every", "each", "所有", "全部"
- No list extraction in recorded operations

**Generated Node** (implicit list extraction):
```yaml
- id: node_implicit
  intent_id: implicit_extract_list
  intent_name: "ExtractItemList"
  intent_description: "Extract list of items (inferred node)"
  operations:
    - type: extract
      target: "item_urls"
      element:
        xpath: "<PLACEHOLDER>"
      value: []
  outputs:
    item_urls: "item_urls"
```

## Examples

### Example 1: Translation Gap

**Input**:
```
Recorded: navigate → extract product data
Query: "Collect products and translate to Chinese"
```

**Analysis**:
- Output of operations: English product data
- Expected result: Chinese product data
- Gap: Translation needed (semantic transformation)
- Action: Add text processing node after extraction

**Generated MetaFlow**:
```yaml
nodes:
  - id: node_1
    # ... navigate node
  - id: node_2
    # ... extract node
    outputs:
      product_data: "product_data"
  - id: node_3  # Inferred
    intent_id: inferred_text_process
    intent_name: "TranslateProducts"
    intent_description: "Translate product data to Chinese (Inferred)"
    operations:
      - type: text_process
        params:
          source: "{{product_data}}"
    outputs:
      translated_data: "translated_data"
```

### Example 2: Analysis Gap

**Input**:
```
Recorded: navigate → loop → extract prices
Query: "Get prices and analyze the distribution"
```

**Analysis**:
- Output of operations: List of prices
- Expected result: Analysis of price patterns
- Gap: Analysis needed (requires understanding data patterns)
- Action: Add text processing node for analysis

**Generated MetaFlow**:
```yaml
nodes:
  - id: node_1
    # ... navigate and extract loop
    outputs:
      all_prices: "all_prices"
  - id: node_2  # Inferred
    intent_id: inferred_text_process
    intent_name: "AnalyzePrices"
    intent_description: "Analyze price distribution and patterns (Inferred)"
    operations:
      - type: text_process
        params:
          source: "{{all_prices}}"
    outputs:
      price_analysis: "price_analysis"
```

### Example 3: Unrecorded Task

**Input**:
```
Recorded: navigate to company page → extract info
Query: "Get company info and find CEO's LinkedIn"
```

**Analysis**:
- Recorded operations only cover company info extraction
- "Find CEO LinkedIn" has no recorded steps
- Gap: Exploration task needed
- Action: Add autonomous task node

**Generated MetaFlow**:
```yaml
nodes:
  - id: node_1
    # ... navigate node
  - id: node_2
    # ... extract company info
    outputs:
      company_info: "company_info"
  - id: node_3  # Inferred
    intent_id: inferred_autonomous
    intent_name: "FindCEOLinkedIn"
    intent_description: "Find CEO LinkedIn profile (Inferred)"
    operations:
      - type: autonomous_task
        params:
          goal: "Find the CEO's LinkedIn profile starting from company page"
    outputs:
      ceo_linkedin: "ceo_linkedin"
```

### Example 4: No Gap

**Input**:
```
Recorded: navigate → extract → store
Query: "Collect products and save"
```

**Analysis**:
- Output: Data saved to storage
- Expected: Data saved
- Gap: None
- Action: No inferred nodes needed

## Node Placement

### Text Processing Nodes

Place immediately after the node that produces the data to be processed:

```yaml
- id: node_extract
  outputs:
    raw_data: "raw_data"
- id: node_process  # Inferred, placed right after
  intent_description: "... (Inferred)"
  operations:
    - type: text_process
      params:
        source: "{{raw_data}}"
```

### Autonomous Task Nodes

Place at the point in the flow where the task should occur:
- If it depends on previous data, place after that data is available
- If it's independent, place at the logical point in user's goal

### Inside Loops

If processing should happen for each item:

```yaml
- id: loop_node
  type: loop
  children:
    - id: extract_item
      outputs:
        item_data: "item_data"
    - id: process_item  # Inferred, inside loop
      intent_description: "... (Inferred)"
```

If processing should happen after all items are collected:

```yaml
- id: loop_node
  type: loop
  # ... collect all items
- id: process_all  # Inferred, outside loop
  intent_description: "... (Inferred)"
```

## Important Notes

1. **Only add inferred nodes when there is a genuine gap** - if the recorded operations already achieve the goal, do not add extra nodes

2. **Always mark with `(Inferred)`** - this tells WorkflowGenerator to use appropriate agent types

3. **Be specific in descriptions** - the intent_description should clearly state what transformation or task is needed

4. **Consider data flow** - ensure the inferred node has access to the data it needs and produces output for subsequent nodes

5. **Don't over-infer** - only add nodes for explicitly stated requirements in the user query
