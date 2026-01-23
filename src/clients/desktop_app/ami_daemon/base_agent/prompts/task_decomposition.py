"""
Task Decomposition Prompt

Used for breaking down complex tasks into subtasks for multi-agent orchestration.
Based on CAMEL framework's task decomposition via Eigent's workforce.py.

References:
- CAMEL: https://github.com/camel-ai/camel
- Eigent: third-party/eigent/backend/app/utils/workforce.py
"""

from .base import PromptTemplate

# Main task decomposition prompt - from CAMEL/Eigent
TASK_DECOMPOSITION_PROMPT = PromptTemplate(
    template="""<role>
You are a Task Decomposition Expert. Your job is to break down complex tasks
into smaller, manageable subtasks that can be executed by specialized agents.
</role>

<task>
{task_content}
</task>

<available_agents>
{available_agents}
</available_agents>

<additional_context>
{additional_context}
</additional_context>

<decomposition_guidelines>
## Principles
1. Each subtask should be atomic and completable by a single agent
2. Identify dependencies between subtasks (what must complete first)
3. Look for opportunities for parallel execution
4. Define clear success criteria for each subtask
5. Keep subtasks focused and well-scoped

## Output Format
For each subtask, provide:
- **ID**: Unique identifier (e.g., "task_1")
- **Description**: Clear description of what needs to be done
- **Agent Type**: Best suited agent from available agents
- **Dependencies**: List of task IDs that must complete first
- **Inputs**: What data/context this task needs
- **Outputs**: What this task will produce
- **Success Criteria**: How to determine if task succeeded
- **Estimated Complexity**: low/medium/high
</decomposition_guidelines>

<output_format>
```json
{{
  "subtasks": [
    {{
      "id": "task_1",
      "description": "Search for relevant information about X",
      "agent_type": "browser_agent",
      "dependencies": [],
      "inputs": {{"query": "X", "context": "..."}},
      "outputs": ["search_results", "relevant_urls"],
      "success_criteria": "Found at least 3 relevant sources",
      "complexity": "low"
    }},
    {{
      "id": "task_2",
      "description": "Extract detailed data from found sources",
      "agent_type": "browser_agent",
      "dependencies": ["task_1"],
      "inputs": {{"urls": "from task_1.relevant_urls"}},
      "outputs": ["extracted_data"],
      "success_criteria": "Data extracted from all sources",
      "complexity": "medium"
    }}
  ],
  "execution_plan": {{
    "parallel_groups": [
      ["task_1"],
      ["task_2", "task_3"],
      ["task_4"]
    ],
    "estimated_total_complexity": "medium"
  }}
}}
```
</output_format>

<constraints>
- Do not create more subtasks than necessary
- Ensure all subtasks together fully cover the original task
- Consider resource efficiency (avoid redundant work)
- Account for potential failures and recovery paths
</constraints>
""",
    name="task_decomposition",
    description="Break down complex tasks into subtasks"
)


# Task assignment prompt
TASK_ASSIGNMENT_PROMPT = PromptTemplate(
    template="""<role>
You are a Task Assignment Agent. Your job is to assign a subtask to the most
appropriate specialized agent based on the task requirements and agent capabilities.
</role>

<subtask>
{subtask_description}
</subtask>

<available_agents>
{agent_descriptions}
</available_agents>

<assignment_criteria>
1. Match task requirements to agent capabilities
2. Consider agent current workload (if provided)
3. Prefer specialized agents over general ones
4. Consider the agent's track record with similar tasks
</assignment_criteria>

<output>
Provide:
1. Selected agent type
2. Reasoning for selection
3. Confidence level (0-1)
4. Alternative agent if primary is unavailable
</output>
""",
    name="task_assignment",
    description="Assign subtask to appropriate agent"
)


# Task router prompt (for determining best agent for a task)
TASK_ROUTER_PROMPT = PromptTemplate(
    template="""<role>
You are a Task Router that analyzes user requests and determines which
specialized agent should handle them.
</role>

<available_agents>
- **browser_agent**: Web automation, research, data collection from websites
  - Use for: searching the web, navigating websites, extracting web data

- **developer_agent**: Coding, debugging, git operations, development tasks
  - Use for: writing code, fixing bugs, running builds, git operations

- **document_agent**: Document creation, Google Drive, Notion operations
  - Use for: creating documents, organizing files, managing cloud docs

- **social_medium_agent**: Email, calendar, communication tasks
  - Use for: sending emails, scheduling meetings, checking calendar

- **question_confirm_agent**: User confirmations and Q&A
  - Use for: clarifying ambiguous requests, confirming actions
</available_agents>

<user_task>
{user_task}
</user_task>

<analysis>
Analyze the task and determine:
1. What type of work is primarily required?
2. What tools/capabilities are needed?
3. Which agent best matches these needs?
</analysis>

<output>
Return your decision as JSON:
```json
{{
  "selected_agent": "agent_type",
  "reasoning": "why this agent is best suited",
  "confidence": 0.0-1.0,
  "requires_confirmation": true/false,
  "subtasks_suggested": ["optional list of subtasks if complex"]
}}
```
</output>
""",
    name="task_router",
    description="Route task to appropriate agent"
)


# Dependency resolution prompt
DEPENDENCY_RESOLUTION_PROMPT = PromptTemplate(
    template="""<role>
You are analyzing task dependencies to determine execution order.
</role>

<subtasks>
{subtasks_json}
</subtasks>

<analyze>
1. Identify all dependencies
2. Detect any circular dependencies (error if found)
3. Determine execution order
4. Identify parallel execution opportunities
</analyze>

<output>
```json
{{
  "execution_order": [
    {{"phase": 1, "tasks": ["task_1", "task_2"]}},
    {{"phase": 2, "tasks": ["task_3"]}},
    {{"phase": 3, "tasks": ["task_4", "task_5"]}}
  ],
  "parallel_opportunities": [
    ["task_1", "task_2"],
    ["task_4", "task_5"]
  ],
  "critical_path": ["task_1", "task_3", "task_4"],
  "has_circular_dependencies": false,
  "warnings": []
}}
```
</output>
""",
    name="dependency_resolution",
    description="Resolve task dependencies and execution order"
)
