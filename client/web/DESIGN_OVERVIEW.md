# AgentBuilder Web集成设计方案

## 设计目标

将 AgentBuilder 的功能集成到 client/web 系统中，实现从用户输入到 Agent 构建的完整流程。

## 核心功能需求

### 1. 用户流程设计
```
首页输入需求 → 提交 → AgentBuilder构建 → 跳转workspace → 实时显示进度 → 展示workflow → 对话测试
```

### 2. 三个核心功能点

#### 功能点 1: HomePage → Workspace 流程
- **HomePage**: 用户在 userdialog 中输入需求描述
- **提交时**: 调用 AgentBuilder 开始构建 Agent
- **跳转**: 自动跳转到 workspace 页面并传递构建会话ID

#### 功能点 2: 实时进度显示
- **AgentBuilder 思考过程**: 将构建过程中的思考步骤输出到 workspace 的 Agent output 区域
- **实时更新**: 通过 API 轮询或 WebSocket 实时推送构建进度
- **进度阶段**: 需求解析、工具分析、代码生成、测试部署等

#### 功能点 3: 结果展示和交互
- **中间窗口**: 展示构建出来的 Agent 的 Workflow 逻辑结构
- **右侧窗口**: 提供与构建好的 Agent 的实时对话功能

## 技术架构设计

### 后端 API 设计

#### 核心API接口 (4个)
```python
# 1. 开始构建 Agent
POST /api/agents/build
{
    "description": "用户需求描述",
    "agent_name": "可选的Agent名称"
}
→ 返回: {"build_id": "uuid", "status": "building"}

# 2. 实时构建进度 (WebSocket)
WS /ws/agents/build/{build_id}
→ 推送: {"step": "requirement_parsing", "status": "in_progress", "message": "正在解析需求..."}

# 3. 获取构建好的Workflow
GET /api/agents/{agent_id}/workflow
→ 返回: {"workflow": {...}, "steps": [...], "metadata": {...}}

# 4. Agent对话 (WebSocket)  
WS /ws/agents/{agent_id}/chat
→ 双向: {"message": "用户消息"} ↔ {"response": "Agent回复"}
```

#### 数据库设计
```sql
-- Agent构建会话表
agent_build_sessions (
    build_id,
    user_id,
    description,
    status,
    current_step,
    progress_message,
    error_message,
    result_data
)

-- 生成的Agent信息表
generated_agents (
    agent_id,
    build_session_id,
    user_id,
    name,
    workflow_data,
    code_path,
    metadata_path
)
```

### 前端页面改造

#### HomePage 修改
```typescript
const handleGenerate = async () => {
  const result = await agentAPI.buildAgent(prompt);
  navigate('/workspace', { 
    state: { 
      buildId: result.build_id,
      initialPrompt: prompt 
    } 
  });
};
```

#### WorkspacePage 布局
```
┌─────────────────────────────────────────────────────┐
│                    Header                           │
├─────────┬─────────────────────────┬─────────────────┤
│ 左侧面板 │        中间面板          │     右侧面板     │
│         │                        │                │
│ Agent   │    Workflow           │   Agent 对话     │
│ 输出日志 │    可视化展示          │   预览窗口       │
│         │                        │                │
│ 用户    │    工作流结构          │   实时对话       │
│ 对话区   │    步骤显示            │   测试区域       │
└─────────┴─────────────────────────┴─────────────────┘
```

## 实现阶段划分

### Phase 1: 基础构建流程 ✅
- [x] 实现 `/api/agents/build` 接口
- [x] 集成 AgentBuilder 调用
- [x] 基础的状态返回和跳转逻辑
- [x] HomePage 提交逻辑修改
- [x] 基础 WorkspacePage 布局

### Phase 2: 实时进度显示
- [ ] WebSocket 连接建立
- [ ] AgentBuilder 进度推送机制
- [ ] 前端实时显示构建日志
- [ ] 详细的构建步骤追踪

### Phase 3: Workflow展示
- [ ] Workflow 数据格式设计
- [ ] 可视化组件开发 (节点图/流程图)
- [ ] 中间窗口展示实现
- [ ] 缩放、拖拽交互功能

### Phase 4: Agent对话
- [ ] 生成的Agent代码执行环境
- [ ] 对话WebSocket接口
- [ ] 右侧聊天窗口UI
- [ ] 实时对话功能

## 当前实现状态

### 已完成
- ✅ 后端基础API框架
- ✅ AgentBuilder 集成 (真实连接)
- ✅ 数据库模型设计
- ✅ HomePage 改造完成
- ✅ WorkspacePage 基础布局
- ✅ 构建状态轮询机制

### 当前问题
1. **构建进度显示简单**: 目前只显示几个基础状态，缺少详细的构建过程日志
2. **AgentBuilder 日志捕获**: 需要捕获 AgentBuilder 内部的 logger 输出
3. **WebSocket 未实现**: 目前使用轮询，需要改为 WebSocket 实时推送
4. **Workflow 可视化缺失**: 中间面板暂时只显示占位符
5. **Agent 对话功能缺失**: 右侧面板暂时只显示占位符

### 技术关键点
- **日志捕获**: 需要拦截 AgentBuilder 的 logger 输出并转发给前端
- **进度分解**: 将 AgentBuilder 的构建过程细分为更多可观察的步骤
- **WebSocket 架构**: 建立稳定的实时通信机制
- **Workflow 数据结构**: 设计适合前端可视化的数据格式
- **Agent 执行环境**: 为生成的 Agent 提供独立的运行环境

## 设计原则

1. **从简单到复杂**: 先实现基础功能，再逐步优化
2. **不考虑向后兼容**: 专注于新功能的完整实现  
3. **实时性优先**: 用户体验要求实时反馈构建进度
4. **模块化设计**: 每个阶段的功能相对独立，便于逐步开发
5. **用户体验导向**: 界面布局和交互要直观易用