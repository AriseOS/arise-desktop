"""
ReAct Browser Agent Prompt

Step-by-step browser automation with structured JSON output.
Based on the existing eigent_browser_agent.py ReAct prompt.

References:
- 2ami: src/clients/desktop_app/ami_daemon/base_agent/agents/eigent_browser_agent.py
"""

from .base import PromptTemplate

# ReAct-style browser automation prompt with JSON output
REACT_BROWSER_SYSTEM_PROMPT = PromptTemplate(
    template="""You are a web automation assistant.

Analyse the page snapshot and create a plan, then output the FIRST action to start with.
If a Reference Path is provided, your plan should follow it (see Memory Reference section below).

## Memory Reference

You may receive a "Reference Path" - this is a VERIFIED SUCCESSFUL execution path from a past workflow that actually completed successfully.

How to use the Reference Path:
1. The path is FACTUAL - it represents real actions that worked on this website
2. Analyze which parts of the path are relevant to the current task
3. If relevant parts exist, use those path segments to build your plan
4. CRITICAL: You may trim irrelevant steps from the beginning or end, but NEVER skip steps in the middle
   - Valid: Use steps 2-5 from a 7-step path (trimmed front and back)
   - Valid: Use steps 0-3 from a 7-step path (trimmed back only)
   - INVALID: Use steps 0, 1, 3, 5 (skipping step 2 and 4 breaks the flow)
5. For each plan step, indicate the corresponding path_ref or null if it's a new step not from the path

## Output Format

Return a JSON object in *exactly* this shape:
{{
  "plan": [
    {{"step": "Step description", "path_ref": 2}},
    ...
  ],
  "current_plan_step": 0,
  "action": {{
    "type": "click",
    "ref": "e1"
  }}
}}

## Available action types:
- 'click': {{"type": "click", "ref": "e1"}}
- 'type': {{"type": "type", "ref": "e1", "text": "search text"}}
- 'select': {{"type": "select", "ref": "e1", "value": "option"}}
- 'wait': {{"type": "wait", "timeout": 2000}}
- 'scroll': {{"type": "scroll", "direction": "down", "amount": 300}}
- 'enter': {{"type": "enter", "ref": "e1"}}
- 'navigate': {{"type": "navigate", "url": "https://example.com"}}
- 'back': {{"type": "back"}}
- 'forward': {{"type": "forward"}}
- 'finish': {{"type": "finish", "summary": "task completion summary"}}

{reference_path}
""",
    name="react_browser",
    description="ReAct-style browser automation with JSON output"
)


# Continue action prompt for subsequent steps
REACT_CONTINUE_PROMPT = PromptTemplate(
    template="""Based on the current page state and your previous plan, output the next action.

Previous plan:
{previous_plan}

Current step: {current_step}

Return a JSON object with:
- "current_plan_step": the step number you're executing
- "action": the action to perform
- "plan_update": (optional) if the plan needs adjustment based on page changes

{{
  "current_plan_step": {current_step},
  "action": {{
    "type": "...",
    ...
  }}
}}
""",
    name="react_continue",
    description="Continue action prompt for ReAct browser"
)


# Error recovery prompt
REACT_ERROR_RECOVERY_PROMPT = PromptTemplate(
    template="""The previous action failed or produced unexpected results.

Error: {error_message}

Previous action: {previous_action}

Analyze the current page state and decide:
1. Should we retry the same action?
2. Should we try an alternative approach?
3. Should we skip this step and continue?
4. Should we ask for human help?

Return a JSON object with your decision:
{{
  "recovery_strategy": "retry" | "alternative" | "skip" | "ask_human",
  "reasoning": "explanation of your decision",
  "action": {{
    "type": "...",
    ...
  }}
}}
""",
    name="react_error_recovery",
    description="Error recovery prompt for ReAct browser"
)


# Task completion verification prompt
REACT_COMPLETION_PROMPT = PromptTemplate(
    template="""Review the current page state and determine if the task is complete.

Original task: {task}

Steps completed:
{completed_steps}

Analyze:
1. Has the task been fully accomplished?
2. Is there any remaining work?
3. What is the final result/summary?

Return a JSON object:
{{
  "is_complete": true | false,
  "confidence": 0.0-1.0,
  "summary": "description of what was accomplished",
  "remaining_work": "what still needs to be done (if any)",
  "extracted_data": {{...}}  // any data extracted during the task
}}
""",
    name="react_completion",
    description="Task completion verification prompt"
)


# Page analysis prompt for understanding current state
REACT_PAGE_ANALYSIS_PROMPT = PromptTemplate(
    template="""Analyze the current page state to understand what actions are possible.

Current URL: {current_url}
Page Title: {page_title}

Identify:
1. Interactive elements (buttons, links, inputs, dropdowns)
2. Navigation options
3. Forms or data entry points
4. Data that could be extracted
5. Potential obstacles (modals, popups, login requirements)

Return a structured analysis:
{{
  "page_type": "search_results" | "form" | "content" | "login" | "error" | "other",
  "key_elements": [
    {{"ref": "e1", "type": "button", "text": "Submit", "purpose": "form submission"}}
  ],
  "navigation_options": ["home", "back", "category links"],
  "data_present": ["product prices", "article text", etc.],
  "obstacles": ["login required", "captcha detected", etc.],
  "recommended_actions": ["click search button", "fill in form field"]
}}
""",
    name="react_page_analysis",
    description="Page state analysis prompt"
)
