# Ami 前端重构计划：对齐 Eigent 设计

## 目标

将 Ami 前端布局重构为与 Eigent 一致的设计：
- **ChatBox 只负责对话**（用户消息、Agent 回复）
- **Workspace 负责执行详情**（Thinking、Toolkit、Browser、Terminal、Files）
- **清晰的职责分离**，减少信息混杂

---

## 当前布局 vs 目标布局

### 当前布局
```
┌─────────────────────────────────────────────────────────────┐
│                    Compact Header                           │
├────────────────────────────────────┬────────────────────────┤
│         Left Panel                 │      Right Panel       │
│  ┌──────────────────────────────┐  │  ┌──────────────────┐  │
│  │ Task Status Bar              │  │  │ Agents Section   │  │
│  │ Tool Activity Panel ▼        │  │  │ File Browser     │  │
│  │ Memory Paths Card            │  │  │ File Preview     │  │
│  │ ChatBox (混合内容)           │  │  │ Terminal Output  │  │
│  │ Result/Error/Notes Cards     │  │  │                  │  │
│  └──────────────────────────────┘  │  └──────────────────┘  │
└────────────────────────────────────┴────────────────────────┘
```

### 目标布局
```
┌─────────────────────────────────────────────────────────────┐
│                    Compact Header                           │
├─────────────────────────────┬───────────────────────────────┤
│      ChatBox (35%)          │       Workspace (65%)         │
│      (纯对话)               │       (Tabs 切换)             │
│  ┌───────────────────────┐  │  ┌─────────────────────────┐  │
│  │ [User] 消息            │  │  │ [Agent|Browser|Files|Terminal] │
│  │ [Agent] 回复           │  │  ├─────────────────────────┤  │
│  │ [System] 通知          │  │  │                         │  │
│  │                       │  │  │  << Tab 内容 >>          │  │
│  │                       │  │  │                         │  │
│  └───────────────────────┘  │  └─────────────────────────┘  │
│  ┌───────────────────────┐  │                               │
│  │ [Input Box]           │  │                               │
│  └───────────────────────┘  │                               │
├─────────────────────────────┴───────────────────────────────┤
│ [Status Bar] Running │ Task: xxx...  │ [Pause] [Cancel]     │
└─────────────────────────────────────────────────────────────┘
```

---

## 重构阶段

### Phase 1: 创建 Workspace Tabs 组件框架

**目标**: 创建右侧 Workspace 的 Tab 切换基础架构

**新建文件**:
```
src/components/Workspace/
├── index.js                    # 导出
├── WorkspaceTabs.jsx           # Tab 容器组件
├── WorkspaceTabs.css           # 样式
├── tabs/
│   ├── index.js               # 导出所有 tabs
│   ├── AgentTab.jsx           # Agent 执行详情 tab
│   ├── BrowserTab.jsx         # 浏览器视图 tab
│   ├── FilesTab.jsx           # 文件浏览 tab (复用 FileBrowser)
│   └── TerminalTab.jsx        # 终端输出 tab (复用 TerminalOutput)
```

**改动内容**:

1. `WorkspaceTabs.jsx` - 新建
   - Tab 切换逻辑（Agent / Browser / Files / Terminal）
   - 根据当前 tab 渲染对应内容
   - Tab 图标和标签

2. `AgentTab.jsx` - 新建
   - 整合 Memory Paths 显示
   - 整合 Thinking/Reasoning 显示
   - 整合 Toolkit Events 显示（从 Tool Activity Panel 移植）
   - 整合 Result/Error 显示

3. `BrowserTab.jsx` - 新建
   - 显示浏览器截图
   - 显示当前 URL
   - 预留 Take Control 功能

4. `FilesTab.jsx` - 新建
   - 包装现有 `FileBrowser.jsx`
   - 包装现有 `FilePreview.jsx`

5. `TerminalTab.jsx` - 新建
   - 包装现有 `TerminalOutput.jsx`

**预计工作量**: 2-3 天

---

### Phase 2: 重构 AgentPage 布局

**目标**: 将 AgentPage 改为新的两栏布局

**修改文件**:
- `src/pages/AgentPage.jsx`
- `src/styles/AgentPage.css`

**改动内容**:

1. **删除左侧面板中的组件**:
   - ❌ Tool Activity Panel (`<details className="tool-activity-panel">`)
   - ❌ Memory Paths Card
   - ❌ Result Card
   - ❌ Error Card
   - ❌ Notes Card
   - ❌ Task Status Bar (移到底部)

2. **简化左侧面板**:
   ```jsx
   <div className="left-panel">
     <ChatBox ... />  {/* 只保留 ChatBox */}
   </div>
   ```

3. **替换右侧面板**:
   ```jsx
   <div className="right-panel">
     <WorkspaceTabs
       activeTab={activeTab}
       onTabChange={setActiveTab}
       taskId={taskId}
       // 传入需要的数据
       toolkitEvents={toolkitEvents}
       memoryPaths={memoryPaths}
       thinkingLogs={thinkingLogs}
       terminalOutput={terminalOutput}
       workspaceFiles={workspaceFiles}
       browserScreenshot={browserScreenshot}
       result={result}
       error={error}
     />
   </div>
   ```

4. **添加底部 Status Bar**:
   ```jsx
   <div className="status-bar">
     <TaskStatusIndicator status={taskStatus} />
     <span className="task-description">{taskDescription}</span>
     <div className="task-controls">
       <button onClick={onPause}>Pause</button>
       <button onClick={onCancel}>Cancel</button>
     </div>
   </div>
   ```

5. **更新 CSS 布局**:
   ```css
   .execution-layout {
     display: flex;
     flex: 1;
   }
   .left-panel {
     flex: 0 0 35%;
     max-width: 450px;
     min-width: 300px;
   }
   .right-panel {
     flex: 1;
     min-width: 400px;
   }
   .status-bar {
     flex: 0 0 auto;
     height: 40px;
     border-top: 1px solid var(--border-color);
   }
   ```

**预计工作量**: 1-2 天

---

### Phase 3: 重构 ChatBox 组件

**目标**: 简化 ChatBox，只保留对话功能

**修改文件**:
- `src/components/ChatBox/index.jsx`
- `src/components/ChatBox/MessageList.jsx`
- `src/components/ChatBox/ChatBox.css`

**改动内容**:

1. **简化 MessageList 渲染逻辑**:
   - 只渲染 `role: user` 和 `role: assistant` 消息
   - 系统通知 (notices) 保留但简化
   - 移除 thinking/reasoning 消息的特殊渲染
   - 移除 tool_result 消息的详细渲染

2. **消息类型过滤**:
   ```jsx
   // 只显示对话消息
   const displayMessages = messages.filter(m =>
     m.role === 'user' ||
     m.role === 'assistant' ||
     m.type === 'system_notice'
   );
   ```

3. **简化 AgentMessage 组件**:
   - 移除 thinking 展开/折叠逻辑
   - 移除 tool calls 内联显示
   - 只显示最终文本回复

4. **更新样式**:
   - 移除 thinking 相关样式
   - 移除 tool-result 相关样式
   - 保持干净的对话界面

**预计工作量**: 1 天

---

### Phase 4: 实现 AgentTab 详情视图

**目标**: 完善 Agent Tab 的执行详情展示

**新建/修改文件**:
- `src/components/Workspace/tabs/AgentTab.jsx`
- `src/components/Workspace/tabs/AgentTab.css`

**组件结构**:
```jsx
<AgentTab>
  {/* Memory Paths Section */}
  <MemoryPathsSection paths={memoryPaths} />

  {/* Execution Timeline */}
  <ExecutionTimeline>
    {timelineEvents.map(event => (
      <TimelineItem key={event.id}>
        {event.type === 'thinking' && <ThinkingItem content={event.content} />}
        {event.type === 'toolkit' && <ToolkitItem event={event} />}
      </TimelineItem>
    ))}
  </ExecutionTimeline>

  {/* Result Section */}
  {result && <ResultSection result={result} />}
  {error && <ErrorSection error={error} />}
</AgentTab>
```

**子组件**:

1. `MemoryPathsSection` - 显示语义搜索结果
   - 复用现有 Memory Paths Card 逻辑
   - 可折叠

2. `ExecutionTimeline` - 时间线容器
   - 按时间排序显示 thinking + toolkit 事件
   - 滚动到最新

3. `ThinkingItem` - 思考过程项
   - 显示 💭 图标
   - Markdown 渲染内容
   - 可折叠长内容

4. `ToolkitItem` - 工具调用项
   - 显示 🔧 图标 + 状态 (⟳/✓/✗)
   - 显示 toolkit_name.method_name
   - 显示 input_preview
   - 显示 output_preview (完成后)
   - 显示耗时

5. `ResultSection` - 结果显示
   - JSON 格式化
   - 复制按钮

6. `ErrorSection` - 错误显示
   - 错误堆栈
   - 红色主题

**预计工作量**: 2 天

---

### Phase 5: 实现 BrowserTab 视图

**目标**: 显示浏览器状态和截图

**新建文件**:
- `src/components/Workspace/tabs/BrowserTab.jsx`
- `src/components/Workspace/tabs/BrowserTab.css`

**功能**:
1. 显示当前页面 URL
2. 显示最新浏览器截图
3. 截图刷新（手动/自动）
4. 预留 Take Control 按钮

**数据来源**:
- `browser_screenshot` SSE 事件
- `browser_navigated` SSE 事件

**预计工作量**: 1 天

---

### Phase 6: 数据流重构

**目标**: 确保数据正确流向新组件

**修改文件**:
- `src/store/agentStore.js`
- `src/store/chatStore.js`

**改动内容**:

1. **分离消息类型**:
   ```js
   // chatStore 新增
   thinkingLogs: [],      // thinking/reasoning 日志
   addThinkingLog: (taskId, log) => { ... },
   ```

2. **SSE 事件路由更新**:
   ```js
   case 'llm_reasoning':
     // 不再添加到 messages，添加到 thinkingLogs
     store.addThinkingLog(taskId, event);
     break;

   case 'activate_toolkit':
   case 'deactivate_toolkit':
     // 保持现有逻辑，确保 toolkitEvents 正确更新
     break;
   ```

3. **AgentPage 数据传递**:
   ```jsx
   // 从 store 获取分离的数据
   const { messages, thinkingLogs, toolkitEvents, ... } = useAgentStore();

   // 传递给对应组件
   <ChatBox messages={messages} />
   <WorkspaceTabs
     thinkingLogs={thinkingLogs}
     toolkitEvents={toolkitEvents}
     ...
   />
   ```

**预计工作量**: 1 天

---

### Phase 7: 样式和 UX 优化

**目标**: 完善视觉效果和交互体验

**改动内容**:

1. **Tab 切换动画**
2. **时间线滚动优化**（自动滚动到最新）
3. **响应式布局**（移动端适配）
4. **暗色主题适配**
5. **加载状态和骨架屏**

**预计工作量**: 1-2 天

---

## 文件变更汇总

### 新建文件 (11 个)
```
src/components/Workspace/
├── index.js
├── WorkspaceTabs.jsx
├── WorkspaceTabs.css
└── tabs/
    ├── index.js
    ├── AgentTab.jsx
    ├── AgentTab.css
    ├── BrowserTab.jsx
    ├── BrowserTab.css
    ├── FilesTab.jsx
    └── TerminalTab.jsx
```

### 修改文件 (8 个)
```
src/pages/AgentPage.jsx          # 主要重构
src/styles/AgentPage.css         # 布局样式更新
src/components/ChatBox/index.jsx # 简化逻辑
src/components/ChatBox/MessageList.jsx  # 消息过滤
src/components/ChatBox/ChatBox.css      # 样式简化
src/components/ChatBox/MessageItem/AgentMessage.jsx  # 简化
src/store/agentStore.js          # 数据分离
src/store/chatStore.js           # SSE 路由更新
```

### 可删除文件 (0 个)
- 暂无，现有 Workspace 组件可复用

---

## 时间估算

| Phase | 内容 | 预计时间 |
|-------|------|---------|
| Phase 1 | 创建 Workspace Tabs 框架 | 2-3 天 |
| Phase 2 | 重构 AgentPage 布局 | 1-2 天 |
| Phase 3 | 重构 ChatBox 组件 | 1 天 |
| Phase 4 | 实现 AgentTab 详情 | 2 天 |
| Phase 5 | 实现 BrowserTab | 1 天 |
| Phase 6 | 数据流重构 | 1 天 |
| Phase 7 | 样式和 UX 优化 | 1-2 天 |
| **总计** | | **9-12 天** |

---

## 风险和注意事项

1. **SSE 事件兼容性**: 确保后端事件格式与前端期望一致
2. **状态同步**: 多个 Tab 共享数据时的状态同步
3. **性能**: 长时间运行任务的 thinkingLogs 和 toolkitEvents 可能积累很多，需要考虑虚拟滚动
4. **向后兼容**: 考虑是否需要保留旧布局作为选项

---

## 测试清单

- [ ] ChatBox 只显示对话消息
- [ ] Agent Tab 正确显示 thinking + toolkit 时间线
- [ ] Toolkit 事件状态正确更新（running → completed/failed）
- [ ] Browser Tab 显示截图
- [ ] Files Tab 文件浏览正常
- [ ] Terminal Tab 输出正常
- [ ] Tab 切换流畅
- [ ] 底部 Status Bar 状态正确
- [ ] Pause/Resume/Cancel 功能正常
- [ ] 响应式布局正常
