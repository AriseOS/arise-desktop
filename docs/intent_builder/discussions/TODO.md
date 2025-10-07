# Intent Builder - 待讨论事项清单

**更新日期**: 2025-10-07

---

## 已完成 ✅

### 系统设计
- [x] 系统整体设计（design_overview.md）
- [x] MVP 范围界定
- [x] Intent 数据结构（4个域：id, name, description, operations）
- [x] Intent 粒度定义（粗粒度，基于页面状态变化）
- [x] 循环推断策略（从用户描述关键词）
- [x] 意图版本管理（MVP 不考虑）
- [x] 存储方案（MVP 使用内存）

### MetaFlow 设计
- [x] MetaFlow 格式设计（metaflow_design.md）
- [x] MetaFlow 职责边界（执行顺序 + 控制流，不包含数据流）
- [x] 基本数据结构（图结构，YAML 格式）
- [x] 数据流表示方式（不包含，由 LLM 推断）
- [x] 循环表示方式（特殊节点 + 自然语言 description）
- [x] 变量命名策略（生成 workflow 时由 LLM 决定）
- [x] MetaFlow → YAML 映射关系（由 LLM 灵活决定）
- [x] 可读性要求（人类可读优先）
- [x] 格式选择（YAML + Pydantic）
- [x] 扩展性设计（只加必要功能，保持可扩展）
- [x] Operations 格式（从意图记忆中来，包含详细 DOM 信息）
- [x] 节点 ID 来源（从意图记忆系统中获取）

### WorkflowGenerator 设计
- [x] MetaFlow → Workflow 生成策略讨论（discussions/03）
- [x] WorkflowGenerator 设计文档（workflow_generator_design.md）
- [x] LLM 决策点明确（Agent 类型、数据流、循环、Step 拆分）
- [x] Operations 格式确认（已足够详细）
- [x] Step 拆分原则（以 Step Agent 为最小单元）
- [x] Prompt 设计方案（精简规范 + 1 个示例 + 重试机制）

---

## 待讨论 🔴

### P0 - 核心组件设计

#### 1. IntentExtractor（意图提取器）
- [ ] 从 user_operations.json 切分意图的具体规则
- [ ] 如何识别页面状态变化（URL 变化 + DOM 变化？）
- [ ] 如何使用 LLM 生成 intent 的 name, description, operations
- [ ] 粒度控制：什么时候应该合并操作，什么时候应该拆分

#### 2. IntentMemoryGraph（意图记忆图）
- [ ] 图的存储结构（节点 + 边）
- [ ] 如何记录意图之间的连接关系
- [ ] 如何记录和更新频率信息
- [ ] MVP 使用什么实现（Python 字典 vs NetworkX）

#### 3. IntentRetriever（意图检索器）
- [ ] 根据 user_description 检索意图的策略
- [ ] 标签匹配的具体实现（关键词提取？）
- [ ] 如何利用频率信息排序
- [ ] 如何确定检索结果的数量和相关性

#### 4. MetaFlowGenerator（MetaFlow 生成器）
- [ ] 如何将检索到的意图列表组装成 MetaFlow
- [ ] 如何从 user_description 推断循环（关键词列表是什么？）
- [ ] 如何确定循环的范围（哪些意图在循环内？）
- [ ] 如何生成节点 ID

#### 5. WorkflowGenerator（Workflow 生成器）
- [ ] **LLM Prompt 设计**（见下一节详细讨论）
- [ ] 如何确保生成的 YAML 格式正确
- [ ] 错误处理和重试策略
- [ ] 性能优化（缓存？）

---

## 待深入讨论 🟡

### MetaFlow → Workflow 生成细节

需要明确 LLM 在转换过程中的决策点：

1. **Operations → Agent Type 映射**
   - 哪些 operations 应该用 tool_agent？
   - 哪些应该用 scraper_agent？
   - 决策依据是什么？

2. **数据流推断**
   - 如何识别意图之间需要传递的数据？
   - 变量命名规则（page_state, product_list 等）
   - 如何处理多个输出的情况？

3. **循环结构生成**
   - 从自然语言 description 如何生成 foreach 结构？
   - 如何推断 source（循环来源）？
   - 如何推断 item_var（循环变量名）？

4. **Step 拆分策略**
   - 一个意图的多个 operations 如何拆分成多个 step？
   - 什么时候应该合并，什么时候应该拆分？

5. **Prompt 设计**
   - 需要提供什么样的上下文？
   - 需要什么样的约束和示例？
   - 如何确保输出格式正确？

---

## 下一步计划

1. 讨论 MetaFlow → Workflow 生成的 LLM 决策点
2. 确定各个组件的设计方案
3. 编写各组件的详细设计文档
4. 制定实施计划
