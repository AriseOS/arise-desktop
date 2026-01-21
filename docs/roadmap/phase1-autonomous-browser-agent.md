# Phase 1: 自主浏览器 Agent 实现规范

## 概述

本文档描述 Phase 1 的实际实现，包括核心 Agent、API 设计和前端页面。

**核心架构**: Quick Task 使用 `EigentBrowserAgent` 进行 LLM 引导的浏览器自动化，基于 ReAct 模式实现。

---

## 1. 核心 Agent 实现

### 1.1 EigentBrowserAgent

**文件路径:** `src/clients/desktop_app/ami_daemon/base_agent/agents/eigent_browser_agent.py`

从 CAMEL-AI/Eigent 项目移植的 LLM 引导浏览器自动化 Agent。

**核心流程 (ReAct 模式):**
1. 接收文字任务描述
2. 获取页面快照 (PageSnapshot)
3. 发送快照 + 任务给 LLM，获取 Plan + 下一步 Action
4. 通过 ActionExecutor 执行 Action
5. 重复 2-4 直到任务完成或达到 max_steps

```python
"""
EigentBrowserAgent - LLM-guided browser automation

核心组件:
- HybridBrowserSession: 浏览器会话管理
- PageSnapshot (unified_analyzer.js): DOM → 文本快照
- ActionExecutor: 执行浏览器动作
"""

class EigentBrowserAgent(BaseStepAgent):
    """
    Eigent Browser Agent - LLM-guided browser automation

    基于 ReAct (Reasoning + Acting) 模式:
    1. Observe: 捕获页面快照
    2. Think: LLM 分析并生成 Plan + Action
    3. Act: 执行 Action
    4. Repeat: 直到完成
    """

    SYSTEM_PROMPT = """
    You are a web automation assistant.

    Analyse the page snapshot and create a short high-level plan,
    then output the FIRST action to start with.

    Return a JSON object:
    {
      "plan": ["Step 1", "Step 2"],
      "action": {
        "type": "click",
        "ref": "e1"
      }
    }

    Available action types:
    - 'click': {"type": "click", "ref": "e1"}
    - 'type': {"type": "type", "ref": "e1", "text": "search text"}
    - 'select': {"type": "select", "ref": "e1", "value": "option"}
    - 'scroll': {"type": "scroll", "direction": "down", "amount": 300}
    - 'enter': {"type": "enter", "ref": "e1"}
    - 'navigate': {"type": "navigate", "url": "https://example.com"}
    - 'finish': {"type": "finish", "summary": "task completion summary"}

    IMPORTANT:
    - Use 'ref' values from snapshot (e.g., ref=e1, ref=e2)
    - Use 'finish' when task is completed
    """
```

### 1.2 与 AutonomousBrowserAgent 的区别

| 特性 | EigentBrowserAgent | AutonomousBrowserAgent |
|------|-------------------|----------------------|
| 用途 | Quick Task (独立任务) | Workflow 步骤 |
| 底层 | Eigent 工具 (PageSnapshot + ActionExecutor) | browser-use 库 |
| 元素定位 | `[ref=eN]` → `[aria-ref='eN']` | browser-use 内置 |
| LLM 调用 | 直接调用 Anthropic API (通过 CRS) | browser-use 封装 |
| 浏览器管理 | HybridBrowserSession (独立) | 共享 browser session |

---

## 2. Eigent 浏览器工具

### 2.1 PageSnapshot (unified_analyzer.js)

**文件路径:** `src/clients/desktop_app/ami_daemon/base_agent/tools/eigent_browser/page_snapshot.py`

将 DOM 转换为 LLM 友好的文本格式。

**输出示例:**
```yaml
- Page Snapshot
  url: https://www.amazon.com/s?k=headphones
  title: Amazon.com - Shopping
  viewport: 1280x720
  elements:
    - input [ref=e1] type="text" placeholder="Search Amazon"
    - button [ref=e2] "Search"
    - a [ref=e3] href="/dp/B08..." "Sony WH-1000XM4 - $248.00"
```

**关键特性:**
- 为每个可交互元素分配 `[ref=eN]` 引用
- 在 DOM 中设置 `aria-ref` 属性用于后续定位
- 支持差异快照 (diff_only) 减少 token 消耗

### 2.2 ActionExecutor

**文件路径:** `src/clients/desktop_app/ami_daemon/base_agent/tools/eigent_browser/action_executor.py`

执行 LLM 返回的浏览器动作。

```python
class ActionExecutor:
    """
    执行浏览器动作

    使用 [aria-ref='eN'] CSS 选择器定位元素
    """

    async def execute(self, action: Dict) -> Dict:
        """执行动作并返回结果"""
        action_type = action.get("type")
        ref = action.get("ref")

        if action_type == "click":
            return await self._click(ref)
        elif action_type == "type":
            return await self._type(ref, action.get("text"))
        # ... 其他动作类型
```

**支持的动作类型:**
- `click` - 点击元素
- `type` - 输入文本
- `select` - 选择下拉框选项
- `scroll` - 滚动页面
- `enter` - 按回车键
- `navigate` - 导航到 URL
- `back` / `forward` - 浏览器导航
- `finish` - 完成任务

### 2.3 HybridBrowserSession

**文件路径:** `src/clients/desktop_app/ami_daemon/base_agent/tools/eigent_browser/browser_session.py`

浏览器会话管理，支持多标签页。

```python
class HybridBrowserSession:
    """
    浏览器会话管理

    - 单例模式 (per event-loop + session-id)
    - 支持 headless / headful 模式
    - Stealth 模式防检测
    """

    async def visit(self, url: str) -> None:
        """导航到 URL"""

    async def get_snapshot(self, diff_only: bool = False) -> str:
        """获取页面快照"""

    async def exec_action(self, action: Dict) -> Dict:
        """执行动作"""
```

---

## 3. API 路由

### 3.1 Quick Task Router

**文件路径:** `src/clients/desktop_app/ami_daemon/routers/quick_task.py`

```python
router = APIRouter(prefix="/api/v1/quick-task", tags=["Quick Task"])

@router.post("/execute")
async def execute_task(
    request: TaskRequest,
    x_ami_api_key: Optional[str] = Header(None, alias="X-Ami-API-Key"),
):
    """
    提交任务执行

    Headers:
    - X-Ami-API-Key: 用户的 Ami API key (ami_xxxxx 格式)

    LLM 调用通过 CRS (Claude Relay Service) 转发。
    """

@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """查询任务状态"""

@router.get("/result/{task_id}")
async def get_task_result(task_id: str):
    """获取任务结果"""

@router.post("/cancel/{task_id}")
async def cancel_task(task_id: str):
    """取消任务"""

@router.websocket("/ws/{task_id}")
async def task_progress_websocket(websocket: WebSocket, task_id: str):
    """实时任务进度 WebSocket"""
```

### 3.2 Request/Response Models

```python
class TaskRequest(BaseModel):
    task: str = Field(..., description="Task description", min_length=1, max_length=2000)
    start_url: Optional[str] = Field(None, description="Optional starting URL")
    max_steps: int = Field(15, description="Maximum steps", ge=1, le=50)
    headless: bool = Field(False, description="Run browser in headless mode")

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str  # pending, running, completed, failed, cancelled
    plan: Optional[List] = None
    current_step: Optional[Dict] = None
    progress: float = 0.0
    error: Optional[str] = None

class TaskResultResponse(BaseModel):
    task_id: str
    success: bool
    output: Any = None
    plan: List = []
    steps_executed: int = 0
    total_steps: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    action_history: List = []
```

---

## 4. 服务层

### 4.1 QuickTaskService

**文件路径:** `src/clients/desktop_app/ami_daemon/services/quick_task_service.py`

```python
class QuickTaskService:
    """
    Quick Task 服务

    负责:
    - 任务提交和执行 (使用 EigentBrowserAgent)
    - 状态跟踪
    - 结果存储
    - 进度推送
    """

    def configure_llm(
        self,
        api_key: str,
        model: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        """
        配置 LLM

        Args:
            api_key: 用户的 Ami API key (ami_xxxxx 格式)
            model: LLM 模型名称
            base_url: CRS 代理 URL (https://api.ariseos.com/api)
        """

    async def submit_task(
        self,
        task: str,
        start_url: Optional[str] = None,
        max_steps: int = 15,
        headless: bool = False,
    ) -> str:
        """提交任务，返回 task_id"""

    async def _execute_task(self, task_id: str, max_steps: int, headless: bool):
        """
        执行任务 (内部方法)

        1. 创建 EigentBrowserAgent
        2. 传递 LLM 配置 (包括 CRS proxy URL)
        3. 执行任务
        4. 推送进度事件
        """
```

---

## 5. 前端页面

### 5.1 QuickTaskPage

**文件路径:** `src/clients/desktop_app/src/pages/QuickTaskPage.jsx`

```jsx
/**
 * Quick Task Page
 *
 * 状态:
 * - idle: 任务输入表单
 * - running: 执行状态和 action history
 * - completed: 成功结果
 * - failed: 错误信息
 */

export default function QuickTaskPage({ session, onNavigate, showStatus }) {
  // API 调用使用 X-Ami-API-Key header
  const handleStartTask = async () => {
    const response = await api.callAppBackend(
      '/api/v1/quick-task/execute',
      { task, start_url, max_steps, headless },
      'POST'
    );
    // WebSocket 连接获取实时进度
  };
}
```

### 5.2 导航入口

在 App.jsx 中添加:
```jsx
// 导航项
{ id: "quick-task", icon: "sparkle", label: "Quick Task" }

// 路由
case "quick-task":
  return <QuickTaskPage ... />;
```

---

## 6. LLM 调用架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Quick Task Flow                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Frontend (QuickTaskPage.jsx)                                  │
│  └── POST /execute + X-Ami-API-Key header                      │
│                                                                 │
│  API Router (quick_task.py)                                    │
│  └── 从 config 读取 CRS 配置                                    │
│  └── 调用 service.configure_llm(api_key, model, base_url)      │
│                                                                 │
│  QuickTaskService                                              │
│  └── 创建 EigentBrowserAgent                                   │
│  └── 传递 LLM 配置到 agent context                             │
│                                                                 │
│  EigentBrowserAgent                                            │
│  └── 使用 base_url 初始化 Anthropic client                     │
│  └── LLM 调用 → CRS (api.ariseos.com) → Anthropic API          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**CRS 配置 (app-backend.yaml):**
```yaml
llm:
  provider: anthropic
  model: claude-sonnet-4-5-20250929
  use_proxy: true
  proxy_url: https://api.ariseos.com/api
```

---

## 7. 测试指南

详见 `docs/roadmap/quick-task-testing-guide.md`

### 7.1 API 测试

```bash
# 使用 Ami API Key
curl -X POST http://localhost:8765/api/v1/quick-task/execute \
  -H "Content-Type: application/json" \
  -H "X-Ami-API-Key: ami_your_api_key_here" \
  -d '{
    "task": "Go to google.com and search for Python tutorials",
    "start_url": "https://www.google.com",
    "max_steps": 10,
    "headless": false
  }'
```

### 7.2 测试场景

| 场景 | 任务描述 |
|------|---------|
| 简单搜索 | Go to google.com and search for "AI news 2024" |
| 导航任务 | Navigate to github.com and find trending repositories |
| 表单填写 | Go to wikipedia.org, search for "Machine Learning" |
| 多步骤 | Go to Amazon, search for "wireless headphones", find products under $50 |

---

## 8. 文件结构

```
ami_daemon/
├── routers/
│   └── quick_task.py              # Quick Task API 路由
├── services/
│   └── quick_task_service.py      # 任务管理服务
└── base_agent/
    ├── agents/
    │   ├── eigent_browser_agent.py    # Quick Task 使用的 Agent
    │   └── autonomous_browser_agent.py # Workflow 使用的 Agent (browser-use wrapper)
    └── tools/
        └── eigent_browser/
            ├── page_snapshot.py       # 页面快照
            ├── action_executor.py     # 动作执行器
            ├── browser_session.py     # 浏览器会话
            ├── unified_analyzer.js    # DOM 分析脚本
            └── config_loader.py       # 配置加载
```

---

## 9. 后续开发

参考后续 Phase 文档:
- Phase 2: Memory 生成 Plan
- Phase 3: Memory 纠错能力
- Phase 4: Workflow 协作
