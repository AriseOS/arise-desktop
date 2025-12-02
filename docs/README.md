# Ami 文档索引

本文档库包含 Ami 项目的所有技术文档，按照模块分类组织。

## 📁 文档结构

```
docs/
├── platform/           # Ami 平台文档（最新架构）
├── base_app/           # BaseAgent 核心框架文档（原 baseagent）
├── intent_builder/     # Intent Builder 系统文档
├── app_backend/       # App Backend 文档
├── cloud_backend/      # Cloud Backend 文档
├── workflow_management/ # Workflow 管理文档
├── guides/             # 通用开发指南
└── obsolete/           # 已废弃的文档
```

---

## 🏗️ Ami 平台架构

> **路径**: `docs/platform/`
>
> Ami 是通过观察学习的可进化 AI Agent 系统，采用 App Backend + Cloud Backend 架构。

### 核心设计文档

- **[README.md](platform/README.md)** - 平台文档入口
- **[architecture.md](platform/architecture.md)** - 完整系统架构设计
- **[components_overview.md](platform/components_overview.md)** - 四大核心组件概述
- **[requirements.md](platform/requirements.md)** - MVP 需求分析

### 应用后端设计

- **[app_backend_design.md](platform/design/app_backend_design.md)** - App Backend 详细设计
- **[app_backend_requirements.md](platform/design/app_backend_requirements.md)** - App Backend 需求文档

### 讨论记录

- **[mvp_product_discussion_2025-11-07.md](platform/design/mvp_product_discussion_2025-11-07.md)** - MVP 产品形态讨论
- **[refactoring_plan_2025-11-07.md](platform/refactoring_plan_2025-11-07.md)** - 重构计划和进度

---

## 🔧 BaseAgent 核心框架

> **路径**: `docs/base_app/`
>
> BaseAgent 是 Ami 的核心运行时框架，提供 Workflow 执行引擎、Agent 抽象、Memory 系统和工具集成。

### 核心架构

- **[ARCHITECTURE.md](base_app/ARCHITECTURE.md)** - BaseAgent 技术架构概述
- **[CORE_ARCHITECTURE.md](base_app/CORE_ARCHITECTURE.md)** - 核心实现细节
- **[agent_as_step_design.md](base_app/agent_as_step_design.md)** - Agent-as-Step 架构设计
- **[contextual_dynamic_architecture.md](base_app/contextual_dynamic_architecture.md)** - 上下文动态架构
- **[user_customization_design.md](base_app/user_customization_design.md)** - 用户定制设计

### Workflow 系统

- **[workflow_specification.md](base_app/workflow_specification.md)** - Workflow YAML 规范
- **[workflow_development_guide.md](base_app/workflow_development_guide.md)** - Workflow 开发指南
- **[workflow_requirements.md](base_app/workflow_requirements.md)** - Workflow 需求文档
- **[variable_chain_design.md](base_app/variable_chain_design.md)** - 变量链设计

### Memory 系统

- **[memory_system.md](base_app/memory_system.md)** - Memory 系统架构和使用

### Agent 实现

> **路径**: `docs/base_app/agents/`

- **[scraper_agent_design.md](base_app/agents/scraper_agent_design.md)** - ScraperAgent 设计

### 工具和 API

> **路径**: `docs/base_app/tools/`

- **[browser_use_api_reference.md](base_app/tools/browser_use_api_reference.md)** - Browser-use API 参考
- **[dom_api_reference.md](base_app/tools/dom_api_reference.md)** - DOM API 参考

---

## 🧠 Intent Builder 系统

> **路径**: `docs/intent_builder/`
>
> Intent Builder 是基于意图记忆的新一代 Agent 构建系统，通过 Intent Extraction、Intent Graph 和 MetaFlow 生成 Workflow。

### 核心组件

- **[README.md](intent_builder/README.md)** - 系统概述
- **[01_design_overview.md](intent_builder/01_design_overview.md)** - 系统整体设计
- **[02_intent_specification.md](intent_builder/02_intent_specification.md)** - Intent 规范
- **[03_intent_memory_graph_specification.md](intent_builder/03_intent_memory_graph_specification.md)** - Intent Memory Graph 设计

### 核心组件设计

- **[04_intent_extractor_design.md](intent_builder/04_intent_extractor_design.md)** - Intent Extractor 设计
- **[05_metaflow_specification.md](intent_builder/05_metaflow_specification.md)** - MetaFlow 规范
- **[06_metaflow_design.md](intent_builder/06_metaflow_design.md)** - MetaFlow 设计
- **[07_metaflow_generator_design.md](intent_builder/07_metaflow_generator_design.md)** - MetaFlow Generator 设计

### Workflow 生成

- **[08_workflow_generator_design.md](intent_builder/08_workflow_generator_design.md)** - Workflow Generator 设计
- **[09_complete_pipeline_flow.md](intent_builder/09_complete_pipeline_flow.md)** - 完整流程
- **[10_implementation_guide.md](intent_builder/10_implementation_guide.md)** - 实现指南

---

## 💻 App Backend

> **路径**: `src/app_backend/`
>
> App Backend 运行在用户电脑上，负责录制控制、Workflow 执行和 Cloud API 代理。

### 核心功能

- **录制控制** - 接收 Chrome Extension 的操作事件
- **执行控制** - 使用 BaseAgent 执行 Workflow
- **云端代理** - 统一管理与 Cloud Backend 的通信
- **本地存储** - Workflow 缓存和执行历史

### API 文档

- 启动服务后访问 http://localhost:8000/docs

---

## ☁️ Cloud Backend

> **路径**: `src/cloud_backend/`
>
> Cloud Backend 运行在服务器上，负责 AI 分析、数据存储和 Workflow 生成。

### 核心功能

- **用户管理** - 注册、登录、Token 管理
- **录制数据处理** - 接收并存储操作数据
- **AI 分析** - Intent Extraction、MetaFlow 生成、Workflow 生成
- **数据存储** - 服务器文件系统 + PostgreSQL

### API 文档

- 启动服务后访问 http://localhost:9000/docs

---

## 📋 Workflow 管理

> **路径**: `docs/workflow_management/`

- **[DESIGN.md](workflow_management/DESIGN.md)** - Workflow 管理系统设计
- **[REQUIREMENTS.md](workflow_management/REQUIREMENTS.md)** - Workflow 管理需求

---

## 📚 开发指南

> **路径**: `docs/guides/`

- **[DEVELOPMENT_GUIDE.md](guides/DEVELOPMENT_GUIDE.md)** - 开发环境搭建指南
- **[integration_testing_guide.md](guides/integration_testing_guide.md)** - 集成测试指南

---

## 🎯 快速导航

### 我想了解...

**Ami 系统架构**
- 从 [platform/README.md](platform/README.md) 开始
- 阅读 [platform/architecture.md](platform/architecture.md) 了解完整架构
- 查看 [platform/components_overview.md](platform/components_overview.md) 了解四大组件

**BaseAgent 核心概念**
- 从 [base_app/ARCHITECTURE.md](base_app/ARCHITECTURE.md) 开始
- 阅读 [base_app/workflow_specification.md](base_app/workflow_specification.md) 了解 Workflow 语法
- 查看 [base_app/memory_system.md](base_app/memory_system.md) 了解存储系统

**开发一个 Workflow**
- 阅读 [base_app/workflow_development_guide.md](base_app/workflow_development_guide.md)
- 参考 [base_app/workflow_specification.md](base_app/workflow_specification.md)

**Intent Builder 系统**
- 从 [intent_builder/README.md](intent_builder/README.md) 开始
- 阅读 [intent_builder/01_design_overview.md](intent_builder/01_design_overview.md) 了解系统设计

**运行 App Backend**
```bash
cd src/app_backend
python main.py
# 访问 http://localhost:8000/docs
```

**运行 Cloud Backend**
```bash
cd src/cloud_backend
python main.py
# 访问 http://localhost:9000/docs
```

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

**最后更新**: 2025-11-08
