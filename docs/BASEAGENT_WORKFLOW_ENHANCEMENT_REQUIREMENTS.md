# BaseAgent Workflow系统增强需求文档

## 文档信息
- **版本**: 3.0
- **创建时间**: 2025-07-22
- **更新时间**: 2025-07-22
- **目标**: 基于"算子即结构，判断即Agent"理念为BaseAgent Workflow添加if/else和while控制流

## 1. 现状分析

### 1.1 当前能力
BaseAgent Workflow采用Agent-as-Step架构，具备以下核心能力：
- **顺序执行**: 支持线性步骤序列执行
- **条件跳转**: 基于变量比较的简单条件执行
- **变量传递**: 使用`{{variable_name}}`模板的数据流传递
- **智能路由**: Auto类型Agent的自动选择机制
- **统一接口**: TextAgent、ToolAgent、CodeAgent的统一执行接口

### 1.2 关键限制
- **控制流单一**: 仅支持顺序+简单条件，缺乏循环和复杂分支
- **错误处理粗糙**: 主要是fail-fast模式，缺乏重试机制
- **状态管理简单**: 全局变量模式，缺乏作用域管理

## 2. 用户需求场景分析

### 2.1 条件分支需求  
**场景**: 智能客服系统
```
意图识别 → 根据意图类型分派到不同处理分支 → 合并响应
```
**需求**: 基于条件的多路分支控制

### 2.2 循环处理需求
**场景**: 批量数据处理和重试机制
```
读取数据列表 → 循环处理每个项目 → 累积结果
API调用失败 → 自动重试 → 直到成功或达到上限
```
**需求**: 支持迭代和循环控制

## 3. 核心功能需求

### 3.1 增强条件控制 [必需]

#### 3.1.1 If/Else分支控制
**功能**: 基于条件的二分支执行
```yaml
steps:
  - id: "user_check"
    type: "if"
    condition: "{{user_type}} == 'premium'"
    inputs: {}
    outputs:
      branch_executed: "service_branch"
    then:
      - id: "premium_service"
        agent_type: "text_agent"
        agent_instruction: "提供高级服务"
        inputs:
          question: "{{premium_prompt}}"
          context_data:
            user_type: "{{user_type}}"
        outputs:
          answer: "service_response"
    else:
      - id: "basic_service"
        agent_type: "text_agent"
        agent_instruction: "提供基础服务"
        inputs:
          question: "{{basic_prompt}}"
          context_data:
            user_type: "{{user_type}}"
        outputs:
          answer: "service_response"
```

#### 3.1.2 嵌套条件控制
**功能**: 支持多层嵌套的if/else结构
```yaml
steps:
  - id: "multi_condition_routing"
    type: "if"
    condition: "{{user_type}} == 'premium'"
    inputs: {}
    outputs:
      primary_branch: "user_category"
    then:
      - id: "check_subscription"
        type: "if"
        condition: "{{subscription_active}} == true"
        inputs: {}
        outputs:
          subscription_status: "final_service_type"
        then:
          - id: "active_premium_service"
            agent_type: "text_agent"
            agent_instruction: "提供活跃premium服务"
            inputs:
              question: "{{active_premium_prompt}}"
              context_data:
                user_type: "{{user_type}}"
                subscription_active: "{{subscription_active}}"
            outputs:
              answer: "final_response"
        else:
          - id: "expired_premium_service"
            agent_type: "text_agent"
            agent_instruction: "处理过期premium用户"
            inputs:
              question: "{{expired_premium_prompt}}"
              context_data:
                user_type: "{{user_type}}"
            outputs:
              answer: "final_response"
    else:
      - id: "check_trial"
        type: "if"
        condition: "{{trial_available}} == true"
        inputs: {}
        outputs:
          trial_status: "final_service_type"
        then:
          - id: "trial_service"
            agent_type: "text_agent"
            agent_instruction: "提供试用服务"
            inputs:
              question: "{{trial_service_prompt}}"
              context_data:
                trial_available: "{{trial_available}}"
            outputs:
              answer: "final_response"
        else:
          - id: "basic_service"
            agent_type: "text_agent"
            agent_instruction: "提供基础服务"
            inputs:
              question: "{{basic_service_prompt}}"
              context_data:
                user_type: "{{user_type}}"
            outputs:
              answer: "final_response"
```

#### 3.1.3 条件表达式增强
**功能**: 支持复杂的条件逻辑表达式
```yaml
condition:
  expression: "{{confidence}} > 0.8 and {{user_type}} in ['premium', 'vip']"
```

### 3.2 循环控制 [必需]

#### 3.2.1 While循环
**功能**: 基于条件的循环执行
```yaml
steps:
  - id: "retry_until_success"
    type: "while"
    condition: "{{success}} != true and {{retry_count}} < 5"
    inputs: {}
    outputs:
      iterations_executed: "total_attempts"
      exit_reason: "loop_exit_status"
    steps:
      - id: "attempt_operation"
        agent_type: "tool_agent"
        agent_instruction: "尝试执行API调用操作"
        inputs:
          task_description: "{{api_task_description}}"
          context_data:
            retry_count: "{{retry_count}}"
            endpoint: "{{api_endpoint}}"
        outputs:
          result: "operation_result"
          success: "success"
      - id: "update_counters"
        agent_type: "code_agent"
        agent_instruction: "更新重试计数器"
        inputs:
          task_description: "{{counter_update_task}}"
          input_data:
            current_count: "{{retry_count}}"
            success_status: "{{success}}"
        outputs:
          result: "retry_count"
```

#### 3.2.2 While循环安全限制
**功能**: 防止无限循环的安全机制
```yaml
steps:
  - id: "safe_while_loop"
    type: "while"
    condition: "{{task_incomplete}} == true"
    max_iterations: 10  # 最大循环次数限制
    timeout: 300        # 超时限制（秒）
    inputs: {}
    outputs:
      iterations_executed: "actual_iterations"
      exit_reason: "termination_reason"
    steps:
      - id: "process_task"
        agent_type: "text_agent"
        agent_instruction: "处理任务并更新完成状态"
        inputs:
          question: "{{task_processing_prompt}}"
          context_data:
            current_task: "{{current_task}}"
            progress: "{{task_progress}}"
        outputs:
          answer: "task_result"
      - id: "check_completion"
        agent_type: "code_agent" 
        agent_instruction: "检查任务完成状态"
        inputs:
          task_description: "{{completion_check_task}}"
          input_data:
            result: "{{task_result}}"
        outputs:
          result: "task_incomplete"  # 更新循环条件变量
```

## 4. 架构设计原则

### 4.1 核心理念：算子即结构，判断即Agent

#### 4.1.1 控制流算子设计
- **算子即结构**: if/else、while等控制流是"结构化节点"，负责组织和引导执行流程
- **轻量级条件判断**: 90%的条件判断通过内联表达式实现，无需额外Agent
- **统一的条件处理**: 支持直接变量引用、表达式计算和Agent输出判断

#### 4.1.2 判断逻辑统一方案

**内联条件判断**（最常见场景）
```yaml
steps:
  - id: "user_analysis"
    agent_type: "text_agent"
    agent_instruction: "分析用户状态，输出：premium, basic, 或 trial"
    inputs:
      question: "{{analysis_prompt}}"
      context_data:
        user_info: "{{user_info}}"
        subscription_data: "{{subscription_data}}"
    outputs:
      answer: "user_type"  # 将TextAgent的answer字段存储到user_type变量
    
  - id: "service_routing" 
    type: "if"
    condition: "{{user_type}} == 'premium'"
    inputs: {}  # 控制流节点通常不需要额外输入
    outputs:
      branch_executed: "selected_branch"  # 记录执行的分支
    then:
      - id: "premium_service"
        agent_type: "text_agent"
        agent_instruction: "提供高级服务"
        inputs:
          question: "{{premium_service_prompt}}"
          context_data:
            user_type: "{{user_type}}"
            user_info: "{{user_info}}"
        outputs:
          answer: "service_result"
    else:
      - id: "check_basic_user"
        type: "if" 
        condition: "{{user_type}} == 'basic'"
        inputs: {}
        outputs:
          branch_executed: "basic_or_trial"
        then:
          - id: "basic_service"
            agent_type: "text_agent"
            agent_instruction: "提供基础服务"
            inputs:
              question: "{{basic_service_prompt}}"
              context_data:
                user_type: "{{user_type}}"
            outputs:
              answer: "service_result"
        else:
          - id: "trial_service"
            agent_type: "text_agent"
            agent_instruction: "提供试用服务"
            inputs:
              question: "{{trial_service_prompt}}"
              context_data:
                user_type: "{{user_type}}"
            outputs:
              answer: "service_result"
```

**表达式条件判断**（中等复杂场景）
```yaml
steps:
  - id: "confidence_check"
    agent_type: "tool_agent"
    agent_instruction: "计算用户请求的置信度"
    inputs:
      task_description: "{{confidence_task_desc}}"
      context_data:
        user_request: "{{user_request}}"
    outputs:
      confidence: "confidence_score"
      
  - id: "complex_routing"
    type: "if"
    condition: "{{confidence_score}} > 0.8 and {{user_status}} == 'premium'"
    inputs: {}
    outputs:
      routing_result: "chosen_path"
    then:
      - id: "high_confidence_service"
        agent_type: "text_agent"
        agent_instruction: "提供高置信度premium服务"
        inputs:
          question: "{{high_confidence_prompt}}"
          context_data:
            confidence: "{{confidence_score}}"
            user_status: "{{user_status}}"
        outputs:
          answer: "final_result"
    else:
      - id: "standard_service"
        agent_type: "text_agent"
        agent_instruction: "提供标准服务"
        inputs:
          question: "{{standard_service_prompt}}"
          context_data:
            confidence: "{{confidence_score}}"
            user_status: "{{user_status}}"
        outputs:
          answer: "final_result"
```

**复杂逻辑判断**（复杂推理场景）
```yaml
steps:
  - id: "decision_agent"
    agent_type: "text_agent"
    agent_instruction: "基于多个因素决策路由策略"
    inputs:
      question: "{{decision_prompt}}"
      context_data:
        confidence: "{{confidence}}"
        user_history: "{{user_history}}"
        current_load: "{{system_load}}"
    outputs:
      answer: "routing_decision"  # TextAgent的answer字段存储到routing_decision变量
    
  - id: "apply_route_a"
    type: "if" 
    condition: "{{routing_decision}} == 'route_a'"
    inputs: {}
    outputs:
      branch_taken: "final_route"
    then:
      - id: "route_a_handler"
        agent_type: "tool_agent"
        agent_instruction: "执行路由A的处理逻辑"
        inputs:
          task_description: "{{route_a_task}}"
          context_data:
            decision: "{{routing_decision}}"
        outputs:
          result: "execution_result"
    else:
      - id: "apply_route_b"
        type: "if"
        condition: "{{routing_decision}} == 'route_b'"
        inputs: {}
        outputs:
          branch_taken: "final_route"
        then:
          - id: "route_b_handler"
            agent_type: "text_agent"
            agent_instruction: "执行路由B的处理逻辑"
            inputs:
              question: "{{route_b_prompt}}"
              context_data:
                decision: "{{routing_decision}}"
            outputs:
              answer: "execution_result"
        else:
          - id: "route_c_handler"
            agent_type: "code_agent"
            agent_instruction: "执行路由C的代码生成逻辑"
            inputs:
              task_description: "{{route_c_task}}"
              input_data:
                decision: "{{routing_decision}}"
            outputs:
              result: "execution_result"
```

#### 4.1.3 设计优势
- **减少概念复杂度**: 无需引入专门的LogicAgent类型
- **提高执行效率**: 简单条件无需LLM调用，直接计算
- **保持架构一致性**: 复杂逻辑仍遵循"Agent-as-Step"模式
- **降低学习成本**: 开发者只需掌握一套Agent概念

### 4.2 保持简洁性
- 控制流通过组合if/else和while两种基本元素实现
- 配置语法保持直观易懂
- 避免过度工程化，专注核心需求

### 4.3 确保安全性和可测试性
- While循环必须有最大迭代次数和超时限制
- 每个控制流元素独立可测试
- 提供完整的调试和监控能力
- 支持流程可视化

## 5. 实现优先级

### 第一阶段：基础条件控制
1. If/Else分支控制实现
2. 简单条件表达式支持
3. 基础测试和文档

### 第二阶段：循环控制
1. While循环实现
2. 安全限制机制
3. 嵌套控制流支持

### 第三阶段：增强功能
1. 复杂表达式引擎
2. 性能优化
3. 完整的可视化工具

## 6. 技术约束

- **兼容性**: 所有新功能必须与现有BaseAgent架构完全兼容
- **性能**: 控制流判断不应显著影响执行性能
- **安全性**: 必须防止无限循环和资源耗尽
- **可维护性**: 保持代码简洁，易于理解和维护

**注**: 本需求文档专注于workflow控制流增强，仅扩展if/else和while两种控制结构，不涉及Agent执行内核的修改。