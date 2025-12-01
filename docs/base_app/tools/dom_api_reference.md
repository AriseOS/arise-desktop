# DOM API 参考文档

## 概述

本文档详细介绍了 Ami 中用于 DOM 数据提取的统一 API 接口。这些 API 专为网页数据抓取场景设计，采用智能的分层过滤策略，提供了既精确又简洁的 DOM 数据提取能力。

## ✨ 新特性

### 智能分层过滤
- **内容元素**（有文本/链接/交互功能）：保留完整定位信息
- **容器元素**（纯结构）：只保留基本标签，大幅减少噪音

### 文本节点优化
- 文本内容直接合并到父元素的 `text` 属性
- 消除了独立 TEXT_NODE 带来的结构复杂性

### 统一数据视图
- 人类调试和 LLM 消费使用相同的简化数据
- 确保一致性，便于理解和维护

## 🚀 快速开始

```python
from base_app.base_agent.tools.browser_use.dom_extractor import (
    extract_dom_dict, extract_llm_view, DOMExtractor
)

# 1. 获取 DOM 数据源
extractor = DOMExtractor()
dom_state, enhanced_dom_tree, timing = await dom_service.get_serialized_dom_tree()

# 2. 生成智能简化的字典（内容元素保留完整信息，容器元素最小化）
visible_dom, _ = extractor.serialize_accessible_elements_custom(enhanced_dom_tree, include_non_visible=False)
simplified_dict = extract_dom_dict(visible_dom)

# 3. 生成 LLM 视图（与简化字典内容一致）
llm_view = extract_llm_view(simplified_dict)
print(llm_view)  # 输出紧凑的 JSON 字符串
```

## 📚 核心 API

### 1. `extract_dom_dict(serialized_dom)`

**功能**：将 SerializedDOM 转换为智能简化的 Python 字典结构，采用分层过滤策略。

**参数**：
- `serialized_dom`: SerializedDOM 对象（任何来源）

**返回**：
- `Dict`: 智能简化的嵌套字典结构

**分层过滤策略**：
- **内容元素**（有 text/href/src/interactive_index 等）：保留完整信息
- **容器元素**（纯结构 div/span 等）：只保留 tag + children

**示例**：
```python
dom_dict = extract_dom_dict(serialized_dom)

# 内容元素 - 完整信息
{
    "tag": "h1",
    "text": "商品标题",                    # 文本直接在元素上
    "structural_path": "html>body>div.container>h1.title",
    "class": "mp4t_0 mryx_0 mj7a_4",
    "id": "product-title"
}

# 容器元素 - 最小信息  
{
    "tag": "div",
    "children": [
        {
            "tag": "a", 
            "href": "/product/123",
            "text": "商品名称",               # 文本合并到链接元素
            "structural_path": "html>body>div>a.product-link",
            "interactive_index": 1
        }
    ]
}
```

### 2. `extract_llm_view(dom_dict)`

**功能**：将简化的DOM字典转换为紧凑的JSON字符串供LLM消费。

**重要变化**：现在与 `extract_dom_dict()` 返回完全相同的内容，只是格式不同（紧凑JSON vs 字典对象）。

**参数**：
- `dom_dict`: 来自 `extract_dom_dict()` 的简化字典

**返回**：
- `str`: 紧凑的 JSON 字符串

**示例**：
```python
# 1. 获取简化字典
dom_dict = extract_dom_dict(serialized_dom)

# 2. 转换为LLM格式（内容完全相同，只是JSON格式）
llm_view = extract_llm_view(dom_dict)

# 输出示例（紧凑格式）
{"tag":"h1","text":"商品标题","structural_path":"html>body>h1.title","class":"mp4t_0"}

# 人类调试格式
human_readable = json.dumps(dom_dict, indent=2, ensure_ascii=False)
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

### 智能分层过滤结构

DOM 字典现在采用智能的分层结构，根据元素价值提供不同密度的信息：

#### 内容元素（完整信息）
包含有价值数据的元素保留完整定位和属性信息：

```python
{
    "tag": "h1",                           # 元素类型
    "text": "商品标题",                       # 文本内容（直接合并）
    "structural_path": "html>body>h1.title", # 结构化定位路径
    "class": "mp4t_0 mryx_0",              # CSS类名
    "id": "product-title",                 # 元素ID
    "interactive_index": 1,                # 交互索引（如有）
    "href": "/product/123",                # 链接地址（如有）
    "children": [...]                      # 子元素
}
```

#### 容器元素（最小信息）
纯结构性的元素只保留基本标识：

```python
{
    "tag": "div",                          # 只保留标签类型
    "children": [...]                      # 和子元素结构
}
```

### 内容元素判断规则

元素被识别为"内容元素"的条件：
- 包含文本内容（`text` 字段非空）
- 具有交互能力（`interactive_index` 存在）  
- 包含重要属性（`href`, `src`, `alt`, `value` 等）
- 属于内容语义标签（`h1-h6`, `p`, `img`, `button`, `input`, `a` 等）

### 文本节点优化

**之前**：
```python
{
    "tag": "h1",
    "children": [
        {"tag": "text", "text": "商品标题"}  # 独立的文本节点
    ]
}
```

**现在**：
```python
{
    "tag": "h1", 
    "text": "商品标题"                        # 文本直接合并到父元素
}
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

1. **智能过滤的优势**：新的分层过滤策略大幅减少了数据量，提升了处理性能和LLM理解效率。

2. **按需提取**：只在需要时提取全量元素（`include_non_visible=True`），可见元素提取更快。

3. **缓存结果**：DOM 提取结果可以缓存，避免重复处理。

4. **减少Token消耗**：容器元素的最小化表示显著降低了LLM的Token使用量。

## 🔍 调试技巧

### 查看原始结构（推荐用于调试和日志）
```python
import json
# 人类可读格式，适用于调试、日志和文件保存
human_readable = json.dumps(dom_dict, indent=2, ensure_ascii=False)
print(human_readable)
```

### 对比格式化输出
```python
formatted_text = format_dict_as_text(dom_dict)
print("格式化文本:")
print(formatted_text)
```

### 验证 LLM 视图（仅用于大模型输入）
```python
import json
# 注意：llm_view 是紧凑格式，专为大模型设计，不适合人类阅读
llm_view = extract_llm_view(dom_dict)
meaningful_elements = json.loads(llm_view)
print(f"有意义元素数量: {len(meaningful_elements)}")

# 如果要查看内容，建议先格式化
for i, elem in enumerate(meaningful_elements[:5]):
    print(f"[{i+1}] {json.dumps(elem, ensure_ascii=False)}")
```

### 保存调试文件的最佳实践
```python
import json

# ✅ 推荐：保存到文件时使用人类可读格式
with open('debug_dom.json', 'w', encoding='utf-8') as f:
    json.dump(dom_dict, f, indent=2, ensure_ascii=False)

# ❌ 不推荐：不要将 llm_view 直接保存为调试文件
# llm_view 专为大模型设计，人类阅读困难
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

### v2.0.0 - 智能分层过滤 🎉
- **重大改进**：实现智能分层过滤策略
  - 内容元素：保留完整定位信息（text、href、structural_path等）
  - 容器元素：最小化表示（仅tag + children）
- **文本节点优化**：文本内容直接合并到父元素，消除独立TEXT_NODE
- **统一数据视图**：人类调试和LLM消费使用相同的简化数据
- **性能提升**：大幅减少数据量和Token消耗

### v1.0.0 - 统一DOM API
- 初始版本，统一的 DOM 提取 API
- 删除了旧的 `extract_scraping_data`、`extract_enhanced_data` 等接口
- 简化为 3 个核心函数：`extract_dom_dict`、`extract_llm_view`、`format_dict_as_text`