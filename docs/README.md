# AgentCrafter 文档索引

本文档库包含 AgentCrafter 项目的所有技术文档，按照模块分类组织。

## 📁 文档结构

```
docs/
├── baseagent/          # BaseAgent 核心框架文档
├── agentbuilder/       # AgentBuilder 构建系统文档
├── platform/           # AgentCrafter 平台文档
└── guides/             # 通用开发指南
```

---

## 🔧 BaseAgent 核心框架

> **路径**: `docs/baseagent/`
>
> BaseAgent 是 AgentCrafter 的核心运行时框架，提供 Workflow 执行引擎、Agent 抽象、Memory 系统和工具集成。

### 核心架构

- **[ARCHITECTURE.md](baseagent/ARCHITECTURE.md)** - BaseAgent 技术架构概述
- **[CORE_ARCHITECTURE.md](baseagent/CORE_ARCHITECTURE.md)** - 核心实现细节
- **[agent_as_step_design.md](baseagent/agent_as_step_design.md)** - Agent-as-Step 架构设计
- **[contextual_dynamic_architecture.md](baseagent/contextual_dynamic_architecture.md)** - 上下文动态架构
- **[user_customization_design.md](baseagent/user_customization_design.md)** - 用户定制设计
- **[requirements_analysis.md](baseagent/requirements_analysis.md)** - 需求分析

### Workflow 系统

- **[workflow_specification.md](baseagent/workflow_specification.md)** - Workflow YAML 规范
- **[workflow_development_guide.md](baseagent/workflow_development_guide.md)** - Workflow 开发指南
- **[workflow_requirements.md](baseagent/workflow_requirements.md)** - Workflow 需求文档
- **[workflow_enhancement_requirements.md](baseagent/workflow_enhancement_requirements.md)** - 增强需求
- **[variable_chain_design.md](baseagent/variable_chain_design.md)** - 变量链设计

### Memory 系统

- **[memory_system.md](baseagent/memory_system.md)** - Memory 系统架构和使用

### Agent 实现

> **路径**: `docs/baseagent/agents/`

- **[scraper_agent_design.md](baseagent/agents/scraper_agent_design.md)** - ScraperAgent 设计
- **[scraper_agent_requirements.md](baseagent/agents/scraper_agent_requirements.md)** - ScraperAgent 需求

### 工具和 API

> **路径**: `docs/baseagent/tools/`

- **[browser_use_api_reference.md](baseagent/tools/browser_use_api_reference.md)** - Browser-use API 参考
- **[dom_api_reference.md](baseagent/tools/dom_api_reference.md)** - DOM API 参考

---

## 🏗️ AgentBuilder 构建系统

> **路径**: `docs/agentbuilder/`
>
> AgentBuilder 是 AI 驱动的 Agent 自动生成系统，通过自然语言描述生成完整的 Agent 实现。

- **[ARCHITECTURE.md](agentbuilder/ARCHITECTURE.md)** - AgentBuilder 架构设计
- **[REQUIREMENTS.md](agentbuilder/REQUIREMENTS.md)** - AgentBuilder 需求文档
- **[database_design.md](agentbuilder/database_design.md)** - Agent 构建过程数据存储设计
- **[claude_sdk_integration.md](agentbuilder/claude_sdk_integration.md)** - Claude SDK 集成方案

---

## 🌐 AgentCrafter 平台

> **路径**: `docs/platform/`
>
> AgentCrafter 平台提供用户管理、Agent 实例管理、Web UI 和 API 服务。

### 整体架构

- **[AGENTCRAFTER_ARCHITECTURE.md](platform/AGENTCRAFTER_ARCHITECTURE.md)** - AgentCrafter 整体架构
- **[OVERALL_ARCHITECTURE.md](platform/OVERALL_ARCHITECTURE.md)** - 系统总体架构

### BaseApp 应用

- **[baseapp_architecture.md](platform/baseapp_architecture.md)** - BaseApp 应用层架构
- **[baseapp_requirements.md](platform/baseapp_requirements.md)** - BaseApp 需求文档
- **[cli_design.md](platform/cli_design.md)** - CLI 工具设计
- **[user_interface_guide.md](platform/user_interface_guide.md)** - 用户界面指南

### Web 平台

- **[web_design_overview.md](platform/web_design_overview.md)** - Web 平台设计概览
- **[agent_backend_design.md](platform/agent_backend_design.md)** - Agent 后端设计

### 数据和配置

- **[database_architecture.md](platform/database_architecture.md)** - 平台数据库架构
- **[config_design.md](platform/config_design.md)** - 配置系统设计
- **[session_driven_chat.md](platform/session_driven_chat.md)** - 会话驱动的聊天设计
- **[user_behavior_monitoring.md](platform/user_behavior_monitoring.md)** - 用户行为监控

---

## 📚 通用指南

> **路径**: `docs/guides/`

- **[DEVELOPMENT_GUIDE.md](guides/DEVELOPMENT_GUIDE.md)** - 开发指南

---

## 🎯 快速导航

### 我想了解...

**BaseAgent 核心概念**
- 从 [ARCHITECTURE.md](baseagent/ARCHITECTURE.md) 开始
- 阅读 [workflow_specification.md](baseagent/workflow_specification.md) 了解 Workflow 语法
- 查看 [memory_system.md](baseagent/memory_system.md) 了解存储系统

**开发一个 Workflow**
- 阅读 [workflow_development_guide.md](baseagent/workflow_development_guide.md)
- 参考 [workflow_specification.md](baseagent/workflow_specification.md)

**开发一个自定义 Agent**
- 查看 [scraper_agent_design.md](baseagent/agents/scraper_agent_design.md) 作为范例
- 阅读 [agent_as_step_design.md](baseagent/agent_as_step_design.md) 了解架构

**使用 AgentBuilder 生成 Agent**
- 从 [ARCHITECTURE.md](agentbuilder/ARCHITECTURE.md) 开始
- 了解 [claude_sdk_integration.md](agentbuilder/claude_sdk_integration.md)

**部署 AgentCrafter 平台**
- 查看 [AGENTCRAFTER_ARCHITECTURE.md](platform/AGENTCRAFTER_ARCHITECTURE.md)
- 阅读 [baseapp_architecture.md](platform/baseapp_architecture.md)

---

## 📝 文档约定

- **ARCHITECTURE.md** - 高层架构设计
- **REQUIREMENTS.md** - 需求文档
- ***_design.md** - 详细设计文档
- ***_guide.md** - 使用指南
- ***_specification.md** - 规范文档
- ***_reference.md** - API 参考

---

## 🔄 文档更新

文档随代码同步更新。如发现文档过时或错误，请：
1. 在相关文档中添加 TODO 注释
2. 或提交 Issue 到项目仓库

---

**最后更新**: 2025-10-01
