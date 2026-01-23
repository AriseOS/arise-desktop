"""
Workflow Builder Prompts

For converting browser actions into reusable workflows and modifying existing workflows.
Based on 2ami's intent_builder workflow creation patterns.

References:
- 2ami: src/cloud_backend/intent_builder/agents/workflow_builder.py
"""

from .base import PromptTemplate

# Main workflow builder prompt
WORKFLOW_BUILDER_PROMPT = PromptTemplate(
    template="""<role>
You are an expert at analyzing browser action sequences and creating clear,
reusable workflow descriptions.
</role>

<task>
Given a sequence of browser actions (clicks, types, navigations, etc.),
create a workflow specification that:
1. Describes the high-level intent of the workflow
2. Identifies key steps and their purposes
3. Notes any data extraction points
4. Handles variations and edge cases
</task>

<action_sequence>
{action_sequence}
</action_sequence>

<output_requirements>
The workflow should be:
- Understood by humans (clear descriptions)
- Replayable by automation systems (precise selectors)
- Modifiable for similar tasks (parameterized)
</output_requirements>

<output_format>
```yaml
name: {workflow_name}
description: {workflow_description}
version: "1.0.0"
parameters:
  - name: {param_name}
    type: string
    description: {param_description}
    required: true

steps:
  - name: Navigate to site
    action: navigate
    url: "{url}"
    wait_for: page_load

  - name: Search for item
    action: type
    selector: "#search-input"
    text: "{{search_query}}"

  - name: Click search button
    action: click
    selector: ".search-button"
    wait_for: results_loaded

  - name: Extract results
    action: extract
    selector: ".result-item"
    fields:
      - name: title
        selector: ".title"
      - name: url
        selector: "a@href"

output:
  - name: results
    type: array
    source: extract_step.data
```
</output_format>
""",
    name="workflow_builder",
    description="Convert browser actions to workflow"
)


# Workflow modification prompt
WORKFLOW_MODIFICATION_PROMPT = PromptTemplate(
    template="""<role>
You are a workflow modification assistant.
</role>

<existing_workflow>
{existing_workflow}
</existing_workflow>

<modification_request>
{modification_request}
</modification_request>

<guidelines>
Given the existing workflow and modification request, update the workflow
to incorporate the changes while:
1. Preserving the overall structure and intent
2. Maintaining consistency with existing patterns
3. Ensuring the modification doesn't break existing functionality
</guidelines>

<analysis>
Consider:
- Which steps need to be added, removed, or modified
- How the changes affect dependencies between steps
- Whether the modification aligns with the original workflow's purpose
- Any new parameters or outputs needed
</analysis>

<output>
Provide:
1. The modified workflow in the same format as input
2. A summary of changes made
3. Any warnings about potential issues
</output>
""",
    name="workflow_modification",
    description="Modify existing workflow"
)


# Workflow optimization prompt
WORKFLOW_OPTIMIZATION_PROMPT = PromptTemplate(
    template="""<role>
You are analyzing a workflow to suggest optimizations.
</role>

<workflow>
{workflow}
</workflow>

<optimization_goals>
- Reduce number of steps where possible
- Improve reliability (better wait conditions, error handling)
- Enhance flexibility (parameterize hardcoded values)
- Improve performance (parallel steps, caching)
</optimization_goals>

<output>
```json
{{
  "suggestions": [
    {{
      "type": "combine_steps",
      "steps": ["step_1", "step_2"],
      "reason": "These steps can be combined into one action",
      "impact": "minor"
    }},
    {{
      "type": "add_wait",
      "after_step": "step_3",
      "condition": "element_visible",
      "selector": ".result",
      "reason": "Results may load asynchronously",
      "impact": "reliability"
    }},
    {{
      "type": "parameterize",
      "step": "step_5",
      "field": "text",
      "current_value": "example search",
      "parameter_name": "search_query",
      "reason": "Allow dynamic search terms",
      "impact": "flexibility"
    }}
  ],
  "optimized_workflow": {{ ... }}
}}
```
</output>
""",
    name="workflow_optimization",
    description="Optimize workflow for reliability and efficiency"
)


# Workflow validation prompt
WORKFLOW_VALIDATION_PROMPT = PromptTemplate(
    template="""<role>
You are validating a workflow definition for correctness and completeness.
</role>

<workflow>
{workflow}
</workflow>

<validation_checks>
1. **Structure**: All required fields present
2. **Selectors**: Selectors are valid CSS/XPath
3. **Dependencies**: Step references are valid
4. **Parameters**: All used parameters are defined
5. **Logic**: Workflow flow makes sense
6. **Error Handling**: Appropriate error handling exists
</validation_checks>

<output>
```json
{{
  "valid": true/false,
  "errors": [
    {{
      "severity": "error",
      "step": "step_name",
      "field": "selector",
      "message": "Invalid CSS selector",
      "suggestion": "Use '#id' instead of 'id'"
    }}
  ],
  "warnings": [
    {{
      "severity": "warning",
      "step": "step_name",
      "message": "No error handling defined",
      "suggestion": "Add on_error: skip or retry"
    }}
  ],
  "summary": "Workflow validation summary"
}}
```
</output>
""",
    name="workflow_validation",
    description="Validate workflow definition"
)


# Workflow documentation prompt
WORKFLOW_DOCUMENTATION_PROMPT = PromptTemplate(
    template="""<role>
You are creating user-friendly documentation for a workflow.
</role>

<workflow>
{workflow}
</workflow>

<output_format>
# {workflow_name}

## Overview
{brief_description}

## What This Workflow Does
{detailed_description}

## Prerequisites
- {prerequisite_1}
- {prerequisite_2}

## Parameters
| Name | Type | Required | Description |
|------|------|----------|-------------|
| {param_name} | {param_type} | {required} | {param_description} |

## Steps
### Step 1: {step_name}
{step_description}

### Step 2: {step_name}
{step_description}

## Output
{output_description}

## Example Usage
```
{example_usage}
```

## Common Issues & Solutions
### Issue: {issue_description}
**Solution:** {solution}

## Related Workflows
- {related_workflow_1}
- {related_workflow_2}
</output_format>
""",
    name="workflow_documentation",
    description="Generate workflow documentation"
)
