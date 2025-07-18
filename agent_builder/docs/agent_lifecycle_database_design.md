# Agent构建过程数据存储设计

## 概述

专注于Agent构建过程中最核心、最必要的数据存储需求。

## 构建过程中需要存储的核心数据

### 1. 构建基本信息
- **构建ID**：唯一标识一次构建
- **用户ID**：谁发起的构建
- **用户描述**：用户输入的原始需求
- **构建状态**：building/completed/failed
- **开始时间**：构建开始时间
- **完成时间**：构建结束时间

### 2. 构建结果数据
- **需求解析结果**：LLM解析后的Agent目的
- **生成的代码**：最终生成的Agent代码
- **工作流配置**：生成的YAML配置文件

### 3. 构建过程追踪
- **当前步骤**：正在执行哪个步骤
- **错误信息**：如果失败，错误详情

## 最简数据表设计

```sql
CREATE TABLE agent_builds (
    build_id VARCHAR(255) PRIMARY KEY,
    user_id INTEGER NOT NULL,
    
    -- 基本信息
    user_description TEXT NOT NULL,
    status ENUM('building', 'completed', 'failed') DEFAULT 'building',
    current_step VARCHAR(100),
    error_message TEXT,
    
    -- 构建结果
    agent_purpose TEXT,                    -- 解析后的Agent目的
    generated_code TEXT,                   -- 生成的Python代码
    workflow_config TEXT,                  -- 生成的YAML配置
    
    -- 时间戳
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_builds (user_id, status)
);
```

## 数据流转

1. **开始构建**：创建记录，status='building'
2. **步骤执行**：更新current_step
3. **生成结果**：保存agent_purpose, generated_code, workflow_config
4. **构建完成**：status='completed', 设置completed_at
5. **构建失败**：status='failed', 记录error_message

这是最基础的数据存储需求，确保能够：
- 追踪构建状态
- 保存构建结果
- 支持错误调试
- 查询构建历史