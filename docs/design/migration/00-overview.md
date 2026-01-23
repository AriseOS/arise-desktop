# Eigent Feature Migration Overview

## Summary

This document set provides comprehensive guidance for migrating key features from the Eigent project (based on CAMEL-AI framework) to the 2ami system.

## Document Index

| Document | Description | Priority |
|----------|-------------|----------|
| [01-multi-agent-architecture.md](./01-multi-agent-architecture.md) | Multi-agent orchestration with specialized agents | High |
| [02-google-cloud-mcp-integration.md](./02-google-cloud-mcp-integration.md) | Gmail, Drive, Calendar, Notion via MCP | Medium |
| [03-budget-management.md](./03-budget-management.md) | Token tracking and cost control | High |
| [04-system-prompts.md](./04-system-prompts.md) | Specialized agent prompts | High |
| [05-frontend-implementation.md](./05-frontend-implementation.md) | Frontend UI components for multi-agent support | High |

---

## Feature Analysis Summary

### 1. Multi-Agent Architecture

**Eigent Implementation**:
- 5 specialized agents: browser, developer, document, social_medium, question_confirm
- `ListenChatAgent` base class with event emission
- `Workforce` class for task decomposition and orchestration
- Async event queue for real-time progress tracking

**Migration Approach**:
- Create new agent classes inheriting from `BaseStepAgent`
- Implement `TaskOrchestrator` for multi-agent coordination
- Add event system for progress tracking
- Use agent registry for dynamic routing

**Key Files**:
- Source: `third-party/eigent/backend/app/utils/agent.py`, `workforce.py`
- Target: `src/clients/desktop_app/ami_daemon/base_agent/agents/`

---

### 2. Google Cloud MCP Integration

**Eigent Implementation**:
- Gmail via `@gongrzhe/server-gmail-autoauth-mcp`
- Google Drive via `@modelcontextprotocol/server-gdrive`
- Notion via remote MCP `https://mcp.notion.com/mcp`
- Calendar via direct Google API

**Migration Approach**:
- Create `MCPClient` base class for MCP communication
- Implement toolkit wrappers for each service
- Handle OAuth credential management
- Integrate with existing toolkit system

**Key Files**:
- Source: `third-party/eigent/backend/app/utils/toolkit/google_*.py`
- Target: `src/clients/desktop_app/ami_daemon/base_agent/tools/toolkits/`

---

### 3. Budget Management

**Eigent Implementation**:
- CAMEL's `ModelProcessingError` for budget exceeded detection
- Token tracking per LLM call
- Event emission for budget warnings/exceeded

**Migration Approach**:
- Implement `TokenUsage` and `SessionTokenUsage` classes
- Create `BudgetController` with configurable limits
- Integrate with `AnthropicProvider` for automatic tracking
- Support throttling to cheaper models when limits approached

**Key Files**:
- Source: `third-party/eigent/backend/app/utils/agent.py`
- Target: `src/clients/desktop_app/ami_daemon/base_agent/core/`

---

### 4. System Prompts

**Eigent Implementation**:
- Comprehensive research analyst prompt with XML-style sections
- Role-based identity with clear responsibilities
- Environment-aware (platform, date, working directory)
- Strong note-taking and citation requirements
- Memory/workflow integration sections

**Migration Approach**:
- Create `PromptTemplate` class with variable substitution
- Define specialized prompts for each agent type
- Implement prompt registry for easy access
- Support dynamic context injection

**Key Files**:
- Source: `third-party/eigent/backend/app/utils/agent.py`
- Target: `src/clients/desktop_app/ami_daemon/base_agent/prompts/`

---

### 5. Frontend Implementation

**Eigent Implementation**:
- **Zustand** for global state management (chatStore, projectStore, authStore)
- **SSE** (fetch-event-source) for real-time streaming events
- **React Flow** for multi-agent workflow visualization
- **Radix UI + shadcn** component library
- Comprehensive event handling (30+ event types)
- Auto-confirm timers for task decomposition (30s)

**2ami Current State**:
- **Local React hooks** for state management
- **WebSocket** for real-time events
- **React Flow** for workflow visualization (existing)
- **Custom CSS** for styling
- Basic event handling in QuickTaskPage

**Migration Approach**:
- Enhance WebSocket event handling for new event types
- Add multi-agent visualization components
- Implement task decomposition UI with auto-confirm
- Add token/budget usage display
- Optionally migrate to Zustand for complex state
- Add cloud service integration UI (OAuth flows)

**Key Files**:
- Source: `third-party/eigent/src/store/chatStore.ts`, `components/WorkFlow/`
- Target: `src/clients/desktop_app/src/pages/QuickTaskPage.jsx`, `components/`

---

## Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)

| Task | Document | Effort |
|------|----------|--------|
| Token tracking infrastructure | 03-budget-management.md | 2 days |
| Budget controller | 03-budget-management.md | 2 days |
| Prompt templates system | 04-system-prompts.md | 1 day |
| Event system basics | 01-multi-agent-architecture.md | 2 days |

### Phase 2: Core Agents (Weeks 3-4)

| Task | Document | Effort |
|------|----------|--------|
| QuestionConfirmAgent | 01-multi-agent-architecture.md | 2 days |
| DeveloperAgent | 01-multi-agent-architecture.md | 3 days |
| Agent registry | 01-multi-agent-architecture.md | 1 day |
| Task router | 01-multi-agent-architecture.md | 2 days |

### Phase 3: MCP Integration (Weeks 5-6)

| Task | Document | Effort |
|------|----------|--------|
| MCP client base | 02-google-cloud-mcp-integration.md | 2 days |
| Gmail toolkit | 02-google-cloud-mcp-integration.md | 2 days |
| Google Drive toolkit | 02-google-cloud-mcp-integration.md | 2 days |
| Calendar toolkit | 02-google-cloud-mcp-integration.md | 1 day |
| Notion toolkit | 02-google-cloud-mcp-integration.md | 2 days |

### Phase 4: Orchestration (Weeks 7-8)

| Task | Document | Effort |
|------|----------|--------|
| TaskOrchestrator | 01-multi-agent-architecture.md | 3 days |
| Multi-agent coordination | 01-multi-agent-architecture.md | 3 days |
| Integration testing | All | 2 days |
| Documentation | All | 1 day |

### Phase 5: Frontend Enhancement (Weeks 9-10)

| Task | Document | Effort |
|------|----------|--------|
| Enhanced event handling | 05-frontend-implementation.md | 2 days |
| Multi-agent visualization | 05-frontend-implementation.md | 3 days |
| Task decomposition UI | 05-frontend-implementation.md | 2 days |
| Token/budget display | 05-frontend-implementation.md | 1 day |
| Human interaction modals | 05-frontend-implementation.md | 2 days |
| Integration list UI | 05-frontend-implementation.md | 2 days |
| Zustand migration (optional) | 05-frontend-implementation.md | 3 days |

---

## Architecture Comparison

### Current 2ami Architecture

```
src/clients/desktop_app/ami_daemon/
├── base_agent/
│   ├── agents/
│   │   ├── eigent_browser_agent.py      # ReAct browser
│   │   └── eigent_style_browser_agent.py # Tool-calling browser
│   ├── tools/
│   │   └── toolkits/                     # 6 toolkits
│   └── core/
│       └── schemas.py
├── services/
│   └── quick_task_service.py
└── routers/
    └── quick_task.py
```

### Target Architecture (After Migration)

```
src/clients/desktop_app/ami_daemon/
├── base_agent/
│   ├── agents/
│   │   ├── eigent_browser_agent.py
│   │   ├── eigent_style_browser_agent.py
│   │   ├── question_confirm_agent.py     # NEW
│   │   ├── developer_agent.py            # NEW
│   │   ├── document_agent.py             # NEW
│   │   └── social_medium_agent.py        # NEW
│   ├── tools/
│   │   └── toolkits/
│   │       ├── (existing toolkits)
│   │       ├── mcp_base.py               # NEW
│   │       ├── gmail_mcp_toolkit.py      # NEW
│   │       ├── gdrive_mcp_toolkit.py     # NEW
│   │       ├── calendar_toolkit.py       # NEW
│   │       └── notion_mcp_toolkit.py     # NEW
│   ├── core/
│   │   ├── schemas.py
│   │   ├── token_usage.py                # NEW
│   │   ├── cost_calculator.py            # NEW
│   │   ├── budget_controller.py          # NEW
│   │   ├── agent_registry.py             # NEW
│   │   └── task_orchestrator.py          # NEW
│   ├── prompts/                           # NEW
│   │   ├── base.py
│   │   ├── browser_agent.py
│   │   ├── developer.py
│   │   └── ...
│   └── events/
│       ├── event_types.py                # NEW
│       └── event_emitter.py              # NEW
└── ...
```

### Target Frontend Architecture

```
src/clients/desktop_app/src/
├── pages/
│   └── QuickTaskPage.jsx                 # MODIFY: Enhanced for multi-agent
├── components/
│   ├── AgentNode.jsx                     # NEW: Agent visualization
│   ├── TaskDecomposition.jsx             # NEW: Task plan editor
│   ├── TokenUsage.jsx                    # NEW: Budget indicator
│   ├── HumanInteraction.jsx              # NEW: Enhanced Q&A modal
│   └── IntegrationList.jsx               # NEW: Cloud service integrations
├── store/
│   └── taskStore.js                      # NEW: Zustand store (optional)
└── styles/
    └── QuickTaskPage.css                 # MODIFY: New component styles
```

---

## Dependencies

### NPM Packages (for MCP servers)

```json
{
  "dependencies": {
    "@gongrzhe/server-gmail-autoauth-mcp": "^1.0.0",
    "@modelcontextprotocol/server-gdrive": "^1.0.0"
  }
}
```

### NPM Packages (for Frontend - optional Zustand)

```json
{
  "dependencies": {
    "zustand": "^5.0.0"
  }
}
```

### Python Packages

```txt
# Already in requirements
anthropic>=0.20.0
aiohttp>=3.9.0

# For Google Calendar direct API
google-auth>=2.0.0
google-api-python-client>=2.0.0
```

### Environment Variables

```bash
# Budget management
DEFAULT_MAX_TOKENS_PER_TASK=100000
DEFAULT_MAX_COST_PER_TASK=1.00
BUDGET_FALLBACK_MODEL=claude-3-5-haiku-20241022

# MCP credentials
GMAIL_CREDENTIALS_PATH=/path/to/gmail-creds.json
GDRIVE_CREDENTIALS_PATH=/path/to/gdrive-creds.json
GCAL_CREDENTIALS_PATH=/path/to/gcal-creds.json
MCP_REMOTE_CONFIG_DIR=~/.config/mcp
```

---

## Testing Strategy

1. **Unit Tests**: Each new class/module
2. **Integration Tests**: Toolkit + Agent interactions
3. **E2E Tests**: Full task execution flows
4. **Performance Tests**: Token usage, latency
5. **Budget Tests**: Limit enforcement

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| MCP server compatibility | High | Version pinning, fallback mechanisms |
| Token tracking accuracy | Medium | Validate against actual API usage |
| Multi-agent coordination complexity | High | Start simple, iterate |
| OAuth credential management | Medium | Secure storage, token refresh |

---

## Success Criteria

### Backend
1. ✅ All 5 specialized agents functional
2. ✅ Gmail/Drive/Calendar/Notion integration working
3. ✅ Budget limits enforced correctly
4. ✅ Task orchestration handles multi-step workflows
5. ✅ Real-time progress tracking via events
6. ✅ No regression in existing functionality

### Frontend
7. ✅ Multi-agent workflow visualization displays all agents and tasks
8. ✅ Task decomposition panel with auto-confirm timer working
9. ✅ Token/budget usage displayed in real-time
10. ✅ Human interaction modals functional (questions, confirmations)
11. ✅ Cloud integration UI for OAuth flows
12. ✅ All 30+ event types properly handled

---

## References

- Eigent source: `third-party/eigent/`
- CAMEL framework: https://github.com/camel-ai/camel
- MCP specification: https://modelcontextprotocol.io/
- Anthropic API: https://docs.anthropic.com/
