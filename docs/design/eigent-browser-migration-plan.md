# Eigent Browser Agent 完整复刻计划

## 1. 项目背景

### 1.1 目标

**完整复刻** Eigent 项目中 Browser Agent 的架构和能力，包括：
- Tool-calling 架构（替换现有 ReAct 架构）
- 完整的 Toolkit 系统
- Eigent 风格的 System Prompt
- 事件驱动的工具执行监控

### 1.2 Eigent 架构分析

#### 核心组件

```
┌─────────────────────────────────────────────────────────────┐
│                    ListenChatAgent                          │
│  (继承自 CAMEL ChatAgent，添加事件监听)                       │
├─────────────────────────────────────────────────────────────┤
│  - api_task_id: 任务 ID                                     │
│  - agent_name: Agent 名称                                   │
│  - step(): 执行一步，发送 activate/deactivate 事件          │
│  - _execute_tool(): 执行工具，发送工具事件                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Toolkits                               │
├──────────────┬──────────────┬───────────────┬───────────────┤
│ Browser      │ NoteTaking   │ Search        │ Terminal      │
│ Toolkit      │ Toolkit      │ Toolkit       │ Toolkit       │
├──────────────┼──────────────┼───────────────┼───────────────┤
│ browser_click│ append_note  │ search_google │ shell_exec    │
│ browser_type │ read_note    │               │               │
│ browser_visit│ create_note  │               │               │
│ ...          │ list_note    │               │               │
└──────────────┴──────────────┴───────────────┴───────────────┘
```

#### Tool-calling 执行流程

```
用户输入 "帮我在 Product Hunt 上找热门产品"
    │
    ▼
┌─────────────────────────────────────────┐
│ ChatAgent.step(input_message)           │
│  1. 将消息加入 memory                   │
│  2. 获取上下文 (with summarization)     │
│  3. 调用 LLM                           │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ LLM 返回 tool_call_requests             │
│  [                                      │
│    {tool: "browser_visit_page",         │
│     args: {url: "producthunt.com"}}     │
│  ]                                      │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ ChatAgent._execute_tool()               │
│  1. 发送 ActionActivateToolkitData      │
│  2. 执行工具: tool(**args)              │
│  3. 发送 ActionDeactivateToolkitData    │
│  4. 记录到 tool_call_records            │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ 工具结果加入 memory，继续循环           │
│  while True:                            │
│    if no tool_calls: break              │
│    execute tools                        │
│    add results to memory                │
│    call LLM again                       │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ LLM 返回最终文本响应                    │
│  "我找到了以下热门产品：..."            │
└─────────────────────────────────────────┘
```

#### Eigent Browser Agent 的 Toolkit 配置

```python
# 来自 eigent/backend/app/utils/agent.py browser_agent()

tools = [
    # 1. HumanToolkit - 人工协助
    *HumanToolkit.get_can_use_tools(project_id, Agents.browser_agent),

    # 2. HybridBrowserToolkit - 浏览器操作
    #    启用的工具:
    #    - browser_click
    #    - browser_type
    #    - browser_back
    #    - browser_forward
    #    - browser_select
    #    - browser_console_exec
    #    - browser_console_view
    #    - browser_switch_tab
    #    - browser_enter
    #    - browser_visit_page
    #    - browser_get_page_snapshot
    *web_toolkit_custom.get_tools(),

    # 3. TerminalToolkit - 终端命令
    #    - shell_exec
    *terminal_toolkit,

    # 4. NoteTakingToolkit - 笔记记录
    #    - append_note
    #    - read_note
    #    - create_note
    #    - list_note
    *note_toolkit.get_tools(),

    # 5. SearchToolkit - 搜索引擎 (可选)
    #    - search_google
    *search_tools,
]
```

### 1.3 与现有架构对比

| 特性 | Eigent (Tool-calling) | 我们现有 (ReAct) |
|------|----------------------|------------------|
| **LLM 交互** | Function calling API | 固定 JSON 格式输出 |
| **工具选择** | LLM 自由选择多个工具 | 每次只能返回一个 action |
| **执行循环** | while(has_tool_calls) | while(action != finish) |
| **Memory** | ChatHistoryMemory (自动管理) | 手动 action_history |
| **Plan** | 无显式 plan | 有 plan + path_ref |
| **笔记** | ✅ NoteTakingToolkit | ❌ 无 |
| **搜索** | ✅ SearchToolkit | ❌ 无 |
| **终端** | ✅ TerminalToolkit | ❌ 无 |

---

## 2. 完整复刻方案

### 2.1 架构决策

**方案：完整复刻 Eigent 的 Tool-calling 架构**

创建新的 `EigentStyleBrowserAgent`，实现：
1. Tool-calling 模式（使用 Anthropic tool_use API）
2. 完整的 Toolkit 系统
3. Eigent 风格的 System Prompt
4. Memory 自动管理
5. 保留 Memory Path 参考能力（作为 system prompt 的一部分）

### 2.2 新架构设计

```
┌─────────────────────────────────────────────────────────────┐
│              EigentStyleBrowserAgent                        │
├─────────────────────────────────────────────────────────────┤
│ 核心属性:                                                   │
│  - _llm_client: Anthropic client                           │
│  - _tools: List[FunctionTool]                              │
│  - _memory: List[Dict] (对话历史)                           │
│  - _memory_paths: 可选的参考路径                            │
│  - _note_toolkit: NoteTakingToolkit                        │
│  - _browser_session: HybridBrowserSession                  │
├─────────────────────────────────────────────────────────────┤
│ 核心方法:                                                   │
│  - execute(task, context) -> str                           │
│  - _step(message) -> response                              │
│  - _execute_tool(tool_name, args) -> result                │
│  - _build_tools_schema() -> List[Dict]                     │
│  - _format_system_prompt() -> str                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 详细任务分解

### 阶段一：Toolkit 系统 (基础设施)

#### 任务 1.1: 完善 BaseToolkit 和 FunctionTool
- **文件**: `tools/toolkits/base_toolkit.py`
- **状态**: ✅ 部分完成
- **待补充**:
  ```python
  class FunctionTool:
      def to_anthropic_tool(self) -> Dict:
          """转换为 Anthropic tool_use 格式"""
          return {
              "name": self.name,
              "description": self.description,
              "input_schema": {
                  "type": "object",
                  "properties": self._extract_properties(),
                  "required": self._extract_required()
              }
          }
  ```

#### 任务 1.2: 完善 NoteTakingToolkit
- **文件**: `tools/toolkits/note_taking_toolkit.py`
- **状态**: ✅ 已完成
- **工具列表**:
  | 工具 | 参数 | 描述 |
  |------|------|------|
  | `append_note` | note_name, content | 追加内容到笔记 |
  | `create_note` | note_name, content, overwrite | 创建新笔记 |
  | `read_note` | note_name | 读取笔记内容 |
  | `list_note` | - | 列出所有笔记 |

#### 任务 1.3: 创建 SearchToolkit
- **文件**: `tools/toolkits/search_toolkit.py`
- **状态**: 🔲 待完成
- **工具列表**:
  | 工具 | 参数 | 描述 |
  |------|------|------|
  | `search_google` | query, num_results=10 | Google 搜索 |
- **实现细节**:
  ```python
  class SearchToolkit(BaseToolkit):
      def __init__(self, google_api_key=None, search_engine_id=None):
          # 优先使用配置的 API Key
          # 否则降级为 DuckDuckGo

      def search_google(self, query: str, num_results: int = 10) -> List[Dict]:
          """
          返回: [
              {"title": "...", "link": "...", "snippet": "..."},
              ...
          ]
          """
  ```

#### 任务 1.4: 创建 TerminalToolkit
- **文件**: `tools/toolkits/terminal_toolkit.py`
- **状态**: 🔲 待完成
- **工具列表**:
  | 工具 | 参数 | 描述 |
  |------|------|------|
  | `shell_exec` | command, timeout=60 | 执行 shell 命令 |
- **安全措施**:
  - 工作目录限制
  - 超时控制
  - 敏感命令警告（rm -rf, sudo 等）

#### 任务 1.5: 创建 HumanToolkit
- **文件**: `tools/toolkits/human_toolkit.py`
- **状态**: 🔲 待完成
- **工具列表**:
  | 工具 | 参数 | 描述 |
  |------|------|------|
  | `ask_human` | question | 向用户提问，等待响应 |
  | `send_message` | title, description | 单向通知用户 |
- **实现细节**:
  - 通过回调函数与外部交互
  - 支持同步等待用户响应

#### 任务 1.6: 创建 BrowserToolkit
- **文件**: `tools/toolkits/browser_toolkit.py`
- **状态**: 🔲 待完成
- **工具列表**:
  | 工具 | 参数 | 描述 |
  |------|------|------|
  | `browser_visit_page` | url | 访问页面，返回快照 |
  | `browser_click` | ref/text/selector | 点击元素 |
  | `browser_type` | ref/selector, text | 输入文本 |
  | `browser_enter` | ref/selector | 按 Enter 键 |
  | `browser_back` | - | 返回 |
  | `browser_forward` | - | 前进 |
  | `browser_select` | ref/selector, value | 选择下拉框 |
  | `browser_switch_tab` | tab_id/index | 切换标签页 |
  | `browser_get_page_snapshot` | - | 获取当前快照 |
  | `browser_scroll` | direction, amount | 滚动页面 |
- **实现细节**:
  - 封装现有的 HybridBrowserSession
  - 每个操作返回页面快照

---

### 阶段二：Agent 核心实现

#### 任务 2.1: 创建 EigentStyleBrowserAgent
- **文件**: `agents/eigent_style_browser_agent.py`
- **状态**: 🔲 待完成
- **核心结构**:
  ```python
  class EigentStyleBrowserAgent(BaseStepAgent):
      """
      完整复刻 Eigent 的 Tool-calling 架构
      """

      def __init__(self):
          # Toolkit 初始化
          self._note_toolkit = NoteTakingToolkit(working_directory)
          self._search_toolkit = SearchToolkit()
          self._terminal_toolkit = TerminalToolkit()
          self._human_toolkit = HumanToolkit(callback)
          self._browser_toolkit = BrowserToolkit(session)

          # 收集所有工具
          self._tools = [
              *self._note_toolkit.get_tools(),
              *self._search_toolkit.get_tools(),
              *self._terminal_toolkit.get_tools(),
              *self._human_toolkit.get_tools(),
              *self._browser_toolkit.get_tools(),
          ]

          # Memory
          self._messages = []  # 对话历史

      async def execute(self, input_data, context):
          """主执行入口"""
          task = input_data.get("task")
          memory_paths = input_data.get("memory_paths")

          # 构建 system prompt
          system_prompt = self._build_system_prompt(memory_paths)

          # 执行循环
          response = await self._run_agent_loop(task, system_prompt)

          return {"result": response, "notes": self._note_toolkit.read_note()}

      async def _run_agent_loop(self, task, system_prompt):
          """Tool-calling 主循环"""
          self._messages = [{"role": "user", "content": task}]

          while True:
              # 调用 LLM
              response = await self._call_llm(system_prompt, self._messages)

              # 检查是否有 tool_use
              tool_uses = [b for b in response.content if b.type == "tool_use"]

              if not tool_uses:
                  # 没有工具调用，返回文本响应
                  return self._extract_text_response(response)

              # 执行所有工具
              tool_results = []
              for tool_use in tool_uses:
                  result = await self._execute_tool(tool_use.name, tool_use.input)
                  tool_results.append({
                      "type": "tool_result",
                      "tool_use_id": tool_use.id,
                      "content": result
                  })

              # 将工具结果加入消息历史
              self._messages.append({"role": "assistant", "content": response.content})
              self._messages.append({"role": "user", "content": tool_results})
  ```

#### 任务 2.2: 实现 Anthropic Tool Calling
- **文件**: 同上
- **关键代码**:
  ```python
  async def _call_llm(self, system_prompt, messages):
      """调用 Anthropic API with tools"""
      return self._llm_client.messages.create(
          model=self._model,
          max_tokens=4096,
          system=system_prompt,
          messages=messages,
          tools=self._build_tools_schema()
      )

  def _build_tools_schema(self):
      """构建 Anthropic tools schema"""
      return [tool.to_anthropic_tool() for tool in self._tools]
  ```

#### 任务 2.3: 实现工具执行路由
- **文件**: 同上
- **关键代码**:
  ```python
  async def _execute_tool(self, tool_name: str, args: Dict) -> str:
      """执行工具并返回结果"""
      # 查找工具
      tool = self._find_tool(tool_name)
      if not tool:
          return f"Error: Unknown tool '{tool_name}'"

      # 执行
      try:
          if asyncio.iscoroutinefunction(tool.func):
              result = await tool.func(**args)
          else:
              result = tool.func(**args)
          return str(result)
      except Exception as e:
          return f"Error executing {tool_name}: {e}"
  ```

---

### 阶段三：System Prompt 复刻

#### 任务 3.1: 复刻 Eigent 的 System Prompt
- **文件**: `agents/eigent_style_browser_agent.py`
- **状态**: 🔲 待完成
- **完整 Prompt 结构**:

```python
EIGENT_STYLE_SYSTEM_PROMPT = """
<role>
You are a Senior Research Analyst, a key member of a multi-agent team. Your
primary responsibility is to conduct expert-level web research to gather,
analyze, and document information required to solve the user's task. You
operate with precision, efficiency, and a commitment to data quality.
You must use the search/browser tools to get the information you need.
</role>

<operating_environment>
- System: {platform} ({architecture})
- Working Directory: {working_directory}
- Current Date: {current_date}
</operating_environment>

<mandatory_instructions>
- You MUST use the note-taking tools to record your findings. This is a
  critical part of your role. Your notes are the primary source of
  information for your teammates. To avoid information loss, you must not
  summarize your findings. Instead, record all information in detail.
  For every piece of information you gather, you must:
  1. Extract ALL relevant details: Quote all important sentences,
     statistics, or data points. Your goal is to capture the information
     as completely as possible.
  2. Cite your source: Include the exact URL where you found the
     information.
  Your notes should be a detailed and complete record of the information
  you have discovered.

- CRITICAL URL POLICY: You are STRICTLY FORBIDDEN from inventing,
  guessing, or constructing URLs yourself. You MUST only use URLs from
  trusted sources:
  1. URLs returned by search tools (search_google)
  2. URLs found on webpages you have visited through browser tools
  3. URLs provided by the user in their request
  Fabricating or guessing URLs is considered a critical error.

- You MUST NOT answer from your own knowledge. All information
  MUST be sourced from the web using the available tools.

- When you complete your task, your final response must be a comprehensive
  summary of your findings, presented in a clear, detailed format.

- When encountering verification challenges (like login, CAPTCHAs or
  robot checks), you MUST request help using the ask_human tool.
</mandatory_instructions>

<capabilities>
Your capabilities include:
- Search and get information from the web using search_google
- Use browser tools to investigate websites:
  - browser_visit_page: Open URLs
  - browser_click: Click elements
  - browser_type: Fill out forms
  - browser_enter: Submit forms
  - browser_back/forward: Navigate history
  - browser_switch_tab: Manage multiple pages
  - browser_get_page_snapshot: Get current page state
- Use the terminal tools (shell_exec) for data processing
- Use the note-taking tools to record your findings
- Use ask_human to request help when stuck
</capabilities>

<web_search_workflow>
**If Google Search is Available:**
1. Start with search_google to get relevant URLs
2. Use browser_visit_page to investigate URLs
3. Record findings with append_note

**If Google Search is NOT Available:**
1. Use browser_visit_page to go to search engines (google.com, bing.com)
2. Use browser_type + browser_enter to search manually
3. Extract URLs from search results
4. Visit and investigate URLs
5. Record findings with append_note
</web_search_workflow>

{memory_reference_section}
"""

MEMORY_REFERENCE_TEMPLATE = """
<memory_reference>
You have access to a VERIFIED SUCCESSFUL PATH from a similar past task.
This path shows real actions that worked before.

How to use:
1. The path is FACTUAL - represents real actions that worked
2. Analyze which parts are relevant to current task
3. You may use path segments as guidance
4. CRITICAL: Only trim front/back, NEVER skip middle steps

Reference Path (similarity: {score:.2f}):
{formatted_steps}
</memory_reference>
"""
```

---

### 阶段四：集成和测试

#### 任务 4.1: 集成到 QuickTaskService
- **文件**: `services/quick_task_service.py`
- **修改点**:
  ```python
  # 添加配置选项，选择使用哪种 Agent
  if config.use_eigent_style_agent:
      agent = EigentStyleBrowserAgent(...)
  else:
      agent = EigentBrowserAgent(...)  # 现有 ReAct 风格
  ```

#### 任务 4.2: 单元测试
- **文件**: `tests/test_eigent_style_agent.py`
- **测试用例**:
  1. Tool schema 生成正确
  2. 单工具调用正常
  3. 多工具调用正常
  4. 笔记记录正常
  5. 错误处理正常

#### 任务 4.3: 端到端测试
- **测试场景**:
  1. "在 Product Hunt 上找热门产品" - 搜索 + 浏览 + 记笔记
  2. "比较 iPhone 15 和 Samsung S24 的价格" - 多站点浏览
  3. 遇到登录页面 - ask_human 交互

---

## 4. 文件清单

### 新建文件

| 文件 | 描述 |
|------|------|
| `tools/toolkits/search_toolkit.py` | 搜索工具 |
| `tools/toolkits/terminal_toolkit.py` | 终端工具 |
| `tools/toolkits/human_toolkit.py` | 人工协助工具 |
| `tools/toolkits/browser_toolkit.py` | 浏览器工具（封装） |
| `tools/toolkits/memory_toolkit.py` | 记忆查询工具 (query_similar_workflows) |
| `agents/eigent_style_browser_agent.py` | 新的 Tool-calling Agent |
| `tests/test_eigent_style_agent.py` | 测试文件 |

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `tools/toolkits/__init__.py` | 导出新 Toolkit |
| `tools/toolkits/base_toolkit.py` | 完善 to_anthropic_tool() |
| `services/quick_task_service.py` | 集成新 Agent |
| `tools/CONTEXT.md` | 更新文档 |

---

## 5. 执行计划

### Week 1: Toolkit 系统
- [x] Day 1: 完善 base_toolkit.py (to_anthropic_tool) ✅
- [x] Day 2: 实现 SearchToolkit ✅
- [x] Day 3: 实现 TerminalToolkit ✅
- [x] Day 4: 实现 HumanToolkit ✅
- [x] Day 5: 实现 BrowserToolkit (封装现有 session) ✅

### Week 2: Agent 核心
- [x] Day 1-2: 实现 EigentStyleBrowserAgent 框架 ✅
- [x] Day 3: 实现 Tool-calling 循环 ✅
- [x] Day 4: 实现 System Prompt ✅
- [x] Day 5: 集成 Memory Path 参考 ✅

### Week 3: 测试和优化
- [ ] Day 1-2: 单元测试
- [ ] Day 3-4: 端到端测试
- [ ] Day 5: 文档和优化

---

## 6. 成功标准

1. **架构一致性**
   - [x] 使用 Anthropic tool_use API ✅
   - [x] Tool-calling 循环正常工作 ✅
   - [x] Memory 自动管理 ✅

2. **功能完整性**
   - [x] 5 个 Toolkit 全部可用 ✅
   - [x] System Prompt 与 Eigent 一致 ✅
   - [x] Memory Path 参考功能保留 ✅

3. **质量指标**
   - [ ] 所有测试通过
   - [ ] 无明显性能退化
   - [x] 代码有完整注释 ✅

---

## 7. 风险和缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Anthropic API 限制 | 高 | 错误重试、降级处理 |
| Tool 执行超时 | 中 | 超时控制、取消机制 |
| Memory 过长 | 中 | 自动摘要、裁剪 |
| 与现有系统冲突 | 低 | 新建 Agent，不修改现有代码 |

---

## 8. 附录：Eigent 关键代码参考

### A. ListenChatAgent._execute_tool()

```python
# eigent/backend/app/utils/agent.py:362-464
def _execute_tool(self, tool_call_request: ToolCallRequest) -> ToolCallingRecord:
    func_name = tool_call_request.tool_name
    tool: FunctionTool = self._internal_tools[func_name]
    args = tool_call_request.args

    # 发送 activate 事件
    asyncio.create_task(
        task_lock.put_queue(ActionActivateToolkitData(...))
    )

    # 执行工具
    result = tool(**args)

    # 发送 deactivate 事件
    asyncio.create_task(
        task_lock.put_queue(ActionDeactivateToolkitData(...))
    )

    return self._record_tool_calling(func_name, args, result, tool_call_id)
```

### B. Browser Agent System Prompt

```python
# eigent/backend/app/utils/agent.py:1036-1146
system_message = f"""
<role>
You are a Senior Research Analyst...
</role>

<mandatory_instructions>
- You MUST use the note-taking tools to record your findings...
- CRITICAL URL POLICY: You are STRICTLY FORBIDDEN from inventing URLs...
- You MUST NOT answer from your own knowledge...
</mandatory_instructions>

<web_search_workflow>
...
</web_search_workflow>
"""
```

### C. CAMEL ChatAgent.step() 核心循环

```python
# camel/agents/chat_agent.py:2844-2971
while True:
    # 获取上下文
    openai_messages, num_tokens = self._get_context_with_summarization()

    # 调用 LLM
    response = self._get_model_response(openai_messages, tool_schemas=...)

    # 检查 tool calls
    if tool_call_requests := response.tool_call_requests:
        for tool_call_request in tool_call_requests:
            result = self._execute_tool(tool_call_request)
            tool_call_records.append(result)
        continue  # 继续循环

    # 无 tool calls，检查是否完成
    break

return ChatAgentResponse(...)
```
