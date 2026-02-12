# base_agent/agents/

Specialized agent implementations for the AMI Task Executor.

## Agent Types

| File | Agent | Purpose |
|------|-------|---------|
| `question_confirm_agent.py` | QuestionConfirmAgent | Human-in-the-loop confirmations and Q&A |
| `developer_agent.py` | DeveloperAgent | Coding, debugging, git operations |
| `document_agent.py` | DocumentAgent | Google Drive, Notion, document creation |
| `social_medium_agent.py` | SocialMediumAgent | Email (Gmail), calendar, communication |

These agents are created via factory functions in `core/agent_factories.py` and executed by `AMITaskExecutor`.

## Key Design

- Agents are lightweight wrappers providing agent-specific metadata
- Actual creation and configuration happens in `agent_factories.py`
- The old step-agent workflow engine (BaseStepAgent, INPUT_SCHEMA) has been removed
- Routing is handled by AMITaskPlanner, not agent registry
