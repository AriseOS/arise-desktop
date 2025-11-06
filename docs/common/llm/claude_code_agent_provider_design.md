# ClaudeCodeAgentProvider 设计文档

**版本:** 1.0
**日期:** 2025-01-26
**位置:** `src/common/llm/claude_code_agent_provider.py`
**状态:** 设计讨论中

---

## 1. 概述

### 1.1 定位

ClaudeCodeAgentProvider 是对 Claude Agent SDK 的封装，提供给其他 Agent（如 ScraperAgent）使用。

**核心原则:**
- ✅ 通用性：不绑定具体业务（爬虫、翻译、代码审查等）
- ✅ 简单性：提供简洁的接口
- ✅ 完整性：封装 Claude SDK 的核心功能

### 1.2 与现有 Provider 的关系

```python
# 现有 Provider
src/common/llm/
├── base_provider.py           # 基类
├── anthropic_provider.py      # Anthropic API 封装（单轮对话）
├── openai_provider.py         # OpenAI API 封装（单轮对话）
└── claude_code_agent_provider.py  # 新增：Claude Agent SDK 封装（多轮 Agent）
```

**区别:**
- `AnthropicProvider`: 单次 API 调用，生成文本
- `ClaudeCodeAgentProvider`: 多轮迭代，可使用工具（Read/Write/Bash）

---

## 2. 待讨论的设计问题

### 问题 1: 类命名

**候选方案:**

A. `ClaudeCodeAgentProvider`（更明确，强调 Claude Code）
B. `ClaudeAgentProvider`（简洁，但可能与 Anthropic API 混淆）
C. `ClaudeSDKProvider`（强调 SDK）
D. 其他？

**你的倾向:**

---

### 问题 2: 是否需要继承 BaseLLMProvider？

**现有 BaseLLMProvider 接口:**
```python
class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate_response(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> str:
        """生成单次响应"""
```

**考虑因素:**

**方案 A: 继承 BaseLLMProvider**
- ✅ 保持接口一致性
- ❌ Claude Agent SDK 不是简单的请求-响应，需要多轮迭代
- ❌ 需要实现 `generate_response()` 但实际不会用到

**方案 B: 不继承，独立实现**
- ✅ 接口更符合 Agent 语义
- ✅ 不需要实现无用的方法
- ❌ 与现有 Provider 不一致

**你的倾向:**

---

### 问题 3: 核心接口设计

**核心方法应该叫什么？接受什么参数？**

**方案 A: 通用任务执行**
```python
async def run_task(
    self,
    task_prompt: str,          # 任务描述
    working_dir: Path,         # 工作目录
    max_iterations: int = 5    # 最大迭代次数
) -> TaskResult
```

**方案 B: Agent 循环执行**
```python
async def run_agent_loop(
    self,
    prompt: str,
    working_dir: Path,
    tools: List[str] = None,    # 可选：指定工具
    max_turns: int = 5
) -> AgentResult
```

**方案 C: 更详细的配置**
```python
async def execute(
    self,
    prompt: str,
    working_dir: Path,
    options: AgentOptions = None  # 封装所有配置
) -> AgentResult

@dataclass
class AgentOptions:
    max_iterations: int = 5
    tools: List[str] = ["Read", "Write", "Bash"]
    permission_mode: str = "acceptEdits"
    timeout: int = 120
```

**你的倾向:**

---

### 问题 4: 返回值设计

**Agent 执行完成后应该返回什么信息？**

**方案 A: 简单返回**
```python
@dataclass
class TaskResult:
    success: bool
    error: Optional[str] = None
```

**方案 B: 包含迭代信息**
```python
@dataclass
class AgentResult:
    success: bool
    iterations: int              # 实际迭代次数
    error: Optional[str] = None
```

**方案 C: 详细信息**
```python
@dataclass
class AgentExecutionResult:
    success: bool
    iterations: int
    iteration_history: List[Dict]  # 每轮的详细信息
    output_files: List[Path]        # 生成的文件
    error: Optional[str] = None
    elapsed_time: float             # 执行时间
```

**你的倾向:**

---

### 问题 5: 错误处理策略

**当 Claude SDK 执行失败时，应该如何处理？**

**场景:**
- 网络错误
- API 限流
- 达到最大迭代次数但未成功
- 工作目录不存在
- Claude SDK 异常

**方案 A: 抛出异常**
```python
async def run_task(...):
    try:
        # 执行任务
    except ClaudeSDKError as e:
        raise ClaudeAgentError(f"执行失败: {e}")
```

**方案 B: 返回错误结果**
```python
async def run_task(...) -> TaskResult:
    try:
        # 执行任务
        return TaskResult(success=True)
    except Exception as e:
        return TaskResult(success=False, error=str(e))
```

**方案 C: 混合方式**
- 网络错误、配置错误 → 抛出异常
- 业务失败（迭代未成功）→ 返回失败结果

**你的倾向:**

---

### 问题 6: 工具（Tools）配置

**Claude SDK 支持的工具如何配置？**

**方案 A: 固定工具集**
```python
# 在类内部固定
TOOLS = ["Read", "Write", "Edit", "Bash", "Glob"]

async def run_task(self, prompt, working_dir):
    # 始终使用这些工具
```

**方案 B: 调用时指定**
```python
async def run_task(
    self,
    prompt,
    working_dir,
    tools: List[str] = ["Read", "Write", "Bash"]  # 默认值
):
    # 使用传入的工具
```

**方案 C: 配置文件 + 可覆盖**
```python
# 从 baseapp.yaml 读取默认值
default_tools = config.get("claude_sdk.tools")

async def run_task(self, prompt, working_dir, tools: List[str] = None):
    tools = tools or self.default_tools
```

**你的倾向:**

---

### 问题 7: 迭代过程的可见性

**调用者是否需要看到迭代过程？如何实现？**

**方案 A: 仅日志**
```python
# 内部记录日志
logger.info(f"迭代 1: Claude 正在写文件...")
logger.info(f"迭代 2: Claude 正在测试...")
```

**方案 B: 回调函数**
```python
async def run_task(
    self,
    prompt,
    working_dir,
    on_iteration: Callable[[int, str], None] = None
):
    # 每轮迭代调用回调
    if on_iteration:
        on_iteration(iteration_count, "写入文件...")
```

**方案 C: 返回详细历史**
```python
# 在返回值中包含完整历史
return AgentResult(
    success=True,
    iteration_history=[
        {"iteration": 1, "action": "write", "file": "script.py"},
        {"iteration": 2, "action": "bash", "command": "python test.py"}
    ]
)
```

**你的倾向:**

---

### 问题 8: 并发和线程安全

**是否需要考虑并发调用？**

**场景:**
- 多个 ScraperAgent 实例同时使用同一个 ClaudeCodeAgentProvider
- 或者多个用户并发请求

**方案 A: 无状态设计**
```python
class ClaudeCodeAgentProvider:
    # 没有实例变量存储状态
    # 每次调用都是独立的
```

**方案 B: 每次创建新实例**
```python
# 调用者每次创建新实例
provider = ClaudeCodeAgentProvider()
result = await provider.run_task(...)
```

**方案 C: 使用锁**
```python
class ClaudeCodeAgentProvider:
    def __init__(self):
        self._lock = asyncio.Lock()

    async def run_task(self, ...):
        async with self._lock:
            # 执行任务
```

**你的倾向:**

---

### 问题 9: 配置和初始化

**ClaudeCodeAgentProvider 需要哪些配置？如何初始化？**

**方案 A: 最小化配置**
```python
provider = ClaudeCodeAgentProvider(
    api_key="xxx",
    model="claude-sonnet-4-5"
)
```

**方案 B: 详细配置**
```python
provider = ClaudeCodeAgentProvider(
    api_key="xxx",
    model="claude-sonnet-4-5",
    default_tools=["Read", "Write", "Bash"],
    default_max_iterations=5,
    timeout=120,
    permission_mode="acceptEdits"
)
```

**方案 C: 从配置文件读取**
```python
# 从 baseapp.yaml 读取
provider = ClaudeCodeAgentProvider.from_config(config_service)
```

**你的倾向:**

---

### 问题 10: 与 Claude SDK 的具体交互

**使用 Claude SDK 的哪个 API？**

**Claude SDK 提供两种方式:**

**方式 A: `query()` 函数（简单）**
```python
from claude_agent_sdk import query

async for message in query(prompt="...", options=options):
    # 处理消息
```

**方式 B: `ClaudeSDKClient` 类（高级）**
```python
from claude_agent_sdk import ClaudeSDKClient

async with ClaudeSDKClient(options=options) as client:
    await client.query(prompt)
    async for message in client.receive_response():
        # 处理消息
```

**考虑因素:**
- `query()` 更简单，但功能有限
- `ClaudeSDKClient` 更灵活，支持自定义工具、钩子

**你的倾向:**

---

## 3. 初步代码框架（待确定）

```python
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass

class ClaudeCodeAgentProvider:  # 名称待定
    """
    Claude Agent SDK 封装

    提供多轮迭代的 Agent 能力
    """

    def __init__(
        self,
        api_key: str = None,
        model: str = "claude-sonnet-4-5",
        # 其他配置？
    ):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        # ...

    async def run_task(  # 方法名待定
        self,
        prompt: str,              # 参数待定
        working_dir: Path,
        # 其他参数？
    ) -> TaskResult:              # 返回类型待定
        """
        执行 Claude Agent 任务

        Args:
            prompt: 任务描述
            working_dir: 工作目录

        Returns:
            任务执行结果
        """
        # 实现待定
        pass


@dataclass
class TaskResult:  # 类名和字段待定
    success: bool
    error: Optional[str] = None
    # 其他字段？
```

---

## 4. 总结

请回答上述 10 个问题，我会根据你的回答来完善设计并开始实现代码。

**问题清单:**
1. 类命名
2. 是否继承 BaseLLMProvider
3. 核心接口设计
4. 返回值设计
5. 错误处理策略
6. 工具配置方式
7. 迭代过程可见性
8. 并发和线程安全
9. 配置和初始化
10. 与 Claude SDK 的交互方式

期待你的反馈！
