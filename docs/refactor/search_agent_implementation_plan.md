# TavilyAgent 实现方案

## 1. 背景与目标

### 1.1 问题描述

当前 BaseAgent 的 workflow 系统缺乏网络搜索和研究能力。对于以下类型的任务：
- "收集过去3天的10个热门AI实践"
- "搜索最新的 React 18 教程"
- "研究竞品公司的最新动态"

现有 agents 无法直接完成，因为：
1. `BrowserAgent` / `ScraperAgent` 需要已知的 URL
2. `TextAgent` 只能处理已有数据，无法获取实时信息
3. `AutonomousBrowserAgent` 理论上可以，但成本高、速度慢、不可控

### 1.2 解决方案

新增 `TavilyAgent`，通过 CRS 调用 Tavily API，提供两种操作模式：

| 操作 | CRS 端点 | 用途 | 流式 |
|------|----------|------|------|
| `search` | `/tavily/search` | 基础搜索，返回 URL 列表 | 否 |
| `research` | `/tavily/research` | 深度研究，综合分析报告 | 可选 |

### 1.3 适用场景

| 场景 | 推荐操作 | 说明 |
|------|----------|------|
| 获取搜索结果列表，后续 workflow 处理 | `search` | 返回 `List[{url, title, snippet}]` |
| 需要综合分析报告 | `research` | 返回 `{report, sources}` |
| "最近3天10个AI大新闻" | `search` + `text_agent` | search 获取候选，text_agent 筛选 |
| "分析 OpenAI 和 Anthropic 竞争格局" | `research` | 直接返回分析报告 |

## 2. 架构设计

### 2.1 调用链路

```
┌─────────────┐      ┌──────────────────┐      ┌─────────────────────┐      ┌─────────────┐
│ TavilyAgent │ ──── │ Cloud Backend    │ ──── │ CRS                 │ ──── │ Tavily API  │
│ (Desktop)   │ HTTP │ /api/v1/tavily/* │ HTTP │ /tavily/*           │ HTTP │             │
└─────────────┘      └──────────────────┘      └─────────────────────┘      └─────────────┘
                            │                          │
                     ┌──────┴──────┐            ┌──────┴──────┐
                     │ X-Ami-API-Key            │ Rate Limiting
                     │ (用户认证)               │ Usage Tracking
                     └─────────────┘            └─────────────┘
```

### 2.2 CRS 支持的端点

```
┌────────────────────────────────┬───────────────┬──────────┐
│              端点              │     类型      │ MVP 支持 │
├────────────────────────────────┼───────────────┼──────────┤
│ /tavily/search                 │ 非流式        │ ✅       │
├────────────────────────────────┼───────────────┼──────────┤
│ /tavily/research               │ 非流式        │ ✅       │
├────────────────────────────────┼───────────────┼──────────┤
│ /tavily/research (stream=true) │ 原始字节流    │ ✅       │
├────────────────────────────────┼───────────────┼──────────┤
│ /tavily/extract                │ 非流式        │ 后续     │
├────────────────────────────────┼───────────────┼──────────┤
│ /tavily/crawl                  │ 非流式        │ 后续     │
├────────────────────────────────┼───────────────┼──────────┤
│ /tavily/map                    │ 非流式        │ 后续     │
└────────────────────────────────┴───────────────┴──────────┘
```

### 2.3 在 Workflow 中的位置

```
┌─────────────────────────────────────────────────────────┐
│                   WorkflowEngine                         │
│  (Orchestration & Dispatch)                             │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┼────────────────────────────────────────┐
        ▼            ▼            ▼            ▼              ▼
   TextAgent   BrowserAgent  ScraperAgent  StorageAgent  TavilyAgent (NEW)
        │            │            │            │              │
        └────────────┴────────────┴────────────┴──────────────┘
```

## 3. 详细设计

### 3.1 INPUT_SCHEMA 定义

```python
INPUT_SCHEMA = InputSchema(
    description="Tavily agent for web search and research",
    fields={
        "operation": FieldSchema(
            type="str",
            required=True,
            enum=["search", "research"],
            description="Operation type: 'search' for basic search, 'research' for deep research"
        ),
        "query": FieldSchema(
            type="str",
            required=True,
            description="Search query or research topic"
        ),
        # search 操作参数
        "num_results": FieldSchema(
            type="int",
            required=False,
            description="Number of results to return (search only, default: 10, max: 50)"
        ),
        "search_depth": FieldSchema(
            type="str",
            required=False,
            enum=["basic", "advanced"],
            description="Search depth (search only): 'basic' (fast) or 'advanced' (comprehensive)"
        ),
        "include_domains": FieldSchema(
            type="list",
            required=False,
            items_type="str",
            description="Only include results from these domains"
        ),
        "exclude_domains": FieldSchema(
            type="list",
            required=False,
            items_type="str",
            description="Exclude results from these domains"
        ),
        # research 操作参数
        "stream": FieldSchema(
            type="bool",
            required=False,
            description="Enable streaming for research operation (default: false)"
        ),
    },
    examples=[
        {
            "operation": "search",
            "query": "AI news 2024",
            "num_results": 10,
            "search_depth": "basic"
        },
        {
            "operation": "research",
            "query": "分析最近3天的10个AI领域大新闻",
            "stream": True
        }
    ]
)
```

### 3.2 输出格式

**search 操作输出**：
```python
{
    "result": [
        {
            "title": "Article Title",
            "url": "https://example.com/article",
            "snippet": "Brief description of the article content...",
            "published_date": "2024-01-15",  # 可选
            "source": "example.com"
        },
        # ... more results
    ]
}
```

**research 操作输出**：
```python
{
    "result": {
        "report": "综合分析报告内容...",
        "sources": [
            {"title": "Source 1", "url": "https://..."},
            # ... more sources
        ]
    }
}
```

### 3.3 Workflow 示例

**示例1：基础搜索 + 筛选**
```yaml
steps:
  # 1. 搜索获取候选
  - id: search-ai-news
    agent: tavily_agent
    inputs:
      operation: search
      query: "AI news January 2024"
      num_results: 20
    outputs:
      result: raw_results

  # 2. 用 LLM 筛选
  - id: filter-top-news
    agent: text_agent
    inputs:
      instruction: "从这些搜索结果中筛选出最重要的10条AI新闻，返回 JSON 数组"
      data: "{{raw_results}}"
    outputs:
      result: top_10_news
```

**示例2：深度研究**
```yaml
steps:
  - id: research-competition
    agent: tavily_agent
    inputs:
      operation: research
      query: "分析 OpenAI 和 Anthropic 的竞争格局"
      stream: true
    outputs:
      result: analysis_report
```

## 4. 需要修改的模块

### 4.1 新增文件

| 文件路径 | 说明 |
|----------|------|
| `src/clients/desktop_app/ami_daemon/base_agent/agents/tavily_agent.py` | TavilyAgent 实现 |

### 4.2 Cloud Backend 修改

#### 4.2.1 在 `main.py` 中添加 Tavily API 路由

```python
# ============================================================
# Tavily API - Web search and research
# ============================================================

class TavilySearchRequest(BaseModel):
    """Request for Tavily search operation"""
    query: str
    num_results: int = 10
    search_depth: str = "basic"
    include_domains: Optional[List[str]] = None
    exclude_domains: Optional[List[str]] = None


class TavilyResearchRequest(BaseModel):
    """Request for Tavily research operation"""
    query: str
    stream: bool = False


@app.post("/api/v1/tavily/search")
async def tavily_search(
    request: TavilySearchRequest,
    x_ami_api_key: str = Header(..., alias="X-Ami-API-Key")
):
    """Execute Tavily search via CRS"""
    proxy_url = config_service.get("llm.proxy_url", "https://api.ariseos.com/api")
    tavily_endpoint = f"{proxy_url.rstrip('/')}/tavily/search"

    payload = {
        "query": request.query,
        "search_depth": request.search_depth,
        "max_results": min(request.num_results, 50),
    }
    if request.include_domains:
        payload["include_domains"] = request.include_domains
    if request.exclude_domains:
        payload["exclude_domains"] = request.exclude_domains

    headers = {
        "X-Ami-API-Key": x_ami_api_key,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            tavily_endpoint,
            json=payload,
            headers=headers,
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()

        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", "")[:500],
                "published_date": r.get("published_date"),
                "source": r.get("url", "").split("/")[2] if r.get("url") else None,
            }
            for r in data.get("results", [])
        ]

        return {"results": results, "query": request.query, "total": len(results)}


@app.post("/api/v1/tavily/research")
async def tavily_research(
    request: TavilyResearchRequest,
    x_ami_api_key: str = Header(..., alias="X-Ami-API-Key")
):
    """Execute Tavily research via CRS"""
    proxy_url = config_service.get("llm.proxy_url", "https://api.ariseos.com/api")
    tavily_endpoint = f"{proxy_url.rstrip('/')}/tavily/research"

    payload = {
        "query": request.query,
        "stream": request.stream,
    }

    headers = {
        "X-Ami-API-Key": x_ami_api_key,
        "Content-Type": "application/json",
    }

    if request.stream:
        # 流式响应
        async def event_generator():
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    tavily_endpoint,
                    json=payload,
                    headers=headers,
                    timeout=300.0
                ) as response:
                    async for chunk in response.aiter_bytes():
                        yield chunk

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    else:
        # 非流式响应
        async with httpx.AsyncClient() as client:
            response = await client.post(
                tavily_endpoint,
                json=payload,
                headers=headers,
                timeout=300.0
            )
            response.raise_for_status()
            return response.json()
```

### 4.3 Desktop Agent 修改

#### 4.3.1 `agents/__init__.py`

```python
# 添加导入
from .tavily_agent import TavilyAgent

# 更新 __all__
__all__ = [
    # ... existing exports ...
    'TavilyAgent',
]

# 更新 get_all_agent_schemas()
def get_all_agent_schemas() -> dict:
    return {
        # ... existing agents ...
        'tavily_agent': TavilyAgent.get_input_schema(),
    }
```

#### 4.3.2 `core/workflow_engine.py`

```python
# 在 _load_agent_types() 中添加
from ..agents.tavily_agent import TavilyAgent

cls._AGENT_TYPES = {
    # ... existing agents ...
    'tavily_agent': TavilyAgent,
}
```

#### 4.3.3 `services/cloud_client.py` 新增方法

```python
async def tavily_search(
    self,
    query: str,
    num_results: int = 10,
    search_depth: str = "basic",
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
) -> dict:
    """Call Cloud Backend Tavily search API"""
    payload = {
        "query": query,
        "num_results": num_results,
        "search_depth": search_depth,
    }
    if include_domains:
        payload["include_domains"] = include_domains
    if exclude_domains:
        payload["exclude_domains"] = exclude_domains

    response = await self.client.post(
        "/api/v1/tavily/search",
        json=payload,
        headers={"X-Ami-API-Key": self.api_key},
        timeout=30.0
    )
    response.raise_for_status()
    return response.json()


async def tavily_research(
    self,
    query: str,
    stream: bool = False,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """Call Cloud Backend Tavily research API"""
    payload = {
        "query": query,
        "stream": stream,
    }

    if stream:
        # 流式处理
        result = {"report": "", "sources": []}
        async with self.client.stream(
            "POST",
            "/api/v1/tavily/research",
            json=payload,
            headers={"X-Ami-API-Key": self.api_key},
            timeout=300.0
        ) as response:
            async for chunk in response.aiter_bytes():
                chunk_str = chunk.decode('utf-8')
                # 解析 SSE 事件并回调进度
                if progress_callback and chunk_str.strip():
                    try:
                        await progress_callback("info", f"Research progress: {chunk_str[:100]}...", {})
                    except:
                        pass
                # 累积结果
                result["report"] += chunk_str
        return result
    else:
        response = await self.client.post(
            "/api/v1/tavily/research",
            json=payload,
            headers={"X-Ami-API-Key": self.api_key},
            timeout=300.0
        )
        response.raise_for_status()
        return response.json()
```

### 4.4 Validation 修改

#### 4.4.1 `intent_builder/validators/yaml_validator.py`

```python
# 更新 valid_agent_types 列表
valid_agent_types = [
    "variable",
    "browser_agent",
    "scraper_agent",
    "storage_agent",
    "code_agent",
    "text_agent",
    "autonomous_browser_agent",
    "tavily_agent",  # 新增
]
```

#### 4.4.2 `intent_builder/agents/tools/validate.py`

```python
# 更新 VALID_AGENT_TYPES
VALID_AGENT_TYPES = {
    "browser_agent",
    "scraper_agent",
    "storage_agent",
    "variable",
    "text_agent",
    "autonomous_browser_agent",
    "tavily_agent",  # 新增
}

# 更新 AGENT_SPECIFIC_FIELDS
AGENT_SPECIFIC_FIELDS = {
    # ... existing agents ...
    "tavily_agent": {"step": [], "inputs": ["operation", "query"]},
}
```

#### 4.4.3 `skills/repository/workflow-validation/scripts/validate.py`

```python
# 更新 VALID_AGENT_TYPES
VALID_AGENT_TYPES = {
    "browser_agent",
    "scraper_agent",
    "storage_agent",
    "variable",
    "text_agent",
    "autonomous_browser_agent",
    "tavily_agent",  # 新增
}

# 更新 AGENT_SPECIFIC_FIELDS
AGENT_SPECIFIC_FIELDS = {
    # ... existing agents ...
    "tavily_agent": {"step": [], "inputs": ["operation", "query"]},
}
```

### 4.5 Skills 修改

#### 4.5.1 `skills/repository/agent-specs/SKILL.md`

添加 tavily_agent 章节：

```markdown
## tavily_agent

Web search and research agent powered by Tavily API.

**Required**: `operation`, `query`

### Operations

| Operation | Use Case | Output |
|-----------|----------|--------|
| `search` | Basic web search, get URL list | `List[{title, url, snippet}]` |
| `research` | Deep research, comprehensive analysis | `{report, sources}` |

### search operation

```yaml
- id: search-news
  agent: tavily_agent
  inputs:
    operation: search
    query: "AI news 2024"
    num_results: 10                  # Optional: max results (default: 10)
    search_depth: basic              # Optional: "basic" | "advanced"
    include_domains:                 # Optional: domain whitelist
      - "techcrunch.com"
    exclude_domains:                 # Optional: domain blacklist
      - "spam.com"
  outputs:
    result: search_results           # List[{title, url, snippet, published_date, source}]
```

### research operation

```yaml
- id: research-topic
  agent: tavily_agent
  inputs:
    operation: research
    query: "Analyze the competition between OpenAI and Anthropic"
    stream: true                     # Optional: enable streaming progress
  outputs:
    result: research_report          # {report: "...", sources: [...]}
```

### When to use which

- **search**: When you need a list of URLs/results for further processing in workflow
- **research**: When you need a comprehensive analysis report directly
```

### 4.6 Workflow Builder 修改

#### 4.6.1 `intent_builder/agents/workflow_builder.py`

更新 Agent 表格：

```markdown
### Available Agents

| Agent | Use Case | Required Inputs |
|-------|----------|-----------------|
| `browser_agent` | Navigate, click, fill forms | `target_url` or `interaction_steps` |
| `scraper_agent` | Extract data from page | `data_requirements` |
| `text_agent` | LLM text generation/transform | `instruction` |
| `variable` | Data operations (set/filter/slice) | `operation`, `data` |
| `storage_agent` | Store/query/export data | `operation`, `collection` |
| `tavily_agent` | Web search and research | `operation`, `query` |
```

### 4.7 Frontend 修改

#### 4.7.1 `src/components/CustomNode.jsx`

```javascript
const AGENT_COLORS = {
  browser_agent: { border: '#06b6d4', bg: '#ecfeff', text: '#0e7490', label: 'BROWSER' },
  scraper_agent: { border: '#f97316', bg: '#ffedd5', text: '#c2410c', label: 'SCRAPER' },
  variable: { border: '#a855f7', bg: '#f3e8ff', text: '#7e22ce', label: 'VARIABLE' },
  foreach: { border: '#8b5cf6', bg: '#ede9fe', text: '#6d28d9', label: 'LOOP' },
  loop: { border: '#8b5cf6', bg: '#ede9fe', text: '#6d28d9', label: 'LOOP' },
  storage_agent: { border: '#10b981', bg: '#d1fae5', text: '#047857', label: 'STORAGE' },
  text_agent: { border: '#3b82f6', bg: '#dbeafe', text: '#1d4ed8', label: 'TEXT' },
  tavily_agent: { border: '#ec4899', bg: '#fce7f3', text: '#be185d', label: 'TAVILY' },  // Pink
  default: { border: '#94a3b8', bg: '#f1f5f9', text: '#475569', label: 'STEP' }
};
```

### 4.8 Documentation 修改

#### 4.8.1 `base_agent/agents/CONTEXT.md`

更新 Agent Types 表格：

```markdown
### Core Agents (BaseStepAgent subclasses)

| File | Agent | Required Inputs |
|------|-------|-----------------|
| `text_agent.py` | TextAgent | `inputs.instruction` |
| `browser_agent.py` | BrowserAgent | `inputs.target_url` or `inputs.interaction_steps` |
| `scraper_agent.py` | ScraperAgent | `inputs.data_requirements` |
| `storage_agent.py` | StorageAgent | `inputs.operation`, `inputs.collection` |
| `variable_agent.py` | VariableAgent | `inputs.operation`, `inputs.data` |
| `autonomous_browser_agent.py` | AutonomousBrowserAgent | `inputs.task` |
| `tavily_agent.py` | TavilyAgent | `inputs.operation`, `inputs.query` |
```

## 5. 完整修改清单

### 🔴 P0 - 阻塞性修改（必须完成）

| # | 模块 | 文件 | 修改内容 |
|---|------|------|----------|
| 1 | Desktop Agent | `base_agent/agents/tavily_agent.py` | 新增 TavilyAgent 实现 |
| 2 | Desktop Agent | `base_agent/agents/__init__.py` | 注册 TavilyAgent |
| 3 | Desktop Agent | `base_agent/core/workflow_engine.py` | 添加到 AGENT_TYPES |
| 4 | Desktop Agent | `services/cloud_client.py` | 新增 `tavily_search()` 和 `tavily_research()` 方法 |
| 5 | Cloud Backend | `main.py` | 添加 `/api/v1/tavily/search` 和 `/api/v1/tavily/research` 路由 |
| 6 | Validation | `intent_builder/validators/yaml_validator.py` | 添加 `tavily_agent` 到 valid_agent_types |
| 7 | Validation | `intent_builder/agents/tools/validate.py` | 添加 `tavily_agent` 到 VALID_AGENT_TYPES |
| 8 | Validation | `skills/repository/workflow-validation/scripts/validate.py` | 添加 `tavily_agent` |
| 9 | Skills | `skills/repository/agent-specs/SKILL.md` | 添加 tavily_agent 规范 |
| 10 | Workflow Builder | `intent_builder/agents/workflow_builder.py` | 更新 Agent 表格 |

### 🟡 P1 - 重要修改（建议完成）

| # | 模块 | 文件 | 修改内容 |
|---|------|------|----------|
| 11 | Docs | `base_agent/agents/CONTEXT.md` | 更新 Agent 列表 |
| 12 | Frontend | `src/components/CustomNode.jsx` | 添加 tavily_agent 颜色配置 |

### 前置依赖（CRS）

| 端点 | 说明 |
|------|------|
| `/tavily/search` | 基础搜索，非流式 |
| `/tavily/research` | 深度研究，支持流式 |

### 修改依赖关系

```
前置条件: CRS 支持 Tavily
┌─────────────────────────────────────────────────────────────────┐
│ CRS (Claude Relay Service) - 假定已实现                          │
│  ├── /tavily/search                                              │
│  └── /tavily/research (支持 stream=true)                         │
└─────────────────────────────────────────────────────────────────┘

Phase 1: 核心实现
┌─────────────────────────────────────────────────────────────────┐
│ Cloud Backend                                                    │
│  └── main.py (添加 /api/v1/tavily/* 路由)                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Desktop Agent                                                    │
│  ├── agents/tavily_agent.py (新增)                               │
│  ├── agents/__init__.py (修改)                                   │
│  ├── core/workflow_engine.py (修改)                              │
│  └── services/cloud_client.py (修改)                             │
└─────────────────────────────────────────────────────────────────┘

Phase 2: Validation & Skills
┌─────────────────────────────────────────────────────────────────┐
│ Validation (3 files)                                             │
│  ├── yaml_validator.py                                           │
│  ├── validate.py (tools)                                         │
│  └── validate.py (scripts)                                       │
├─────────────────────────────────────────────────────────────────┤
│ Skills                                                           │
│  ├── agent-specs/SKILL.md                                        │
│  └── workflow_builder.py                                         │
└─────────────────────────────────────────────────────────────────┘

Phase 3: Frontend & Docs
┌─────────────────────────────────────────────────────────────────┐
│ Frontend                                                         │
│  └── CustomNode.jsx                                              │
├─────────────────────────────────────────────────────────────────┤
│ Documentation                                                    │
│  └── agents/CONTEXT.md                                           │
└─────────────────────────────────────────────────────────────────┘
```
