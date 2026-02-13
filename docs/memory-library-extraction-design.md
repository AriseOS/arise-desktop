# Memory Library Extraction Design

> 将 `cloud_backend/memgraph` 迁移到 `common/memory` 公共库

## 1. 目标

将 Memory 系统从 Cloud Backend 专属模块迁移为公共库，让 Desktop App 和 Cloud Backend 都能引用。

**本质**：代码迁移 + 路径修改，不改变功能逻辑。

---

## 2. 迁移范围

### 2.1 完整迁移

```
src/cloud_backend/memgraph/     →     src/common/memory/
├── __init__.py                 →     ├── __init__.py
├── CONTEXT.md                  →     ├── CONTEXT.md
├── ontology/                   →     ├── ontology/
├── graphstore/                 →     ├── graphstore/
├── memory/                     →     ├── memory/
├── services/                   →     ├── services/
├── thinker/                    →     ├── thinker/
├── reasoner/                   →     ├── reasoner/
└── agent/                      →     └── (不迁移)
```

### 2.2 不迁移的模块

| 模块 | 原因 |
|------|------|
| `agent/` | Desktop App 特有的 Agent 集成代码 |

---

## 3. 迁移后的引用方式

### 3.1 import 路径变化

```python
# 之前
from src.cloud_backend.memgraph import WorkflowMemory, Reasoner
from src.cloud_backend.memgraph.graphstore import create_graph_store
from src.cloud_backend.memgraph.ontology import State, Action
from src.cloud_backend.memgraph.services import EmbeddingService

# 之后
from src.common.memory import WorkflowMemory, Reasoner
from src.common.memory.graphstore import create_graph_store
from src.common.memory.ontology import State, Action
from src.common.memory.services import EmbeddingService
```

### 3.2 使用者

| 使用者 | 引用方式 |
|--------|---------|
| Cloud Backend | `from src.common.memory import ...` |
| Desktop App | `from src.common.memory import ...` |

---

## 4. 迁移步骤

### Step 1: 创建目标目录

```bash
mkdir -p src/common/memory
```

### Step 2: 复制代码

```bash
# 复制所有模块（除了 agent/）
cp -r src/cloud_backend/memgraph/ontology src/common/memory/
cp -r src/cloud_backend/memgraph/graphstore src/common/memory/
cp -r src/cloud_backend/memgraph/memory src/common/memory/
cp -r src/cloud_backend/memgraph/services src/common/memory/
cp -r src/cloud_backend/memgraph/thinker src/common/memory/
cp -r src/cloud_backend/memgraph/reasoner src/common/memory/
cp src/cloud_backend/memgraph/__init__.py src/common/memory/
cp src/cloud_backend/memgraph/CONTEXT.md src/common/memory/
```

### Step 3: 修改 import 路径

在 `src/common/memory/` 下所有文件中：

```python
# 替换
src.cloud_backend.memgraph  →  src.common.memory
```

### Step 4: 修改 Cloud Backend 引用

在 `src/cloud_backend/` 下所有引用 memgraph 的文件中：

```python
# 替换
from src.cloud_backend.memgraph  →  from src.common.memory
```

### Step 5: 删除旧目录

```bash
rm -rf src/cloud_backend/memgraph
```

### Step 6: 验证

```bash
# 运行 Cloud Backend
cd src/cloud_backend && python -m uvicorn main:app --reload

# 检查是否正常启动
```

---

## 5. 需要修改 import 的文件清单

### 5.1 common/memory 内部（约 71 个文件）

所有从 `src.cloud_backend.memgraph` 导入的都要改为 `src.common.memory`。

### 5.2 Cloud Backend 其他文件

需要全局搜索 `from src.cloud_backend.memgraph` 并替换。

主要涉及：
- `src/cloud_backend/main.py`
- `src/cloud_backend/routers/*.py`
- 其他引用 Memory 的文件

---

## 6. 外部依赖检查

### 6.1 memgraph 对外部的依赖

| 依赖模块 | 来源 | 处理方式 |
|---------|------|---------|
| `src.common.llm.AnthropicProvider` | common | ✅ 无需修改 |
| `pydantic` | pip | ✅ 无需修改 |
| `networkx` | pip | ✅ 无需修改 |
| `surrealdb` | pip | ✅ 无需修改 |
| `openai` | pip | ✅ 无需修改 |

### 6.2 处理方式

无需特殊处理，所有外部依赖保持不变。

---

## 7. 后续任务：Desktop App 本地 Memory 集成

### 7.1 SurrealDB Embedded 模式 ✅ 已完成

**调研结论**：✅ Python SDK 完全支持 Embedded 模式，使用 `AsyncSurreal` 异步客户端

| 模式 | 连接字符串 | 说明 |
|------|-----------|------|
| 文件 | `surrealkv://~/.ami/memory.db` | SurrealKV 引擎，推荐 |
| 服务器 | `ws://localhost:8000/rpc` | WebSocket 连接 |

**配置示例**：

```python
from src.common.memory.graphstore import create_graph_store, SurrealDBConfig

# Desktop App (本地文件存储)
config = SurrealDBConfig(mode="file", path="~/.ami/memory.db")
store = create_graph_store("surrealdb", config=config)

# Cloud Backend (远程服务器)
config = SurrealDBConfig(mode="server", url="ws://localhost:8000/rpc")
store = create_graph_store("surrealdb", config=config)
```

### 7.2 Embedding 服务集成 ✅ 已完成

**配置（app-backend.yaml）**：

```yaml
embedding:
  provider: openai
  model: BAAI/bge-m3
  dimension: 1024
  api_url: https://api.siliconflow.cn/v1
  api_key_env: SILICONFLOW_API_KEY
```

### 7.3 Desktop App 集成 ✅ 已完成

**创建的文件**：
- `src/clients/desktop_app/ami_daemon/memory/__init__.py`
- `src/clients/desktop_app/ami_daemon/memory/personal_memory.py`
- `src/clients/desktop_app/ami_daemon/memory/CONTEXT.md`

**修改的文件**：
- `src/clients/desktop_app/ami_daemon/config/app-backend.yaml` - 添加 memory 和 embedding 配置
- `src/clients/desktop_app/ami_daemon/daemon.py` - 在 lifespan 中初始化 PersonalMemory

**使用方式**：

```python
from src.clients.desktop_app.ami_daemon.memory import PersonalMemory
from src.clients.desktop_app.ami_daemon.memory.personal_memory import get_personal_memory

# 在 daemon.py 中自动初始化
# 其他地方通过 get_personal_memory() 获取实例
memory = get_personal_memory()
stats = memory.get_stats()
```

---

## 8. 风险与应对

| 风险 | 应对措施 |
|------|---------|
| import 遗漏导致运行时错误 | 全局搜索替换 + 运行测试 |
| 循环依赖 | 迁移后检查 import 顺序 |
| 路径硬编码 | 搜索字符串 "cloud_backend/memgraph" |

---

## 9. 验收标准

1. ✅ `src/common/memory/` 目录存在且结构完整
2. ✅ `src/cloud_backend/memgraph/` 目录已删除
3. ✅ Cloud Backend 正常启动
4. ✅ Memory API 功能正常（add/query/stats/clear）
5. ✅ 无 import 错误
