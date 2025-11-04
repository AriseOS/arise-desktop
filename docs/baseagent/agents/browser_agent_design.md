# BrowserAgent 设计文档

**版本**: 1.0
**日期**: 2025-11-02
**状态**: 设计阶段

---

## 一、设计概述

### 1.1 设计目标

创建一个专门处理浏览器导航操作的 Agent，职责清晰：

- **核心职责**: 页面导航 + 页面交互（scroll）
- **不负责**: 数据提取
- **协作方式**: 与 ScraperAgent 共享浏览器会话，完成导航后交给 ScraperAgent 提取数据

### 1.2 架构位置

```
BaseStepAgent (抽象基类)
├── BrowserAgent (新建)
│   ├── 职责: 导航 + scroll
│   ├── 输入: target_url + interaction_steps
│   └── 输出: success + current_url + message
│
├── ScraperAgent (现有，不改动)
│   ├── 职责: 导航 + 交互 + 数据提取
│   ├── 输入: target_path + interaction_steps + data_requirements
│   └── 输出: success + extracted_data + metadata
│
└── 其他 Agent...
```

### 1.3 设计原则

1. **最小改动**: 不修改 ScraperAgent，复制必要代码
2. **代码复用**: 从 ScraperAgent 复制浏览器会话管理和导航逻辑
3. **职责单一**: BrowserAgent 只负责导航和交互，不负责数据提取
4. **会话共享**: 通过 AgentContext 共享浏览器会话
5. **可扩展性**: 预留扩展接口，方便后续添加 click、input 等操作

---

## 二、类设计

### 2.1 类定义

```python
class BrowserAgent(BaseStepAgent):
    """Browser navigation and interaction agent

    Responsibilities:
    - Navigate to specified URLs
    - Execute scroll operations (optional)
    - Share browser session with other agents

    NOT responsible for:
    - Data extraction (use ScraperAgent instead)
    - Complex interactions like click, input (future enhancement)
    """

    def __init__(self,
                 config_service=None,
                 metadata: Optional[AgentMetadata] = None):
        """Initialize BrowserAgent

        Args:
            config_service: Configuration service
            metadata: Agent metadata
        """

    async def initialize(self, context: AgentContext) -> bool:
        """Initialize agent with browser session from context"""

    async def validate_input(self, input_data: Any) -> bool:
        """Validate input data"""

    async def execute(self, input_data: Any, context: AgentContext) -> Any:
        """Execute navigation and interactions"""

    # Private methods (copied from ScraperAgent)
    async def _navigate_to_pages(self,
                                path: Union[str, List[str]],
                                interaction_steps: List[Dict]) -> ActionResult:
        """Execute sequential page navigation"""

    async def _execute_interaction_step(self, step_config: Dict) -> ActionResult:
        """Execute single interaction step (scroll only in MVP)"""
```

### 2.2 属性设计

```python
class BrowserAgent:
    # Configuration service
    config_service: Optional[ConfigService]

    # Browser-use components (shared from AgentContext)
    browser_session: Optional[BrowserSession] = None
    controller: Optional[Tools] = None

    # Initialization flag
    is_initialized: bool = False
```

### 2.3 方法设计

#### 核心方法

| 方法 | 职责 | 输入 | 输出 |
|------|------|------|------|
| `__init__()` | 初始化 Agent | config_service, metadata | - |
| `initialize()` | 从 context 获取浏览器会话 | AgentContext | bool |
| `validate_input()` | 验证输入数据 | input_data | bool |
| `execute()` | 执行导航和交互 | input_data, context | AgentOutput |

#### 私有方法（从 ScraperAgent 复制）

| 方法 | 职责 | 来源 |
|------|------|------|
| `_navigate_to_pages()` | 导航到指定 URL | ScraperAgent:327-388 |
| `_execute_interaction_step()` | 执行交互步骤（scroll） | ScraperAgent:389-419 |
| `_create_response()` | 创建响应对象 | ScraperAgent:1500-1507 |

---

## 三、数据流设计

### 3.1 输入数据结构

```python
# Workflow YAML 输入
inputs:
  target_url: str                    # 必需：目标 URL
  interaction_steps: List[Dict] = [] # 可选：交互步骤
  timeout: int = 30                  # 可选：超时时间

# interaction_steps 结构
interaction_steps:
  - action_type: "scroll"
    parameters:
      down: bool              # true=向下, false=向上
      num_pages: float        # 滚动页数
      frame_element_index: Optional[int]  # iframe 索引
```

**验证规则**:
- `target_url` 必须存在且为有效 URL
- `interaction_steps` 如果存在，每个 step 必须有 `action_type`
- 当前只支持 `action_type: "scroll"`

### 3.2 输出数据结构

```python
# AgentOutput 结构
{
    "success": bool,           # 是否成功
    "data": {
        "current_url": str,    # 当前页面 URL
        "message": str,        # 执行消息
        "steps_executed": int  # 执行的步骤数
    },
    "message": str,            # 顶层消息
    "error": Optional[str]     # 错误信息
}
```

**示例输出**:
```python
# 成功案例
{
    "success": True,
    "data": {
        "current_url": "https://example.com/page",
        "message": "Successfully navigated to https://example.com/page",
        "steps_executed": 0
    },
    "message": "Navigation completed successfully"
}

# 有交互步骤的案例
{
    "success": True,
    "data": {
        "current_url": "https://example.com/page",
        "message": "Successfully navigated and executed 2 interaction steps",
        "steps_executed": 2
    },
    "message": "Navigation and interactions completed successfully"
}

# 失败案例
{
    "success": False,
    "data": {},
    "message": "Navigation failed",
    "error": "Failed to load https://example.com/page: Timeout"
}
```

### 3.3 数据流图

```
┌─────────────────┐
│ Workflow Engine │
└────────┬────────┘
         │ AgentInput
         │ {target_url, interaction_steps}
         ▼
┌─────────────────┐
│ BrowserAgent    │
│                 │
│ 1. Initialize   │◄─────── AgentContext.get_browser_session()
│ 2. Validate     │
│ 3. Navigate     │
│ 4. Interact     │         browser_session (shared)
│ 5. Return       │                │
└────────┬────────┘                │
         │ AgentOutput              │
         │ {success, current_url}   │
         ▼                          ▼
┌─────────────────┐         ┌─────────────────┐
│ Next Agent      │◄────────│ Browser Session │
│ (ScraperAgent)  │         │ (Shared State)  │
└─────────────────┘         └─────────────────┘
```

---

## 四、核心逻辑设计

### 4.1 initialize() 实现

```python
async def initialize(self, context: AgentContext) -> bool:
    """Initialize agent with browser session from context

    Flow:
    1. Get shared browser session from context
    2. Set browser_session and controller
    3. Mark as initialized

    Args:
        context: Agent execution context

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get browser session from context (shared across workflow)
        session_info = await context.get_browser_session()

        # Set browser-use components
        self.browser_session = session_info.session
        self.controller = session_info.controller

        # Mark as initialized
        self.is_initialized = True

        logger.info("BrowserAgent initialized successfully with shared session")
        return True

    except Exception as e:
        logger.error(f"BrowserAgent initialization failed: {e}")
        return False
```

**关键点**:
- ✅ 从 AgentContext 获取共享会话（不创建新会话）
- ✅ 复用 ScraperAgent 的实现逻辑
- ✅ 异常处理和日志记录

### 4.2 validate_input() 实现

```python
async def validate_input(self, input_data: Any) -> bool:
    """Validate input data

    Required fields:
    - target_url: str

    Optional fields:
    - interaction_steps: List[Dict]
    - timeout: int

    Returns:
        bool: True if valid, False otherwise
    """
    # Handle AgentInput wrapper
    from ..core.schemas import AgentInput

    if isinstance(input_data, AgentInput):
        actual_data = input_data.data
    elif isinstance(input_data, dict):
        actual_data = input_data
    else:
        return False

    # Check required field
    if 'target_url' not in actual_data:
        logger.error("Validation failed: missing 'target_url'")
        return False

    # Validate interaction_steps if present
    if 'interaction_steps' in actual_data:
        steps = actual_data['interaction_steps']
        if not isinstance(steps, list):
            logger.error("Validation failed: 'interaction_steps' must be a list")
            return False

        for step in steps:
            if 'action_type' not in step:
                logger.error("Validation failed: step missing 'action_type'")
                return False

            # Currently only support 'scroll'
            if step['action_type'] not in ['scroll']:
                logger.error(f"Validation failed: unsupported action_type '{step['action_type']}'")
                return False

    return True
```

**验证规则**:
- ✅ `target_url` 必须存在
- ✅ `interaction_steps` 如果存在必须是列表
- ✅ 每个 step 必须有 `action_type`
- ✅ 当前只支持 `scroll`

### 4.3 execute() 实现

```python
async def execute(self, input_data: Any, context: AgentContext) -> Any:
    """Execute navigation and interactions

    Flow:
    1. Check initialization
    2. Extract input data
    3. Navigate to target_url
    4. Execute interaction_steps (if any)
    5. Return result

    Args:
        input_data: Input data (AgentInput or dict)
        context: Execution context

    Returns:
        AgentOutput with navigation result
    """
    if not self.is_initialized:
        raise RuntimeError("BrowserAgent not initialized")

    # Handle AgentInput wrapper
    from ..core.schemas import AgentInput, AgentOutput

    if isinstance(input_data, AgentInput):
        actual_data = input_data.data
    else:
        actual_data = input_data

    # Extract parameters
    target_url = actual_data['target_url']
    interaction_steps = actual_data.get('interaction_steps', [])
    timeout = actual_data.get('timeout', 30)

    logger.info(f"BrowserAgent executing: target_url={target_url}, "
                f"interaction_steps={len(interaction_steps)}")

    try:
        # Navigate to target URL and execute interactions
        result = await self._navigate_to_pages(target_url, interaction_steps)

        # Check navigation result
        if result.success is False:
            return self._create_error_response(
                f"Navigation failed: {result.error}"
            )

        # Get current URL from browser session
        current_url = self.browser_session.context.pages[0].url if self.browser_session else target_url

        # Success response
        response = self._create_response(
            success=True,
            message=f"Successfully navigated to {target_url}",
            current_url=current_url,
            steps_executed=len(interaction_steps)
        )

        # Wrap in AgentOutput if needed
        if isinstance(input_data, AgentInput):
            return AgentOutput(
                success=True,
                data=response,
                message=response['message']
            )
        else:
            return response

    except Exception as e:
        logger.error(f"BrowserAgent execution failed: {e}")
        error_response = self._create_error_response(str(e))

        if isinstance(input_data, AgentInput):
            return AgentOutput(
                success=False,
                data=error_response,
                message=f"Execution failed: {e}"
            )
        else:
            return error_response
```

**执行流程**:
1. ✅ 检查初始化状态
2. ✅ 提取输入参数
3. ✅ 调用 `_navigate_to_pages()` 导航
4. ✅ 检查导航结果
5. ✅ 返回成功/失败响应

### 4.4 _navigate_to_pages() 实现

**复用 ScraperAgent 的实现** (scraper_agent.py:327-388)

```python
async def _navigate_to_pages(self,
                           path: Union[str, List[str]],
                           interaction_steps: List[Dict]) -> ActionResult:
    """Execute sequential page navigation in the same tab

    Copied from ScraperAgent with minor modifications.

    Args:
        path: Target URL or list of URLs
        interaction_steps: Interaction steps to execute after navigation

    Returns:
        ActionResult with navigation result
    """
    try:
        # Convert single path to list for unified processing
        urls = path if isinstance(path, list) else [path]
        last_result = None

        # Navigate through all URLs in the same tab
        for i, url in enumerate(urls):
            logger.info(f"Navigating to: {url}")

            # Create ActionModel for navigation
            class GoToUrlActionModel(ActionModel):
                go_to_url: GoToUrlAction | None = None

            # Navigate (always in same tab, not new tab)
            action_data = {'go_to_url': GoToUrlAction(url=url, new_tab=False)}
            result = await self.controller.act(GoToUrlActionModel(**action_data), self.browser_session)
            await asyncio.sleep(5)  # Wait for page stability

            # Check for failure
            if result.success is False:
                logger.error(f"Navigation failed for URL: {url}, error: {result.error}")
                return result

            last_result = result

        # Execute interaction steps after navigation (if provided)
        if interaction_steps:
            logger.info(f"Executing {len(interaction_steps)} interaction steps...")
            for idx, step in enumerate(interaction_steps):
                action_type = step.get('action_type', 'unknown')
                logger.info(f"  Step {idx + 1}/{len(interaction_steps)}: {action_type}")

                interaction_result = await self._execute_interaction_step(step)

                # Check if interaction failed
                if interaction_result.success is False:
                    logger.error(f"Interaction step {idx + 1} failed: {interaction_result.error}")
                    return interaction_result

                # Small delay between interactions
                await asyncio.sleep(0.5)

            logger.info("All interaction steps completed successfully")

            # Wait for content stability after interactions
            await asyncio.sleep(3)

        # Return the last result
        return last_result if last_result else ActionResult(extracted_content="No navigation performed")

    except Exception as e:
        logger.error(f"Navigation failed: {e}")
        return ActionResult(success=False, error=str(e))
```

**关键点**:
- ✅ 支持单个 URL 或 URL 列表
- ✅ 支持 interaction_steps（导航后执行）
- ✅ 异常处理和错误返回
- ✅ 等待页面稳定（browser-use 自动处理 + 额外 sleep）

### 4.5 _execute_interaction_step() 实现

**复用 ScraperAgent 的实现**（只保留 scroll 部分）

```python
async def _execute_interaction_step(self, step_config: Dict) -> ActionResult:
    """Execute single interaction step (currently only supports scroll)

    Copied from ScraperAgent, only scroll is supported in MVP.

    Args:
        step_config: Step configuration with action_type and parameters

    Returns:
        ActionResult with execution result
    """
    try:
        action_type = step_config['action_type']
        parameters = step_config.get('parameters', {})

        if action_type == 'scroll':
            # Create ScrollAction model
            class ScrollActionModel(ActionModel):
                scroll: ScrollAction | None = None

            action_data = {'scroll': ScrollAction(
                down=parameters.get('down', True),
                num_pages=parameters.get('num_pages', 1.0),
                frame_element_index=parameters.get('frame_element_index')
            )}

            logger.debug(f"Scrolling: down={parameters.get('down', True)}, "
                        f"num_pages={parameters.get('num_pages', 1.0)}")
            result = await self.controller.act(ScrollActionModel(**action_data), self.browser_session)

            # Wait for page stability after scroll
            await asyncio.sleep(1)

            return result
        else:
            logger.warning(f"Unsupported action type: {action_type}. Currently only 'scroll' is supported.")
            return ActionResult(success=False, error=f"Unsupported action type: {action_type}")

    except Exception as e:
        logger.error(f"Interaction step failed: {e}")
        return ActionResult(success=False, error=str(e))
```

**关键点**:
- ✅ 当前只支持 scroll
- ✅ 使用 browser-use 的 ScrollAction
- ✅ 滚动后等待页面稳定
- ✅ 预留扩展接口（后续可添加 click、input 等）

---

## 五、错误处理设计

### 5.1 错误类型

| 错误类型 | 触发条件 | 处理方式 |
|---------|---------|---------|
| **初始化错误** | 无法获取浏览器会话 | 返回 False，记录日志 |
| **验证错误** | 缺少必需参数 | 返回 False，记录日志 |
| **导航错误** | URL 无效、网络错误、超时 | 返回 ActionResult(success=False) |
| **交互错误** | scroll 执行失败 | 返回 ActionResult(success=False) |
| **未知错误** | 其他异常 | 捕获异常，返回错误响应 |

### 5.2 错误响应格式

```python
# 错误响应示例
{
    "success": False,
    "data": {},
    "message": "Navigation failed",
    "error": "Failed to load https://example.com/page: Timeout after 30s"
}
```

### 5.3 日志设计

**日志级别**:
- `INFO`: 正常执行流程（初始化、导航、交互）
- `WARNING`: 不支持的操作（如 click）
- `ERROR`: 错误情况（导航失败、交互失败）
- `DEBUG`: 详细调试信息（参数值、中间状态）

**日志示例**:
```python
logger.info("BrowserAgent initialized successfully with shared session")
logger.info(f"Navigating to: {url}")
logger.info(f"Executing {len(interaction_steps)} interaction steps...")
logger.error(f"Navigation failed for URL: {url}, error: {result.error}")
logger.warning(f"Unsupported action type: {action_type}")
logger.debug(f"Scrolling: down={down}, num_pages={num_pages}")
```

---

## 六、测试设计

### 6.1 单元测试

| 测试用例 | 测试内容 | 预期结果 |
|---------|---------|---------|
| test_initialization | 初始化 BrowserAgent | ✅ 成功获取浏览器会话 |
| test_validate_input_success | 验证有效输入 | ✅ 返回 True |
| test_validate_input_missing_url | 验证缺少 URL | ✅ 返回 False |
| test_validate_input_invalid_steps | 验证无效 interaction_steps | ✅ 返回 False |
| test_execute_simple_navigation | 简单导航 | ✅ 成功导航，返回正确 URL |
| test_execute_with_scroll | 导航 + 滚动 | ✅ 成功导航并滚动 |
| test_execute_navigation_failure | 导航失败（无效 URL） | ✅ 返回失败响应 |

### 6.2 集成测试

| 测试用例 | 测试内容 | 预期结果 |
|---------|---------|---------|
| test_browser_session_sharing | 与 ScraperAgent 共享会话 | ✅ 两个 Agent 使用同一个 session |
| test_browser_then_scraper | BrowserAgent → ScraperAgent | ✅ ScraperAgent 能在当前页面提取数据 |
| test_multi_step_navigation | 首页 → 分类页 → 详情页 | ✅ 所有导航步骤执行成功 |

### 6.3 端到端测试

| 测试用例 | 测试内容 | 预期结果 |
|---------|---------|---------|
| test_allegro_workflow | Allegro 咖啡产品抓取 | ✅ 完整流程运行成功 |
| test_workflow_generation | MetaFlow → Workflow | ✅ 生成包含 BrowserAgent 的 workflow |
| test_navigation_preservation | 导航步骤不被优化 | ✅ 首页导航被保留 |

---

## 七、性能考虑

### 7.1 性能指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 导航时间 | < 30s | 正常网络条件下 |
| scroll 执行时间 | < 2s | 每次滚动操作 |
| 初始化时间 | < 1s | 获取浏览器会话 |

### 7.2 性能优化

1. **复用浏览器会话**: 不创建新会话，复用 AgentContext 的共享会话
2. **等待策略**: 使用 browser-use 的智能等待机制（_wait_for_stable_network）
3. **并发控制**: 同一个 workflow 内的 Agent 串行执行（避免会话冲突）

---

## 八、扩展设计

### 8.1 后续功能扩展

**Phase 2: 增加 click 操作**

```python
# 扩展 _execute_interaction_step() 支持 click
if action_type == 'click':
    class ClickActionModel(ActionModel):
        click_element: ClickElementAction | None = None

    action_data = {'click_element': ClickElementAction(
        element_index=parameters.get('element_index')
    )}
    result = await self.controller.act(ClickActionModel(**action_data), self.browser_session)
    return result
```

**Phase 3: 增加 input 操作**

```python
if action_type == 'input':
    class InputTextActionModel(ActionModel):
        input_text: InputTextAction | None = None

    action_data = {'input_text': InputTextAction(
        element_index=parameters.get('element_index'),
        text=parameters.get('text')
    )}
    result = await self.controller.act(InputTextActionModel(**action_data), self.browser_session)
    return result
```

### 8.2 代码重构扩展

**未来可能的重构**:

```python
# 创建共享基类
class BrowserBaseAgent(BaseStepAgent):
    """Shared base class for browser-based agents"""

    # Shared browser session management
    async def initialize(self, context: AgentContext) -> bool:
        ...

    # Shared navigation methods
    async def _navigate_to_pages(self, ...) -> ActionResult:
        ...

    async def _execute_interaction_step(self, ...) -> ActionResult:
        ...

# BrowserAgent 继承
class BrowserAgent(BrowserBaseAgent):
    # Pure navigation and interaction
    ...

# ScraperAgent 重构为继承
class ScraperAgent(BrowserBaseAgent):
    # Add data extraction on top of base
    ...
```

---

## 九、实现清单

### 9.1 代码文件

| 文件 | 路径 | 状态 |
|------|------|------|
| BrowserAgent 实现 | `src/base_app/base_app/base_agent/agents/browser_agent.py` | ⏳ 待实现 |
| BrowserAgent 测试 | `tests/base_app/test_browser_agent.py` | ⏳ 待实现 |

### 9.2 文档文件

| 文件 | 路径 | 状态 |
|------|------|------|
| 讨论记录 | `docs/intent_builder/discussions/05_browser_agent_integration.md` | ✅ 已完成 |
| 需求文档 | `docs/baseagent/agents/browser_agent_requirements.md` | ✅ 已完成 |
| 设计文档 | `docs/baseagent/agents/browser_agent_design.md` | ✅ 已完成 |
| 规范文档 | `docs/baseagent/browser_agent_spec.md` | ⏳ 待创建 |

### 9.3 配置文件

| 文件 | 路径 | 修改内容 | 状态 |
|------|------|---------|------|
| PromptBuilder | `src/intent_builder/generators/prompt_builder.py` | 添加 BrowserAgent，删除优化规则 | ⏳ 待修改 |

---

## 十、参考资料

### 10.1 相关文档
- [讨论记录](../../../intent_builder/discussions/05_browser_agent_integration.md)
- [需求文档](./browser_agent_requirements.md)
- [ScraperAgent 设计](./scraper_agent_design.md)

### 10.2 相关代码
- ScraperAgent: `src/base_app/base_app/base_agent/agents/scraper_agent.py`
- BaseStepAgent: `src/base_app/base_app/base_agent/core/base_step_agent.py`
- AgentContext: `src/base_app/base_app/base_agent/core/schemas.py`

### 10.3 依赖库
- browser-use: 浏览器自动化库
- playwright: 底层浏览器控制

---

**文档版本**: 1.0
**最后更新**: 2025-11-02
**作者**: Claude Code
