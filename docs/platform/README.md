# Ami Platform 文档

**最新架构文档** - 2025-11-07

---

## 📚 核心文档

### 架构设计
- **[architecture.md](./architecture.md)** - 完整系统架构（四大组件）
- **[components_overview.md](./components_overview.md)** - 组件详细说明
- **[requirements.md](./requirements.md)** - 需求分析

### 重构相关
- **[refactoring_plan_2025-11-07.md](./refactoring_plan_2025-11-07.md)** - 重构计划和进度
- **[mvp_product_discussion_2025-11-07.md](./mvp_product_discussion_2025-11-07.md)** - 产品讨论记录

---

## 🗂️ 文档说明

### 当前架构（v2.0）

```
Ami 系统 = 4 个核心组件

1. Desktop App (Tauri)    - 主控制中心
2. Chrome Extension       - 录制 + 快速执行
3. Local Backend          - 执行引擎 + 云端代理
4. Cloud Backend          - AI 分析 + 数据存储
```

### 存储路径

- **Local Backend**: `~/.ami/`
- **Cloud Backend**: `~/.ami/` (开发) 或 `/var/lib/ami/` (生产)

---

## 📖 阅读顺序

1. **快速了解**: [components_overview.md](./components_overview.md)
2. **完整架构**: [architecture.md](./architecture.md)
3. **需求背景**: [requirements.md](./requirements.md)
4. **重构历史**: [refactoring_plan_2025-11-07.md](./refactoring_plan_2025-11-07.md)

---

## 🗄️ 已删除文档

以下文档已过时，已删除：
- `agent_backend_design.md` - 旧 Agent 后端设计
- `AGENTCRAFTER_ARCHITECTURE.md` - 旧架构
- `baseapp_architecture.md` - 移至 docs/baseagent/
- `cli_design.md` - CLI 已废弃
- `database_architecture.md` - 旧数据库设计
- `session_driven_chat.md` - 聊天功能已废弃
- `user_interface_guide.md` - 旧 UI 设计
- `web_design_overview.md` - Web 前端已废弃

---

**维护**: Droid  
**更新**: 2025-11-07
