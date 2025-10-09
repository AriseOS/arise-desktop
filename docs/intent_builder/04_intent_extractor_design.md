# IntentExtractor 组件设计文档

**版本**: v2.0
**日期**: 2025-10-09
**状态**: 已确定

---

## 1. 概述

### 1.1 定义

**IntentExtractor（意图提取器）** 负责从用户的浏览器操作记录中提取语义化的 Intent。

### 1.2 职责

- **输入**: User Operations JSON + Task Description
- **输出**: Intent List
- **核心任务**:
  1. 将操作序列切分成有意义的片段（segments）
  2. 为每个片段生成 Intent（description + operations）

### 1.3 设计策略

**混合策略**: 规则切分 + LLM 语义提取

- **规则**: 按 URL 变化切分操作序列（结构化问题）
- **LLM**: 为每个片段生成语义描述和进一步切分（语义问题）

---

## 2. 架构设计

### 2.1 组件结构

```
IntentExtractor
  ├── _split_by_url()         # 规则切分
  ├── _extract_from_segment() # LLM 提取
  └── extract_intents()       # 主流程
```

### 2.2 数据流

```
User Operations JSON + Task Description
  ↓
[1] URL-based Segmentation (规则)
  ↓
Operation Segments (List[List[Operation]])
  ↓
[2] LLM Intent Extraction (语义)
  ↓
Intent List
```

---

## 3. 详细设计

### 3.1 主流程方法

```python
class IntentExtractor:
    """从用户操作提取意图"""

    def __init__(self, llm_service: LLMService):
        self.llm = llm_service

    async def extract_intents(
        self,
        operations: List[Dict],
        task_description: str
    ) -> List[Intent]:
        """
        从操作序列提取 Intent 列表

        Args:
            operations: 用户操作序列（来自 JSON）
            task_description: 任务的自然语言描述

        Returns:
            Intent 列表
        """
        # Step 1: 按 URL 变化切分
        segments = self._split_by_url(operations)

        # Step 2: 对每个 segment 提取 Intent
        all_intents = []
        for segment in segments:
            intents = await self._extract_from_segment(
                segment,
                task_description
            )
            all_intents.extend(intents)

        return all_intents
```

---

### 3.2 规则切分方法

#### 方法签名

```python
def _split_by_url(self, operations: List[Dict]) -> List[List[Dict]]:
    """按 URL 变化切分操作序列"""
```

#### 切分规则

**触发条件**: `navigate` 操作 **且** URL 发生变化

**实现逻辑**:
```python
def _split_by_url(self, operations: List[Dict]) -> List[List[Dict]]:
    """按 URL 变化切分操作序列"""
    segments = []
    current_segment = []
    last_url = None

    for op in operations:
        url = op.get('url', '')

        # navigate 操作 + URL 变化 → 新 segment
        if op['type'] == 'navigate' and last_url and url != last_url:
            if current_segment:
                segments.append(current_segment)
            current_segment = [op]
        else:
            current_segment.append(op)

        last_url = url

    # 添加最后一个 segment
    if current_segment:
        segments.append(current_segment)

    return segments
```

#### 切分示例

**输入操作序列**:
```python
[
  {"type": "navigate", "url": "https://allegro.pl/"},           # Op 0
  {"type": "click", "url": "https://allegro.pl/"},              # Op 1
  {"type": "click", "url": "https://allegro.pl/"},              # Op 2
  {"type": "navigate", "url": "https://allegro.pl/kawa"},       # Op 3
  {"type": "click", "url": "https://allegro.pl/kawa"},          # Op 4
  {"type": "select", "url": "https://allegro.pl/kawa"},         # Op 5
  {"type": "navigate", "url": "https://allegro.pl/product/1"},  # Op 6
  {"type": "select", "url": "https://allegro.pl/product/1"},    # Op 7
  {"type": "copy_action", "url": "https://allegro.pl/product/1"} # Op 8
]
```

**切分结果**:
```python
[
  [Op 0, Op 1, Op 2],        # Segment 1: 首页操作
  [Op 3, Op 4, Op 5],        # Segment 2: 分类页操作
  [Op 6, Op 7, Op 8]         # Segment 3: 产品页操作
]
```

#### 设计原理

**为什么选择 URL 变化？**
- 页面状态变化的明确标志
- 符合"粗粒度"原则（一个页面 = 一个或多个意图）
- 简单可靠，无需复杂判断

**边界情况处理**:
1. **同页面多操作**: 保持在同一 segment（由 LLM 进一步切分）
2. **AJAX 导航**: 如果 URL 变化（即使是 query 参数），视为新 segment
3. **第一个操作**: 如果不是 navigate，仍加入 segment

---

### 3.3 LLM 提取方法

#### 方法签名

```python
async def _extract_from_segment(
    self,
    segment: List[Dict],
    task_description: str
) -> List[Intent]:
    """用 LLM 从 segment 提取 1-N 个 Intent"""
```

#### 核心逻辑

```python
async def _extract_from_segment(
    self,
    segment: List[Dict],
    task_description: str
) -> List[Intent]:
    """用 LLM 从 segment 提取 1-N 个 Intent"""

    # 1. 构建 Prompt
    prompt = self._build_extraction_prompt(segment, task_description)

    # 2. 调用 LLM
    response = await self.llm.generate_response("", prompt)

    # 3. 解析 LLM 返回的 JSON
    intent_list = json.loads(response)

    # 4. 转换为 Intent 对象
    intents = []
    for intent_data in intent_list:
        # 根据 operation_indices 切分操作
        op_indices = intent_data['operation_indices']
        intent_operations = [segment[idx] for idx in op_indices]

        # 生成 Intent ID
        intent_id = generate_intent_id(intent_data['description'])

        # 创建 Intent 对象
        intent = Intent(
            id=intent_id,
            description=intent_data['description'],
            operations=intent_operations,
            created_at=datetime.now(),
            source_session_id="session_demo"  # 实际应从参数传入
        )
        intents.append(intent)

    return intents
```

---

### 3.4 Prompt 设计

#### Prompt 模板

```python
def _build_extraction_prompt(
    self,
    segment: List[Dict],
    task_desc: str
) -> str:
    """构建 LLM 提取提示词"""

    # 简化操作序列的显示
    ops_summary = []
    for i, op in enumerate(segment):
        ops_summary.append(
            f"[{i}] {op['type']} - {op.get('url', 'N/A')}"
        )

    return f"""分析以下用户操作序列，提取意图。

## 任务描述
{task_desc}

## 操作序列摘要
{chr(10).join(ops_summary)}

## 完整操作详情
{json.dumps(segment, indent=2, ensure_ascii=False)}

---

请将这个操作序列切分成 **1 个或多个意图**。

## 切分原则

一个意图 = 一个明确的子目标

**典型的意图类型**：
- 导航到某个页面
- 完成某个交互（点击菜单、选择分类）
- 提取某类数据
- 填写表单

**如何判断是否需要切分**：
- 如果所有操作都服务于同一个目标 → 保持为一个意图
- 如果操作有多个不同的目标 → 切分成多个意图

**示例**：
- "点击菜单 + 选择咖啡分类" → 一个意图："进入咖啡分类页面"
- "导航到首页 + 点击登录按钮 + 填写表单" → 可能是两个意图："导航到首页" + "登录"

## 输出格式

输出 JSON 数组格式：

```json
[
  {{
    "description": "意图的简短描述（一句话，说明做什么）",
    "operation_indices": [0, 1, 2]
  }},
  ...
]
```

## 要求

1. **description** 必须简洁明确，说明"做什么"
2. **operation_indices** 必须是操作的索引数组
3. **所有操作都必须被分配**到某个意图中
4. **索引不能重复**使用
5. **索引必须按顺序**（不能跳跃）

## 示例输出

```json
[
  {{
    "description": "导航到 Allegro 电商网站首页",
    "operation_indices": [0]
  }},
  {{
    "description": "通过菜单进入咖啡产品分类页面",
    "operation_indices": [1, 2, 3]
  }}
]
```
"""
```

#### Prompt 设计要点

1. **清晰的任务定义**: "提取意图" + "切分原则"
2. **提供上下文**: 任务描述 + 操作详情
3. **明确输出格式**: JSON 数组 + 字段说明
4. **切分指导**: 典型意图类型 + 判断标准
5. **约束条件**: 索引不重复、必须覆盖所有操作
6. **示例**: 展示正确的输出格式

---

### 3.5 LLM 输出解析

#### 期望的 LLM 输出

```json
[
  {
    "description": "导航到 Allegro 电商网站首页",
    "operation_indices": [0]
  },
  {
    "description": "通过菜单导航进入咖啡产品分类页面",
    "operation_indices": [1, 2, 3]
  }
]
```

#### 解析逻辑

```python
intent_list = json.loads(response)

for intent_data in intent_list:
    # 提取字段
    description = intent_data['description']
    op_indices = intent_data['operation_indices']

    # 验证索引
    if not all(0 <= idx < len(segment) for idx in op_indices):
        raise ValueError(f"Invalid operation indices: {op_indices}")

    # 切分操作
    intent_operations = [segment[idx] for idx in op_indices]

    # 生成 Intent
    intent_id = generate_intent_id(description)
    intent = Intent(
        id=intent_id,
        description=description,
        operations=intent_operations,
        created_at=datetime.now(),
        source_session_id=source_session_id
    )
```

#### 错误处理

```python
try:
    intent_list = json.loads(response)
except json.JSONDecodeError as e:
    logger.error(f"Failed to parse LLM response: {e}")
    # 重试或回退策略
```

---

## 4. 完整示例

### 4.1 输入示例

**User Operations JSON** (简化):
```json
{
  "session_info": {
    "start_time": "2025-09-13T10:34:05",
    "total_operations": 16
  },
  "operations": [
    {
      "type": "navigate",
      "timestamp": 1757730777260,
      "url": "https://allegro.pl/",
      "page_title": "Navigated Page",
      "element": {}
    },
    {
      "type": "click",
      "timestamp": 1757730778353,
      "url": "https://allegro.pl/",
      "page_title": "Allegro - Strona Główna",
      "element": {
        "xpath": "//button/i",
        "tagName": "I",
        "textContent": ""
      }
    },
    {
      "type": "click",
      "timestamp": 1757730780902,
      "url": "https://allegro.pl/",
      "element": {
        "xpath": "//li[1]/a",
        "tagName": "A",
        "textContent": "Kawy",
        "href": "https://allegro.pl/kategoria/kawa-74030"
      }
    },
    {
      "type": "navigate",
      "timestamp": 1757730782138,
      "url": "https://allegro.pl/kategoria/kawa-74030",
      "page_title": "Kawa - Allegro",
      "element": {}
    },
    {
      "type": "click",
      "timestamp": 1757730784186,
      "url": "https://allegro.pl/kategoria/kawa-74030",
      "element": {
        "xpath": "//*[@id=\"search-results\"]//h2/a",
        "tagName": "A",
        "textContent": "Kawa ziarnista 1kg BRAZYLIA...",
        "href": "https://allegro.pl/oferta/kawa-12786896326"
      }
    },
    {
      "type": "navigate",
      "timestamp": 1757730785298,
      "url": "https://allegro.pl/oferta/kawa-12786896326",
      "page_title": "Kawa ziarnista Arabica...",
      "element": {}
    },
    {
      "type": "select",
      "timestamp": 1757730788101,
      "url": "https://allegro.pl/oferta/kawa-12786896326",
      "element": {
        "xpath": "//h1",
        "tagName": "H1",
        "textContent": "Kawa ziarnista 1kg BRAZYLIA Santos..."
      },
      "data": {
        "selectedText": "Kawa ziarnista 1kg BRAZYLIA Santos..."
      }
    },
    {
      "type": "copy_action",
      "timestamp": 1757730788659,
      "url": "https://allegro.pl/oferta/kawa-12786896326",
      "element": {...},
      "data": {
        "copiedText": "Kawa ziarnista 1kg BRAZYLIA Santos..."
      }
    }
  ]
}
```

**Task Description**:
```
"用户希望收集热门的第一页的咖啡的商品的相关信息"
```

---

### 4.2 执行流程

```python
# 初始化
llm = AnthropicProvider()
extractor = IntentExtractor(llm)

# 提取
operations = data['operations']
task_desc = "用户希望收集热门的第一页的咖啡的商品的相关信息"

intents = await extractor.extract_intents(operations, task_desc)
```

---

### 4.3 中间结果：Segments

**Segment 1** (Operations 0-2):
```python
[
  {"type": "navigate", "url": "https://allegro.pl/", ...},
  {"type": "click", "url": "https://allegro.pl/", ...},
  {"type": "click", "url": "https://allegro.pl/", ...}
]
```

**Segment 2** (Operations 3-4):
```python
[
  {"type": "navigate", "url": "https://allegro.pl/kategoria/kawa-74030", ...},
  {"type": "click", "url": "https://allegro.pl/kategoria/kawa-74030", ...}
]
```

**Segment 3** (Operations 5-7):
```python
[
  {"type": "navigate", "url": "https://allegro.pl/oferta/kawa-12786896326", ...},
  {"type": "select", ...},
  {"type": "copy_action", ...}
]
```

---

### 4.4 LLM 输出

**For Segment 1**:
```json
[
  {
    "description": "导航到 Allegro 电商网站首页",
    "operation_indices": [0]
  },
  {
    "description": "通过菜单导航进入咖啡产品分类页面",
    "operation_indices": [1, 2]
  }
]
```

**For Segment 2**:
```json
[
  {
    "description": "从咖啡分类页面点击第一个商品查看详情",
    "operation_indices": [0, 1]
  }
]
```

**For Segment 3**:
```json
[
  {
    "description": "访问产品详情页并提取产品标题",
    "operation_indices": [0, 1, 2]
  }
]
```

---

### 4.5 最终输出：Intent List

```python
[
  Intent(
    id="intent_a3f5b2c1",
    description="导航到 Allegro 电商网站首页",
    operations=[Op 0],
    created_at=...,
    source_session_id="session_demo_001"
  ),
  Intent(
    id="intent_b7e4c8d2",
    description="通过菜单导航进入咖啡产品分类页面",
    operations=[Op 1, Op 2],
    created_at=...,
    source_session_id="session_demo_001"
  ),
  Intent(
    id="intent_c5a9e3f1",
    description="从咖啡分类页面点击第一个商品查看详情",
    operations=[Op 3, Op 4],
    created_at=...,
    source_session_id="session_demo_001"
  ),
  Intent(
    id="intent_d8b2f4e6",
    description="访问产品详情页并提取产品标题",
    operations=[Op 5, Op 6, Op 7],
    created_at=...,
    source_session_id="session_demo_001"
  )
]
```

---

## 5. 错误处理

### 5.1 LLM 返回格式错误

**场景**: LLM 返回非 JSON 或格式不正确

**处理**:
```python
try:
    intent_list = json.loads(response)
except json.JSONDecodeError:
    logger.error("LLM response is not valid JSON")
    # 重试或使用默认策略
    return [create_default_intent(segment)]
```

### 5.2 操作索引越界

**场景**: LLM 返回的索引超出范围

**处理**:
```python
for intent_data in intent_list:
    op_indices = intent_data['operation_indices']
    if not all(0 <= idx < len(segment) for idx in op_indices):
        logger.error(f"Invalid indices: {op_indices}")
        continue  # 跳过这个 Intent
```

### 5.3 操作未完全覆盖

**场景**: LLM 返回的索引没有覆盖所有操作

**处理**:
```python
covered = set()
for intent_data in intent_list:
    covered.update(intent_data['operation_indices'])

if len(covered) != len(segment):
    logger.warning(f"Not all operations covered: {len(covered)}/{len(segment)}")
    # 为未覆盖的操作创建默认 Intent
```

---

## 6. 测试策略

### 6.1 单元测试

**测试 URL 切分**:
```python
def test_split_by_url():
    extractor = IntentExtractor(mock_llm)

    ops = [
        {"type": "navigate", "url": "https://a.com"},
        {"type": "click", "url": "https://a.com"},
        {"type": "navigate", "url": "https://b.com"},
        {"type": "click", "url": "https://b.com"}
    ]

    segments = extractor._split_by_url(ops)

    assert len(segments) == 2
    assert len(segments[0]) == 2  # [navigate, click]
    assert len(segments[1]) == 2  # [navigate, click]
```

**测试 LLM 解析**:
```python
@pytest.mark.asyncio
async def test_extract_from_segment():
    mock_llm = MockLLMService(response='[{"description": "test", "operation_indices": [0]}]')
    extractor = IntentExtractor(mock_llm)

    segment = [{"type": "navigate", "url": "https://example.com"}]
    intents = await extractor._extract_from_segment(segment, "test task")

    assert len(intents) == 1
    assert intents[0].description == "test"
```

### 6.2 集成测试

**完整流程测试**:
```python
@pytest.mark.asyncio
async def test_extract_intents_full():
    llm = AnthropicProvider()
    extractor = IntentExtractor(llm)

    # 使用真实的 operations JSON
    with open('browser-user-operation-tracker-example.json') as f:
        data = json.load(f)

    operations = data['operations']
    task_desc = "用户希望收集咖啡商品信息"

    intents = await extractor.extract_intents(operations, task_desc)

    # 验证
    assert len(intents) > 0
    assert all(intent.description for intent in intents)
    assert all(intent.operations for intent in intents)
```

---

## 7. 性能考虑

### 7.1 时间复杂度

- **URL 切分**: O(N)，N = 操作数量
- **LLM 提取**: O(S × T)，S = segment 数量，T = LLM 调用时间
- **总体**: O(N + S × T)

### 7.2 优化方向

1. **并行处理**: 多个 segment 并行调用 LLM
2. **缓存**: 缓存相似 segment 的结果
3. **批处理**: 一次 LLM 调用处理多个 segment

---

## 8. MVP 范围

### 包含功能

1. ✅ URL 切分
2. ✅ LLM 语义提取
3. ✅ Intent 对象生成
4. ✅ 基本错误处理

### 不包含功能

1. ❌ 并行处理优化
2. ❌ 结果缓存
3. ❌ 高级错误恢复
4. ❌ Intent 去重

---

## 9. 参考资料

- Intent 规范: `intent_specification.md`
- 讨论记录: `discussions/04_intent_architecture_decisions.md`
- User Operations 示例: `tests/sample_data/browser-user-operation-tracker-example.json`
