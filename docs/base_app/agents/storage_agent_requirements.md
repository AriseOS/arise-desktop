# StorageAgent 需求文档 v1.0

## 1. 概述

StorageAgent 是一个用于持久化数据存储的 Agent，解决 workflow 执行过程中数据持久化的需求。它提供自动 schema 管理和结构化数据存储能力，让用户无需编写 SQL 或手动定义表结构。

### 1.1 核心目标

- **持久化存储**: 数据在 workflow 结束后保留
- **自动 Schema 管理**: 从数据结构自动推断并创建表
- **用户隔离**: 不同用户的数据相互隔离
- **简单易用**: 声明式 YAML 配置，无需了解数据库细节

### 1.2 设计理念

StorageAgent 与 ScraperAgent 形成对称设计：
- **ScraperAgent**: 数据输入（从网页提取数据）
- **StorageAgent**: 数据输出（将数据持久化存储）

## 2. 核心概念

### 2.1 Collection（集合）

**定义**: 一组相关数据的逻辑分组，类似于：
- MongoDB 的 collection
- SQL 数据库的 table（但无需预定义 schema）
- 文件系统的文件夹

**命名规范**:
- 使用小写字母和下划线：`scraped_products`, `product_reviews`
- 具有描述性：反映数据类型
- 避免 SQL 关键字：如 `order`, `select`, `table`

**示例**:
```yaml
collection: "scraped_products"    # ✅ 好
collection: "product_reviews"     # ✅ 好
collection: "price_history"       # ✅ 好
```

### 2.2 Schema 管理（简化版）

**核心原则**：
- Schema 由第一次存储确定，之后**固定不变**
- 不支持 Schema 演化（不支持 ALTER TABLE 添加新字段）
- 字段必须严格匹配，否则报错
- 保持简单，避免复杂的 schema 管理

**首次存储（Generate Script）**:
1. **Plan**: 分析数据结构，推断 schema（字段名和类型）
2. **Generate**: 生成 INSERT SQL 并缓存
3. **Execute**:
   - 创建表（CREATE TABLE，直接执行，不缓存）
   - 插入数据（INSERT，使用缓存的 script）

**后续存储（Execute Script）**:
1. 从 Memory 加载缓存的 INSERT script
2. 验证数据字段与 schema 匹配
3. 直接执行 INSERT 语句

**Schema 规则**:
- Collection + user_id → 唯一表名（如 `products_alice`）
- Schema 由第一次存储确定，之后不可改变
- 字段不匹配报错（缺少字段、多余字段、类型错误）

**Script 缓存**:

系统缓存三种操作的 SQL script 到 Memory（KV Storage）：

**INSERT Script**:
```python
cache_key = f"storage_insert_{collection}_{user_id}"
```

**QUERY Script**:
```python
cache_key = f"storage_query_{collection}_{user_id}_{filters_hash}"
```

**EXPORT Script**:
```python
cache_key = f"storage_export_{collection}_{user_id}_{filters_hash}_{format}"
```

首次执行时生成并缓存 script，后续执行直接使用缓存。

### 2.3 数据隔离

**实现方式**:
- 每个用户拥有独立的表：`{collection}_{user_id}`
- 不需要 `user_id` 字段，通过表名天然隔离
- 更简单、更安全

**示例**:
```sql
-- 用户 alice 的表
CREATE TABLE products_alice (
    id INTEGER PRIMARY KEY,
    name TEXT,
    price REAL,
    created_at TEXT NOT NULL
);

-- 用户 bob 的表（独立表结构）
CREATE TABLE products_bob (
    id INTEGER PRIMARY KEY,
    name TEXT,
    price REAL,
    created_at TEXT NOT NULL
);

-- 用户输入
collection: "products"
user_id: "alice"

-- 系统自动映射到表
table_name = f"products_alice"

-- 查询时直接查询对应表
SELECT * FROM products_alice;  -- 天然隔离
```

## 3. 基本使用场景

### 3.1 场景：爬取商品并持久化存储

**需求**: 用户每天运行爬虫，将商品数据存储到数据库

**Workflow**:
```yaml
steps:
  - id: "scrape-product"
    agent_type: "scraper_agent"
    inputs:
      target_path: "https://example.com/product/123"
      data_requirements:
        output_format:
          name: "商品名称"
          price: "价格"
          rating: "评分"
    outputs:
      extracted_data: "product_detail"

  - id: "save-product"
    agent_type: "storage_agent"
    inputs:
      operation: "store"
      collection: "scraped_products"
      data: "{{product_detail}}"
```

**第一次运行（Generate Script）**:
- Plan: 推断 schema `{name: TEXT, price: REAL, rating: REAL}`
- Generate: 生成 SQL script（CREATE TABLE + INSERT）
- Cache: 缓存 script 到 Memory（key: `storage_script_scraped_products_alice`）
- Execute: 创建表 `scraped_products_alice` 并插入数据
- 输出: `"Stored 1 record to collection 'scraped_products'"`

**第二天运行（Execute Script）**:
- 从 Memory 加载缓存的 script
- 直接执行 INSERT 语句
- 数据累积：总记录数增加

### 3.2 场景：查询历史数据

**需求**: 用户想查询最近 7 天爬取的商品

**Workflow**:
```yaml
steps:
  - id: "query-recent-products"
    agent_type: "storage_agent"
    inputs:
      operation: "query"
      collection: "scraped_products"
      filters:
        created_at: {">=": "2025-09-24"}
      limit: 10
    outputs:
      results: "recent_products"

  - id: "show-results"
    agent_type: "text_agent"
    inputs:
      prompt: "总结这些商品: {{recent_products}}"
```

**执行结果**:
```yaml
recent_products: [
  {name: "Coffee", price: 45.99, created_at: "2025-10-01"},
  {name: "Tea", price: 29.99, created_at: "2025-09-30"},
  # ... 更多记录
]
```

### 3.3 场景：导出数据到 CSV

**需求**: 用户想导出所有商品数据到 CSV 文件

**Workflow**:
```yaml
steps:
  - id: "export-products"
    agent_type: "storage_agent"
    inputs:
      operation: "export"
      collection: "scraped_products"
      format: "csv"
      output_path: "./exports/products.csv"
```

**执行结果**:
- 生成文件 `./exports/products.csv`
- 包含所有字段和当前用户的所有数据

## 4. 输入输出规格

### 4.1 Store 操作

**输入格式**:
```yaml
inputs:
  operation: "store"                    # 必需: 操作类型
  collection: "string"                  # 必需: 集合名称
  data: "dict | list[dict]"             # 必需: 要存储的数据
```

**字段说明**:
- `operation`: 固定为 `"store"`
- `collection`: 集合名称，如 `"scraped_products"`
- `data`: 要存储的数据
  - 单个对象: `{name: "Coffee", price: 45.99}`
  - 对象数组: `[{name: "Coffee", price: 45.99}, {name: "Tea", price: 29.99}]`

**示例**:
```yaml
- id: "save-product"
  agent_type: "storage_agent"
  inputs:
    operation: "store"
    collection: "scraped_products"
    data:
      name: "Coffee Lavazza"
      price: 45.99
      rating: 4.5
```

**输出格式**:
```yaml
outputs:
  success: true
  message: "Stored 1 record to collection 'scraped_products'"
  operation: "store"
  collection: "scraped_products"
  rows_stored: 1
  schema_created: false    # true 表示首次创建表，false 表示表已存在
```

### 4.2 Query 操作

**输入格式**:
```yaml
inputs:
  operation: "query"                    # 必需: 操作类型
  collection: "string"                  # 必需: 集合名称
  filters: "dict"                       # 可选: 查询过滤条件
  limit: "integer"                      # 可选: 限制结果数量
  order_by: "string"                    # 可选: 排序字段
```

**过滤条件语法**:
```yaml
filters:
  # 简单相等
  name: "Coffee"

  # 比较操作符
  price: {"<": 50}
  rating: {">": 4.0}
  price: {">=": 30, "<": 50}

  # 时间范围
  created_at: {">=": "2025-09-24", "<": "2025-10-01"}
```

**示例**:
```yaml
- id: "query-products"
  agent_type: "storage_agent"
  inputs:
    operation: "query"
    collection: "scraped_products"
    filters:
      price: {"<": 50}
      rating: {">": 4.0}
    limit: 10
    order_by: "price ASC"
  outputs:
    results: "filtered_products"
```

**输出格式**:
```yaml
outputs:
  success: true
  message: "Retrieved 10 records from collection 'scraped_products'"
  operation: "query"
  collection: "scraped_products"
  total_count: 10
  data: [
    {
      id: 1,
      name: "Coffee Lavazza",
      price: 45.99,
      rating: 4.5,
      created_at: "2025-10-01 14:30:00"
    },
    # ... 更多记录
  ]
```

### 4.3 Export 操作

**输入格式**:
```yaml
inputs:
  operation: "export"                   # 必需: 操作类型
  collection: "string"                  # 必需: 集合名称
  format: "csv | excel | json"          # 必需: 导出格式
  output_path: "string"                 # 必需: 输出文件路径
  filters: "dict"                       # 可选: 过滤要导出的数据
```

**示例**:
```yaml
- id: "export-to-csv"
  agent_type: "storage_agent"
  inputs:
    operation: "export"
    collection: "scraped_products"
    format: "csv"
    output_path: "./exports/products.csv"
    filters:
      created_at: {">=": "2025-09-01"}
```

**输出格式**:
```yaml
outputs:
  success: true
  message: "Exported 50 records to ./exports/products.csv"
  operation: "export"
  collection: "scraped_products"
  format: "csv"
  output_path: "./exports/products.csv"
  rows_exported: 50
```

## 5. Schema 管理细节

### 5.1 数据类型映射

| Python 类型 | SQLite 类型 | 示例 |
|-------------|-------------|------|
| `str` | TEXT | `"Coffee"` |
| `int` | INTEGER | `100` |
| `float` | REAL | `45.99` |
| `bool` | INTEGER | `True` → `1`, `False` → `0` |
| `dict` | TEXT | `{"key": "value"}` → JSON 字符串 |
| `list` | TEXT | `[1, 2, 3]` → JSON 字符串 |
| `None` | NULL | `None` |

### 5.2 系统字段

每个 collection 自动包含以下系统字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PRIMARY KEY | 自增唯一 ID |
| `created_at` | TEXT NOT NULL | 数据创建时间戳 |

注意：不需要 `user_id` 字段，因为通过表名 `{collection}_{user_id}` 已经实现了用户隔离。

### 5.3 字段验证示例

**第一次存储**:
```yaml
collection: "products"
data: {name: "Coffee", price: 45.99}
```
创建表 `products_alice`，schema 固定为 `{name: TEXT, price: REAL}`。

**第二次存储（字段匹配）**:
```yaml
data: {name: "Tea", price: 29.99}
```
✅ 字段匹配，正常插入。

**第三次存储（缺少字段）**:
```yaml
data: {name: "Juice"}  # 缺少 price
```
❌ 报错：`Missing required field 'price'`

**第四次存储（多余字段）**:
```yaml
data: {name: "Milk", price: 15.99, rating: 4.5}  # 多了 rating
```
❌ 报错：`Extra field 'rating' not in schema`

**第五次存储（类型错误）**:
```yaml
data: {name: "Juice", price: "20 dollars"}  # price 是字符串！
```
报错:
```yaml
outputs:
  success: false
  error: "Type mismatch for field 'price': expected REAL, got TEXT"
  suggestion: "Ensure data type consistency for field 'price'"
```

### 5.4 Script 缓存详情

所有 script 缓存到 Memory（KV Storage）：

**INSERT Script 缓存**:
```python
cache_key = f"storage_insert_{collection}_{user_id}"
cache_data = {
    "table_name": "products_alice",
    "schema": {"name": "TEXT", "price": "REAL"},
    "insert_sql": "INSERT INTO products_alice (name, price, created_at) VALUES (?, ?, ?)",
    "field_order": ["name", "price"]
}
```

**QUERY Script 缓存**:
```python
import hashlib
filters_hash = hashlib.md5(json.dumps(filters, sort_keys=True).encode()).hexdigest()[:8]
cache_key = f"storage_query_{collection}_{user_id}_{filters_hash}"

cache_data = {
    "table_name": "products_alice",
    "query_sql": "SELECT * FROM products_alice WHERE price < ? AND rating > ? LIMIT ?",
    "params_order": [("price", "<"), ("rating", ">"), ("limit", None)]
}
```

**EXPORT Script 缓存**:
```python
cache_key = f"storage_export_{collection}_{user_id}_{filters_hash}_{format}"
cache_data = {
    "table_name": "products_alice",
    "query_sql": "SELECT * FROM products_alice WHERE created_at >= ?",
    "params_order": [("created_at", ">=")],
    "format": "csv"
}
```

## 6. Workflow 集成模式

### 6.1 基本存储模式

```yaml
steps:
  - id: "scrape"
    agent_type: "scraper_agent"
    outputs:
      extracted_data: "product"

  - id: "save"
    agent_type: "storage_agent"
    inputs:
      operation: "store"
      collection: "products"
      data: "{{product}}"
```

### 6.2 批量存储模式

```yaml
steps:
  - id: "scrape-list"
    agent_type: "scraper_agent"
    outputs:
      extracted_data: "products_list"  # 返回数组

  - id: "save-batch"
    agent_type: "storage_agent"
    inputs:
      operation: "store"
      collection: "products"
      data: "{{products_list}}"  # 批量存储
```

### 6.3 循环存储模式

```yaml
steps:
  - id: "scrape-urls"
    agent_type: "scraper_agent"
    outputs:
      extracted_data: "product_urls"

  - id: "foreach-product"
    agent_type: "foreach"
    source: "{{product_urls}}"
    steps:
      - id: "scrape-detail"
        agent_type: "scraper_agent"
        inputs:
          target_path: "{{item.url}}"
        outputs:
          extracted_data: "product_detail"

      - id: "save-product"
        agent_type: "storage_agent"
        inputs:
          operation: "store"
          collection: "products"
          data: "{{product_detail}}"
```

### 6.4 查询和分析模式

```yaml
steps:
  - id: "query-data"
    agent_type: "storage_agent"
    inputs:
      operation: "query"
      collection: "products"
      filters:
        price: {"<": 50}
      limit: 10
    outputs:
      results: "cheap_products"

  - id: "analyze"
    agent_type: "code_agent"
    inputs:
      data: "{{cheap_products}}"
      instruction: "Calculate average price"
```

### 6.5 导出模式

```yaml
steps:
  - id: "export"
    agent_type: "storage_agent"
    inputs:
      operation: "export"
      collection: "products"
      format: "csv"
      output_path: "./exports/products_{{date}}.csv"
```

## 7. 用户使用流程

### 7.1 首次使用

**步骤 1**: 编写 workflow
```yaml
- id: "save"
  agent_type: "storage_agent"
  inputs:
    operation: "store"
    collection: "my_products"
    data: {name: "Coffee", price: 45.99}
```

**步骤 2**: 运行 workflow
```bash
python run_workflow.py my-workflow --user-id alice
```

**步骤 3**: 系统自动（Generate Script）
- Plan: 推断 schema `{name: TEXT, price: REAL}`
- Generate: 生成 CREATE TABLE + INSERT SQL
- Cache: 缓存 script 到 Memory (key: `storage_script_my_products_alice`)
- Execute: 创建表 `my_products_alice` 并插入数据

**步骤 4**: 输出
```
✅ Stored 1 record to collection 'my_products'
✅ Schema created automatically
```

### 7.2 第二天使用

**步骤 1**: 再次运行相同 workflow
```bash
python run_workflow.py my-workflow --user-id alice
```

**步骤 2**: 系统自动
- 从 `_storage_schemas` 读取 schema
- 验证数据兼容性
- 直接插入数据

**步骤 3**: 输出
```
✅ Stored 1 record to collection 'my_products'
✅ Total records: 2
```

### 7.3 查询数据

```bash
python run_workflow.py query-workflow --user-id alice
```

输出:
```json
{
  "success": true,
  "total_count": 2,
  "data": [
    {"name": "Coffee", "price": 45.99, "created_at": "2025-10-01"},
    {"name": "Coffee", "price": 45.99, "created_at": "2025-10-02"}
  ]
}
```

## 8. 实现总结

### 8.1 核心特性

1. **自动 Schema 管理**
   - 从数据推断类型
   - 自动创建表
   - 支持 schema 演化
   - Schema 存储在数据库

2. **三个基本操作**
   - Store: 存储数据
   - Query: 查询数据
   - Export: 导出数据

3. **用户隔离**
   - 通过表名隔离（{collection}_{user_id}）
   - 每个用户独立的表
   - 不需要 user_id 字段

4. **Workflow 集成**
   - 声明式 YAML 配置
   - 清晰的输入输出
   - 支持变量引用

### 8.2 适用场景

**适合**:
- ✅ 定期爬虫数据存储
- ✅ 历史数据追踪
- ✅ 简单查询和导出
- ✅ 用户独立数据管理

**不适合**:
- ❌ 高频写入（> 100 次/秒）
- ❌ 复杂关联查询（JOIN）
- ❌ 大文件存储（图片、视频）

本需求文档定义了 StorageAgent v1.0 的最小可行版本，聚焦核心功能，后续可根据实际使用逐步扩展。
