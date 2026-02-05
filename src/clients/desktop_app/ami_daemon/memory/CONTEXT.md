# Memory Module

Desktop App 的 Memory 模块，目前作为代理转发请求到 Cloud Backend。

## 架构

```
Frontend / Extension
       │
       ▼
Daemon HTTP (/api/v1/memory/*)
       │
       │  Proxy (HTTP)
       ▼
Cloud Backend (/api/v1/memory/*)
       │
       ▼
Neo4j (Public Memory)
```

## 当前状态

**Local Memory 已禁用**。所有 Memory API 请求都通过 Daemon 代理到 Cloud Backend。

| 组件 | 状态 | 说明 |
|------|------|------|
| Local Memory (SurrealDB) | 禁用 | 配置保留，未初始化 |
| Daemon HTTP API | 代理模式 | 转发到 Cloud Backend |
| Cloud Backend | 启用 | Neo4j 存储 |

## HTTP API (代理)

Daemon 提供的 Memory HTTP 接口，全部代理到 Cloud Backend：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/memory/add` | POST | 添加录制到记忆 |
| `/api/v1/memory/query` | POST | 语义查询记忆 |
| `/api/v1/memory/stats` | GET | 获取统计信息 |
| `/api/v1/memory` | DELETE | 清空所有记忆 |
| `/api/v1/memory/phrases` | GET | 列出 CognitivePhrase |
| `/api/v1/memory/phrases/{id}` | GET | 获取 CognitivePhrase 详情 |
| `/api/v1/memory/phrases/{id}` | DELETE | 删除 CognitivePhrase |
| `/api/v1/memory/debug` | GET | 禁用（仅本地模式可用） |

## 配置

`app-backend.yaml`:

```yaml
# Local Memory 配置（保留，未启用）
memory:
  url: file://${storage.base_path}/memory.db
  namespace: ami
  database: personal

# Cloud Backend（实际使用）
cloud:
  api_url: http://127.0.0.1:9000  # 开发环境
  # api_url: https://cloud.ariseos.com  # 生产环境

# Embedding Service（Cloud Backend 使用）
embedding:
  provider: openai
  model: BAAI/bge-m3
  dimension: 1024
  api_url: https://api.siliconflow.cn/v1
  api_key_env: SILICONFLOW_API_KEY
```

## 文件结构

- `__init__.py` - 重新导出 common/memory 接口（为将来启用本地 Memory 准备）
- `CONTEXT.md` - 本文档

## 将来计划

启用 Local Memory 时需要：
1. 在 daemon.py 中初始化 `local_memory_service`
2. 修改 HTTP 端点使用 `get_local_memory_service()`
3. 或者让 MemoryToolkit 直接调用本地 MemoryService
