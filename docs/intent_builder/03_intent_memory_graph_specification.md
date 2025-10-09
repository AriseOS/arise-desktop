# IntentMemoryGraph 规范文档

**版本**: v2.0
**日期**: 2025-10-09
**状态**: 已确定

---

## 1. 概述

### 1.1 定义

**IntentMemoryGraph（意图记忆图）** 是存储和管理所有学习到的 Intent 的数据结构。

- **职责**: 存储 Intent 节点和它们之间的连接关系
- **用途**: 支持 Intent 的检索和复用
- **实现**: MVP 使用内存数据结构 + JSON 文件持久化

### 1.2 核心功能

1. **存储**: 添加和管理 Intent 节点
2. **连接**: 记录 Intent 之间的执行顺序
3. **检索**: 基于语义相似度检索相关 Intent
4. **持久化**: 保存和加载 Graph 到文件

---

## 2. 数据结构定义

### 2.1 核心结构

```python
from typing import Dict, List, Tuple
from datetime import datetime
import json

class IntentMemoryGraph:
    """Intent 记忆图"""

    def __init__(self):
        # 节点存储
        self.intents: Dict[str, Intent] = {}  # id -> Intent

        # 边存储（有向边）
        self.edges: List[Tuple[str, str]] = []  # [(from_id, to_id), ...]

        # 元数据
        self.created_at: datetime = datetime.now()
        self.last_updated: datetime = datetime.now()
```

### 2.2 字段说明

#### `intents: Dict[str, Intent]`

**用途**: 存储所有 Intent 节点

**键**: Intent ID
**值**: Intent 对象

**示例**:
```python
intents = {
    "intent_a3f5b2c1": Intent(
        id="intent_a3f5b2c1",
        description="导航到 Allegro 首页",
        operations=[...],
        created_at=...,
        source_session_id="session_001"
    ),
    "intent_b7e4c8d2": Intent(
        id="intent_b7e4c8d2",
        description="进入咖啡分类页面",
        operations=[...],
        created_at=...,
        source_session_id="session_001"
    )
}
```

#### `edges: List[Tuple[str, str]]`

**用途**: 记录 Intent 之间的连接关系

**格式**: (from_intent_id, to_intent_id) 元组列表

**语义**: from_intent 执行后，执行 to_intent（时间顺序）

**示例**:
```python
edges = [
    ("intent_a3f5b2c1", "intent_b7e4c8d2"),  # 导航首页 → 进入分类
    ("intent_b7e4c8d2", "intent_c9f2d5e3"),  # 进入分类 → 提取数据
]
```

**注意**: MVP 不记录边的权重（频率），未来可扩展

---

## 3. 核心方法

### 3.1 写入操作

#### `add_intent(intent: Intent) -> None`

**功能**: 添加一个 Intent 到图中

**行为**:
- 如果 Intent ID 已存在：覆盖（MVP 不去重）
- 更新 `last_updated` 时间

**示例**:
```python
graph = IntentMemoryGraph()

intent = Intent(
    id="intent_a3f5b2c1",
    description="导航到 Allegro 首页",
    operations=[...],
    created_at=datetime.now(),
    source_session_id="session_001"
)

graph.add_intent(intent)
```

#### `add_edge(from_id: str, to_id: str) -> None`

**功能**: 添加一条边（Intent 之间的连接）

**行为**:
- 添加 (from_id, to_id) 到 edges 列表
- MVP 不检查重复（允许重复边）
- 更新 `last_updated` 时间

**示例**:
```python
graph.add_edge("intent_a3f5b2c1", "intent_b7e4c8d2")
graph.add_edge("intent_b7e4c8d2", "intent_c9f2d5e3")
```

**未来扩展**: 记录边的权重（执行次数）

---

### 3.2 读取操作

#### `get_intent(intent_id: str) -> Intent | None`

**功能**: 根据 ID 获取 Intent

**返回**: Intent 对象，如果不存在返回 None

**示例**:
```python
intent = graph.get_intent("intent_a3f5b2c1")
if intent:
    print(intent.description)
```

#### `get_all_intents() -> List[Intent]`

**功能**: 获取所有 Intent

**返回**: Intent 列表

**示例**:
```python
all_intents = graph.get_all_intents()
print(f"Total intents: {len(all_intents)}")
```

#### `get_successors(intent_id: str) -> List[Intent]`

**功能**: 获取某个 Intent 的后继节点

**返回**: 后继 Intent 列表

**示例**:
```python
# 获取 intent_a3f5b2c1 的后继节点
successors = graph.get_successors("intent_a3f5b2c1")
# [Intent(id="intent_b7e4c8d2", ...)]
```

**实现**:
```python
def get_successors(self, intent_id: str) -> List[Intent]:
    """获取后继节点"""
    successor_ids = [to_id for from_id, to_id in self.edges if from_id == intent_id]
    return [self.intents[id] for id in successor_ids if id in self.intents]
```

---

### 3.3 检索操作

#### `retrieve_similar(query: str, limit: int = 5) -> List[Intent]`

**功能**: 基于语义相似度检索相关 Intent

**输入**:
- query: 用户查询（自然语言）
- limit: 返回的最大数量

**返回**: 按相似度排序的 Intent 列表

**算法**:
1. 计算查询的 embedding
2. 计算所有 Intent 描述的 embedding
3. 计算余弦相似度
4. 过滤低相似度（< 0.6）
5. 排序并返回 top-K

**注意**: 此方法需要依赖外部的 EmbeddingService

**示例**（伪代码）:
```python
class IntentMemoryGraph:
    def __init__(self, embedding_service):
        self.intents = {}
        self.edges = []
        self.embedding = embedding_service

    async def retrieve_similar(self, query: str, limit: int = 5) -> List[Intent]:
        """检索相似 Intent"""
        # 计算查询 embedding
        query_embedding = await self.embedding.embed(query)

        # 计算所有 Intent 的相似度
        scored = []
        for intent in self.intents.values():
            intent_embedding = await self.embedding.embed(intent.description)
            similarity = cosine_similarity(query_embedding, intent_embedding)

            if similarity > 0.6:  # 相似度阈值
                scored.append((similarity, intent))

        # 排序并返回 top-K
        scored.sort(key=lambda x: x[0], reverse=True)
        return [intent for _, intent in scored[:limit]]
```

---

### 3.4 持久化操作

#### `save(filepath: str) -> None`

**功能**: 保存 Graph 到 JSON 文件

**格式**:
```json
{
  "intents": {
    "intent_a3f5b2c1": {
      "id": "intent_a3f5b2c1",
      "description": "导航到 Allegro 首页",
      "operations": [...],
      "created_at": "2025-10-09T12:30:00",
      "source_session_id": "session_001"
    },
    ...
  },
  "edges": [
    ["intent_a3f5b2c1", "intent_b7e4c8d2"],
    ["intent_b7e4c8d2", "intent_c9f2d5e3"]
  ],
  "metadata": {
    "created_at": "2025-10-09T12:00:00",
    "last_updated": "2025-10-09T12:35:00",
    "version": "2.0"
  }
}
```

**示例**:
```python
graph.save("intent_graph.json")
```

**实现注意**:
- Intent 对象需要序列化为 dict
- datetime 需要转换为 ISO 格式字符串
- operations 需要完整保存

#### `@staticmethod load(filepath: str) -> IntentMemoryGraph`

**功能**: 从 JSON 文件加载 Graph

**返回**: IntentMemoryGraph 对象

**示例**:
```python
graph = IntentMemoryGraph.load("intent_graph.json")
print(f"Loaded {len(graph.intents)} intents")
```

**实现注意**:
- 反序列化 Intent 对象
- 解析 datetime 字符串
- 重建 operations 列表

---

## 4. 使用流程

### 4.1 学习流程（添加 Intent）

```python
from datetime import datetime

# 1. 创建 Graph
graph = IntentMemoryGraph()

# 2. 提取 Intent（从 User Operations）
intent1 = Intent(
    id="intent_a3f5b2c1",
    description="导航到 Allegro 首页",
    operations=[...],
    created_at=datetime.now(),
    source_session_id="session_001"
)

intent2 = Intent(
    id="intent_b7e4c8d2",
    description="进入咖啡分类页面",
    operations=[...],
    created_at=datetime.now(),
    source_session_id="session_001"
)

# 3. 添加到 Graph
graph.add_intent(intent1)
graph.add_intent(intent2)

# 4. 添加连接关系
graph.add_edge(intent1.id, intent2.id)

# 5. 保存
graph.save("intent_graph.json")

print(f"Graph saved with {len(graph.intents)} intents")
```

### 4.2 检索流程（复用 Intent）

```python
# 1. 加载 Graph
graph = IntentMemoryGraph.load("intent_graph.json")

# 2. 用户查询
user_query = "我想爬取图书分类的商品信息"

# 3. 检索相似 Intent
similar_intents = await graph.retrieve_similar(user_query, limit=5)

# 4. 展示结果
for intent in similar_intents:
    print(f"- {intent.description}")

# 5. 使用检索到的 Intent 生成 MetaFlow
# (由 MetaFlowGenerator 负责)
```

---

## 5. 边的语义

### 5.1 当前语义：时间顺序

**含义**: from_intent 执行后，执行 to_intent

**用途**:
- 记录 Intent 的执行顺序
- 支持路径查询（未来）
- 支持高频路径推荐（未来）

**示例**:
```
intent1 (导航首页) → intent2 (进入分类) → intent3 (提取数据)
```

**注意**: MVP 边没有额外属性（无权重、无标签）

### 5.2 未来扩展：边的属性

```python
@dataclass
class Edge:
    from_id: str
    to_id: str
    frequency: int = 1       # 执行次数
    context: str = ""        # 上下文信息（可选）
    created_at: datetime
```

**用途**:
- 记录高频路径
- 推荐常用的 Intent 组合
- 支持路径优化

---

## 6. MVP 范围

### 包含功能

1. ✅ 存储 Intent 节点
2. ✅ 记录 Intent 之间的边（时间顺序）
3. ✅ 基本的读取操作（get_intent, get_all_intents, get_successors）
4. ✅ 语义相似度检索（retrieve_similar）
5. ✅ JSON 文件持久化（save, load）

### 不包含功能

1. ❌ Intent 去重/合并
2. ❌ 边的权重记录
3. ❌ 高频路径推荐
4. ❌ 图的可视化
5. ❌ 数据库持久化（SQLite, Neo4j）
6. ❌ 索引优化（标签索引、embedding 缓存）

---

## 7. 完整示例

### 7.1 创建和填充 Graph

```python
from datetime import datetime

# 创建 Graph
graph = IntentMemoryGraph()

# Intent 1: 导航
intent1 = Intent(
    id="intent_a3f5b2c1",
    description="导航到 Allegro 电商网站首页",
    operations=[
        Operation(type="navigate", url="https://allegro.pl/", ...)
    ],
    created_at=datetime.now(),
    source_session_id="session_001"
)

# Intent 2: 进入分类
intent2 = Intent(
    id="intent_b7e4c8d2",
    description="通过菜单导航进入咖啡产品分类页面",
    operations=[
        Operation(type="click", ...),
        Operation(type="click", ...),
        Operation(type="navigate", ...)
    ],
    created_at=datetime.now(),
    source_session_id="session_001"
)

# Intent 3: 提取数据
intent3 = Intent(
    id="intent_c9f2d5e3",
    description="访问产品详情页，提取产品的标题、价格、销量信息",
    operations=[
        Operation(type="navigate", ...),
        Operation(type="select", ...),
        Operation(type="copy_action", ...),
        ...
    ],
    created_at=datetime.now(),
    source_session_id="session_001"
)

# 添加到 Graph
graph.add_intent(intent1)
graph.add_intent(intent2)
graph.add_intent(intent3)

# 添加边
graph.add_edge(intent1.id, intent2.id)  # 导航 → 进入分类
graph.add_edge(intent2.id, intent3.id)  # 进入分类 → 提取数据

# 保存
graph.save("coffee_collection_intent_graph.json")
```

### 7.2 加载和检索

```python
# 加载 Graph
graph = IntentMemoryGraph.load("coffee_collection_intent_graph.json")

print(f"Loaded graph with {len(graph.intents)} intents and {len(graph.edges)} edges")

# 检索相似 Intent
query = "我想爬取图书分类的商品信息"
similar_intents = await graph.retrieve_similar(query, limit=3)

print(f"\n检索到 {len(similar_intents)} 个相似的 Intent:")
for i, intent in enumerate(similar_intents, 1):
    print(f"{i}. {intent.description}")
    print(f"   Operations: {len(intent.operations)} steps")
```

### 7.3 遍历路径

```python
# 获取某个 Intent 的后继
start_intent_id = "intent_a3f5b2c1"
successors = graph.get_successors(start_intent_id)

print(f"\nIntent '{start_intent_id}' 的后继节点:")
for successor in successors:
    print(f"- {successor.description}")
```

---

## 8. 设计决策记录

### 为什么使用 List[Tuple] 而不是 Dict 存储边？

**原因**: 允许重复边（未来记录频率）

**优势**:
- 简单：List append 即可
- 灵活：未来可扩展为 Dict[Tuple, EdgeMeta]
- 符合图的语义：多次执行同一路径

### 为什么 MVP 不实现去重？

**原因**: 去重需要语义相似度计算，增加复杂度

**优势**:
- 简化 MVP 实现
- 先验证核心流程
- 未来迭代时再优化

### 为什么使用 JSON 而不是数据库？

**原因**: MVP 数据量小，JSON 足够

**优势**:
- 简单：无需配置数据库
- 人类可读：便于调试
- 跨平台：无依赖

**未来**: 数据量大时可迁移到 SQLite/Neo4j

---

## 9. 性能考虑

### 9.1 当前性能特征

- **存储**: O(1) 添加 Intent 和边
- **检索**: O(N) 遍历所有 Intent（N = Intent 数量）
- **持久化**: O(N) 序列化和反序列化

### 9.2 性能瓶颈（未来）

当 Intent 数量增长到 1000+ 时：
- 检索变慢（需要遍历所有 Intent）
- embedding 计算耗时

### 9.3 优化方向（未来迭代）

1. **Embedding 缓存**: 预计算并缓存所有 Intent 的 embedding
2. **向量数据库**: 使用 Faiss/Chroma 加速相似度检索
3. **索引优化**: 为常用查询建立索引
4. **数据库迁移**: 使用 SQLite/PostgreSQL 替代 JSON

---

## 10. 参考资料

- Intent 规范: `intent_specification.md`
- 讨论记录: `discussions/04_intent_architecture_decisions.md`
- 系统设计: `design_overview.md`
- IntentExtractor 设计: `intent_extractor_design.md`
