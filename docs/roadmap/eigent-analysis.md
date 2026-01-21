# Eigent 项目分析

## 概述

Eigent 是一个基于 CAMEL-AI 框架的多智能体桌面自动化系统，支持 Computer Use 能力。本文档分析其核心实现，为 AMI 集成提供参考。

**项目地址:** https://github.com/eigent-ai/eigent

---

## 1. 项目架构

```
Eigent
├── Electron (桌面应用)
│   └── 启动 CDP 浏览器，管理会话
│
├── Python Backend (FastAPI)
│   ├── Agent 定义 (agent.py)
│   ├── Toolkit 工具包
│   └── Workforce 多智能体协作
│
└── React Frontend
    └── UI 界面
```

### 技术栈

| 组件 | 技术 |
|------|------|
| 桌面框架 | Electron |
| 后端 | Python FastAPI |
| Agent 框架 | CAMEL-AI |
| 浏览器自动化 | Playwright + CDP |
| 前端 | React |

---

## 2. Agent 系统

Eigent 定义了 5 个专业 Agent：

| Agent | 职责 | 工具 |
|-------|------|------|
| **Developer Agent** | 编码、终端操作、桌面自动化 | Terminal, Screenshot, File, WebDeploy |
| **Browser Agent** | 网页搜索、信息采集 | HybridBrowser, Search, Terminal |
| **Document Agent** | 文档、报告、演示文稿 | File, PPTX, Excel, MarkItDown |
| **Multi-Modal Agent** | 图像、音频、视频处理 | VideoDownloader, ImageAnalysis, AudioAnalysis |
| **Social Medium Agent** | 社交媒体、邮件 | WhatsApp, Twitter, LinkedIn, Gmail |

### Browser Agent 系统提示词

```
<role>
You are a Senior Research Analyst, a key member of a multi-agent team.
</role>

<web_search_workflow>
**If Google Search is Available:**
- Initial Search: Start with `search_google` to get relevant URLs
- Browser-Based Exploration: Use browser tools to investigate

**If Google Search is NOT Available:**
- MUST start with direct website search
- Type query using `browser_type` and submit with `browser_enter`
- Extract URLs from results

**Common Browser Operations:**
- Navigation: browser_visit_page, browser_click, browser_back
- Interaction: browser_type, browser_enter
- Multi-tab: browser_switch_tab
</web_search_workflow>

<mandatory_instructions>
- MUST use note-taking tools to record findings
- STRICTLY FORBIDDEN from inventing/guessing URLs
- MUST NOT answer from own knowledge
</mandatory_instructions>
```

---

## 3. 浏览器控制实现

### 3.1 两套实现方案

**方案 A: TypeScript + WebSocket**
```
HybridBrowserToolkit (Python)
    ↓ WebSocket
Node.js TypeScript 服务
    ↓ CDP
Electron 内置 Chromium
```

**方案 B: Python + Playwright**
```
HybridBrowserPythonToolkit
    ↓ Playwright
CDP 连接
    ↓
Electron 内置 Chromium
```

### 3.2 CDP 启动 (Electron 端)

```typescript
// electron/main/index.ts
let browser_port = 9222;

profileInitPromise = findAvailablePort(browser_port).then(async (port) => {
  browser_port = port;

  // 启用 Chrome DevTools Protocol
  app.commandLine.appendSwitch('remote-debugging-port', port + '');

  // 创建独立的浏览器配置目录
  const cdpProfile = path.join(browserProfilesBase, `cdp_profile_${port}`);
  app.commandLine.appendSwitch('user-data-dir', cdpProfile);
});
```

### 3.3 Playwright 连接 CDP

```python
# hybrid_browser_python_toolkit.py

class BrowserSession:
    async def _ensure_browser_inner(self) -> None:
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        port = env("browser_port", 9222)

        # 通过 CDP 连接到 Electron 的浏览器
        self._browser = await pl.chromium.connect_over_cdp(f"http://localhost:{port}")
        self._context = self._browser.contexts[0]

        # 初始化核心组件
        self.snapshot = PageSnapshot(self._page)
        self.executor = ActionExecutor(self._page, ...)
```

---

## 4. 可用的浏览器工具

| 工具 | 功能 |
|------|------|
| `browser_visit_page(url)` | 访问页面，返回快照 |
| `browser_click(ref)` | 点击元素（通过 ref ID） |
| `browser_type(ref, text)` | 在输入框输入文本 |
| `browser_enter()` | 模拟回车键 |
| `browser_back()` / `browser_forward()` | 前进/后退 |
| `browser_switch_tab(tab_id)` | 切换标签页 |
| `browser_scroll(direction, amount)` | 滚动页面 |
| `browser_get_page_snapshot()` | 获取页面文本快照 |
| `browser_get_som_screenshot()` | 获取带标记的截图 (SOM) |
| `browser_console_exec(code)` | 执行 JavaScript |

---

## 5. 页面理解机制

### 5.1 PageSnapshot

将 DOM 转换为 LLM 友好的文本格式：

```
Page: Amazon.com - Shopping
URL: https://www.amazon.com/s?k=headphones

Interactive Elements:
[1] <input type="text" placeholder="Search Amazon">
[2] <button>Search</button>
[3] <a href="/dp/B08...">Sony WH-1000XM4 - $248.00</a>
[4] <a href="/dp/B09...">Apple AirPods Pro - $189.99</a>
```

**优点：**
- LLM 可直接理解
- 元素有唯一引用 [n]
- 比完整 DOM 小得多

### 5.2 SOM (Set-of-Marks)

在截图上叠加元素标记：

- 每个可交互元素标注数字
- 用于视觉分析
- 支持精确定位

### 5.3 对比 AMI 现有方案

| 特性 | Eigent | AMI (现有) |
|------|--------|-----------|
| 页面表示 | PageSnapshot (文本) | Enhanced DOM (JSON) |
| 元素定位 | ref 引用 [n] | xpath |
| 数据量 | 小 | 较大 |
| LLM 友好度 | 高 | 中 |

---

## 6. 任务规划机制

### 6.1 任务分解提示词 (TASK_DECOMPOSE_PROMPT)

```
You need to decompose a complex task or enhance a simple one...

1. **Self-Contained Subtasks**: Each subtask must be fully
   self-sufficient and independently understandable.

2. **Define Clear Deliverables**: Each task must specify
   a clear, concrete deliverable.

3. **Full Workflow Completion**: Preserve the entire goal.
   Group sequential actions.

4. **Aggressive Parallelization**: Decompose into parallel
   subtasks when possible.

Output format:
<tasks>
<task>Subtask 1</task>
<task>Subtask 2</task>
</tasks>
```

### 6.2 执行流程

```
用户输入
    ↓
question_confirm_agent 判断复杂度
    ├─ 简单问题 → 直接回答
    └─ 复杂任务 ↓
        ↓
task_agent 使用 TASK_DECOMPOSE_PROMPT 分解任务
    ↓
生成子任务列表
    ↓
coordinator_agent 分配给合适的 Worker
    ↓
Workers 并行执行
    ↓
结果汇总返回
```

---

## 7. 需要移植到 AMI 的核心组件

### 7.1 必须移植

| 组件 | 用途 | 复杂度 |
|------|------|--------|
| **PageSnapshot** | 页面快照生成 | 低 |
| **ActionExecutor** | 基于 ref 的动作执行 | 低 |
| **ReAct 循环** | 自主执行逻辑 | 中 |

### 7.2 可选移植

| 组件 | 用途 | 说明 |
|------|------|------|
| NoteTakingToolkit | 记录发现 | Phase 2 Memory 集成时使用 |
| TASK_DECOMPOSE_PROMPT | 任务分解 | 参考其设计理念 |
| 多 Agent 协作 | 并行执行 | 暂不需要，保持 AMI 单 Agent 模式 |

### 7.3 不需要移植

| 组件 | 原因 |
|------|------|
| Electron 框架 | AMI 使用 Tauri |
| CAMEL-AI 框架 | AMI 有自己的 BaseAgent |
| Workforce 多智能体 | 与 AMI 架构不符 |
| WebSocket 浏览器方案 | Playwright 更简单 |

---

## 8. 关键代码位置

| 功能 | Eigent 文件路径 |
|------|----------------|
| Agent 定义 | `third-party/eigent/backend/app/utils/agent.py` |
| Browser Toolkit (TS) | `third-party/eigent/backend/app/utils/toolkit/hybrid_browser_toolkit.py` |
| Browser Toolkit (Python) | `third-party/eigent/backend/app/utils/toolkit/hybrid_browser_python_toolkit.py` |
| 截图工具 | `third-party/eigent/backend/app/utils/toolkit/screenshot_toolkit.py` |
| 终端工具 | `third-party/eigent/backend/app/utils/toolkit/terminal_toolkit.py` |
| 任务分解 | CAMEL 框架内 `TASK_DECOMPOSE_PROMPT` |
| CDP 启动 | `third-party/eigent/electron/main/index.ts` |

---

## 9. 总结

### Eigent 的优势

1. **PageSnapshot** - 简洁有效的页面表示
2. **ref 定位** - 比 xpath 更灵活
3. **自主执行** - 能处理意外情况
4. **笔记系统** - 记录执行发现

### 对 AMI 的借鉴

1. 采用 PageSnapshot 替代复杂 DOM
2. 使用 ref 定位而非 xpath
3. 引入 ReAct 循环实现自主执行
4. 保持与现有 Workflow 系统独立

### 不采用的部分

1. 多 Agent 协作架构（过于复杂）
2. CAMEL-AI 框架（保持 AMI 自有架构）
3. WebSocket 浏览器方案（Playwright 更简单）
