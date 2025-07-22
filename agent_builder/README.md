# AgentBuilder - 智能Agent生成系统

基于自然语言描述自动生成BaseAgent兼容的Python代码和工作流配置。使用先进的LLM技术和Context Engineering原则，实现成本效益最优化的Agent构建。

## 🎯 项目概述

AgentBuilder是一个革命性的AI Agent开发工具，能够将用户的自然语言需求描述转换为完整的、可执行的AI Agent代码。系统遵循最优控制理论，自动选择最经济高效的实现方案。

### 核心特性

- 🧠 **智能需求解析** - 使用LLM深度理解用户需求
- 🎯 **成本效益优化** - 基于工具能力矩阵进行智能决策
- 🔧 **自动工作流构建** - 生成BaseAgent兼容的YAML工作流
- 💻 **Python代码生成** - 直接输出完整的可执行Python文件
- 📚 **完整文档生成** - 自动生成README、测试和依赖文件
- 🗄️ **数据库集成** - 完整的构建过程追踪和存储

## 🔄 工作流程总览

AgentBuilder采用10步构建流程，每个步骤产生特定的中间产物：

### 构建步骤详解

1. **智能需求解析** → `ParsedRequirement` 对象
2. **步骤提取** → `List[StepDesign]` 执行步骤列表
3. **Agent类型判断** → `Dict[str, str]` 类型优化映射
4. **StepAgent生成** → `List[Dict]` Agent规格列表
5. **工作流构建** → BaseAgent `Workflow` 对象
6. **代码生成** → `GeneratedCode` 完整代码包
7. **文件保存** → 结构化文件夹 `agent_{id}/`
8. **代码测试** → 语法和结构验证报告
9. **构建报告** → 完整构建摘要
10. **数据库存储** → 持久化所有构建数据

## 🏗️ 系统架构

### 核心组件

```
AgentBuilder (主控制器)
├── RequirementParser      # 需求解析器
├── ToolCapabilityAnalyzer # 工具能力分析器  
├── AgentDesigner          # Agent设计器
├── WorkflowBuilder        # 工作流构建器
└── CodeGenerator          # 代码生成器
```

### 设计原则

1. **Context Engineering优化** - 精心设计LLM提示词，确保最佳结果
2. **最优控制理论** - 成本最小化：复用现有工具 > 组合工具 > 实现新工具
3. **BaseAgent集成** - 生成的Agent完全兼容BaseAgent框架

## 🚀 快速开始

### 安装

```bash
# 确保Python 3.8+
pip install pydantic>=2.0.0 pyyaml>=6.0 openai anthropic
```

### 基本使用

```python
import asyncio
from agent_builder import build_agent

async def main():
    result = await build_agent(
        description="创建一个智能问答助手，能够理解用户问题并提供准确回答",
        api_key="your-openai-api-key",
        provider="openai"
    )
    
    if result["success"]:
        print(f"✅ Agent创建成功!")
        print(f"📁 文件路径: {result['files']['agent_file']}")
        print(f"💰 成本分析: {result['agent_info']['cost_analysis']}")
    else:
        print("❌ 创建失败")

if __name__ == "__main__":
    asyncio.run(main())
```

### 高级使用

```python
from agent_builder import AgentBuilder, LLMConfig

# 配置LLM
llm_config = LLMConfig(
    provider="anthropic",
    model="claude-3-sonnet-20240229",
    api_key="your-anthropic-key"
)

# 创建构建器
builder = AgentBuilder(llm_config)

# 构建Agent
result = await builder.build_agent_from_description(
    user_description="""
    创建一个数据分析专家，能够：
    1. 理解数据分析需求
    2. 生成Python分析代码
    3. 创建可视化图表
    4. 提供分析结论
    """,
    output_dir="./my_agents",
    agent_name="data_analysis_expert"
)

# 查看构建摘要
summary = builder.get_build_summary(result)
print(summary)
```

## 📁 项目结构

```
agent_builder/
├── core/                          # 核心实现
│   ├── schemas.py                 # 数据结构定义
│   ├── requirement_parser.py      # 需求解析器
│   ├── tool_capability_analyzer.py # 工具能力分析
│   ├── agent_designer.py          # Agent设计器
│   ├── workflow_builder.py        # 工作流构建器
│   ├── code_generator.py          # 代码生成器
│   └── agent_builder.py           # 主控制器
├── examples/                      # 使用示例
│   └── usage_example.py          # 详细使用示例
├── tests/                         # 测试套件
│   └── test_agent_builder.py     # 单元测试
├── __init__.py                    # 模块入口
└── README.md                      # 本文档
```

## 🔧 生成的Agent结构

AgentBuilder生成的每个Agent包含完整的项目结构：

### 文件清单
```
agent_{agent_id}/
├── agent.py              # 主Agent实现代码（包含CLI入口）
├── config.json           # Agent配置文件
├── workflow.yaml         # BaseAgent工作流配置
├── metadata.json         # Agent元数据和能力描述
├── README.md             # 详细使用说明和示例
└── requirements.txt      # Python依赖包列表
```

### 数据库存储
所有构建数据都存储在 `AgentBuild` 表中：
- `build_id` - 唯一构建标识符
- `agent_purpose` - Agent目的和功能描述
- `generated_code` - 完整的Python Agent代码
- `workflow_data` - BaseAgent工作流JSON数据
- `steps_data` - 执行步骤的详细信息
- `step_agents_data` - StepAgent规格数据
- `agent_types_data` - Agent类型优化结果

### Agent代码结构
生成的Agent具备完整的CLI功能和BaseAgent集成：

```python
#!/usr/bin/env python3
class Agent_Generated(BaseAgent):
    """由AgentBuilder自动生成的Agent"""
    
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.workflow = None
        self.workflow_name = "custom_workflow"
    
    async def initialize(self):
        """初始化Agent和工作流"""
        await super().initialize()
        await self._setup_workflow()
    
    async def _setup_workflow(self):
        """设置BaseAgent工作流"""
        builder = self.create_workflow_builder("工作流名称", "工作流描述")
        
        # 自动生成的工作流步骤（基于用户需求）
        builder.add_text_step(name="步骤1", instruction="处理用户输入")
        builder.add_tool_step(name="步骤2", instruction="调用外部工具", tools=["browser_use"])
        builder.add_code_step(name="步骤3", instruction="生成分析代码")
        
        self.workflow = builder.build()
    
    async def execute(self, input_data: Any) -> AgentResult:
        """执行Agent主要功能"""
        if not self.workflow:
            await self._setup_workflow()
        
        # 包装输入数据为字典格式
        workflow_input = {"user_input": input_data} if not isinstance(input_data, dict) else input_data
        result = await self.run_custom_workflow(self.workflow, workflow_input)
        
        return AgentResult(
            success=True, 
            data=result, 
            agent_name=self.config.name,
            execution_time=0.0
        )

# 完整的CLI入口支持
def main():
    parser = argparse.ArgumentParser(description="Generated Agent")
    parser.add_argument('--input', help='输入数据')
    parser.add_argument('--interactive', action='store_true', help='交互模式')
    parser.add_argument('--api-key', help='API密钥')
    parser.add_argument('--config', help='配置文件路径')
    
    # 支持配置文件加载和环境变量
    # 支持交互模式和单次执行模式
    # 完整的错误处理和输出格式化

if __name__ == "__main__":
    main()
```

## 🎨 使用示例

### 1. 问答助手
```python
result = await build_agent(
    description="创建一个友好的问答助手",
    api_key="your-key"
)
```

### 2. 数据分析师
```python
result = await build_agent(
    description="""
    创建数据分析专家，能够：
    1. 读取CSV/Excel文件
    2. 执行数据清洗和预处理
    3. 生成统计分析报告
    4. 创建可视化图表
    """,
    api_key="your-key"
)
```

### 3. 代码审查员
```python
result = await build_agent(
    description="""
    创建代码审查助手，功能包括：
    1. 分析代码质量和结构
    2. 识别潜在的bug和安全问题
    3. 提供重构建议
    4. 检查代码规范遵循情况
    """,
    api_key="your-key"
)
```

### 4. 翻译专家
```python
result = await build_agent(
    description="""
    创建专业翻译Agent：
    1. 自动检测源语言
    2. 提供高质量中英互译
    3. 保持原文语调和风格
    4. 处理专业术语翻译
    """,
    api_key="your-key"
)
```

## 🧪 测试

运行测试套件：

```bash
cd agent_builder/tests
python test_agent_builder.py
```

运行示例：

```bash
cd agent_builder/examples
python usage_example.py
```

## 📊 成本优化策略

AgentBuilder遵循最优控制理论，自动选择成本最低的实现方案：

### 决策优先级
1. **复用现有工具** (成本最低)
   - 使用BaseAgent内置的text_agent、tool_agent、code_agent

2. **组合现有工具** (中等成本)
   - 将多个现有工具组合使用

3. **实现新工具** (成本最高)
   - 只在必要时才生成自定义工具代码

### 工具能力矩阵
- **browser_use**: 网页操作和数据提取
- **android_use**: 移动设备自动化
- **llm_extract**: 文本分析和处理

## 🔍 技术特性

### Context Engineering
- 精心设计的LLM提示词，包含完整的工具能力信息
- 基于成本效益分析的决策框架
- 多轮优化的代码生成过程

### 智能分析
- 自动识别Agent类型需求
- 智能工具选择和组合
- 工作流复杂度评估

### 代码质量
- 自动语法检查和修复
- BaseAgent接口兼容性验证
- 完整的错误处理和日志记录

## 🔧 配置选项

### LLM配置
```python
llm_config = LLMConfig(
    provider="openai",          # openai | anthropic
    model="gpt-4o",             # 模型名称
    api_key="your-key",         # API密钥
    temperature=0.7,            # 生成温度
    max_tokens=4000             # 最大token数
)
```

### 构建选项
```python
result = await builder.build_agent_from_description(
    user_description="需求描述",
    output_dir="./agents",      # 输出目录
    agent_name="my_agent"       # Agent名称
)
```

## 📈 性能优化

### 缓存机制
- LLM响应缓存
- 工具能力分析缓存
- 代码模板缓存

### 并行处理
- 异步LLM调用
- 并行文件生成
- 批量Agent创建支持

## 🛠️ 扩展开发

### 添加新的LLM提供商
```python
# 在code_generator.py中添加新提供商支持
if self.llm_config.provider == "new_provider":
    # 初始化新提供商客户端
    pass
```

### 自定义工具能力
```python
# 在tool_capability_analyzer.py中添加新工具
self.existing_tools["new_tool"] = ToolCapability(
    name="new_tool",
    description="新工具描述",
    category="category",
    actions=["action1", "action2"],
    # ...
)
```

## 🤝 贡献指南

1. Fork项目仓库
2. 创建特性分支：`git checkout -b feature/new-feature`
3. 提交更改：`git commit -am 'Add new feature'`
4. 推送到分支：`git push origin feature/new-feature`
5. 创建Pull Request

## 📄 许可证

本项目采用MIT许可证 - 详见LICENSE文件

## 👥 团队

- **AgentCrafter Team** - 初始开发和维护

## 🆘 支持

如有问题或建议，请：
- 提交GitHub Issue
- 查看文档和示例
- 联系开发团队

---

**AgentBuilder** - 让AI Agent开发变得简单而高效！ 🚀