# AgentBuilder 复杂测试脚本使用说明

## 概述

`test_builder.py` 是一个功能强大的 AgentBuilder 测试脚本，支持完整流程测试和单步测试。每个单步测试都使用 mock 数据来独立测试特定模块，无需依赖前面步骤的结果。

## 功能特性

### 1. 完整流程测试
- 测试 AgentBuilder 的完整构建流程
- 从需求解析到代码生成的端到端测试

### 2. 单步测试（使用 mock 数据）
- **步骤 1**: 需求解析 - 使用真实的用户描述
- **步骤 2**: 步骤提取 - 使用 mock 需求解析结果
- **步骤 3**: Agent类型判断 - 使用 mock 步骤提取结果
- **步骤 4**: StepAgent生成 - 使用 mock 步骤提取结果
- **步骤 5**: 工作流构建 - 使用 mock 步骤和Agent规格
- **步骤 6**: 工作流注册 - 使用 mock 工作流
- **步骤 7**: 代码生成 - 使用 mock 工作流和Agent规格

## 使用方法

### 基本语法
```bash
python test_builder.py --description "用户需求描述" [选项]
```

### 参数说明
- `--description, -d`: 用户需求描述 (必需)
- `--step`: 测试特定步骤 (1-7，可选)
- `--output, -o`: 输出目录 (默认: ./output)
- `--provider`: LLM提供商 (默认: openai)
- `--model`: LLM模型 (默认: gpt-4o)
- `--api-key`: API密钥 (可通过环境变量设置)

### 环境变量
```bash
export OPENAI_API_KEY="your-api-key-here"
```

## 使用示例

### 1. 完整流程测试
```bash
python test_builder.py -d "创建一个工作汇报助手"
```

### 2. 单步测试示例

#### 测试步骤1：需求解析
```bash
python test_builder.py --step 1 -d "创建一个工作汇报助手"
```

#### 测试步骤2：步骤提取
```bash
python test_builder.py --step 2 -d "创建一个工作汇报助手"
```

#### 测试步骤3：Agent类型判断
```bash
python test_builder.py --step 3 -d "创建一个工作汇报助手"
```

#### 测试步骤4：StepAgent生成
```bash
python test_builder.py --step 4 -d "创建一个工作汇报助手"
```

#### 测试步骤5：工作流构建
```bash
python test_builder.py --step 5 -d "创建一个工作汇报助手"
```

#### 测试步骤6：工作流注册
```bash
python test_builder.py --step 6 -d "创建一个工作汇报助手"
```

#### 测试步骤7：代码生成
```bash
python test_builder.py --step 7 -d "创建一个工作汇报助手"
```

### 3. 高级用法

#### 使用不同的模型
```bash
python test_builder.py --step 1 -d "创建一个工作汇报助手" --model gpt-3.5-turbo
```

#### 指定输出目录
```bash
python test_builder.py -d "创建一个工作汇报助手" --output ./my_output
```

#### 使用API密钥参数
```bash
python test_builder.py --step 1 -d "创建一个工作汇报助手" --api-key "your-api-key"
```

## Mock 数据说明

### 单步测试中的 Mock 数据
- **步骤2-7**: 使用预定义的 mock 数据，模拟前面步骤的输出
- **工作汇报场景**: Mock 数据基于"工作汇报助手"的典型用例设计
- **数据一致性**: 所有 mock 数据保持逻辑一致性

### Mock 数据内容
- **需求解析结果**: 智能工作汇报助手的目标定义
- **步骤提取结果**: 数据收集、分析、汇报生成三个步骤
- **Agent类型**: tool、text、text 的组合
- **工作流**: 完整的工作流定义，包含数据流转
- **Agent规格**: 详细的Agent实现规格

## 输出格式

### 测试成功示例
```
🧪 AgentBuilder 复杂测试脚本
提供商: openai
模型: gpt-4o
用户描述: 创建一个工作汇报助手
============================================================
🎯 单步测试模式 - 步骤 1
📦 使用 mock 数据进行独立测试
============================================================
📝 测试步骤1: 需求解析
用户描述: 创建一个工作汇报助手
----------------------------------------
✅ 需求解析成功
Agent目的: 智能工作汇报助手，帮助用户自动总结工作内容并生成汇报
```

### 测试失败示例
```
❌ 需求解析失败: OpenAI API key 未设置
```

## 故障排除

### 常见问题

1. **API密钥未设置**
   ```
   ❌ 错误: 未设置API密钥
   ```
   解决方法：设置环境变量或使用 --api-key 参数

2. **模块导入失败**
   ```
   ModuleNotFoundError: No module named 'core.agent_builder'
   ```
   解决方法：确保在正确的目录中运行脚本

3. **无效的步骤编号**
   ```
   ❌ 无效的步骤编号: 8
   ```
   解决方法：使用 1-7 之间的步骤编号

### 调试技巧

1. **启用详细日志**
   ```bash
   python test_builder.py --step 1 -d "test" 2>&1 | grep -E "(INFO|ERROR|WARNING)"
   ```

2. **测试特定模块**
   ```bash
   python test_builder.py --step 1 -d "简单测试"
   ```

3. **检查输出目录**
   ```bash
   ls -la ./output/
   ```

## 开发说明

### 添加新的 Mock 数据
1. 在 `AgentBuilderTester` 类中添加新的 `get_mock_*` 方法
2. 更新 `test_individual_step` 方法以使用新的 mock 数据
3. 确保数据格式与实际模块输出一致

### 扩展测试场景
1. 修改 mock 数据以支持不同的用例
2. 添加新的测试方法
3. 更新使用文档

## 注意事项

1. **API 费用**: 真实的 LLM 调用会产生费用
2. **Mock 数据**: 单步测试使用的 mock 数据可能与实际输出有差异
3. **环境依赖**: 需要正确设置 Python 环境和依赖包
4. **网络连接**: 需要稳定的网络连接来调用 LLM API