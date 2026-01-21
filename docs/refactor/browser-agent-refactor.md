# Browser Agent 改造方案（简化版）

## 背景

### 当前问题

在 foreach 循环场景中，browser_agent 无法正确处理动态 xpath：

```yaml
- foreach: "{{product_list}}"
  as: product
  do:
    - id: click-product
      agent: browser_agent
      inputs:
        interaction_steps:
          - task: "Click on product"
            xpath_hints:
              product: "{{product.xpath}}"   # 每次迭代值不同
```

**问题**：
1. `find_element.py` 的函数签名是 `find_target_element(dom_dict)` —— 不接受 xpath 参数
2. 脚本中的搜索条件是写死的（如 `'submit' in text`）
3. 即使 xpath 每次迭代不同，脚本逻辑不变，永远返回相同的元素

---

## 简化方案

### 核心思路

**不再让 Claude 生成复杂的动态脚本**，而是：

1. 函数签名添加 `xpath` 参数
2. 默认使用 `element_tools.py` 的 `hint` 方法直接查找
3. 如果 `hint` 能找到可交互元素 → 生成简单的包装脚本
4. 如果 `hint` 找不到 → 标记为 fallback 模式，每次都用 LLM 实时判断

### 新的查找流程

```
┌─────────────────────────────────────────────────────────┐
│ 1. 调用 analyze_xpath_hint(dom, xpath)                  │
│    (复用 element_tools.py 的 hint 逻辑)                 │
└─────────────────────────────────────────────────────────┘
                          ↓
              hint 返回 interactive_match?
                    ↓              ↓
                   有              无
                    ↓              ↓
         生成简单包装脚本      标记 fallback 模式
         (直接调用 hint)      (每次用 LLM 判断)
```

---

## 详细设计

### 1. 新的函数签名

```python
# 之前
def find_target_element(dom_dict: dict) -> dict:

# 之后
def find_target_element(dom_dict: dict, xpath: str) -> dict:
```

### 2. 生成的脚本（简化版）

**关键变化**：脚本不再包含复杂的搜索逻辑，而是直接调用 `element_tools.py` 的 `analyze_xpath_hint`

```python
#!/usr/bin/env python3
"""Find target element using hint-based search"""
import json
import sys
from pathlib import Path

# 导入 element_tools
tools_path = Path(__file__).parent / ".claude/skills/element-finder/tools"
sys.path.insert(0, str(tools_path))
from element_tools import analyze_xpath_hint

def find_target_element(dom_dict: dict, xpath: str) -> dict:
    """
    使用 hint 方法查找目标元素

    Args:
        dom_dict: DOM 字典
        xpath: 运行时传入的 xpath

    Returns:
        {success: bool, interactive_index: int, ...}
    """
    if not xpath:
        return {"success": False, "error": "No xpath provided"}

    # 直接调用 hint 分析
    result = analyze_xpath_hint(dom_dict, xpath)

    # 检查是否找到可交互元素
    match = result.get('interactive_match')
    if match and match.get('interactive_index') is not None:
        return {
            "success": True,
            "interactive_index": match['interactive_index'],
            "element_info": {
                "tag": match.get("tag"),
                "text": match.get("text", "")[:100],
                "xpath": match.get("xpath"),
                "class": match.get("class")
            }
        }

    # hint 找不到，返回错误触发 fallback
    return {
        "success": False,
        "error": "Cannot find interactive element via hint, fallback required",
        "hint_result": result  # 包含分析结果供调试
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python find_element.py '<xpath>'")
        sys.exit(1)

    xpath = sys.argv[1]

    with open("dom_data.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    dom = data.get("dom", data)
    result = find_target_element(dom, xpath)
    print(json.dumps(result, indent=2, ensure_ascii=False))
```

### 3. Claude Agent 的新职责

**之前**：分析 DOM，生成复杂的搜索脚本

**之后**：
1. 读取 task.json 获取 xpath_hints
2. 用 `hint` 命令测试 xpath 是否能找到元素
3. 如果能找到 → 输出标准的包装脚本（上面的模板）
4. 如果找不到 → 输出一个返回 fallback 错误的脚本

### 4. Fallback 模式

当 `find_element.py` 返回 `"fallback required"` 错误时：

```python
def _find_element_with_fallback(self, dom_dict: Dict, xpath: str, task: str) -> Dict:
    """
    先尝试脚本，失败则 fallback 到 LLM
    """
    # 1. 尝试执行脚本
    script_result = self._execute_find_element_script(script, dom_dict, xpath)

    if script_result.get("success"):
        return script_result

    # 2. Fallback: 调用 LLM 实时判断
    return self._llm_find_element(dom_dict, xpath, task)


def _llm_find_element(self, dom_dict: Dict, xpath: str, task: str) -> Dict:
    """
    使用 LLM 直接分析 DOM 并返回 interactive_index

    这个方法每次调用都会消耗 LLM tokens，但能处理复杂场景
    """
    prompt = f"""
    Task: {task}
    XPath hint: {xpath}

    Analyze the DOM and find the target interactive element.
    Return the interactive_index of the element to click/fill.

    DOM:
    {json.dumps(dom_dict, indent=2)[:50000]}  # 截断避免太长
    """

    # 调用 LLM
    response = self.llm.complete(prompt)

    # 解析 LLM 返回的 interactive_index
    ...
```

### 5. 缓存策略调整

```python
def _is_cache_valid(self, working_dir: Path, task: str, xpath_hints: Dict[str, str]) -> bool:
    """
    缓存验证：
    - task 相同
    - xpath_hints 的 KEY 相同（不比较 VALUE）
    - 没有标记为 fallback 模式
    """
    # 检查是否是 fallback 模式
    fallback_marker = working_dir / ".fallback_mode"
    if fallback_marker.exists():
        return False  # fallback 模式不使用缓存，每次都用 LLM

    # 只比较 xpath_hints 的 keys
    current_keys = sorted(xpath_hints.keys())
    saved_keys = sorted(saved_xpath_hints.keys())

    return current_keys == saved_keys and task == saved_task_desc
```

当脚本返回 fallback 错误时，创建 `.fallback_mode` 标记文件：

```python
if "fallback required" in result.get("error", ""):
    (working_dir / ".fallback_mode").touch()
```

---

## 需要修改的代码

### 1. browser_agent.py

**文件位置**: `src/clients/desktop_app/ami_daemon/base_agent/agents/browser_agent.py`

| 修改点 | 行号 | 描述 |
|--------|------|------|
| `_execute_find_element_script()` | 1595-1627 | 添加 `xpath` 参数，注入 `analyze_xpath_hint` 函数 |
| 缓存命中调用 | 1159 | 传入 xpath 到脚本执行 |
| 生成后执行调用 | 1361 | 传入 xpath 到脚本执行 |
| `_is_cache_valid()` | 579-619 | 只比较 xpath_hints 的 keys |
| 新增 `_llm_find_element()` | - | LLM fallback 实现 |
| 新增 `_find_element_with_fallback()` | - | 整合脚本执行和 fallback |
| 删除重复模板 | 146-457 | 删除 `PRESET_TEST_OPERATION`, `PRESET_FIND_ELEMENT_TEMPLATE` 等类属性（已从 templates.py 导入） |
| `_scroll_to_element_with_claude()` | 2032+ | 添加 `SkillManager.prepare_browser_skills(working_dir)` 调用 |

#### 1.1 exec() 环境注入

**关键问题**：当前 `exec()` 执行环境无法直接导入 `element_tools`，因为：
- `__file__` 在 exec 中不存在
- 当前工作目录不是 `working_dir`
- 相对路径无法工作

**解决方案**：在 `_execute_find_element_script()` 中注入 `analyze_xpath_hint` 函数：

```python
def _execute_find_element_script(self, code: str, dom_dict: Dict, xpath: str) -> Dict:
    """Execute find_element.py to get target element info"""
    try:
        # 导入 element_tools（在 agent 层导入，而非脚本内）
        from src.cloud_backend.services.skills.repository.element_finder.tools.element_tools import analyze_xpath_hint

        # 创建执行环境，注入所需函数
        exec_env = {
            'dom_dict': dom_dict,
            'xpath': xpath,
            'analyze_xpath_hint': analyze_xpath_hint,  # 注入到执行环境
            'json': json,
        }

        exec(code, exec_env, exec_env)

        find_target_element = exec_env.get('find_target_element')
        if not find_target_element:
            return {'success': False, 'error': 'Script missing find_target_element function'}

        # 传入 xpath 参数
        result = find_target_element(dom_dict, xpath)
        return result

    except Exception as e:
        return {'success': False, 'error': f'Script execution failed: {str(e)}'}
```

#### 1.2 scroll_to_element 改造

`_scroll_to_element_with_claude()` (Line 1980+) 需要添加 skills 准备：

```python
# Step 4: Prepare workspace for Claude Agent (Line 2032+)
task_info = {...}
(working_dir / "task.json").write_text(...)

# 新增: 准备 element-finder skills
SkillManager.prepare_browser_skills(working_dir, use_symlink=True)

# Save template
(working_dir / "find_xpath_template.py").write_text(...)
```

### 2. templates.py

**文件位置**: `src/common/script_generation/templates.py`

| 修改点 | 描述 |
|--------|------|
| `BROWSER_FIND_ELEMENT_TEMPLATE` | 改为简单包装，使用注入的 `analyze_xpath_hint` |
| `BROWSER_TEST_OPERATION` | 测试时传入 sample xpath |
| `BROWSER_AGENT_PROMPT` | 简化，告诉 Claude 用 hint 方法 |

#### 2.1 新的 BROWSER_FIND_ELEMENT_TEMPLATE

```python
BROWSER_FIND_ELEMENT_TEMPLATE = '''#!/usr/bin/env python3
"""Find target element using hint-based search

Note: analyze_xpath_hint is injected by the execution environment,
do not import it manually.
"""

def find_target_element(dom_dict: dict, xpath: str) -> dict:
    """Find target element using hint method

    Args:
        dom_dict: DOM dictionary
        xpath: Runtime xpath from xpath_hints

    Returns:
        dict with success, interactive_index, element_info
    """
    if not xpath:
        return {"success": False, "error": "No xpath provided"}

    # analyze_xpath_hint is injected by exec environment
    result = analyze_xpath_hint(dom_dict, xpath)

    match = result.get('interactive_match')
    if match and match.get('interactive_index') is not None:
        return {
            "success": True,
            "interactive_index": match['interactive_index'],
            "element_info": {
                "tag": match.get("tag"),
                "text": match.get("text", "")[:100],
                "xpath": match.get("xpath"),
                "class": match.get("class")
            }
        }

    return {
        "success": False,
        "error": "Cannot find interactive element via hint, fallback required",
        "hint_result": result
    }
'''
```

#### 2.2 新的 BROWSER_TEST_OPERATION

```python
BROWSER_TEST_OPERATION = '''#!/usr/bin/env python3
"""Test script - Validates find_element.py with xpath parameter"""
import json
import sys

def test():
    # Load DOM
    with open("dom_data.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    dom_dict = data.get("dom", data)

    # Load task to get sample xpath
    with open("task.json", "r", encoding="utf-8") as f:
        task = json.load(f)

    xpath_hints = task.get("xpath_hints", {})
    sample_xpath = list(xpath_hints.values())[0] if xpath_hints else ""

    # Import find_element
    from find_element import find_target_element

    # Note: In test mode, we need to provide analyze_xpath_hint
    # This is normally injected by browser_agent's exec environment
    sys.path.insert(0, ".claude/skills/element-finder/tools")
    from element_tools import analyze_xpath_hint

    # Inject into module globals for testing
    import find_element
    find_element.analyze_xpath_hint = analyze_xpath_hint

    result = find_target_element(dom_dict, sample_xpath)

    if result.get("success"):
        print(f"SUCCESS: interactive_index = {result.get('interactive_index')}")
        return True
    else:
        print(f"FAILED: {result.get('error')}")
        return False

if __name__ == "__main__":
    sys.exit(0 if test() else 1)
'''
```

### 3. element-finder/SKILL.md

**文件位置**: `src/cloud_backend/services/skills/repository/element-finder/SKILL.md`

更新反映新的简化设计：

```markdown
# Element Finder (Simplified)

## Goal

Generate `find_element.py` that uses `analyze_xpath_hint` to find target elements.

## Key Change

The script now uses the injected `analyze_xpath_hint` function:

```python
def find_target_element(dom_dict: dict, xpath: str) -> dict:
    # analyze_xpath_hint is injected by execution environment
    result = analyze_xpath_hint(dom_dict, xpath)
    ...
```

## Workflow

1. Read task.json to get xpath_hints
2. Test with hint command: `python element_tools.py hint "<xpath>"`
3. If hint finds element → output standard template
4. If hint fails → output fallback error script

## When hint fails

Return this to trigger LLM fallback:
```python
return {"success": False, "error": "fallback required"}
```
```

### 4. browser_script_generator.py

**文件位置**: `src/common/script_generation/browser_script_generator.py`

可能需要调整 `_build_prompt()` 方法，简化 Claude 的任务说明。

### 5. element_tools.py

**文件位置**: `src/cloud_backend/services/skills/repository/element-finder/tools/element_tools.py`

**无需修改**，现有的 `analyze_xpath_hint` 函数已经足够用。

### 6. .fallback_mode 标记

**不清除**，原因：
- 如果一个 step 的 xpath 没有可提取特征，DOM 变化也不会改变这个事实
- 这是结构性问题，不是运行时问题
- 只有 task/xpath_hints keys 变化时才会重新生成脚本并评估

---

## 运行时行为示例

### 场景 1：foreach 循环（hint 能找到）

```yaml
- foreach: "{{product_list}}"
  as: product
  do:
    - id: click-product
      agent: browser_agent
      inputs:
        interaction_steps:
          - task: "Click on product"
            xpath_hints:
              product: "{{product.xpath}}"
```

**第一次迭代** (xpath = `//*[@id='PROD001']/div/a`):
1. 执行 `find_target_element(dom, xpath)`
2. 内部调用 `analyze_xpath_hint(dom, "//*[@id='PROD001']/div/a")`
3. hint 找到 id=PROD001 容器下的可交互 `<a>` 元素
4. 返回 `{success: True, interactive_index: 42}`
5. 点击元素 42

**第二次迭代** (xpath = `//*[@id='PROD002']/div/a`):
1. 执行同一个脚本 `find_target_element(dom, xpath)`
2. 内部调用 `analyze_xpath_hint(dom, "//*[@id='PROD002']/div/a")`
3. hint 找到 id=PROD002 容器下的可交互 `<a>` 元素
4. 返回 `{success: True, interactive_index: 87}`
5. 点击元素 87

**同一个脚本，不同的结果！**

### 场景 2：无特征 xpath（fallback）

```yaml
- id: click-item
  agent: browser_agent
  inputs:
    interaction_steps:
      - task: "Click third item in the list"
        xpath_hints:
          item: "/html/body/div[2]/ul/li[3]"
```

**执行流程**:
1. 执行 `find_target_element(dom, xpath)`
2. `analyze_xpath_hint` 找不到可交互元素（纯位置 xpath）
3. 返回 `{success: False, error: "fallback required"}`
4. 创建 `.fallback_mode` 标记
5. 调用 `_llm_find_element(dom, xpath, task)`
6. LLM 分析 DOM + task 描述，返回正确的 interactive_index

**后续调用**：
- 检测到 `.fallback_mode` 标记
- 直接跳过脚本，每次都用 LLM 判断

---

## 实施步骤

### Phase 1: 更新模板和 Skill

| 序号 | 文件 | 操作 |
|------|------|------|
| 1.1 | `src/common/script_generation/templates.py` | 更新 `BROWSER_FIND_ELEMENT_TEMPLATE` |
| 1.2 | `src/common/script_generation/templates.py` | 更新 `BROWSER_TEST_OPERATION` |
| 1.3 | `src/common/script_generation/templates.py` | 简化 `BROWSER_AGENT_PROMPT` |
| 1.4 | `src/cloud_backend/services/skills/repository/element-finder/SKILL.md` | 更新 Skill 文档 |

### Phase 2: 修改 browser_agent.py 执行逻辑

| 序号 | 修改点 | 操作 |
|------|--------|------|
| 2.1 | `_execute_find_element_script()` | 添加 xpath 参数，注入 `analyze_xpath_hint` |
| 2.2 | Line 1159 (缓存命中) | 调用时传入 xpath |
| 2.3 | Line 1361 (生成后执行) | 调用时传入 xpath |
| 2.4 | `_is_cache_valid()` | 只比较 xpath_hints 的 keys |
| 2.5 | Line 146-457 | 删除重复的模板类属性 |
| 2.6 | `_scroll_to_element_with_claude()` | 添加 `SkillManager.prepare_browser_skills()` |

### Phase 3: 实现 LLM Fallback

| 序号 | 操作 |
|------|------|
| 3.1 | 新增 `_llm_find_element()` 方法 |
| 3.2 | 新增 `_find_element_with_fallback()` 整合方法 |
| 3.3 | 实现 `.fallback_mode` 标记逻辑 |
| 3.4 | 设计 LLM prompt 模板 |

### Phase 4: 测试

| 序号 | 测试场景 |
|------|----------|
| 4.1 | 单次点击回归测试 |
| 4.2 | foreach 循环测试（动态 xpath） |
| 4.3 | fallback 场景测试（无特征 xpath） |
| 4.4 | scroll_to_element 测试 |

---

## 总结

### 方案对比

| 方面 | 之前 | 之后 |
|------|------|------|
| 脚本复杂度 | Claude 生成复杂搜索逻辑 | 简单包装，调用 hint |
| 函数签名 | `find_target_element(dom)` | `find_target_element(dom, xpath)` |
| 查找逻辑 | 写死在脚本中 | 运行时用 hint 动态查找 |
| foreach 支持 | ❌ | ✅ |
| 无特征 xpath | 可能失败 | fallback 到 LLM |
| 缓存策略 | 基于完整 xpath 值 | 基于 xpath keys + fallback 标记 |

### 完整文件修改清单

| 序号 | 文件 | 修改类型 |
|------|------|----------|
| 1 | `src/clients/desktop_app/ami_daemon/base_agent/agents/browser_agent.py` | 修改 |
| 2 | `src/common/script_generation/templates.py` | 修改 |
| 3 | `src/cloud_backend/services/skills/repository/element-finder/SKILL.md` | 修改 |
| 4 | `src/common/script_generation/browser_script_generator.py` | 可能修改 |

### 优势

1. **简化 Claude 的工作**：不需要生成复杂脚本，只需验证 hint 是否工作
2. **复用现有代码**：直接使用 `element_tools.py` 的 `analyze_xpath_hint`
3. **可靠的 fallback**：hint 找不到时，LLM 兜底确保不会卡住
4. **支持动态 xpath**：同一脚本处理不同 xpath 值

### 风险点

1. **exec 环境注入**：需要确保 `analyze_xpath_hint` 正确注入到执行环境
2. **测试脚本兼容性**：`test_operation.py` 需要特殊处理才能在 Claude Agent 环境中运行
3. **LLM Fallback 成本**：fallback 模式下每次调用都消耗 tokens
