# AgentCrafter 集成测试指南

本文档介绍 AgentCrafter 项目中的集成测试脚本使用方法，帮助开发者快速测试和验证系统功能。

## 目录
- [测试脚本概览](#测试脚本概览)
- [Demo 场景说明](#demo-场景说明)
- [测试脚本详解](#测试脚本详解)
- [常见使用场景](#常见使用场景)

---

## 测试脚本概览

AgentCrafter 提供两个主要的集成测试脚本：

| 脚本名称 | 路径 | 功能 | 使用场景 |
|---------|------|------|---------|
| **test_end_to_end.py** | `tests/integration/intent_builder/` | 端到端 Workflow 生成 | 从用户操作生成新的 Workflow |
| **run_workflow.py** | `tests/integration/workflow/` | Workflow 执行器 | 运行已有的 Workflow YAML |

### 核心区别

- **test_end_to_end.py**:
  - **生成器** - 用于创建新的 Workflow
  - 完整流程：用户操作 → 意图提取 → MetaFlow → Workflow YAML
  - 需要 LLM API（调用 Anthropic Claude）
  - 输出：生成新的 workflow.yaml 文件

- **run_workflow.py**:
  - **执行器** - 用于运行现有的 Workflow
  - 直接执行：加载 Workflow YAML → 执行步骤 → 返回结果
  - 需要 LLM API（用于 Agent 执行）
  - 输出：Workflow 执行结果和数据

---

## Demo 场景说明

AgentCrafter 目前支持两个 Demo 场景，用于演示网页数据采集能力：

### 1. Allegro 咖啡数据采集 (coffee_allegro)

**场景描述**：从波兰电商平台 Allegro 采集咖啡产品信息

**数据目录**：`tests/test_data/coffee_allegro/`

**采集内容**：
- 产品标题
- 产品价格
- 销量数据

**目标网站**：https://allegro.pl/kategoria/produkty-spozywcze-kawa-74030

---

### 2. Amazon 咖啡数据采集 (coffee_amazon)

**场景描述**：从 Amazon 采集咖啡产品信息

**数据目录**：`tests/test_data/coffee_amazon/`

**采集内容**：
- 产品标题
- 产品价格
- 产品评分

**目标网站**：Amazon 咖啡产品分类页面

---

## 测试脚本详解

### 1. test_end_to_end.py - Workflow 生成器

#### 功能说明

完整的端到端流程，从用户操作记录生成可执行的 Workflow：

```
用户操作录制 (user_operations.json)
    ↓
意图提取 (Intent Extraction)
    ↓
意图图构建 (Intent Memory Graph)
    ↓
MetaFlow 生成 (中间表示)
    ↓
Workflow YAML 生成 (最终产物)
```

#### 使用方法

```bash
# 1. 进入测试目录
cd tests/integration/intent_builder

# 2. 运行测试（默认使用 coffee_allegro 场景）
python test_end_to_end.py

# 3. 指定特定场景
TEST_NAME=coffee_allegro python test_end_to_end.py
TEST_NAME=coffee_amazon python test_end_to_end.py

# 4. 使用 pytest 运行（显示详细输出）
pytest test_end_to_end.py -v -s

# 5. 完全重新生成（删除缓存）
rm -rf ../../test_data/coffee_allegro/output/*
python test_end_to_end.py
```

#### 输入文件

- **用户操作记录**: `tests/test_data/{场景名}/fixtures/user_operations.json`
  - 包含用户在浏览器中的操作序列
  - 包含任务描述和元数据

#### 输出文件

所有输出保存在 `tests/test_data/{场景名}/output/` 目录：

1. **intent_graph.json** - 意图记忆图（缓存）
2. **metaflow.yaml** - MetaFlow 中间表示
3. **workflow.yaml** - 最终生成的 Workflow

#### 环境要求

```bash
# 必须设置 Anthropic API Key
export ANTHROPIC_API_KEY=your-api-key-here
```

#### 缓存机制

- 如果 `intent_graph.json` 已存在，会跳过意图提取阶段
- 如果 `expected/intents.json` 存在，会直接使用缓存的意图
- 完全重新生成需删除 output 目录中的缓存文件

---

### 2. run_workflow.py - Workflow 执行器

#### 功能说明

加载并执行已有的 Workflow YAML 文件，支持多种运行模式：

- 运行内置 Workflow
- 运行用户自定义 Workflow
- 运行文件系统中的任意 Workflow YAML
- 测试浏览器会话复用

#### 使用方法

##### 基础用法

```bash
# 1. 进入测试目录
cd tests/integration/workflow

# 2. 列出所有可用的 Workflow
python run_workflow.py --list

# 3. 运行内置 Workflow
python run_workflow.py user-qa-workflow --input user_input="你好"

# 4. 运行文件路径指定的 Workflow（相对路径）
python run_workflow.py ../../test_data/coffee_allegro/output/workflow.yaml --verbose

# 5. 运行文件路径指定的 Workflow（绝对路径）
python run_workflow.py /path/to/workflow.yaml --verbose
```

##### Demo 场景调用

**Allegro 咖啡采集**
```bash
cd tests/integration/workflow

# 基础运行
python run_workflow.py ../../test_data/coffee_allegro/output/workflow.yaml

# 详细输出 + 保存结果
python run_workflow.py ../../test_data/coffee_allegro/output/workflow.yaml \
    --verbose \
    --save
```

**Amazon 咖啡采集**
```bash
cd tests/integration/workflow

python run_workflow.py ../../test_data/coffee_amazon/output/workflow.yaml \
    --verbose \
    --save
```


##### 高级用法

```bash
# 1. 指定 LLM 提供商和模型
python run_workflow.py workflow.yaml \
    --llm-provider anthropic \
    --llm-model claude-3-5-sonnet-20241022 \
    --verbose

# 2. 使用自定义配置文件
python run_workflow.py workflow.yaml \
    --config /path/to/config.yaml \
    --verbose

# 3. 传递 JSON 输入数据
python run_workflow.py workflow.yaml \
    --json '{"max_items": 10, "target_url": "https://example.com"}'

# 4. 传递键值对输入
python run_workflow.py workflow.yaml \
    --input key1=value1 \
    --input key2=value2

# 5. 测试浏览器会话复用
python run_workflow.py --test-reuse workflow_a.yaml workflow_b.yaml
```

#### 命令行参数

**输入选项**
- `--input, -i`: 键值对输入（可多次使用）
- `--json, -j`: JSON 格式输入

**Workflow 特定参数**
- `--url`: 爬虫目标 URL
- `--max-pages`: 最大页面数
- `--products-per-page`: 每页产品数

**配置选项**
- `--config, -c`: 配置文件路径
- `--llm-provider`: LLM 提供商（openai, anthropic）
- `--llm-model`: LLM 模型名称
- `--user-id`: 用户 ID（用于内存隔离）

**输出选项**
- `--save, -s`: 保存结果到 JSON 文件
- `--verbose, -v`: 详细日志输出

**特殊命令**
- `--list`: 列出所有可用 Workflow
- `--test-reuse`: 测试浏览器会话复用

#### 环境要求

```bash
# 根据使用的 LLM 提供商设置 API Key
export OPENAI_API_KEY=your-openai-key
# 或
export ANTHROPIC_API_KEY=your-anthropic-key
```

#### 输出结果

执行成功后会输出：
- 实时执行日志
- 各步骤执行状态
- 最终结果数据
- 可选：JSON 结果文件（`--save` 参数）

---

## 常见使用场景

### 场景 1: 开发新的 Workflow

```bash
# Step 1: 录制用户操作，保存到 user_operations.json
# （通过浏览器插件或手动编写）

# Step 2: 生成 Workflow
cd tests/integration/intent_builder
TEST_NAME=my_new_scenario python test_end_to_end.py

# Step 3: 运行生成的 Workflow
cd ../workflow
python run_workflow.py ../../test_data/my_new_scenario/output/workflow.yaml --verbose
```

### 场景 2: 测试现有 Workflow

```bash
# 直接运行 Workflow 并查看结果
cd tests/integration/workflow
python run_workflow.py ../../test_data/coffee_allegro/output/workflow.yaml \
    --verbose \
    --save
```

### 场景 3: 调试 Workflow 问题

```bash
# 1. 启用详细日志
cd tests/integration/workflow
python run_workflow.py workflow.yaml --verbose

# 2. 检查生成过程
cd ../intent_builder
rm -rf ../../test_data/coffee_allegro/output/*
pytest test_end_to_end.py -v -s

# 3. 查看中间产物
cat ../../test_data/coffee_allegro/output/metaflow.yaml
cat ../../test_data/coffee_allegro/output/workflow.yaml
```

### 场景 4: 修改 Workflow 配置

```bash
# 1. 修改生成的 workflow.yaml（手动编辑）
vim tests/test_data/coffee_allegro/output/workflow.yaml

# 示例：修改 max_items 限制
# 在 extract-product-urls 步骤的 inputs 中添加：
#   max_items: 10

# 2. 运行修改后的 Workflow
cd tests/integration/workflow
python run_workflow.py ../../test_data/coffee_allegro/output/workflow.yaml --verbose
```

### 场景 5: 批量测试多个场景

```bash
# 创建测试脚本
cat > test_all_scenarios.sh << 'EOF'
#!/bin/bash

scenarios=("coffee_allegro" "coffee_amazon")

for scenario in "${scenarios[@]}"; do
    echo "Testing scenario: $scenario"

    cd tests/integration/workflow
    python run_workflow.py ../../test_data/$scenario/output/workflow.yaml \
        --verbose \
        --save

    if [ $? -eq 0 ]; then
        echo "✅ $scenario passed"
    else
        echo "❌ $scenario failed"
    fi
done
EOF

chmod +x test_all_scenarios.sh
./test_all_scenarios.sh
```

---

## 故障排查

### 问题 1: API Key 未设置

**错误信息**：
```
ANTHROPIC_API_KEY not set and no cached data
```

**解决方案**：
```bash
export ANTHROPIC_API_KEY=your-api-key-here
```

### 问题 2: Workflow 文件未找到

**错误信息**：
```
Failed to load workflow: [Errno 2] No such file or directory
```

**解决方案**：
```bash
# 先生成 Workflow
cd tests/integration/intent_builder
python test_end_to_end.py

# 再运行 Workflow
cd ../workflow
python run_workflow.py ../../test_data/coffee_allegro/output/workflow.yaml
```

### 问题 3: 浏览器依赖未安装

**错误信息**：
```
browser-use 库未安装
```

**解决方案**：
```bash
cd src/base_app
pip install -r requirements.txt
python scripts/install_chromium.py
playwright install chromium --with-deps
```

### 问题 4: 配置文件未找到

**错误信息**：
```
Config file not found
```

**解决方案**：
```bash
# 确保配置文件存在
ls src/base_app/config/baseapp.yaml

# 或者使用环境变量指定
export BASEAPP_CONFIG_PATH=/path/to/baseapp.yaml
```

---

## 目录结构参考

```
tests/
├── test_data/                          # 测试数据目录
│   ├── coffee_allegro/                 # Allegro 咖啡场景
│   │   ├── fixtures/
│   │   │   └── user_operations.json    # 用户操作记录（输入）
│   │   ├── expected/
│   │   │   └── intents.json            # 预期意图（缓存）
│   │   └── output/                     # 生成的输出
│   │       ├── intent_graph.json       # 意图图
│   │       ├── metaflow.yaml           # MetaFlow
│   │       └── workflow.yaml           # Workflow（最终产物）
│   └── coffee_amazon/                  # Amazon 咖啡场景
│
├── integration/
│   ├── intent_builder/
│   │   └── test_end_to_end.py          # Workflow 生成器
│   └── workflow/
│       ├── run_workflow.py             # Workflow 执行器
│       └── README.md
│
└── unit/                               # 单元测试
```

---

## 最佳实践

### 1. 开发流程

```bash
# 1. 录制用户操作
# 2. 生成 Workflow
TEST_NAME=my_scenario python test_end_to_end.py

# 3. 测试 Workflow
python run_workflow.py workflow.yaml --verbose

# 4. 调优参数（修改 workflow.yaml）
# 5. 重新测试
python run_workflow.py workflow.yaml --verbose --save

# 6. 生产部署
```

### 2. 测试优化

- **使用缓存**：重复测试时利用 intent_graph.json 缓存
- **分阶段调试**：先测试生成，再测试执行
- **详细日志**：始终使用 `--verbose` 参数调试问题
- **保存结果**：使用 `--save` 保存执行结果用于分析

### 3. 版本控制

```bash
# 提交的文件
git add tests/test_data/*/fixtures/user_operations.json
git add tests/test_data/*/expected/intents.json

# 不提交的文件（.gitignore）
tests/test_data/*/output/*
```

---

## 相关文档

- [BaseAgent 架构文档](../baseagent/ARCHITECTURE.md)
- [Workflow 开发指南](../baseagent/workflow_development_guide.md)
- [Intent Builder 架构](../agentbuilder/ARCHITECTURE.md)
- [数据库架构](../platform/database_architecture.md)

---

## 更新日志

- **2025-01-20**: 初始版本，包含两个主要测试脚本的使用说明
