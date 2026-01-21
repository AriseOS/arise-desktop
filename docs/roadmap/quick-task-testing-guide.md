# Quick Task 测试指南

## 概述

Quick Task 是 AMI 的自主浏览器自动化功能，允许用户用自然语言描述任务，由 EigentBrowserAgent 自主完成。

**LLM 调用架构**:
- 所有 LLM 调用通过 **Claude Relay Service (CRS)** 转发
- 使用用户的 **Ami API Key** (`ami_xxxxx` 格式) 进行身份验证
- CRS URL: `https://api.ariseos.com/api`

---

## 1. 环境准备

### 1.1 获取 Ami API Key

用户需要有有效的 Ami API Key (格式: `ami_xxxxx`)。这个 key 用于:
- 身份验证
- 配额管理
- LLM 调用计费

### 1.2 开发环境配置 (可选)

如果不想使用 CRS，可以设置环境变量直接调用 Anthropic:

```bash
# 仅用于本地开发测试
export ANTHROPIC_API_KEY="sk-ant-xxx..."
```

注意: 生产环境应通过 `X-Ami-API-Key` header 使用 CRS。

### 1.2 安装依赖

```bash
# Python 后端依赖
cd src/clients/desktop_app/ami_daemon
pip install -r requirements.txt

# Playwright 浏览器
pip install playwright
playwright install chromium
```

### 1.3 验证安装

```bash
# 验证 Playwright
python -c "from playwright.async_api import async_playwright; print('Playwright OK')"

# 验证 Anthropic
python -c "import anthropic; print('Anthropic OK')"
```

---

## 2. 启动服务

### 2.1 启动后端

```bash
cd src/clients/desktop_app/ami_daemon
python daemon.py
```

预期输出:
```
INFO:     App Backend daemon starting
INFO:     ✓ Browser manager initialized
INFO:     ✓ Workflow executor initialized
INFO:     ✅ App Backend ready!
INFO:     Uvicorn running on http://0.0.0.0:8765
```

### 2.2 验证服务

```bash
curl http://localhost:8765/health
```

预期响应:
```json
{
  "status": "ok",
  "magic": "ami-daemon-0.0.x",
  "version": "0.0.x",
  "browser_ready": false
}
```

---

## 3. API 测试

### 3.1 提交任务

**推荐: 使用 Ami API Key (通过 CRS)**
```bash
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

**备选: 使用环境变量 (仅限开发)**
```bash
# 需要先设置 ANTHROPIC_API_KEY 环境变量
curl -X POST http://localhost:8765/api/v1/quick-task/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Go to google.com and search for Python tutorials",
    "start_url": "https://www.google.com",
    "max_steps": 10,
    "headless": false
  }'
```

预期响应:
```json
{
  "task_id": "abc12345",
  "status": "started",
  "message": "Task submitted successfully"
}
```

### 3.2 查询状态

```bash
# 替换 {task_id} 为实际的 task_id
curl http://localhost:8765/api/v1/quick-task/status/{task_id}
```

预期响应:
```json
{
  "task_id": "abc12345",
  "status": "running",
  "plan": [],
  "current_step": null,
  "progress": 0.0,
  "error": null
}
```

状态值:
- `pending` - 等待执行
- `running` - 正在执行
- `completed` - 执行完成
- `failed` - 执行失败
- `cancelled` - 已取消

### 3.3 获取结果

```bash
curl http://localhost:8765/api/v1/quick-task/result/{task_id}
```

预期响应 (成功):
```json
{
  "task_id": "abc12345",
  "success": true,
  "output": "Task completed: searched for Python tutorials",
  "plan": [],
  "steps_executed": 5,
  "total_steps": 0,
  "duration_seconds": 0,
  "error": null,
  "action_history": [
    {
      "action": {"type": "type", "ref": "e1", "text": "Python tutorials"},
      "result": "Typed text",
      "success": true
    },
    {
      "action": {"type": "enter", "ref": "e1"},
      "result": "Pressed Enter",
      "success": true
    }
  ]
}
```

### 3.4 取消任务

```bash
curl -X POST http://localhost:8765/api/v1/quick-task/cancel/{task_id}
```

### 3.5 WebSocket 实时进度

使用 websocat (命令行 WebSocket 工具):

```bash
# 安装
brew install websocat  # macOS
# 或
cargo install websocat  # 通用

# 连接
websocat ws://localhost:8765/api/v1/quick-task/ws/{task_id}
```

WebSocket 事件:
```json
// 连接确认
{"event": "connected", "task_id": "abc12345"}

// 任务开始
{"event": "task_started", "task_id": "abc12345", "task": "..."}

// Plan 生成 (LLM 返回的计划)
{"event": "plan_generated", "plan": ["Step 1", "Step 2", "Step 3"], "first_action": {"type": "click", "ref": "e1"}}

// 步骤开始执行
{"event": "step_started", "step": 1, "max_steps": 10, "action": {"type": "click", "ref": "e1"}, "action_type": "click"}

// 步骤执行成功
{"event": "step_completed", "step": 1, "max_steps": 10, "action": {"type": "click", "ref": "e1"}, "result": "Clicked element", "action_history": [...]}

// 步骤执行失败 (但任务继续)
{"event": "step_failed", "step": 2, "max_steps": 10, "action": {"type": "type", "ref": "e2"}, "error": "Element not found", "action_history": [...]}

// 任务完成
{"event": "task_completed", "output": "Task completed: searched for...", "action_history": [...]}

// 任务失败
{"event": "task_failed", "error": "..."}

// 任务取消
{"event": "task_cancelled"}

// 心跳 (30秒无事件时发送)
{"event": "heartbeat"}
```

**事件顺序示例**:
```
connected → task_started → plan_generated → step_started → step_completed → step_started → step_completed → ... → task_completed
```

---

## 4. 测试场景

### 4.1 简单搜索

| 字段 | 值 |
|------|-----|
| task | Go to google.com and search for "AI news 2024" |
| start_url | https://www.google.com |
| max_steps | 10 |
| headless | false |

预期行为:
1. 浏览器打开 Google
2. 定位搜索框 (ref=eX)
3. 输入搜索词
4. 按回车或点击搜索按钮
5. 返回 finish action

### 4.2 导航任务

| 字段 | 值 |
|------|-----|
| task | Navigate to github.com and find the trending repositories page |
| start_url | https://github.com |
| max_steps | 15 |
| headless | false |

预期行为:
1. 打开 GitHub
2. 找到 Explore 或 Trending 链接
3. 点击导航
4. 确认到达 trending 页面
5. 返回 finish action

### 4.3 表单填写

| 字段 | 值 |
|------|-----|
| task | Go to wikipedia.org, search for "Machine Learning" |
| start_url | https://www.wikipedia.org |
| max_steps | 10 |
| headless | false |

### 4.4 多步骤任务

| 字段 | 值 |
|------|-----|
| task | Go to Amazon, search for "wireless headphones", and find products under $50 |
| start_url | https://www.amazon.com |
| max_steps | 20 |
| headless | false |

---

## 5. 前端测试

### 5.1 启动前端

```bash
cd src/clients/desktop_app
npm install
npm run tauri dev
```

### 5.2 导航到 Quick Task

1. 登录应用
2. 点击底部导航栏的 "Quick Task" (sparkle 图标)
3. 进入 Quick Task 页面

### 5.3 执行任务

1. 在文本框输入任务描述
2. (可选) 输入起始 URL
3. (可选) 调整 max_steps
4. 点击 "Start Task"
5. 观察浏览器自动执行
6. 查看执行结果

### 5.4 预期 UI 状态

- **idle**: 显示任务输入表单和示例任务
- **running**: 显示执行状态和 action history
- **completed**: 显示成功结果和完整 action history
- **failed**: 显示错误信息和失败前的 action history

---

## 6. 常见问题

### 6.1 浏览器不启动

**症状**: 任务提交后没有浏览器窗口出现

**排查步骤**:
```bash
# 检查 Playwright 安装
playwright install chromium

# 检查日志
tail -f ~/.ami/logs/app.log
```

### 6.2 API Key 错误

**症状**: 任务失败，提示 authentication error

**解决方案**:
```bash
# 检查 Ami API Key 是否正确
# 格式应该是 ami_xxxxx

# 通过请求头传递
curl -H "X-Ami-API-Key: ami_your_key_here" ...

# 或者设置环境变量 (仅限开发)
export ANTHROPIC_API_KEY="sk-ant-xxx..."
```

**CRS 相关错误**:
- 401 Unauthorized: API Key 无效或已过期
- 429 Too Many Requests: 超出配额限制
- 502 Bad Gateway: CRS 服务暂时不可用

### 6.3 任务超时

**症状**: 执行到一半停止

**解决方案**:
- 增加 `max_steps` 参数
- 检查网络连接
- 查看 action_history 定位失败点

### 6.4 元素定位失败

**症状**: LLM 返回的 action 执行失败

**可能原因**:
- 页面结构变化
- 元素加载延迟
- ref 引用过期

**排查**:
```bash
# 查看详细日志
tail -f ~/.ami/logs/app.log | grep -i eigent
```

---

## 7. 日志位置

| 日志类型 | 路径 |
|----------|------|
| 系统日志 | `~/.ami/logs/app.log` |
| 错误日志 | `~/.ami/logs/error.log` |

### 日志关键词

```bash
# 查看 EigentBrowserAgent 相关日志
grep -i "eigent" ~/.ami/logs/app.log

# 查看 Quick Task 服务日志
grep -i "quick.task" ~/.ami/logs/app.log

# 查看 LLM 调用日志
grep -i "llm" ~/.ami/logs/app.log
```

---

## 8. 架构说明

```
┌─────────────────────────────────────────────────────────┐
│                   Quick Task System                      │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Frontend (QuickTaskPage.jsx)                           │
│  └── 任务输入 → WebSocket 实时更新 → 结果展示            │
│                                                          │
│  API Router (routers/quick_task.py)                     │
│  └── POST /execute → GET /status → WebSocket /ws        │
│                                                          │
│  Service (services/quick_task_service.py)               │
│  └── 任务状态管理 → 异步执行 → 进度推送                   │
│                                                          │
│  Agent (agents/eigent_browser_agent.py)                 │
│  └── ReAct Loop: Snapshot → LLM → Action → Repeat       │
│                                                          │
│  Tools (tools/eigent_browser/)                          │
│  ├── page_snapshot.py    # DOM → 文本快照                │
│  ├── action_executor.py  # 执行浏览器动作                │
│  └── browser_session.py  # 浏览器会话管理                │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## 9. 后续开发

参考 `docs/roadmap/react-agent-integration.md` 了解:
- Phase 2: Memory 生成 Plan
- Phase 3: Memory 纠错能力
- Phase 4: Workflow 协作
