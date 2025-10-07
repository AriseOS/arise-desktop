# Intent-Based AgentBuilder

这是基于意图记忆的新一代 AgentBuilder 系统。

## 核心设计思想

**意图 + 记忆图 → MetaFlow → Workflow**

用户的操作被抽象为意图，意图之间形成记忆图。新任务通过检索记忆图生成 MetaFlow，最终转换为可执行的 Workflow。

## 文档结构

- `design_overview.md` - 系统整体设计
- `metaflow_design.md` - MetaFlow 格式设计（待讨论）
- `data_structures.md` - 数据结构设计
- `component_design.md` - 各组件详细设计
- `implementation_plan.md` - 实施计划

## 与旧版 AgentBuilder 的区别

| 维度 | 旧版 (agent_builder/) | 新版 (intent_builder/) |
|-----|---------------------|----------------------|
| 核心概念 | 直接生成 workflow | 意图 + 记忆图 |
| 学习能力 | 无 | 持续学习和积累 |
| 复用能力 | 低 | 高（意图可复用） |
| 状态 | 已过期 | 当前开发中 |

## 当前状态

🚧 **设计阶段** - 正在讨论 MetaFlow 格式
