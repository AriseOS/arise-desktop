# Eigent 功能迁移实现计划

## 一、功能缺失清单

### P0 - 核心功能 (必须实现)

| ID | 功能 | 描述 | 涉及文件 | 工作量 |
|----|------|------|----------|--------|
| P0-1 | TaskState 组件 | 任务状态过滤器 (all/done/ongoing/pending/failed/reassigned) | 新建 `TaskState.jsx` | 中 |
| P0-2 | StreamingTaskList | 流式任务分解显示，解析 `<task>` XML | 新建 `StreamingTaskList.jsx` | 中 |
| P0-3 | TaskCard 增强 | 状态过滤、编辑、删除、重分配显示 | 修改 `TaskCard.jsx` | 大 |
| P0-4 | 全局状态管理 | Zustand chatStore + projectStore | 新建 `store/` 目录 | 大 |
| P0-5 | 多轮会话支持 | 自动创建新 chatStore，保留历史 | 修改 AgentPage + store | 大 |

### P1 - 重要功能 (应该实现)

| ID | 功能 | 描述 | 涉及文件 | 工作量 |
|----|------|------|----------|--------|
| P1-1 | Agent 节点增强 | 工具列表、Webview 截图、Toolkit 日志详情 | 修改 `AgentNode.jsx` | 大 |
| P1-2 | WorkFlow 可视化 | React Flow 多 Agent 图形化 | 新建 `WorkFlow/` | 大 |
| P1-3 | BottomBox 状态机 | input/splitting/confirm/running/finished | 新建 `BottomBox.jsx` | 中 |
| P1-4 | 文件附件功能 | 文件选择器 + 附件显示 | 修改 ChatBox | 中 |
| P1-5 | 任务回放功能 | replay API + UI | 修改 AgentPage | 中 |
| P1-6 | 暂停/恢复功能 | pause/resume API + UI | 修改 AgentPage | 小 |

### P2 - 增强功能 (可选实现)

| ID | 功能 | 描述 | 涉及文件 | 工作量 |
|----|------|------|----------|--------|
| P2-1 | IntegrationList | 云服务集成 (OAuth, 环境变量) | 新建 `IntegrationList/` | 大 |
| P2-2 | 任务队列管理 | queuedMessages 排队任务 | 修改 store + UI | 中 |
| P2-3 | Completion Report | 任务完成报告显示 | 修改 AgentNode | 小 |
| P2-4 | 编辑查询功能 | 编辑已提交的查询重新执行 | 修改 ChatBox | 小 |
| P2-5 | 上下文超长提示 | context_too_long 处理 | 修改 SSE 处理 | 小 |
| P2-6 | 预算不足提示 | budget_not_enough 处理 | 修改 SSE 处理 | 小 |

---

## 二、执行计划

### Phase 1: 基础组件 (P0-1, P0-2, P0-3)

**目标**: 完成任务分解和状态显示的核心 UI 组件

#### Step 1.1: TaskState 组件
```
文件: src/components/TaskState/TaskState.jsx
功能:
- 6种状态类型: all, done, reassigned, ongoing, pending, failed
- 可点击切换选中状态
- 显示各状态计数
- 支持 forceVisible 强制显示
```

#### Step 1.2: StreamingTaskList 组件
```
文件: src/components/TaskBox/StreamingTaskList.jsx
功能:
- 解析 <task>content</task> XML 格式
- 显示加载骨架屏
- 不完整任务光标动画
- 任务计数显示
```

#### Step 1.3: TaskCard 增强
```
文件: src/components/TaskBox/TaskCard.jsx
修改:
- 集成 TaskState 组件
- 添加 taskType 支持 (1: 手动, 2: agent分配)
- 添加 onAddTask, onUpdateTask, onDeleteTask
- 显示 reAssignTo 重分配
- 显示 failure_count 重试计数
- 展开/折叠动画
```

### Phase 2: 状态管理 (P0-4, P0-5)

**目标**: 实现 Zustand 全局状态管理

#### Step 2.1: chatStore
```
文件: src/store/chatStore.js
功能:
- Task 生命周期管理
- messages, taskInfo, taskRunning, taskAssigning
- SSE 连接管理 (AbortController)
- 30秒自动确认计时器
- streamingDecomposeText 流式文本
```

#### Step 2.2: projectStore
```
文件: src/store/projectStore.js
功能:
- 多 chatStore 管理
- activeProjectId, activeChatStoreId
- queuedMessages 任务队列
- history 历史记录
```

#### Step 2.3: useChatStoreAdapter Hook
```
文件: src/hooks/useChatStoreAdapter.js
功能:
- 桥接 vanilla Zustand store 和 React 组件
- 订阅 store 变化
- 返回响应式状态
```

### Phase 3: Agent 可视化增强 (P1-1, P1-2)

**目标**: 完善 Agent 节点和 WorkFlow 可视化

#### Step 3.1: AgentNode 增强
```
文件: src/components/AgentNode/AgentNode.jsx
修改:
- 添加 tools 工具列表显示
- 添加 Webview 截图预览 (img 数组)
- 添加 Toolkit 执行日志详情面板
- 添加 Completion Report 显示
- 集成 TaskState 组件
```

#### Step 3.2: WorkFlow React Flow
```
文件: src/components/WorkFlow/WorkFlow.jsx
功能:
- React Flow 集成
- 5种 Agent 节点类型
- 视口左右导航
- 编辑模式 (拖拽)
- NodeResizer 调整大小
```

### Phase 4: 交互增强 (P1-3, P1-4, P1-5, P1-6)

**目标**: 完善用户交互功能

#### Step 4.1: BottomBox 状态机
```
文件: src/components/ChatBox/BottomBox.jsx
功能:
- 5种状态: input, splitting, confirm, running, finished
- 根据状态显示不同 UI
- 任务队列显示
```

#### Step 4.2: 文件附件
```
修改: src/components/ChatBox/ChatBox.jsx
功能:
- 文件选择器 (electron IPC)
- 附件预览
- 发送时携带附件
```

#### Step 4.3: 任务回放
```
修改: src/pages/AgentPage.jsx
功能:
- handleReplay 函数
- /api/chat/steps/playback/{taskId} API
- delay_time 参数
```

#### Step 4.4: 暂停/恢复
```
修改: src/pages/AgentPage.jsx
功能:
- handlePauseResume 函数
- /task/{projectId}/take-control API
- elapsed 时间计算
```

### Phase 5: 集成功能 (P2-1 ~ P2-6)

**目标**: 云服务集成和边缘功能

#### Step 5.1: IntegrationList
```
文件: src/components/IntegrationList/IntegrationList.jsx
功能:
- select/manage 两种模式
- OAuth 流程 (Google Calendar)
- MCPEnvDialog 环境变量配置
- 安装/卸载状态
```

#### Step 5.2: 其他增强
- 任务队列管理 UI
- 编辑查询功能
- context_too_long 处理
- budget_not_enough 处理

---

## 三、依赖关系

```
Phase 1 (基础组件)
    │
    ├── TaskState ──────────────────┐
    │                               │
    ├── StreamingTaskList           │
    │                               ▼
    └── TaskCard ──────────────► Phase 3 (Agent 可视化)
                                    │
Phase 2 (状态管理)                   │
    │                               │
    ├── chatStore ◄─────────────────┤
    │       │                       │
    ├── projectStore                │
    │       │                       │
    └── useChatStoreAdapter ────────┘
                │
                ▼
        Phase 4 (交互增强)
                │
                ▼
        Phase 5 (集成功能)
```

---

## 四、文件结构规划

```
src/clients/desktop_app/src/
├── components/
│   ├── TaskState/
│   │   ├── TaskState.jsx       # P0-1
│   │   └── index.js
│   ├── TaskBox/
│   │   ├── TaskCard.jsx        # P0-3 (修改)
│   │   ├── StreamingTaskList.jsx # P0-2
│   │   ├── TaskItem.jsx        # 新建
│   │   └── index.js
│   ├── AgentNode/
│   │   ├── AgentNode.jsx       # P1-1 (修改)
│   │   ├── AgentsPanel.jsx
│   │   └── index.js
│   ├── WorkFlow/
│   │   ├── WorkFlow.jsx        # P1-2
│   │   ├── WorkFlowNode.jsx
│   │   └── index.js
│   ├── ChatBox/
│   │   ├── ChatBox.jsx         # (修改)
│   │   ├── BottomBox.jsx       # P1-3
│   │   └── index.js
│   └── IntegrationList/
│       ├── IntegrationList.jsx # P2-1
│       ├── MCPEnvDialog.jsx
│       └── index.js
├── store/
│   ├── chatStore.js            # P0-4
│   ├── projectStore.js         # P0-4
│   └── index.js
├── hooks/
│   ├── useChatStoreAdapter.js  # P0-4
│   └── useIntegrationManagement.js
└── pages/
    └── AgentPage.jsx           # (修改)
```

---

## 五、验收标准

### Phase 1 验收
- [ ] TaskState 组件可点击切换状态
- [ ] StreamingTaskList 正确解析流式 XML
- [ ] TaskCard 显示状态过滤器和重分配信息

### Phase 2 验收
- [ ] chatStore 管理完整任务生命周期
- [ ] projectStore 支持多会话切换
- [ ] 页面刷新后状态恢复

### Phase 3 验收
- [ ] AgentNode 显示工具列表和执行日志
- [ ] WorkFlow 可拖拽调整节点位置
- [ ] Webview 截图正确显示

### Phase 4 验收
- [ ] BottomBox 正确切换 5 种状态
- [ ] 文件附件可选择和预览
- [ ] 任务回放功能正常

### Phase 5 验收
- [ ] IntegrationList OAuth 流程正常
- [ ] 任务队列可添加删除
- [ ] 上下文超长时禁用输入

---

## 六、风险和注意事项

1. **状态管理迁移**: 从 local hooks 迁移到 Zustand 需要逐步进行，避免一次性重构
2. **SSE 事件兼容**: 需要同时支持 2ami 和 Eigent 两种事件命名
3. **Electron IPC**: 文件选择器等功能依赖 Electron API
4. **React Flow 性能**: 大量节点时需要注意性能优化
5. **后端 API**: 部分功能需要后端 API 支持 (replay, pause/resume)
