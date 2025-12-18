# BrowserAgent 设计文档

**版本**: 2.0
**日期**: 2025-12-16
**状态**: 设计阶段

---

## 一、设计概述

### 1.1 设计目标

创建一个智能的浏览器交互 Agent，采用与 ScraperAgent 相同的"脚本生成 + 验证"模式：

- **核心职责**: 页面导航 + 智能交互（click、input、scroll、send_keys）
- **设计原则**: LLM 根据实际 DOM 生成操作脚本，而非硬编码 xpath
- **验证机制**: 执行后验证操作是否成功
- **协作方式**: 与 ScraperAgent 共享浏览器会话

### 1.2 与 ScraperAgent 的对比

| 特性 | ScraperAgent | BrowserAgent (v2) |
|------|-------------|-------------------|
| 核心功能 | 数据提取 | 页面交互 |
| 输入 | data_requirements + xpath_hints | task + xpath_hints |
| 脚本生成 | LLM 根据 DOM 生成提取脚本 | LLM 根据 DOM 生成操作脚本 |
| 验证方式 | 检查提取的数据是否符合格式 | 检查操作后页面是否变化 |
| 缓存策略 | 缓存脚本（同结构页面复用） | 不缓存（每次页面状态不同） |

### 1.3 架构位置

```
BaseStepAgent (抽象基类)
├── BrowserAgent (v2 - 智能交互)
│   ├── 职责: 导航 + 智能交互（click/input/scroll/send_keys）
│   ├── 输入: target_url + interaction_steps (task + xpath_hints)
│   ├── 脚本生成: LLM 根据 DOM + task 生成操作脚本
│   ├── 验证: LLM 对比前后 DOM 判断是否成功
│   └── 输出: success + current_url + message
│
├── ScraperAgent (现有，不改动)
│   ├── 职责: 导航 + 数据提取
│   └── 模式: DOM → LLM 生成脚本 → 执行 → 验证
│
└── 其他 Agent...
```

---

## 二、核心设计：智能脚本生成模式

### 2.1 为什么不使用硬编码 xpath？

**问题**：
- 硬编码的 xpath 可能在实际页面上不存在
- 页面更新后 xpath 可能失效
- 没有验证机制确保操作成功

**解决方案**：采用 ScraperAgent 的成功模式

```
workflow 定义意图 → 获取 DOM → LLM 生成脚本 → 执行 → 验证结果 → (失败则修复)
```

### 2.2 执行流程

```
┌─────────────────────────────────────────────────────────┐
│  Step 1: 执行前 - 获取 DOM + 生成脚本                    │
│  ├─ 调用 _get_current_page_dom() 获取页面 DOM           │
│  ├─ LLM 分析 DOM + task + xpath_hints                   │
│  └─ 生成操作脚本（定位元素 + 执行操作）                   │
├─────────────────────────────────────────────────────────┤
│  Step 2: 执行脚本                                        │
│  ├─ 从 DOM 中获取目标元素的 backend_node_id              │
│  ├─ 创建 Element 对象                                    │
│  └─ 执行 click() / fill() / send_keys()                 │
├─────────────────────────────────────────────────────────┤
│  Step 3: 执行后 - 验证结果                               │
│  ├─ 等待页面变化稳定                                     │
│  ├─ 再次调用 _get_current_page_dom() 获取新 DOM         │
│  ├─ LLM 对比前后 DOM + task 描述                        │
│  └─ 判断操作是否成功                                     │
├─────────────────────────────────────────────────────────┤
│  Step 4: 失败处理（可选）                                │
│  ├─ 分析失败原因                                         │
│  └─ 重试或调用 Claude Agent 修复                        │
└─────────────────────────────────────────────────────────┘
```

### 2.3 DOM 数据结构

复用 ScraperAgent 的 DOMExtractor，获取的 dom_dict 包含：

```python
{
    "tag": "button",
    "text": "Send Email",
    "xpath": "//*[@id='send-btn']",
    "backend_node_id": 12345,  # 关键：可直接用于操作
    "node_id": 67890,
    "interactive_index": 42,
    "class": "btn btn-primary",
    "id": "send-btn",
    "children": [...]
}
```

**关键点**：`backend_node_id` 可以直接用于创建 Element 对象执行操作。

---

## 三、数据结构设计

### 3.1 输入数据结构

```yaml
inputs:
  target_url: string              # 可选：目标 URL（如果省略则在当前页面操作）
  interaction_steps:              # 必需：交互步骤列表
    - task: string                # 必需：任务描述（LLM 用来理解意图和判断成功）
      xpath_hints:                # 必需：xpath 提示（帮助 LLM 定位元素）
        element_name: "xpath"
      text: string                # 可选：仅 input 操作需要
  timeout: int                    # 可选：超时时间（默认 60）
```

### 3.2 interaction_step 详细定义

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task` | string | ✅ | 任务描述，LLM 用来理解意图和判断成功 |
| `xpath_hints` | dict | ✅ | xpath 提示，帮助 LLM 定位目标元素 |
| `text` | string | ❌ | 仅 input 操作需要的文本内容 |

### 3.3 使用示例

**示例 1：发送邮件流程**

```yaml
- id: "send-email"
  agent_type: "browser_agent"
  name: "Send email via Outlook"
  inputs:
    target_url: "https://outlook.office.com/mail/"
    interaction_steps:
      - task: "点击'新建邮件'按钮"
        xpath_hints:
          button: "//button[@aria-label='New mail']"

      - task: "在收件人输入框中填写邮箱地址"
        xpath_hints:
          input: "//input[@aria-label='To']"
        text: "{{recipient_email}}"

      - task: "在邮件标题输入框中填写标题"
        xpath_hints:
          input: "//input[@aria-label='Subject']"
        text: "{{email_subject}}"

      - task: "在邮件正文区域填写内容"
        xpath_hints:
          editor: "//div[@role='textbox']"
        text: "{{email_body}}"

      - task: "点击发送按钮"
        xpath_hints:
          button: "//button[@aria-label='Send']"
  outputs:
    result: "send_result"
  timeout: 120
```

**示例 2：标记订单已处理**

```yaml
- id: "mark-order-done"
  agent_type: "browser_agent"
  name: "Mark order as processed"
  inputs:
    interaction_steps:
      - task: "点击'已反馈'按钮标记订单为已处理状态"
        xpath_hints:
          button: "//button[contains(@class, 'feedback-btn')]"
  outputs:
    result: "mark_result"
```

**示例 3：登录表单**

```yaml
- id: "login"
  agent_type: "browser_agent"
  name: "Login to system"
  inputs:
    target_url: "https://example.com/login"
    interaction_steps:
      - task: "在用户名输入框中填写用户名"
        xpath_hints:
          input: "//input[@name='username']"
        text: "{{username}}"

      - task: "在密码输入框中填写密码"
        xpath_hints:
          input: "//input[@name='password']"
        text: "{{password}}"

      - task: "点击登录按钮"
        xpath_hints:
          button: "//button[@type='submit']"
  outputs:
    result: "login_result"
```

### 3.4 输出数据结构

```yaml
{
  "success": true,
  "message": "All interaction steps completed successfully",
  "data": {
    "current_url": "https://outlook.office.com/mail/",
    "steps_executed": 5,
    "steps_results": [
      {
        "task": "点击'新建邮件'按钮",
        "success": true,
        "verification": "New mail compose window opened"
      },
      ...
    ]
  }
}
```

---

## 四、LLM 职责设计

### 4.1 脚本生成阶段

**输入**：
- DOM data（包含 xpath、backend_node_id 等）
- task 描述
- xpath_hints

**LLM 职责**：
1. 分析 DOM 结构，理解页面布局
2. 根据 xpath_hints 找到目标元素（可能需要适配实际 DOM）
3. 获取目标元素的 backend_node_id
4. 生成操作代码

**输出**：操作脚本

```python
# LLM 生成的脚本示例
def execute_interaction(dom_dict, browser_session):
    # 根据 xpath hints 和 DOM 分析，找到目标元素
    target_element = find_element_by_xpath(dom_dict, "//*[@id='send-btn']")

    if not target_element:
        # 尝试备选定位方式
        target_element = find_element_by_text(dom_dict, "Send")

    if not target_element:
        return {"success": False, "error": "Target element not found"}

    # 获取 backend_node_id
    backend_node_id = target_element.get("backend_node_id")

    # 执行点击
    element = Element(browser_session, backend_node_id)
    await element.click()

    return {"success": True, "element_clicked": target_element}
```

### 4.2 验证阶段

**输入**：
- 执行前的 DOM
- 执行后的 DOM
- task 描述

**LLM 职责**：
1. 对比前后 DOM 的变化
2. 根据 task 描述判断操作是否达到预期效果
3. 返回验证结果

**验证逻辑示例**：

| task | 验证标准 |
|------|---------|
| "点击'新建邮件'按钮" | 页面出现邮件编辑区域 |
| "在输入框中填写邮箱" | 输入框的 value 变为目标值 |
| "点击发送按钮" | 出现"已发送"提示或页面跳转 |
| "点击标记按钮" | 按钮状态变化或消失 |

---

## 五、技术实现细节

### 5.1 Element 操作方式

browser-use 的 Element 类提供的方法：

```python
# 通过 backend_node_id 创建 Element
element = Element(browser_session, backend_node_id, session_id)

# 可用操作
await element.click()           # 点击
await element.fill(text)        # 填充输入框（自动清空原内容）
await element.hover()           # 悬停
await element.focus()           # 聚焦
await element.select_option()   # 选择下拉选项
```

### 5.2 xpath 到 backend_node_id 的映射

```python
def find_element_by_xpath(dom_dict: Dict, target_xpath: str) -> Optional[Dict]:
    """在 dom_dict 中查找匹配 xpath 的元素"""

    def search_recursive(node: Dict) -> Optional[Dict]:
        # 检查当前节点的 xpath 是否匹配
        if node.get("xpath") == target_xpath:
            return node

        # 递归搜索子节点
        for child in node.get("children", []):
            result = search_recursive(child)
            if result:
                return result

        return None

    return search_recursive(dom_dict)
```

### 5.3 复用 ScraperAgent 的 DOM 获取逻辑

```python
async def _get_current_page_dom(self) -> tuple:
    """Get DOM from current page (复用 ScraperAgent 的实现)"""
    from browser_use.browser.events import BrowserStateRequestEvent
    from ..tools.browser_use.dom_extractor import DOMExtractor, extract_llm_view

    # 等待页面稳定
    await asyncio.sleep(3)

    # 获取 DOM
    event = self.browser_session.event_bus.dispatch(
        BrowserStateRequestEvent(include_dom=True, include_screenshot=False)
    )
    await event.event_result(raise_if_any=True)

    # 获取 enhanced DOM
    enhanced_dom = self.browser_session._dom_watchdog.enhanced_dom_tree

    # 转换为 dom_dict
    extractor = DOMExtractor()
    serialized_dom, _ = extractor.serialize_accessible_elements_custom(
        enhanced_dom, include_non_visible=True
    )
    dom_dict = extractor.extract_dom_dict(serialized_dom)
    llm_view = extract_llm_view(dom_dict, include_xpath=True)

    return serialized_dom, dom_dict, llm_view
```

---

## 六、与旧版本的对比

### 6.1 旧版本（v1）- 硬编码操作

```yaml
# 旧版本：只支持 scroll，硬编码参数
interaction_steps:
  - action_type: "scroll"
    parameters:
      down: true
      num_pages: 2
```

**问题**：
- 只支持 scroll
- 无法支持 click、input
- 没有验证机制

### 6.2 新版本（v2）- 智能脚本生成

```yaml
# 新版本：支持任意交互，LLM 智能生成脚本
interaction_steps:
  - task: "点击发送按钮"
    xpath_hints:
      button: "//button[@aria-label='Send']"
```

**优势**：
- 支持 click、input、scroll、send_keys
- LLM 根据实际 DOM 生成脚本
- 有验证机制确保操作成功
- xpath_hints 只是提示，LLM 可以适配实际 DOM

---

## 七、错误处理设计

### 7.1 错误类型

| 错误类型 | 触发条件 | 处理方式 |
|---------|---------|---------|
| **元素未找到** | xpath_hints 指定的元素不存在 | LLM 尝试备选定位方式 |
| **操作失败** | click/input 执行失败 | 重试或报告错误 |
| **验证失败** | 操作后页面未达到预期状态 | 记录详情，可选重试 |
| **超时** | 操作超过指定时间 | 返回超时错误 |

### 7.2 重试策略

```python
max_retries = 2

for attempt in range(max_retries + 1):
    # 生成脚本
    script = await generate_script(dom_dict, task, xpath_hints)

    # 执行脚本
    result = await execute_script(script)

    # 验证结果
    if await verify_result(task, dom_before, dom_after):
        return success_result

    if attempt < max_retries:
        logger.warning(f"Attempt {attempt + 1} failed, retrying...")
        await asyncio.sleep(1)

return failure_result
```

---

## 八、测试设计

### 8.1 单元测试

| 测试用例 | 测试内容 |
|---------|---------|
| test_find_element_by_xpath | xpath 查找元素 |
| test_script_generation | LLM 脚本生成 |
| test_click_execution | click 操作执行 |
| test_input_execution | input 操作执行 |
| test_verification | 操作验证 |

### 8.2 集成测试

| 测试用例 | 测试内容 |
|---------|---------|
| test_outlook_send_email | Outlook 发送邮件完整流程 |
| test_login_flow | 登录表单填写和提交 |
| test_mark_order | 订单标记操作 |

---

## 九、实现清单

### 9.1 需要实现的功能

| 功能 | 优先级 | 状态 |
|------|--------|------|
| DOM 获取（复用 ScraperAgent） | P0 | ⏳ 待实现 |
| xpath 到 backend_node_id 映射 | P0 | ⏳ 待实现 |
| Element 操作（click/fill） | P0 | ⏳ 待实现 |
| LLM 脚本生成 | P0 | ⏳ 待实现 |
| 操作验证 | P1 | ⏳ 待实现 |
| 失败重试 | P2 | ⏳ 待实现 |

### 9.2 代码文件

| 文件 | 路径 | 状态 |
|------|------|------|
| BrowserAgent 实现 | `src/clients/base_app/base_app/base_agent/agents/browser_agent.py` | ⏳ 待修改 |
| BrowserAgent 测试 | `tests/unit/baseagent/agents/test_browser_agent.py` | ⏳ 待更新 |

---

## 十、参考资料

### 10.1 相关代码

- ScraperAgent: `src/clients/base_app/base_app/base_agent/agents/scraper_agent.py`
- DOMExtractor: `src/clients/base_app/base_app/base_agent/tools/browser_use/dom_extractor.py`
- Element: `third-party/browser-use/browser_use/actor/element.py`

### 10.2 browser-use Element 方法

- `click()` - 点击元素
- `fill(value, clear=True)` - 填充输入框
- `hover()` - 悬停
- `focus()` - 聚焦
- `select_option(values)` - 选择下拉选项

---

**文档版本**: 2.0
**最后更新**: 2025-12-16
**作者**: Claude Code
