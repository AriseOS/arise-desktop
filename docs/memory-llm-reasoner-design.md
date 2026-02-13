# Memory Query Redesign: LLM-as-Reasoner

> 让 LLM 深度参与路径规划，取代纯 Embedding + BFS 的机械检索。

## 1. 问题诊断

### 1.1 现象

执行 `debug_memory_llm_context.py` 查询 "收集 Product Hunt 周榜产品信息" 时，L2 返回了 **2 个 state 的 path**：

```
Step 1: 产品发布首页 (producthunt.com/)
  -> 点击 "Launches"
Step 2: 每日排行榜 (producthunt.com/leaderboard/daily/...)
```

问题：
- 只有 2 个 state，路径不完整（缺少后续的产品详情页等）
- 选错了"日榜"而不是"周榜"
- Agent 拿到这个 guide 后效果不佳

### 1.2 根因分析

当前 L2 路径检索流程（`Reasoner._find_navigation_path`）：

```
用户任务
  ↓ (1) LLM 查询分解
生成 target_query + key_queries
  ↓ (2) Embedding 搜索
找到候选 target states
  ↓ (3) BFS 反向遍历 (max_depth=3)
从 target state 往回走，组装路径
  ↓ (4) 向量分数打分
path_score = has_target * target_score + key_coverage * 0.3
  ↓
输出最佳路径
```

**每一步的信息损失**：

| 步骤 | 做了什么 | 信息损失 |
|------|---------|---------|
| (1) 查询分解 | LLM 生成检索语句 | 唯一用到 LLM 的地方，但输出只是搜索关键词，无法利用图结构 |
| (2) Embedding 搜索 | 向量相似度匹配 states | "周榜" vs "日榜" 向量接近，无法区分；阈值 0.3 可能放入噪声或漏掉正确结果 |
| (3) BFS 反向遍历 | 从 target 往回走 | 盲目遍历，不理解任务语义；depth=3 限制路径长度 |
| (4) 打分 | 向量分数加权 | 完全基于向量距离，没有语义验证 |

**核心矛盾**：用 Embedding（模糊的连续向量空间）做一个需要精确推理的事情（路径选择与组装）。模型只在查询分解环节参与，最关键的路径选择完全靠机械搜索。

### 1.3 Embedding 的能力边界

**擅长**：
- 相似性检索：从大量数据中快速缩小候选范围
- 粗筛：找到"大概相关"的内容

**不擅长**：
- 精确区分："PH 周榜" vs "PH 日榜" 的 embedding 非常接近，但语义完全不同
- 多跳推理：无法规划 A→B→C 的路径，只能找到孤立的终点
- 意图理解：无法判断任务需要哪些步骤、走哪条分支

## 2. 设计目标

1. **Embedding 降级为粗筛**：放宽阈值，宁多勿少，负责召回候选集
2. **LLM 升级为路径规划者**：看到候选 states + 导航关系后，做出精确的路径选择
3. **随模型进步自动提升**：更强的 LLM = 更好的路径规划，不需要改代码
4. **成本可控**：候选集通常不大（10-20 states），只增加一次 LLM 调用

## 3. 新流程设计

### 3.1 整体流程

```
用户任务
  ↓
L1: CognitivePhrase 精确匹配 (不变)
  ↓ (miss)
L2: LLM-as-Reasoner 路径规划 (核心改动)
  ├── Step 1: Embedding 宽泛检索候选 states
  ├── Step 2: 提取候选 states 之间的 actions (子图)
  ├── Step 3: LLM 路径规划 (新增)
  └── Step 4: 输出结构化路径
  ↓ (miss)
L3: 无记忆，Agent 自由探索 (不变)
```

### 3.2 详细步骤

#### Step 1: Embedding 宽泛检索

目标：召回所有可能相关的 states，宁多勿少。

```python
# 降低阈值（从 0.3 降到 0.15-0.2）
# 增加 top_k（从 10 增到 20）
candidate_states = embedding_search(
    query=task_description,
    top_k=20,
    min_score=0.15,
)
```

变化：
- Embedding 不再负责精确匹配，只负责"大概相关"
- 多召回一些候选，交给 LLM 筛选
- 即使"日榜"和"周榜"都被召回，后续 LLM 能区分

#### Step 2: 提取子图

从图数据库中提取候选 states 之间的 actions，构建一个小型子图。

```python
# 获取候选 state IDs
candidate_ids = {s.id for s in candidate_states}

# 提取这些 states 之间的所有 actions
subgraph_actions = []
for state in candidate_states:
    outgoing = memory.get_outgoing_actions(state.id)
    for action in outgoing:
        if action.target in candidate_ids:
            subgraph_actions.append(action)

# 补充：沿 actions 引入的 states（可能不在候选集中但在路径上）
for action in subgraph_actions:
    if action.target not in candidate_ids:
        bridge_state = memory.get_state(action.target)
        if bridge_state:
            candidate_states.append(bridge_state)
            candidate_ids.add(bridge_state.id)
```

#### Step 3: LLM 路径规划（核心改动）

把子图以结构化文本交给 LLM，让它规划最佳路径。

**输入给 LLM 的上下文**：

```
## 任务
收集 Product Hunt 周榜产品信息

## 记忆中的相关页面
1. [s1] Product Hunt 首页
   URL: https://www.producthunt.com/
2. [s2] PH 每日排行榜
   URL: https://www.producthunt.com/leaderboard/daily/...
3. [s3] PH 每周排行榜
   URL: https://www.producthunt.com/leaderboard/weekly/...
4. [s4] PH 产品详情页
   URL: https://www.producthunt.com/posts/...
5. [s5] PH 产品团队页面
   URL: https://www.producthunt.com/posts/.../team

## 已知导航关系
- s1 -> s2: 点击 "Launches" (text="Launches", role=link)
- s1 -> s3: 点击 "Weekly" (text="Weekly", role=link)
- s2 -> s4: 点击产品链接
- s3 -> s4: 点击产品链接
- s4 -> s5: 点击 "Team" (text="Team", role=tab)
```

**LLM 输出**：

```json
{
  "can_plan": true,
  "path": ["s1", "s3", "s4"],
  "reasoning": "任务要求周榜，应走 s3（每周排行榜）而非 s2（每日排行榜）。从首页点击 Weekly 进入周榜，再点击产品进入详情页收集信息。"
}
```

**关键优势**：
- LLM 能区分"周榜"和"日榜"（embedding 做不到）
- LLM 能判断路径是否完整
- LLM 能理解任务需要哪些步骤
- `can_plan: false` 时优雅降级到 L3

#### Step 4: 输出结构化路径

根据 LLM 规划的 path，组装完整的 states + actions：

```python
planned_states = [state_map[sid] for sid in llm_path]
planned_actions = []
for i in range(len(llm_path) - 1):
    action = memory.get_action(llm_path[i], llm_path[i+1])
    if action:
        planned_actions.append(action)
```

### 3.3 对比

| | 现在（Embedding + BFS） | 改进后（LLM-as-Reasoner） |
|---|---|---|
| Embedding 的角色 | 精确定位 + 打分 | 粗筛候选集 |
| LLM 的角色 | 只做查询分解（生成搜索关键词） | 看到子图后做路径规划 |
| BFS 的角色 | 盲目遍历 | 移除，改为子图提取 |
| 路径质量 | 取决于向量相似度 | 取决于 LLM 推理能力 |
| "周榜 vs 日榜" | 无法区分 | LLM 直接读文本区分 |
| 路径长度 | 受 max_depth 限制 | 不受限，LLM 自由规划 |
| 成本 | 1 次 LLM（查询分解）+ N 次 embedding | 1 次 LLM（路径规划）+ 1 次 embedding |
| 可扩展性 | 模型进步无帮助 | 模型越强效果越好 |

## 4. Prompt 设计

### 4.1 路径规划 Prompt

```
你是一个导航路径规划器。用户给出了一个任务，以下是我记忆中相关的网页和它们之间的导航关系。

请根据任务目标，从这些页面中选择最佳导航路径。

## 规则
1. 路径必须是连通的：每相邻两个页面之间必须存在"已知导航关系"
2. 路径应从起点页面开始（通常是某个网站的首页）
3. 路径应到达能完成任务的终点页面
4. 只选择必要的页面，不要包含无关页面
5. 如果记忆中的页面不足以完成任务，设置 can_plan 为 false

## 任务
{task}

## 记忆中的相关页面
{states_text}

## 已知导航关系
{actions_text}

请返回 JSON：
{
  "can_plan": true/false,
  "path": ["state_id_1", "state_id_2", ...],
  "reasoning": "选择理由"
}
```

### 4.2 子图规模控制

为避免 prompt 过长，需要控制候选集大小：

- **States 上限**：20 个（实际场景中同一 domain 的 states 通常不超过 10-15 个）
- **Actions 上限**：50 条
- **超限策略**：按 embedding score 排序截断

### 4.3 输出解析

```python
result = await llm_provider.generate_json_response(
    system_prompt=PATH_PLANNING_SYSTEM_PROMPT,
    user_prompt=formatted_subgraph,
)

if result.get("can_plan") and result.get("path"):
    # 成功规划 -> L2 结果
    return build_query_result(result["path"])
else:
    # 规划失败 -> 降级到 L3
    return QueryResult(success=False)
```

## 5. 代码变更范围

### 5.1 主要修改

| 文件 | 变更 |
|------|------|
| `src/common/memory/reasoner/reasoner.py` | 重写 `_find_navigation_path()` → `_plan_path_with_llm()` |
| `src/common/memory/reasoner/reasoner.py` | 移除 `_bfs_reverse_paths()` |
| `src/common/memory/reasoner/reasoner.py` | 移除 `_decompose_query_for_path()` |
| `src/common/memory/reasoner/prompts/` | 新增 `path_planning_prompt.py` |

### 5.2 不变的部分

| 模块 | 原因 |
|------|------|
| L1 CognitivePhrase 匹配 | 已用 LLM 做判断，效果好 |
| L3 无记忆降级 | 不涉及路径规划 |
| `format_task_result()` | 输出格式不变，downstream 无感知 |
| `_query_action()` (页面级查询) | 独立逻辑，不受影响 |
| `AMITaskPlanner` / `AMITaskExecutor` | 消费 QueryResult 的格式不变 |

### 5.3 需要新增的图查询方法

```python
# StateManager 新增
def get_outgoing_actions(self, state_id: str) -> List[Action]:
    """获取某个 state 的所有出边 actions"""

# 或复用已有的
state_manager.get_connected_actions(state_id, direction="outgoing")
```

## 6. 风险与缓解

| 风险 | 缓解 |
|------|------|
| LLM 调用增加延迟 | L2 本身已有 LLM 调用（查询分解），新方案替换而非叠加，净增约 1 次调用 |
| LLM 幻觉（规划不存在的路径） | 输出验证：检查 path 中的 state_id 是否存在、相邻 states 间是否有 action |
| 候选集过大导致 prompt 过长 | 限制 states ≤ 20，每个 state 只保留 id + description + URL |
| 候选集过小导致漏掉关键 state | 降低 embedding 阈值 + 沿 actions 扩展一跳邻居 |

## 7. 验证方法

使用现有 `scripts/debug_memory_llm_context.py` 对比改进前后效果：

```python
# 改进前
Task: 收集 Product Hunt 周榜产品信息
Result: 2 states (首页 → 日榜) ❌

# 改进后（预期）
Task: 收集 Product Hunt 周榜产品信息
Result: 3 states (首页 → 周榜 → 产品详情) ✅
Reasoning: "任务要求周榜，走 Weekly 路径"
```
