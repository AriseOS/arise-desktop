# Workflows 目录

AgentCrafter工作流配置文件存储目录。

## 目录结构

```
base_agent/workflows/
├── README.md                 # 本文件
├── builtin/                  # 内置工作流
│   ├── user-qa-workflow.yaml # 用户问答工作流
│   └── ...                   # 其他内置工作流
└── user/                     # 用户自定义工作流
    └── ...                   # 用户创建的工作流文件
```

## 工作流配置文件规范

### 文件格式
- 主要使用 **YAML** 格式 (`.yaml` 或 `.yml`)
- 也支持 JSON 格式 (`.json`)
- 文件命名采用 kebab-case: `my-workflow-name.yaml`

### 配置文件结构

```yaml
apiVersion: "agentcrafter.io/v1"
kind: "Workflow"

metadata:
  name: "workflow-name"           # 工作流名称（必填）
  description: "工作流描述"        # 描述信息
  version: "1.0.0"               # 版本号
  author: "作者"                 # 作者
  tags: ["tag1", "tag2"]         # 标签

inputs:                          # 输入定义
  input_name:
    type: "string"               # 数据类型
    description: "输入描述"
    required: true               # 是否必填
    default: "默认值"            # 默认值（可选）

outputs:                         # 输出定义
  output_name:
    type: "string"
    description: "输出描述"

config:                          # 全局配置
  max_execution_time: 600        # 最大执行时间（秒）
  enable_parallel: false        # 是否启用并行执行
  enable_cache: true             # 是否启用缓存

steps:                           # 工作流步骤
  - id: "step-id"                # 步骤唯一标识
    name: "步骤名称"
    agent_type: "text_agent"     # Agent类型
    description: "步骤描述"
    task_description: "任务描述"
    
    # 执行条件（可选）
    condition:
      expression: "{{variable}} == 'value'"
      description: "条件描述"
    
    # Agent特定配置
    text:                        # text_agent配置
      response_style: "professional"
      max_length: 500
    
    tools:                       # tool_agent配置
      allowed: ["tool1", "tool2"]
      confidence_threshold: 0.8
    
    code:                        # code_agent配置
      allowed_libraries: ["pandas", "numpy"]
      expected_output_format: "JSON"
    
    # 输入输出映射
    inputs:
      input_key: "{{variable_name}}"
    
    outputs:
      output_key: "variable_name"
    
    # 执行控制
    timeout: 60
    retry_count: 1
    
    # 错误处理
    error_handling:
      strategy: "continue"       # continue | stop | retry
      fallback_value: "默认值"

# 高级特性
execution:                       # 执行策略
  parallel_groups: []           # 并行执行组
  dependencies: {}              # 依赖关系
  flow_control: {}              # 流控制

error_handling:                  # 全局错误处理
  global_strategy: "fail_gracefully"
  fallback_response: "错误回复"

monitoring:                      # 监控配置
  enable_step_timing: true
  log_level: "INFO"

caching:                         # 缓存配置
  enable: true
  ttl: 3600
```

## Agent类型说明

### 1. text_agent
文本生成Agent，用于问答、总结、翻译等文本处理任务。

**配置项：**
- `response_style`: 回答风格 (professional/casual/technical)
- `max_length`: 最大回答长度
- `language`: 语言 (zh/en)

### 2. tool_agent  
工具调用Agent，用于执行具体的工具操作。

**配置项：**
- `allowed`: 允许使用的工具列表
- `fallback`: 备选工具列表
- `confidence_threshold`: 工具选择置信度阈值
- `max_tools_per_step`: 单步最大工具数

### 3. code_agent
代码执行Agent，用于代码分析、生成和执行。

**配置项：**
- `allowed_libraries`: 允许使用的库
- `expected_output_format`: 期望输出格式
- `execution_timeout`: 执行超时时间
- `memory_limit_mb`: 内存限制

## 条件执行

工作流支持基于变量的条件执行：

```yaml
condition:
  expression: "{{intent_type}} == 'tool'"
  description: "仅当意图类型为工具调用时执行"
```

**支持的操作符：**
- 比较: `==`, `!=`, `>`, `<`, `>=`, `<=`
- 逻辑: `and`, `or`, `not`
- 包含: `in`, `not in`
- 存在: `exists`, `not exists`

## 变量绑定

使用 `{{variable_name}}` 语法在步骤间传递数据：

```yaml
inputs:
  user_input: "{{user_input}}"    # 从工作流输入获取
  result: "{{previous_step_result}}"  # 从前面步骤获取

outputs:
  answer: "final_response"        # 输出到变量
```

## 错误处理策略

### 步骤级错误处理
- `continue`: 继续执行下一步
- `stop`: 停止整个工作流
- `retry`: 重试当前步骤

### 全局错误处理
- `fail_fast`: 遇到错误立即失败
- `fail_gracefully`: 优雅失败，返回fallback响应

## 最佳实践

1. **命名规范**：使用描述性的步骤ID和名称
2. **错误处理**：为关键步骤设置适当的错误处理策略
3. **超时设置**：根据步骤复杂度设置合理的超时时间
4. **文档化**：添加清晰的描述和注释
5. **测试**：创建测试用例验证工作流正确性

## 示例工作流

查看 `builtin/user-qa-workflow.yaml` 了解完整的工作流配置示例。