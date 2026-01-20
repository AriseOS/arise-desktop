# Web Recording → Graph → YAML Workflow

**最终设计文档 & 实现方案（Production Version）**

---

## 0. 设计总原则（必须写在文档首页）

> **本系统是一个「可执行 Workflow 编译系统」，而不是一个在线智能体。**

**铁律：**

1. **YAML Workflow 是唯一可执行物**
2. **Agent 只在生成期工作，不参与运行时**
3. **LLM 只在执行失败时介入，且只能修改 YAML**
4. **Recording → Graph Builder 全程无 LLM**
5. **任何非确定性逻辑都必须隔离在 Repair Engine**

---

## 1. 系统整体架构

### 1.1 总体架构图（逻辑）

```
┌───────────────────┐
│   Web Recording   │
└─────────┬─────────┘
          ↓
┌────────────────────────────┐
│ Recording → Graph Builder  │  (无 LLM)
│  - Event Normalization     │
│  - Noise Reduction         │
│  - Phase Segmentation      │
│  - Episode Segmentation    │
│  - State / Action Graph    │
└─────────┬──────────────────┘
          ↓
┌────────────────────────────┐
│ Agent (Workflow Generator) │
│  - Graph → YAML Workflow   │
│  - 只生成，不执行          │
└─────────┬──────────────────┘
          ↓
┌────────────────────────────┐
│ Workflow Executor          │
│  - 严格执行 YAML           │
│  - 确定性                  │
└─────────┬──────────────────┘
          ↓ (仅失败)
┌────────────────────────────┐
│ LLM Repair Engine          │
│  - 生成 YAML Patch         │
│  - 不直接操作 UI           │
└────────────────────────────┘
```

---

## 2. 数据模型定义（全局统一）

### 2.1 Event（规范化事件）

```json
{
  "timestamp": 123456,
  "type": "click | input | scroll | navigation",
  "url": "/order/confirm",
  "page_root": "main | iframe_x | modal_y",
  "target": {
    "tag": "button",
    "role": "button",
    "text": "提交",
    "aria": "submit-order"
  },
  "dom_hash": "hash_xxx"
}
```

**约束：**

* 所有 Recording Adapter 必须产出该结构
* 不允许出现“原始 XPath only”

---

### 2.2 State（Graph Node）

```json
{
  "state_id": "S3",
  "url": "/order/confirm",
  "page_root": "main",
  "dom_signature": {
    "form_count": 1,
    "button_texts": ["提交", "取消"],
    "has_modal": false
  }
}
```

---

### 2.3 Action Edge（Graph Edge）

```json
{
  "edge_id": "E_click_submit",
  "from": "S3",
  "to": "S4",
  "action_type": "click",
  "raw_target": {
    "role": "button",
    "text": "提交"
  }
}
```

> ⚠️ **注意：此处不要求语义，不要求 intent**

---

## 3. Recording → Graph Builder（无 LLM）

### 3.1 模块职责

**目标：**

* 不理解业务
* 不做决策
* 不优化
* 只做结构化与压缩

---

### 3.2 模块组成

#### 3.2.1 Event Normalization

* 输入：各种 Recording 格式
* 输出：统一 Event Schema

**实现：**

* Adapter 模式
* 严格校验字段完整性

---

#### 3.2.2 Noise Reduction

**规则：**

| 噪声类型                   | 处理方式         |
| ---------------------- | ------------ |
| hover × N              | 合并           |
| scroll × N             | 合并           |
| input → delete → input | 只保留最终输入      |
| idle > T               | 标记为 Phase 候选 |

---

#### 3.2.3 Phase Segmentation（宏观）

**切分信号：**

* 强信号（必切）：

  * URL Path 变化
  * page_root 变化
  * reload
* 弱信号（≥2）：

  * idle 超阈值
  * DOM 相似度下降
  * 操作类型突变

**输出：**

```json
{
  "phase_id": "P2",
  "events": [...]
}
```

---

#### 3.2.4 Episode Segmentation（中观）

**规则：**

* click / navigation → Episode 边界
* 连续 input 合并
* 噪声 Episode 丢弃

**Episode Signature（结构化）：**

```json
{
  "event_types": ["input", "input", "click"],
  "target_roles": ["textbox", "textbox", "button"],
  "url": "/login"
}
```

---

#### 3.2.5 Graph 构建

* Phase → 子图
* Episode → 宏路径
* Action → 原子边

**验收标准：**

* 同一 Recording 重跑 → Graph 100% 一致
* 不丢失任何 click / navigation

---

## 4. Agent（Workflow Generator）

### 4.1 Agent 职责（再次强调）

**Agent 只做：**

1. 从 Graph 中选一条稳定路径
2. 将路径翻译为 YAML Workflow
3. 输出确定性执行描述

**Agent 不做：**

* 执行
* 回退
* 修复
* UI 查找

---

### 4.2 Graph → YAML 映射规则

#### State → precondition

#### Edge → step

#### raw_target → target.locate 候选

---

## 5. YAML Workflow DSL（执行核心）

### 5.1 Workflow 示例

```yaml
workflow:
  name: submit_order
  version: v1

targets:
  submit_button:
    locate:
      - by: aria
        value: submit-order
      - by: text
        value: 提交
      - by: text_similar
        value: [确认, 下单]

steps:
  - step_id: click_submit
    action: click
    target: submit_button
    precondition:
      url_contains: /order/confirm
    postcondition:
      any:
        - url_contains: /order/success
        - text_visible: 提交成功
```

---

## 6. Workflow Executor（严格确定性）

### 6.1 执行流程

```
校验 precondition
   ↓
按顺序尝试 locate
   ↓
执行 action
   ↓
校验 postcondition
```

---

### 6.2 失败分类（必须结构化）

| Error Code           | 含义            |
| -------------------- | ------------- |
| TARGET_NOT_FOUND     | 所有 locator 失败 |
| NOT_INTERACTABLE     | 元素不可操作        |
| TIMEOUT              | 无状态变化         |
| POSTCONDITION_FAILED | 校验失败          |

---

## 7. LLM Repair Engine（唯一允许 LLM 的地方）

### 7.1 触发条件

* Executor 抛出结构化错误
* 且 retry 已耗尽

---

### 7.2 LLM 输入（强限制）

```json
{
  "step_id": "click_submit",
  "error": "TARGET_NOT_FOUND",
  "visible_buttons": ["确认订单", "取消"],
  "original_target": "提交"
}
```

---

### 7.3 LLM 输出（只能是 Patch）

```yaml
patch:
  target: submit_button
  add_locate:
    - by: text
      value: 确认订单
```

---

### 7.4 Patch 生效规则

* Patch 必须写回 YAML
* 重新执行成功后才能固化
* 失败则丢弃 Patch

---

## 8. 系统验收指标（非常重要）

| 模块                | 指标           |
| ----------------- | ------------ |
| Graph Builder     | 100% 可复现     |
| Workflow Executor | 0 LLM 依赖     |
| Repair Engine     | Patch 可审计    |
| 整体                | 正常路径 0 次 LLM |

---

# 9. TODOLIST（工程拆解）

## 9.1 基础设施

* [ ] 定义 Event / State / Edge Schema
* [ ] Recording Adapter

---

## 9.2 Graph Builder（核心）

* [ ] Event Normalization
* [ ] Noise Reduction 模块
* [ ] Phase Segmentation 算法
* [ ] Episode Segmentation 算法
* [ ] State / Edge Graph 构建
* [ ] Graph 重放一致性测试

---

## 9.3 Agent（生成期）

* [ ] Graph 遍历策略
* [ ] Graph → YAML 映射
* [ ] YAML Schema 校验器

---

## 9.4 Workflow Executor

* [ ] YAML Parser
* [ ] Locator 执行器
* [ ] Pre/Postcondition 校验
* [ ] 错误分类与报告

---

## 9.5 LLM Repair Engine

* [ ] Failure Report Schema
* [ ] Repair Prompt & Contract
* [ ] YAML Patch 应用器
* [ ] Patch 成功验证机制

---

## 9.6 系统级

* [ ] 执行日志 & 可视化
* [ ] Workflow 版本管理
* [ ] Patch 回滚机制
* [ ] 成本 / LLM 调用统计

---

## 10. 最终一句话总结（给团队 & 评审）

> **这是一个“将人类操作编译为可执行知识”的系统。
> 不是自动化脚本，也不是自由智能体。
> 确定性优先，智能只用于修复。**

---

如果你愿意，下一步我可以直接帮你做 **其中任意一个模块的代码级设计**，例如：

* Phase / Episode 的参考实现
* YAML DSL 的 JSON Schema
* Executor 的状态机
* Repair Engine 的 Prompt Contract

你想从 **哪一块直接落代码**？
