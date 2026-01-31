# Memory API - Curl 测试文档

## 环境设置

```bash
# API 地址
API_BASE="http://localhost:9000"

# API Key (替换成你的实际 key)
API_KEY="your-api-key-here"

# User ID (替换成你的实际 user_id)
USER_ID="user123"
```

---

## 1. 添加数据到 Memory

### 方式一：从现有 Recording 添加

```bash
curl -X POST "$API_BASE/api/v1/memory/add" \
  -H "Content-Type: application/json" \
  -H "X-Ami-API-Key: $API_KEY" \
  -d '{
    "user_id": "user123",
    "recording_id": "recording_xxx",
    "generate_embeddings": true
  }'
```

### 方式二：直接提供 Operations

```bash
curl -X POST "$API_BASE/api/v1/memory/add" \
  -H "Content-Type: application/json" \
  -H "X-Ami-API-Key: $API_KEY" \
  -d '{
    "user_id": "user123",
    "session_id": "session_20250129",
    "generate_embeddings": true,
    "operations": [
      {
        "action": "goto",
        "url": "https://producthunt.com",
        "timestamp": 1706500000000
      },
      {
        "action": "click",
        "selector": "#search-button",
        "timestamp": 1706500001000
      },
      {
        "action": "type",
        "selector": "#search-input",
        "text": "AI tools",
        "timestamp": 1706500002000
      },
      {
        "action": "goto",
        "url": "https://producthunt.com/posts/claude",
        "timestamp": 1706500003000
      }
    ]
  }'
```

### 返回示例

```json
{
  "success": true,
  "states_added": 2,
  "states_merged": 0,
  "page_instances_added": 4,
  "intent_sequences_added": 3,
  "actions_added": 1,
  "processing_time_ms": 150
}
```

---

## 2. 查询 Memory (统一查询接口)

**端点**: `POST /api/v1/memory/query`

查询类型自动推断：
- 提供 `target` → 任务查询 (Task)
- 提供 `start_state` + `end_state` → 导航查询 (Navigation)
- 提供 `current_state` → 动作查询 (Action)

### 2.1 任务查询 (Task Query)

```bash
curl -X POST "$API_BASE/api/v1/memory/query" \
  -H "Content-Type: application/json" \
  -H "X-Ami-API-Key: $API_KEY" \
  -d '{
    "target": "在 Product Hunt 搜索 AI 工具",
    "user_id": "user123",
    "top_k": 10
  }'
```

### 2.2 导航查询 (Navigation Query)

```bash
# 使用描述
curl -X POST "$API_BASE/api/v1/memory/query" \
  -H "Content-Type: application/json" \
  -H "X-Ami-API-Key: $API_KEY" \
  -d '{
    "start_state": "Product Hunt 首页",
    "end_state": "产品详情页",
    "user_id": "user123"
  }'

# 使用 state_id
curl -X POST "$API_BASE/api/v1/memory/query" \
  -H "Content-Type: application/json" \
  -H "X-Ami-API-Key: $API_KEY" \
  -d '{
    "start_state": "state_abc123",
    "end_state": "state_def456",
    "user_id": "user123"
  }'
```

### 2.3 动作查询 (Action Query) - 通过 URL 查询页面操作

```bash
# 通过 URL 查询（Agent 使用场景）
curl -X POST "$API_BASE/api/v1/memory/query" \
  -H "Content-Type: application/json" \
  -H "X-Ami-API-Key: $API_KEY" \
  -d '{
    "current_state": "https://www.producthunt.com/",
    "target": "",
    "user_id": "user123"
  }'

# 通过 state_id 查询
curl -X POST "$API_BASE/api/v1/memory/query" \
  -H "Content-Type: application/json" \
  -H "X-Ami-API-Key: $API_KEY" \
  -d '{
    "current_state": "state_abc123",
    "target": "",
    "user_id": "user123"
  }'

# 查找特定操作
curl -X POST "$API_BASE/api/v1/memory/query" \
  -H "Content-Type: application/json" \
  -H "X-Ami-API-Key: $API_KEY" \
  -d '{
    "current_state": "https://www.producthunt.com/",
    "target": "搜索",
    "user_id": "user123"
  }'
```

### 2.4 指定查询类型

```bash
curl -X POST "$API_BASE/api/v1/memory/query" \
  -H "Content-Type: application/json" \
  -H "X-Ami-API-Key: $API_KEY" \
  -d '{
    "target": "查看团队信息",
    "as_type": "task",
    "user_id": "user123"
  }'
```

### 返回示例

#### Task 查询返回
```json
{
  "success": true,
  "query_type": "task",
  "states": [...],
  "actions": [...],
  "cognitive_phrase": {...},
  "execution_plan": [...],
  "metadata": {
    "method": "neighbor_exploration",
    "depth": 2
  }
}
```

#### Navigation 查询返回
```json
{
  "success": true,
  "query_type": "navigation",
  "states": [...],
  "actions": [...],
  "metadata": {
    "path_length": 3
  }
}
```

#### Action 查询返回
```json
{
  "success": true,
  "query_type": "action",
  "intent_sequences": [
    {
      "id": "seq_xxx",
      "description": "点击搜索按钮",
      "intents": [
        {
          "type": "click",
          "element_role": "button",
          "text": "Search"
        }
      ],
      "causes_navigation": false
    }
  ],
  "outgoing_actions": [...],
  "metadata": {...}
}
```

---

## 3. 通过 URL 查询 State 和 IntentSequences

**端点**: `POST /api/v1/memory/state`

专门用于通过 URL 查询对应的 State 和其关联的 IntentSequences。

```bash
curl -X POST "$API_BASE/api/v1/memory/state" \
  -H "Content-Type: application/json" \
  -H "X-Ami-API-Key: $API_KEY" \
  -d '{
    "user_id": "user123",
    "url": "https://www.producthunt.com/"
  }'
```

### 返回示例

```json
{
  "success": true,
  "state": {
    "id": "state_xxx",
    "description": "Product Hunt 首页",
    "page_url": "https://www.producthunt.com/",
    "page_title": "Product Hunt – The best new products in tech."
  },
  "intent_sequences": [
    {
      "id": "seq_xxx",
      "description": "点击 Launches 链接",
      "intents": [
        {
          "type": "click",
          "element_role": "link",
          "text": "Launches"
        }
      ],
      "causes_navigation": true,
      "navigation_target_state_id": "state_yyy"
    }
  ]
}
```

---

## 4. 获取 Memory 统计

```bash
curl -X GET "$API_BASE/api/v1/memory/stats?user_id=$USER_ID" \
  -H "X-Ami-API-Key: $API_KEY"
```

### 返回示例

```json
{
  "success": true,
  "user_id": "user123",
  "stats": {
    "total_states": 10,
    "total_intent_sequences": 25,
    "total_page_instances": 15,
    "total_actions": 8,
    "domains": ["producthunt.com", "google.com"],
    "url_index_size": 12
  }
}
```

---

## 5. 清除 Memory

```bash
curl -X POST "$API_BASE/api/v1/memory/clear" \
  -H "Content-Type: application/json" \
  -H "X-Ami-API-Key: $API_KEY" \
  -d '{
    "user_id": "user123",
    "delete_all": true
  }'
```

### 返回示例

```json
{
  "success": true,
  "deleted_states": 10,
  "deleted_domains": 2,
  "deleted_phrases": 5,
  "deleted_sequences": 25
}
```

---

## 完整测试流程

```bash
# 设置环境变量
API_BASE="http://localhost:9000"
API_KEY="your-api-key"
USER_ID="user123"

# 1. 查看统计
curl -X GET "$API_BASE/api/v1/memory/stats?user_id=$USER_ID" \
  -H "X-Ami-API-Key: $API_KEY"

# 2. 任务查询
curl -X POST "$API_BASE/api/v1/memory/query" \
  -H "Content-Type: application/json" \
  -H "X-Ami-API-Key: $API_KEY" \
  -d '{
    "target": "在 Product Hunt 搜索内容",
    "user_id": "'"$USER_ID"'"
  }'

# 3. 通过 URL 查询页面操作（Agent 场景）
curl -X POST "$API_BASE/api/v1/memory/query" \
  -H "Content-Type: application/json" \
  -H "X-Ami-API-Key: $API_KEY" \
  -d '{
    "current_state": "https://www.producthunt.com/",
    "target": "",
    "user_id": "'"$USER_ID"'"
  }'

# 4. 查询 State 详情
curl -X POST "$API_BASE/api/v1/memory/state" \
  -H "Content-Type: application/json" \
  -H "X-Ami-API-Key: $API_KEY" \
  -d '{
    "url": "https://www.producthunt.com/",
    "user_id": "'"$USER_ID"'"
  }'
```

---

## 错误码

| 状态码 | 说明 |
|--------|------|
| 400 | 缺少必要参数 |
| 404 | Recording/State 不存在 |
| 500 | 服务器内部错误 |
| 503 | Memory 服务未初始化 |
