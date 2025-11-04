# Scraping Workflow Design Discussion

> **Status**: In Discussion
> **Created**: 2025-10-29
> **Participants**: User, Claude Code

## Background

We are designing a workflow system that can convert user browser operations (recorded in `user_operations.json`) into executable workflows for data scraping tasks.

**Example scenario**: Scraping Product Hunt product information
- User operations: Navigate → Click product → Select name → Click Team tab → Select team info → Click Awards tab → Select awards
- Goal: Extract product name, team members, and awards information

## Key Questions Under Discussion

### 1. Operation Semantics Understanding

**Context**: From `user_operations.json`, we have operations like:
- `click` - User clicked an element
- `select` - User selected text
- `navigate` - Page navigation occurred

#### Question 1.1: How to distinguish click intentions at Intent level?

**Scenario examples**:
- Click to navigate to new page (e.g., click product → enter detail page)
- Click to reveal hidden content (e.g., click Team tab → show team section)
- Click as user mistake (duplicate clicks)

**Options**:
- A. Use heuristics (URL change = navigation, no URL change = reveal)
- B. Use LLM to infer intention from context
- C. Track DOM changes after click
- D. Other?

**Discussion**:
[To be filled]

**Decision**:
[To be decided]

---

#### Question 1.2: What is the semantic meaning of `select` operation?

**Options**:
- A. Marker indicating "user wants this data"
- B. Just recording that user selected text (no special meaning)
- C. Represents the target data for extraction
- D. Other?

**Follow-up**: If user doesn't perform `select` operations, how do we know what data to extract?

**Discussion**:
[To be filled]

**Decision**:
[To be decided]

---

### 2. Data Extraction Boundaries

**Context**: Product Hunt example
```
Operation sequence: Navigate → Click product → Select product name → Click Team → Select team info → Click Awards → Select awards
```

#### Question 2.1: What is the scope of one scraping task?

**Option A - One large task**:
Extract all product information (name + team + awards) in a single task

**Option B - Multiple small tasks**:
Three separate tasks: extract name, extract team, extract awards

**Implications**:
- Option A: Simpler workflow, but complex agent input
- Option B: More workflow steps, but simpler agent logic

**Discussion**:
[To be filled]

**Decision**:
[To be decided]

---

#### Question 2.2: If Option A (one large task), what should the structure be?

**Sub-question**: Should interaction steps be part of ScraperAgent input, or separate workflow steps?

**Option A - ScraperAgent handles all interactions**:
```yaml
- step_id: extract_product_info
  agent_type: scraper
  input:
    interaction_steps: [navigate, click_product, click_team, click_awards]
    data_requirements: [product_name, team_members, awards]
```

**Option B - Separate workflow steps**:
```yaml
- step_id: navigate_to_product
  agent_type: navigator

- step_id: show_team_section
  agent_type: browser_operator
  input: {action: click, target: "Team tab"}

- step_id: extract_team_info
  agent_type: scraper
  input: {data_requirements: ...}
```

**Discussion**:
[To be filled]

**Decision**:
[To be decided]

---

### 3. Workflow Granularity

#### Question 3.1: Should workflow be coarse-grained or fine-grained?

**Coarse-grained (Option A)**:
- Single ScraperAgent step containing all interactions
- Pros: Simple workflow, self-contained logic
- Cons: Complex agent implementation, harder to debug

**Fine-grained (Option B)**:
- Multiple steps (Navigate, Click, Scrape, etc.)
- Pros: Modular, easier to debug, reusable components
- Cons: More complex workflow, coordination overhead

**Discussion**:
[To be filled]

**Decision**:
[To be decided]

---

#### Question 3.2: What is your preference and why?

**Considerations**:
- Debuggability
- Reusability
- Maintainability
- Performance
- Error handling

**Discussion**:
[To be filled]

**Decision**:
[To be decided]

---

### 4. Operation Executability

**Context**: Current ScraperAgent (line 350-397) uses **index** to locate elements:
```python
ClickElementAction(index=123)
```

But `user_operations.json` records **xpath**:
```json
{"xpath": "//*[@id='team-tab']"}
```

#### Question 4.1: What element location method should workflows use?

**Options**:
- A. XPath (precise but brittle)
- B. CSS Selector
- C. Index (browser-use approach)
- D. Text content ("click button containing 'Team'")
- E. Semantic description ("click the team tab")
- F. Combination of the above?

**Trade-offs**:
- Precision vs. Robustness
- Speed vs. Reliability
- Maintainability

**Discussion**:
[To be filled]

**Decision**:
[To be decided]

---

#### Question 4.2: When page structure changes (e.g., product order changed), workflow should:

**Options**:
- A. Fail with error message
- B. Attempt intelligent adaptation (find by text/semantic)
- C. Use fallback strategies (try XPath → try text → try LLM)
- D. Other?

**Discussion**:
[To be filled]

**Decision**:
[To be decided]

---

### 5. Intent Builder Responsibilities

#### Question 5.1: How should Intent Builder understand operation sequences?

**Context**: From `user_operations.json` to `workflow.yaml`

**Option A - Recognize relationships**:
Intent Builder identifies that "click Team tab" and "select team info" are related (both for extracting team data)

**Option B - Independent recognition**:
Each operation is identified independently, MetaFlow/Workflow layer organizes them

**Implications**:
- A: Smarter Intent Builder, simpler downstream
- B: Simpler Intent Builder, more complex downstream

**Discussion**:
[To be filled]

**Decision**:
[To be decided]

---

#### Question 5.2: For multi-item scraping (loops), Intent Builder should:

**Options**:
- A. Recognize loop patterns from user operations
- B. Only handle single-item flow, let Workflow engine handle loops
- C. Generate loop intent, let MetaFlow expand it

**Example**: User demonstrates scraping 2 products, should system:
- Recognize the pattern and generate loop for N products?
- Or just record 2 separate scraping tasks?

**Discussion**:
[To be filled]

**Decision**:
[To be decided]

---

### 6. Additional Considerations

#### Question 6.1: Error Handling Strategy

When an operation fails (e.g., element not found), should the workflow:
- A. Retry with alternative selectors
- B. Skip and continue
- C. Fail immediately
- D. Ask LLM to find alternative approach

**Discussion**:
[To be filled]

**Decision**:
[To be decided]

---

#### Question 6.2: Data Validation

After extraction, should we:
- A. Validate extracted data matches expected format
- B. Compare with user's selected data (if available)
- C. Use LLM to verify data quality
- D. No validation, trust the extraction

**Discussion**:
[To be filled]

**Decision**:
[To be decided]

---

## Next Steps

1. Discuss and decide on each question above
2. Document the rationale for each decision
3. Update architecture design based on decisions
4. Implement according to agreed design

---

## Related Documents

- [Intent Builder Architecture](../intent_builder/ARCHITECTURE.md)
- [BaseAgent Architecture](../baseagent/ARCHITECTURE.md)
- [User Behavior Monitoring](../platform/user_behavior_monitoring.md)
