# Design: Remove CAMEL-AI Dependency, Build Lightweight AMI Agent Core

## Context

AMI depends on CAMEL-AI library but only uses a fraction of it. The dependency causes a critical bug: CAMEL's auto-summarization triggers when browser page snapshots (~75K tokens) fill the context window, producing a generic summary that loses browser state. The LLM then sees the original subtask prompt again and restarts from scratch — a dead loop.

Eigent avoids this by cloning fresh agents per subtask, but our architecture reuses agents. The real fix is not patching CAMEL's summarization — it's removing the dependency entirely and building a simple agent loop we fully control.

**What AMI actually uses from CAMEL** (11 files, ~26 imports):
- `ChatAgent` — multi-turn tool calling loop (AMI wraps it with 1,711 lines, only 2 `super()` calls)
- `FunctionTool` — wraps callables, generates JSON schema for LLM
- `BaseModelBackend` — AMI completely replaces the implementation (OpenAI->Anthropic conversion)
- `AgentMemory` — auto-summarization (the bug source)
- Multimodal Toolkits — thin wrappers around CAMEL's image/audio/screenshot implementations

**What AMI already has** (no changes needed):
- `AnthropicProvider` with `generate_with_tools()` — direct Anthropic API calls
- `ToolCallResponse`, `ToolUseBlock`, `TextBlock` data types
- `ProviderCache` for efficient provider reuse
- All custom toolkits (Browser, NoteTaking, Search, Terminal, etc.)
- SSE event system (`ActivateAgentData`, `DeactivateToolkitData`, etc.)
- `@listen_toolkit` decorator for auto event emission

---

## Architecture

### New Module Structure

```
src/clients/desktop_app/ami_daemon/base_agent/core/
  ami_tool.py            # NEW: Tool wrapper (replaces FunctionTool)
  ami_agent.py           # NEW: Agent loop (replaces ChatAgent + ListenChatAgent)
  ami_browser_agent.py   # NEW: Browser agent (replaces ListenBrowserAgent)
  agent_factories.py     # MODIFIED: Use new classes
  ami_task_executor.py   # MODIFIED: response.text instead of response.msg.content
  ami_task_planner.py    # MODIFIED: type hints only
  orchestrator_agent.py  # MODIFIED: Use AMITool

  listen_chat_agent.py   # DELETE (1,712 lines)
  listen_browser_agent.py# DELETE (440 lines)
  ami_model_backend.py   # DELETE (543 lines)

src/clients/desktop_app/ami_daemon/base_agent/tools/toolkits/
  base_toolkit.py              # MODIFIED: one import line change
  image_generation_toolkit.py  # MODIFIED: direct OpenAI SDK, remove CAMEL
  image_analysis_toolkit.py    # MODIFIED: direct AnthropicProvider, remove CAMEL
  audio_analysis_toolkit.py    # MODIFIED: direct OpenAI Whisper SDK, remove CAMEL
  screenshot_toolkit.py        # MODIFIED: direct PIL, remove CAMEL
  web_deploy_toolkit.py        # MODIFIED: direct HTTP, remove CAMEL
```

### Data Flow (Before vs After)

**Before (3 format conversions):**
```
Toolkit -> FunctionTool(callable)
                | OpenAI tool schema
Agent -> ChatAgent.astep() -> CAMEL loop
                | OpenAI messages
AMIModelBackend._async_run() -> convert OpenAI->Anthropic
                | Anthropic messages
AnthropicProvider.generate_with_tools()
```

**After (0 conversions):**
```
Toolkit -> AMITool(callable)
                | Anthropic tool schema (direct)
Agent -> AMIAgent.astep() -> simple loop
                | Anthropic messages (native)
AnthropicProvider.generate_with_tools()
```

---

## 1. AMITool — Replaces FunctionTool

**File**: `src/clients/desktop_app/ami_daemon/base_agent/core/ami_tool.py` (~200 lines)

### Schema Generation

Uses `inspect.signature()` + `get_type_hints()` + `docstring_parser` to generate **Anthropic tool schema directly**:

```python
class AMITool:
    def __init__(self, func: Callable, name: str = None, description: str = None):
        self.func = func
        self._name = name or func.__name__
        self._description = description
        self.is_async = asyncio.iscoroutinefunction(func)

    def get_function_name(self) -> str: ...        # Backward compatible with FunctionTool
    def get_function_description(self) -> str: ...  # From docstring

    def to_anthropic_schema(self) -> Dict[str, Any]:
        """Returns {"name", "description", "input_schema": {...}}"""
        return {
            "name": self._name,
            "description": self.get_function_description(),
            "input_schema": self._build_input_schema(),  # JSON Schema from type hints
        }

    def _build_input_schema(self) -> Dict[str, Any]:
        """Parse function signature -> JSON Schema for parameters."""
        # inspect.signature() -> get type hints -> map to JSON types
        # docstring_parser -> extract parameter descriptions
        # Handle Optional, List, Dict, Literal, Enum types
```

### Key Design Decisions

- Output format: Anthropic native `{"name", "description", "input_schema"}` — NOT OpenAI `{"type": "function", "function": {...}}`
- Schema cached after first generation
- `__call__(**kwargs)` for sync, `acall(**kwargs)` for async
- `get_function_name()` preserved for backward compatibility with toolkit code

### Migration

In `base_toolkit.py`, change one import:
```python
# Before: from camel.toolkits import FunctionTool
# After:
from ..core.ami_tool import AMITool as FunctionTool
```

All existing toolkit code (`FunctionTool(self.search_google)`) works unchanged.

---

## 2. AMIAgent — Replaces ChatAgent + ListenChatAgent

**File**: `src/clients/desktop_app/ami_daemon/base_agent/core/ami_agent.py` (~600 lines)

### Message Format (Anthropic Native)

No OpenAI intermediate format. Messages stored directly as Anthropic expects:

```python
self._system_prompt: str = "..."
self._messages: List[Dict[str, Any]] = [
    {"role": "user", "content": "Search for AI trends"},
    {"role": "assistant", "content": [
        {"type": "text", "text": "I'll search..."},
        {"type": "tool_use", "id": "toolu_01", "name": "search_google", "input": {"query": "..."}},
    ]},
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "toolu_01", "content": "Results..."},
    ]},
]
```

### Core Loop (`astep`)

```python
async def astep(self, input_message: str) -> AMIAgentResponse:
    # 1. Check cancellation, increment step count
    # 2. Enrich message (workflow guide + page operations)
    # 3. Append user message to self._messages
    # 4. Emit ActivateAgentData SSE

    while iteration < max_iterations:
        # 5. Check cancellation + pause
        # 6. Call self._provider.generate_with_tools(system_prompt, messages, tools)
        # 7. Append assistant response to self._messages

        if not response.has_tool_use():
            # 8a. Done — return AMIAgentResponse(text=...)
            break

        for tool_use in response.get_tool_uses():
            # 8b. Emit ActivateToolkitData
            # 8c. Execute tool (async or via asyncio.to_thread)
            # 8d. Truncate result if too large
            # 8e. Emit DeactivateToolkitData

        # 9. Append tool results as user message
        # 10. Truncate OLD tool results if context too large

    # 11. Emit DeactivateAgentData
    return AMIAgentResponse(text=..., tool_calls=..., stop_reason=...)
```

### Context Management — NO Summarization

Replace CAMEL's `_get_context_with_summarization` with simple truncation:

```python
def _maybe_truncate_old_results(self) -> None:
    """When context grows too large, truncate OLD tool_result blocks.

    Strategy:
    - Estimate token count (len(content) // 4)
    - If > threshold (e.g., 150K tokens), find oldest tool_result blocks
    - Replace their content with "[Truncated]"
    - Never truncate: system prompt, user task messages, last N exchanges

    This preserves the conversation STRUCTURE (LLM knows it called a tool
    and got a result) while reducing token count. The LLM can still see
    WHAT it did, just not the full page snapshot.
    """
```

Key difference from CAMEL: **structure is preserved, only content is shortened**. The LLM still sees the full sequence of actions it took, so it doesn't restart from scratch.

### Features Preserved from ListenChatAgent

All 1,712 lines of ListenChatAgent functionality mapped to AMIAgent:

| Feature | Implementation |
|---------|---------------|
| SSE events (agent/toolkit activate/deactivate) | Same `_emit_event()` pattern |
| Workflow guide injection | `_enrich_message()` appends guide to input |
| Page operations cache | `cache_page_operations()`, `set_current_url()` |
| Workflow hints + `workflow_hint_done` tool | Same methods, registered as AMITool |
| Cancellation check | `_is_cancelled()` via `task_state._cancel_event` |
| Pause/resume | `_wait_if_paused()` via asyncio.Event |
| Step counting + max_steps | Same |
| Progress callback | Same |
| Model-visible snapshot export | `_write_model_visible_snapshot()` on truncation |
| `@listen_toolkit` decorator bypass | Same `has_listen_decorator` check |
| Toolkit name inference | Same `_infer_toolkit_name()` helper |
| Tool result truncation | `_truncate_result()` character-based |
| Note toolkit reference | `set_note_toolkit()` for workflow guide persistence |

### What's NOT Preserved (Intentionally Removed)

| Removed | Reason |
|---------|--------|
| `clone()` / `clone(with_memory=)` | No CAMEL cloning needed |
| `reset()` / `init_messages()` / `clear_memory()` | Just `self._messages = []` |
| `_build_conversation_text_from_messages()` | No summarization |
| `_get_context_with_summarization()` | No summarization |
| `_update_memory_with_summary()` | No summarization |
| `summarize()` / `asummarize()` | No summarization |
| `update_memory()` / `memory.write_record()` | Direct list append |
| `BaseModelBackend` / `AMIModelBackend` | Direct provider call |
| OpenAI<->Anthropic format conversion | Native Anthropic throughout |
| `response_terminators` | Not used in AMI |
| `SimpleTokenCounter` | Character-based estimate inline |
| `_shared_executor` / thread pool for sync->async | `asyncio.to_thread()` instead |

### Response Type

```python
@dataclass
class AMIAgentResponse:
    text: str                          # Final text from LLM
    tool_calls: List[Dict[str, Any]]   # All tool calls made during this turn
    stop_reason: str                   # "end_turn" | "max_tokens"
```

---

## 3. AMIBrowserAgent — Replaces ListenBrowserAgent

**File**: `src/clients/desktop_app/ami_daemon/base_agent/core/ami_browser_agent.py` (~200 lines)

Extends `AMIAgent` with:
- `set_memory_context()` — Memory context (L1/L2/L3 workflow guide)
- `set_current_url()` override — triggers page operations query
- `_start_page_operations_query()` / `_query_page_operations()` — async Memory queries
- `_ensure_page_operations()` — await inflight queries
- Page operations checked URL dedup set

Same features as current `ListenBrowserAgent`, minus CAMEL dependencies.

---

## 4. Agent Factories Changes

**File**: `agent_factories.py`

### Before
```python
from camel.agents import ChatAgent
model_config = AMIModelBackend(model_type=model, api_key=key, url=url)
agent = ListenChatAgent(task_state, name, system_message, model=model_config, token_limit=200000, tools=tools)
```

### After
```python
from src.common.llm import AnthropicProvider
provider = AnthropicProvider(api_key=key, model_name=model, base_url=url)
agent = AMIAgent(task_state, name, provider=provider, system_prompt=system_message, tools=tools, context_token_limit=180000)
```

- Remove `create_model_backend()` function
- Remove `token_limit` parameter (no CAMEL summarization)
- Add `context_token_limit` for truncation threshold
- `create_task_summary_agent()` -> direct `provider.generate_response()` call

---

## 5. Multimodal Toolkit Strategy — Remove CAMEL Completely

CAMEL multimodal toolkits are extremely thin wrappers. The underlying logic:

| Toolkit | CAMEL Bottom Layer | Replacement |
|---------|-------------------|-------------|
| `ImageGenerationToolkit` | `OpenAI().images.generate()` | Direct `openai` SDK call (~30 lines) |
| `ImageAnalysisToolkit` | Send image as message content to vision model | Direct `AnthropicProvider` with image content block (~40 lines) |
| `AudioAnalysisToolkit` | `OpenAI().audio.transcriptions.create()` (Whisper) | Direct `openai` SDK call (~30 lines) |
| `ScreenshotToolkit` | `PIL.ImageGrab.grab()` + save to file | Direct `PIL` call (~20 lines) |
| `WebDeployToolkit` | HTTP POST to deploy server | Direct `httpx`/`requests` call (~50 lines) |

### Changes per toolkit

**`image_generation_toolkit.py`** — Replace `CAMELImageGenToolkit` with direct OpenAI SDK:
```python
# Before: self._camel_toolkit.generate_image(prompt=prompt, image_name=image_name, n=n)
# After:
from openai import OpenAI
client = OpenAI(api_key=api_key, base_url=url)
response = client.images.generate(model=model, prompt=prompt, size=size, quality=quality, n=n)
# Save b64 data or return URL
```

**`image_analysis_toolkit.py`** — Replace `CAMELImageAnalysisToolkit` with `AnthropicProvider`:
```python
# Before: self._camel_toolkit.image_to_text(image_path=image_path)
# After: Send image as Anthropic content block via provider
import base64
image_data = base64.b64encode(open(image_path, "rb").read()).decode()
messages = [{"role": "user", "content": [
    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_data}},
    {"type": "text", "text": prompt},
]}]
response = await self._provider.generate_with_tools(system_prompt="", messages=messages, tools=[])
return response.get_text()
```

**`audio_analysis_toolkit.py`** — Replace `CAMELAudioAnalysisToolkit` with direct OpenAI Whisper SDK:
```python
# Before: self._camel_toolkit.audio2text(audio_path=audio_path)
# After:
from openai import OpenAI
client = OpenAI(api_key=api_key)
with open(audio_path, "rb") as f:
    transcript = client.audio.transcriptions.create(model="whisper-1", file=f)
return transcript.text
```

**`screenshot_toolkit.py`** — Replace `BaseScreenshotToolkit` with direct PIL:
```python
# Before: self._base_toolkit.get_tools()
# After:
from PIL import ImageGrab
def take_screenshot(self, filename: str = "screenshot.png") -> str:
    img = ImageGrab.grab()
    path = self._working_directory / filename
    img.save(path)
    return str(path)
```

**`web_deploy_toolkit.py`** — Replace `BaseWebDeployToolkit` with direct HTTP:
```python
# Before: self._base_toolkit.deploy_html_content(...)
# After: Direct HTTP POST to deployment server
import httpx
response = httpx.post(f"http://{server_ip}:{port}/deploy", files={"file": content}, data={"subdirectory": subdir})
```

### No `_camel_compat.py` needed

With all multimodal toolkits rewritten, there is no remaining CAMEL dependency anywhere. The `_camel_compat.py` file is not needed.

**Total CAMEL imports after migration: 0**

---

## 6. AMI Task Executor Changes

**File**: `ami_task_executor.py` — minimal changes:

```python
# Before:
if hasattr(response, 'msg') and response.msg:
    subtask.result = response.msg.content

# After:
subtask.result = response.text
```

The `agent.astep(prompt)` interface is preserved. Executor doesn't need to know about internal agent changes.

---

## 7. Files Summary

### New Files (~1,000 lines)
| File | Lines | Purpose |
|------|-------|---------|
| `ami_tool.py` | ~200 | Tool wrapper + schema generation |
| `ami_agent.py` | ~600 | Core agent loop |
| `ami_browser_agent.py` | ~200 | Browser-specific agent |

### Deleted Files (~2,695 lines)
| File | Lines | Reason |
|------|-------|--------|
| `listen_chat_agent.py` | 1,712 | Replaced by `ami_agent.py` |
| `listen_browser_agent.py` | 440 | Replaced by `ami_browser_agent.py` |
| `ami_model_backend.py` | 543 | Direct provider calls, no adapter needed |

### Modified Files
| File | Change |
|------|--------|
| `agent_factories.py` | Use AMIAgent/AMITool, direct AnthropicProvider |
| `ami_task_executor.py` | `response.text` instead of `response.msg.content` |
| `ami_task_planner.py` | Type hint change only |
| `orchestrator_agent.py` | AMITool instead of FunctionTool |
| `base_toolkit.py` | One import line change |
| `image_generation_toolkit.py` | Direct OpenAI SDK, remove CAMEL wrapper |
| `image_analysis_toolkit.py` | Direct AnthropicProvider, remove CAMEL wrapper |
| `audio_analysis_toolkit.py` | Direct OpenAI Whisper SDK, remove CAMEL wrapper |
| `screenshot_toolkit.py` | Direct PIL, remove CAMEL wrapper |
| `web_deploy_toolkit.py` | Direct HTTP, remove CAMEL wrapper |

### Net: ~1,700 lines reduction, zero CAMEL imports, full control over agent behavior

### CAMEL package
After migration, `camel-ai` can be removed from `requirements.txt` entirely.

---

## 8. Implementation Order

1. **`ami_tool.py`** — Create AMITool, update `base_toolkit.py` import, verify all toolkits still produce valid schemas
2. **`ami_agent.py`** — Core loop with all features from ListenChatAgent
3. **`ami_browser_agent.py`** — Browser-specific extensions
4. **Multimodal toolkits** — Rewrite 5 toolkits to use direct SDK calls
5. **`agent_factories.py`** — Switch to new classes, direct AnthropicProvider
6. **`ami_task_executor.py`** + `orchestrator_agent.py` — Response format + tool import changes
7. **Delete** old files (`listen_chat_agent.py`, `listen_browser_agent.py`, `ami_model_backend.py`)
8. **Remove** `camel-ai` from `requirements.txt`
9. **Update** `core/CONTEXT.md`

---

## 9. Verification

1. Run an Amazon task (the one that triggered summarization bugs) — verify no summarization, no restart
2. Check SSE events are still emitted correctly (frontend agent timeline)
3. Verify workflow guide injection appears in LLM prompt
4. Verify page operations cache injection works
5. Verify multimodal agent still works (image generation/analysis)
6. Check cancellation works mid-task
7. Check context truncation kicks in for very long sessions without losing conversation structure
