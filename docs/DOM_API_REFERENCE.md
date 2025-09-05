# DOM API 参考文档

## 概述

本文档详细介绍了 AgentCrafter 中用于 DOM 数据提取的统一 API 接口。这些 API 专为网页数据抓取场景设计，提供了结构化的 DOM 数据提取能力。

## 🚀 快速开始

```python
from base_app.base_agent.tools.browser_use.dom_extractor import (
    extract_dom_dict, extract_llm_view, DOMExtractor
)

# 1. 获取 DOM 数据源
extractor = DOMExtractor()
dom_state, enhanced_dom_tree, timing = await dom_service.get_serialized_dom_tree()

# 2. 生成可见元素的字典
visible_dom, _ = extractor.serialize_accessible_elements_custom(enhanced_dom_tree, include_non_visible=False)
visible_dict = extract_dom_dict(visible_dom)

# 3. 生成 LLM 简化视图
llm_view = extract_llm_view(visible_dict)
print(llm_view)  # 输出紧凑的 JSON 字符串
```

## 📚 核心 API

### 1. `extract_dom_dict(serialized_dom)`

**功能**：将 SerializedDOM 转换为 Python 字典结构，包含 href 信息。

**参数**：
- `serialized_dom`: SerializedDOM 对象（任何来源）

**返回**：
- `Dict`: 嵌套字典结构，包含 `tag`, `text`, `href`, `interactive_index`, `children`

**示例**：
```python
dom_dict = extract_dom_dict(serialized_dom)

# 输出示例
{
    "tag": "html",
    "children": [
        {
            "tag": "a",
            "href": "/product/123",
            "interactive_index": 1,
            "children": [
                {"tag": "text", "text": "商品名称"}
            ]
        }
    ]
}
```

### 2. `extract_llm_view(dom_dict)`

**功能**：从 DOM 字典中提取有意义的节点（交互元素 + 文本），生成给 LLM 的紧凑视图。

**参数**：
- `dom_dict`: 来自 `extract_dom_dict()` 的字典

**返回**：
- `str`: 紧凑的 JSON 字符串，只包含有意义的元素

**示例**：
```python
llm_view = extract_llm_view(dom_dict)

# 输出示例（紧凑格式）
[{"tag":"a","href":"/product/123","interactive_index":1},{"tag":"text","text":"商品名称"}]
```

### 3. `format_dict_as_text(dom_dict)`

**功能**：将 DOM 字典格式化为类似 `llm_representation()` 的文本格式，主要用于调试。

**参数**：
- `dom_dict`: 来自 `extract_dom_dict()` 的字典

**返回**：
- `str`: 人类可读的文本格式

**示例**：
```python
formatted_text = format_dict_as_text(dom_dict)

# 输出示例
[1]<A href=/product/123 />
    商品名称
```

## 🔧 DOMExtractor 类方法

### `serialize_accessible_elements_custom(enhanced_dom, include_non_visible=False)`

**功能**：自定义 DOM 序列化，控制是否包含不可见元素。

**参数**：
- `enhanced_dom`: EnhancedDOMTreeNode 对象
- `include_non_visible`: 是否包含不可见元素

**返回**：
- `Tuple[SerializedDOMState, Dict[str, float]]`: 序列化的 DOM 和时间信息

**示例**：
```python
extractor = DOMExtractor()

# 只包含可见元素
visible_dom, timing = extractor.serialize_accessible_elements_custom(
    enhanced_dom, include_non_visible=False
)

# 包含所有元素（包括不可见）
full_dom, timing = extractor.serialize_accessible_elements_custom(
    enhanced_dom, include_non_visible=True
)
```

## 📊 数据结构说明

### DOM 字典结构

DOM 字典采用嵌套结构，每个节点包含以下字段（只有非空字段才会出现）：

```python
{
    "tag": "元素标签名（如 a, div, span）或 text",
    "text": "文本内容（仅文本节点有此字段）",
    "href": "链接地址（仅链接元素有此字段）", 
    "interactive_index": "交互元素索引（仅可交互元素有此字段）",
    "children": [子元素数组]
}
```

### LLM 视图结构

LLM 视图是扁平化的数组，只包含有意义的元素：

```python
[
    {"tag": "a", "href": "/link1", "interactive_index": 1},
    {"tag": "text", "text": "链接文字"},
    {"tag": "span", "interactive_index": 2},
    {"tag": "text", "text": "按钮文字"}
]
```

## 🛠️ 完整使用流程

### 场景1：提取可见元素

```python
from base_app.base_agent.tools.browser_use.dom_extractor import extract_dom_dict, extract_llm_view, DOMExtractor
from browser_use.dom.service import DomService

async def extract_visible_elements(dom_service):
    # 1. 获取基础 DOM
    dom_state, enhanced_dom_tree, timing = await dom_service.get_serialized_dom_tree()
    
    # 2. 创建提取器
    extractor = DOMExtractor()
    
    # 3. 获取可见元素的 DOM
    visible_dom, _ = extractor.serialize_accessible_elements_custom(
        enhanced_dom_tree, include_non_visible=False
    )
    
    # 4. 转换为字典
    visible_dict = extract_dom_dict(visible_dom)
    
    # 5. 生成 LLM 视图
    llm_view = extract_llm_view(visible_dict)
    
    return visible_dict, llm_view
```

### 场景2：提取全量元素

```python
async def extract_all_elements(dom_service):
    # 1. 获取基础 DOM  
    dom_state, enhanced_dom_tree, timing = await dom_service.get_serialized_dom_tree()
    
    # 2. 创建提取器
    extractor = DOMExtractor()
    
    # 3. 获取全量元素的 DOM（包含不可见）
    full_dom, _ = extractor.serialize_accessible_elements_custom(
        enhanced_dom_tree, include_non_visible=True
    )
    
    # 4. 转换为字典
    full_dict = extract_dom_dict(full_dom)
    
    # 5. 生成 LLM 视图
    llm_view = extract_llm_view(full_dict)
    
    return full_dict, llm_view
```

### 场景3：数据统计和分析

```python
def analyze_dom_elements(dom_dict):
    """分析 DOM 元素统计"""
    counts = {"interactive": 0, "text": 0, "total": 0, "links": 0}
    
    def traverse(node):
        if isinstance(node, dict):
            counts["total"] += 1
            
            if "interactive_index" in node:
                counts["interactive"] += 1
            
            if node.get("tag") == "text":
                counts["text"] += 1
                
            if "href" in node:
                counts["links"] += 1
            
            for child in node.get("children", []):
                traverse(child)
    
    traverse(dom_dict)
    return counts

# 使用示例
stats = analyze_dom_elements(visible_dict)
print(f"总元素: {stats['total']}, 交互元素: {stats['interactive']}, 链接: {stats['links']}")
```

## ⚡ 性能优化建议

1. **按需提取**：只在需要时提取全量元素（`include_non_visible=True`），可见元素提取更快。

2. **缓存结果**：DOM 提取结果可以缓存，避免重复处理。

3. **分批处理**：对于大型页面，可以分批处理 DOM 数据。

## 🔍 调试技巧

### 查看原始结构
```python
import json
print(json.dumps(dom_dict, indent=2, ensure_ascii=False))
```

### 对比格式化输出
```python
formatted_text = format_dict_as_text(dom_dict)
print("格式化文本:")
print(formatted_text)
```

### 验证 LLM 视图
```python
import json
llm_view = extract_llm_view(dom_dict)
meaningful_elements = json.loads(llm_view)
print(f"有意义元素数量: {len(meaningful_elements)}")
for i, elem in enumerate(meaningful_elements[:5]):
    print(f"[{i+1}] {elem}")
```

## 🚨 常见问题

### Q: 为什么某些元素没有出现在结果中？
A: 元素可能是不可见的，或者没有交互索引。尝试使用 `include_non_visible=True` 参数。

### Q: LLM 视图为空怎么办？
A: 检查页面是否加载完成，或者 DOM 中没有可交互元素和文本内容。

### Q: 如何获取特定类型的元素？
A: 可以在 `extract_llm_view()` 结果中过滤，或者直接遍历 `dom_dict` 查找。

### Q: 性能问题怎么优化？
A: 优先使用 `include_non_visible=False`，并考虑缓存提取结果。

## 📝 更新日志

- **v1.0.0**: 初始版本，统一的 DOM 提取 API
- 删除了旧的 `extract_scraping_data`、`extract_enhanced_data` 等接口
- 简化为 3 个核心函数：`extract_dom_dict`、`extract_llm_view`、`format_dict_as_text`