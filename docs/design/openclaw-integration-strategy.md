# OpenClaw 集成策略

## 目标

将 AMI 的 Memory Planner 和 Learner 能力输出到 OpenClaw 生态，让 OpenClaw 用户在执行浏览器任务时获得工作流记忆辅助，同时将执行数据回馈到共享知识库。

## 架构

```
OpenClaw Agent
  |
  +-- [Plugin: ami-memory-planner] (npm 包)
  |     +-- before_agent_start hook -> 检测浏览器任务 -> 调 AMI API -> 注入 workflow_guide
  |     +-- ami_plan_task tool -> agent 可手动调用规划
  |     +-- agent_end hook -> 采集执行数据 -> 调 AMI Learn API -> 贡献到 public memory
  |     +-- 内置 skill -> 教 agent 何时/如何使用规划
  |
  +-- [ClawHub Skill: ami-planner] (独立发布，轻量)
        +-- Markdown 指令，教 agent 用 curl 调 AMI Planning API
```

## 分发策略

| 渠道 | 形式 | 目标用户 | Learner |
|------|------|---------|---------|
| **ClawHub Skill** | Markdown 指令，curl 调用 | 轻度用户，快速体验 | 无 |
| **npm Plugin** | TypeScript，自动 hook + tool | 深度用户，完整集成 | 有 |

## Planner 集成

Plugin 在浏览器任务前调用 `POST /api/v1/memory/plan`。

- `before_agent_start` hook 检测浏览器相关任务（关键词：browse, visit, click, search, navigate 等）
- 调用 AMI Cloud Backend，传入任务描述
- 将 MemoryPlan 的 workflow_guide 格式化为 agent 可读的上下文
- 通过 hook 返回的 `prependContext` 注入
- 无匹配时静默跳过

## Learner 集成

Plugin 的 `agent_end` hook 采集执行数据，发送到 `POST /api/v1/memory/learn`。

### 数据采集（agent_end hook）

```
agent_end 事件: { messages[], success, durationMs }
  -> 遍历 messages，提取 tool_use block
    -> 对每个 tool_use:
      - tool_name（如 "browser_click", "browser_navigate"）
      - input 关键字段（脱敏处理）
      - 对应 tool_result 的 success/error
      - 从 tool_result 提取 current_url
    -> 组装为 TaskExecutionData 格式
  -> POST /api/v1/memory/learn
```

### 数据脱敏规则

- URL：保留 domain + path 模式，去除敏感 query params
- 输入框内容：替换为 `<user_input>`
- 只保留操作类型 + 目标元素，不保留具体值
- 不采集页面内容、截图、个人数据

### 隐私控制

- Plugin 配置：`contributeToPublicMemory: true | false`（默认 true）
- 用户可随时关闭 Learner 贡献
- 所有贡献数据仅进入 public memory（OpenClaw 用户无 private memory）

## 采用飞轮

```
更多用户安装 Plugin
  -> 更多 agent_end 数据流入 LearnerAgent
    -> 更多 CognitivePhrase 写入 public memory
      -> Planner 返回更好的 workflow_guide
        -> 用户浏览器任务成功率更高
          -> 更多用户安装 Plugin（口碑传播）
```

### 关键原则

1. **Planner 是鱼饵，Learner 是鱼钩**：用户因为 Planner 的价值而安装，Learner 在后台默默运行
2. **网络效应可视化**：在 Planner 输出中展示 "本规划由 N 次社区执行支持"
3. **贡献透明度**：在插件状态中展示 "你已贡献 N 个工作流，帮助了 M 个用户"
4. **优雅降级**：AMI API 不可用时，agent 正常执行（不崩溃、不阻塞）

## 分阶段推进

| 阶段 | 动作 | Learner |
|------|------|---------|
| **Phase 1** | 发布 Skill 到 ClawHub（仅 Planner，curl 调用） | 无 |
| **Phase 2** | 发布 npm Plugin（Planner + Learner 自动 hook） | 有，默认开启 |
| **Phase 3** | 增加贡献统计 + 社区可视化 | 有，带激励 |
| **Phase 4** | 向 OpenClaw 官方提 PR，推荐为内置插件 | 有，规模化 |

## 待决问题

### 1. Cloud Backend 解耦

当前 `main.py` 是 5000+ 行的单体，同时服务 AMI Desktop App + 所有功能。Memory 相关 14 个 endpoint 和以下紧耦合：
- SurrealDB 图存储后端
- 多租户 memory（private + public）
- AMI 专用的 Workflow 生成、Recording 管理

给 OpenClaw 提供 Memory 服务，需要将 Memory Service 抽取为独立微服务（约 400 行 endpoint 代码 + common/memory 模块）。

### 2. API Key 与 LLM 费用

PlannerAgent 和 LearnerAgent 的 LLM 调用谁来付费？

**推荐方案（混合模式）**：
- 用户只需一个 AMI API Key（注册即得）
- Planner 调用：我们付费（核心体验，必须零摩擦）
- Learner 调用：我们付费（用户贡献数据，我们付 LLM 费用作为交换）
- 每个 API Key 有免费额度（如每月 100 次 plan + 50 次 learn）
- 超出后可付费升级，或提供自己的 Anthropic Key

逻辑：**用户贡献执行数据（Learner），我们付 LLM 费用处理——公平交换。**

### 3. 是否开源 Memory Service

**现阶段建议不开源**：
- 飞轮效应依赖数据集中——自建 memory service 会导致 public memory 碎片化
- 核心壁垒是积累的 CognitivePhrase 数据，开源实现会降低壁垒
- 可以开源 Plugin 代码（TypeScript），让用户看到数据采集逻辑，建立信任
- Memory Service 的 API 协议公开即可（OpenAPI spec），无需开源实现

## 技术参考

### Plugin 使用的 AMI API

| 端点 | 用途 | 调用方 |
|------|------|--------|
| `POST /api/v1/memory/plan` | 任务规划（Memory 覆盖分析） | Planner（before_agent_start + tool） |
| `POST /api/v1/memory/learn` | 任务后学习 | Learner（agent_end） |
| `GET /api/v1/memory/stats/public` | Public memory 统计 | 插件状态展示 |

### 使用的 OpenClaw Plugin Hook

| Hook | 用途 | 数据 |
|------|------|------|
| `before_agent_start` | 注入 workflow_guide | `{ prompt }` -> `{ prependContext }` |
| `agent_end` | 采集执行数据 | `{ messages[], success, durationMs }` |

### 数据模型映射：OpenClaw -> AMI

```
OpenClaw messages[]（Anthropic 格式）
  -> 提取 tool_use block 及对应 tool_result
    -> 映射为 ToolUseRecord { tool_name, input_summary, result_summary, success, current_url }
      -> 按子任务分组（启发式：URL 变化 = 新子任务）
        -> 组装 TaskExecutionData { user_request, subtasks[] }
```
