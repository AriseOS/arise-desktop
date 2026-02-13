# Graph Store 双后端支持：Neo4j + SurrealDB

## 概述

Graph Store 模块支持两种持久化后端：
- **Neo4j**: 成熟的图数据库，适合生产环境
- **SurrealDB**: 多模型数据库（文档 + 图 + 向量），新兴选择

两者通过 `GraphStore` 抽象接口统一，配置文件切换即可。

---

## 架构

```
GraphStore (Abstract Interface)
    ├── NetworkXGraph       - In-memory (开发测试)
    ├── Neo4jGraphStore     - Neo4j 持久化 (生产选项 1)
    ├── SurrealDBGraphStore - SurrealDB 持久化 (生产选项 2)
    └── MemoryGraph         - Simple dict-based
```

---

## 配置切换

### 使用 Neo4j

```yaml
# cloud-backend.yaml
graph_store:
  backend: neo4j
  uri: neo4j://localhost:7687
  user: neo4j
  password: your_password
  database: neo4j
```

```bash
# 启动 Neo4j
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password \
  neo4j:5.15
```

### 使用 SurrealDB

```yaml
# cloud-backend.yaml
graph_store:
  backend: surrealdb
  url: ws://localhost:8000/rpc
  namespace: ami
  database: memory
  username: root
  password: your_password
  vector_dimensions: 1024
```

```bash
# 启动 SurrealDB
docker run -d --name surrealdb \
  -p 8000:8000 \
  surrealdb/surrealdb:latest \
  start --user root --pass your_password
```

### 使用 NetworkX (开发)

```yaml
graph_store:
  backend: networkx  # 或直接注释整个 graph_store 段
```

---

## 对比

| 特性 | Neo4j | SurrealDB |
|------|-------|-----------|
| 成熟度 | ⭐⭐⭐⭐⭐ 非常成熟 | ⭐⭐⭐ 较新 |
| 图查询 | Cypher (强大) | SurrealQL (简单) |
| 向量搜索 | 5.11+ 支持 | 原生支持 (HNSW) |
| 复杂类型 | 需 JSON 序列化 | 原生支持 |
| 分布式 | 企业版付费 | TiKV 后端免费 |
| PageRank | GDS 库支持 | 不支持 |
| Python SDK | 成熟 | 较新 |

---

## 文件结构

```
src/cloud_backend/memgraph/graphstore/
├── graph_store.py       # 抽象接口
├── __init__.py          # 工厂函数 (支持 neo4j/surrealdb/networkx/memory)
├── neo4j_graph.py       # Neo4j 实现
├── neo4j_config.py      # Neo4j 配置
├── surrealdb_graph.py   # SurrealDB 实现
├── surrealdb_config.py  # SurrealDB 配置
├── networkx_graph.py    # NetworkX 实现
└── memory_graph.py      # 简单内存实现
```

---

## 代码使用

```python
from src.cloud_backend.memgraph.graphstore import create_graph_store

# 根据配置自动选择
# main.py 已经实现了配置读取逻辑

# 手动选择 Neo4j
store = create_graph_store("neo4j", uri="neo4j://localhost:7687", ...)

# 手动选择 SurrealDB
store = create_graph_store("surrealdb", url="ws://localhost:8000/rpc", ...)

# 两者 API 完全一致
store.initialize_schema()
store.upsert_node("State", {"id": "s1", "name": "test"})
store.vector_search("State", "embedding_vector", query_vec, topk=10)
store.close()
```

---

## 注意事项

1. **不支持运行时切换**: 选择一种后端后，数据存储在该后端，切换需要数据迁移
2. **PageRank**: 只有 Neo4j 支持，SurrealDB 实现为空操作
3. **JSON 序列化**: Neo4j 需要手动处理 `*_json` 字段，SurrealDB 不需要
4. **依赖安装**:
   - Neo4j: `pip install neo4j graphdatascience`
   - SurrealDB: `pip install surrealdb nest-asyncio`

---

## 迁移步骤

### Step 1: 添加依赖

```toml
# pyproject.toml - 移除 neo4j, graphdatascience，添加 surrealdb
dependencies = [
    # 删除: "neo4j>=5.0.0"
    # 删除: "graphdatascience>=1.6"
    "surrealdb>=1.0.0",
]
```

### Step 2: 创建 SurrealDB 配置

新建 `surrealdb_config.py`:

```python
"""SurrealDB configuration."""
import os
from dataclasses import dataclass, field

@dataclass
class SurrealDBConfig:
    url: str = field(default_factory=lambda: os.getenv("SURREALDB_URL", "ws://localhost:8000/rpc"))
    namespace: str = field(default_factory=lambda: os.getenv("SURREALDB_NAMESPACE", "ami"))
    database: str = field(default_factory=lambda: os.getenv("SURREALDB_DATABASE", "memory"))
    username: str = field(default_factory=lambda: os.getenv("SURREALDB_USER", "root"))
    password: str = field(default_factory=lambda: os.getenv("SURREALDB_PASSWORD", "root"))
    vector_dimensions: int = 1024
```

### Step 3: 实现 SurrealDBGraphStore

新建 `surrealdb_graph.py`，实现 `GraphStore` 接口：

#### 3.1 核心结构

```python
"""SurrealDB-based implementation of GraphStore."""
import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple
from surrealdb import Surreal

from src.cloud_backend.memgraph.graphstore.graph_store import GraphStore

logger = logging.getLogger(__name__)


class SurrealDBGraphStore(GraphStore):
    """SurrealDB graph store - 直接替换 Neo4j。"""

    def __init__(
        self,
        url: str,
        namespace: str,
        database: str,
        username: str,
        password: str,
        vector_dimensions: int = 1024,
    ):
        self._url = url
        self._namespace = namespace
        self._database = database
        self._username = username
        self._password = password
        self._vector_dimensions = vector_dimensions
        self._client: Optional[Surreal] = None
        self._connected = False

    def _run(self, coro):
        """Run async coroutine in sync context."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            return asyncio.run(coro)
        return asyncio.run(coro)

    def _ensure_connected(self):
        """Ensure connection is established."""
        if not self._connected:
            self._run(self._connect())

    async def _connect(self):
        """Connect to SurrealDB."""
        self._client = Surreal(self._url)
        await self._client.connect()
        await self._client.signin({"user": self._username, "pass": self._password})
        await self._client.use(self._namespace, self._database)
        self._connected = True
        logger.info(f"Connected to SurrealDB: {self._url}/{self._namespace}/{self._database}")
```

#### 3.2 节点操作

```python
    def upsert_node(
        self,
        label: str,
        properties: Dict[str, Any],
        id_key: str = "id",
        extra_labels: Tuple[str, ...] = ("Entity",),
    ) -> None:
        self._ensure_connected()
        if id_key not in properties:
            raise ValueError(f"Property '{id_key}' not found")

        async def _upsert():
            table = label.lower()
            record_id = f"{table}:`{properties[id_key]}`"
            await self._client.query(
                f"UPSERT {record_id} CONTENT $props",
                {"props": properties}
            )

        self._run(_upsert())

    def upsert_nodes(
        self,
        label: str,
        properties_list: List[Dict[str, Any]],
        id_key: str = "id",
        extra_labels: Tuple[str, ...] = ("Entity",),
    ) -> None:
        for props in properties_list:
            self.upsert_node(label, props, id_key, extra_labels)

    def get_node(
        self,
        label: str,
        id_value: Any,
        id_key: str = "id",
    ) -> Optional[Dict[str, Any]]:
        self._ensure_connected()

        async def _get():
            table = label.lower()
            result = await self._client.query(
                f"SELECT * FROM {table} WHERE {id_key} = $id LIMIT 1",
                {"id": id_value}
            )
            if result and result[0]["result"]:
                return result[0]["result"][0]
            return None

        return self._run(_get())

    def delete_node(
        self,
        label: str,
        id_value: Any,
        id_key: str = "id",
    ) -> bool:
        self._ensure_connected()

        async def _delete():
            table = label.lower()
            await self._client.query(
                f"DELETE FROM {table} WHERE {id_key} = $id",
                {"id": id_value}
            )
            return True

        return self._run(_delete())

    def delete_nodes(
        self,
        label: str,
        id_values: List[Any],
        id_key: str = "id",
    ) -> int:
        self._ensure_connected()

        async def _delete():
            table = label.lower()
            await self._client.query(
                f"DELETE FROM {table} WHERE {id_key} IN $ids",
                {"ids": id_values}
            )
            return len(id_values)

        return self._run(_delete())

    def query_nodes(
        self,
        label: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        self._ensure_connected()

        async def _query():
            table = label.lower()
            query = f"SELECT * FROM {table}"

            params = {}
            if filters:
                conditions = []
                for i, (key, value) in enumerate(filters.items()):
                    param = f"p{i}"
                    conditions.append(f"{key} = ${param}")
                    params[param] = value
                query += " WHERE " + " AND ".join(conditions)

            if limit:
                query += f" LIMIT {limit}"

            result = await self._client.query(query, params)
            return result[0]["result"] if result else []

        return self._run(_query())

    def batch_preprocess_node_properties(
        self,
        node_batch: List[Tuple[str, Dict[str, Any]]],
        extra_labels: Tuple[str, ...] = ("Entity",),
    ) -> List[Tuple[str, Dict[str, Any]]]:
        # SurrealDB 不需要预处理，直接返回
        return node_batch
```

#### 3.3 关系操作

```python
    def upsert_relationship(
        self,
        start_node_label: str,
        start_node_id_value: Any,
        end_node_label: str,
        end_node_id_value: Any,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None,
        upsert_nodes: bool = True,
        start_node_id_key: str = "id",
        end_node_id_key: str = "id",
    ) -> None:
        self._ensure_connected()

        async def _relate():
            start_table = start_node_label.lower()
            end_table = end_node_label.lower()
            rel_table = rel_type.lower()

            query = f"""
                LET $start = (SELECT * FROM {start_table} WHERE {start_node_id_key} = $start_id)[0];
                LET $end = (SELECT * FROM {end_table} WHERE {end_node_id_key} = $end_id)[0];
                RELATE $start->{rel_table}->$end CONTENT $props;
            """
            await self._client.query(query, {
                "start_id": start_node_id_value,
                "end_id": end_node_id_value,
                "props": properties or {},
            })

        self._run(_relate())

    def delete_relationship(
        self,
        start_node_label: str,
        start_node_id_value: Any,
        end_node_label: str,
        end_node_id_value: Any,
        rel_type: str,
        start_node_id_key: str = "id",
        end_node_id_key: str = "id",
    ) -> bool:
        self._ensure_connected()

        async def _delete():
            rel_table = rel_type.lower()
            start_table = start_node_label.lower()
            end_table = end_node_label.lower()

            query = f"""
                DELETE FROM {rel_table}
                WHERE in.{start_node_id_key} = $start_id
                AND out.{end_node_id_key} = $end_id
            """
            await self._client.query(query, {
                "start_id": start_node_id_value,
                "end_id": end_node_id_value,
            })
            return True

        return self._run(_delete())

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
        self._ensure_connected()

        async def _query():
            if not rel_type:
                return []

            rel_table = rel_type.lower()
            query = f"SELECT *, in AS start_node, out AS end_node FROM {rel_table}"

            conditions = []
            params = {}

            if start_node_id_value is not None:
                conditions.append(f"in.{start_node_id_key} = $start_id")
                params["start_id"] = start_node_id_value

            if end_node_id_value is not None:
                conditions.append(f"out.{end_node_id_key} = $end_id")
                params["end_id"] = end_node_id_value

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            result = await self._client.query(query, params)
            if not result or not result[0]["result"]:
                return []

            relationships = []
            for record in result[0]["result"]:
                relationships.append({
                    "start": record.get("start_node", {}),
                    "end": record.get("end_node", {}),
                    "rel": {k: v for k, v in record.items() if k not in ["start_node", "end_node", "in", "out"]},
                })
            return relationships

        return self._run(_query())
```

#### 3.4 索引和搜索

```python
    def create_index(
        self,
        label: str,
        property_key: str,
        index_name: Optional[str] = None,
    ) -> None:
        self._ensure_connected()

        async def _create():
            table = label.lower()
            name = index_name or f"idx_{table}_{property_key}"
            await self._client.query(
                f"DEFINE INDEX {name} ON {table} FIELDS {property_key}"
            )
            logger.info(f"Created index: {name}")

        self._run(_create())

    def create_text_index(
        self,
        labels: List[str],
        property_keys: List[str],
        index_name: Optional[str] = None,
    ) -> None:
        self._ensure_connected()

        async def _create():
            if isinstance(labels, str):
                labels_list = [labels]
            else:
                labels_list = labels

            for label in labels_list:
                table = label.lower()
                for prop in property_keys:
                    name = index_name or f"idx_{table}_{prop}_search"
                    await self._client.query(
                        f"DEFINE INDEX {name} ON {table} FIELDS {prop} SEARCH ANALYZER ascii BM25"
                    )
                    logger.info(f"Created text index: {name}")

        self._run(_create())

    def create_vector_index(
        self,
        label: str,
        property_key: str,
        index_name: Optional[str] = None,
        vector_dimensions: int = 1024,
        metric_type: str = "cosine",
        hnsw_m: Optional[int] = None,
        hnsw_ef_construction: Optional[int] = None,
    ) -> None:
        self._ensure_connected()

        async def _create():
            table = label.lower()
            name = index_name or f"idx_{table}_{property_key}_vec"
            await self._client.query(
                f"DEFINE INDEX {name} ON {table} FIELDS {property_key} "
                f"MTREE DIMENSION {vector_dimensions} DIST COSINE"
            )
            logger.info(f"Created vector index: {name} (dim={vector_dimensions})")

        self._run(_create())

    def delete_index(self, index_name: str) -> None:
        self._ensure_connected()

        async def _delete():
            await self._client.query(f"REMOVE INDEX {index_name}")
            logger.info(f"Deleted index: {index_name}")

        self._run(_delete())

    def text_search(
        self,
        query_string: str,
        label_constraints: Optional[List[str]] = None,
        topk: int = 10,
        index_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        self._ensure_connected()

        async def _search():
            if not label_constraints:
                return []

            results = []
            for label in label_constraints:
                table = label.lower()
                query = f"""
                    SELECT *, search::score(1) AS _score
                    FROM {table}
                    WHERE description @1@ $query
                    ORDER BY _score DESC
                    LIMIT {topk}
                """
                result = await self._client.query(query, {"query": query_string})
                if result and result[0]["result"]:
                    results.extend(result[0]["result"])

            return sorted(results, key=lambda x: x.get("_score", 0), reverse=True)[:topk]

        return self._run(_search())

    def vector_search(
        self,
        label: str,
        property_key: str,
        query_text_or_vector: List[float],
        topk: int = 10,
        index_name: Optional[str] = None,
        ef_search: Optional[int] = None,
    ) -> List[Tuple[Dict[str, Any], float]]:
        self._ensure_connected()

        if isinstance(query_text_or_vector, str):
            raise ValueError("query_text_or_vector must be a list of floats")

        async def _search():
            table = label.lower()
            query = f"""
                SELECT *,
                       vector::similarity::cosine({property_key}, $vec) AS score
                FROM {table}
                WHERE {property_key} <|{topk},COSINE|> $vec
                ORDER BY score DESC
                LIMIT {topk}
            """
            result = await self._client.query(query, {"vec": query_text_or_vector})

            if not result or not result[0]["result"]:
                return []

            return [
                ({k: v for k, v in r.items() if k != "score"}, r.get("score", 0.0))
                for r in result[0]["result"]
            ]

        return self._run(_search())
```

#### 3.5 Schema 和工具方法

```python
    def initialize_schema(self, schema: Any = None) -> None:
        self._ensure_connected()

        async def _init():
            # 定义表
            tables = ["domain", "state", "cognitivephrase", "intentsequence"]
            for table in tables:
                await self._client.query(f"DEFINE TABLE {table} SCHEMALESS")

            # 定义关系表
            rel_tables = ["manages", "has_sequence", "action"]
            for table in rel_tables:
                await self._client.query(f"DEFINE TABLE {table} SCHEMALESS TYPE RELATION")

            # 唯一索引
            for table in tables:
                await self._client.query(
                    f"DEFINE INDEX idx_{table}_id ON {table} FIELDS id UNIQUE"
                )

            # 属性索引
            indexes = [
                ("state", "user_id"),
                ("state", "session_id"),
                ("domain", "user_id"),
                ("cognitivephrase", "user_id"),
                ("intentsequence", "state_id"),
            ]
            for table, field in indexes:
                await self._client.query(
                    f"DEFINE INDEX idx_{table}_{field} ON {table} FIELDS {field}"
                )

            # 向量索引
            vector_tables = ["state", "cognitivephrase", "intentsequence"]
            for table in vector_tables:
                try:
                    await self._client.query(
                        f"DEFINE INDEX idx_{table}_embedding ON {table} "
                        f"FIELDS embedding_vector MTREE DIMENSION {self._vector_dimensions} DIST COSINE"
                    )
                except Exception as e:
                    logger.warning(f"Vector index warning for {table}: {e}")

            logger.info("SurrealDB schema initialized")

        self._run(_init())

    def close(self) -> None:
        if self._client and self._connected:
            self._run(self._client.close())
            self._connected = False
            logger.info("SurrealDB connection closed")

    def clear(self) -> None:
        self._ensure_connected()

        async def _clear():
            tables = ["domain", "state", "cognitivephrase", "intentsequence",
                      "manages", "has_sequence", "action"]
            for table in tables:
                await self._client.query(f"DELETE FROM {table}")
            logger.warning("All data cleared")

        self._run(_clear())

    def get_all_entity_labels(self) -> List[str]:
        self._ensure_connected()

        async def _get():
            result = await self._client.query("INFO FOR DB")
            if result and result[0]["result"]:
                return list(result[0]["result"].get("tables", {}).keys())
            return []

        return self._run(_get())

    def run_script(self, script: str) -> Any:
        self._ensure_connected()

        async def _run_script():
            return await self._client.query(script)

        return self._run(_run_script())

    # PageRank - 不支持，空实现
    def execute_pagerank(self, iterations: int = 20, damping_factor: float = 0.85) -> None:
        logger.info("PageRank not supported in SurrealDB - skipping")

    def get_pagerank_scores(
        self,
        start_nodes: Optional[List[str]] = None,
        target_type: Optional[str] = None,
    ) -> List[Tuple[Dict[str, Any], float]]:
        return []
```

### Step 4: 更新工厂函数

修改 `__init__.py`:

```python
"""Graph storage module."""
from typing import Optional
from src.cloud_backend.memgraph.graphstore.graph_store import GraphStore
from src.cloud_backend.memgraph.graphstore.memory_graph import MemoryGraph
from src.cloud_backend.memgraph.graphstore.networkx_graph import NetworkXGraph


def create_graph_store(
    backend: str = "networkx",
    **kwargs,
) -> GraphStore:
    """Factory function to create GraphStore instance.

    Args:
        backend: Backend type - "networkx", "surrealdb", or "memory"
        **kwargs: Backend-specific configuration

    Returns:
        GraphStore instance
    """
    if backend == "networkx":
        directed = kwargs.get("directed", True)
        return NetworkXGraph(directed=directed)

    elif backend == "surrealdb":
        from src.cloud_backend.memgraph.graphstore.surrealdb_graph import SurrealDBGraphStore
        from src.cloud_backend.memgraph.graphstore.surrealdb_config import SurrealDBConfig

        config = kwargs.get("config")
        if config is None:
            defaults = SurrealDBConfig()
            config = SurrealDBConfig(
                url=kwargs.get("url", defaults.url),
                namespace=kwargs.get("namespace", defaults.namespace),
                database=kwargs.get("database", defaults.database),
                username=kwargs.get("username", defaults.username),
                password=kwargs.get("password", defaults.password),
                vector_dimensions=kwargs.get("vector_dimensions", defaults.vector_dimensions),
            )

        return SurrealDBGraphStore(
            url=config.url,
            namespace=config.namespace,
            database=config.database,
            username=config.username,
            password=config.password,
            vector_dimensions=config.vector_dimensions,
        )

    elif backend == "memory":
        return MemoryGraph()

    else:
        raise ValueError(f"Unknown backend: {backend}. Available: networkx, surrealdb, memory")


__all__ = [
    "GraphStore",
    "MemoryGraph",
    "NetworkXGraph",
    "create_graph_store",
]
```

### Step 5: 删除 Neo4j 文件

```bash
rm src/cloud_backend/memgraph/graphstore/neo4j_graph.py
rm src/cloud_backend/memgraph/graphstore/neo4j_config.py
```

### Step 6: 更新配置文件

修改 `src/cloud_backend/config/cloud-backend.yaml`:

```yaml
# Graph Store Configuration (替换原有 Neo4j 配置)
graph_store:
  backend: surrealdb  # Options: networkx (in-memory), surrealdb (persistent)

  # SurrealDB Configuration
  url: ws://localhost:8000/rpc   # Or use SURREALDB_URL env var
  namespace: ami                  # Or use SURREALDB_NAMESPACE env var
  database: memory                # Or use SURREALDB_DATABASE env var
  username: root                  # Or use SURREALDB_USER env var
  password: your_password         # Or use SURREALDB_PASSWORD env var
  vector_dimensions: 1024
```

### Step 7: 更新 pyproject.toml

```toml
# 删除 Neo4j 依赖
# "neo4j>=5.0.0",        # 删除
# "graphdatascience>=1.6",  # 删除

# 添加 SurrealDB 依赖
"surrealdb>=1.0.0",
"nest-asyncio>=1.6.0",  # 用于异步转同步
```

### Step 8: 更新文档

#### 8.1 更新 `src/cloud_backend/CONTEXT.md`

将 Neo4j 依赖部分替换为:

```markdown
## Dependencies

### SurrealDB (Required for Memory System)

Memory system uses SurrealDB for persistent graph storage.

**Install via Docker:**
```bash
docker run -d --name surrealdb \
  -p 8000:8000 \
  surrealdb/surrealdb:latest \
  start --user root --pass your_password
```

**Configure in `config/cloud-backend.yaml`:**
```yaml
graph_store:
  backend: surrealdb
  url: ws://localhost:8000/rpc
  namespace: ami
  database: memory
  username: root
  password: your_password
```

Or use environment variables:
```bash
export SURREALDB_URL=ws://localhost:8000/rpc
export SURREALDB_NAMESPACE=ami
export SURREALDB_DATABASE=memory
export SURREALDB_USER=root
export SURREALDB_PASSWORD=your_password
```

**Fallback**: Set `backend: networkx` to use in-memory storage (data lost on restart).
```

#### 8.2 更新 `src/cloud_backend/memgraph/CONTEXT.md`

将存储后端部分替换为:

```markdown
## 存储后端

默认使用 **SurrealDB** 持久化存储，支持：
- 持久化（重启不丢数据）
- 向量索引（语义搜索）
- 图查询（关系遍历）
- 原生复杂类型存储（无需 JSON 序列化）

配置见 `cloud-backend.yaml`:
```yaml
graph_store:
  backend: surrealdb  # 或 networkx (内存，重启丢失)
  url: ws://localhost:8000/rpc
  namespace: ami
  database: memory
  username: root
  password: your_password
```
```

#### 8.3 更新 `src/cloud_backend/memgraph/graphstore/CONTEXT.md`

完全重写:

```markdown
# GraphStore Module

Graph storage abstraction layer for the Memory system.

## Purpose

Provides a unified interface (`GraphStore`) for graph data storage with multiple backend implementations.

## Architecture

```
GraphStore (Abstract)
    ├── NetworkXGraph      - In-memory, NetworkX-based (development)
    ├── SurrealDBGraphStore - Persistent, SurrealDB-based (production)
    └── MemoryGraph        - Simple dict-based storage
```

## Key Files

| File | Purpose |
|------|---------|
| `graph_store.py` | Abstract interface definition |
| `networkx_graph.py` | In-memory implementation using NetworkX |
| `surrealdb_graph.py` | SurrealDB persistent storage implementation |
| `surrealdb_config.py` | SurrealDB connection configuration |
| `memory_graph.py` | Simple dict-based storage |
| `vector_index.py` | In-memory vector index |

## Usage

```python
from src.cloud_backend.memgraph.graphstore import create_graph_store

# Development (in-memory)
store = create_graph_store("networkx")

# Production (SurrealDB)
store = create_graph_store("surrealdb")

# With explicit config
store = create_graph_store(
    "surrealdb",
    url="ws://localhost:8000/rpc",
    namespace="ami",
    database="memory",
    username="root",
    password="password",
)
```

## SurrealDB Configuration

Environment variables:
- `SURREALDB_URL` - Connection URL (default: `ws://localhost:8000/rpc`)
- `SURREALDB_NAMESPACE` - Namespace (default: `ami`)
- `SURREALDB_DATABASE` - Database name (default: `memory`)
- `SURREALDB_USER` - Username (default: `root`)
- `SURREALDB_PASSWORD` - Password (required)
- `SURREALDB_VECTOR_DIMENSIONS` - Default vector size (default: `1024`)

## Key Interfaces

### Node Operations
- `upsert_node()`, `get_node()`, `delete_node()`, `query_nodes()`
- `upsert_nodes()`, `delete_nodes()` (batch)

### Relationship Operations
- `upsert_relationship()`, `delete_relationship()`, `query_relationships()`

### Index Operations
- `create_index()`, `create_text_index()`, `create_vector_index()`
- `text_search()`, `vector_search()`

## Data Storage

SurrealDB natively supports complex types - no JSON serialization needed:
- Lists and dicts stored directly
- `embedding_vector` stored as native array
- Relationships use `RELATE` syntax
```

---

## 文件清单

### 新建文件
- `src/cloud_backend/memgraph/graphstore/surrealdb_config.py`
- `src/cloud_backend/memgraph/graphstore/surrealdb_graph.py`

### 修改文件
- `src/cloud_backend/memgraph/graphstore/__init__.py`
- `pyproject.toml` (依赖)
- `src/cloud_backend/config/cloud-backend.yaml`
- `src/cloud_backend/CONTEXT.md`
- `src/cloud_backend/memgraph/CONTEXT.md`
- `src/cloud_backend/memgraph/graphstore/CONTEXT.md`

### 删除文件
- `src/cloud_backend/memgraph/graphstore/neo4j_graph.py`
- `src/cloud_backend/memgraph/graphstore/neo4j_config.py`

---

## 注意事项

1. **异步处理**: SurrealDB SDK 是异步的，用 `asyncio.run()` 包装
2. **ID 格式**: SurrealDB 用 `table:id` 格式，需要适配
3. **不需要 JSON 序列化**: SurrealDB 直接支持复杂类型
4. **PageRank 移除**: 空实现，不影响现有功能

---

## 执行顺序

1. 添加 `surrealdb` 依赖
2. 创建 `surrealdb_config.py`
3. 创建 `surrealdb_graph.py`
4. 修改 `__init__.py`
5. 删除 Neo4j 文件
6. 更新配置文件
7. 测试
