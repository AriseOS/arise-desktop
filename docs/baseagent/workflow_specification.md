# AgentCrafter Workflow 规范文档

## 概述

AgentCrafter支持基于YAML的声明式工作流定义，具备条件执行、控制流和多Agent协作能力。

## 工作流文件位置

所有工作流文件统一存放在：
- **用户工作流**: `base_app/base_app/base_agent/workflows/user/`
- **内置工作流**: `base_app/base_app/base_agent/workflows/builtin/`

## 核心能力

### 1. 支持的步骤类型

#### 普通Agent步骤
- `text_agent` - 文本生成Agent
- `tool_agent` - 工具调用Agent  
- `code_agent` - 代码执行Agent
- `interactive_agent` - 交互式Agent

#### 控制流步骤
- `if` - 条件分支控制（`control_type: "if"`）
- `while` - 条件循环控制（`control_type: "while"`）
- `foreach` - 列表迭代循环（`agent_type: "foreach"`）
- `variable` - 变量操作（`agent_type: "variable"`）

### 2. 条件执行能力

#### 普通步骤的条件执行
**所有普通Agent步骤都支持`condition`字段**：
```yaml
- id: "browser-task"
  name: "浏览器任务"
  agent_type: "tool_agent"
  condition: "{{task_type}} == 'browser'"  # 条件满足才执行
  agent_instruction: "执行浏览器操作"
```

#### 控制流步骤
**if分支控制**：
```yaml
- id: "conditional-branch"
  name: "条件分支"
  control_type: "if"
  condition: "{{has_task}} == true"
  then_steps:
    - id: "task-execution"
      agent_type: "tool_agent"
      # ...
  else_steps:
    - id: "fallback"
      agent_type: "text_agent"
      # ...
```

**while循环控制**：
```yaml
- id: "conversation-loop"
  name: "对话循环"
  control_type: "while"
  condition: "{{continue_chat}} == true"
  max_iterations: 10
  loop_timeout: 300
  then_steps:
    - id: "chat-turn"
      agent_type: "interactive_agent"
      # ...
```

**foreach列表迭代**：
```yaml
- id: "process-items"
  name: "处理商品列表"
  agent_type: "foreach"
  source: "{{product_list}}"        # 要遍历的列表变量
  item_var: "current_product"       # 当前项的变量名（可选，默认"item"）
  index_var: "product_index"        # 当前索引的变量名（可选，默认"index"）
  max_iterations: 100               # 最大迭代次数（可选，默认100）
  loop_timeout: 600                 # 循环总超时（秒，可选，默认600）
  steps:
    - id: "process-product"
      agent_type: "tool_agent"
      inputs:
        product_url: "{{current_product.url}}"  # 访问当前项的属性
        index: "{{product_index}}"              # 访问当前索引
      # ...
```

### 3. 变量和上下文

#### 变量引用语法
- 使用`{{variable_name}}`引用上下文变量
- 支持字符串、数字、布尔值比较
- 示例：`{{task_type}} == 'browser'`、`{{confidence}} > 0.8`

#### 输入输出映射
```yaml
inputs:
  user_message: "{{user_input}}"
  context: "{{previous_result}}"

outputs:
  result: "task_result"
  success: "execution_success"
```

## 完整的Workflow结构

```yaml
# 基础信息
apiVersion: "agentcrafter.io/v1"
kind: "Workflow"

metadata:
  name: "workflow-name"
  description: "工作流描述"
  version: "1.0.0"
  author: "作者"
  tags: ["标签1", "标签2"]

# 输入定义
inputs:
  user_input:
    type: "string"
    description: "用户输入"
    required: true

# 输出定义  
outputs:
  final_result:
    type: "string"
    description: "最终结果"

# 执行配置
config:
  max_execution_time: 3600
  enable_parallel: false
  enable_cache: true

# 工作流步骤
steps:
  # 普通Agent步骤
  - id: "step-1"
    name: "意图识别"
    agent_type: "interactive_agent"
    agent_instruction: "分析用户输入并识别意图"
    
    inputs:
      user_message: "{{user_input}}"
    
    outputs:
      intent: "user_intent"
      task_type: "task_type"
    
    timeout: 300
    retry_count: 1

  # 条件步骤
  - id: "browser-task"
    name: "浏览器任务"
    agent_type: "tool_agent"
    condition: "{{task_type}} == 'browser'"  # 关键：条件执行
    
    agent_instruction: "执行浏览器操作"
    allowed_tools: ["browser_use"]
    
    inputs:
      task: "{{user_intent}}"
    
    outputs:
      result: "browser_result"

  # 控制流步骤
  - id: "conditional-processing"
    name: "条件处理"
    control_type: "if"
    condition: "{{task_type}} == 'complex'"
    
    then_steps:
      - id: "complex-handler"
        agent_type: "tool_agent"
        agent_instruction: "处理复杂任务"
        # ...
    
    else_steps:
      - id: "simple-handler"  
        agent_type: "text_agent"
        agent_instruction: "处理简单任务"
        # ...
```

## Agent特定配置

### ToolAgent配置
```yaml
agent_type: "tool_agent"
tools:
  allowed: ["browser_use", "file_manager"]
  fallback: ["browser_use"]
  confidence_threshold: 0.8
```

### CodeAgent配置
```yaml
agent_type: "code_agent"
code:
  allowed_libraries: ["pandas", "numpy", "matplotlib"]
  expected_output_format: "执行结果和分析"
```

### TextAgent配置
```yaml
agent_type: "text_agent"
response_style: "professional"
max_length: 500
```

### InteractiveAgent配置
```yaml
agent_type: "interactive_agent"
# InteractiveAgent会通过消息队列获取用户输入
```

## 执行流程

### 条件评估规则
1. **普通步骤**：如果有`condition`字段，先评估条件，条件为false则跳过该步骤
2. **控制流步骤**：根据`condition`选择执行分支
3. **变量解析**：`{{variable}}`会被替换为上下文中的实际值

### 变量传递
1. 步骤的`outputs`会更新上下文变量
2. 后续步骤可以通过`{{variable}}`引用
3. 控制流步骤会传递分支执行结果

## 最佳实践

### 1. 条件执行模式
```yaml
steps:
  # 第一步：意图识别
  - id: "intent-analysis"
    agent_type: "interactive_agent"
    outputs:
      task_type: "task_type"
      description: "task_description"

  # 第二步：根据任务类型条件执行
  - id: "browser-handler"
    agent_type: "tool_agent"
    condition: "{{task_type}} == 'browser'"
    # ...

  - id: "code-handler"
    agent_type: "code_agent"
    condition: "{{task_type}} == 'code'"
    # ...

  - id: "text-handler"
    agent_type: "text_agent"
    condition: "{{task_type}} == 'text'"
    # ...
```

### 2. 分支控制模式
```yaml
steps:
  - id: "task-router"
    control_type: "if"
    condition: "{{task_type}} == 'browser'"
    then_steps:
      - id: "browser-ops"
        agent_type: "tool_agent"
        # ...
    else_steps:
      - id: "check-code"
        control_type: "if"
        condition: "{{task_type}} == 'code'"
        # 嵌套分支...
```

### 3. 循环处理模式

**while条件循环**：
```yaml
steps:
  - id: "conversation-loop"
    control_type: "while"
    condition: "{{has_clear_task}} != true"
    max_iterations: 5
    then_steps:
      - id: "chat-turn"
        agent_type: "interactive_agent"
        outputs:
          has_clear_task: "has_clear_task"
```

**foreach列表迭代**：
```yaml
steps:
  # 1. 收集URL列表
  - id: "collect-urls"
    agent_type: "scraper_agent"
    outputs:
      extracted_data: "all_urls"

  # 2. 遍历每个URL
  - id: "process-urls"
    agent_type: "foreach"
    source: "{{all_urls}}"
    item_var: "current_url"
    index_var: "url_index"
    max_iterations: 50
    steps:
      - id: "fetch-detail"
        agent_type: "scraper_agent"
        inputs:
          target_path: "{{current_url.url}}"
        outputs:
          extracted_data: "detail"

      - id: "save-detail"
        agent_type: "variable"
        inputs:
          operation: "append"
          source: "{{all_details}}"
          data: "{{detail}}"
        outputs:
          result: "all_details"
```

## 关键要点

1. **条件执行**：普通Agent步骤通过`condition`字段实现条件执行，不需要嵌套在控制流中
2. **控制流**：`if`和`while`控制流步骤用于复杂的分支和循环逻辑
3. **列表迭代**：`foreach`步骤专门用于遍历列表，自动管理当前项和索引变量
4. **变量作用域**：所有步骤共享同一个上下文变量空间，`foreach`自动添加和清理迭代变量
5. **执行顺序**：按步骤定义顺序执行，跳过条件不满足的步骤
6. **错误处理**：支持步骤级别的超时和重试配置

## foreach vs while 选择指南

**使用foreach当**：
- 需要遍历已知的列表/数组
- 需要访问当前项的所有属性
- 需要知道当前索引位置
- 不需要手动管理循环变量

**使用while当**：
- 循环条件是动态变化的（不是列表遍历）
- 需要基于运行时状态决定是否继续
- 循环次数不确定

这个规范支持了你提到的需求：每个Agent可以通过`condition`字段判断`task_type`来决定是否执行，无需复杂的嵌套控制流结构。