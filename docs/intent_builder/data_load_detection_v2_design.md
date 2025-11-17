# Data Load Detection V2 - 职责分离设计

## 1. 设计原则

### **职责分离**

| 模块 | 职责 | 不负责 |
|------|------|--------|
| **Browser (behavior_tracker.js)** | 检测并记录数据加载事件 | ❌ 不分析滚动意图 |
| **Monitor (monitor.py)** | 接收并存储 operations | ❌ 不做任何判断 |
| **Intent Builder** | 分析时间关联，判断意图 | ❌ 不检测 DOM 变化 |

### **核心思想**

1. **Browser 端只做检测**：当 DOM 变化 + 高度变化同时发生时，记录一个独立的 `dataload` operation
2. **Monitor 端只做记录**：忠实存储所有 operations
3. **Intent Builder 做分析**：基于时间序列，判断 scroll 和 dataload 的关联

---

## 2. 数据加载事件的定义

### **触发条件（AND 关系）**

必须**同时满足**以下两个条件：

```javascript
条件 1: DOM 发生变化
  - 新增元素数量 > 0
  - (可选) 新增的元素是"数据元素"

条件 2: 文档高度增加
  - document.body.scrollHeight 增加
  - 高度变化 > 阈值 (如 100px)
```

### **数据加载事件 (dataload) 的数据结构**

```python
{
    "type": "dataload",
    "timestamp": "2025-11-17 14:32:18",
    "url": "https://example.com/products",
    "page_title": "Products Page",
    "element": {},
    "data": {
        "added_elements_count": 12,        # 新增元素总数
        "data_elements_count": 8,          # 新增的"数据元素"数量
        "height_before": 3000,             # 变化前高度
        "height_after": 4200,              # 变化后高度
        "height_change": 1200,             # 高度变化量
        "sample_elements": [               # 样本元素（最多3个）
            {
                "tagName": "ARTICLE",
                "className": "product-item",
                "xpath": "//div[@id='products']/article[10]"
            },
            # ...
        ]
    }
}
```

---

## 3. Browser 端实现

### **3.1 DataLoadDetector 类设计**

**文件：** `behavior_tracker.js`

**职责：**
- 监控 DOM 变化 (MutationObserver)
- 监控文档高度变化
- 当两者同时发生时，上报 `dataload` operation

```javascript
class DataLoadDetector {
    constructor() {
        this.lastBodyHeight = document.body.scrollHeight;
        this.pendingMutations = [];  // 暂存 DOM 变化
        this.mutationTimeout = null;

        this.setupMutationObserver();
    }

    setupMutationObserver() {
        const observer = new MutationObserver((mutations) => {
            // 收集新增元素
            let addedElements = [];

            mutations.forEach(mutation => {
                if (mutation.type === 'childList') {
                    mutation.addedNodes.forEach(node => {
                        if (node.nodeType === Node.ELEMENT_NODE) {
                            addedElements.push(node);
                        }
                    });
                }
            });

            if (addedElements.length > 0) {
                this.handleDOMChange(addedElements);
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    handleDOMChange(addedElements) {
        // 检查高度是否变化
        const currentHeight = document.body.scrollHeight;
        const heightChange = currentHeight - this.lastBodyHeight;

        // 条件检查：DOM 变化 + 高度增加
        if (addedElements.length > 0 && heightChange > 100) {
            // 记录数据加载事件
            this.recordDataLoad(addedElements, heightChange, currentHeight);

            // 更新高度记录
            this.lastBodyHeight = currentHeight;
        }
    }

    recordDataLoad(addedElements, heightChange, currentHeight) {
        // 分析新增元素
        const dataElements = addedElements.filter(el => this.isDataElement(el));

        // 采样：最多记录 3 个元素
        const sampleElements = addedElements.slice(0, 3).map(el => ({
            tagName: el.tagName,
            className: el.className || '',
            xpath: getElementXPath(el)  // 复用现有函数
        }));

        // 上报 dataload operation
        collector.report('dataload', null, {
            added_elements_count: addedElements.length,
            data_elements_count: dataElements.length,
            height_before: this.lastBodyHeight,
            height_after: currentHeight,
            height_change: heightChange,
            sample_elements: sampleElements
        });
    }

    isDataElement(element) {
        const tag = element.tagName.toLowerCase();
        const classes = (element.className || '').toLowerCase();

        // 典型数据容器标签
        if (['article', 'li', 'tr'].includes(tag)) {
            return true;
        }

        // 典型数据容器 class
        const dataPatterns = ['item', 'card', 'post', 'product', 'entry', 'tile'];
        if (dataPatterns.some(pattern => classes.includes(pattern))) {
            return true;
        }

        return false;
    }
}
```

---

### **3.2 初始化检测器**

**位置：** `behavior_tracker.js` 文件末尾（IIFE 内部）

```javascript
(function() {
    // ... 现有代码 ...

    // 初始化数据加载检测器
    let detector;
    try {
        detector = new DataLoadDetector();
        console.log("🔍 DataLoadDetector initialized");
    } catch (e) {
        console.warn("Failed to initialize DataLoadDetector:", e);
    }

})();
```

---

### **3.3 Scroll Operation 保持简单**

**不需要修改** scroll 事件监听器，保持原样：

```javascript
window.addEventListener('scroll', function() {
    clearTimeout(scrollTimeout);
    scrollTimeout = setTimeout(function() {
        const currentScrollY = window.scrollY;
        const scrollDirection = currentScrollY > lastScrollY ? 'down' : 'up';
        const scrollDelta = Math.abs(currentScrollY - lastScrollY);

        if (scrollDelta > 50) {
            collector.report('scroll', null, {
                direction: scrollDirection,
                distance: scrollDelta
            });
            lastScrollY = currentScrollY;
        }
    }, 100);
});
```

**理由：**
- ✅ Browser 端只负责记录事件，不做关联分析
- ✅ 保持代码简洁
- ✅ 关联逻辑交给 Intent Builder

---

## 4. Monitor 端实现

### **4.1 添加 dataload 打印函数**

**文件：** `monitor.py`
**位置：** `_print_behavior_data()` 方法

```python
async def _print_behavior_data(self, payload: str) -> None:
    try:
        data = json.loads(payload)

        # ... 现有代码 ...

        # Print detailed information based on behavior type
        if data['type'] == 'click':
            self._print_click_details(data)
        elif data['type'] == 'input':
            self._print_input_details(data)
        # ... 其他类型 ...
        elif data['type'] == 'dataload':
            self._print_dataload_details(data)  # 新增

        print("-" * 60)

    except Exception as e:
        logger.error(f"Failed to process behavior data: {e}")
```

---

### **4.2 实现 _print_dataload_details()**

**文件：** `monitor.py`
**位置：** 在其他 `_print_*_details()` 方法附近

```python
def _print_dataload_details(self, data):
    """Print data load event details"""
    user_data = data.get('data', {})

    added_count = user_data.get('added_elements_count', 0)
    data_count = user_data.get('data_elements_count', 0)
    height_change = user_data.get('height_change', 0)

    print(f"  📊 Data Load Detected")
    print(f"     New Elements: {added_count} total, {data_count} data elements")
    print(f"     Height Change: +{height_change}px")
    print(f"     Height: {user_data.get('height_before', 0)}px → {user_data.get('height_after', 0)}px")

    # 打印样本元素
    sample_elements = user_data.get('sample_elements', [])
    if sample_elements:
        print(f"     Sample Elements:")
        for i, elem in enumerate(sample_elements[:3], 1):
            tag = elem.get('tagName', 'UNKNOWN')
            cls = elem.get('className', '')
            print(f"       {i}. <{tag}> class=\"{cls}\"")
```

---

## 5. Intent Builder 端实现

### **5.1 滚动与数据加载的时间关联分析**

**文件：** `intent_extractor.py`

**核心逻辑：**

```python
def analyze_scroll_intent(self, operations):
    """
    分析滚动操作的意图

    Args:
        operations: 完整的操作序列

    Returns:
        filtered_operations: 过滤后的操作列表
    """
    filtered_ops = []

    for i, op in enumerate(operations):
        if op['type'] == 'scroll':
            # 检查滚动后是否有数据加载
            has_dataload = self._check_dataload_after_scroll(
                scroll_op=op,
                operations=operations,
                current_index=i
            )

            if has_dataload:
                # 滚动触发了数据加载 → 保留
                filtered_ops.append(op)
            else:
                # 检查滚动后是否有交互操作
                has_interaction = self._check_interaction_after_scroll(
                    operations=operations,
                    current_index=i
                )

                if has_interaction:
                    # 滚动后有点击/选择 → 保留
                    filtered_ops.append(op)
                else:
                    # 普通浏览滚动 → 过滤
                    logger.debug(f"Filtering browsing scroll at index {i}")

        elif op['type'] == 'dataload':
            # dataload 事件本身不需要生成 Intent
            # 只用于辅助判断 scroll 意图
            pass

        else:
            # 其他操作直接保留
            filtered_ops.append(op)

    return filtered_ops
```

---

### **5.2 检查滚动后的数据加载**

```python
def _check_dataload_after_scroll(self, scroll_op, operations, current_index):
    """
    检查滚动后是否有数据加载事件

    时间窗口：滚动后 3 秒内
    """
    scroll_time = self._parse_timestamp(scroll_op['timestamp'])

    # 查看后续 10 个操作（或到列表末尾）
    window_ops = operations[current_index + 1 : current_index + 11]

    for op in window_ops:
        if op['type'] == 'dataload':
            dataload_time = self._parse_timestamp(op['timestamp'])

            # 计算时间差（秒）
            time_diff = (dataload_time - scroll_time).total_seconds()

            # 在 3 秒窗口内
            if 0 <= time_diff <= 3.0:
                logger.info(f"Scroll at {scroll_time} triggered dataload at {dataload_time} (delay: {time_diff:.2f}s)")
                return True

    return False
```

---

### **5.3 检查滚动后的交互操作**

```python
def _check_interaction_after_scroll(self, operations, current_index):
    """
    检查滚动后是否有交互操作 (click, select, extract)

    时间窗口：滚动后立即（后续 1-3 个操作内）
    """
    # 查看后续 3 个操作
    window_ops = operations[current_index + 1 : current_index + 4]

    interaction_types = {'click', 'select', 'copy_action', 'extract', 'input'}

    for op in window_ops:
        if op['type'] in interaction_types:
            return True

    return False
```

---

### **5.4 时间戳解析**

```python
from datetime import datetime

def _parse_timestamp(self, timestamp_str):
    """
    解析时间戳字符串

    支持格式：
    - "2025-11-17 14:32:18"
    - ISO 格式
    """
    try:
        # 格式：YYYY-MM-DD HH:MM:SS
        return datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        try:
            # 尝试 ISO 格式
            return datetime.fromisoformat(timestamp_str.replace(' ', 'T'))
        except:
            logger.warning(f"Failed to parse timestamp: {timestamp_str}")
            return datetime.now()
```

---

## 6. 操作序列示例

### **场景 1: 无限滚动 (保留)**

```python
operations = [
    {
        "type": "navigate",
        "timestamp": "2025-11-17 14:30:00",
        "url": "https://example.com/products"
    },
    {
        "type": "scroll",
        "timestamp": "2025-11-17 14:30:05",
        "data": {"direction": "down", "distance": 800}
    },
    {
        "type": "dataload",  # 滚动后 1.2 秒触发
        "timestamp": "2025-11-17 14:30:06.2",
        "data": {
            "added_elements_count": 10,
            "height_change": 1500
        }
    },
    {
        "type": "scroll",
        "timestamp": "2025-11-17 14:30:10",
        "data": {"direction": "down", "distance": 800}
    },
    {
        "type": "dataload",  # 滚动后 0.8 秒触发
        "timestamp": "2025-11-17 14:30:10.8",
        "data": {
            "added_elements_count": 10,
            "height_change": 1500
        }
    },
    {
        "type": "select",
        "timestamp": "2025-11-17 14:30:15",
        "data": {"selectedText": "Product Title"}
    }
]

# Intent Builder 分析：
# - scroll #1: 后续有 dataload → 保留
# - scroll #2: 后续有 dataload → 保留
# - dataload 事件本身不生成 Intent
```

---

### **场景 2: 浏览滚动 (过滤)**

```python
operations = [
    {
        "type": "navigate",
        "timestamp": "2025-11-17 14:30:00",
        "url": "https://example.com/article"
    },
    {
        "type": "scroll",
        "timestamp": "2025-11-17 14:30:05",
        "data": {"direction": "down", "distance": 300}
    },
    {
        "type": "scroll",
        "timestamp": "2025-11-17 14:30:08",
        "data": {"direction": "up", "distance": 200}
    },
    {
        "type": "scroll",
        "timestamp": "2025-11-17 14:30:10",
        "data": {"direction": "down", "distance": 400}
    }
    # 无 dataload，无交互操作
]

# Intent Builder 分析：
# - scroll #1: 无 dataload，无交互 → 过滤
# - scroll #2: 无 dataload，无交互 → 过滤
# - scroll #3: 无 dataload，无交互 → 过滤
```

---

### **场景 3: 滚动到元素并点击 (保留)**

```python
operations = [
    {
        "type": "navigate",
        "timestamp": "2025-11-17 14:30:00",
        "url": "https://example.com/page"
    },
    {
        "type": "scroll",
        "timestamp": "2025-11-17 14:30:05",
        "data": {"direction": "down", "distance": 600}
    },
    {
        "type": "click",  # 滚动后立即点击
        "timestamp": "2025-11-17 14:30:06",
        "element": {
            "xpath": "//button[@id='submit']",
            "tagName": "BUTTON"
        }
    }
]

# Intent Builder 分析：
# - scroll: 后续有 click → 保留（滚动到按钮）
```

---

## 7. 实施计划

### **Phase 1: Browser 端实现 (1-2 天)**

#### **任务 1.1: 实现 DataLoadDetector 类**
- **文件：** `behavior_tracker.js`
- **内容：**
  - MutationObserver 监控
  - 高度变化检测
  - isDataElement() 判断
  - recordDataLoad() 上报

#### **任务 1.2: 初始化检测器**
- **文件：** `behavior_tracker.js`
- **位置：** IIFE 末尾
- **代码：** `const detector = new DataLoadDetector();`

#### **任务 1.3: 测试 dataload 事件上报**
- 手动测试无限滚动网站
- 验证 dataload operation 是否正确上报

---

### **Phase 2: Monitor 端实现 (0.5 天)**

#### **任务 2.1: 添加 dataload 打印**
- **文件：** `monitor.py`
- **方法：** `_print_dataload_details()`
- **验证：** 运行 BaseApp，查看控制台输出

---

### **Phase 3: Intent Builder 实现 (1-2 天)**

#### **任务 3.1: 实现滚动分析逻辑**
- **文件：** `intent_extractor.py`
- **方法：**
  - `analyze_scroll_intent()`
  - `_check_dataload_after_scroll()`
  - `_check_interaction_after_scroll()`

#### **任务 3.2: 集成到现有 Intent 提取流程**
- 在 `extract_intents()` 中调用 `analyze_scroll_intent()`
- 使用过滤后的 operations 进行 Intent 提取

#### **任务 3.3: 测试端到端流程**
- 录制无限滚动操作
- 验证滚动过滤是否正确
- 验证生成的 Intent 是否准确

---

## 8. 配置参数

### **可调整的参数**

```javascript
// behavior_tracker.js
class DataLoadDetector {
    constructor(options = {}) {
        // 高度变化阈值（px）
        this.heightChangeThreshold = options.heightThreshold || 100;

        // 是否启用数据元素过滤
        this.filterDataElements = options.filterElements || false;
    }
}
```

```python
# intent_extractor.py
class IntentExtractor:
    def __init__(self):
        # 数据加载时间窗口（秒）
        self.dataload_time_window = 3.0

        # 交互操作查看范围（操作数）
        self.interaction_window_size = 3
```

---

## 9. 测试策略

### **9.1 单元测试**

**Browser 端：**
```javascript
// 测试 DataLoadDetector.isDataElement()
const article = document.createElement('article');
console.assert(detector.isDataElement(article) === true);

const div = document.createElement('div');
console.assert(detector.isDataElement(div) === false);

const productDiv = document.createElement('div');
productDiv.className = 'product-item';
console.assert(detector.isDataElement(productDiv) === true);
```

**Intent Builder 端：**
```python
def test_check_dataload_after_scroll():
    operations = [
        {'type': 'scroll', 'timestamp': '2025-11-17 14:30:00'},
        {'type': 'dataload', 'timestamp': '2025-11-17 14:30:01.5'}  # 1.5秒后
    ]

    extractor = IntentExtractor()
    result = extractor._check_dataload_after_scroll(
        scroll_op=operations[0],
        operations=operations,
        current_index=0
    )

    assert result == True
```

---

### **9.2 集成测试**

**测试场景：**
1. **ProductHunt 无限滚动**
   - 操作：连续滚动 3 次
   - 期望：3 个 scroll + 3 个 dataload
   - 验证：所有 scroll 都被保留

2. **Wikipedia 文章浏览**
   - 操作：上下滚动阅读
   - 期望：多个 scroll + 0 个 dataload
   - 验证：所有 scroll 都被过滤

3. **表单页面滚动到按钮**
   - 操作：滚动 + 点击提交按钮
   - 期望：1 个 scroll + 1 个 click
   - 验证：scroll 被保留（有后续交互）

---

## 10. 优势与权衡

### **设计优势**

✅ **职责清晰**：Browser 检测，Monitor 记录，Intent Builder 分析
✅ **易于调试**：每个模块独立，问题容易定位
✅ **灵活性高**：时间窗口等参数可在 Intent Builder 调整，无需改 JS
✅ **可扩展**：未来可添加更多事件类型（如 network request）
✅ **数据完整**：所有原始事件都被保留，方便后续分析

### **权衡**

⚠️ **存储开销**：增加了 dataload 事件的存储
⚠️ **时间窗口**：需要合理设置，避免误判
⚠️ **复杂度**：Intent Builder 需要处理时间关联逻辑

---

## 11. 后续优化方向

### **11.1 Network Request 监控（可选增强）**

```javascript
// 监听网络请求完成
const originalFetch = window.fetch;
window.fetch = function(...args) {
    return originalFetch.apply(this, args).then(response => {
        if (response.ok && response.headers.get('content-type')?.includes('json')) {
            // 记录数据请求事件
            collector.report('datarequest', null, {
                url: args[0],
                status: response.status
            });
        }
        return response;
    });
};
```

### **11.2 Element Visibility 监控（可选增强）**

```javascript
// 监控元素进入视口
const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            collector.report('element_visible', entry.target, {});
        }
    });
});
```

---

## 12. 总结

### **核心要点**

1. ✅ **Browser 端**：检测 DOM 变化 + 高度变化，记录独立的 `dataload` 事件
2. ✅ **Monitor 端**：接收并存储所有 operations（scroll + dataload）
3. ✅ **Intent Builder**：分析时间序列，判断 scroll 和 dataload 的关联

### **关键参数**

- **高度变化阈值：** 100px
- **时间窗口：** 3 秒
- **交互操作范围：** 后续 3 个操作

### **预期效果**

- 准确识别数据加载型滚动
- 有效过滤无意义浏览滚动
- 为 Workflow 生成提供可靠依据

---

## 附录：完整数据流示例

```
用户操作：滚动 ProductHunt 页面

1. 用户滚动 → Browser 端
   ↓
   scroll event handler 触发
   ↓
   上报: { type: 'scroll', timestamp: '14:30:00', direction: 'down', distance: 800 }

2. 页面加载新数据 → Browser 端
   ↓
   MutationObserver 检测到 10 个新元素
   ↓
   高度从 3000px 增加到 4500px (+1500px)
   ↓
   DataLoadDetector.handleDOMChange() 判断：✅ 满足条件
   ↓
   上报: { type: 'dataload', timestamp: '14:30:01.2', added_elements_count: 10, height_change: 1500 }

3. Monitor 接收 → Python 端
   ↓
   operation_list = [
       { type: 'scroll', timestamp: '14:30:00', ... },
       { type: 'dataload', timestamp: '14:30:01.2', ... }
   ]

4. Intent Builder 分析 → Python 端
   ↓
   analyze_scroll_intent() 遍历 operations
   ↓
   检查 scroll 后是否有 dataload：
     时间差 = 1.2 秒 < 3 秒 → ✅ 有关联
   ↓
   判断：这是数据加载型滚动 → 保留

5. 生成 Intent
   ↓
   Intent: "Scroll down to load more products"
   ↓
   Workflow: scroll_until_no_new_content
```
