# Intent 数据结构规范

**版本**: v2.0
**日期**: 2025-10-09
**状态**: 已确定

---

## 1. 概述

### 1.1 定义

**Intent（意图）** 是用户操作的语义抽象，表示一个完整的子任务单元。

- **职责**: 描述"用户想做什么"（description）和"怎么做的"（operations）
- **粒度**: 粗粒度，一个语义完整的子目标
- **来源**: 从 User Operations JSON 中提取

### 1.2 设计原则

1. **极简设计**: 只保留核心字段，避免过度设计
2. **语义优先**: 依赖 description 进行理解和检索，不依赖标签
3. **操作完整**: 保留原始操作序列，提供完整上下文
4. **可扩展性**: 结构简单，未来可以添加字段

---

## 2. 数据结构定义

### 2.1 Python 数据模型

```python
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any

@dataclass
class Intent:
    """Intent 数据结构"""

    # === 核心字段 ===
    id: str                          # 唯一标识
    description: str                 # 意图的语义描述（人类可读）
    operations: List[Operation]      # 用户操作序列（来自 JSON）

    # === 元数据 ===
    created_at: datetime             # 创建时间
    source_session_id: str           # 来源会话 ID
```

### 2.2 字段说明

#### `id: str`

**用途**: Intent 的唯一标识符

**生成规则**: 基于 description 的 MD5 哈希（前8位）

```python
import hashlib

def generate_intent_id(description: str) -> str:
    """生成 Intent ID"""
    hash_value = hashlib.md5(description.encode('utf-8')).hexdigest()[:8]
    return f"intent_{hash_value}"

# 示例
description = "导航到 Allegro 首页"
intent_id = generate_intent_id(description)
# intent_id = "intent_a3f5b2c1"
```

**设计理由**:
- 语义相关：相同描述生成相同 ID
- 唯一性：MD5 哈希冲突概率极低
- 可读性：ID 包含语义哈希，便于调试
- 未来去重：相同描述的 Intent 可以被识别

#### `description: str`

**用途**: Intent 的自然语言描述

**特点**:
- 简洁明确：一句话说明意图
- 人类可读：便于用户理解
- 语义完整：包含足够的上下文信息

**示例**:
```python
# 好的描述
"导航到 Allegro 电商网站首页"
"通过菜单导航进入咖啡产品分类页面"
"从分类页面提取所有产品的链接"

# 不好的描述（过于简单）
"导航"  # 缺少目标
"点击"  # 缺少语义
"提取数据"  # 不明确

# 不好的描述（过于冗长）
"用户首先导航到 Allegro 网站的首页，然后等待页面加载完成，接着..."
```

**生成方式**: 由 LLM 基于 operations 生成

**检索用途**: 语义相似度检索的主要依据

#### `operations: List[Operation]`

**用途**: 完成这个意图的具体操作序列

**来源**: 从 User Operations JSON 中提取

**格式**: Operation 对象列表（保持原始 JSON 结构）

```python
@dataclass
class Operation:
    """单个操作"""
    type: str                    # navigate, click, select, copy_action, etc.
    timestamp: int               # 时间戳
    url: str                     # 页面 URL
    page_title: str              # 页面标题
    element: Dict[str, Any]      # DOM 元素信息
    data: Dict[str, Any]         # 操作数据（可选）
```

**示例**:
```python
operations = [
    Operation(
        type="click",
        timestamp=1757730778353,
        url="https://allegro.pl/",
        page_title="Allegro - Strona Główna",
        element={
            "xpath": "//div[2]/div[1]/.../button/i",
            "tagName": "I",
            "className": "mjyo_6x meqh_en...",
            "textContent": ""
        },
        data={"button": 0, "clientX": 292, "clientY": 177}
    ),
    Operation(
        type="click",
        url="https://allegro.pl/",
        element={
            "xpath": "//div[2]/div[1]/.../li[1]/a",
            "tagName": "A",
            "className": "mgn2_14 mp0t_0a...",
            "textContent": "Kawy",
            "href": "https://allegro.pl/kategoria/produkty-spozywcze-kawa-74030"
        },
        data={}
    ),
    Operation(
        type="navigate",
        timestamp=1757730782138,
        url="https://allegro.pl/kategoria/produkty-spozywcze-kawa-74030",
        page_title="Kawa - Allegro",
        element={},
        data={}
    )
]
```

**重要性**:
- 提供完整上下文：LLM 理解用户的具体操作
- 支持多种操作类型：navigate, click, select, copy_action, input, wait, scroll
- 保留 DOM 信息：xpath, textContent, href 等
- 支持 MetaFlow 生成：LLM 根据这些信息生成 YAML

#### `created_at: datetime`

**用途**: Intent 创建时间

**用途**:
- 时间排序
- 调试和日志
- 未来的时间分析

#### `source_session_id: str`

**用途**: 标识 Intent 来源的会话

**用途**:
- 追溯来源
- 会话隔离
- 未来的会话分析

---

## 3. 完整示例

### 3.1 导航类 Intent

```python
Intent(
    id="intent_a3f5b2c1",
    description="导航到 Allegro 电商网站首页",
    operations=[
        Operation(
            type="navigate",
            timestamp=1757730777260,
            url="https://allegro.pl/",
            page_title="Navigated Page",
            element={},
            data={}
        )
    ],
    created_at=datetime(2025, 10, 9, 12, 30, 0),
    source_session_id="session_demo_001"
)
```

### 3.2 交互类 Intent

```python
Intent(
    id="intent_b7e4c8d2",
    description="通过菜单导航进入咖啡产品分类页面",
    operations=[
        Operation(
            type="click",
            url="https://allegro.pl/",
            element={
                "xpath": "//div[2]/div[1]/.../button/i",
                "tagName": "I",
                "textContent": ""
            },
            data={"button": 0}
        ),
        Operation(
            type="click",
            url="https://allegro.pl/",
            element={
                "xpath": "//div[2]/div[1]/.../li[1]/a",
                "tagName": "A",
                "textContent": "Kawy",
                "href": "https://allegro.pl/kategoria/produkty-spozywcze-kawa-74030"
            },
            data={}
        ),
        Operation(
            type="navigate",
            url="https://allegro.pl/kategoria/produkty-spozywcze-kawa-74030",
            page_title="Kawa - Allegro",
            element={},
            data={}
        )
    ],
    created_at=datetime(2025, 10, 9, 12, 30, 5),
    source_session_id="session_demo_001"
)
```

### 3.3 数据提取类 Intent

```python
Intent(
    id="intent_c9f2d5e3",
    description="访问产品详情页，提取并存储产品的标题、价格、销量信息",
    operations=[
        Operation(
            type="navigate",
            url="https://allegro.pl/oferta/kawa-ziarnista-1kg-brazylia-santos-...",
            page_title="Kawa ziarnista Arabica Tommy Cafe...",
            element={},
            data={}
        ),
        Operation(
            type="select",
            element={
                "xpath": "//*[@id=\"showproduct-left-column-wrapper\"]/.../h1",
                "tagName": "H1",
                "textContent": "Kawa ziarnista 1kg BRAZYLIA Santos Świeżo Palona 100% ARABICA Tommy Cafe"
            },
            data={"selectedText": "Kawa ziarnista 1kg BRAZYLIA Santos..."}
        ),
        Operation(
            type="copy_action",
            element={...},
            data={"copiedText": "Kawa ziarnista 1kg BRAZYLIA Santos Świeżo Palona 100% ARABICA Tommy Cafe"}
        ),
        Operation(
            type="select",
            element={
                "xpath": "//*[@id=\"showproduct-right-column-wrapper\"]/.../div[1]",
                "tagName": "DIV",
                "textContent": "cena 69,50 złAllegro Smart! to darmowe dostawy..."
            },
            data={"selectedText": "cena69,50 zł\n"}
        ),
        Operation(
            type="copy_action",
            element={...},
            data={"copiedText": "cena69,50 zł\n"}
        )
    ],
    created_at=datetime(2025, 10, 9, 12, 31, 0),
    source_session_id="session_demo_001"
)
```

---

## 4. 与其他组件的关系

### 4.1 Intent → MetaFlowNode 映射

Intent 会被转换为 MetaFlowNode：

```python
# Intent
Intent(
    id="intent_a3f5b2c1",
    description="导航到 Allegro 首页",
    operations=[...]
)

# MetaFlowNode
MetaFlowNode(
    id="node_1",
    intent_id="intent_a3f5b2c1",  # 引用 Intent
    intent_name="NavigateToAllegro",  # 简化的名称
    intent_description="导航到 Allegro 首页",  # 复制 description
    operations=[...]  # 复制 operations
)
```

### 4.2 Intent 在 IntentMemoryGraph 中的存储

```python
graph = IntentMemoryGraph()

# 添加 Intent
graph.add_intent(intent1)
graph.add_intent(intent2)

# 添加边（时间顺序）
graph.add_edge(intent1.id, intent2.id)

# 检索
retrieved_intents = graph.retrieve_similar("爬取咖啡商品", limit=5)
```

---

## 5. 操作类型规范

### 5.1 支持的操作类型

| Type | 说明 | 关键字段 |
|------|------|---------|
| `navigate` | 导航到 URL | url, page_title |
| `click` | 点击元素 | element (xpath, textContent, href) |
| `input` | 输入文本 | element, data.value |
| `select` | 选择文本 | element, data.selectedText |
| `copy_action` | 复制文本 | data.copiedText |
| `wait` | 等待 | data.duration |
| `scroll` | 滚动 | data.direction, data.distance |

### 5.2 特殊操作说明

#### `copy_action`

**含义**: 用户复制了页面上的文本

**重要性**: 表明用户想要提取这个数据

**保留原样**: MVP 不转换为 extract，保留在 Intent.operations 中

**LLM 理解**: 在生成 MetaFlow/Workflow 时，LLM 理解其语义

```python
Operation(
    type="copy_action",
    element={
        "xpath": "//*[@id='price-section']",
        "tagName": "DIV",
        "textContent": "cena 69,50 złAllegro Smart! to..."
    },
    data={
        "copiedText": "69,50 zł",  # 用户实际复制的内容
        "textLength": 13,
        "copyMethod": "selection"
    }
)
```

**注意**: `copiedText` 可能是 `textContent` 的子集（用户只选择了部分）

---

## 6. 设计决策记录

### 为什么没有 tags/category？

**原因**: 使用语义相似度检索，不需要预定义标签

**优势**:
- 灵活：不受标签体系限制
- 准确：基于语义理解，而非关键词匹配
- 简单：减少维护成本

### 为什么没有 inputs/outputs？

**原因**: 数据流由 MetaFlow 层的 LLM 推断

**优势**:
- 解耦：Intent 只负责"做什么"，不负责"数据传递"
- 灵活：LLM 根据上下文推断数据流
- 简单：Intent 结构简单

### 为什么使用描述哈希作为 ID？

**原因**: 语义相关的 ID，支持未来去重

**优势**:
- 相同描述 → 相同 ID
- 便于识别重复的 Intent
- 可读性：ID 包含语义信息

---

## 7. MVP 范围

### 包含

1. ✅ Intent 基本数据结构
2. ✅ 从 User Operations JSON 提取
3. ✅ 存储到 IntentMemoryGraph
4. ✅ 基于语义相似度检索

### 不包含

1. ❌ Intent 去重/合并
2. ❌ 使用频率记录
3. ❌ Intent 版本管理
4. ❌ tags/category 分类

---

## 8. 参考资料

- User Operations 示例: `tests/sample_data/browser-user-operation-tracker-example.json`
- MetaFlow 规范: `metaflow_specification.md`
- 讨论记录: `discussions/04_intent_architecture_decisions.md`
- IntentMemoryGraph 规范: `intent_memory_graph_specification.md`
