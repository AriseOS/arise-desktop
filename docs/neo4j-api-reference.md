# Neo4j Python API Reference

本文档记录项目中使用的 Neo4j Python API 接口，作为 `Neo4jGraphStore` 实现的参考。

## 1. 依赖安装

```bash
# 核心驱动
pip install neo4j

# 可选：Rust 扩展（3-10x 性能提升）
pip install neo4j-rust-ext

# 可选：图数据科学库（PageRank 等算法）
pip install graphdatascience
```

**版本要求**:
- `neo4j` >= 5.0 (当前最新 6.1.0)
- Python >= 3.10
- Neo4j Server >= 5.11 (向量索引支持)

---

## 2. 连接管理

### 2.1 Driver 创建

```python
from neo4j import GraphDatabase

# 本地连接
driver = GraphDatabase.driver(
    "neo4j://localhost:7687",
    auth=("neo4j", "password"),
    max_connection_pool_size=100,      # 连接池大小
    connection_timeout=30,              # TCP 连接超时(秒)
    max_connection_lifetime=3600,       # 连接最大生命周期(秒)
)

# 验证连接
driver.verify_connectivity()

# 关闭
driver.close()
```

### 2.2 Session 管理

```python
# Session 是轻量级的，每个工作单元创建一个
with driver.session(database="neo4j") as session:
    # 工作内容
    pass
```

**关键点**:
- `Driver` 是线程安全的，应用全局共享
- `Session` 不是线程安全的，每个线程/任务创建独立的

---

## 3. 事务模式

### 3.1 托管事务（推荐）

自动重试瞬时错误：

```python
def create_node(tx, label, properties):
    result = tx.run(
        f"CREATE (n:{label} $props) RETURN n",
        props=properties
    )
    return result.single()

def get_nodes(tx, label, filters):
    result = tx.run(
        f"MATCH (n:{label}) WHERE n.id = $id RETURN n",
        id=filters.get("id")
    )
    return [record["n"] for record in result]

with driver.session(database="neo4j") as session:
    # 写操作
    session.execute_write(create_node, "Person", {"name": "Alice"})

    # 读操作
    session.execute_read(get_nodes, "Person", {"id": "123"})
```

### 3.2 简单执行

```python
# 直接执行查询
records, summary, keys = driver.execute_query(
    "MATCH (n:Person) RETURN n LIMIT 10",
    database_="neo4j"
)
```

---

## 4. CRUD 操作 Cypher

### 4.1 节点操作

```cypher
-- 创建/更新节点 (MERGE = upsert)
MERGE (n:State {id: $id})
SET n = $properties
RETURN n

-- 获取节点
MATCH (n:State {id: $id})
RETURN n

-- 删除节点
MATCH (n:State {id: $id})
DETACH DELETE n

-- 查询节点（带过滤）
MATCH (n:State)
WHERE n.user_id = $user_id AND n.session_id = $session_id
RETURN n
LIMIT $limit
```

### 4.2 关系操作

```cypher
-- 创建/更新关系
MATCH (a:State {id: $source_id})
MATCH (b:State {id: $target_id})
MERGE (a)-[r:ACTION]->(b)
SET r = $properties
RETURN r

-- 查询关系
MATCH (a:State)-[r:ACTION]->(b:State)
WHERE a.id = $source_id
RETURN a, r, b

-- 删除关系
MATCH (a:State {id: $source_id})-[r:ACTION]->(b:State {id: $target_id})
DELETE r
```

### 4.3 批量操作

```cypher
-- 批量创建节点
UNWIND $nodes AS node
MERGE (n:State {id: node.id})
SET n = node

-- 批量创建关系
UNWIND $relationships AS rel
MATCH (a:State {id: rel.source})
MATCH (b:State {id: rel.target})
MERGE (a)-[r:ACTION]->(b)
SET r = rel.properties
```

---

## 5. 索引管理

### 5.1 属性索引

```cypher
-- 创建唯一约束（自带索引）
CREATE CONSTRAINT state_id IF NOT EXISTS
FOR (s:State) REQUIRE s.id IS UNIQUE

-- 创建普通索引
CREATE INDEX state_user_id IF NOT EXISTS
FOR (s:State) ON (s.user_id)

-- 复合索引
CREATE INDEX state_user_session IF NOT EXISTS
FOR (s:State) ON (s.user_id, s.session_id)
```

### 5.2 全文索引

```cypher
-- 创建全文索引
CREATE FULLTEXT INDEX state_fulltext IF NOT EXISTS
FOR (s:State)
ON EACH [s.description, s.page_title]

-- 全文搜索
CALL db.index.fulltext.queryNodes('state_fulltext', $query)
YIELD node, score
RETURN node, score
LIMIT $limit
```

### 5.3 向量索引（Neo4j 5.11+）

```cypher
-- 创建向量索引
CREATE VECTOR INDEX state_embedding IF NOT EXISTS
FOR (s:State)
ON s.embedding_vector
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 768,
        `vector.similarity_function`: 'cosine'
    }
}

-- 向量搜索
CALL db.index.vector.queryNodes('state_embedding', $k, $query_vector)
YIELD node, score
RETURN node, score

-- 查看索引
SHOW VECTOR INDEXES

-- 删除索引
DROP INDEX state_embedding
```

---

## 6. 图算法 (GDS)

### 6.1 连接 GDS

```python
from graphdatascience import GraphDataScience

gds = GraphDataScience("neo4j://localhost:7687", auth=("neo4j", "password"))
```

### 6.2 图投影

```python
# 投影图到内存
G, result = gds.graph.project(
    "workflow_graph",           # 图名称
    ["State", "Domain"],        # 节点标签
    ["ACTION", "MANAGES"]       # 关系类型
)
```

### 6.3 PageRank

```python
# 流式返回（不修改数据库）
pagerank_df = gds.pageRank.stream(
    G,
    maxIterations=20,
    dampingFactor=0.85
)
# 返回 pandas DataFrame: nodeId, score

# 写入数据库
gds.pageRank.write(
    G,
    writeProperty="pagerank",
    maxIterations=20,
    dampingFactor=0.85
)
```

### 6.4 清理

```python
G.drop()  # 删除投影图
gds.close()
```

---

## 7. 错误处理

### 7.1 异常类型

```python
from neo4j.exceptions import (
    Neo4jError,          # 服务器错误基类
    DriverError,         # 客户端错误基类
    TransientError,      # 瞬时错误（可重试）
    SessionExpired,      # Session 过期
    ServiceUnavailable,  # 无法连接
    AuthError,           # 认证失败
)
```

### 7.2 错误处理模式

```python
from neo4j.exceptions import Neo4jError, ServiceUnavailable

try:
    with driver.session(database="neo4j") as session:
        result = session.execute_write(lambda tx: tx.run(...))
except ServiceUnavailable:
    # 数据库不可用，考虑重试或降级
    raise
except Neo4jError as e:
    if e.is_retryable():
        # 托管事务会自动重试
        pass
    raise
```

---

## 8. 项目中使用的接口汇总

| GraphStore 方法 | Neo4j API | Cypher |
|----------------|-----------|--------|
| `__init__` | `GraphDatabase.driver()` | - |
| `close` | `driver.close()` | - |
| `upsert_node` | `session.execute_write()` | `MERGE (n:Label {id: $id}) SET n = $props` |
| `get_node` | `session.execute_read()` | `MATCH (n:Label {id: $id}) RETURN n` |
| `delete_node` | `session.execute_write()` | `MATCH (n:Label {id: $id}) DETACH DELETE n` |
| `query_nodes` | `session.execute_read()` | `MATCH (n:Label) WHERE ... RETURN n` |
| `upsert_relationship` | `session.execute_write()` | `MATCH ... MERGE (a)-[r:TYPE]->(b) SET r = $props` |
| `delete_relationship` | `session.execute_write()` | `MATCH ...-[r]->... DELETE r` |
| `query_relationships` | `session.execute_read()` | `MATCH (a)-[r]->(b) WHERE ... RETURN a, r, b` |
| `create_vector_index` | `driver.execute_query()` | `CREATE VECTOR INDEX ...` |
| `vector_search` | `session.execute_read()` | `CALL db.index.vector.queryNodes(...)` |
| `create_text_index` | `driver.execute_query()` | `CREATE FULLTEXT INDEX ...` |
| `text_search` | `session.execute_read()` | `CALL db.index.fulltext.queryNodes(...)` |
| `execute_pagerank` | `gds.pageRank.write()` | GDS API |
| `get_pagerank_scores` | `session.execute_read()` | `MATCH (n) RETURN n.pagerank` |

---

## 9. 配置参考

### 9.1 环境变量

```bash
NEO4J_URI=neo4j://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
NEO4J_DATABASE=neo4j
```

### 9.2 连接池配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_connection_pool_size` | 100 | 最大连接数 |
| `connection_timeout` | 30 | TCP 连接超时(秒) |
| `max_connection_lifetime` | 3600 | 连接最大生命周期(秒) |
| `connection_acquisition_timeout` | 60 | 等待连接超时(秒) |

---

## 参考链接

- [Neo4j Python Driver Manual](https://neo4j.com/docs/python-manual/current/)
- [Neo4j Cypher Manual](https://neo4j.com/docs/cypher-manual/current/)
- [Neo4j Vector Indexes](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/)
- [Neo4j GDS Python Client](https://neo4j.com/docs/graph-data-science-client/current/)
