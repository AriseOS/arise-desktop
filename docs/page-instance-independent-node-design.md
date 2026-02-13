# PageInstance 独立节点设计

> 2026-02-10

## 1. 背景与问题

### 1.1 当前状态

PageInstance 在设计文档 (`memory-graph-ontology-design.md`) 中被定义为"具体页面实例"，但实现上一直作为 State 的嵌套 JSON 数组存储：

```
SurrealDB state table:
{
  "id": "state:xxx",
  "page_url": "https://example.com/products/123",
  "instances": [           ← 嵌套 JSON，不是独立节点
    {"id": "pi-1", "url": "...", "timestamp": 1700000000}
  ]
}
```

### 1.2 存在的问题

1. **snapshot 数据丢失**：BehaviorRecorder 采集了页面 snapshot（accessibility tree text），但 `add_to_memory` 接口没有传递 snapshots，WorkflowProcessor 也不处理它，导致 snapshot 数据在存入 Memory 时被丢弃
2. **PageInstance 字段不足**：现有 6 个字段中 `dom_snapshot_id` 从未赋值，也没有 `snapshot_text` 字段来直接存储页面快照内容
3. **嵌套存储不适合存文档**：snapshot_text 通常几 KB 到几十 KB，嵌套在 State 节点中会导致 State 越来越大
4. **无法独立查询**：无法按时间、session、URL 等维度单独查询 PageInstance

### 1.3 目标

- PageInstance 作为独立图节点，State 通过 `HAS_INSTANCE` 边指向 PageInstance
- PageInstance 直接存储 `snapshot_text`（页面 accessibility tree 文本）
- 从 recording 的 snapshots 数据中提取 snapshot_text，在 add_to_memory 时写入
- private 和 public memory 均改为独立节点

---

## 2. 数据流分析

### 2.1 Snapshot 数据的现有生命周期

```
BehaviorRecorder._capture_snapshot()
  → self.snapshots[url_hash] = {url, snapshot_text, captured_at}

RecordingService.stop_recording()
  → recording_result["snapshots"] = self.snapshots.copy()
  → _save_snapshots() → StorageManager.save_snapshot()
    → ~/.ami/recordings/{session_id}/snapshots/{url_hash}.yaml

StorageManager.get_recording()
  → 加载 snapshots/*.yaml
  → data["snapshots"] = {url: {url, snapshot, captured_at}}   # key 变成了 url
```

### 2.2 断裂点

```
Daemon add_to_memory()                     ← 只取 operations，丢弃 snapshots
  → cloud_client.add_to_memory(operations) ← 不传 snapshots
    → Cloud /api/v1/memory/add             ← 接口不接受 snapshots
      → WorkflowProcessor                  ← 不知道 snapshots 的存在
        → PageInstance(dom_snapshot_id=None) ← 从未赋值
```

### 2.3 修复后的数据流

```
Daemon add_to_memory()
  → 如果有 recording_id，加载 recording（含 snapshots）
  → cloud_client.add_to_memory(operations, snapshots=snapshots)
    → Cloud /api/v1/memory/add(operations, snapshots)
      → WorkflowProcessor(snapshots=snapshots)
        → _create_page_instance(segment, snapshots)
          → 按 URL 匹配 snapshot → PageInstance(snapshot_text=...)
        → _store_to_memory()
          → page_instance_manager.create_instance(instance)   # 独立节点
          → page_instance_manager.link_to_state(state_id, instance.id)  # 边
```

---

## 3. 数据模型变更

### 3.1 PageInstance 新增字段

```python
class PageInstance(BaseModel):
    id: str                          # UUID (保留)
    url: str                         # 具体 URL (保留)
    page_title: Optional[str]        # 页面标题 (保留)
    timestamp: int                   # 访问时间 (保留)
    session_id: Optional[str]        # Session ID (保留)
    snapshot_text: Optional[str]     # 新增：页面 accessibility tree 文本
    # 删除 dom_snapshot_id，不再使用引用方式
```

### 3.2 图结构变更

```
之前：
  State {instances: [PageInstance, ...]}    ← 嵌套 JSON

之后：
  State ──HAS_INSTANCE──▶ PageInstance      ← 独立节点 + 边
  State ──HAS_INSTANCE──▶ PageInstance
```

### 3.3 SurrealDB Schema 新增

```sql
-- 新增实体表
DEFINE TABLE pageinstance SCHEMALESS

-- 新增关系表
DEFINE TABLE has_instance SCHEMALESS TYPE RELATION
DEFINE FIELD in ON has_instance TYPE record<state> REFERENCE ON DELETE CASCADE
DEFINE FIELD out ON has_instance TYPE record<pageinstance> REFERENCE ON DELETE CASCADE

-- 索引
DEFINE INDEX idx_pageinstance_id ON pageinstance FIELDS id UNIQUE
DEFINE INDEX idx_pageinstance_url ON pageinstance FIELDS url
DEFINE INDEX idx_pageinstance_session_id ON pageinstance FIELDS session_id
DEFINE INDEX idx_has_instance_unique ON has_instance FIELDS in, out UNIQUE
```

---

## 4. 变更清单

### 4.1 模型层

| 文件 | 变更 |
|------|------|
| `src/common/memory/ontology/page_instance.py` | 新增 `snapshot_text` 字段，删除 `dom_snapshot_id` |

### 4.2 存储层

| 文件 | 变更 |
|------|------|
| `src/common/memory/graphstore/surrealdb_graph.py` | `initialize_schema()`: 新增 `pageinstance` 表、`has_instance` 关系表、索引 |
| `src/common/memory/memory/memory.py` | 新增 `PageInstanceManager` ABC |
| `src/common/memory/memory/workflow_memory.py` | 新增 `GraphPageInstanceManager` 实现；`WorkflowMemory.__init__` 添加 manager；修改 `add_page_instance()`、`get_memory_stats()` |

### 4.3 State 模型

| 文件 | 变更 |
|------|------|
| `src/common/memory/ontology/state.py` | `to_dict()` 序列化时排除 `instances`；`from_dict()` 兼容旧数据；保留内存中的 `instances` 字段供向后兼容 |

### 4.4 处理层

| 文件 | 变更 |
|------|------|
| `src/common/memory/thinker/workflow_processor.py` | 接收 `snapshots` 参数；`_create_page_instance()` 匹配 URL 获取 snapshot_text；`_store_to_memory()` 新增 PageInstance 独立存储逻辑（参照 IntentSequence 模式） |
| `src/common/memory/memory/url_index.py` | `build_from_graph()` 改用 `has_instance` 关系查询，不再遍历 `state.instances` |

### 4.5 API 层

| 文件 | 变更 |
|------|------|
| `src/cloud_backend/main.py` | `POST /api/v1/memory/add` 接受 `snapshots` 参数并传给 WorkflowProcessor；Stats API 更新 PageInstance 计数 |
| `src/clients/desktop_app/ami_daemon/daemon.py` | `AddToMemoryRequest` 新增 `snapshots` 字段；加载 recording 时传递 snapshots |
| `src/clients/desktop_app/ami_daemon/services/cloud_client.py` | `add_to_memory()` 新增 `snapshots` 参数并放入 payload |

### 4.6 Share to Public（PageInstance 深拷贝）

| 文件 | 变更 |
|------|------|
| `src/common/memory/memory_service.py` | `share_phrase()` 新增 PageInstance 深拷贝逻辑：遍历每个被引用 State 的 PageInstance，deep-copy 到 public，建 `has_instance` 边 |

当前 `share_phrase()` 深拷贝 States、Actions、IntentSequences、Domains，但**完全没有拷贝 PageInstance**。需要在 States 拷贝后增加：

```python
# Copy page instances for each state
if private_wm.page_instance_manager and public_wm.page_instance_manager:
    for old_state_id, state in states.items():
        new_state_id = id_map.get(old_state_id, old_state_id)
        instances = private_wm.page_instance_manager.list_by_state(old_state_id)
        for inst in instances:
            new_inst = inst.model_copy(deep=True)
            new_inst.id = str(uuid.uuid4())
            public_wm.page_instance_manager.create_instance(new_inst)
            public_wm.page_instance_manager.link_to_state(new_state_id, new_inst.id)
```

### 4.7 Legacy 兼容

| 文件 | 变更 |
|------|------|
| `src/cloud_backend/graph_builder/graph_builder.py` | `_update_state_with_event_instance()` 改为收集 PageInstance 而非嵌套到 State |

---

## 5. 关键实现参照

PageInstance 独立节点完全参照 `GraphIntentSequenceManager` 模式：

```
IntentSequence 模式（已有）:
  - 独立节点: intentsequence 表
  - 关系边: has_sequence (State → IntentSequence)
  - Manager: GraphIntentSequenceManager
    - create_sequence() → graph_store.upsert_node()
    - link_to_state() → graph_store.upsert_relationship()
    - list_by_state() → graph_store.query_relationships()
  - 存储顺序: 先存节点，再建边

PageInstance 模式（新增，完全对称）:
  - 独立节点: pageinstance 表
  - 关系边: has_instance (State → PageInstance)
  - Manager: GraphPageInstanceManager
    - create_instance() → graph_store.upsert_node()
    - link_to_state() → graph_store.upsert_relationship()
    - list_by_state() → graph_store.query_relationships()
  - 存储顺序: 先存节点，再建边
```

---

## 6. Snapshot URL 匹配逻辑

WorkflowProcessor 在创建 PageInstance 时，需要从 snapshots dict 中按 URL 匹配 snapshot_text：

```python
def _create_page_instance(self, segment, state_id, session_id, snapshots):
    # snapshots 格式: {url: {url, snapshot/snapshot_text, captured_at}}
    snapshot_text = None
    if snapshots and segment.url in snapshots:
        snapshot_data = snapshots[segment.url]
        snapshot_text = snapshot_data.get("snapshot") or snapshot_data.get("snapshot_text")

    instance = PageInstance(
        url=segment.url,
        page_title=segment.page_title,
        timestamp=segment.timestamp,
        session_id=session_id,
        snapshot_text=snapshot_text,
    )
    instance._parent_state_id = state_id  # 用于 _store_to_memory 建边
    return instance
```

注意 snapshot 有两种来源格式：
- 从 StorageManager.get_recording 加载：`snapshot_data.get("snapshot")` (YAML 存储用 `snapshot:` key)
- 从 BehaviorRecorder 直接传：`snapshot_data.get("snapshot_text")`

---

## 7. 不在本次范围

- PageInstance 的 embedding / 语义搜索
- DOM 快照的版本管理 / 增量更新
- snapshot 内容的压缩存储
