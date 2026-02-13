# PlannerAgent 测试结果 (2026-02-11)

## 改动摘要

1. **Prompt 重写**：任务目标从"找最佳参考"→"用 Memory 拼出覆盖率最高的执行计划"；4 步流程（Recall → Judge → Graph Explore → Output）
2. **工具精简**：5 个工具 → 3 个（`recall_phrases`, `search_states`, `explore_graph`）
3. **explore_graph**：新工具，代码层完成 embedding 搜终点 + BFS 找路径，一次调用返回完整路径
4. **max_iterations**：15 → 8

---

## 测试结果

### 场景 1: Amazon 泛化 — "收集 Amazon 上卖的最好的 10 款眼镜"

| 指标 | 结果 |
|------|------|
| **Memory Level** | L1 |
| **Coverage** | 1 item（Amazon 搜索+排序流程 → 泛化到眼镜） |
| **Preferences** | 3（Best Sellers 排序、提取价格评分、CSV 导出） |
| **Subtasks** | 4（3 browser + 1 document），3/4 有 workflow_guide |
| **PlannerAgent 耗时** | 42.0s |
| **Decompose 耗时** | 3.1s |
| **总耗时** | 45.1s |
| **LLM 调用次数** | 6（4 tool calls） |
| **工具链** | recall_phrases → search_states → explore_graph → search_states |
| **Token 用量** | in=56,317 out=494 |
| **符合预期？** | **是** — 正确泛化 Amazon 搜索流程到眼镜品类 |

**备注**: PlannerAgent 做了 explore_graph 尝试找到更多路径（Best Sellers 页面），属于合理探索。

---

### 场景 2: ProductHunt 部分匹配 — "去 ProductHunt 看看本周有什么好的 AI 产品"

| 指标 | 结果 |
|------|------|
| **Memory Level** | L1 |
| **Coverage** | 1 item（PH 周排行导航覆盖，AI 过滤标为 uncovered） |
| **Preferences** | 2（周排行、滚动浏览） |
| **Subtasks** | 5（4 browser + 1 document），4/5 有 workflow_guide |
| **PlannerAgent 耗时** | **13.2s** |
| **Decompose 耗时** | 3.1s |
| **总耗时** | **16.3s** |
| **LLM 调用次数** | 4（2 tool calls） |
| **工具链** | explore_graph → search_states |
| **Token 用量** | in=25,847 out=407 |
| **符合预期？** | **是** — 导航部分 covered，AI 过滤 uncovered，快速结束 |

**关键改进**: 改动前 200.5s / 15 轮工具调用 / L3 → 改动后 **13.2s / 2 轮工具调用 / L1**。

---

### 场景 3: 混合覆盖 — "去 ProductHunt 看看本周排行榜 top 10，整理成 Excel 发邮件给老板"

| 指标 | 结果 |
|------|------|
| **Memory Level** | L1（browser），L3（document） |
| **Coverage** | 1 item（PH 周排行覆盖） |
| **Preferences** | 2 |
| **Subtasks** | 4（2 browser + 2 document），2/4 有 workflow_guide |
| **PlannerAgent 耗时** | 41.4s |
| **Decompose 耗时** | 6.9s |
| **总耗时** | 48.3s |
| **LLM 调用次数** | 9（6 tool calls） |
| **工具链** | search_states → search_states → explore_graph → search_states → search_states → search_states |
| **Token 用量** | in=76,978 out=579 |
| **符合预期？** | **部分** — PH 覆盖正确，但 PlannerAgent 花了太多轮搜索 Excel/Email，这些本不在 Memory 中 |

**备注**: PlannerAgent 做了 6 轮工具调用尝试搜索 Excel/Email 相关页面。根据 prompt 逻辑应该更快放弃（recall_phrases 没有返回 Excel/Email 相关 phrase 就应该直接标 uncovered）。但注意到这个场景 LLM 第一轮没调 recall_phrases 而是直接 search_states — 说明 prompt 的 "Always start with recall_phrases" 指令没被严格遵守。

---

### 场景 4: 完全无关 — "帮我订一张下周三从北京到上海的机票"

| 指标 | 结果 |
|------|------|
| **Memory Level** | L3 |
| **Coverage** | 0 items |
| **Preferences** | 0 |
| **Subtasks** | 4（3 browser + 1 document），0/4 有 workflow_guide |
| **PlannerAgent 耗时** | **88.3s** |
| **Decompose 耗时** | 4.3s |
| **总耗时** | **92.6s** |
| **LLM 调用次数** | 9（7 tool calls） |
| **工具链** | recall_phrases → search_states ×6（携程/去哪儿/飞猪/airline/trip/北京上海/预订） |
| **Token 用量** | in=85,840 out=442 |
| **符合预期？** | **结果正确但太慢** — 正确返回 L3 / 0 coverage，但做了 7 轮工具调用才放弃 |

**问题**: Memory 里完全没有机票/航班相关内容，recall_phrases 第一轮就应该发现所有结果都不相关，直接输出空 coverage。但 LLM 又做了 6 轮 search_states 换各种关键词搜索（中文、英文、具体平台名），白白消耗 88 秒。**这是 "Know when to stop" 原则没被遵守的典型例子。**

---

### 场景 5: 模糊意图 — "帮我看看最近有什么好产品"

| 指标 | 结果 |
|------|------|
| **Memory Level** | L1 |
| **Coverage** | 2 items（PH 周排行 + Amazon 搜索） |
| **Preferences** | 3 |
| **Subtasks** | 5（4 browser + 1 document），4/5 有 workflow_guide |
| **PlannerAgent 耗时** | **11.5s** |
| **Decompose 耗时** | 4.9s |
| **总耗时** | **16.4s** |
| **LLM 调用次数** | 3（1 tool call） |
| **工具链** | search_states |
| **Token 用量** | in=14,738 out=375 |
| **符合预期？** | **是** — 模糊意图正确推断为 PH 好产品，快速完成 |

---

## 时间对比（改动前 vs 改动后）

| 场景 | 改动前 PlannerAgent | 改动后 PlannerAgent | 改动前工具调用 | 改动后工具调用 |
|------|--------------------|--------------------|---------------|---------------|
| 1. Amazon 泛化 | 40.0s | 42.0s | 3 | 4 |
| **2. PH 部分匹配** | **200.5s** | **13.2s (15x faster)** | **14** | **2** |
| 3. 混合覆盖 | 82.8s | 41.4s | 3 | 6 |
| 4. 完全无关 | 27.5s | 88.3s | 7 | 7 |
| 5. 模糊意图 | 25.9s | 11.5s | 3 | 1 |

## 效果对比（改动前 vs 改动后）

| 场景 | 改动前 Coverage | 改动后 Coverage | 改动前 Memory Level | 改动后 Memory Level |
|------|----------------|----------------|--------------------|--------------------|
| 1. Amazon 泛化 | 1 item | 1 item | L1 | L1 |
| **2. PH 部分匹配** | **0 items** | **1 item** | **L3** | **L1** |
| 3. 混合覆盖 | 1 item | 1 item | L1 | L1 |
| 4. 完全无关 | 0 items | 0 items | L3 | L3 |
| 5. 模糊意图 | 1 item | 2 items | L1 | L1 |

## 待优化

1. **场景 4（完全无关）耗时退化**：从 27.5s → 88.3s。LLM 做了 6 轮 search_states 换关键词搜索机票相关内容，但 Memory 里根本没有。需要加强 "Know when to stop" — recall_phrases 返回全不相关时，不应再做 search_states。
2. **场景 3 没有先调 recall_phrases**：跳过了 Step 1 直接 search_states，说明 prompt 的 "Always start with recall_phrases" 指令执行不稳定。
3. **场景 3 和 4 的过度搜索**：对于 Memory 中不存在的功能（Excel、Email、机票），LLM 仍尝试多轮搜索。考虑在 prompt 中增加 few-shot 示例，展示 "全不相关 → 立即输出" 的模式。
