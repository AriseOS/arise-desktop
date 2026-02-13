# Memory Service 平台策略

## 核心定位

**Memory Service 是所有 Agent 的记忆基础设施，AMI 是第一个标杆客户。**

```
AMI (开源)          ──→  Memory Service (闭源 SaaS)
OpenClaw            ──→  Memory Service
Browser-use         ──→  Memory Service
Playwright Agent    ──→  Memory Service
任何 Agent          ──→  Memory Service
```

## 三层架构

| 层 | 开源 | 壁垒 | 商业模式 |
|----|------|------|---------|
| **AMI**（Agent 产品） | 开源 | 无（样板工程） | 不赚钱，做分发 |
| **Memory**（智能服务） | 闭源 SaaS | 算法 + 数据 + 网络效应 | API 调用收费 |
| **Database**（存储引擎） | 未来开源 | 生态标准 | 未来独立产品 |

### AMI = 样板

- 开源完整的 Agent 系统：Desktop App + Agent 框架 + 任务编排
- 目的不是卖 AMI，是让所有人看到：接了 Memory Service 的 Agent 能做什么
- 任何人可以 fork、修改、接自己的 Memory（但体验会差很多）
- 降低 Agent 开发者的认知门槛："照着 AMI 抄就行"

### Memory = 商业化引擎

- 闭源：算法、数据、服务全部不公开
- 统一 API，任何 Agent 都能接入
- 壁垒三层：
  1. **算法**：Reasoner 多层查询、LearnerAgent 自动学习、PlannerAgent 规划策略
  2. **数据**：Public Memory 积累的 CognitivePhrase，越用越多
  3. **网络效应**：用户越多 → 数据越好 → 规划越准 → 用户越多

### Database = 未来

- 当前：graphstore 抽象层（SurrealDB/Neo4j/NetworkX）
- 未来：专为浏览器操作知识设计的图数据库，独立产品
- 开源建标准，类似 SQLite 之于移动端

## 飞轮

```
AMI 开源 → 更多 Agent 开发者看到 Memory 的价值
  → 更多 Agent 接入 Memory Service
    → 更多执行数据流入 → Learn API 自动生成 CognitivePhrase
      → Public Memory 越来越丰富
        → Plan API 返回越来越准的 workflow_guide
          → 接入 Memory 的 Agent 体验越来越好
            → 更多 Agent 接入（口碑传播）
```

## Memory Service API

面向所有 Agent 的统一接口，Agent 不需要知道背后的数据结构：

| API | 作用 | 调用时机 |
|-----|------|---------|
| `POST /plan` | "我要做这个任务，有没有经验？" | 任务开始前 |
| `POST /learn` | "我做完了，帮我记住" | 任务完成后 |
| `POST /query` | "这个页面上怎么操作？" | 执行过程中 |
| `POST /add` | "这是一段操作录制" | 录制/执行时 |

### 接入方式

不同 Agent 框架用不同方式接入：

| Agent 框架 | 接入方式 | 说明 |
|-----------|---------|------|
| **AMI** | 原生集成 | 开源代码直接调用，标杆实现 |
| **OpenClaw** | npm Plugin | before_agent_start + agent_end hook |
| **Browser-use** | Python SDK | pip install，提供装饰器 |
| **其他** | REST API | 直接 HTTP 调用 |

## AMI 开放接口：MemoryProvider

AMI 开源代码中定义一个抽象接口，允许对接任何 Memory 后端：

```python
class MemoryProvider:
    async def plan(task, context) -> WorkflowGuide
    async def learn(execution_data) -> LearnResult
    async def query(question, url) -> QueryResult
    async def add(operations) -> None
```

我们提供**唯一的官方实现**：连接 2AMI Memory Service。任何人可以自己实现这个接口，对接其他后端。

### 为什么不怕替换

1. **接口简单，实现难**：四个方法签名很简单，但背后是 Reasoner 多层查询、LearnerAgent 自动学习、PlannerAgent 规划策略、整个 ontology 体系。自己实现一个能用的版本，工作量巨大
2. **实现了也没数据**：自建 Memory 里是空的。我们的 Public Memory 有大量 CognitivePhrase，接入即可用
3. **网络效应锁定**：自建是孤岛，接我们的服务能共享全社区知识

类比：Android 允许不装 Google Play Services，但 99% 的用户还是会装。

预期分布：
- 90% 用户 → 用我们的 Memory Service（免费、好用、有数据）
- 8% 用户 → 试着自建，发现太难，回来用我们的
- 2% 用户 → 大公司自建（隐私要求）→ 量太小，无所谓

**提供接口是姿态，数据是壁垒。**

## 商业模式

### AMI 用户

AMI 用户可选择自带 LLM API Key，也可以用我们的付费 LLM 服务：

| AMI 用户类型 | LLM Key | Memory Service | 我们的收入 |
|-------------|---------|----------------|-----------|
| **自带 Key** | 用户自己的 Anthropic Key | 免费（我们付 Plan/Learn 的 LLM 费） | 无（换数据） |
| **用我们的 LLM** | 用我们的 Key | 免费 | Agent 执行的 LLM 加价 |

关键：Plan/Learn 的 LLM 费用始终由我们承担。
- Learn 是帮我们积累数据，不该花用户的钱
- Plan 是我们提供的价值，用我们的 Key 控制质量
- 对 AMI 用户来说 Memory Service 是**真免费**，接入零摩擦

### 2B 开发者（Agent 框架接入）

Agent 开发者（OpenClaw、Browser-use 等）接入 Memory Service API，按量付费：

| 额度 | 费用 |
|------|------|
| 免费额度 | 每月 N 次 plan + M 次 learn |
| 超出 | 按调用量收费 |

### 2C 用户

间接通过 2B，最终用户不直接和我们打交道。Agent 开发者负责将 Memory 费用打包到自己的产品定价中。

### 收入来源总结

1. **AMI 付费用户**：不想自带 Key 的人，用我们的 LLM 服务，赚差价
2. **2B**：Agent 开发者接入 Memory API，按量付费
3. **2C**：间接通过 2B

AMI 免费用户不赚钱，但**他们是数据来源**——用执行数据换免费 Memory Service，公平交换。早期砸钱养数据，数据是真正的壁垒。

## 分阶段推进

| 阶段 | 动作 |
|------|------|
| **Phase 1** | 把 Memory Service 从 Cloud Backend 中解耦，独立部署，对外提供 API |
| **Phase 2** | 开源 AMI，文档中引导接入 Memory Service |
| **Phase 3** | 发布 OpenClaw Plugin + Python SDK，扩大接入面 |
| **Phase 4** | 积累数据，验证飞轮效应 |
| **Phase 5** | 向更多 Agent 框架推广（Browser-use, Playwright Agent 等） |

## Cloud Backend 解耦

当前 `main.py` 5000+ 行单体，Memory 14 个 endpoint 和 Workflow 生成、Recording 管理混在一起。

### 解耦目标

```
现在：
  cloud_backend/main.py (5000+ 行)
    ├── Memory endpoints (14 个)
    ├── Workflow endpoints (7 个)
    ├── Recording endpoints (5 个)
    ├── Intent Builder endpoints (4 个)
    └── Auth/Log endpoints (4 个)

未来：
  memory-service/     (独立部署，对外)
    ├── Plan API
    ├── Learn API
    ├── Query API
    └── Add API

  ami-backend/        (AMI 专用，可开源)
    ├── Workflow 生成
    ├── Recording 管理
    └── Intent Builder
```

### 解耦路径

1. 把 14 个 Memory endpoint 抽取为独立 FastAPI 应用
2. `src/common/memory/` 模块不动（已经独立）
3. AMI Backend 通过 HTTP 调 Memory Service（和外部 Agent 一样）
4. Memory Service 加 API Key 认证层

## OpenClaw 接入方案

OpenClaw 作为第二个接入方（AMI 之后），通过 npm Plugin 接入：

### Plugin 结构

```
ami-memory-plugin/
  ├── index.ts          # 注册 hook + tool
  ├── planner-client.ts # 调 Memory Service API
  └── skills/
      └── SKILL.md      # 教 agent 使用 planning
```

### Hook 机制

| Hook | 用途 |
|------|------|
| `before_agent_start` | 检测浏览器任务 → 调 Plan API → 注入 workflow_guide |
| `agent_end` | 采集执行数据 → 调 Learn API → 贡献到 public memory |

### 数据采集与脱敏

```
agent_end 事件: { messages[], success, durationMs }
  → 提取 tool_use + tool_result
  → 脱敏：URL 保留 domain+path，输入值替换为 <user_input>
  → 组装 TaskExecutionData
  → POST /learn
```

### 隐私控制

- 配置项：`contributeToPublicMemory: true | false`（默认 true）
- 只采集操作模式（tool_name + URL pattern + success/fail），不采集具体数据
- 用户可随时关闭

## 关键原则

1. **AMI 是样板，不是产品**：开源 AMI 的目的是展示 Memory 的价值，不是卖 AMI
2. **Memory 是平台，不是功能**：面向所有 Agent，不只是 AMI
3. **数据是壁垒，不是代码**：算法可以被抄，积累的 CognitivePhrase 抄不走
4. **早期砸钱养数据**：免费提供 Plan/Learn API，用 LLM 成本换数据积累
5. **Planner 是鱼饵，Learner 是鱼钩**：Agent 接入是为了 Plan 的价值，Learn 顺带贡献数据
