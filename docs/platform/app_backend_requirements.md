# App Backend 需求文档

**版本**: v3.0
**日期**: 2025-11-08
**状态**: Draft
**策略**: Desktop App Only (Tauri IPC + CDP Recording)

---

## 1. 概述

### 1.1 产品定位

App Backend 是 Python 库（非 HTTP 服务），为 Desktop App (Tauri) 提供：
- CDP 录制能力（无需浏览器插件）
- Workflow 生成和执行能力
- 本地存储管理
- Cloud Backend API 代理

### 1.2 架构模式

```
Desktop App Frontend (React/Vue)
   ↓ invoke() - Tauri IPC
Desktop App Rust Backend (Tauri Commands)
   ↓ stdin/stdout (JSON-RPC)
App Backend (Python daemon process)
   ├── Global Browser Session (persistent)
   └── Background Tasks (async execution)
   ↓ CDP Binding
Browser (behavior_tracker.js)
```

**开发阶段设计（MVP）**：
- Python CLI 作为**常驻进程**运行
- Rust 通过 stdin/stdout 与 Python 进程通信（JSON-RPC）
- 全局浏览器会话在 Python 进程中持久化
- 异步任务在 Python 进程后台运行
- 开发环境优先，暂不考虑打包发布

### 1.3 核心价值

- **轻量级**: 无需启动 HTTP 服务器
- **原生集成**: Tauri IPC 类型安全
- **代码复用**: 基于已验证的 base_app 和 monitor.py
- **隐私优先**: Workflow 执行在本地

---

## 2. 功能需求

### 2.1 CDP 录制功能

#### 2.1.1 启动录制

**函数签名**:
```python
async def start_recording(url: str) -> Dict[str, Any]
```

**输入**:
- `url`: 起始 URL

**输出**:
```json
{
  "session_id": "session_20251108_120000",
  "status": "recording"
}
```

**功能描述**:
1. 启动 Playwright CDP 浏览器
2. 设置 CDP Binding (`window.reportUserBehavior`)
3. 注入 behavior_tracker.js
4. 导航到起始 URL

**复用代码**:
- `base_app/tools/browser_use/user_behavior/monitor.py` - SimpleUserBehaviorMonitor

#### 2.1.2 停止录制

**函数签名**:
```python
async def stop_recording(session_id: str) -> Dict[str, Any]
```

**输出**:
```json
{
  "session_id": "session_20251108_120000",
  "operations_count": 42,
  "local_file_path": "~/.ami/recordings/.../operations.json"
}
```

**功能描述**:
1. 停止监控
2. **保持浏览器打开**（不关闭，供后续任务复用）
3. 保存 operations.json 到本地

#### 2.1.3 捕获操作

**实现方式**: CDP Binding（自动，无需显式调用）

**数据流**:
```
behavior_tracker.js (页面内)
   ↓ window.reportUserBehavior(JSON.stringify({...}))
CDP Binding
   ↓ handle_runtime_binding(event)
Python
   ↓ operations.append(operation)
```

**支持的操作类型**:
- click, input, select, scroll, navigate, newtab, hover, keydown

---

### 2.2 Workflow 生成功能

#### 2.2.1 生成 Workflow

**函数签名**:
```python
async def generate_workflow(
    recording_id: str,
    title: str,
    description: str
) -> Dict[str, Any]
```

**输入**:
- `recording_id`: 录制 ID（或本地 session_id）
- `title`: Workflow 标题
- `description`: 用户意图描述

**输出**:
```json
{
  "workflow_name": "从-allegro-抓取咖啡产品",
  "local_path": "~/.ami/users/.../workflows/.../workflow.yaml"
}
```

**处理流程** (完整流程参考 architecture.md):
1. 读取本地 operations.json
2. 上传录制数据到 Cloud Backend (`/api/recordings/upload`) → recording_id
3. 调用 MetaFlow 生成接口 (`/api/recordings/{recording_id}/generate-metaflow`) → metaflow
   - Intent Extraction (Cloud Backend 调用 LLM)
   - Intent Graph 更新
   - MetaFlow 生成 (Cloud Backend 调用 LLM)
4. 调用 Workflow 生成接口 (`/api/metaflows/{metaflow_id}/generate-workflow`) → workflow_name
   - Workflow YAML 生成 (Cloud Backend 调用 LLM)
5. 下载 workflow.yaml 到本地
6. 保存到 `~/.ami/users/{user_id}/workflows/{name}/`

**备注**:
- MetaFlow 生成和 Workflow 生成是两个独立的 Cloud Backend 接口
- 调用方式灵活，可根据现有代码和架构选择最方便的实现（同步等待、轮询、回调等）

---

### 2.3 Workflow 执行功能

#### 2.3.1 执行 Workflow

**函数签名**:
```python
async def execute_workflow(workflow_name: str) -> Dict[str, Any]
```

**输出**:
```json
{
  "task_id": "task_20251108_120000",
  "status": "running"
}
```

**处理流程**:
1. 加载本地 workflow.yaml
2. 创建 BaseAgent 实例（复用 base_app）
3. 异步执行 workflow（不阻塞）

**复用代码**:
- `base_app/base_agent/core/base_agent.py` - BaseAgent
- `base_app/tools/browser_session_manager.py` - BrowserSessionManager

#### 2.3.2 查询执行状态

**函数签名**:
```python
def get_workflow_status(task_id: str) -> Dict[str, Any]
```

**输出**:
```json
{
  "task_id": "task_xxx",
  "status": "running",
  "progress": 50,
  "current_step": "step_2_search"
}
```

**调用方式**: Desktop App Frontend 每 2 秒轮询查询

#### 2.3.3 获取执行结果

**函数签名**:
```python
def get_workflow_result(task_id: str) -> Dict[str, Any]
```

**输出**:
```json
{
  "status": "success",
  "final_output": {...},
  "logs": [...],
  "screenshots": [...]
}
```

---

### 2.4 辅助功能

#### 2.4.1 列出 Workflows

**函数签名**:
```python
def list_workflows(user_id: str = "default") -> List[Dict[str, str]]
```

**输出**:
```json
{
  "workflows": [
    {"name": "workflow1", "created_at": "2025-11-08 12:00:00"},
    {"name": "workflow2", "created_at": "2025-11-07 10:00:00"}
  ]
}
```

---

## 3. 非功能需求

### 3.1 性能要求

- CDP 浏览器启动时间 < 5秒（仅首次启动）
- 操作捕获延迟 < 100ms（CDP Binding 同步）
- Python 函数调用响应 < 200ms（非执行类）
- 浏览器会话复用：所有任务共享同一个全局浏览器实例，避免重复启动

### 3.2 可靠性要求

- CDP Binding 数据传输无丢失
- 录制文件完整性保证
- 执行失败提供详细错误信息

### 3.3 安全性要求

- 录制数据仅保存在用户本地 `~/.ami/`
- 不对外暴露任何网络端口

---

## 4. 约束条件

### 4.1 技术约束

- Python 3.9+
- 作为常驻进程运行（daemon mode）
- 通过 stdin/stdout 与 Rust 进程通信（JSON-RPC）
- 维护全局浏览器会话和异步任务状态
- 复用 base_app/BaseAgent
- 复用 monitor.py 的 CDP Binding 逻辑

### 4.2 MVP 范围限制

- **假设单一执行**: 同时只运行一个 workflow
- **假设单一录制**: 同时只有一个录制 session
- **轮询查询**: 执行进度用轮询（每 2 秒），无需 WebSocket
- **简化错误处理**: 暂不考虑错误情况，不实现自动重试、断点续传
- **浏览器管理**: 使用全局单一浏览器实例，录制和执行都复用该实例，App Backend 关闭时才关闭浏览器
- **开发环境优先**: 暂不考虑打包发布、路径问题，专注内部测试
- **Cloud API 假设**: 所有 Cloud Backend API 均为同步接口，无超时限制

---

## 5. 数据模型

### 5.1 录制数据 (operations.json)

```json
{
  "session_id": "session_20251108_120000",
  "timestamp": "2025-11-08T12:00:00",
  "operations": [
    {
      "type": "click",
      "timestamp": "2025-11-08 12:00:05",
      "url": "https://example.com",
      "page_title": "Example",
      "element": {
        "xpath": "//*[@id='button']",
        "text": "Submit",
        "tag_name": "button"
      }
    }
  ]
}
```

### 5.2 执行结果 (result.json)

```json
{
  "task_id": "task_20251108_120000",
  "status": "success",
  "start_time": "2025-11-08T12:00:00",
  "end_time": "2025-11-08T12:05:00",
  "duration": 300,
  "final_output": {...},
  "logs": [...],
  "screenshots": [...]
}
```

---

## 6. 存储结构

```
~/.ami/
├── users/{user_id}/
│   ├── workflows/              # Workflow YAML 缓存
│   │   └── {workflow_name}/
│   │       ├── workflow.yaml
│   │       └── executions/
│   │           └── {task_id}/
│   │               ├── result.json
│   │               └── screenshots/
│   ├── recordings/             # 临时录制数据
│   │   └── {session_id}/
│   │       └── operations.json
│   └── cache/
└── logs/
    └── app-backend.log
```

---

## 7. 接口清单

| 函数 | 用途 | 调用方式 |
|------|------|----------|
| `start_recording(url)` | 启动 CDP 录制 | Rust invoke → Python |
| `stop_recording(session_id)` | 停止录制 | Rust invoke → Python |
| `generate_workflow(recording_id, title, description)` | 生成 workflow | Rust invoke → Python |
| `execute_workflow(workflow_name)` | 执行 workflow | Rust invoke → Python |
| `get_workflow_status(task_id)` | 查询执行状态 | Rust invoke → Python (轮询) |
| `get_workflow_result(task_id)` | 获取执行结果 | Rust invoke → Python |
| `list_workflows()` | 列出所有 workflows | Rust invoke → Python |

---

## 8. 验收标准

### 8.1 MVP 验收

- [ ] CDP 录制功能可用（启动、捕获、停止）
- [ ] 成功上传录制并生成 Workflow
- [ ] 成功执行本地 Workflow 并获取结果
- [ ] Tauri IPC 调用 Python 函数正常工作
- [ ] 轮询查询执行状态正常

### 8.2 测试用例

**测试用例 1: 完整录制流程**
1. 调用 `start_recording(url)` → 返回 session_id
2. 在浏览器中操作
3. 调用 `stop_recording(session_id)` → 生成 operations.json
4. 验证文件内容

**测试用例 2: Workflow 生成和执行**
1. 调用 `generate_workflow(...)` → 生成 workflow
2. 调用 `execute_workflow(...)` → 获得 task_id
3. 轮询 `get_workflow_status(task_id)` → 直到完成
4. 调用 `get_workflow_result(task_id)` → 验证结果

---

## 9. 未来扩展 (非 MVP)

- 支持并发 workflow 执行
- 支持多用户隔离
- WebSocket 实时进度推送（替代轮询）
- 录制断点续传
- 执行失败自动重试

---

**文档版本**: v3.0 (Tauri IPC)
**最后更新**: 2025-11-08
**审核状态**: Draft
**下一步**: 编写设计文档 `app_backend_design.md`
