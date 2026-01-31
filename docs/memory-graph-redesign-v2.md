# Memory Graph Redesign v2

## 1. 设计目标

基于图原生思维，重新设计 Memory Graph 数据模型和查询接口，支持三种查询场景：
1. **任务级查询** - 完整工作流检索
2. **导航级查询** - 页面间路径规划
3. **操作级查询** - 页面内操作检索

---

## 2. 新的图模型设计

### 2.1 节点类型

```
┌─────────────────────────────────────────────────────────────┐
│                      Node Types                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. State (页面状态节点)                                      │
│     - 抽象的页面类型（如"产品详情页"）                         │
│     - 有 description + embedding（支持向量检索）              │
│     - 包含 instances（具体 URL）                              │
│                                                              │
│  2. IntentSequence (操作序列节点) ✨ NEW                      │
│     - 页面内的操作序列（如"点击查看团队"）                     │
│     - 有 description + embedding（支持向量检索）              │
│     - 包含 intents 列表（操作细节）                           │
│     - ✨ 标记 causes_navigation（是否导致跳转）               │
│     - ✨ 标记 navigation_target（跳转目标）                   │
│                                                              │
│  3. CognitivePhrase (认知短语节点)                            │
│     - 完整的任务工作流（如"在 PH 查看团队信息"）               │
│     - 有 description + embedding（支持向量检索）              │
│     - 包含 state_path（状态序列）                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 关系类型

```
┌─────────────────────────────────────────────────────────────┐
│                    Relationship Types                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. HAS_SEQUENCE (State → IntentSequence) ✨ NEW             │
│     - State 包含哪些操作序列                                  │
│     - 用于查询"在这个页面能做什么"                            │
│                                                              │
│  2. Action (State → State)                                   │
│     - 页面间的跳转                                           │
│     - 有 type, trigger, trigger_sequence_id                 │
│     - 用于路径规划和导航                                      │
│                                                              │
│  3. RECORDS (CognitivePhrase → State) - Optional             │
│     - 认知短语记录了哪些状态                                  │
│     - 可以用于快速检索                                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 完整图结构示例

```cypher
// 节点
(State:ProductDetailPage {
    id: "state_123",
    description: "产品详情页",
    embedding: [...],
    instances: [
        {url: "https://www.producthunt.com/posts/cursor-2", ...},
        {url: "https://www.producthunt.com/posts/claude-3-5", ...}
    ]
})

(IntentSequence:ClickTeamTab {
    id: "seq_456",
    description: "点击 Team 标签查看团队信息",
    embedding: [...],
    intents: [
        {type: "click", ref: "e42", text: "Team", role: "button"}
    ],
    causes_navigation: true,  // ✨ 标记：导致页面跳转
    navigation_target_state_id: "state_124"  // ✨ 跳转到团队页
})

(IntentSequence:ScrollDown {
    id: "seq_457",
    description: "向下滚动浏览产品信息",
    embedding: [...],
    intents: [
        {type: "scroll", value: "down"}
    ],
    causes_navigation: false  // ✨ 标记：纯页面内操作
})

(CognitivePhrase:ViewTeamOnPH {
    id: "phrase_789",
    label: "在 PH 查看团队信息",
    description: "从 PH 首页到产品详情页，点击查看团队信息",
    embedding: [...],
    
    // ✨ 结构化执行计划（唯一的路径表示）
    execution_plan: [
        {
            index: 1,
            state_id: "state_001",
            in_page_sequence_ids: ["seq_100"],  // 首页滚动
            navigation_action_id: "action_001"  // 点击 Leaderboard
        },
        {
            index: 2,
            state_id: "state_002",
            in_page_sequence_ids: [],  // 无页面内操作
            navigation_action_id: "action_002"  // 点击 Cursor 产品
        },
        {
            index: 3,
            state_id: "state_123",
            in_page_sequence_ids: ["seq_457"],  // 滚动
            navigation_action_id: "action_003"  // 点击 Team（seq_456 导致跳转）
        },
        {
            index: 4,
            state_id: "state_124",
            in_page_sequence_ids: [],  // 最后一页，无操作
            navigation_action_id: null
        }
    ]
})

// 关系
(State:ProductDetailPage)-[:HAS_SEQUENCE]->(IntentSequence:ClickTeamTab)
(State:ProductDetailPage)-[:HAS_SEQUENCE]->(IntentSequence:ScrollDown)

(State:Leaderboard)-[Action {
    type: "click",
    trigger: {ref: "e99", text: "Cursor", role: "link"},
    trigger_sequence_id: null,  // 单次点击，无需引用序列
    description: "点击产品名称进入详情页"
}]->(State:ProductDetailPage)

(State:ProductDetailPage)-[Action {
    type: "click",
    trigger: {ref: "e42", text: "Team", role: "button"},
    trigger_sequence_id: "seq_456",  // 引用完整操作序列
    description: "点击 Team 标签查看团队"
}]->(State:TeamSection)
```

---

## 3. Action 的双重设计

### 3.1 trigger vs trigger_sequence_id

```python
class Action:
    # 自包含：直接执行所需的信息
    trigger: Optional[Dict[str, Any]] = {
        "ref": "e42",      # 元素引用（必需）
        "text": "Team",    # 元素文本（可选）
        "role": "button"   # ARIA 角色（可选）
    }
    
    # 可选引用：指向完整操作序列（提供上下文）
    trigger_sequence_id: Optional[str] = "seq_456"
```

### 3.2 使用场景

| 场景 | trigger | trigger_sequence_id | 说明 |
|------|---------|---------------------|------|
| **单步跳转** | {ref: "e99", text: "Login"} | None | 简单点击，不需要上下文 |
| **多步操作最后一步** | {ref: "e42", text: "Submit"} | "seq_register" | 引用"填写注册表单"序列 |
| **自动跳转** | None | None | 页面自动重定向（无触发元素） |

### 3.3 查询模式

```python
# 执行 Action（只需 trigger）
action = memory.get_action(source_state_id, target_state_id)
ref = action.trigger["ref"]
await browser.click(ref=ref)  # ✅ 不需要额外查询

# 获取完整上下文（可选）
if action.trigger_sequence_id:
    sequence = memory.get_intent_sequence(action.trigger_sequence_id)
    # 可以看到完整的操作流程，用于理解/学习
```

---

## 4. 核心设计：标记类型 + 分层返回

### 4.1 设计原则

**双层解决方案**：
1. **数据层（标记类型）** - IntentSequence 自包含语义信息
2. **接口层（分层返回）** - 根据查询场景返回适当的数据结构

### 4.2 为什么需要标记类型？

**问题**：IntentSequence 可能包含导致页面跳转的操作

```python
# 例如：点击 "Team" 按钮
IntentSequence {
    description: "点击 Team 标签",
    intents: [{type: "click", ref: "e42", text: "Team"}]
    # ❓ 这个操作会导致页面跳转吗？
}
```

**如果不标记**：
- ❌ Agent 执行后页面突然跳转，感到困惑
- ❌ 无法区分"页面内操作"和"导致跳转的操作"
- ❌ Replay 时不知道何时等待页面加载

**标记后**：
```python
IntentSequence {
    description: "点击 Team 标签",
    intents: [{type: "click", ref: "e42", text: "Team"}],
    causes_navigation: true,  # ✅ 明确：会跳转
    navigation_target_state_id: "state_team"  # ✅ 提供目标
}
```

### 4.3 为什么需要分层返回？

**问题**：不同查询场景需要不同的数据组合

#### 场景冲突示例

```python
# Agent 查询："从产品页到团队页"
# 如果返回所有数据：
{
    "states": [State(产品页), State(团队页)],
    "actions": [
        Action(trigger={ref: "e42", text: "Team"})
    ],
    "intent_sequences": [
        IntentSequence(intents=[{ref: "e42", text: "Team"}])
    ]
}

# ❌ Agent 困惑：
# 1. 我应该执行 Action 还是 IntentSequence？
# 2. 它们的 ref 都是 "e42"，是重复吗？
# 3. 执行一次还是两次？
```

**分层返回后**：

```python
# 导航查询 → 只返回 Actions
NavigationResult {
    states: [...],
    actions: [Action(trigger={ref: "e42"})]
    # ✅ 不返回 intent_sequences，避免混淆
}

# 操作查询 → 只返回 IntentSequences
ActionResult {
    sequences: [
        IntentSequence(
            intents=[{ref: "e42"}],
            causes_navigation: true  # ✅ 有标记，Agent 知道会跳转
        )
    ]
}
```

### 4.4 IntentSequence 完整定义

```python
class IntentSequence(BaseModel):
    """操作序列节点
    
    包含页面上的一组相关操作，可能是：
    - 纯页面内操作（滚动、输入但不提交）
    - 导致页面跳转的操作（点击链接、提交表单）
    """
    
    # 基础字段
    id: str = Field(..., description="唯一标识")
    description: str = Field(..., description="语义描述")
    embedding_vector: Optional[List[float]] = Field(
        default=None, 
        description="向量表示，用于语义检索"
    )
    intents: List[Intent] = Field(
        default_factory=list,
        description="操作列表"
    )
    timestamp: int = Field(..., description="开始时间戳")
    
    # ✨ 导航标记（核心）
    causes_navigation: bool = Field(
        default=False,
        description="是否导致页面跳转"
    )
    navigation_target_state_id: Optional[str] = Field(
        default=None,
        description="如果导致跳转，目标 State 的 ID"
    )
    
    # 元数据
    user_id: Optional[str] = None
    session_id: Optional[str] = None
```

### 4.4b CognitivePhrase 完整定义

```python
class CognitivePhrase(BaseModel):
    """认知短语 - 完整的任务工作流
    
    代表一个完整的、用户录制/验证过的任务流程。
    包含完整的结构化执行计划，可以直接 replay。
    """
    
    # 基础字段
    id: str = Field(..., description="唯一标识")
    label: str = Field(..., description="简短标签（如'查看 PH 团队信息'）")
    description: str = Field(..., description="详细描述")
    embedding_vector: Optional[List[float]] = Field(
        default=None,
        description="向量表示，用于语义检索"
    )
    
    # ✨ 核心：结构化执行计划（唯一的路径表示）
    execution_plan: List[ExecutionStep] = Field(
        default_factory=list,
        description="结构化执行计划"
    )
    
    # 统计信息
    access_count: int = Field(default=0, description="访问次数")
    success_count: int = Field(default=0, description="成功执行次数")
    last_accessed: Optional[int] = Field(default=None, description="最后访问时间")
    
    # 元数据
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    created_at: Optional[int] = None


class ExecutionStep(BaseModel):
    """执行计划中的一步
    
    明确区分页面内操作和跳转操作。
    """
    
    index: int = Field(..., description="步骤序号（1-based）")
    state_id: str = Field(..., description="当前页面的 State ID")
    
    # 页面内操作（不导致跳转的 IntentSequences）
    in_page_sequence_ids: List[str] = Field(
        default_factory=list,
        description="页面内操作序列的 ID 列表"
    )
    
    # 跳转操作（导致页面跳转）
    navigation_action_id: Optional[str] = Field(
        default=None,
        description="跳转到下一页的 Action ID（最后一步为 None）"
    )
    
    # 或者直接引用导致跳转的 IntentSequence
    navigation_sequence_id: Optional[str] = Field(
        default=None,
        description="导致跳转的 IntentSequence ID（如果有）"
    )
```

**关键点**：

1. **execution_plan 是唯一的路径表示**：
   - 每一步在哪个页面（state_id）
   - 每一步执行哪些页面内操作（in_page_sequence_ids）
   - 如何跳转到下一页（navigation_action_id）

2. **区分页面内操作和跳转操作**：
   ```python
   ExecutionStep {
       state_id: "产品页",
       in_page_sequence_ids: ["seq_scroll"],  # 滚动浏览（不跳转）
       navigation_action_id: "action_to_team"  # 点击 Team 跳转
   }
   ```

3. **完全基于 execution_plan 的 replay**：
   - 不需要其他辅助字段
   - execution_plan 包含所有必要信息
   - 精确可重现

### 4.5 数据流：如何创建

```python
# WorkflowProcessor 创建流程
async def _process_workflow(self, recording):
    # 1. 按 URL 分段
    segments = segment_by_url(recording)
    
    # 2. 为每个段创建 State 和 IntentSequences
    states = []
    all_intent_sequences = []
    
    for segment in segments:
        state = create_state(segment)
        
        # 创建 IntentSequences（包含所有操作）
        intent_sequences = create_intent_sequences(segment)
        all_intent_sequences.extend(intent_sequences)
        
        # 保存到 State（用于创建过程）
        state.intent_sequences = intent_sequences
        
        states.append(state)
    
    # 3. 创建 Actions（页面间跳转）
    actions = []
    for i in range(len(states) - 1):
        source = states[i]
        target = states[i + 1]
        
        # 找到触发跳转的操作
        trigger = find_transition_trigger(segments[i])
        
        # 4. ✨ 在 source 的 IntentSequences 中找到匹配的序列
        matching_sequence = find_sequence_with_trigger(
            source.intent_sequences,
            trigger["ref"]
        )
        
        # 5. ✨ 标记这个序列导致跳转
        if matching_sequence:
            matching_sequence.causes_navigation = True
            matching_sequence.navigation_target_state_id = target.id
        
        # 6. 创建 Action
        action = Action(
            source=source.id,
            target=target.id,
            trigger=trigger,
            trigger_sequence_id=matching_sequence.id if matching_sequence else None
        )
        actions.append(action)
    
    # 7. ✨ 创建 CognitivePhrase（结构化执行计划）
    cognitive_phrase = self._create_cognitive_phrase(
        states=states,
        actions=actions,
        intent_sequences=all_intent_sequences
    )
    
    return states, actions, all_intent_sequences, cognitive_phrase

def _create_cognitive_phrase(
    self,
    states: List[State],
    actions: List[Action],
    intent_sequences: List[IntentSequence]
) -> CognitivePhrase:
    """创建 CognitivePhrase（结构化执行计划）"""
    
    # 构建 execution_plan
    execution_plan = []
    
    for i, state in enumerate(states):
        # 分类 IntentSequences：页面内 vs 导致跳转
        in_page_sequences = []
        navigation_sequence = None
        
        for seq in state.intent_sequences:
            if seq.causes_navigation:
                navigation_sequence = seq
            else:
                in_page_sequences.append(seq)
        
        # 找到对应的 Action
        navigation_action = None
        if i < len(states) - 1:
            navigation_action = actions[i]
        
        # 创建 ExecutionStep
        step = ExecutionStep(
            index=i + 1,
            state_id=state.id,
            in_page_sequence_ids=[seq.id for seq in in_page_sequences],
            navigation_action_id=navigation_action.id if navigation_action else None,
            navigation_sequence_id=navigation_sequence.id if navigation_sequence else None
        )
        
        execution_plan.append(step)
    
    # 生成 CognitivePhrase
    phrase = CognitivePhrase(
        id=str(uuid.uuid4()),
        label=self._generate_phrase_label(states),
        description=await self._generate_phrase_description(states, actions),
        embedding_vector=None,  # 稍后生成
        execution_plan=execution_plan,
        user_id=self.user_id,
        session_id=self.session_id,
        created_at=int(time.time() * 1000)
    )
    
    # 生成 embedding
    if self.embedding_model:
        phrase.embedding_vector = self.embedding_model.encode(phrase.description)
    
    return phrase
```

---

## 5. 三种查询场景

### 5.1 任务级查询（Task-Level Query）

**使用场景**：
- 用户请求完整任务（如"在淘宝买鼠标"）
- 需要从头到尾的完整流程

**查询接口**：
```python
async def query_task_workflow(target: str) -> WorkflowResult:
    """查询完整任务工作流
    
    Returns:
        WorkflowResult {
            states: List[State],    # 页面序列
            actions: List[Action],  # 页面间跳转
            cognitive_phrases: List[CognitivePhrase]  # 如果匹配
        }
    """
```

**实现策略**：
```python
# 1. 优先查询 CognitivePhrase（用户录制的完整工作流）
query_vector = embedding_service.encode(target)
phrases = vector_search(
    label="CognitivePhrase",
    vector=query_vector,
    topk=5
)

if phrases:
    # 找到匹配的认知短语
    best_phrase = llm_select_best(target, phrases)
    return convert_phrase_to_workflow(best_phrase)

# 2. 如果没有 CognitivePhrase，使用任务分解 + 组合检索
dag = await decompose_task(target)
results = []
for subtask in dag.topological_order():
    # 每个子任务可能是导航查询或操作查询
    result = await query_subtask(subtask)
    results.append(result)

# 3. 链接成完整工作流
workflow = assemble_workflow(results)
return workflow
```

---

### 5.2 导航级查询（Navigation-Level Query）

**使用场景**：
- 已知起点和终点（如"从首页到个人中心"）
- 需要找到导航路径

**查询接口**：
```python
async def query_navigation_path(
    start_description: str,
    end_description: str
) -> PathResult:
    """查询导航路径
    
    Returns:
        PathResult {
            states: List[State],    # 路径上的页面
            actions: List[Action]   # 路径上的操作
        }
    """
```

**实现策略**：
```python
# 1. 语义检索起点和终点 State
start_vector = embedding_service.encode(start_description)
start_states = vector_search(
    label="State",
    vector=start_vector,
    topk=3
)

end_vector = embedding_service.encode(end_description)
end_states = vector_search(
    label="State",
    vector=end_vector,
    topk=3
)

# 2. 图原生路径查询
best_path = None
min_length = float('inf')

for start in start_states:
    for end in end_states:
        # Neo4j shortestPath
        path = graph.query("""
            MATCH path = shortestPath(
                (start:State {id: $start_id})-[a:Action*]-(end:State {id: $end_id})
            )
            RETURN path
        """, start_id=start.id, end_id=end.id)
        
        if path and len(path.actions) < min_length:
            best_path = path
            min_length = len(path.actions)

# 3. 如果没有路径，返回 None
return best_path
```

---

### 5.3 操作级查询（Action-Level Query）

**使用场景**：
- Agent 当前在某个页面
- 需要知道"在这个页面能做什么"
- 查询特定操作（如"如何查看团队信息"）

**查询接口**：
```python
async def query_page_actions(
    state_id: str,
    query: str
) -> List[IntentSequence]:
    """查询页面内操作
    
    Returns:
        List[IntentSequence]  # 匹配的操作序列
    """
```

**实现策略**：
```python
# 1. 向量检索 IntentSequence（过滤：只在当前 State）
query_vector = embedding_service.encode(query)

sequences = graph.query("""
    MATCH (s:State {id: $state_id})-[:HAS_SEQUENCE]->(seq:IntentSequence)
    CALL db.index.vector.queryNodes(
        'intent_sequence_embeddings',
        10,
        $query_vector
    ) YIELD node, score
    WHERE node = seq
    RETURN seq, score
    ORDER BY score DESC
    LIMIT 5
""", state_id=state_id, query_vector=query_vector)

# 2. LLM 评估最佳匹配
if llm_provider:
    best_sequence = await llm_select_best(query, sequences)
    return [best_sequence]

return sequences
```

**扩展：探索式查询（当前页面能做什么？）**
```python
# 不提供 query，返回所有可能操作
all_actions = graph.query("""
    MATCH (s:State {id: $state_id})-[:HAS_SEQUENCE]->(seq:IntentSequence)
    MATCH (s)-[a:Action]->(next:State)
    RETURN seq, a, next
""", state_id=state_id)

return {
    "page_actions": all_actions.sequences,      # 页面内操作
    "navigations": all_actions.actions          # 可能的跳转
}
```

---

## 6. Replay 和执行示例

### 6.1 Replay CognitivePhrase（使用结构化执行计划）

```python
async def replay_cognitive_phrase(phrase: CognitivePhrase, memory: Memory):
    """完整 Replay 一个认知短语（录制的工作流）
    
    使用 execution_plan 进行精确 replay
    """
    
    # 1. 导航到起点
    first_step = phrase.execution_plan[0]
    start_state = memory.get_state(first_step.state_id)
    await browser.goto(start_state.page_url)
    print(f"✅ 到达起点: {start_state.description}")
    
    # 2. 遍历执行计划
    for step in phrase.execution_plan:
        state = memory.get_state(step.state_id)
        print(f"\n📍 Step {step.index}: {state.description}")
        
        # 2a. 执行页面内操作（不导致跳转）
        for seq_id in step.in_page_sequence_ids:
            sequence = memory.get_intent_sequence(seq_id)
            if sequence:
                print(f"  🎬 {sequence.description}")
                await execute_intent_sequence(sequence)
                # 这些操作不会导致跳转（已经分层了）
        
        # 2b. 执行跳转操作
        if step.navigation_action_id:
            action = memory.get_action_by_id(step.navigation_action_id)
            if action:
                print(f"  ➡️  {action.description}")
                
                # 可以选择执行 Action 或对应的 IntentSequence
                if action.trigger and action.trigger.get("ref"):
                    await browser.click(ref=action.trigger["ref"])
                
                await browser.wait_for_navigation()
                next_state = memory.get_state(action.target)
                print(f"  ✅ 已到达: {next_state.description}")
    
    print("\n✅ Replay 完成！")

async def execute_intent_sequence(sequence: IntentSequence):
    """执行一个 IntentSequence"""
    for intent in sequence.intents:
        # 获取操作类型
        intent_type = intent.get("type") if isinstance(intent, dict) else intent.type
        
        if intent_type == "click":
            ref = intent.get("ref") if isinstance(intent, dict) else intent.element_ref
            await browser.click(ref=ref)
            print(f"    ✓ 点击: {ref}")
        
        elif intent_type == "input":
            ref = intent.get("ref") if isinstance(intent, dict) else intent.element_ref
            value = intent.get("value") if isinstance(intent, dict) else intent.value
            await browser.fill(ref=ref, value=value)
            print(f"    ✓ 输入: {value}")
        
        elif intent_type == "scroll":
            value = intent.get("value") if isinstance(intent, dict) else intent.value
            await browser.scroll(direction=value)
            print(f"    ✓ 滚动: {value}")
        
        # 其他操作类型...
```

**输出示例**：
```
✅ 到达起点: Product Hunt 首页

📍 Step 1: Product Hunt 首页
  🎬 向下滚动浏览
    ✓ 滚动: down
  🎬 点击 Leaderboard 导航
    ✓ 点击: e1
  ➡️  跳转到: state_leaderboard

📍 Step 2: 排行榜页面
  🎬 点击 Cursor 产品
    ✓ 点击: e2
  ➡️  跳转到: state_product

📍 Step 3: 产品详情页
  🎬 向下滚动查看产品
    ✓ 滚动: down
  🎬 点击 Team 标签
    ✓ 点击: e3
  ➡️  跳转到: state_team

📍 Step 4: 团队信息页面
  (最后一步，无需操作)

✅ Replay 完成！
```

### 6.2 执行导航查询结果

```python
# Agent 执行导航查询的结果
async def execute_navigation_result(result: NavigationResult):
    """执行导航查询返回的路径"""
    
    print(f"开始导航: {result.states[0].description} → {result.states[-1].description}")
    
    # 遍历路径
    for i, state in enumerate(result.states[:-1]):
        action = result.actions[i]
        next_state = result.states[i + 1]
        
        print(f"\n从 {state.description} 到 {next_state.description}")
        print(f"  操作: {action.description}")
        
        # 直接执行 Action.trigger
        if action.trigger and action.trigger.get("ref"):
            await browser.click(ref=action.trigger["ref"])
            print(f"  ✓ 点击: {action.trigger.get('text', action.trigger['ref'])}")
            
            # 等待跳转
            await browser.wait_for_navigation()
            print(f"  ✅ 已到达: {next_state.description}")
        else:
            print(f"  ⚠️ 自动跳转（无需操作）")
            await browser.wait_for_navigation()
    
    print("\n✅ 导航完成！")
```

### 6.3 执行操作查询结果

```python
# Agent 执行操作查询的结果
async def execute_action_query_result(sequences: List[IntentSequence]):
    """执行操作查询返回的 IntentSequences"""
    
    if not sequences:
        print("❌ 没有找到匹配的操作")
        return
    
    # 选择最佳匹配（通常是第一个）
    best_sequence = sequences[0]
    
    print(f"执行操作: {best_sequence.description}")
    
    # 检查是否会导致跳转
    if best_sequence.causes_navigation:
        print(f"  ⚠️ 此操作将导致页面跳转")
        target_state = memory.get_state(best_sequence.navigation_target_state_id)
        if target_state:
            print(f"  目标页面: {target_state.description}")
    
    # 执行操作
    await execute_intent_sequence(best_sequence)
    
    # 如果导致跳转，等待
    if best_sequence.causes_navigation:
        await browser.wait_for_navigation()
        print(f"  ✅ 已跳转到新页面")
    else:
        print(f"  ✅ 页面内操作完成")
```

### 6.4 执行任务查询结果（结构化计划）

```python
# Agent 执行任务查询的结果
async def execute_task_result(result: TaskResult):
    """执行任务查询返回的结构化计划"""
    
    print(f"开始执行任务: {result.cognitive_phrase.label if result.cognitive_phrase else '未知任务'}")
    
    for step in result.execution_plan:
        print(f"\n📍 Step {step.index}: {step.state.description}")
        
        # 1. 执行页面内操作
        if step.in_page_operations:
            print(f"  页面内操作:")
            for sequence in step.in_page_operations:
                print(f"    - {sequence.description}")
                await execute_intent_sequence(sequence)
                # 不需要检查 causes_navigation，因为已经分层了
        
        # 2. 执行跳转（如果有）
        if step.navigation:
            next_state = result.execution_plan[step.index].state  # step.index 是 1-based
            print(f"  跳转操作: {step.navigation.description}")
            
            if step.navigation.trigger and step.navigation.trigger.get("ref"):
                await browser.click(ref=step.navigation.trigger["ref"])
                await browser.wait_for_navigation()
                print(f"  ✅ 已到达: {next_state.description}")
    
    print("\n✅ 任务执行完成！")
```

---

## 7. 向量索引配置

### 7.1 需要建立的索引

```cypher
// 1. State 向量索引
CREATE VECTOR INDEX state_embeddings
FOR (s:State)
ON s.embedding_vector
OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}}

// 2. IntentSequence 向量索引 ✨ NEW
CREATE VECTOR INDEX intent_sequence_embeddings
FOR (seq:IntentSequence)
ON seq.embedding_vector
OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}}

// 3. CognitivePhrase 向量索引
CREATE VECTOR INDEX cognitive_phrase_embeddings
FOR (p:CognitivePhrase)
ON p.embedding_vector
OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}}

// 4. ID 索引（加速精确查询）
CREATE INDEX state_id_index FOR (s:State) ON (s.id)
CREATE INDEX sequence_id_index FOR (seq:IntentSequence) ON (seq.id)
```

---

## 8. Memory 查询接口设计（方案 5：上下文感知）

### 8.1 核心设计理念

**单一智能查询入口 + 上下文自动判断**

- 根据参数自动判断查询类型（navigation / action / task）
- 支持显式指定类型（避免误判）
- 保留 1 个便捷方法（最常用的导航场景）
- 基础方法独立（不是查询）

### 8.2 主接口定义

```python
class Memory:
    """Memory 主接口"""
    
    # ============ 统一智能查询入口 ============
    
    async def query(
        self,
        target: str,
        *,
        # 上下文参数（根据这些自动判断查询类型）
        current_state: Optional[str] = None,      # 有 → action 查询
        start_state: Optional[str] = None,        # start + end → navigation
        end_state: Optional[str] = None,
        # 显式指定类型（避免自动判断错误）
        as_type: Optional[Literal["navigation", "action", "task"]] = None,
        # 通用参数
        user_id: Optional[str] = None,
        top_k: int = 10
    ) -> QueryResult:
        """统一智能查询入口
        
        自动判断逻辑：
        1. 如果 as_type 指定 → 使用指定类型
        2. 如果有 start_state + end_state → navigation
        3. 如果有 current_state → action
        4. 否则 → task
        
        Args:
            target: 查询目标描述
            current_state: 当前所在页面 State ID（action 查询必需）
            start_state: 起点 State（navigation 查询必需）
            end_state: 终点 State（navigation 查询必需）
            as_type: 显式指定查询类型
            user_id: 用户 ID（可选过滤）
            top_k: 返回结果数量
        
        Returns:
            QueryResult - 统一查询结果
        
        Examples:
            # 任务查询（最简单）
            result = await memory.query("在 PH 查看团队信息")
            
            # 操作查询（提供当前状态）
            result = await memory.query(
                "查看团队信息",
                current_state="产品页"
            )
            
            # 导航查询（提供起点终点）
            result = await memory.query(
                "导航",
                start_state="产品页",
                end_state="团队页"
            )
            
            # 显式指定类型
            result = await memory.query(
                "查看团队",
                as_type="task"
            )
            
            # 探索查询（空 target + current_state）
            result = await memory.query("", current_state="产品页")
        """
        pass
    
    # ============ 便捷方法（最常用场景）============
    
    async def navigate(
        self,
        start: str,
        end: str,
        user_id: Optional[str] = None
    ) -> QueryResult:
        """导航便捷方法
        
        语法糖，等价于：
        query("", start_state=start, end_state=end, as_type="navigation")
        
        Args:
            start: 起点 State ID 或描述
            end: 终点 State ID 或描述
        
        Returns:
            QueryResult with query_type="navigation"
        """
        return await self.query(
            "",
            start_state=start,
            end_state=end,
            as_type="navigation",
            user_id=user_id
        )
    
    # ============ 基础查询方法（不是智能查询）============
    
    def get_state(self, state_id: str) -> Optional[State]:
        """根据 ID 获取 State（基础操作）"""
        pass
    
    def get_intent_sequence(self, sequence_id: str) -> Optional[IntentSequence]:
        """根据 ID 获取 IntentSequence（基础操作）"""
        pass
    
    def get_action(
        self, 
        source_id: str, 
        target_id: str
    ) -> Optional[Action]:
        """获取两个 State 之间的 Action（基础操作）"""
        pass
    
    def get_action_by_id(self, action_id: str) -> Optional[Action]:
        """根据 ID 获取 Action（基础操作）"""
        pass
    
    def get_cognitive_phrase(self, phrase_id: str) -> Optional[CognitivePhrase]:
        """根据 ID 获取 CognitivePhrase（基础操作）"""
        pass
```

### 8.3 查询实现逻辑

```python
async def query(self, target: str, **kwargs) -> QueryResult:
    """智能查询实现"""
    
    # 1. 确定查询类型
    query_type = self._determine_query_type(target, kwargs)
    
    # 2. 根据类型分发
    if query_type == "navigation":
        return await self._query_navigation(
            kwargs.get("start_state"),
            kwargs.get("end_state"),
            kwargs.get("user_id")
        )
    
    elif query_type == "action":
        return await self._query_action(
            target,
            kwargs.get("current_state"),
            kwargs.get("user_id"),
            kwargs.get("top_k", 10)
        )
    
    else:  # task
        return await self._query_task(
            target,
            kwargs.get("user_id")
        )

def _determine_query_type(
    self, 
    target: str, 
    kwargs: Dict
) -> Literal["navigation", "action", "task"]:
    """确定查询类型"""
    
    # 1. 显式指定
    if kwargs.get("as_type"):
        return kwargs["as_type"]
    
    # 2. 有 start + end → navigation
    if kwargs.get("start_state") and kwargs.get("end_state"):
        return "navigation"
    
    # 3. 有 current_state → action
    if kwargs.get("current_state"):
        return "action"
    
    # 4. 默认 → task
    return "task"

# ============ 内部实现方法 ============

async def _query_navigation(
    self,
    start: str,
    end: str,
    user_id: Optional[str]
) -> QueryResult:
    """导航查询实现"""
    
    # 1. 语义检索起点和终点
    start_vector = self.embedding_service.encode(start)
    start_states = self.state_manager.search_states_by_embedding(
        start_vector, top_k=3, user_id=user_id
    )
    
    end_vector = self.embedding_service.encode(end)
    end_states = self.state_manager.search_states_by_embedding(
        end_vector, top_k=3, user_id=user_id
    )
    
    # 2. 图原生路径查询
    best_path = None
    min_length = float('inf')
    
    for start_state in start_states:
        for end_state in end_states:
            path = self.graph_store.find_shortest_path(
                start_state.id,
                end_state.id
            )
            
            if path and len(path.actions) < min_length:
                best_path = path
                min_length = len(path.actions)
    
    # 3. 返回结果
    if best_path:
        return QueryResult(
            query_type="navigation",
            success=True,
            states=best_path.states,
            actions=best_path.actions
        )
    else:
        return QueryResult(
            query_type="navigation",
            success=False,
            metadata={"error": "No path found"}
        )

async def _query_action(
    self,
    target: str,
    state_id: str,
    user_id: Optional[str],
    top_k: int
) -> QueryResult:
    """操作查询实现"""
    
    # 如果 target 为空，返回所有能力
    if not target:
        capabilities = self._get_page_capabilities(state_id)
        return QueryResult(
            query_type="action",
            success=True,
            intent_sequences=capabilities["page_actions"],
            actions=capabilities["navigations"],
            metadata={"mode": "explore"}
        )
    
    # 向量检索 IntentSequences（过滤到当前 State）
    query_vector = self.embedding_service.encode(target)
    sequences = self.intent_sequence_manager.search_by_embedding(
        query_vector,
        state_id=state_id,
        top_k=top_k
    )
    
    # LLM 评估最佳匹配（可选）
    if self.llm_provider and sequences:
        best_sequence = await self._llm_select_best(target, sequences)
        sequences = [best_sequence]
    
    return QueryResult(
        query_type="action",
        success=len(sequences) > 0,
        intent_sequences=sequences
    )

async def _query_task(
    self,
    target: str,
    user_id: Optional[str]
) -> QueryResult:
    """任务查询实现"""
    
    # 1. 优先查询 CognitivePhrase
    query_vector = self.embedding_service.encode(target)
    phrases = self.phrase_manager.search_phrases_by_embedding(
        query_vector,
        top_k=5
    )
    
    if phrases:
        # LLM 选择最佳匹配
        best_phrase = await self._llm_select_best(target, phrases)
        
        # 构建执行计划
        return QueryResult(
            query_type="task",
            success=True,
            cognitive_phrase=best_phrase,
            execution_plan=best_phrase.execution_plan,
            metadata={"method": "cognitive_phrase"}
        )
    
    # 2. 如果没有 CognitivePhrase，使用任务分解
    dag = await self.task_decomposer.decompose(target)
    results = await self._execute_dag(dag)
    
    # 3. 组装工作流
    workflow = self._assemble_workflow(results)
    
    return QueryResult(
        query_type="task",
        success=True,
        states=workflow.states,
        actions=workflow.actions,
        metadata={"method": "task_decomposition"}
    )

def _get_page_capabilities(self, state_id: str) -> Dict[str, List]:
    """获取页面能力（探索式查询）"""
    
    # 获取页面内操作
    sequences = self.intent_sequence_manager.list_by_state(state_id)
    
    # 获取可能的跳转
    outgoing_actions = self.action_manager.list_outgoing_actions(state_id)
    
    return {
        "page_actions": sequences,
        "navigations": outgoing_actions
    }
```

### 8.4 统一返回类型

```python
class QueryResult(BaseModel):
    """统一查询结果"""
    
    # 元信息
    query_type: Literal["navigation", "action", "task"]
    success: bool
    
    # 通用字段（根据 query_type 填充）
    states: List[State] = Field(default_factory=list)
    actions: List[Action] = Field(default_factory=list)
    intent_sequences: List[IntentSequence] = Field(default_factory=list)
    
    # 任务级特有
    cognitive_phrase: Optional[CognitivePhrase] = None
    execution_plan: List[ExecutionStep] = Field(default_factory=list)
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # ============ 便捷转换方法 ============
    
    def as_navigation(self) -> "NavigationResult":
        """转换为导航结果"""
        if self.query_type != "navigation":
            raise ValueError("Not a navigation query result")
        return NavigationResult(
            states=self.states,
            actions=self.actions
        )
    
    def as_task(self) -> "TaskResult":
        """转换为任务结果"""
        if self.query_type != "task":
            raise ValueError("Not a task query result")
        return TaskResult(
            execution_plan=self.execution_plan,
            cognitive_phrase=self.cognitive_phrase
        )


class NavigationResult(BaseModel):
    """导航查询专用结果"""
    states: List[State]
    actions: List[Action]


class TaskResult(BaseModel):
    """任务查询专用结果"""
    execution_plan: List[ExecutionStep]
    cognitive_phrase: Optional[CognitivePhrase] = None
```

### 8.5 使用示例

```python
# ============ Agent 使用示例 ============

# 1. 任务查询（最简单）
result = await memory.query("在 Product Hunt 查看团队信息")
if result.success and result.query_type == "task":
    # 执行任务
    await execute_task_result(result)

# 2. 操作查询（Agent 在某个页面，想知道能做什么）
result = await memory.query(
    "查看团队信息",
    current_state=current_state_id
)
if result.success:
    # 执行操作
    for sequence in result.intent_sequences:
        await execute_intent_sequence(sequence)
        if sequence.causes_navigation:
            await browser.wait_for_navigation()

# 3. 导航查询（使用统一接口）
result = await memory.query(
    "导航",
    start_state="产品页",
    end_state="团队页"
)
# 或使用便捷方法
result = await memory.navigate("产品页", "团队页")

if result.success:
    # 执行导航
    for action in result.actions:
        await browser.click(ref=action.trigger["ref"])
        await browser.wait_for_navigation()

# 4. 探索查询（空 target，查看当前页面能做什么）
result = await memory.query("", current_state=current_state_id)
if result.success:
    print(f"当前页面可以执行 {len(result.intent_sequences)} 个操作")
    print(f"可以跳转到 {len(result.actions)} 个页面")

# 5. 显式指定类型（避免误判）
result = await memory.query(
    "查看产品信息",
    as_type="task"  # 明确指定为任务查询
)
```

### 8.6 IntentSequence Manager（新增）

```python
class IntentSequenceManager:
    """管理 IntentSequence 节点"""
    
    def create_sequence(self, sequence: IntentSequence) -> bool:
        """创建 IntentSequence 节点"""
        pass
    
    def link_to_state(self, state_id: str, sequence_id: str) -> bool:
        """创建 HAS_SEQUENCE 关系"""
        pass
    
    def search_by_embedding(
        self,
        query_vector: List[float],
        state_id: Optional[str] = None,  # 可选：过滤到特定 State
        top_k: int = 10
    ) -> List[Tuple[IntentSequence, float]]:
        """向量检索 IntentSequences"""
        pass
    
    def list_by_state(self, state_id: str) -> List[IntentSequence]:
        """列出某个 State 的所有 IntentSequences"""
        pass
```

---

## 7. Reasoner 重新设计

### 7.1 新的 Reasoner 架构

```python
class Reasoner:
    """Memory 查询推理器"""
    
    def __init__(self, memory: Memory, llm_provider, embedding_service):
        self.memory = memory
        self.llm_provider = llm_provider
        self.embedding_service = embedding_service
        
        # 查询分类器
        self.query_classifier = QueryClassifier(llm_provider)
        
        # 任务分解器
        self.task_decomposer = TaskDecomposer(llm_provider)
    
    async def plan(
        self, 
        target: str, 
        context: Optional[Dict] = None
    ) -> WorkflowResult:
        """统一查询入口
        
        Args:
            target: 查询描述
            context: {
                "current_state_id": "state_123",  // 当前页面（可选）
                "query_type": "task" | "navigation" | "action"  // 可选
            }
        """
        # 1. 智能分类查询类型
        query_type = await self._classify_query(target, context)
        
        # 2. 根据类型分发
        if query_type == "action":
            return await self._handle_action_query(target, context)
        elif query_type == "navigation":
            return await self._handle_navigation_query(target, context)
        else:  # "task"
            return await self._handle_task_query(target, context)
    
    async def _classify_query(
        self, 
        target: str, 
        context: Optional[Dict]
    ) -> str:
        """分类查询类型
        
        Returns:
            "task" | "navigation" | "action"
        """
        # 规则 1: 如果有 current_state_id，可能是 action 查询
        if context and context.get("current_state_id"):
            # 使用 LLM 判断是页面内操作还是导航
            classification = await self.query_classifier.classify(
                target, 
                has_current_page=True
            )
            return classification
        
        # 规则 2: 包含"从...到..."模式，是 navigation 查询
        if "从" in target and "到" in target:
            return "navigation"
        
        # 规则 3: 包含"如何"、"怎么"，可能是 action 查询
        if any(word in target for word in ["如何", "怎么", "怎样"]):
            # 进一步用 LLM 判断
            classification = await self.query_classifier.classify(target)
            return classification
        
        # 默认：task 查询
        return "task"
    
    async def _handle_task_query(
        self, 
        target: str, 
        context: Optional[Dict]
    ) -> WorkflowResult:
        """处理任务级查询"""
        return await self.memory.query_task_workflow(target)
    
    async def _handle_navigation_query(
        self, 
        target: str, 
        context: Optional[Dict]
    ) -> WorkflowResult:
        """处理导航级查询"""
        # 解析起点和终点
        start_desc, end_desc = self._parse_navigation_target(target)
        
        path = await self.memory.query_navigation_path(start_desc, end_desc)
        
        if path:
            return WorkflowResult(
                success=True,
                states=path.states,
                actions=path.actions,
                metadata={"query_type": "navigation"}
            )
        else:
            return WorkflowResult(
                success=False,
                metadata={"query_type": "navigation", "error": "No path found"}
            )
    
    async def _handle_action_query(
        self, 
        target: str, 
        context: Optional[Dict]
    ) -> WorkflowResult:
        """处理操作级查询"""
        state_id = context.get("current_state_id")
        
        sequences = await self.memory.query_page_actions(state_id, target)
        
        if sequences:
            return WorkflowResult(
                success=True,
                intent_sequences=sequences,
                metadata={"query_type": "action", "state_id": state_id}
            )
        else:
            return WorkflowResult(
                success=False,
                metadata={"query_type": "action", "error": "No actions found"}
            )
```

---

## 8. WorkflowProcessor 更新

### 8.1 创建 IntentSequence 节点

```python
class WorkflowProcessor:
    
    async def _process_state(self, state: State, segment: URLSegment):
        """处理单个 State（更新）"""
        
        # 1. 创建 IntentSequences
        for sequence in state.intent_sequences:
            # 生成描述和 embedding
            if not sequence.description:
                sequence.description = await self._generate_sequence_description(sequence)
            
            if not sequence.embedding_vector and self.embedding_model:
                sequence.embedding_vector = self.embedding_model.encode(sequence.description)
            
            # ✨ 创建 IntentSequence 节点
            success = self.memory.intent_sequence_manager.create_sequence(sequence)
            
            if success:
                # ✨ 创建 HAS_SEQUENCE 关系
                self.memory.intent_sequence_manager.link_to_state(
                    state_id=state.id,
                    sequence_id=sequence.id
                )
        
        # 2. 创建/更新 State 节点（不再嵌套 intent_sequences）
        state_exists = self.memory.state_manager.get_state(state.id)
        if state_exists:
            self.memory.state_manager.update_state(state)
        else:
            self.memory.state_manager.create_state(state)
    
    async def _create_actions(self, states: List[State], segments: List[URLSegment]):
        """创建 Actions（更新）"""
        
        actions = []
        for i in range(len(states) - 1):
            source = states[i]
            target = states[i + 1]
            segment = segments[i]
            
            # 查找触发跳转的操作
            trigger = self._find_transition_trigger(segment)
            
            # ✨ 查找对应的 IntentSequence
            trigger_sequence_id = None
            if trigger and trigger.get("ref"):
                # 在 source State 的 IntentSequences 中查找匹配的序列
                trigger_sequence_id = self._find_matching_sequence(
                    state=source,
                    trigger_ref=trigger["ref"]
                )
            
            action = Action(
                source=source.id,
                target=target.id,
                type=self._determine_action_type(trigger),
                trigger=trigger,
                trigger_sequence_id=trigger_sequence_id,  # ✨ 新增
                timestamp=segment.start_time,
                user_id=self.user_id,
                session_id=self.session_id
            )
            
            # 生成描述
            action.description = await self._generate_action_description(action)
            
            actions.append(action)
        
        return actions
    
    def _find_matching_sequence(
        self, 
        state: State, 
        trigger_ref: str
    ) -> Optional[str]:
        """查找匹配触发元素的 IntentSequence
        
        策略：
        1. 遍历 state.intent_sequences
        2. 查找 intents 中最后一个操作的 ref 匹配 trigger_ref
        3. 返回匹配的 sequence.id
        """
        for sequence in state.intent_sequences:
            if sequence.intents:
                # 检查最后一个 intent
                last_intent = sequence.intents[-1]
                if hasattr(last_intent, 'element_ref'):
                    if last_intent.element_ref == trigger_ref:
                        return sequence.id
                elif isinstance(last_intent, dict):
                    if last_intent.get("ref") == trigger_ref:
                        return sequence.id
        
        return None
```

---

## 9. 数据迁移策略

### 9.1 迁移步骤

```python
async def migrate_to_v2():
    """从旧模型迁移到新模型"""
    
    # 1. 遍历所有 States
    all_states = memory.state_manager.list_states()
    
    for state in all_states:
        # 2. 提取嵌套的 intent_sequences
        for sequence_data in state.intent_sequences:
            if isinstance(sequence_data, dict):
                sequence = IntentSequence.from_dict(sequence_data)
            else:
                sequence = sequence_data
            
            # 3. 创建独立的 IntentSequence 节点
            memory.intent_sequence_manager.create_sequence(sequence)
            
            # 4. 创建 HAS_SEQUENCE 关系
            memory.intent_sequence_manager.link_to_state(
                state_id=state.id,
                sequence_id=sequence.id
            )
        
        # 5. 清空 State 的 intent_sequences（不再嵌套）
        # （Neo4j 中可以保留，但不用于查询）
    
    # 6. 更新所有 Actions，添加 trigger_sequence_id
    all_actions = memory.action_manager.list_actions()
    
    for action in all_actions:
        if action.trigger and action.trigger.get("ref"):
            # 查找对应的 IntentSequence
            source_state = memory.get_state(action.source)
            sequence_id = find_matching_sequence(source_state, action.trigger["ref"])
            
            if sequence_id:
                action.trigger_sequence_id = sequence_id
                memory.action_manager.update_action(action)
    
    # 7. 创建向量索引
    memory.graph_store.execute("""
        CREATE VECTOR INDEX intent_sequence_embeddings
        FOR (seq:IntentSequence)
        ON seq.embedding_vector
        OPTIONS {indexConfig: {`vector.dimensions`: 1024}}
    """)
    
    print("Migration to v2 completed!")
```

---

## 10. 查询性能对比

### 10.1 操作级查询性能

| 方案 | 查询方式 | 复杂度 | 性能 |
|------|---------|--------|------|
| **旧设计（嵌套）** | 遍历所有 States，内存计算相似度 | O(n×m) | 慢（数据量大时） |
| **新设计（独立节点）** | Neo4j 向量索引直接查询 | O(log n) | 快（利用索引） |

### 10.2 查询示例对比

**旧设计**：
```python
# 需要加载所有 States 到内存
all_states = memory.list_states()  # 假设 1000 个 States

similarities = []
for state in all_states:  # O(1000)
    for seq in state.intent_sequences:  # O(5)
        if seq.embedding_vector:
            similarity = cosine_similarity(query_vector, seq.embedding_vector)
            similarities.append((seq, state, similarity))

# 总复杂度：O(1000 × 5 × 1024) = O(5M) 次计算
```

**新设计**：
```cypher
// Neo4j 向量索引查询
CALL db.index.vector.queryNodes(
    'intent_sequence_embeddings',
    10,
    [query_vector]
) YIELD node, score
RETURN node, score
LIMIT 5

// 复杂度：O(log n) = O(log 5000) ≈ 12 次比较
```

---

## 11. 总结

### 11.1 核心改进

| 方面 | 改进 |
|------|------|
| **数据模型** | IntentSequence 提升为独立节点 ✅ |
| **导航标记** | IntentSequence 添加 causes_navigation 标记 ✅ |
| **查询性能** | 支持 Neo4j 向量索引，O(log n) 复杂度 ✅ |
| **查询场景** | 明确区分任务级、导航级、操作级 ✅ |
| **Action 设计** | trigger（自包含）+ trigger_sequence_id（上下文） ✅ |
| **接口设计** | 标记类型 + 分层返回（双层解决方案）✅ |
| **查询接口** | 上下文感知查询（方案 5）- 单一智能入口 ✅ |
| **CognitivePhrase** | 包含结构化执行计划（execution_plan）✅ |
| **Replay 能力** | 基于 execution_plan 的精确 replay ✅ |

### 11.2 待实现清单

#### Phase 1: 数据模型更新（Breaking Changes）
- [ ] 修改 IntentSequence 添加 causes_navigation 和 navigation_target_state_id
- [ ] 修改 Action 添加 trigger_sequence_id（已部分完成）
- [ ] 添加 Action.id 字段（支持 ExecutionStep 引用）
- [ ] 创建 ExecutionStep 数据模型
- [ ] 修改 CognitivePhrase：删除 state_path/action_path，只保留 execution_plan
- [ ] **删除 State.intent_sequences 字段**（IntentSequence 独立存储）
- [ ] **删除 State.add_intent_sequence() 方法**
- [ ] **删除 WorkflowMemory.add_intent_sequence() 方法**

#### Phase 2: 存储层更新（全新架构）
- [ ] IntentSequence 存储为独立节点
- [ ] 添加 HAS_SEQUENCE 关系类型
- [ ] 创建 IntentSequenceManager
- [ ] 创建 Neo4j 向量索引（intent_sequence_embeddings）
- [ ] 更新 State 存储逻辑（无嵌套字段）
- [ ] 清空旧数据，重建数据库

#### Phase 3: WorkflowProcessor 更新
- [ ] 修改 _process_workflow 标记 causes_navigation
- [ ] 实现 _create_cognitive_phrase 创建 execution_plan
- [ ] **更新 IntentSequence 创建流程**：
  - **删除** `self.memory.add_intent_sequence(state_id, sequence)`
  - **改用** `self.memory.intent_sequence_manager.create_sequence(sequence)`
  - **改用** `self.memory.intent_sequence_manager.link_to_state(state_id, sequence.id)`
- [ ] 更新 Action 创建流程（关联 trigger_sequence_id）

#### Phase 4: 查询接口实现（方案 5：上下文感知）
- [ ] 创建 QueryResult 统一返回类型
- [ ] 实现 Memory.query() 统一智能查询入口
  - 根据参数自动判断查询类型
  - 导航查询：语义检索 + 图路径查询
  - 操作查询：向量检索 IntentSequences（过滤到当前 State）
  - 任务查询：优先 CognitivePhrase，fallback 到任务分解
- [ ] 可选：实现 Memory.navigate() 便捷方法（如果常用）

#### Phase 5: Reasoner 重新设计
- [ ] 如果没有接口需要调用了，Reasoner 暂时保留，可以先留着做参考，如果还需要，那就修改他。 plan 接口可以保留做参考
- [ ] 直接在 Memory 内部实现查询逻辑

#### Phase 6: 测试与验证
- [ ] 单元测试：IntentSequence 创建和标记
- [ ] 单元测试：CognitivePhrase execution_plan 构建
- [ ] 集成测试：Memory.query() 三种查询场景
- [ ] 集成测试：Replay CognitivePhrase
- [ ] 性能测试：向量检索性能对比（IntentSequence 独立节点 vs 嵌套）
- [ ] 端到端测试：完整工作流（录制 → 存储 → 查询 → 执行）

### 11.3 Breaking Changes（不考虑向后兼容）

**数据模型变更**：
- ❌ State.intent_sequences 字段删除（IntentSequence 作为独立节点）
- ❌ State.add_intent_sequence() 方法删除
- ❌ WorkflowMemory.add_intent_sequence() 方法删除
- ❌ CognitivePhrase.state_path 和 action_path 删除（只保留 execution_plan）
- ❌ 旧的 IntentSequence 嵌套结构不再支持

**接口变更**：
- ❌ 删除多个独立查询方法（统一为 query()）
- ❌ 旧的返回结构不再兼容

**代码适配要求**：
需要修改所有使用旧接口的地方：

```python
# ❌ 旧代码（需要删除）
self.memory.add_intent_sequence(state_id, sequence)
state.add_intent_sequence(sequence)
for seq in state.intent_sequences:
    ...

# ✅ 新代码（改用 IntentSequenceManager）
self.memory.intent_sequence_manager.create_sequence(sequence)
self.memory.intent_sequence_manager.link_to_state(state_id, sequence.id)
sequences = self.memory.intent_sequence_manager.list_by_state(state_id)
for seq in sequences:
    ...
```

**受影响的文件**：
- `src/cloud_backend/memgraph/ontology/state.py` - 删除字段和方法
- `src/cloud_backend/memgraph/memory/workflow_memory.py` - 删除 add_intent_sequence()
- `src/cloud_backend/memgraph/thinker/workflow_processor.py` - 改用 intent_sequence_manager
- `src/cloud_backend/memgraph/thinker/action_extractor.py` - 改用 list_by_state()
- `src/cloud_backend/memgraph/reasoner/workflow_converter.py` - 改用 list_by_state()
- `tests/test_memory_workflow.py` - 更新所有测试

**迁移策略**：
- ✅ 数据库完全重建（不做迁移脚本）
- ✅ 旧数据清空，从头开始
- ✅ 更简洁的实现，无历史包袱

---

## 12. 参考

- [Memory as Map Design](./memory-as-map-design.md) - 原有设计思路
- [Neo4j Vector Search](https://neo4j.com/docs/cypher-manual/current/indexes-for-vector-search/) - 向量索引文档
