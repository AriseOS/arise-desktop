# SurrealDB API Reference

本文档为 `SurrealDBGraphStore` 实现提供 API 参考。

## Python SDK

### 安装

```bash
pip install surrealdb
```

### 基础用法

```python
from surrealdb import Surreal, AsyncSurreal

# 同步客户端
db = Surreal("ws://localhost:8000/rpc")
db.connect()
db.signin({"user": "root", "pass": "root"})
db.use("namespace", "database")

# 异步客户端
db = AsyncSurreal("ws://localhost:8000/rpc")
await db.connect()
await db.signin({"user": "root", "pass": "root"})
await db.use("namespace", "database")
```

### SDK 方法

| 方法 | 描述 |
|------|------|
| `db.connect()` | 连接到数据库 |
| `db.close()` | 关闭连接 |
| `db.signin(vars)` | 登录认证 |
| `db.use(namespace, database)` | 切换命名空间和数据库 |
| `db.query(sql, vars)` | 执行 SurrealQL 查询 |
| `db.select(thing)` | 查询记录 |
| `db.create(thing, data)` | 创建记录 |
| `db.update(thing, data)` | 更新记录（替换） |
| `db.merge(thing, data)` | 更新记录（合并） |
| `db.delete(thing)` | 删除记录 |

---

## SurrealQL 语句

### UPSERT 语句

插入或更新记录。

```sql
-- 基础语法
UPSERT @targets
    [ CONTENT @value | MERGE @value | SET @field = @value, ... ]
    [ WHERE @condition ]
    [ RETURN NONE | BEFORE | AFTER | DIFF ]
    [ TIMEOUT @duration ];

-- 示例：使用 record ID 插入/更新
UPSERT person:`john` CONTENT { id: "john", name: "John", age: 30 };

-- 示例：使用 SET
UPSERT person:`john` SET name = "John", age = 30;

-- 示例：使用 MERGE（只更新指定字段）
UPSERT person:`john` MERGE { age: 31 };
```

### SELECT 语句

查询记录。

```sql
-- 基础语法
SELECT @fields
FROM @targets
[ WHERE @conditions ]
[ ORDER BY @field [ ASC | DESC ] ]
[ LIMIT @limit ]
[ START @offset ];

-- 示例：查询所有记录
SELECT * FROM person;

-- 示例：条件查询
SELECT * FROM person WHERE age > 18;

-- 示例：查询单条记录
SELECT * FROM person WHERE id = $id LIMIT 1;

-- 示例：分页查询
SELECT * FROM person ORDER BY created_at DESC LIMIT 10 START 20;
```

### DELETE 语句

删除记录。

```sql
-- 基础语法
DELETE [ FROM ] @targets
[ WHERE @condition ]
[ RETURN NONE | BEFORE | AFTER ]
[ TIMEOUT @duration ];

-- 示例：删除单条记录
DELETE person:`john`;

-- 示例：按条件删除
DELETE FROM person WHERE id = $id;

-- 示例：批量删除
DELETE FROM person WHERE id IN $ids;

-- 示例：删除表中所有记录
DELETE FROM person;

-- 示例：删除关系
DELETE FROM wrote WHERE in.id = $start_id AND out.id = $end_id;
```

### RELATE 语句

创建图关系（边）。

```sql
-- 基础语法
RELATE @from -> @table -> @to
    [ CONTENT @value | SET @field = @value, ... ]
    [ RETURN NONE | BEFORE | AFTER ];

-- 示例：创建关系
RELATE person:`john` -> wrote -> article:`post1`;

-- 示例：带属性的关系
RELATE person:`john` -> wrote -> article:`post1`
    SET created_at = time::now(), rating = 5;

-- 示例：使用 CONTENT
RELATE person:`john` -> wrote -> article:`post1`
    CONTENT { created_at: time::now(), rating: 5 };
```

### 图遍历查询

SurrealDB 支持使用箭头操作符进行图遍历，这是其作为图数据库的核心能力。

```sql
-- 正向遍历（outgoing）: ->edge->target
SELECT ->wrote->article FROM person:`john`;

-- 反向遍历（incoming）: <-edge<-source
SELECT <-wrote<-person FROM article:`post1`;

-- 双向遍历（忽略方向）: <->edge<->node
SELECT <->friend<->person FROM person:`john`;

-- 多跳遍历
SELECT ->action->state->action->state FROM state:`home`;

-- 直接从 Record ID 遍历
state:`home`->action->state;
person:`john`.{ name, articles: ->wrote->article };

-- 查询关系表
SELECT * FROM wrote WHERE in.id = $person_id;

-- 带过滤的关系查询
SELECT *, in AS start_node, out AS end_node FROM wrote
WHERE in.id = $start_id;

-- 在遍历中使用 Graph Clauses (v2.2+)
SELECT ->(SELECT * FROM action WHERE type = 'click') AS clicks FROM state;
SELECT ->(action LIMIT 5) AS recent_actions FROM state;
```

### 递归图查询 (v2.1+)

递归查询用于遍历未知深度的图结构，如查找所有可达节点或最短路径。

```sql
-- 指定深度的递归遍历
SELECT
    @.{1}->action->state AS level_1,
    @.{2}->action->state AS level_2,
    @.{3}->action->state AS level_3
FROM state:`home`;

-- 深度范围递归 (1-20 层)
state:`home`.{1..20}->action->state;

-- 收集嵌套结构
SELECT @.{3}.{
    id,
    next_states: ->action->state.@
} FROM state:`home`;

-- 开放式递归（最大 256 层，建议加 TIMEOUT）
SELECT @.{..}.{
    id,
    reachable: ->action->state.@
} FROM state TIMEOUT 1s;
```

### 最短路径查询 (v2.1+)

SurrealDB 内置最短路径算法：

```sql
-- 查找从 state:home 到 state:target 的最短路径
state:`home`.{..+shortest=state:`target`}->action->state;

-- 在 SELECT 中使用
SELECT @.{..+shortest=state:`target`}->action->state AS shortest_path
FROM state:`home`;

-- 查找人际关系最短路径
person:`you`.{..+shortest=person:`celebrity`}->knows->person;
```

### 路径收集与算法

```sql
-- +path: 收集所有可能的路径
state:`home`.{..+path}->action->state;

-- +collect: 收集所有唯一节点（去重）
state:`home`.{..+collect}->action->state;

-- +inclusive: 包含起始节点在结果中
state:`home`.{..+inclusive}->action->state;

-- 组合使用
SELECT @.{1..10+shortest=state:`target`+inclusive}->action->state
FROM state:`home`;
```

### 图模型实际应用示例

基于我们的 Memory Graph 模型（State、Action、IntentSequence）：

```sql
-- 1. 查询某个 State 的所有出边（可到达的 State）
SELECT ->action->state AS reachable_states FROM state:`home_page`;

-- 2. 查询某个 State 的所有入边（能到达此 State 的来源）
SELECT <-action<-state AS source_states FROM state:`product_detail`;

-- 3. 查询某个 State 关联的所有 IntentSequence
SELECT ->has_sequence->intentsequence AS sequences FROM state:`login_page`;

-- 4. 查询某个 Domain 管理的所有 State
SELECT ->manages->state AS managed_states FROM domain:`producthunt.com`;

-- 5. 两个 State 之间的最短路径
state:`home`.{..+shortest=state:`team_page`}->action->state;

-- 6. 查找从首页到目标页面的所有可能路径（限制深度）
SELECT @.{1..5+path}->action->state AS all_paths
FROM state:`home`
TIMEOUT 2s;

-- 7. 收集从某 State 可达的所有唯一 State
SELECT @.{..+collect}->action->state AS all_reachable
FROM state:`home`
TIMEOUT 1s;

-- 8. 带条件的图遍历（只走 click 类型的 Action）
SELECT ->(SELECT * FROM action WHERE type = 'click')->state AS click_paths
FROM state:`home`;

-- 9. 完整的工作流路径查询（包含边属性）
SELECT
    id,
    @.{1..10}.{
        state_id: id,
        actions: ->action.{ type, description },
        next_state: ->action->state.@
    } AS workflow_path
FROM state:`home`;
```

---

## 索引定义

### 普通索引

```sql
-- 基础索引
DEFINE INDEX idx_name ON table FIELDS field;

-- 唯一索引
DEFINE INDEX idx_name ON table FIELDS field UNIQUE;

-- 复合索引
DEFINE INDEX idx_name ON table FIELDS field1, field2;

-- 示例
DEFINE INDEX idx_person_id ON person FIELDS id UNIQUE;
DEFINE INDEX idx_person_user_id ON person FIELDS user_id;
```

### 全文搜索索引

```sql
-- 基础语法
DEFINE ANALYZER @name TOKENIZERS @tokenizers FILTERS @filters;
DEFINE INDEX @name ON @table FIELDS @field
    FULLTEXT ANALYZER @analyzer BM25[(@k1, @b)] [HIGHLIGHTS];

-- 示例：定义分析器
DEFINE ANALYZER ascii_analyzer TOKENIZERS class FILTERS ascii, lowercase;

-- 示例：定义全文索引
DEFINE INDEX idx_description_search ON state FIELDS description
    FULLTEXT ANALYZER ascii_analyzer BM25(1.2, 0.75);
```

### 向量索引 (HNSW)

> **注意**: MTREE 索引已在最新版本中弃用，请使用 HNSW。

```sql
-- 基础语法
DEFINE INDEX @name ON @table FIELDS @field
    HNSW DIMENSION @dim [TYPE @type] [DIST @metric] [EFC @efc] [M @m];

-- 参数说明
-- DIMENSION: 向量维度（必需）
-- TYPE: 数据类型 (F64, F32, I64, I32, I16)，默认 F64
-- DIST: 距离度量 (COSINE, EUCLIDEAN, MANHATTAN, HAMMING, MINKOWSKI)
-- EFC: 构建时探索因子，默认 150
-- M: 每节点最大连接数，默认 12

-- 示例
DEFINE INDEX idx_embedding ON state FIELDS embedding_vector
    HNSW DIMENSION 1024 DIST COSINE;

-- 完整参数示例
DEFINE INDEX idx_embedding ON state FIELDS embedding_vector
    HNSW DIMENSION 1024 TYPE F32 DIST COSINE EFC 150 M 12;
```

### 删除索引

```sql
-- 需要指定表名
REMOVE INDEX @name ON @table;

-- 示例
REMOVE INDEX idx_embedding ON state;
```

---

## 搜索功能

### 全文搜索

```sql
-- 使用 @@ 操作符（需要数字标记用于 score/highlight）
SELECT *, search::score(1) AS score
FROM state
WHERE description @1@ $query
ORDER BY score DESC
LIMIT 10;

-- 多字段搜索
SELECT *,
    search::score(0) AS title_score,
    search::score(1) AS content_score,
    search::score(0) + search::score(1) AS total_score
FROM article
WHERE title @0@ $query OR content @1@ $query
ORDER BY total_score DESC;

-- 高亮显示
SELECT id,
    search::highlight('<b>', '</b>', 1) AS highlighted
FROM state
WHERE description @1@ $query;
```

### 向量搜索 (KNN)

```sql
-- KNN 操作符语法: <|k, METRIC|> 或 <|k, ef_search|>
-- k: 返回数量
-- METRIC: COSINE, EUCLIDEAN, MANHATTAN, HAMMING, MINKOWSKI
-- ef_search: 使用 HNSW 索引时的搜索参数（数字）

-- 精确 KNN 搜索（使用距离度量名称）
SELECT *, vector::distance::knn() AS distance
FROM state
WHERE embedding_vector <|10, COSINE|> $vec
ORDER BY distance ASC;

-- 使用 HNSW 索引的近似搜索（使用 ef_search 数字）
SELECT *, vector::distance::knn() AS distance
FROM state
WHERE embedding_vector <|10, 40|> $vec
ORDER BY distance ASC;

-- 计算相似度（需要单独计算）
SELECT *,
    vector::similarity::cosine(embedding_vector, $vec) AS similarity
FROM state
WHERE embedding_vector <|10, COSINE|> $vec
ORDER BY similarity DESC;
```

### 向量函数

```sql
-- 距离函数
vector::distance::cosine(a, b)      -- 余弦距离
vector::distance::euclidean(a, b)   -- 欧几里得距离
vector::distance::manhattan(a, b)   -- 曼哈顿距离
vector::distance::knn()             -- KNN 查询时计算的距离

-- 相似度函数
vector::similarity::cosine(a, b)    -- 余弦相似度 (0-1)
vector::similarity::jaccard(a, b)   -- Jaccard 相似度
vector::similarity::pearson(a, b)   -- Pearson 相关系数
```

---

## 数据库信息

```sql
-- 获取数据库信息（包含所有表）
INFO FOR DB;

-- 返回格式
{
    "tables": {
        "person": "DEFINE TABLE person SCHEMALESS",
        "article": "DEFINE TABLE article SCHEMALESS"
    },
    "analyzers": {},
    "functions": {},
    ...
}

-- 获取表信息
INFO FOR TABLE person;

-- 获取命名空间信息
INFO FOR NS;
```

---

## 表定义

```sql
-- 普通表
DEFINE TABLE @name SCHEMALESS;

-- 关系表（用于 RELATE）
DEFINE TABLE @name SCHEMALESS TYPE RELATION;

-- 示例
DEFINE TABLE person SCHEMALESS;
DEFINE TABLE wrote SCHEMALESS TYPE RELATION;
```

---

## Record ID 格式

SurrealDB 使用 `table:id` 格式的 Record ID：

```sql
-- 字符串 ID（需要反引号）
person:`john`
person:`user-123`

-- 数字 ID
person:123

-- 复杂 ID
person:`uuid-v4-here`

-- 在查询中使用
SELECT * FROM person:`john`;
UPSERT person:`john` CONTENT { name: "John" };
```

---

## 参数化查询

```python
# Python SDK 中使用参数
result = await db.query(
    "SELECT * FROM person WHERE id = $id",
    {"id": "john"}
)

result = await db.query(
    "UPSERT person:`$id` CONTENT $props",
    {"id": "john", "props": {"name": "John", "age": 30}}
)

result = await db.query(
    "DELETE FROM person WHERE id IN $ids",
    {"ids": ["john", "jane", "bob"]}
)
```

---

## 常见模式

### 批量插入

```sql
-- 使用 INSERT（推荐用于批量操作）
INSERT INTO person [
    { id: "john", name: "John" },
    { id: "jane", name: "Jane" }
];

-- 或循环 UPSERT（Python 中）
for item in items:
    await db.query("UPSERT person:`$id` CONTENT $data",
                   {"id": item["id"], "data": item})
```

### 计数查询

```sql
-- 统计记录数
SELECT count() FROM person GROUP ALL;

-- 返回格式: [{"count": 42}]

-- 按条件统计
SELECT count() FROM person WHERE age > 18 GROUP ALL;
```

### 聚合查询

```sql
-- 多种聚合
SELECT
    count() AS total,
    math::sum(age) AS age_sum,
    math::mean(age) AS age_avg
FROM person
GROUP ALL;
```

---

## 参考资源

- [SurrealDB Python SDK](https://surrealdb.com/docs/sdk/python)
- [SurrealQL Statements](https://surrealdb.com/docs/surrealql/statements)
- [Vector Search Guide](https://surrealdb.com/docs/surrealdb/models/vector)
- [Full-Text Search Guide](https://surrealdb.com/docs/surrealdb/models/full-text-search)
- [DEFINE INDEX](https://surrealdb.com/docs/surrealql/statements/define/indexes)
