# ChatBox Task Integration Plan

## 目标

将 Eigent 的任务展示能力完整移植到 AMI 的 ChatBox 中，实现：
1. 任务分解的 inline 展示（TaskCard in ChatBox）
2. BottomBox 状态机的完整连接
3. 30秒自动确认流程的 UI 展示
4. 任务执行进度的实时显示

---

## 一、当前状态分析

### Eigent 的设计

```
ChatBox
├── MessageList
│   └── UserQueryGroup (per user query)
│       ├── UserMessageCard
│       ├── TaskCard [STICKY] ← 任务卡片，inline 显示
│       └── AgentMessageCard
└── BottomBox (状态机: input→splitting→confirm→running→finished)
    ├── BoxHeaderConfirm (确认状态时显示)
    ├── InputBox (输入状态)
    └── BoxAction (运行/完成状态)
```

**关键特点：**
- TaskCard 在消息流中 inline 显示，不是 Modal
- BottomBox 有完整状态机控制输入/确认/运行等状态
- 30秒自动确认在 chatStore 中实现，UI 显示确认按钮

### AMI 当前状态

```
AgentPage
├── ChatBox (只传了 messages, notices)
│   ├── MessageList ← 只显示消息，无 TaskCard
│   └── BottomBox ← 未连接状态机
├── WorkspaceTabs (右侧面板)
└── TaskDecomposition ← Modal 方式，但未触发
```

**问题：**
1. ChatBox 缺少 `task` prop，无法获取任务状态
2. BottomBox 状态机未连接到 agentStore
3. MessageList 中没有 TaskCard
4. TaskDecomposition 是 Modal，设计与 Eigent 不同

---

## 二、设计方案

### 方案选择

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A. 完全复刻 Eigent | TaskCard inline 在 ChatBox | 与 Eigent 一致 | 改动大 |
| B. 保留 Modal + 增强 ChatBox | TaskDecomposition Modal + ChatBox 进度 | 改动小 | 与 Eigent 不同 |
| **C. 混合方案（推荐）** | TaskCard inline + Modal 作为备选 | 灵活，可渐进 | 需要两套 UI |

**选择方案 C**：
- 主要展示：TaskCard inline 在 ChatBox 中（与 Eigent 一致）
- Modal 作为可选的详细编辑界面

### 架构设计

```
AgentPage
├── ChatBox
│   ├── MessageList
│   │   ├── MessageItem (user/agent messages)
│   │   └── TaskCard [NEW] ← inline 任务卡片
│   │       ├── StreamingTaskList (分解中)
│   │       ├── TaskItem (子任务列表)
│   │       └── TaskState (状态筛选)
│   └── BottomBox [ENHANCED]
│       ├── BoxHeaderConfirm (确认状态)
│       ├── BoxHeaderSplitting (分解中状态)
│       ├── InputBox (输入状态)
│       └── BoxAction (运行/完成状态)
├── WorkspaceTabs (右侧 - 执行详情)
└── TaskDecomposition (Modal - 可选详细编辑)
```

---

## 三、数据流设计

### 状态流转

```
用户输入任务
    ↓
BottomBox state: 'input' → 'splitting'
    ↓
后端发送 task_decomposed 事件
    ↓
agentStore 更新: subtasks, showDecomposition: true
    ↓
BottomBox state: 'splitting' → 'confirm'
TaskCard 显示子任务列表
    ↓
30秒自动确认 OR 用户点击确认
    ↓
BottomBox state: 'confirm' → 'running'
    ↓
后端发送 subtask_state 事件
    ↓
TaskCard 更新子任务状态
    ↓
任务完成
    ↓
BottomBox state: 'running' → 'finished'
```

### Props 传递

```jsx
// AgentPage.jsx
<ChatBox
  messages={messages}
  notices={notices}
  // 新增 props
  task={{
    taskInfo: subtasks,
    taskRunning: taskRunning,
    status: status,
    streamingDecomposeText: streamingDecomposeText,
    summaryTask: summaryTask,
    progressValue: progressValue,
  }}
  onSendMessage={handleSubmit}
  inputValue={taskInput}
  onInputChange={setTaskInput}
  onStartTask={handleDecompositionConfirm}
  onEditTask={handleDecompositionCancel}
  onPauseResume={handlePauseResume}
/>
```

---

## 四、执行计划

### Phase 1: 连接 ChatBox Props（基础连接）

**目标**：让 ChatBox 能获取任务状态，BottomBox 状态机工作

**任务**：
1. [ ] 更新 AgentPage.jsx - 传递完整 props 给 ChatBox
2. [ ] 更新 agentStore.js - 添加缺失的状态字段
   - `streamingDecomposeText` - 流式分解文本
   - `summaryTask` - 任务摘要
   - `taskRunning` - 运行中的任务状态
3. [ ] 验证 BottomBox 状态机工作

**预期结果**：
- BottomBox 能根据任务状态切换 UI
- 确认按钮出现在 confirm 状态

### Phase 2: TaskCard in MessageList（核心功能）

**目标**：在消息流中显示 TaskCard

**任务**：
1. [ ] 更新 MessageList.jsx - 添加 TaskCard 渲染逻辑
2. [ ] 创建 TaskCardInline 组件（或复用现有 TaskCard）
3. [ ] 实现 StreamingTaskList 组件（流式分解显示）
4. [ ] 添加 TaskCard 的 sticky 定位样式

**预期结果**：
- 任务分解时，TaskCard 出现在消息流中
- 子任务列表实时更新状态

### Phase 3: 增强 BottomBox（交互完善）

**目标**：完善确认/编辑/运行状态的 UI

**任务**：
1. [ ] 实现 BoxHeaderConfirm 组件
   - 显示 "Start Task" 按钮
   - 显示子任务数量
   - 显示编辑按钮（返回编辑）
2. [ ] 实现 BoxHeaderSplitting 组件
   - 显示 "Analyzing task..." 加载动画
3. [ ] 实现 BoxAction 组件增强
   - 显示运行时间
   - 暂停/继续按钮
   - 完成状态显示

**预期结果**：
- 各状态有对应的 UI 展示
- 用户能看到确认倒计时或手动确认

### Phase 4: 30秒自动确认 UI（体验优化）

**目标**：显示自动确认倒计时

**任务**：
1. [ ] 在 BoxHeaderConfirm 中添加倒计时显示
2. [ ] 添加暂停/恢复倒计时按钮
3. [ ] 倒计时结束自动触发确认

**预期结果**：
- 用户能看到 "Auto-confirm in Xs"
- 可以暂停/恢复倒计时

### Phase 5: 清理和优化

**目标**：移除冗余代码，统一体验

**任务**：
1. [ ] 评估 TaskDecomposition Modal 是否保留
   - 如果 inline TaskCard 足够，可以移除
   - 如果需要详细编辑，保留作为 "Edit" 入口
2. [ ] 移除 AgentPage 中未使用的组件引用
3. [ ] 统一样式，确保一致性
4. [ ] 添加测试

---

## 五、文件修改清单

### 需要修改的文件

| 文件 | Phase | 修改内容 |
|------|-------|---------|
| `src/pages/AgentPage.jsx` | 1 | 传递完整 props 给 ChatBox |
| `src/store/agentStore.js` | 1 | 添加缺失状态字段 |
| `src/components/ChatBox/index.jsx` | 1,3 | 接收并使用 task prop |
| `src/components/ChatBox/MessageList.jsx` | 2 | 添加 TaskCard 渲染 |
| `src/components/ChatBox/BottomBox/index.jsx` | 3 | 增强状态机 UI |
| `src/components/ChatBox/BottomBox/BoxHeader.jsx` | 3,4 | 实现 Confirm/Splitting header |
| `src/components/TaskBox/TaskCard.jsx` | 2 | 适配 inline 显示 |
| `src/components/TaskBox/StreamingTaskList.jsx` | 2 | 新建流式分解组件 |
| `src/styles/ChatBox.css` | 2,3 | 添加 TaskCard inline 样式 |

### 可能新建的文件

| 文件 | Phase | 用途 |
|------|-------|------|
| `src/components/ChatBox/TaskCardInline.jsx` | 2 | inline TaskCard 封装 |
| `src/components/TaskBox/StreamingTaskList.jsx` | 2 | 流式分解显示 |

---

## 六、验收标准

### Phase 1 完成标准
- [ ] BottomBox 在 splitting 状态显示加载 UI
- [ ] BottomBox 在 confirm 状态显示确认按钮
- [ ] BottomBox 在 running 状态显示运行 UI

### Phase 2 完成标准
- [ ] 任务分解后，TaskCard 出现在 ChatBox 中
- [ ] 子任务状态实时更新（pending→running→completed）
- [ ] TaskCard 支持状态筛选

### Phase 3 完成标准
- [ ] 确认状态显示 "Start Task" 按钮和子任务数量
- [ ] 运行状态显示运行时间和暂停按钮
- [ ] 完成状态显示结果摘要

### Phase 4 完成标准
- [ ] 显示 "Auto-confirm in Xs" 倒计时
- [ ] 可以暂停/恢复倒计时
- [ ] 倒计时结束自动确认

---

## 七、风险和注意事项

1. **向后兼容**：确保现有功能不受影响
2. **性能**：TaskCard 实时更新可能影响性能，需要优化渲染
3. **状态同步**：确保 agentStore 和 UI 状态一致
4. **样式冲突**：新增样式可能与现有样式冲突

---

## 八、参考资料

- Eigent TaskCard: `third-party/eigent/src/components/ChatBox/TaskBox/TaskCard.tsx`
- Eigent BottomBox: `third-party/eigent/src/components/ChatBox/BottomBox/`
- Eigent chatStore: `third-party/eigent/src/store/chatStore.ts`
- AMI agentStore: `src/clients/desktop_app/src/store/agentStore.js`
