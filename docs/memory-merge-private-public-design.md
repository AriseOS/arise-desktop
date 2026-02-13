# Memory Merge: Private + Public 并行查询

## 概述

所有 Memory 查询层同时查询 Private 和 Public Memory，通过 LLM 选择或直接合并产生最优结果。

**之前**: Private-first fallback（先查 Private，失败才查 Public）
**之后**: 并行查询 + 智能融合（两边都查，LLM 选或合并）

## 融合策略总览

| 查询层 | 融合方式 | 是否需要 LLM | source 值 |
|--------|---------|-------------|----------|
| L1 CognitivePhrase | 合并 phrases 列表，单次 LLM 调用选最佳 | 是（1次，比之前最差2次更少） | `private` / `public` |
| L2 Path Retrieval | 两边并行跑 embedding+BFS，LLM 选一条路径 | 是（新增1次 select） | `private` / `public` |
| Navigation | 两边各跑 shortest path，LLM 选一条 | 是（新增0-1次 select） | `private` / `public` |
| Action | 合并去重 IntentSequences | 否 | `merged` |
| State-by-URL | State 优先 private，Sequences 合并去重 | 否 | `private` / `public` |

## 架构核心：Reasoner 双 Memory

```python
# reasoner.py
class Reasoner:
    def __init__(self, memory: Memory, public_memory: Optional[Memory] = None, ...):
        self.memory = memory                # private (必须)
        self.public_memory = public_memory  # public (可选，None 时行为不变)
```

`_active_memories()` 返回 `[self.memory] + ([self.public_memory] if exists)`，private 始终在前，保证去重时 private 优先。

## 各层详细实现

### L1 CognitivePhrase（合并 + LLM 选）

**文件**: `reasoner.py: _l1_phrase_match()`, `cognitive_phrase_checker.py: check_merged()`

**流程**:
1. `private_phrases = self.memory.phrase_manager.list_phrases()`
2. `public_phrases = self.public_memory.phrase_manager.list_phrases()`
3. 每个 phrase 打上 `[SOURCE: private]` / `[SOURCE: public]` 标签
4. 合并列表送入 LLM（**单次调用**），LLM 输出包含 `source` 字段
5. 从正确的 Memory 中解析 states/actions

**容量保护**: phrases 总数 > 50 时，先按文本相关性 pre-filter 各取 top-25。

**Prompt 关键指令**:
- private = 用户自己录制的工作流，更贴合个人习惯
- public = 社区共享工作流，可能覆盖用户没做过的任务
- 同等匹配时优先 private

### L2 Path Retrieval（并行查询 + LLM 选）

**文件**: `reasoner.py: _l2_path_retrieval()`, `_embedding_search_and_bfs()`, `_select_best_path()`

**流程**:
1. `_decompose_query_for_path(target)` — 单次 LLM 调用，两边共用
2. `asyncio.gather` 并行执行:
   - `_embedding_search_and_bfs(decomposed, self.memory)` — private
   - `_embedding_search_and_bfs(decomposed, self.public_memory)` — public
3. `_select_best_path(target, private_result, public_result)` — LLM 选路径

**LLM 选择标准**（按重要性排序）:
1. Completeness: 路径是否覆盖任务所需的所有关键页面/步骤
2. Relevance: 路径中的页面是否与任务直接相关
3. Efficiency: 无不必要的绕路
4. 同等时优先 Path A (private)

**Fallback**: LLM 调用失败时，取 embedding score 更高的一方。

### Navigation（双边查询 + LLM 选）

**文件**: `reasoner.py: _query_navigation()`, `_find_shortest_path_in_memory()`

**流程**:
1. 在 private memory 中: resolve start/end state → find_shortest_path
2. 在 public memory 中: resolve start/end state → find_shortest_path
3. 只有一边有结果 → 直接用
4. 两边都有 → 复用 `_select_best_path()` LLM 选择

`_resolve_state_id()` 已参数化，接受 `memory: Optional[Memory]` 参数。

### Action Query（合并去重）

**文件**: `reasoner.py: _query_action()`, `_get_page_capabilities()`, `_deduplicate_sequences()`

**流程**:
1. 遍历 `_active_memories()` (private 在前)
2. 每个 memory 中: resolve state → 搜索 IntentSequences
3. `_deduplicate_sequences()` 按 description 去重，保留首次出现（= private 优先）

**无 LLM 调用**，纯合并。

### State-by-URL（合并去重）

**文件**: `main.py: get_state_by_url()`

**流程**:
1. 先查 private state, 没有则查 public state
2. 如果 state 来自 private 且 public 也有同 URL 的 state → 合并两边的 IntentSequences
3. Sequences 按 description 去重

**无 LLM 调用**，纯合并。

## API 端点变更

### POST /api/v1/memory/phrase/query

响应新增 `source` 字段:
```json
{"success": true, "phrase": {...}, "reasoning": "...", "source": "private"}
```

### POST /api/v1/memory/query

响应新增 `source` 字段（从 `metadata.source` 提取到顶层）:
```json
{"success": true, "query_type": "task", "source": "private", "states": [...], ...}
```

### POST /api/v1/memory/state

响应新增 `source` 字段:
```json
{"success": true, "state": {...}, "intent_sequences": [...], "source": "private"}
```

## 数据模型变更

`QueryResult` 新增 `source` 字段:
```python
source: Optional[str] = Field(default=None, description="Memory source: 'private', 'public', or 'merged'")
```

## 成本分析

| 查询类型 | 之前 LLM 调用数 | 之后 LLM 调用数 | 额外 DB 操作 |
|---------|---------------|-------------|------------|
| L1 Phrase | 1-2 次（fallback 最差 2 次） | **1 次**（减少） | +1 次 list_phrases |
| L2 Path | 1 次 decompose | 1 次 decompose + **1 次 select** | +1 次 embedding+BFS（并行） |
| Navigation | 0 次 | **0-1 次 select** | +1 次 resolve+shortest_path |
| Action | 0 次 | 0 次 | +1 次 URL lookup+sequences |
| State-by-URL | 0 次 | 0 次 | +1 次 URL lookup |

## 修改文件清单

| 文件 | 改动 |
|------|-----|
| `src/common/memory/ontology/query_result.py` | 新增 `source` 字段 |
| `src/common/memory/reasoner/reasoner.py` | 双 Memory 架构、`_l1_phrase_match`、`_l2_path_retrieval`、`_select_best_path`、`_embedding_search_and_bfs`、`_query_action`、`_get_page_capabilities`、`_active_memories`、`_deduplicate_sequences`、参数化 `_find_navigation_path`/`_resolve_state_id` |
| `src/common/memory/reasoner/cognitive_phrase_checker.py` | `check_merged()` 方法、`_score_phrases()` |
| `src/common/memory/reasoner/prompts/cognitive_phrase_match_prompt.py` | source 标签、source 输出字段、偏好指引 |
| `src/cloud_backend/main.py` | `_get_reasoner_for_user` 注入 public_memory、`phrase/query` 合并查询、`memory/query` 移除 fallback、`memory/state` 合并 sequences |
| `src/common/memory/CONTEXT.md` | 文档更新 |
