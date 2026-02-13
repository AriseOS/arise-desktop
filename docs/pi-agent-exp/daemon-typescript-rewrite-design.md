# Daemon TypeScript Rewrite Design

## 1. Motivation

### Why Rewrite

The Python daemon (`src/clients/desktop_app/ami_daemon/`, ~42,800 LoC) has structural problems:

1. **Sync blocking**: `AnthropicProvider` uses sync `httpx.Client`; embedding calls, file I/O, `subprocess.run()` all block the single async event loop
2. **Single LLM provider**: Only Anthropic Claude. No path to OpenAI, Gemini, Bedrock
3. **No multi-modal**: No image input, no streaming thinking blocks, no extended thinking
4. **Language boundary**: Electron (TS) ↔ Python (HTTP) adds latency, complexity, two runtimes to package
5. **Duplicate abstractions**: `AnthropicProvider`, `BaseProvider`, `ToolCallResponse`, `AMIAgent`, `AMITool` — all reimplementations of what pi-ai already provides better
6. **Over-engineered multi-agent**: 5 agent types with 5 factories, 5 system prompts, a router, type-specific toolkit selection — all unnecessary when a single agent can self-select tools at runtime

### What pi-ai Gives Us

`@mariozechner/pi-ai` (TypeScript, `third-party/pi-mono/packages/ai/`):
- 16+ LLM providers (Anthropic, OpenAI, Google, Bedrock, Azure, Mistral, etc.)
- Native async streaming, no `to_thread` workarounds
- Multi-modal: text + image input, thinking blocks, extended thinking control
- Built-in cost calculation, prompt caching, retry logic
- Type-safe tool schema via TypeBox

`@mariozechner/pi-agent-core` (`third-party/pi-mono/packages/agent/`):
- Multi-turn tool-calling loop with automatic continuation
- Streaming events (`message_update`, `tool_execution_start/end`, etc.)
- Abort/cancellation via AbortSignal
- Steering (inject user message mid-execution) and follow-up messages
- `transformContext()` hook for context pruning/enrichment
- Independent concurrent instances

### What Stays Python

- **Cloud backend** (`src/cloud_backend/`): Stays Python. Daemon calls via HTTP API
- **Memory module** (`src/common/memory/`): Stays in cloud backend, accessed via HTTP (`/api/v1/memory/plan`, `/api/v1/memory/query`, `/api/v1/memory/learn`)

---

## 2. Architecture Change: Multi-Agent → Parent-Child

### Current: Type-Based Multi-Agent

```
Orchestrator (decides: direct_reply | tool_use | decompose_task)
  └── decompose_task
        ├── AMITaskPlanner (decompose into subtasks with agent_type)
        └── AMITaskExecutor
              ├── agents = {browser: BrowserAgent, document: DocumentAgent, code: DeveloperAgent, multi_modal: MultiModalAgent}
              ├── For subtask with type="browser" → agents["browser"].astep()
              ├── For subtask with type="document" → agents["document"].astep()
              └── Each agent has different tools, different system prompt
```

**Problems**:
- LLM must pre-classify each subtask into agent_type during planning
- Wrong classification → wrong tools → failure
- 5 factory functions, 5 system prompts, a router class — all just for tool selection
- Agent can't use browser + file + terminal in one subtask

### New: Unified Parent-Child

```
Orchestrator (Parent Agent)
  ├── Direct reply: search, terminal, ask_human (same as before)
  ├── inject_message: steer running child via pi-agent-core's steer()
  └── decompose_task
        ├── TaskPlanner (decompose into subtasks, NO agent_type needed)
        └── TaskExecutor
              └── For each subtask → create child Agent with ALL tools
                    ├── All toolkits available: browser, file, terminal, MCP, media, etc.
                    ├── Single unified system prompt
                    └── Agent self-selects tools based on task content
```

**Key changes**:
- **No agent_type classification** — subtasks are just `{id, content, depends_on}`
- **No routing** — every child agent has all tools
- **Single factory** — `createChildAgent(model, allTools, systemPrompt)`
- **Single system prompt** — describes all capabilities, agent decides what to use
- **LLM naturally picks tools** — "Extract products from website and save to Excel" → agent uses browser tools then excel tools, no pre-classification needed

### What's Preserved

| Feature | Status | Notes |
|---------|--------|-------|
| Orchestrator as entry point | KEPT | Parent agent, decides direct reply vs decompose |
| Task decomposition (XML) | KEPT | Planner still decomposes, just without agent_type |
| Sequential execution with deps | KEPT | TaskExecutor, dependency resolution, fail-fast |
| Memory-first planning | KEPT | PlannerAgent → workflow_guide injection |
| Replan (dynamic subtask split) | KEPT | replan_review_context + replan_split_and_handoff |
| Online learning | KEPT | ExecutionDataCollector → cloud backend learn API |
| inject_message (steering) | IMPROVED | pi-agent-core's `steer()` is built-in |
| Budget tracking | SIMPLIFIED | pi-ai returns `response.usage.cost` per call |

### What's Eliminated

| Component | Lines | Why |
|-----------|-------|-----|
| `ami_agent.py` (tool loop) | 1,127 | Replaced by pi-agent-core `Agent` |
| `ami_tool.py` (schema gen) | 333 | Replaced by `AgentTool<TSchema>` |
| `cost_calculator.py` | 293 | pi-ai has `calculateCost()` built-in |
| `task_router.py` | 420 | No agent_type routing needed |
| `question_confirm_agent.py` | 422 | Dead code (never instantiated) |
| `question_confirm.py` (prompt) | 240 | Dead code |
| `task_planning_toolkit.py` | 559 | Dead code (superseded by ReplanToolkit) |
| 4 separate agent factories | ~600 | Collapsed into 1 factory |
| 4 separate system prompts | ~800 | Collapsed into 1 unified prompt |
| `base_provider.py` | 306 | pi-ai replaces entire LLM layer |
| `anthropic_provider.py` | 508 | pi-ai replaces |
| `openai_provider.py` | 101 | Unused in daemon |
| `provider_cache.py` | 402 | pi-ai model selection replaces |
| **Total eliminated** | **~6,111** | |

---

## 3. pi-ai Integration

### LLM Provider (replaces AnthropicProvider + BaseProvider)

```typescript
import { getModel, complete, stream } from "@mariozechner/pi-ai";

// Select model — any provider, any model
const model = getModel("anthropic", "claude-sonnet-4-5-20250929");
// or: getModel("openai", "gpt-4o")
// or: getModel("google", "gemini-2.0-flash")

// Simple completion (replaces generate_response)
const response = await complete(model, {
  systemPrompt: "...",
  messages: [{ role: "user", content: "Hello", timestamp: Date.now() }],
});

// With tools (replaces generate_with_tools) — same function
const response = await complete(model, {
  systemPrompt: "...",
  messages: [...],
  tools: [{ name: "browser_navigate", description: "...", parameters: schema }],
});
// response.stopReason: "stop" | "toolUse" | "length" | "error"
// response.usage: { input, output, cacheRead, cacheWrite, cost: { total } }

// Multi-modal: images in user messages
messages: [{ role: "user", content: [
  { type: "text", text: "What's in this image?" },
  { type: "image", data: base64Data, mimeType: "image/png" },
], timestamp: Date.now() }]
```

### Agent Loop (replaces AMIAgent)

```typescript
import { Agent } from "@mariozechner/pi-agent-core";

const child = new Agent({
  streamFn: stream,
  model: getModel("anthropic", "claude-sonnet-4-5-20250929"),
  tools: [...browserTools, ...fileTools, ...terminalTools, ...memoryTools, ...searchTools],
  initialState: {
    systemPrompt: UNIFIED_AGENT_PROMPT,
    messages: [],
  },
});

// Event streaming → SSE to frontend
child.subscribe((event) => {
  if (event.type === "tool_execution_start") {
    sseEmit({ step: "activate_toolkit", data: { toolkit_name: event.tool.name, ... } });
  }
  if (event.type === "message_update") {
    sseEmit({ step: "agent_thinking", data: { content: event.message.content, ... } });
  }
});

// Execute subtask
const eventStream = child.run([{
  role: "user",
  content: subtaskPrompt,  // includes task + browser state + workflow_guide + dep results
  timestamp: Date.now(),
}]);
const result = await eventStream.result();

// Steering (replaces inject_message)
child.steer([{ role: "user", content: "Focus on the first 5 results", timestamp: Date.now() }]);

// Abort (replaces cancel_task)
child.abort();
```

### Key Mappings

| Python (current) | TypeScript (pi-ai/pi-agent-core) |
|---|---|
| `AnthropicProvider` | `getModel(provider, modelId)` — no class |
| `generate_response()` | `complete(model, context)` |
| `generate_with_tools()` | `complete(model, context)` with `tools` |
| `generate_json_response()` | `complete()` + JSON parse + repair |
| `ToolCallResponse` | `AssistantMessage` |
| `ToolUseBlock` | `ToolCall` (`.id`, `.name`, `.arguments`) |
| `TextBlock` | `TextContent` (`.text`) |
| `AMIAgent.astep()` | `Agent.run()` → returns AsyncIterable event stream |
| `AMIAgent._should_stop_after_tool` | `Agent.steer()` / `Agent.abort()` |
| `AMITool` | `AgentTool<TSchema>` with TypeBox schema |
| `_record_usage()` / `BudgetController` | `response.usage.cost.total` |

---

## 4. Dead Code Audit (Do NOT Rewrite)

Analysis of the current daemon found these unused/dead components:

| File | Lines | Status | Evidence |
|---|---|---|---|
| `question_confirm_agent.py` | 422 | DEAD | Never instantiated, no factory, no route |
| `prompts/question_confirm.py` | 240 | DEAD | Only imported by dead agent |
| `task_planning_toolkit.py` | 559 | DEAD | Superseded by ReplanToolkit, never imported |
| `task_router.py` | 420 | DEAD | Routing logic unused, planner LLM assigns type directly |
| `base_tool.py` | 307 | DELETE | Replaced by pi-agent-core AgentTool |
| `cost_calculator.py` | 293 | DELETE | Replaced by pi-ai built-in |
| `openai_provider.py` | 101 | UNUSED in daemon | Only used by cloud backend |
| `claude_agent_provider.py` | 591 | UNUSED in daemon | Only used by cloud backend |
| **Total** | **~2,933** | | |

**All other toolkits are actively used** — confirmed via factory imports and agent creation paths.

---

## 5. SSE Event Contract (Frontend Compatibility)

The frontend (`src/clients/desktop_app/src/utils/sseClient.js`) connects via:
- `GET /api/v1/quick-task/stream/{task_id}` — SSE stream
- `POST /api/v1/quick-task/message/{task_id}` — user messages (steering, human response)

### Event Format (MUST preserve)

```json
{"step": "action_type", "data": {"action": "action_type", "timestamp": "...", "task_id": "...", ...}}
```

### Events the Frontend Listens For

| Event | When | Key Data Fields |
|-------|------|-----------------|
| `activate_agent` | Agent starts | `agent_name`, `agent_id`, `message` |
| `deactivate_agent` | Agent finishes | `agent_name`, `tokens_used`, `duration_seconds` |
| `agent_thinking` | Agent reasoning | `content` |
| `activate_toolkit` | Tool call starts | `toolkit_name`, `method_name`, `input_preview` |
| `deactivate_toolkit` | Tool call ends | `toolkit_name`, `method_name`, `output_preview`, `success`, `duration_ms` |
| `browser_action` | Browser interaction | `action_type`, `target`, `value`, `success`, `page_url` |
| `screenshot` | Screenshot taken | `screenshot_url` |
| `terminal` | Shell command | `command`, `output`, `exit_code`, `duration_ms` |
| `task_decomposed` | Plan generated | subtask list |
| `worker_assigned` | Subtask started | subtask info |
| `worker_completed` | Subtask done | subtask result |
| `worker_failed` | Subtask failed | error |
| `ask` / `wait_confirm` | Need user input | `content`, `question`, `context` |
| `memory_result` | Memory query done | `paths_count`, `paths`, `has_workflow` |
| `task_completed` | Task success | `output`, `tools_called`, `duration_seconds` |
| `task_failed` | Task failure | `error`, `step` |
| `heartbeat` | Keep-alive (30s) | `message`, `timestamp` |
| `end` | Stream close | `status`, `message`, `result` |

### Mapping pi-agent-core Events → SSE

```typescript
// pi-agent-core emits AgentEvent, we map to SSE
function mapToSSE(agentEvent: AgentEvent, taskId: string): SSEEvent | null {
  switch (agentEvent.type) {
    case "tool_execution_start":
      return { step: "activate_toolkit", data: {
        action: "activate_toolkit", task_id: taskId,
        toolkit_name: agentEvent.tool.label,
        method_name: agentEvent.tool.name,
        timestamp: new Date().toISOString(),
      }};
    case "tool_execution_end":
      return { step: "deactivate_toolkit", data: {
        action: "deactivate_toolkit", task_id: taskId,
        toolkit_name: agentEvent.tool.label,
        method_name: agentEvent.tool.name,
        success: !agentEvent.result.isError,
        output_preview: agentEvent.result.content[0]?.text?.slice(0, 200),
        duration_ms: agentEvent.duration,
        timestamp: new Date().toISOString(),
      }};
    case "message_update":
      return { step: "agent_thinking", data: {
        action: "agent_thinking", task_id: taskId,
        content: extractTextFromMessage(agentEvent.message),
        timestamp: new Date().toISOString(),
      }};
    // ... other mappings
  }
}
```

---

## 6. Module Migration Plan

### 6.1 DELETE — Not Ported (~6,100 lines saved)

| Python Module | Lines | Reason |
|---|---|---|
| `ami_agent.py` + `ami_tool.py` | 1,460 | Replaced by pi-agent-core |
| `cost_calculator.py` | 293 | Replaced by pi-ai |
| `task_router.py` | 420 | No type routing in new architecture |
| `question_confirm_agent.py` + prompt | 662 | Dead code |
| `task_planning_toolkit.py` | 559 | Dead code |
| `base_tool.py` | 307 | Replaced by AgentTool |
| `llm_service.py` | 137 | Replaced by pi-ai model selection |
| `base_provider.py` + providers | 1,506 | Replaced by pi-ai |
| `provider_cache.py` | 402 | Replaced by pi-ai |
| `agents/_base.py` | 66 | No base class needed |

### 6.2 PORT — Core Pipeline (~5,500 lines → ~3,500 TS)

| Python File | Lines | TypeScript Target | Notes |
|---|---|---|---|
| `orchestrator_agent.py` | 1,365 | `orchestrator.ts` (~900) | Parent agent, tools: search/terminal/human + decompose/inject/cancel |
| `ami_task_planner.py` | 1,703 | `task-planner.ts` (~1,000) | Decompose to subtasks (no agent_type), memory-first |
| `ami_task_executor.py` | 1,333 | `task-executor.ts` (~900) | Sequential exec, deps, replan |
| `agent_factories.py` | 1,388 | `agent-factory.ts` (~200) | Single factory: `createChildAgent()` |
| `execution_data_collector.py` | 304 | `execution-data-collector.ts` (~200) | Extract tool records for learning |
| `budget_controller.py` + `token_usage.py` | 766 | `budget.ts` (~200) | Simplified: pi-ai returns cost per call |
| `schemas.py` | 250 | `schemas.ts` (~150) | Zod schemas |

### 6.3 PORT — Browser Automation (~4,500 lines → ~3,500 TS)

| Python File | Lines | TypeScript Target | Notes |
|---|---|---|---|
| `browser_session.py` | 1,397 | `browser-session.ts` (~1,100) | Playwright JS, CDP connect, tab management |
| `action_executor.py` | 798 | `action-executor.ts` (~650) | click/type/navigate/extract/mouse/keyboard |
| `behavior_recorder.py` | 704 | `behavior-recorder.ts` (~550) | CDP event recording for memory learning |
| `page_snapshot.py` | 239 | `page-snapshot.ts` (~200) | Accessible tree, `[ref=eN]` element refs |
| `config_loader.py` | 492 | `config-loader.ts` (~350) | Action timeout/retry config |

### 6.4 PORT — Toolkits (~7,500 lines → ~5,500 TS)

Each toolkit becomes an array of `AgentTool<TSchema>`:

| Toolkit | Lines | Target TS | Notes |
|---|---|---|---|
| `browser_toolkit.py` | 1,347 | ~1,000 | Wraps browser session |
| `memory_toolkit.py` | 1,866 | ~1,200 | HTTP calls to cloud backend |
| `file_toolkit.py` | 684 | ~400 | Node.js `fs/promises` |
| `terminal_toolkit.py` | 393 | ~250 | `child_process.exec` |
| `replan_toolkit.py` | 281 | ~200 | replan_review + split_and_handoff |
| `search_toolkit.py` | 257 | ~150 | Google search API |
| `human_toolkit.py` | 164 | ~100 | ask_human, wait_confirm |
| `calendar_toolkit.py` | 536 | ~350 | Google Calendar API |
| `excel_toolkit.py` | 422 | ~300 | exceljs |
| `pptx_toolkit.py` | 333 | ~250 | pptxgenjs |
| `markitdown_toolkit.py` | 225 | ~150 | marked |
| `mcp_base.py` | 491 | ~350 | MCP protocol base |
| `gmail_mcp_toolkit.py` | 225 | ~150 | MCP |
| `gdrive_mcp_toolkit.py` | 331 | ~200 | MCP |
| `notion_mcp_toolkit.py` | 413 | ~250 | MCP |
| `image_generation_toolkit.py` | 232 | ~150 | DALL-E/OpenAI API |
| `image_analysis_toolkit.py` | 223 | ~150 | Vision via pi-ai (multi-modal) |
| `audio_analysis_toolkit.py` | 224 | ~150 | Whisper API |
| `video_downloader_toolkit.py` | 347 | ~200 | ffmpeg subprocess |
| `base_toolkit.py` | 85 | 0 | Not needed (flat tool arrays) |

### 6.5 PORT — Services (~6,900 lines → ~4,500 TS)

| Python File | Lines | TypeScript Target | Notes |
|---|---|---|---|
| `quick_task_service.py` | 2,536 | ~1,600 | Main task execution orchestration |
| `cloud_client.py` | 1,740 | ~1,100 | Cloud backend HTTP API |
| `context_builder.py` | 487 | ~300 | LLM context construction |
| `storage_manager.py` | 447 | ~300 | File storage |
| `browser_window_manager.py` | 402 | ~250 | Browser state |
| `recording_service.py` | 315 | ~200 | Recording management |
| `recording_analyzer.py` | 160 | ~100 | Analysis |
| `replay/` | ~600 | ~400 | Task replay |

### 6.6 PORT — Server, Routes, Events, Prompts (~7,500 lines → ~4,500 TS)

| Component | Python Lines | TS Target | Notes |
|---|---|---|---|
| `daemon.py` (server) | 2,221 | ~1,200 | Express.js + CORS + lifecycle |
| `routers/` | 1,550 | ~800 | Express route handlers |
| `events/` (SSE) | 1,600 | ~800 | Action types + SSE emitter |
| `prompts/` | 2,100 | ~1,500 | String templates (mostly copy-paste) |
| `i18n.py` + utils | ~500 | ~200 | Minimal |

### Summary

| Category | Python Lines | TS Lines | Savings |
|---|---|---|---|
| Deleted (dead/replaced) | 6,100 | 0 | -6,100 |
| Core pipeline | 5,500 | 3,500 | -2,000 |
| Browser automation | 4,500 | 3,500 | -1,000 |
| Toolkits | 7,500 | 5,500 | -2,000 |
| Services | 6,900 | 4,500 | -2,400 |
| Server/routes/events/prompts | 7,500 | 4,500 | -3,000 |
| **Total** | **~38,000** | **~21,500** | **-16,500 (43%)** |

---

## 7. Unified System Prompt Design

The current 5 system prompts (browser, developer, document, social, multi-modal) collapse into 1:

```
You are Ami, a capable AI assistant with access to tools for:
- **Web**: Search, browse, navigate, click, extract, take screenshots
- **Files**: Read, write, create, delete files in workspace
- **Terminal**: Execute shell commands
- **Documents**: Create/edit Excel, PowerPoint, Markdown
- **Communication**: Gmail, Google Calendar, Notion
- **Media**: Analyze images, generate images, transcribe audio, download videos
- **Memory**: Query and learn from past workflows

## Operating Environment
- Platform: {platform}
- Working directory: {workspace}
- Current time: {datetime}

## Instructions
- Use ONLY the tools available to you. Do not hallucinate tool names.
- For web tasks: navigate → extract → process. Always cite sources.
- For file tasks: read existing files before modifying. Verify output.
- Save all output files to the workspace directory.
- Respond in the user's language.

## Workflow Guide (if provided)
{workflow_guide}
```

This is shorter than any individual current prompt and covers all capabilities.

---

## 8. Phase Plan

### Phase 1: Foundation (Week 1-2)
- Project scaffolding (`src/clients/desktop_app/daemon-ts/`)
- Express.js server: health check, CORS, SSE endpoint
- pi-ai integration: model selection, `complete()`, `stream()`
- pi-agent-core: `Agent` class with 1 test tool
- SSE event bridge: map pi-agent-core events → frontend SSE format
- **Verify**: Agent calls a tool, result streams to frontend via SSE

### Phase 2: Browser Automation (Week 2-5)
- Port browser-session.ts (Playwright JS CDP connection to Electron)
- Port action-executor.ts (click, type, navigate, extract, mouse, keyboard)
- Port page-snapshot.ts (DOM extraction, `[ref=eN]` element references)
- Port behavior-recorder.ts (CDP event recording for memory learning)
- Wrap as `AgentTool[]`
- **Verify**: Agent navigates browser, clicks elements, extracts data

### Phase 3: Agent Pipeline (Week 3-5, overlaps with Phase 2)
- Port orchestrator.ts (parent agent: direct reply / decompose / steer / cancel)
- Port task-planner.ts (memory-first decomposition, no agent_type)
- Port task-executor.ts (sequential execution, deps, replan)
- Single `createChildAgent()` factory with all tools
- Budget tracking via pi-ai usage
- **Verify**: Orchestrator decomposes task, executor runs subtasks with single unified agent

### Phase 4: Toolkits (Week 4-7, parallelizable)
- Core: file, terminal, search, human, replan
- Memory: HTTP calls to cloud backend (plan, query, learn)
- MCP base + gmail, gdrive, notion
- Document: excel, pptx, markitdown
- Media: image_gen, image_analysis, audio, video
- **Verify**: Each tool works in isolation via agent call

### Phase 5: Services & Integration (Week 6-9)
- Port quick-task-service.ts (main task execution)
- Port cloud-client.ts (cloud backend API)
- Port routes: quick_task, session, integrations, settings
- Connect to Electron (replace Python subprocess spawn)
- Port session management, workspace management, i18n
- **Verify**: Full end-to-end task execution, frontend unchanged

### Critical Path

```
Week 1-2: Foundation
    ↓
Week 2-5: Browser Automation ←── LONGEST
    ↓
Week 3-5: Agent Pipeline (overlaps)
    ↓                    ↗ Week 4-7: Toolkits (parallel)
Week 6-9: Services & Integration
```

---

## 9. Target Directory Structure

```
src/clients/desktop_app/daemon-ts/
├── package.json
├── tsconfig.json
├── src/
│   ├── server.ts                    # Express.js entry
│   ├── agent/
│   │   ├── orchestrator.ts          # Parent agent (direct reply / decompose / steer)
│   │   ├── task-planner.ts          # Decompose → subtasks (no agent_type)
│   │   ├── task-executor.ts         # Sequential execution with deps
│   │   ├── agent-factory.ts         # Single createChildAgent()
│   │   ├── budget.ts                # Cost tracking via pi-ai usage
│   │   └── schemas.ts               # Zod schemas
│   ├── browser/
│   │   ├── browser-session.ts       # Playwright JS CDP
│   │   ├── action-executor.ts       # DOM actions
│   │   ├── behavior-recorder.ts     # CDP recording for memory
│   │   ├── page-snapshot.ts         # DOM → text, [ref=eN]
│   │   └── config.ts                # Timeouts, retry
│   ├── tools/                       # Flat AgentTool[] per domain
│   │   ├── browser-tools.ts
│   │   ├── file-tools.ts
│   │   ├── terminal-tools.ts
│   │   ├── memory-tools.ts
│   │   ├── search-tools.ts
│   │   ├── human-tools.ts
│   │   ├── replan-tools.ts
│   │   ├── mcp-base.ts
│   │   ├── gmail-tools.ts
│   │   ├── notion-tools.ts
│   │   ├── gdrive-tools.ts
│   │   ├── calendar-tools.ts
│   │   ├── excel-tools.ts
│   │   ├── pptx-tools.ts
│   │   ├── image-tools.ts
│   │   ├── audio-tools.ts
│   │   └── video-tools.ts
│   ├── services/
│   │   ├── quick-task-service.ts    # Task execution orchestration
│   │   ├── cloud-client.ts          # Cloud backend HTTP
│   │   ├── storage-manager.ts       # File storage
│   │   └── recording-service.ts     # Recording management
│   ├── routes/
│   │   ├── quick-task.ts            # SSE stream + task endpoints
│   │   ├── session.ts
│   │   ├── integrations.ts
│   │   └── settings.ts
│   ├── events/
│   │   ├── types.ts                 # SSE event type definitions
│   │   ├── emitter.ts               # Queue-based event emitter
│   │   └── bridge.ts                # pi-agent-core events → SSE events
│   ├── prompts/
│   │   ├── orchestrator.ts
│   │   ├── unified-agent.ts         # Single prompt for all child agents
│   │   └── task-decomposition.ts
│   └── utils/
│       ├── i18n.ts
│       ├── logging.ts
│       └── session-manager.ts
```

---

## 10. Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| Browser `[ref=eN]` parity | HIGH | Port page_snapshot logic exactly, test with same pages |
| SSE event format mismatch | HIGH | Strict TypeScript types matching current Pydantic models |
| Tool regression | MEDIUM | Port one toolkit at a time, test each in isolation |
| Electron child process lifecycle | MEDIUM | Start as child process (like Python), migrate to in-process later |
| Document libs (Excel/PPTX) | MEDIUM | exceljs and pptxgenjs are mature |
| MCP protocol porting | MEDIUM | Port mcp_base first, then individual MCPs |
| pi-ai version stability | LOW | Pin version, pi-ai is v0.52.9 |
| Cloud backend compatibility | LOW | HTTP API contract unchanged |

---

## 11. Success Criteria

1. **Functional parity**: Existing task types all work (web research, file operations, terminal, documents, email, media)
2. **Frontend unchanged**: Same SSE event format, no frontend code changes needed
3. **Unified agent**: Single child agent type handles all subtasks, no pre-classification failures
4. **Multi-provider**: Switch between Anthropic/OpenAI/Google via config
5. **Multi-modal**: Image input support (screenshots as context, image analysis)
6. **No blocking**: All I/O truly async, no `to_thread` workarounds
7. **Always responsive**: Orchestrator handles user messages while child agents execute (via steer/cancel)
8. **Online learning**: ExecutionDataCollector → cloud backend learn API still works
9. **Code reduction**: ~38,000 Python → ~21,500 TypeScript (~43% reduction)
