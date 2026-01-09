# StorageAgent 设计文档 v1.0

## 1. 系统架构

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    StorageAgent                        │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────┐ │
│  │  Unified Entry  │  │  Script Cache   │  │  SQLite  │ │
│  │    (execute)    │  │   (Memory KV)   │  │ Storage  │ │
│  └─────────────────┘  └─────────────────┘  └──────────┘ │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │         LLM Script Generator                     │   │
│  │  (Generate CREATE TABLE / INSERT / SELECT SQL)  │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 1.2 核心设计理念

**参考 ScraperAgent 的 Plan-Generate-Execute 模式**:
- **Plan**: 分析数据结构和查询需求
- **Generate**: LLM 生成 SQL 脚本（CREATE TABLE / INSERT / SELECT）
- **Execute**: 缓存并执行 SQL 脚本

**LLM 生成优势**:
- 自动推断最优数据类型
- 智能处理复杂查询条件
- 支持自然语言查询描述
- 代码简洁，无需手写 SQL 生成逻辑

### 1.3 核心组件

**StorageAgent**:
- 继承自 `BaseStepAgent`
- 统一的 `execute()` 入口
- 支持三种操作：store, query, export
- 使用 LLM 生成所有 SQL 脚本

## 2. Script 缓存机制

### 2.1 Script 类型和命名

**INSERT Script**:
```python
cache_key = f"storage_insert_{collection}_{user_id}"
# Example: "storage_insert_products_alice"
```

**QUERY Script**:
```python
import hashlib
query_config = {
    "filters": filters,
    "order_by": order_by,
    "limit": limit
}
config_hash = hashlib.md5(
    json.dumps(query_config, sort_keys=True).encode()
).hexdigest()[:8]

cache_key = f"storage_query_{collection}_{user_id}_{config_hash}"
# Example: "storage_query_products_alice_a3f8b2c1"
```

**EXPORT Script**:
```python
export_config = {
    "filters": filters,
    "format": format
}
config_hash = hashlib.md5(
    json.dumps(export_config, sort_keys=True).encode()
).hexdigest()[:8]

cache_key = f"storage_export_{collection}_{user_id}_{config_hash}"
# Example: "storage_export_products_alice_b7d4e9f2_csv"
```

### 2.2 Script 缓存内容

**INSERT Script Cache**:
```python
{
    "table_name": "products_alice",
    "create_table_sql": "CREATE TABLE IF NOT EXISTS products_alice (...)",
    "insert_sql": "INSERT INTO products_alice (name, price, created_at) VALUES (?, ?, ?)",
    "field_order": ["name", "price"]
}
```

**QUERY Script Cache**:
```python
{
    "table_name": "products_alice",
    "query_sql": "SELECT * FROM products_alice WHERE price < ? AND rating > ? LIMIT ?",
    "params_order": ["price", "rating", "limit"]
}
```

**EXPORT Script Cache**:
```python
{
    "table_name": "products_alice",
    "query_sql": "SELECT * FROM products_alice WHERE created_at >= ?",
    "params_order": ["created_at"],
    "format": "csv"
}
```

## 3. 详细设计

### 3.1 StorageAgent 主类

```python
class StorageAgent(BaseStepAgent):
    """
    Storage Agent for persistent data storage using LLM-generated SQL

    Supports three operations:
    - store: Insert data into collection
    - query: Query data with filters
    - export: Export data to CSV/Excel/JSON
    """

    SYSTEM_PROMPT_SCHEMA = """You are a SQLite schema expert. Generate CREATE TABLE statement based on data structure.

Rules:
1. Table name: {table_name}
2. Always include: id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL
3. Infer optimal SQLite types from data
4. Return ONLY the CREATE TABLE SQL, no explanations
5. Use IF NOT EXISTS clause"""

    SYSTEM_PROMPT_INSERT = """You are a SQL expert. Generate INSERT statement for the table.

Rules:
1. Table name: {table_name}
2. Fields: {fields}
3. Return ONLY the INSERT SQL with placeholders (?), no explanations
4. Example: INSERT INTO table_name (field1, field2, created_at) VALUES (?, ?, ?)"""

    SYSTEM_PROMPT_QUERY = """You are a SQL query expert. Generate SELECT statement based on requirements.

Rules:
1. Table name: {table_name}
2. Return ONLY the SELECT SQL with placeholders (?), no explanations
3. Use parameterized queries for security
4. Return parameter order as comment at end"""

    def __init__(
        self,
        config_service,
        metadata: Optional[AgentMetadata] = None
    ):
        super().__init__(metadata)
        self.config_service = config_service

        # Get database path
        db_path = config_service.get_path("data.databases.storage")
        self.db_path = db_path

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute storage operation"""
        operation = self.config.get("operation")

        if operation == "store":
            return await self._store(context)
        elif operation == "query":
            return await self._query(context)
        elif operation == "export":
            return await self._export(context)
        else:
            raise ValueError(f"Unsupported operation: {operation}")
```

### 3.2 Store 操作实现

```python
async def _store(self, context: AgentContext) -> AgentResult:
    """Store data to collection"""
    collection = self.config.get("collection")
    data = self.config.get("data")
    user_id = context.user_id

    # Handle list of data
    if isinstance(data, list):
        count = 0
        for item in data:
            await self._store_single(collection, item, user_id, context)
            count += 1
        return AgentResult(
            success=True,
            data={
                "message": f"Stored {count} records to collection '{collection}'",
                "collection": collection,
                "rows_stored": count
            }
        )
    else:
        # Single data
        await self._store_single(collection, data, user_id, context)
        return AgentResult(
            success=True,
            data={
                "message": f"Stored 1 record to collection '{collection}'",
                "collection": collection,
                "rows_stored": 1
            }
        )

async def _store_single(
    self,
    collection: str,
    data: dict,
    user_id: str,
    context: AgentContext
):
    """Store single data record"""
    table_name = f"{collection}_{user_id}"

    # Generate cache key
    cache_key = f"storage_insert_{collection}_{user_id}"

    # Try to load cached script
    cached = await context.memory_manager.get_data(cache_key)

    if not cached:
        # First time: Generate SQL scripts using LLM
        # 1. Generate CREATE TABLE SQL
        create_sql = await self._generate_create_table_sql(table_name, data, context)

        # 2. Generate INSERT SQL
        insert_sql = await self._generate_insert_sql(table_name, list(data.keys()), context)

        # 3. Create table
        await self._execute_sql(create_sql)

        # 4. Cache script
        await context.memory_manager.set_data(cache_key, {
            "table_name": table_name,
            "create_table_sql": create_sql,
            "insert_sql": insert_sql,
            "field_order": list(data.keys())
        })

        cached = await context.memory_manager.get_data(cache_key)

    # Validate data fields
    self._validate_fields(data, cached["field_order"])

    # Prepare values
    values = []
    for field in cached["field_order"]:
        value = data[field]
        # Convert complex types to JSON
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        values.append(value)

    # Add system field: created_at
    values.append(datetime.now().isoformat())

    # Execute INSERT
    await self._execute_sql(cached["insert_sql"], values)

async def _generate_create_table_sql(
    self,
    table_name: str,
    data: dict,
    context: AgentContext
) -> str:
    """Generate CREATE TABLE SQL using LLM"""
    from ..providers.anthropic_provider import AnthropicProvider

    # Build prompt
    system_prompt = self.SYSTEM_PROMPT_SCHEMA.format(table_name=table_name)

    data_desc = json.dumps(data, indent=2, ensure_ascii=False)
    user_prompt = f"""Generate CREATE TABLE statement for this data:

{data_desc}

Remember:
- Table name: {table_name}
- Include: id INTEGER PRIMARY KEY AUTOINCREMENT
- Include: created_at TEXT NOT NULL
- Infer types from data values"""

    # Call LLM
    llm_provider = AnthropicProvider()
    response = await llm_provider.generate_response(
        system_prompt=system_prompt,
        user_prompt=user_prompt
    )

    # Extract SQL from response
    create_sql = self._extract_sql(response)
    return create_sql

async def _generate_insert_sql(
    self,
    table_name: str,
    fields: list,
    context: AgentContext
) -> str:
    """Generate INSERT SQL using LLM"""
    from ..providers.anthropic_provider import AnthropicProvider

    # Build prompt
    system_prompt = self.SYSTEM_PROMPT_INSERT.format(
        table_name=table_name,
        fields=", ".join(fields)
    )

    user_prompt = f"""Generate INSERT statement for table: {table_name}

Fields to insert: {", ".join(fields)}
System fields: created_at

Return INSERT SQL with placeholders (?)."""

    # Call LLM
    llm_provider = AnthropicProvider()
    response = await llm_provider.generate_response(
        system_prompt=system_prompt,
        user_prompt=user_prompt
    )

    # Extract SQL from response
    insert_sql = self._extract_sql(response)
    return insert_sql

def _extract_sql(self, llm_response: str) -> str:
    """Extract SQL from LLM response"""
    # Remove markdown code blocks
    if "```sql" in llm_response:
        llm_response = llm_response.split("```sql")[1].split("```")[0]
    elif "```" in llm_response:
        llm_response = llm_response.split("```")[1].split("```")[0]

    return llm_response.strip()

def _validate_fields(self, data: dict, field_order: list):
    """Validate data fields"""
    data_fields = set(data.keys())
    schema_fields = set(field_order)

    # Check missing fields
    missing = schema_fields - data_fields
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    # Check extra fields
    extra = data_fields - schema_fields
    if extra:
        raise ValueError(f"Extra fields not in schema: {extra}")

async def _execute_sql(self, sql: str, params: tuple = None):
    """Execute SQL statement"""
    import aiosqlite
    async with aiosqlite.connect(self.db_path) as db:
        if params:
            await db.execute(sql, params)
        else:
            await db.execute(sql)
        await db.commit()
```

### 3.3 Query 操作实现

```python
async def _query(self, context: AgentContext) -> AgentResult:
    """Query data from collection"""
    collection = self.config.get("collection")
    filters = self.config.get("filters", {})
    limit = self.config.get("limit")
    order_by = self.config.get("order_by")
    user_id = context.user_id

    table_name = f"{collection}_{user_id}"

    # Generate cache key (include query config hash)
    query_config = {
        "filters": filters,
        "order_by": order_by,
        "limit": limit
    }
    config_hash = self._hash_config(query_config)
    cache_key = f"storage_query_{collection}_{user_id}_{config_hash}"

    # Try to load cached script
    cached = await context.memory_manager.get_data(cache_key)

    if not cached:
        # First time: Generate query SQL using LLM
        query_sql, params_order = await self._generate_query_sql(
            table_name, filters, order_by, limit, context
        )

        # Cache script
        await context.memory_manager.set_data(cache_key, {
            "table_name": table_name,
            "query_sql": query_sql,
            "params_order": params_order
        })

        cached = await context.memory_manager.get_data(cache_key)

    # Prepare parameters
    params = self._prepare_query_params(
        cached["params_order"], filters, limit
    )

    # Execute query
    rows = await self._query_sql(cached["query_sql"], params)

    return AgentResult(
        success=True,
        data={
            "message": f"Retrieved {len(rows)} records from collection '{collection}'",
            "operation": "query",
            "collection": collection,
            "total_count": len(rows),
            "data": rows
        }
    )

async def _generate_query_sql(
    self,
    table_name: str,
    filters: dict,
    order_by: str,
    limit: int,
    context: AgentContext
) -> tuple[str, list]:
    """Generate SELECT SQL using LLM"""
    from ..providers.anthropic_provider import AnthropicProvider

    # Build prompt
    system_prompt = self.SYSTEM_PROMPT_QUERY.format(table_name=table_name)

    user_prompt = f"""Generate SELECT query for table: {table_name}

Requirements:
- Filters: {json.dumps(filters, ensure_ascii=False)}
- Order by: {order_by or 'None'}
- Limit: {limit or 'None'}

Return:
1. SELECT SQL with placeholders (?)
2. Parameter order as comment

Example:
SELECT * FROM table WHERE price < ? AND rating > ? LIMIT ?
# params: price, rating, limit"""

    # Call LLM
    llm_provider = AnthropicProvider()
    response = await llm_provider.generate_response(
        system_prompt=system_prompt,
        user_prompt=user_prompt
    )

    # Extract SQL and params order
    query_sql = self._extract_sql(response)

    # Extract params order from comment
    params_order = []
    if "# params:" in response:
        params_line = response.split("# params:")[1].split("\n")[0]
        params_order = [p.strip() for p in params_line.split(",")]

    return query_sql, params_order

def _prepare_query_params(
    self,
    params_order: list,
    filters: dict,
    limit: int
) -> list:
    """Prepare parameters for query"""
    params = []

    for param in params_order:
        if param == "limit":
            params.append(limit)
        elif param in filters:
            filter_val = filters[param]
            if isinstance(filter_val, dict):
                # Handle comparison operators
                params.append(list(filter_val.values())[0])
            else:
                params.append(filter_val)

    return params

async def _query_sql(self, sql: str, params: list = None) -> list:
    """Execute SELECT query"""
    import aiosqlite
    async with aiosqlite.connect(self.db_path) as db:
        db.row_factory = aiosqlite.Row
        if params:
            cursor = await db.execute(sql, params)
        else:
            cursor = await db.execute(sql)
        rows = await cursor.fetchall()
        # Convert to list of dicts
        return [dict(row) for row in rows]

def _hash_config(self, config: dict) -> str:
    """Generate hash for config"""
    import hashlib
    import json

    config_str = json.dumps(config, sort_keys=True)
    return hashlib.md5(config_str.encode()).hexdigest()[:8]
```

### 3.4 Export 操作实现

```python
async def _export(self, context: AgentContext) -> AgentResult:
    """Export data to file"""
    collection = self.config.get("collection")
    format = self.config.get("format")
    output_path = self.config.get("output_path")
    filters = self.config.get("filters", {})
    user_id = context.user_id

    table_name = f"{collection}_{user_id}"

    # Generate cache key
    export_config = {
        "filters": filters,
        "format": format
    }
    config_hash = self._hash_config(export_config)
    cache_key = f"storage_export_{collection}_{user_id}_{config_hash}"

    # Try to load cached script
    cached = await context.memory_manager.get_data(cache_key)

    if not cached:
        # Generate query SQL (same as query operation)
        query_sql, params_order = await self._generate_query_sql(
            table_name, filters, order_by=None, limit=None, context=context
        )

        # Cache script
        await context.memory_manager.set_data(cache_key, {
            "table_name": table_name,
            "query_sql": query_sql,
            "params_order": params_order,
            "format": format
        })

        cached = await context.memory_manager.get_data(cache_key)

    # Prepare parameters
    params = self._prepare_query_params(
        cached["params_order"], filters, None
    )

    # Execute query
    rows = await self._query_sql(cached["query_sql"], params)

    # Export to file
    if format == "csv":
        self._export_to_csv(rows, output_path)
    elif format == "excel":
        self._export_to_excel(rows, output_path)
    elif format == "json":
        self._export_to_json(rows, output_path)

    return AgentResult(
        success=True,
        data={
            "message": f"Exported {len(rows)} records to {output_path}",
            "operation": "export",
            "collection": collection,
            "format": format,
            "output_path": output_path,
            "rows_exported": len(rows)
        }
    )

def _export_to_csv(self, rows: list, output_path: str):
    """Export to CSV"""
    import pandas as pd
    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)

def _export_to_excel(self, rows: list, output_path: str):
    """Export to Excel"""
    import pandas as pd
    df = pd.DataFrame(rows)
    df.to_excel(output_path, index=False, engine='openpyxl')

def _export_to_json(self, rows: list, output_path: str):
    """Export to JSON"""
    import json
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
```

## 4. 执行流程

### 4.1 Store 流程

```
┌─────────────────────────────────────────────────┐
│ 1. Parse inputs (collection, data, user_id)    │
└─────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│ 2. Generate cache_key                           │
│    storage_insert_{collection}_{user_id}        │
└─────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│ 3. Load cached script from Memory               │
└─────────────────────────────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        │                           │
     Cached?                    Not Cached
        │                           │
        │                           ▼
        │         ┌─────────────────────────────────┐
        │         │ 4a. LLM: Generate CREATE TABLE  │
        │         └─────────────────────────────────┘
        │                           │
        │                           ▼
        │         ┌─────────────────────────────────┐
        │         │ 4b. LLM: Generate INSERT SQL    │
        │         └─────────────────────────────────┘
        │                           │
        │                           ▼
        │         ┌─────────────────────────────────┐
        │         │ 4c. Execute CREATE TABLE        │
        │         └─────────────────────────────────┘
        │                           │
        │                           ▼
        │         ┌─────────────────────────────────┐
        │         │ 4d. Cache scripts to Memory     │
        │         └─────────────────────────────────┘
        │                           │
        └───────────────┬───────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────┐
│ 5. Validate data fields                         │
└─────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────┐
│ 6. Prepare values (user fields + created_at)    │
└─────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────┐
│ 7. Execute INSERT SQL                           │
└─────────────────────────────────────────────────┘
```

### 4.2 Query 流程

```
┌─────────────────────────────────────────────────┐
│ 1. Parse inputs (collection, filters, user_id) │
└─────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│ 2. Generate cache_key (include config hash)    │
│    storage_query_{collection}_{user_id}_{hash} │
└─────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│ 3. Load cached script from Memory               │
└─────────────────────────────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        │                           │
     Cached?                    Not Cached
        │                           │
        │                           ▼
        │         ┌─────────────────────────────────┐
        │         │ 4a. LLM: Generate SELECT SQL    │
        │         │     with WHERE conditions       │
        │         └─────────────────────────────────┘
        │                           │
        │                           ▼
        │         ┌─────────────────────────────────┐
        │         │ 4b. Cache script to Memory      │
        │         └─────────────────────────────────┘
        │                           │
        └───────────────┬───────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────┐
│ 5. Prepare query parameters                     │
└─────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────┐
│ 6. Execute SELECT SQL                           │
└─────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────┐
│ 7. Return query results                         │
└─────────────────────────────────────────────────┘
```

### 4.3 Export 流程

Export 流程与 Query 类似，增加了最后的文件导出步骤：
1. 生成 cache_key（包含 format）
2. LLM 生成或加载 query SQL
3. 执行查询
4. 根据 format 导出文件（CSV/Excel/JSON）

## 5. 配置和注册

### 5.1 数据库配置

```yaml
# base_app/config/baseapp.yaml
data:
  root: ~/.local/share/baseapp
  databases:
    storage: ${data.root}/storage.db  # New
    sessions: ${data.root}/sessions.db
    kv: ${data.root}/agent_kv.db
```

### 5.2 Agent 注册

```python
# base_app/base_agent/core/workflow_engine.py

class WorkflowEngine:
    def __init__(self, ...):
        # Register built-in agents
        self.agent_registry.register("text_agent", TextAgent)
        self.agent_registry.register("tool_agent", ToolAgent)
        self.agent_registry.register("code_agent", CodeAgent)
        self.agent_registry.register("scraper_agent", ScraperAgent)
        self.agent_registry.register("storage_agent", StorageAgent)  # New
```

## 6. 代码结构

```
base_app/base_agent/
├── agents/
│   └── storage_agent.py          # StorageAgent main class (single file)
└── core/
    └── workflow_engine.py  # Register StorageAgent
```

## 7. LLM 生成 SQL 的优势

### 7.1 vs 手写 SQL 生成

**LLM 生成**:
- ✅ 自动推断最优数据类型
- ✅ 处理复杂查询逻辑
- ✅ 支持自然语言描述
- ✅ 代码简洁（无需 SchemaManager/QueryBuilder）
- ❌ 需要 LLM 调用成本（但有缓存）

**手写 SQL**:
- ✅ 无 LLM 调用成本
- ✅ 确定性执行
- ❌ 需要复杂的类型推断逻辑
- ❌ 需要复杂的查询构建逻辑
- ❌ 代码量大（SchemaManager + QueryBuilder + 300+ 行）

### 7.2 缓存机制保证性能

- **首次**: LLM 生成 SQL（2-3 秒）
- **后续**: 从 Memory 加载（< 10ms）
- 由于 workflow 配置固定，缓存命中率接近 100%

## 8. 实现要点

### 8.1 LLM Prompt 设计

- **明确输出格式**: 只返回 SQL，不要解释
- **安全性**: 使用参数化查询（?）
- **类型推断**: 提供数据示例
- **参数顺序**: 在注释中返回

### 8.2 SQL 提取

- 移除 markdown 代码块
- 提取参数顺序
- 验证 SQL 语法

### 8.3 错误处理

- LLM 生成失败：重试或降级
- SQL 执行失败：详细错误信息
- Schema 验证失败：明确提示缺失字段

## 9. 总结

StorageAgent v1.0 采用 **LLM 生成 SQL** 的设计：

**核心特性**:
- LLM 生成 CREATE TABLE / INSERT / SELECT SQL
- Script 缓存机制（复用 LLM 生成结果）
- Schema 固定（首次确定，不可变更）
- 用户隔离（独立表）
- 三种操作（Store/Query/Export）

**技术栈**:
- SQLite + aiosqlite
- LLM Provider（Anthropic/OpenAI）
- Memory KV Storage（script 缓存）
- pandas（CSV/Excel 导出）
- BaseStepAgent 继承

**设计原则**:
- **简单优先**: 单文件实现，无辅助类
- **LLM 驱动**: 利用 LLM 生成 SQL
- **性能优化**: Script 缓存避免重复生成
- **参考 ScraperAgent**: 相同的 Plan-Generate-Execute 模式
