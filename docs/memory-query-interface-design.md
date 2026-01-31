# Memory Query Interface Design

## 设计目标

设计一个优雅、灵活、易用的 Memory 查询接口。

---

## 方案对比

### 方案 1：多个独立方法（当前设计）

```python
# 导航查询
result = await memory.query_navigation_path("产品页", "团队页")

# 操作查询
sequences = await memory.query_page_actions(state_id="产品页", query="查看团队")

# 任务查询
workflow = await memory.query_task_workflow("在 PH 查看团队信息")

# 探索查询
capabilities = memory.get_page_capabilities(state_id="产品页")
```

**优点**：
- ✅ 接口明确，一看就知道功能
- ✅ 类型提示清晰（每个方法返回类型不同）
- ✅ 参数不会混淆

**缺点**：
- ❌ 方法太多（4+ 个）
- ❌ 不够灵活，新增场景需要新方法
- ❌ API 表面积大

---

### 方案 2：单一 query 方法（参数区分）

```python
# 导航查询
result = await memory.query(
    "从产品页到团队页",
    query_type="navigation"
)

# 操作查询
sequences = await memory.query(
    "查看团队",
    query_type="action",
    state_id="产品页"
)

# 任务查询
workflow = await memory.query(
    "在 PH 查看团队信息",
    query_type="task"
)
```

**优点**：
- ✅ 统一入口
- ✅ 灵活，容易扩展

**缺点**：
- ❌ 参数语义不够清晰（为什么有时有 state_id，有时没有？）
- ❌ 类型提示困难（返回类型不确定）
- ❌ 容易误用（忘记传 query_type）

---

### 方案 3：查询构建器模式（Builder Pattern）

```python
# 操作查询
sequences = await memory.query("查看团队信息") \
    .in_state("产品页") \
    .as_action() \
    .execute()

# 导航查询
path = await memory.query("从首页到产品页") \
    .as_navigation() \
    .execute()

# 任务查询
workflow = await memory.query("完整购物流程") \
    .as_task() \
    .execute()

# 探索查询
capabilities = memory.query() \
    .in_state("产品页") \
    .get_capabilities()
```

**优点**：
- ✅ 链式调用优雅
- ✅ 语义清晰
- ✅ 灵活组合

**缺点**：
- ❌ 实现复杂
- ❌ 可能过度设计
- ❌ 对于简单查询过于啰嗦

---

### 方案 4：分层 + 统一（平衡方案）

```python
class Memory:
    
    # ============ 统一入口（智能分发）============
    async def query(
        self,
        target: str,
        context: Optional[QueryContext] = None
    ) -> QueryResult:
        """智能查询入口
        
        根据 target 和 context 自动判断查询类型
        """
        pass
    
    # ============ 便捷方法（语法糖）============
    async def navigation(self, start: str, end: str):
        """导航查询（语法糖）"""
        return await self.query(
            f"从{start}到{end}",
            context=QueryContext(type="navigation")
        )
    
    async def actions(self, state_id: str, query: str):
        """操作查询（语法糖）"""
        return await self.query(
            query,
            context=QueryContext(type="action", state_id=state_id)
        )
    
    async def workflow(self, target: str):
        """任务查询（语法糖）"""
        return await self.query(
            target,
            context=QueryContext(type="task")
        )
```

**使用示例**：
```python
# 使用统一入口（自动判断）
result = await memory.query("查看团队信息")

# 使用便捷方法（明确意图）
path = await memory.navigation("产品页", "团队页")
sequences = await memory.actions(state_id="产品页", query="查看团队")
workflow = await memory.workflow("在 PH 查看团队信息")
```

**优点**：
- ✅ 既有统一入口，又有便捷方法
- ✅ 灵活且清晰
- ✅ 向后兼容
- ✅ 简单场景用便捷方法，复杂场景用统一入口

**缺点**：
- ⚠️ API 表面积略大（但每个都有明确用途）

---

### 方案 5：上下文感知查询（最优雅）✨ 推荐

```python
class Memory:
    
    async def query(
        self,
        target: str,
        *,
        # 上下文参数（可选）
        current_state: Optional[str] = None,
        start_state: Optional[str] = None,
        end_state: Optional[str] = None,
        # 显式类型（可选）
        as_type: Optional[Literal["navigation", "action", "task"]] = None,
        # 其他
        user_id: Optional[str] = None
    ) -> QueryResult:
        """智能查询入口
        
        根据参数自动判断查询类型：
        - 如果有 start_state + end_state → navigation
        - 如果有 current_state → action
        - 否则 → task
        - 可以用 as_type 显式指定
        """
        pass
```

**使用示例**：

```python
# 1. 任务查询（最简单）
result = await memory.query("在 PH 查看团队信息")
# → 自动识别为 task 查询

# 2. 操作查询（提供当前状态）
result = await memory.query(
    "查看团队信息",
    current_state="产品页"
)
# → 自动识别为 action 查询

# 3. 导航查询（提供起点和终点）
result = await memory.query(
    "导航",
    start_state="产品页",
    end_state="团队页"
)
# → 自动识别为 navigation 查询

# 4. 显式指定类型（确保不被误判）
result = await memory.query(
    "查看团队信息",
    as_type="task"  # 明确指定
)

# 5. 探索查询（特殊情况）
capabilities = await memory.query(
    "",  # 空查询
    current_state="产品页"
)
# → 返回当前页面的所有能力
```

**实现逻辑**：
```python
async def query(self, target: str, **kwargs) -> QueryResult:
    """智能查询"""
    
    # 1. 如果显式指定类型，直接使用
    if kwargs.get("as_type"):
        query_type = kwargs["as_type"]
    
    # 2. 根据参数自动判断
    elif kwargs.get("start_state") and kwargs.get("end_state"):
        query_type = "navigation"
    
    elif kwargs.get("current_state"):
        query_type = "action"
    
    else:
        query_type = "task"
    
    # 3. 分发到具体实现
    if query_type == "navigation":
        return await self._query_navigation(
            kwargs["start_state"],
            kwargs["end_state"]
        )
    
    elif query_type == "action":
        return await self._query_action(
            target,
            kwargs["current_state"]
        )
    
    else:  # task
        return await self._query_task(target)
```

**优点**：
- ✅ 接口最简洁（只有一个 query 方法）
- ✅ 智能判断，符合自然使用
- ✅ 灵活，支持复杂场景
- ✅ 类型提示清晰（通过 as_type）
- ✅ 可以显式指定，避免误判

**缺点**：
- ⚠️ 需要良好的文档说明参数组合
- ⚠️ 自动判断可能出错（但可以用 as_type 纠正）

---

## 推荐方案对比

### 方案 4 vs 方案 5

| 方面 | 方案 4（分层 + 统一） | 方案 5（上下文感知） |
|------|---------------------|---------------------|
| **API 数量** | 多（1个统一 + 3个便捷） | 少（1个统一） |
| **易用性** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **灵活性** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **类型安全** | ⭐⭐⭐⭐⭐（便捷方法有类型） | ⭐⭐⭐⭐（需要 as_type） |
| **学习曲线** | 中等（需要记住便捷方法） | 低（只记住一个方法） |
| **误用风险** | 低 | 低（有 as_type 保底） |

---

## 最终推荐：方案 5 + 少量便捷方法

**核心设计**：
```python
class Memory:
    
    # ============ 主入口（智能）============
    async def query(
        self,
        target: str,
        *,
        current_state: Optional[str] = None,
        start_state: Optional[str] = None,
        end_state: Optional[str] = None,
        as_type: Optional[Literal["navigation", "action", "task"]] = None,
        user_id: Optional[str] = None
    ) -> QueryResult:
        """智能查询入口"""
        pass
    
    # ============ 便捷方法（可选，最常用的场景）============
    async def navigate(self, start: str, end: str) -> NavigationResult:
        """导航便捷方法"""
        return await self.query("", start_state=start, end_state=end, as_type="navigation")
    
    # ============ 基础方法（保留）============
    def get_state(self, state_id: str) -> Optional[State]:
        """获取 State（基础操作，不是查询）"""
        pass
    
    def get_intent_sequence(self, sequence_id: str) -> Optional[IntentSequence]:
        """获取 IntentSequence（基础操作，不是查询）"""
        pass
```

**使用示例**：
```python
# 90% 的场景：使用 query
result = await memory.query("查看团队信息")
result = await memory.query("查看团队", current_state="产品页")
result = await memory.query("导航", start_state="首页", end_state="产品页")

# 10% 的场景：明确导航（最常用）
path = await memory.navigate("首页", "产品页")

# 基础操作（不是查询）
state = memory.get_state("state_123")
sequence = memory.get_intent_sequence("seq_456")
```

---

## 返回类型设计

### 统一返回类型

```python
class QueryResult(BaseModel):
    """统一查询结果"""
    
    # 元信息
    query_type: Literal["navigation", "action", "task"]
    success: bool
    
    # 通用字段（可能为空）
    states: List[State] = []
    actions: List[Action] = []
    intent_sequences: List[IntentSequence] = []
    
    # 任务级特有
    cognitive_phrase: Optional[CognitivePhrase] = None
    execution_plan: List[ExecutionStep] = []
    
    # 元数据
    metadata: Dict[str, Any] = {}
    
    # 便捷方法
    def as_navigation(self) -> NavigationResult:
        """转换为 NavigationResult"""
        return NavigationResult(states=self.states, actions=self.actions)
    
    def as_task(self) -> TaskResult:
        """转换为 TaskResult"""
        return TaskResult(
            execution_plan=self.execution_plan,
            cognitive_phrase=self.cognitive_phrase
        )
```

**优点**：
- 统一返回类型，易于处理
- 包含所有可能的数据
- 提供便捷转换方法

---

## 总结

**推荐**：方案 5（上下文感知查询）+ 1个便捷方法（navigate）

**核心接口**：
```python
# 主接口
memory.query(target, current_state=..., start_state=..., end_state=..., as_type=...)

# 便捷方法（只保留最常用的）
memory.navigate(start, end)

# 基础方法（不是查询）
memory.get_state(id)
memory.get_intent_sequence(id)
```

**理由**：
1. 接口最简洁（1个主接口 + 1个便捷方法）
2. 智能且灵活
3. 符合自然语言理解
4. 易于扩展
5. 类型安全（通过 as_type）
