# AMI 产品演进路线图

本目录包含 AMI 产品的演进规划文档，核心是引入 ReAct Agent 能力，与现有 Workflow 系统形成互补。

## 核心理念

> **All agent needs is context**

- Workflow 是结果，不是起点
- ReAct + Memory 是过程
- 越用越聪明

## 文档索引

| 文档 | 描述 |
|------|------|
| [react-agent-integration.md](./react-agent-integration.md) | 整体集成方案和路线图 |
| [phase1-autonomous-browser-agent.md](./phase1-autonomous-browser-agent.md) | Phase 1 详细实现规范 |
| [eigent-analysis.md](./eigent-analysis.md) | Eigent 项目分析（技术参考） |

## 演进路线

```
Phase 1                 Phase 2              Phase 3              Phase 4
    │                      │                    │                    │
    ▼                      ▼                    ▼                    ▼
┌─────────────┐      ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│ 独立的      │      │ + Memory    │      │ + Memory    │      │ Workflow    │
│ BrowserAgent│ ───► │   生成 Plan │ ───► │   纠错能力  │ ───► │ 失败时调用  │
│ (自主执行)  │      │             │      │             │      │ BrowserAgent│
└─────────────┘      └─────────────┘      └─────────────┘      └─────────────┘
```

### Phase 1: 独立的自主 BrowserAgent ⬅️ 当前

**目标:** 给 AMI 加上自主执行能力

- 接受文字描述的任务
- 调用 LLM 拆分任务生成 Plan
- ReAct 模式逐步执行
- 与现有 Workflow 完全分开

**交付物:**
- `AutonomousBrowserAgent` 核心 Agent
- `PageSnapshot` 页面快照工具（从 Eigent 移植）
- `ActionExecutor` 动作执行器（从 Eigent 移植）
- Quick Task API 和前端页面

### Phase 2: Memory 生成 Plan

**目标:** 利用历史经验改进 Plan 生成

- 相似任务的执行经验
- 网站交互模式记录
- 执行成功后自动记录

### Phase 3: Memory 纠错能力

**目标:** 执行出错时智能恢复

- 查询相似错误的处理方式
- 无记录时询问用户或 LLM 猜测
- 新方案存入 Memory

### Phase 4: Workflow 协作

**目标:** Workflow 和 ReAct 协同工作

- Workflow 步骤失败时触发 BrowserAgent
- BrowserAgent 尝试完成该步骤
- 成功后继续 Workflow 执行

## 产品价值

### 对用户

| 场景 | 现状 | 集成后 |
|------|------|--------|
| 首次任务 | Workflow 生成不可靠 | ReAct 灵活处理 |
| 重复任务 | 每次 ReAct，慢且费 token | 自动使用已验证 Workflow |
| 任务变体 | 小改动就要重新生成 | Memory 提供经验，灵活适应 |
| 意外情况 | Workflow 出错就卡死 | ReAct 查 Memory 或问用户 |

### 长期愿景

```
用户: "帮我做 XXX"
    ↓
系统自动判断:
    • 有成熟 Workflow？ → 直接执行（快、省 token）
    • 没有？ → ReAct 执行（灵活、能处理意外）
    • 执行多次后 → 后台总结生成 Workflow

用户无需关心底层是 Workflow 还是 ReAct
```

## 相关资源

- [Eigent 项目](https://github.com/eigent-ai/eigent) - 参考其 Browser Agent 实现
- [ReAct 论文](https://arxiv.org/abs/2210.03629) - Reasoning + Acting 模式
- [CAMEL-AI](https://github.com/camel-ai/camel) - Eigent 使用的 Agent 框架
