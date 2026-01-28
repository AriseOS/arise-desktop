# Neo4j GraphStore 设计文档

## 1. 概述

### 1.1 目标

实现 `Neo4jGraphStore` 类，作为 `GraphStore` 抽象接口的 Neo4j 后端实现，为 Memory 系统提供持久化存储能力。

### 1.2 当前架构

```
┌─────────────────────────────────────────────────────────────┐
│                    WorkflowMemory                            │
├─────────────────────────────────────────────────────────────┤
│  GraphDomainManager / GraphStateManager / GraphActionManager │
├─────────────────────────────────────────────────────────────┤
│                   GraphStore (抽象接口)                       │
├─────────────────────────────────────────────────────────────┤
│               NetworkXGraph (内存实现)                        │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 目标架构

```
┌─────────────────────────────────────────────────────────────┐
│                    WorkflowMemory                            │
├─────────────────────────────────────────────────────────────┤
│  GraphDomainManager / GraphStateManager / GraphActionManager │
├─────────────────────────────────────────────────────────────┤
│                   GraphStore (抽象接口)                       │
├──────────────────────┬──────────────────────────────────────┤
│  NetworkXGraph       │  Neo4jGraphStore (新增)               │
│  (内存/开发)         │  (生产/持久化)                        │
└──────────────────────┴──────────────────────────────────────┘
```

### 1.4 收益

| 方面 | NetworkXGraph | Neo4jGraphStore |
|------|--------------|-----------------|
| 持久化 | ❌ 重启丢失 | ✅ 磁盘持久化 |
| 并发 | ❌ 单线程 | ✅ 多用户并发 |
| 事务 | ❌ 无 | ✅ ACID |
| 向量搜索 | ⚠️ 手动实现 | ✅ 原生向量索引 |
| 图算法 | ✅ NetworkX | ✅ GDS (更强大) |
| 扩展性 | ⚠️ 内存限制 | ✅ 可扩展 |

---

## 2. 数据模型映射

### 2.1 节点类型

| Ontology | Neo4j Label | 主键 | 索引 |
|----------|-------------|------|------|
| Domain | `:Domain` | `id` | unique constraint |
| State | `:State` | `id` | unique constraint, vector index |
| CognitivePhrase | `:CognitivePhrase` | `id` | unique constraint, vector index |

### 2.2 关系类型

| Ontology | Neo4j Type | 方向 |
|----------|------------|------|
| Action | `:ACTION_{type}` | `(State)-[:ACTION_CLICK]->(State)` |
| Manage | `:MANAGES` | `(Domain)-[:MANAGES]->(State)` |

### 2.3 属性存储

复杂属性使用 JSON 序列化：

```python
# State.instances (List[PageInstance])
# 存储为 JSON 字符串
state.instances_json = json.dumps([inst.to_dict() for inst in instances])

# State.intent_sequences (List[IntentSequence])
state.intent_sequences_json = json.dumps([seq.to_dict() for seq in sequences])

# embedding_vector (List[float])
# Neo4j 原生支持 float[]，直接存储
state.embedding_vector = [0.1, 0.2, ...]
```

### 2.4 Schema 定义

```cypher
-- 约束
CREATE CONSTRAINT domain_id IF NOT EXISTS FOR (d:Domain) REQUIRE d.id IS UNIQUE;
CREATE CONSTRAINT state_id IF NOT EXISTS FOR (s:State) REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT phrase_id IF NOT EXISTS FOR (p:CognitivePhrase) REQUIRE p.id IS UNIQUE;

-- 属性索引
CREATE INDEX state_user_id IF NOT EXISTS FOR (s:State) ON (s.user_id);
CREATE INDEX state_session_id IF NOT EXISTS FOR (s:State) ON (s.session_id);
CREATE INDEX domain_user_id IF NOT EXISTS FOR (d:Domain) ON (d.user_id);

-- 向量索引
CREATE VECTOR INDEX state_embedding IF NOT EXISTS
FOR (s:State) ON s.embedding_vector
OPTIONS { indexConfig: { `vector.dimensions`: 768, `vector.similarity_function`: 'cosine' } };

CREATE VECTOR INDEX phrase_embedding IF NOT EXISTS
FOR (p:CognitivePhrase) ON p.embedding_vector
OPTIONS { indexConfig: { `vector.dimensions`: 768, `vector.similarity_function`: 'cosine' } };

-- 全文索引
CREATE FULLTEXT INDEX state_fulltext IF NOT EXISTS
FOR (s:State) ON EACH [s.description, s.page_title, s.page_url];
```

---

## 3. 类设计

### 3.1 Neo4jGraphStore 类

```python
class Neo4jGraphStore(GraphStore):
    """Neo4j-based implementation of GraphStore.

    Provides persistent graph storage with ACID transactions,
    native vector indexing, and graph algorithms via GDS.

    Thread-safety:
        - The driver is thread-safe and shared
        - Sessions are created per-operation
    """

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: str = "neo4j",
        max_connection_pool_size: int = 50,
        connection_timeout: float = 30.0,
        vector_dimensions: int = 768,
    ):
        """Initialize Neo4j connection.

        Args:
            uri: Neo4j connection URI (e.g., "neo4j://localhost:7687")
            user: Username
            password: Password
            database: Database name (default: "neo4j")
            max_connection_pool_size: Connection pool size
            connection_timeout: Connection timeout in seconds
            vector_dimensions: Embedding vector dimensions (default: 768)
        """

    def close(self) -> None:
        """Close the driver and release resources."""

    def initialize_schema(self, schema: Any = None) -> None:
        """Initialize database schema (constraints, indexes)."""
```

### 3.2 方法实现概览

#### 节点操作

```python
def upsert_node(
    self,
    label: str,
    properties: Dict[str, Any],
    id_key: str = "id",
) -> None:
    """Insert or update a node using MERGE."""

def get_node(
    self,
    label: str,
    id_value: Any,
    id_key: str = "id",
) -> Optional[Dict[str, Any]]:
    """Get a node by label and ID."""

def delete_node(
    self,
    label: str,
    id_value: Any,
    id_key: str = "id",
) -> bool:
    """Delete a node and its relationships."""

def query_nodes(
    self,
    label: str,
    filters: Optional[Dict[str, Any]] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Query nodes with optional filters."""
```

#### 关系操作

```python
def upsert_relationship(
    self,
    start_node_label: str,
    start_node_id_value: Any,
    end_node_label: str,
    end_node_id_value: Any,
    rel_type: str,
    properties: Optional[Dict[str, Any]] = None,
    start_node_id_key: str = "id",
    end_node_id_key: str = "id",
) -> None:
    """Create or update a relationship."""

def query_relationships(
    self,
    start_node_label: Optional[str] = None,
    start_node_id_value: Optional[Any] = None,
    end_node_label: Optional[str] = None,
    end_node_id_value: Optional[Any] = None,
    rel_type: Optional[str] = None,
    start_node_id_key: str = "id",
    end_node_id_key: str = "id",
) -> List[Dict[str, Any]]:
    """Query relationships with optional filters."""
```

#### 索引和搜索

```python
def create_vector_index(
    self,
    label: str,
    property_key: str,
    index_name: Optional[str] = None,
    vector_dimensions: int = 768,
    metric_type: str = "cosine",
) -> None:
    """Create a vector index."""

def vector_search(
    self,
    label: str,
    property_key: str,
    query_vector: List[float],
    topk: int = 10,
    index_name: Optional[str] = None,
) -> List[Tuple[Dict[str, Any], float]]:
    """Search nodes by vector similarity."""

def create_text_index(
    self,
    labels: List[str],
    property_keys: List[str],
    index_name: Optional[str] = None,
) -> None:
    """Create a fulltext index."""

def text_search(
    self,
    query_string: str,
    label_constraints: Optional[List[str]] = None,
    topk: int = 10,
    index_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Execute fulltext search."""
```

#### 图算法

```python
def execute_pagerank(
    self,
    iterations: int = 20,
    damping_factor: float = 0.85,
) -> None:
    """Execute PageRank and store scores on nodes."""

def get_pagerank_scores(
    self,
    label: Optional[str] = None,
    limit: int = 10,
) -> List[Tuple[Dict[str, Any], float]]:
    """Get nodes with their PageRank scores."""
```

---

## 4. 实现细节

### 4.1 属性序列化

复杂类型需要序列化：

```python
# 序列化配置
SERIALIZED_PROPERTIES = {
    "instances",           # List[PageInstance]
    "intent_sequences",    # List[IntentSequence]
    "intents",            # List[Intent]
    "state_path",         # List[str]
    "action_path",        # List[str]
    "visit_timestamps",   # List[int]
}

def _serialize_properties(self, properties: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize complex properties to JSON strings."""
    result = {}
    for key, value in properties.items():
        if key in SERIALIZED_PROPERTIES and isinstance(value, list):
            # 序列化列表
            result[f"{key}_json"] = json.dumps(value, default=str)
        elif key == "embedding_vector" and value is not None:
            # embedding 直接存储（Neo4j 支持 float[]）
            result[key] = value
        else:
            result[key] = value
    return result

def _deserialize_properties(self, properties: Dict[str, Any]) -> Dict[str, Any]:
    """Deserialize JSON strings back to objects."""
    result = {}
    for key, value in properties.items():
        if key.endswith("_json"):
            original_key = key[:-5]  # 移除 _json 后缀
            result[original_key] = json.loads(value)
        else:
            result[key] = value
    return result
```

### 4.2 事务处理

```python
def _execute_write(self, work_func, *args, **kwargs):
    """Execute a write transaction with automatic retry."""
    with self._driver.session(database=self._database) as session:
        return session.execute_write(work_func, *args, **kwargs)

def _execute_read(self, work_func, *args, **kwargs):
    """Execute a read transaction."""
    with self._driver.session(database=self._database) as session:
        return session.execute_read(work_func, *args, **kwargs)
```

### 4.3 批量操作

使用 UNWIND 优化批量写入：

```python
def upsert_nodes(
    self,
    nodes: List[Tuple[str, Dict[str, Any]]],
    id_key: str = "id",
) -> None:
    """Batch upsert nodes using UNWIND."""
    # 按 label 分组
    by_label = defaultdict(list)
    for label, props in nodes:
        by_label[label].append(self._serialize_properties(props))

    for label, props_list in by_label.items():
        self._execute_write(
            lambda tx, label, props_list: tx.run(
                f"""
                UNWIND $nodes AS node
                MERGE (n:{label} {{{id_key}: node.{id_key}}})
                SET n = node
                """,
                nodes=props_list
            ),
            label, props_list
        )
```

### 4.4 向量搜索实现

```python
def vector_search(
    self,
    label: str,
    property_key: str,
    query_vector: List[float],
    topk: int = 10,
    index_name: Optional[str] = None,
) -> List[Tuple[Dict[str, Any], float]]:
    """Search nodes by vector similarity using Neo4j vector index."""

    if index_name is None:
        index_name = f"{label.lower()}_{property_key}"

    def _search(tx):
        result = tx.run(
            """
            CALL db.index.vector.queryNodes($index_name, $k, $query_vector)
            YIELD node, score
            RETURN node, score
            """,
            index_name=index_name,
            k=topk,
            query_vector=query_vector,
        )
        return [
            (self._deserialize_properties(dict(record["node"])), record["score"])
            for record in result
        ]

    return self._execute_read(_search)
```

### 4.5 PageRank 实现（可选 GDS）

两种实现方式：

**方式 1：使用 GDS（推荐，需要安装 GDS 插件）**

```python
def execute_pagerank(self, iterations: int = 20, damping_factor: float = 0.85):
    """Execute PageRank using Neo4j GDS."""
    from graphdatascience import GraphDataScience

    gds = GraphDataScience(self._uri, auth=(self._user, self._password))

    # 投影图
    G, _ = gds.graph.project(
        "workflow_graph",
        ["State"],
        {"ACTION": {"orientation": "NATURAL"}}
    )

    # 执行 PageRank 并写入
    gds.pageRank.write(
        G,
        writeProperty="pagerank",
        maxIterations=iterations,
        dampingFactor=damping_factor,
    )

    G.drop()
    gds.close()
```

**方式 2：纯 Cypher（无需 GDS）**

```python
def execute_pagerank(self, iterations: int = 20, damping_factor: float = 0.85):
    """Execute PageRank using pure Cypher (fallback)."""
    # 简化版 PageRank，适用于小图
    self._execute_write(
        lambda tx: tx.run(
            """
            // 初始化
            MATCH (n:State)
            SET n.pagerank = 1.0 / count(n)
            WITH count(n) AS nodeCount

            // 迭代（简化版，实际应用建议使用 GDS）
            UNWIND range(1, $iterations) AS i
            MATCH (n:State)
            OPTIONAL MATCH (m:State)-[:ACTION]->(n)
            WITH n, nodeCount,
                 CASE WHEN count(m) > 0
                      THEN sum(m.pagerank / size((m)-[:ACTION]->()))
                      ELSE 0
                 END AS incomingRank
            SET n.pagerank = (1 - $damping) / nodeCount + $damping * incomingRank
            """,
            iterations=iterations,
            damping=damping_factor,
        )
    )
```

---

## 5. 配置管理

### 5.1 环境变量

```python
# src/cloud_backend/memgraph/graphstore/neo4j_config.py

import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class Neo4jConfig:
    """Neo4j connection configuration."""

    uri: str = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    user: str = os.getenv("NEO4J_USER", "neo4j")
    password: str = os.getenv("NEO4J_PASSWORD", "")
    database: str = os.getenv("NEO4J_DATABASE", "neo4j")
    max_pool_size: int = int(os.getenv("NEO4J_MAX_POOL_SIZE", "50"))
    connection_timeout: float = float(os.getenv("NEO4J_CONNECTION_TIMEOUT", "30.0"))
    vector_dimensions: int = int(os.getenv("NEO4J_VECTOR_DIMENSIONS", "768"))

    @classmethod
    def from_env(cls) -> "Neo4jConfig":
        """Create config from environment variables."""
        return cls()

    def validate(self) -> None:
        """Validate configuration."""
        if not self.password:
            raise ValueError("NEO4J_PASSWORD is required")
```

### 5.2 工厂函数

```python
# src/cloud_backend/memgraph/graphstore/__init__.py

def create_graph_store(backend: str = "networkx", **kwargs) -> GraphStore:
    """Factory function to create GraphStore instance.

    Args:
        backend: "networkx" or "neo4j"
        **kwargs: Backend-specific configuration

    Returns:
        GraphStore instance
    """
    if backend == "networkx":
        from .networkx_graph import NetworkXGraph
        return NetworkXGraph(**kwargs)
    elif backend == "neo4j":
        from .neo4j_graph import Neo4jGraphStore
        from .neo4j_config import Neo4jConfig

        config = kwargs.get("config") or Neo4jConfig.from_env()
        return Neo4jGraphStore(
            uri=config.uri,
            user=config.user,
            password=config.password,
            database=config.database,
            max_connection_pool_size=config.max_pool_size,
            connection_timeout=config.connection_timeout,
            vector_dimensions=config.vector_dimensions,
        )
    else:
        raise ValueError(f"Unknown backend: {backend}")
```

---

## 6. 迁移方案

### 6.1 数据迁移

使用现有的 `export_memory()` / `import_memory()` 方法：

```python
from src.cloud_backend.memgraph.memory.workflow_memory import WorkflowMemory
from src.cloud_backend.memgraph.graphstore import create_graph_store

# 1. 从 NetworkX 导出
old_store = create_graph_store("networkx")
old_memory = WorkflowMemory(old_store)
data = old_memory.export_memory()

# 2. 导入到 Neo4j
new_store = create_graph_store("neo4j")
new_store.initialize_schema()
new_memory = WorkflowMemory(new_store)
new_memory.import_memory(data)
```

### 6.2 双写模式（可选）

渐进式迁移，同时写入两个后端：

```python
class DualWriteGraphStore(GraphStore):
    """Write to both backends for migration period."""

    def __init__(self, primary: GraphStore, secondary: GraphStore):
        self._primary = primary
        self._secondary = secondary

    def upsert_node(self, label, properties, id_key="id"):
        self._primary.upsert_node(label, properties, id_key)
        try:
            self._secondary.upsert_node(label, properties, id_key)
        except Exception as e:
            logging.warning(f"Secondary write failed: {e}")

    # ... 其他方法类似
```

---

## 7. 测试策略

### 7.1 单元测试

```python
# tests/test_neo4j_graph.py

import pytest
from src.cloud_backend.memgraph.graphstore.neo4j_graph import Neo4jGraphStore

@pytest.fixture
def neo4j_store():
    """Create Neo4j store for testing."""
    store = Neo4jGraphStore(
        uri="neo4j://localhost:7687",
        user="neo4j",
        password="test_password",
        database="test",
    )
    store.initialize_schema()
    yield store
    # 清理测试数据
    store._execute_write(lambda tx: tx.run("MATCH (n) DETACH DELETE n"))
    store.close()

def test_upsert_and_get_node(neo4j_store):
    neo4j_store.upsert_node("State", {"id": "s1", "description": "Test"})
    node = neo4j_store.get_node("State", "s1")
    assert node is not None
    assert node["description"] == "Test"

def test_vector_search(neo4j_store):
    # 创建带 embedding 的节点
    neo4j_store.upsert_node("State", {
        "id": "s1",
        "embedding_vector": [0.1] * 768,
    })

    # 搜索
    results = neo4j_store.vector_search(
        "State", "embedding_vector",
        query_vector=[0.1] * 768,
        topk=5,
    )
    assert len(results) == 1
    assert results[0][0]["id"] == "s1"
```

### 7.2 集成测试

```python
def test_workflow_memory_with_neo4j():
    """Test WorkflowMemory with Neo4j backend."""
    store = create_graph_store("neo4j")
    memory = WorkflowMemory(store)

    # 创建 State
    state = State(
        page_url="https://example.com",
        page_title="Example",
        user_id="user1",
    )
    assert memory.create_state(state)

    # 查询
    retrieved = memory.get_state(state.id)
    assert retrieved is not None
    assert retrieved.page_url == "https://example.com"
```

---

## 8. 实施计划

### Phase 1: 核心实现 (1.5d)

- [ ] 创建 `neo4j_graph.py` 基础框架
- [ ] 实现节点 CRUD: `upsert_node`, `get_node`, `delete_node`, `query_nodes`
- [ ] 实现关系 CRUD: `upsert_relationship`, `delete_relationship`, `query_relationships`
- [ ] 实现属性序列化/反序列化
- [ ] 实现 `initialize_schema()`

### Phase 2: 索引和搜索 (1d)

- [ ] 实现 `create_vector_index`, `vector_search`
- [ ] 实现 `create_text_index`, `text_search`
- [ ] 实现 `create_index`, `delete_index`

### Phase 3: 图算法和完善 (0.5d)

- [ ] 实现 `execute_pagerank`, `get_pagerank_scores`
- [ ] 实现批量操作: `upsert_nodes`, `delete_nodes`, `upsert_relationships`
- [ ] 实现 `get_all_entity_labels`, `run_script`

### Phase 4: 配置和集成 (0.5d)

- [ ] 创建 `neo4j_config.py`
- [ ] 更新 `__init__.py` 添加工厂函数
- [ ] 添加环境变量配置
- [ ] 编写单元测试

---

## 9. 文件结构

```
src/cloud_backend/memgraph/graphstore/
├── __init__.py           # 添加工厂函数
├── graph_store.py        # 抽象接口（不变）
├── networkx_graph.py     # 内存实现（不变）
├── neo4j_graph.py        # 新增：Neo4j 实现
└── neo4j_config.py       # 新增：配置管理

docs/
├── neo4j-api-reference.md      # Neo4j API 文档
└── neo4j-graphstore-design.md  # 本设计文档
```

---

## 10. 风险和缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Neo4j 不可用 | 服务中断 | 保留 NetworkX 作为 fallback |
| 向量索引性能 | 搜索慢 | 合理配置 vector.dimensions |
| GDS 未安装 | PageRank 不可用 | 提供纯 Cypher fallback |
| 数据迁移失败 | 数据丢失 | 先备份，使用双写模式 |
