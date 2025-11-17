# BaseAgent技术架构描述

## 核心架构概述

BaseAgent框架采用了三层架构设计：**BaseAgent核心框架** + **Workflow引擎** + **Step As Agent执行模式**，实现了高度模块化和可扩展的智能代理系统。

## 1. Workflow + Step As Agent 架构模式

### 1.1 核心设计理念
**Step As Agent**模式将传统的workflow步骤转换为独立的智能代理，每个步骤不再是简单的函数调用，而是一个完整的Agent实例。

### 1.2 技术实现结构
```
AgentWorkflowEngine (base_agent/core/agent_workflow_engine.py:24)
├── AgentRegistry - 管理所有可用Agent类型
├── AgentExecutor - 负责Agent的执行调度  
├── AgentRouter - 处理Agent间的路由和通信
└── ConditionEvaluator - 处理条件表达式求值
```

### 1.3 内置Agent类型
系统内置三种基础Agent类型：

**TextAgent** (base_agent/agents/text_agent.py:22)
- 基于LLM的文本生成和理解
- 支持结构化JSON输出格式
- 智能提示词构建和响应解析

**ToolAgent** (base_agent/agents/tool_agent.py:13)  
- 工具调用的智能代理
- 两轮决策机制：先选工具，再选API
- 置信度评估和工具降级策略

**CodeAgent** (base_agent/agents/code_agent.py:17)
- Python代码生成和安全执行
- AST安全检查机制
- 沙箱执行环境

### 1.4 YAML配置驱动
工作流通过YAML文件定义，支持：
- 条件分支 (`if/else`)
- 循环控制 (`while`)  
- 变量传递和模板解析 (`{{variable_name}}`)
- Agent参数配置

示例工作流 (base_agent/workflows/builtin/user-qa-workflow.yaml:38)：
```yaml
steps:
  - id: "intent-analysis"
    agent_type: "text_agent"
    outputs:
      intent_type: "intent_type"
  
  - id: "intent-routing"  
    agent_type: "if"
    condition: "{{intent_type}} == 'tool'"
    then: [...] # 工具调用分支
    else: [...] # 代码或对话分支
```

### 1.5 执行流程
1. **工作流解析**: YAML转换为AgentWorkflowStep对象列表
2. **上下文初始化**: 创建AgentContext存储变量和状态
3. **步骤执行**: 顺序执行每个Agent步骤
4. **变量传递**: 通过模板语法实现步骤间数据流转
5. **条件控制**: 支持if/while等控制流结构

## 2. Plan-Generate-Exec模式 (ScraperAgent实现)

### 2.1 架构设计
ScraperAgent实现了经典的两阶段模式：

**Phase 1: Plan & Generate (Initialize模式)**
- 分析目标页面DOM结构
- 使用LLM生成数据提取脚本
- 脚本缓存到KV存储中

**Phase 2: Execute (Execute模式)**  
- 加载缓存的提取脚本
- 在目标页面执行数据提取
- 返回结构化提取结果

### 2.2 技术实现细节

**DOM分析引擎** (base_agent/tools/browser_use/dom_extractor.py)
```python
# 双模式DOM提取
if dom_scope == "full":
    target_dom, _ = extractor.serialize_accessible_elements_custom(
        enhanced_dom, include_non_visible=True  # 完整DOM
    )
else:
    target_dom, _ = extractor.serialize_accessible_elements_custom(
        enhanced_dom, include_non_visible=False # 可见DOM
    )
```

**脚本生成流程** (base_agent/agents/scraper_agent.py:637)
1. DOM结构分析和特征提取
2. LLM理解数据需求
3. 生成基于特征匹配的Python脚本
4. 脚本包装为`execute_extraction`函数

**执行模式切换** (base_agent/agents/scraper_agent.py:73)
```python
# 支持两种提取方法
extraction_method: str = 'script'  # script | llm
- script模式: Plan-Generate-Exec
- llm模式: 直接LLM提取
```

### 2.3 关键技术特性

**智能脚本缓存**
- 基于数据需求生成唯一Key
- 支持不同DOM配置的脚本版本
- Initialize阶段生成，Execute阶段复用

**安全执行环境**
- 受限的Python执行环境
- 预定义的安全内建函数集
- DOM数据注入而非网络访问

**容错机制**
- 脚本执行失败时的错误回传
- LLM模式作为fallback选项
- 详细的调试信息输出

## 3. 架构优势

### 3.1 模块化设计
- 每个Agent都是独立的执行单元
- 支持动态Agent注册和发现
- 工作流和Agent实现完全解耦

### 3.2 可扩展性
- 新Agent类型只需继承BaseStepAgent
- YAML配置支持复杂的控制流
- Provider抽象支持多种LLM后端

### 3.3 状态管理
- 统一的AgentContext状态传递
- 变量模板系统支持数据流转
- 完整的执行历史记录

### 3.4 Memory 系统架构

**核心原则**: Memory 绑定到用户，不绑定到 BaseAgent 实例

```
User (用户)
  ├── owns Memory (用户的持久化数据)
  └── uses multiple BaseAgent instances

BaseAgent Instance (长期运行的容器)
  ├── serves specific User
  ├── executes User's Workflows
  └── accesses User's Memory (via user_id)
```

**设计要点**:
1. **BaseAgent 是无状态容器** - 可以为同一用户创建多个实例
2. **Memory 有状态且持久** - 绑定到 `user_id`，跨实例共享
3. **创建 BaseAgent 时必须指定 user_id** - 确保访问正确用户的 Memory
4. **示例用法**:
```python
# 为用户 user123 创建 BaseAgent 实例
agent = BaseAgent(
    config,
    config_service=config_service,
    provider_config=provider_config,
    user_id="user123"  # 指定用户ID
)

# 多个实例共享同一用户的 Memory
agent1 = BaseAgent(..., user_id="user123")
agent2 = BaseAgent(..., user_id="user123")
# agent1 和 agent2 可以访问相同的缓存数据
```

这种架构设计使得BaseAgent既保持了workflow的灵活性，又具备了Agent的智能决策能力，特别适合需要多步骤智能处理的复杂任务场景。

## 4. 核心代码文件索引

### 4.1 核心框架文件
- `base_app/base_app/base_agent/core/base_agent.py` - BaseAgent主类实现
- `base_app/base_app/base_agent/core/agent_workflow_engine.py` - Agent工作流引擎
- `base_app/base_app/base_agent/core/schemas.py` - 数据结构定义

### 4.2 Agent实现文件
- `base_app/base_app/base_agent/agents/text_agent.py` - 文本生成Agent
- `base_app/base_app/base_agent/agents/tool_agent.py` - 工具调用Agent
- `base_app/base_app/base_agent/agents/code_agent.py` - 代码生成Agent
- `base_app/base_app/base_agent/agents/scraper_agent.py` - 爬虫Agent(Plan-Generate-Exec模式)

### 4.3 工作流配置文件
- `base_app/base_app/base_agent/workflows/builtin/user-qa-workflow.yaml` - 用户问答工作流

### 4.4 工具和支持文件
- `base_app/base_app/base_agent/tools/browser_use/dom_extractor.py` - DOM提取工具
- `base_app/base_app/base_agent/providers/` - LLM Provider抽象层