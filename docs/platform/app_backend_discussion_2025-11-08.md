# App Backend 设计讨论记录

**日期**: 2025-11-08
**参与者**: User, Claude
**目的**: 确定 App Backend 的功能范围和技术方案
**版本**: v3.0 - Desktop App Only (CDP Recording)

---

## 讨论背景

根据 v3.0 重构计划，App Backend 作为运行在用户电脑上的执行引擎和云端代理。

**v3.0 核心变更**：
- ❌ 不再依赖 Chrome Extension
- ✅ 使用 CDP (Chrome DevTools Protocol) 注入脚本录制
- ✅ Desktop App (Tauri) 作为唯一客户端
- ✅ 复用现有代码：behavior_tracker.js、base_app

参考文档：
- `docs/platform/refactoring_plan_2025-11-07.md` (v3.0)
- `docs/platform/architecture.md`
- `docs/platform/components_overview.md`
- `docs/platform/flow_analysis.md`

---

## 核心功能确认

### 1. App Backend 的定位 (v3.0)

**角色**: 运行在用户电脑上的**执行引擎**和**云端代理**

**四大核心功能模块**:
1. **CDP 录制控制** (CDP Recording Controller) - **v3.0 新增**
2. **执行控制** (Execution Controller)
3. **云端代理** (Cloud Client)
4. **本地存储管理** (Storage Manager)

**v3.0 技术栈**:
- CDP 录制：Playwright + CDP + behavior_tracker.js (复用)
- 执行引擎：base_app/BaseAgent (复用)
- 浏览器管理：base_app/BrowserSessionManager (复用)

---

## 关键问题讨论

### 问题 1: 上传和生成的同步/异步机制

**Claude 最初理解**:
- 上传后同步等待 30-60 秒生成 workflow
- 可能需要异步轮询方案

**User 澄清**: ✅
- **上传 (学习)** 和 **生成 (workflow)** 是**两个独立接口**
- 上传后 Cloud Backend 异步学习 (Intent 提取、Intent Graph 更新)
- 用户主动点击"生成 Workflow"时调用生成接口
- **MVP 阶段不考虑学习状态检查**（假设学习很快）

**最终方案 (v3.0 CDP)**:
```
阶段 1: 录制和学习 (CDP 注入脚本)
  Desktop App: 用户点击"开始录制" + 输入 URL
  ↓
  Desktop App → App Backend: POST /api/recording/start
  ↓
  App Backend (cdp_recorder.py):
    1. 使用 Playwright 启动 CDP 浏览器
    2. 注入 behavior_tracker.js (复用 chrome-extension 代码)
    3. 返回 session_id
  ↓
  用户在 CDP 浏览器中操作
  ↓
  behavior_tracker.js 捕获操作 → HTTP POST /api/recording/operation
  ↓
  App Backend: 存储到内存/临时文件
  ↓
  用户点击"停止录制"
  ↓
  App Backend:
    1. 关闭 CDP 浏览器
    2. 生成本地文件 operations.json (只包含操作)
    3. POST /api/recordings/upload 到 Cloud Backend
  ↓
  Cloud Backend: 保存 + 异步学习（Intent 提取、Intent Graph 更新）
  返回: recording_id

阶段 2: 生成 Workflow（用户描述意图）
  Desktop App: 用户填写表单
    - title: "从 Allegro 抓取咖啡产品"
    - description: "搜索咖啡，筛选价格低于100的产品，导出前50个"
  ↓
  Desktop App → App Backend: POST /api/recordings/{recording_id}/generate
  Body: { recording_id, title, description }
  ↓
  App Backend → Cloud Backend: 转发请求
  ↓
  Cloud Backend:
    - 结合 recording operations + 用户描述
    - 生成 MetaFlow + Workflow YAML
  返回: workflow_name (基于 title)
  ↓
  App Backend: 下载 workflow.yaml 到本地 ~/.ami/users/{user_id}/workflows/
```

**关键点**:
- 录制时不需要 title/description（只捕获操作）
- 生成时需要 title/description（用户描述意图）
- title/description 帮助 LLM 理解用户真正想做什么

**可选改进 (非 MVP)**:
- 添加 `GET /api/recordings/{recording_id}/status` 检查学习状态
- 如果正在学习，返回等待提示

---

### 问题 2: 浏览器会话并发策略

**Claude 提问**:
- 如果用户同时执行多个 workflow 怎么办？
- 方案 A: 串行执行 (排队)
- 方案 B: 允许独立浏览器会话

**User 决策**: ✅
- **假设用户同时只运行一个 workflow**
- 使用全局单例浏览器会话
- MVP 不处理并发队列

**技术实现**:
```python
# 全局浏览器管理器
browser_manager = BrowserManager()
await browser_manager.init_global_session()

# 所有 workflow 强制使用 "global" 会话
workflow.name = "global"
```

---

### 问题 3: 配置系统设计

**Claude 提议**:
- 创建 `app-backend.yaml` 配置文件
- 参考 Cloud Backend 的 ConfigService

**User 确认**: ✅ 需要配置系统

**配置文件结构**:
```yaml
server:
  host: 0.0.0.0
  port: 8000

storage:
  base_path: ~/.ami  # macOS/Linux

browser:
  headless: false
  timeout: 30

cloud:
  api_url: https://api.ami.com
  timeout: 120

logging:
  level: INFO
```

**实现**:
- 创建 `src/app_backend/core/config_service.py`
- 支持环境变量覆盖
- 支持点号路径访问 (如 `config.get("server.port")`)

---

### 问题 4: WebSocket vs HTTP 轮询

**Claude 提议**:
- 方案 A: WebSocket (实时推送)
- 方案 B: HTTP 轮询 (MVP 简化)

**User 决策**: ✅ **直接使用 WebSocket**

**v3.0 通信方式 (Tauri IPC + CDP Binding)**:

**核心决策**：
- ❌ 不使用 HTTP 服务器（之前为了对接 Extension 才用 HTTP）
- ✅ Desktop App Frontend ↔ Rust Backend: **Tauri IPC** (invoke)
- ✅ Rust Backend ↔ Python App Backend: **Python 函数调用** (PyO3 或 subprocess)
- ✅ behavior_tracker.js → Python: **CDP Binding** (复用 monitor.py，无需额外通信)

**通信架构**:
```
Frontend (React/Vue)
   ↓ invoke('start_recording')
Rust Backend (Tauri Commands)
   ↓ 调用 Python 函数
Python App Backend (cdp_recorder.py, workflow_executor.py)
   ↓ CDP Binding
behavior_tracker.js (注入到浏览器页面)
```

**优势**:
- ✅ 无需启动 HTTP 服务器（更轻量）
- ✅ Tauri IPC 原生支持（类型安全）
- ✅ CDP Binding 复用已验证代码（monitor.py）
- ✅ 执行进度用轮询（简化实现，无需 WebSocket）

---

### 问题 5: MVP 错误处理级别

**Claude 提议**:
- 必须处理: Cloud Backend 不可用、Token 过期、资源不存在
- 暂不处理: 网络重试、队列持久化、自动重试

**User 确认**: ✅ 同意简化方案

**错误处理策略**:

**必须处理**:
- ✅ Cloud Backend 不可用 → 返回 503 + 友好提示
- ✅ Token 无效/过期 → 返回 401 + 重新登录提示
- ✅ Workflow 不存在 → 返回 404

**暂不处理 (非 MVP)**:
- ❌ 录制中网络中断的操作重传
- ❌ 执行失败自动重试
- ❌ 操作队列持久化

---

## 技术方案总结

### 架构组件 (v3.0 简化)

**App Backend** (Python 库，非 HTTP 服务):
- `cdp_recorder.py` - CDP 录制（核心模块，复用 monitor.py）
- `storage_manager.py` - 本地文件管理
- `cloud_client.py` - Cloud API 调用
- `workflow_executor.py` - Workflow 执行（调用 base_app）

**Desktop App** (Tauri):
- Frontend: React/Vue
- Rust Backend: Tauri Commands (调用 Python 函数)

**代码复用**:
- CDP 录制 → 复用 `monitor.py`
- behavior_tracker.js → 复用 `chrome-extension/public/behavior_tracker.js`
- Workflow 执行 → 调用 `base_app/BaseAgent`

### 存储结构

```
~/.ami/
├── users/{user_id}/
│   ├── workflows/              # Workflow YAML 缓存
│   │   └── {workflow_name}/
│   │       ├── workflow.yaml
│   │       └── executions/{execution_id}/result.json
│   ├── recordings/             # 临时录制数据
│   │   └── {session_id}/operations.json
│   └── cache/
└── logs/
    └── app-backend.log
```

### 接口设计 (v3.0 简化)

**核心接口**:
- `start_recording(url)` - 启动 CDP 录制
- `stop_recording(session_id)` - 停止录制
- `generate_workflow(recording_id, title, description)` - 生成 workflow
- `execute_workflow(workflow_name)` - 执行 workflow
- `get_workflow_status(task_id)` - 查询执行状态
- `list_workflows()` - 列出所有 workflows

详细接口设计见 `app_backend_design.md`

---

## 实施计划 (v3.0)

### Phase 1: CDP 录制核心
- [ ] `services/cdp_recorder.py` - **核心模块**
  - [ ] 复用 `base_app/tools/browser_use/user_behavior/monitor.py` 的 CDP Binding 逻辑
  - [ ] `start_recording(url)` - 启动 CDP 浏览器 + 注入 behavior_tracker.js
  - [ ] `stop_recording()` - 关闭浏览器 + 生成 operations.json
  - [ ] `get_operations()` - 获取当前录制的操作列表
- [ ] 复制 `chrome-extension/public/behavior_tracker.js` 到 `static/recorder.js`
  - [ ] 适配脚本（确保使用 CDP Binding 而非 postMessage）

### Phase 2: 配置系统
- [ ] `core/config_service.py` - 配置管理
- [ ] `config/app-backend.yaml` - 配置文件

### Phase 3: 核心服务
- [ ] `services/storage_manager.py` - 本地文件管理
- [ ] `services/cloud_client.py` - Cloud API 调用
- [ ] `services/browser_manager.py` - 复用 `base_app/tools/browser_session_manager.py`
- [ ] `services/workflow_executor.py` - 复用 `base_app/base_agent/core/base_agent.py`

### Phase 4: API 控制器
- [ ] `controllers/recording_controller.py` - CDP 录制 API (HTTP)
- [ ] `controllers/execution_controller.py` - 执行 API (HTTP)
- [ ] (可选) WebSocket 端点实现 - 执行进度推送

### Phase 5: 测试
- [ ] 单元测试 - CDP 录制、存储、Cloud API 调用
- [ ] 本地联调 (App Backend + Cloud Backend)
- [ ] 完整流程测试 (CDP 录制→上传→生成→下载→执行)

---

## 关键设计原则 (v3.0)

1. **本地优先**: 执行在本地，保护隐私，降低成本
2. **云端智能**: AI 分析在云端，利用强大算力
3. **职责分离**: 执行和分析清晰分离
4. **单一执行**: MVP 假设用户同时只运行一个 workflow
5. **CDP Binding 通信**: 复用已验证的 CDP Binding 机制，无需额外 WebSocket
6. **代码复用**: 直接复用 base_app 和 behavior_tracker.js，避免重复开发
7. **简化错误处理**: MVP 关注核心场景，避免过度设计

---

## 后续优化方向 (非 MVP)

1. **并发执行**: 支持多个 workflow 同时运行
2. **学习状态检查**: 生成前检查 Intent 提取是否完成
3. **断点续传**: 录制中断可恢复
4. **自动重试**: 执行失败自动重试
5. **离线模式**: Cloud Backend 不可用时的降级方案

---

## 决策记录

| 问题 | 决策 | 理由 |
|------|------|------|
| 上传和生成是否同步 | 分离为两个独立接口 | 学习需要时间，用户主动控制生成 |
| 浏览器并发策略 | 假设单一执行 | MVP 简化，降低复杂度 |
| 是否需要配置系统 | 需要 | 统一管理路径、Cloud API 地址等 |
| **通信方式 (v3.0)** | **Tauri IPC + CDP Binding** | 不需要 HTTP 服务器，更轻量 |
| 录制数据传输 (v3.0) | **CDP Binding** | 复用已验证的 monitor.py，无需额外通信 |
| 执行进度查询 (v3.0) | **轮询** (invoke 查询) | MVP 简化，无需 WebSocket |
| Rust ↔ Python 调用方式 | PyO3 或 subprocess | 根据实际情况选择 |
| 错误处理级别 | 处理核心错误，暂不重试 | MVP 聚焦核心功能 |

---

**v3.0 更新完成** ✅

本文档已更新为 v3.0 Desktop App Only + Tauri IPC 策略：
- ✅ 使用 Tauri IPC（不再使用 HTTP 服务器）
- ✅ Rust Backend 通过 PyO3 或 subprocess 调用 Python
- ✅ CDP 注入脚本录制（复用 monitor.py + behavior_tracker.js）
- ✅ App Backend 作为 Python 库（非 HTTP 服务）
- ✅ 执行进度用轮询（简化实现）

**下一步**:
1. 更新需求文档 `app_backend_requirements.md` (Python 库接口)
2. 更新设计文档 `app_backend_design.md` (详细接口设计)
