# Scroll Behavior Analysis - 用户滚动行为分析

## 概述

本文档分析用户在浏览器中的滚动（scroll）行为，识别不同的滚动意图，并提供相应的 workflow 生成策略。

---

## 用户 Scroll 行为分类

### **1. 数据加载类 Scroll（关键操作）**

#### **场景 1.1: 无限滚动加载（Infinite Scroll）**
```
用户意图：加载页面上的所有数据
典型网站：社交媒体、商品列表、搜索结果

用户行为模式：
- 连续向下滚动多次
- 每次滚动后有短暂停顿（等待加载）
- 滚动方向单一（向下）
- 滚动后通常伴随提取操作

示例：
scroll down → wait → scroll down → wait → scroll down → extract
```

**判断特征：**
- ✅ 多次同向滚动（3次以上向下）
- ✅ 滚动后有提取操作
- ✅ URL未改变
- ✅ 滚动距离较大且规律

**技术实现要点：**
- 需要 monitor 能检测到页面 DOM 变化（新内容加载）
- 需要记录滚动前后的 DOM 差异
- 需要识别动态加载的新元素

---

#### **场景 1.2: 触发懒加载（Lazy Loading）**
```
用户意图：让页面加载隐藏的内容（图片、组件）
典型网站：图片网站、长文章、产品详情页

用户行为模式：
- 滚动到特定位置
- 目标是让某些元素进入视口（viewport）
- 滚动后提取新出现的元素

示例：
scroll to element → extract (newly loaded content)
```

**判断特征：**
- ✅ 滚动到特定位置后停止
- ✅ 滚动后提取的内容之前不在 DOM 中
- ✅ 可能有 "Load More" 按钮触发

**技术实现要点：**
- 检测元素从不可见到可见的状态变化
- 检测 DOM 中新增的节点
- 记录元素进入视口的事件

---

### **2. 导航定位类 Scroll（中度关键）**

#### **场景 2.1: 滚动到目标元素**
```
用户意图：找到页面上的特定内容位置
典型场景：长页面中找到特定章节、滚动到评论区、找到"购买"按钮

用户行为模式：
- 滚动 → 停止 → 点击/提取
- 滚动距离不固定
- 目标是让某个元素可见

示例：
navigate → scroll down → click "Add to Cart"
navigate → scroll down → extract reviews section
```

**判断特征：**
- ✅ 滚动后立即有点击或提取操作
- ✅ 操作的元素在页面底部（需要滚动才能看到）
- ✅ 单次滚动，方向明确

**技术实现要点：**
- 通过 scroll + click 模式识别
- 通过 scroll + select/extract 模式识别
- 记录滚动后操作的目标元素位置（是否在初始视口外）

---

#### **场景 2.2: 滚动到页面顶部/底部**
```
用户意图：快速跳转到页面的起始或结束位置
典型场景：返回顶部、查看页脚信息、跳到评论区

用户行为模式：
- 大幅度滚动（scroll to top/bottom）
- 通常是单次操作
- 可能伴随点击"返回顶部"按钮

示例：
scroll to bottom → click "Load More"
scroll to top → click navigation menu
```

**判断特征：**
- ✅ 滚动距离很大（接近页面高度）
- ✅ 滚动后的操作在页面边缘位置
- ✅ direction: "up"/"down", distance: 大数值

**技术实现要点：**
- 记录滚动距离（scrollTop 变化量）
- 判断是否接近页面顶部（scrollTop ≈ 0）或底部（scrollTop + viewportHeight ≈ scrollHeight）

---

### **3. 浏览阅读类 Scroll（通常无意义）**

#### **场景 3.1: 随意浏览页面**
```
用户意图：随便看看，没有明确目标
典型场景：浏览新闻、查看产品详情、阅读文章

用户行为模式：
- 不规则滚动（上下反复）
- 滚动距离不固定
- 滚动后没有具体操作
- 停留时间较长（阅读）

示例：
scroll down → scroll up → scroll down → (无后续操作)
```

**判断特征：**
- ❌ 滚动方向不一致（上下反复）
- ❌ 滚动后没有点击/提取操作
- ❌ 不规律的滚动距离
- ❌ 时间间隔不均匀

**处理策略：** 这类滚动应该被**过滤掉**，不生成到 workflow

**技术实现要点：**
- 检测滚动方向变化（direction switching）
- 检测滚动后的操作窗口（如后续5秒内无操作 → 浏览）

---

#### **场景 3.2: 查看完整内容（预览）**
```
用户意图：快速浏览页面全貌，了解有什么内容
典型场景：首次访问页面、预览文档、查看商品详情

用户行为模式：
- 快速向下滚动到底部
- 可能再滚回顶部
- 没有提取或点击操作

示例：
navigate → scroll down (fast) → scroll up → (离开或执行其他操作)
```

**判断特征：**
- ❌ 滚动速度快（duration 短）
- ❌ 滚动后没有交互操作
- ❌ 往返滚动（down then up）

**处理策略：** 这类滚动应该被**忽略**

**技术实现要点：**
- 记录滚动持续时间（duration）
- 检测往返模式（down → up 或 up → down）

---

### **4. 交互触发类 Scroll（特殊场景）**

#### **场景 4.1: 触发悬浮菜单/工具栏**
```
用户意图：让页面显示隐藏的导航栏或工具
典型场景：滚动后出现"返回顶部"按钮、固定导航栏、悬浮购物车

用户行为模式：
- 滚动 → 等待UI元素出现 → 点击该元素

示例：
scroll down → click "Back to Top" (button appears after scroll)
```

**判断特征：**
- ✅ 滚动后点击的元素是动态出现的（scroll-triggered）
- ✅ 该元素的 className 可能包含 "fixed"、"sticky"、"float"

**技术实现要点：**
- 检测元素的 CSS 属性变化（display: none → block）
- 记录元素的出现时机（是否在滚动后出现）

---

#### **场景 4.2: 视频/轮播图进入视口**
```
用户意图：让视频/轮播图自动播放或加载
典型场景：滚动到视频位置触发自动播放

用户行为模式：
- 滚动到媒体元素位置
- 元素进入视口后自动播放/加载

示例：
scroll to video → (video auto-plays) → extract video info
```

**判断特征：**
- ✅ 滚动后操作的元素是 `<video>`、`<iframe>`、轮播图等
- ✅ 滚动距离精确（刚好让元素可见）

**技术实现要点：**
- 检测滚动后操作的元素类型（video, iframe 等）
- 记录元素进入视口事件

---

### **5. 验证确认类 Scroll（低频但重要）**

#### **场景 5.1: 检查表单提交结果**
```
用户意图：查看表单提交后的成功/错误提示
典型场景：填写表单 → 提交 → 滚动查看提示信息

用户行为模式：
- input → click submit → scroll to error/success message

示例：
input (email) → click "Submit" → scroll to top → extract error message
```

**判断特征：**
- ✅ 滚动发生在 click（提交按钮）之后
- ✅ 滚动到页面顶部（错误提示通常在顶部）
- ✅ 滚动后提取文本内容

**技术实现要点：**
- 检测滚动前的操作类型（是否是表单提交）
- 识别滚动目标（错误提示、成功消息的位置）

---

#### **场景 5.2: 确认内容加载完成**
```
用户意图：等待页面内容完全加载后再操作
典型场景：滚动验证新内容已加载

用户行为模式：
- click (Load More) → scroll down → verify new content → extract

示例：
click "Load More" → scroll → extract (newly loaded items)
```

**判断特征：**
- ✅ 滚动发生在点击"加载更多"之后
- ✅ 滚动后立即提取数据

**技术实现要点：**
- 检测滚动前的点击目标（Load More 按钮等）
- 检测滚动后的 DOM 变化

---

## **Scroll 分类总结**

| Scroll 类型 | 关键程度 | 是否保留 | 优化策略 | 判断特征 |
|------------|---------|---------|---------|---------|
| **无限滚动加载** | 🔥 P0 | ✅ 保留 | 转换为 `scroll_until_no_new_content` | 多次同向 + 后续提取 |
| **懒加载触发** | 🔥 P0 | ✅ 保留 | 保持单次滚动 | 滚动到特定位置 + 新内容出现 |
| **滚动到目标元素** | ⚠️ P1 | ✅ 保留 | 转换为 `scroll_to_element(xpath)` | 滚动后立即点击/提取 |
| **滚动到顶部/底部** | ⚠️ P1 | ✅ 保留 | `scroll_to_top`/`scroll_to_bottom` | 大距离滚动 + 边缘操作 |
| **随意浏览** | ❌ 无关 | ❌ 过滤 | 移除 | 不规则 + 无后续操作 |
| **预览内容** | ❌ 无关 | ❌ 过滤 | 移除 | 快速往返 + 无交互 |
| **触发UI元素** | ⚠️ P2 | ✅ 保留 | 保持原样 | 滚动后点击动态元素 |
| **视频/媒体触发** | ⚠️ P2 | ✅ 保留 | 保持原样 | 滚动到媒体元素 |
| **验证结果** | ⚠️ P2 | ✅ 保留 | 保持原样 | 提交后滚动 + 提取提示 |

---

## **Scroll 判断算法设计**

### **核心思路：**
基于上下文分析滚动操作的意图，判断是否应该保留以及如何优化。

### **算法流程：**

```python
def classify_scroll(scroll_op, operations_context):
    """
    判断 scroll 操作的意图和是否应该保留

    Args:
        scroll_op: 当前 scroll 操作
        operations_context: 前后操作序列
            {
                'previous': [op1, op2, op3],  # 前面3个操作
                'next': [op4, op5, op6]       # 后面3个操作
            }

    Returns:
        {
            'should_keep': bool,           # 是否保留该滚动操作
            'scroll_type': str,            # 滚动类型
            'optimization': str,           # 优化建议
            'reason': str                  # 判断理由
        }
    """

    # 获取上下文
    prev_ops = operations_context['previous']
    next_ops = operations_context['next']

    # 特征提取
    scroll_direction = scroll_op.get('direction')  # 'up' or 'down'
    scroll_distance = scroll_op.get('distance')    # 滚动距离（像素）
    scroll_duration = scroll_op.get('duration')    # 滚动持续时间（毫秒）

    # === 规则1: 检查是否是无限滚动加载 ===
    if is_infinite_scroll_pattern(scroll_op, prev_ops, next_ops):
        return {
            'should_keep': True,
            'scroll_type': 'infinite_scroll',
            'optimization': 'scroll_until_no_new_content',
            'reason': '检测到多次同向滚动 + 后续提取操作 + 页面动态加载内容'
        }

    # === 规则2: 检查是否滚动到目标元素（scroll + click/select） ===
    if has_immediate_interaction(next_ops):
        target_element = next_ops[0].get('element', {})
        target_xpath = target_element.get('xpath', '')
        return {
            'should_keep': True,
            'scroll_type': 'scroll_to_element',
            'optimization': f'scroll_to_element({target_xpath})',
            'reason': f'滚动后立即{next_ops[0].get("type")}目标元素'
        }

    # === 规则3: 检查是否是浏览式滚动（上下反复） ===
    if is_browsing_scroll(scroll_op, prev_ops, next_ops):
        return {
            'should_keep': False,
            'scroll_type': 'browsing',
            'optimization': 'remove',
            'reason': '检测到上下反复滚动或滚动后无交互操作'
        }

    # === 规则4: 检查是否是大幅度跳转 ===
    if is_large_jump(scroll_distance):
        optimization = 'scroll_to_top' if scroll_direction == 'up' else 'scroll_to_bottom'
        return {
            'should_keep': True,
            'scroll_type': 'large_jump',
            'optimization': optimization,
            'reason': f'大幅度{scroll_direction}滚动（距离: {scroll_distance}px）'
        }

    # === 规则5: 检查是否触发动态UI元素 ===
    if triggers_dynamic_ui(next_ops):
        return {
            'should_keep': True,
            'scroll_type': 'trigger_ui',
            'optimization': 'keep_original',
            'reason': '滚动后点击的元素是动态出现的（fixed/sticky）'
        }

    # === 规则6: 检查后续是否有交互操作（窗口期：5个操作内） ===
    if not has_interaction_within(next_ops, window=5):
        return {
            'should_keep': False,
            'scroll_type': 'casual_browsing',
            'optimization': 'remove',
            'reason': '滚动后5个操作内无任何交互，判定为浏览行为'
        }

    # === 默认：保守策略，保留但不优化 ===
    return {
        'should_keep': True,
        'scroll_type': 'unknown',
        'optimization': 'keep_original',
        'reason': '无法明确分类，保守保留'
    }


# ========== 辅助判断函数 ==========

def is_infinite_scroll_pattern(scroll_op, prev_ops, next_ops):
    """
    检测无限滚动模式

    特征：
    - 前后有多次同向滚动（>=3次）
    - 滚动后有提取操作
    - URL保持不变
    - 可能检测到DOM变化（新内容加载）
    """
    # 收集所有滚动操作
    all_ops = prev_ops + [scroll_op] + next_ops
    scroll_ops = [op for op in all_ops if op.get('type') == 'scroll']

    # 检查同向滚动次数
    same_direction_count = sum(
        1 for op in scroll_ops
        if op.get('direction') == scroll_op.get('direction')
    )

    # 检查滚动后是否有提取操作
    has_extract_after = any(
        op.get('type') in {'extract', 'select', 'copy_action'}
        for op in next_ops
    )

    # 检查URL是否保持不变
    current_url = scroll_op.get('url')
    url_unchanged = all(
        op.get('url') == current_url
        for op in prev_ops + next_ops
        if op.get('url')
    )

    # 检查是否有DOM变化记录（如果monitor支持）
    has_dom_change = scroll_op.get('data', {}).get('dom_changed', False)

    return (
        same_direction_count >= 3
        and has_extract_after
        and url_unchanged
    )


def has_immediate_interaction(next_ops):
    """
    检查后续是否立即有交互操作

    定义：接下来1-2个操作中有 click/extract/input/select
    """
    if not next_ops:
        return False

    immediate_ops = next_ops[:2]
    interaction_types = {'click', 'extract', 'input', 'select', 'copy_action'}

    return any(op.get('type') in interaction_types for op in immediate_ops)


def is_browsing_scroll(scroll_op, prev_ops, next_ops):
    """
    检测浏览式滚动（应该过滤）

    特征：
    - 方向变化（上下反复）
    - 后续无交互操作
    - 快速往返（duration短 + 方向反转）
    """
    # 收集所有滚动操作的方向
    all_scroll_ops = [op for op in prev_ops + [scroll_op] + next_ops if op.get('type') == 'scroll']
    directions = [op.get('direction') for op in all_scroll_ops]

    # 检查方向变化
    has_direction_change = 'up' in directions and 'down' in directions

    # 检查后续无交互
    no_interaction = not has_immediate_interaction(next_ops)

    # 检查快速往返模式
    if len(all_scroll_ops) >= 2:
        is_quick_return = (
            all_scroll_ops[0].get('direction') != all_scroll_ops[1].get('direction')
            and all_scroll_ops[0].get('duration', 1000) < 500
        )
    else:
        is_quick_return = False

    return has_direction_change or no_interaction or is_quick_return


def is_large_jump(scroll_distance):
    """
    判断是否是大幅度跳转

    阈值：滚动距离 > 视口高度的80%（假设视口高度 ~800px）
    """
    VIEWPORT_HEIGHT = 800  # 典型视口高度
    LARGE_JUMP_THRESHOLD = VIEWPORT_HEIGHT * 0.8

    return abs(scroll_distance) > LARGE_JUMP_THRESHOLD


def triggers_dynamic_ui(next_ops):
    """
    检查滚动后点击的元素是否是动态出现的

    判断依据：
    - 元素的 className 包含 fixed、sticky、float
    - 元素的 display 属性在滚动前后发生变化（需monitor支持）
    """
    if not next_ops or next_ops[0].get('type') != 'click':
        return False

    element = next_ops[0].get('element', {})
    class_name = element.get('className', '')

    dynamic_keywords = ['fixed', 'sticky', 'float', 'back-to-top', 'scroll-top']
    return any(keyword in class_name.lower() for keyword in dynamic_keywords)


def has_interaction_within(next_ops, window=5):
    """
    检查窗口期内是否有交互操作

    Args:
        next_ops: 后续操作列表
        window: 窗口大小（操作数量）

    Returns:
        bool: 窗口期内是否有交互
    """
    ops_in_window = next_ops[:window]
    interaction_types = {'click', 'extract', 'input', 'select', 'copy_action'}

    return any(op.get('type') in interaction_types for op in ops_in_window)
```

---

## **技术实现需求 - Monitor 支持**

为了准确判断 scroll 意图，需要 monitor（浏览器监控模块）提供以下能力：

### **1. DOM 变化检测**

**需求：** 检测滚动前后页面 DOM 的变化

**实现方式：**
```javascript
// 在浏览器端监控
let domSnapshot = {
    beforeScroll: null,
    afterScroll: null
};

// 滚动前记录 DOM 状态
function captureDOM() {
    return {
        elementCount: document.querySelectorAll('*').length,
        bodyHeight: document.body.scrollHeight,
        hash: generateDOMHash()  // 生成简单的DOM hash
    };
}

// 滚动后检测变化
window.addEventListener('scroll', debounce(() => {
    const beforeState = domSnapshot.beforeScroll;
    const afterState = captureDOM();

    const domChanged = (
        afterState.elementCount > beforeState.elementCount ||
        afterState.bodyHeight > beforeState.bodyHeight
    );

    // 记录到 operation 的 data 字段
    operation.data.dom_changed = domChanged;
    operation.data.new_element_count = afterState.elementCount - beforeState.elementCount;
}, 300));
```

**记录到 Operation：**
```yaml
- type: scroll
  direction: down
  distance: 800
  data:
    dom_changed: true              # DOM发生变化
    new_element_count: 12          # 新增12个元素
    body_height_change: 1200       # 页面高度增加1200px
```

---

### **2. 元素可见性检测**

**需求：** 记录滚动后哪些元素变为可见

**实现方式：**
```javascript
// 使用 Intersection Observer API
const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            // 元素进入视口
            recordElementVisible(entry.target);
        }
    });
});

// 监控关键元素（用户后续操作的目标）
function recordElementVisible(element) {
    operation.data.newly_visible_elements = operation.data.newly_visible_elements || [];
    operation.data.newly_visible_elements.push({
        xpath: getXPath(element),
        tagName: element.tagName,
        className: element.className,
        textContent: element.textContent.substring(0, 50)
    });
}
```

**记录到 Operation：**
```yaml
- type: scroll
  direction: down
  distance: 600
  data:
    newly_visible_elements:
      - xpath: "//button[@class='load-more']"
        tagName: "BUTTON"
        className: "load-more btn-primary"
        textContent: "Load More Products"
```

---

### **3. 滚动位置记录**

**需求：** 记录滚动前后的页面位置

**实现方式：**
```javascript
function recordScrollPosition() {
    return {
        scrollTop: window.scrollY,
        scrollHeight: document.body.scrollHeight,
        viewportHeight: window.innerHeight,
        scrollPercentage: (window.scrollY / (document.body.scrollHeight - window.innerHeight)) * 100
    };
}

// 记录滚动操作
operation.data.scroll_position = {
    before: recordScrollPosition(),  // 滚动前
    after: recordScrollPosition()    // 滚动后
};
```

**记录到 Operation：**
```yaml
- type: scroll
  direction: down
  distance: 800
  data:
    scroll_position:
      before:
        scrollTop: 0
        scrollHeight: 3000
        viewportHeight: 800
        scrollPercentage: 0
      after:
        scrollTop: 800
        scrollHeight: 3000
        viewportHeight: 800
        scrollPercentage: 36.4
```

---

### **4. 目标元素初始位置检测**

**需求：** 判断用户点击/提取的元素是否在初始视口内

**实现方式：**
```javascript
// 记录元素的位置信息
function isElementInViewport(element) {
    const rect = element.getBoundingClientRect();
    return (
        rect.top >= 0 &&
        rect.left >= 0 &&
        rect.bottom <= window.innerHeight &&
        rect.right <= window.innerWidth
    );
}

// 在记录 click/select 操作时
operation.element.was_in_initial_viewport = isElementInViewport(element);
operation.element.position_from_top = element.getBoundingClientRect().top + window.scrollY;
```

**记录到 Operation：**
```yaml
- type: click
  element:
    xpath: "//button[@id='add-to-cart']"
    was_in_initial_viewport: false     # 不在初始视口内
    position_from_top: 1500            # 距离页面顶部1500px
```

---

## **实施路线图**

### **Phase 1: 基础模式识别（立即实施）**

**目标：** 在 `IntentExtractor` 中添加基础 scroll 过滤

**实现内容：**
1. ✅ 识别 `scroll + click` 模式 → 保留
2. ✅ 识别 `scroll + select/extract` 模式 → 保留
3. ✅ 识别"上下反复滚动 + 无后续操作" → 过滤
4. ✅ 识别"多次同向滚动 + 提取" → 保留（无限滚动模式）

**修改文件：**
- `src/intent_builder/extractors/intent_extractor.py`

**不依赖 Monitor 增强：** 仅使用现有 operation 数据

---

### **Phase 2: Monitor 增强（中期实施）**

**目标：** 增强浏览器监控能力，支持更精确的意图识别

**实现内容：**
1. ⚠️ DOM 变化检测（检测新元素加载）
2. ⚠️ 元素可见性检测（Intersection Observer）
3. ⚠️ 滚动位置详细记录
4. ⚠️ 目标元素位置检测

**修改文件：**
- 浏览器监控脚本（monitor）
- `src/intent_builder/core/operation.py`（扩展 Operation 数据结构）

---

### **Phase 3: Workflow 优化（后期实施）**

**目标：** 在 `WorkflowGenerator` 中应用滚动优化规则

**实现内容：**
1. 📋 多次同向滚动 → `scroll_until_no_new_content`
2. 📋 滚动到特定元素 → `scroll_to_element(xpath)`
3. 📋 大幅度跳转 → `scroll_to_top`/`scroll_to_bottom`

**修改文件：**
- `src/intent_builder/generators/prompt_builder.py`（添加滚动优化规则）
- `src/intent_builder/generators/workflow_generator.py`

---

## **测试用例**

### **测试场景1: 无限滚动加载**
```
用户操作：
  navigate → scroll down → scroll down → scroll down → select (product list)

期望识别：
  scroll_type: infinite_scroll
  should_keep: true
  optimization: scroll_until_no_new_content

期望 Workflow:
  - browser_agent: navigate
  - browser_agent: scroll_until_no_new_content
  - scraper_agent: extract product list
```

---

### **测试场景2: 滚动到按钮并点击**
```
用户操作：
  navigate → scroll down → click "Add to Cart"

期望识别：
  scroll_type: scroll_to_element
  should_keep: true
  optimization: scroll_to_element(xpath)

期望 Workflow:
  - browser_agent: navigate
  - browser_agent: scroll_to_element("//button[@id='add-to-cart']")
  - browser_agent: click
```

---

### **测试场景3: 随意浏览（应过滤）**
```
用户操作：
  navigate → scroll down → scroll up → scroll down → (无操作)

期望识别：
  scroll_type: browsing
  should_keep: false
  optimization: remove

期望 Workflow:
  - browser_agent: navigate
  (滚动操作被完全移除)
```

---

### **测试场景4: 滚动后提取评论**
```
用户操作：
  navigate → scroll down → select (reviews section)

期望识别：
  scroll_type: scroll_to_element
  should_keep: true
  optimization: scroll_to_element(xpath)

期望 Workflow:
  - browser_agent: navigate
  - browser_agent: scroll_to_element("//div[@id='reviews']")
  - scraper_agent: extract reviews
```

---

## **关键讨论问题**

### **问题1: Monitor 能力边界**
- ✅ Monitor 能检测 DOM 变化吗？
- ✅ Monitor 能记录元素可见性变化吗？
- ✅ Monitor 能判断滚动前后页面状态差异吗？

### **问题2: 滚动模式识别**
- ✅ 是否可以通过 `scroll + click` 模式识别"滚动到目标元素"？
- ✅ 是否可以通过 `scroll + select` 模式识别"滚动到内容区"？
- ✅ 如何区分"无限滚动"和"随意浏览"？

### **问题3: 优化策略**
- ✅ 何时使用 `scroll_until_no_new_content`？
- ✅ 何时使用 `scroll_to_element(xpath)`？
- ✅ 是否需要支持 `scroll_by(distance)` 的精确控制？

---

## **参考文档**

- [Workflow Generation Strategy](./workflow_generation_strategy.md)
- [Intent Builder Architecture](./ARCHITECTURE.md)
- [BrowserAgent Spec](../baseagent/browser_agent_spec.md)
