# Ami 开发指南

## 概述

本指南为开发者提供详细的Ami开发说明，包括架构理解、组件开发、最佳实践等。

## 核心架构理解

### 1. BaseAgent 基础框架

BaseAgent是所有定制Agent的基础类，提供标准化接口：

```python
class CustomAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentConfig(name="CustomAgent"))
        # 注册需要的工具
        self.register_tool('browser', BrowserTool())
        self.register_tool('android', AndroidTool())
    
    async def execute(self, input_data: Any, **kwargs) -> AgentResult:
        # 实现具体的Agent逻辑
        result = await self.use_tool('browser', 'navigate', {'url': input_data})
        return AgentResult(success=True, data=result.data)
```

### 2. 工具开发规范

所有工具必须继承BaseTool：

```python
class MyCustomTool(BaseTool):
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="my_tool",
            description="我的自定义工具",
            category="custom"
        )
    
    async def execute(self, action: str, params: Dict[str, Any], **kwargs) -> ToolResult:
        # 实现工具逻辑
        pass
    
    def get_available_actions(self) -> List[str]:
        return ["action1", "action2"]
```

### 3. 项目经理Agent集成

项目经理Agent通过以下方式理解和使用框架：

```python
# 获取BaseAgent能力描述
capabilities = base_agent.get_capabilities()

# 获取工具知识
tool_knowledge = knowledge_base.get_tool_knowledge("browser_use")

# 生成Agent代码
prompt = f"""
基于Ami框架生成Agent:
框架能力: {capabilities}
工具信息: {tool_knowledge}
用户需求: {user_requirements}
"""
generated_code = await claude_code_client.generate_code(prompt)
```

## 开发流程

### Stage 1: 当前阶段

#### 已完成
- [x] 项目架构设计
- [x] BaseAgent基础框架
- [x] 工具系统基础类
- [x] 数据Schema定义
- [x] 目录结构规划

#### 开发中
- [ ] 核心组件实现
- [ ] 工具知识库系统
- [ ] 项目经理Agent
- [ ] Claude Code集成

#### 待开发
- [ ] Web界面
- [ ] API接口
- [ ] 测试覆盖
- [ ] 文档完善

### 开发优先级

1. **高优先级 (Stage 1)**
   - 完善BaseAgent功能
   - 实现工具知识库
   - 开发项目经理Agent
   - Claude Code集成

2. **中优先级 (Stage 2)**
   - Web管理界面
   - API接口开发
   - 测试系统完善
   - 性能优化

3. **低优先级 (Stage 3)**
   - 高级功能
   - 企业级特性
   - 第三方集成

## 代码规范

### 1. 文件结构

```
component/
├── __init__.py          # 模块导出
├── main_module.py       # 主要实现
├── schemas.py           # 数据结构(可选)
├── exceptions.py        # 异常定义(可选)
└── tests/              # 测试文件
    └── test_main.py
```

### 2. 代码风格

- 使用Python 3.9+语法
- 遵循PEP 8代码规范
- 使用类型注解
- 写详细的文档字符串
- 错误处理要完善

### 3. 异步编程

所有IO操作使用async/await：

```python
async def process_data(self, data: str) -> ProcessResult:
    """处理数据 - 异步方法示例"""
    try:
        # 异步IO操作
        result = await self.external_service.process(data)
        return ProcessResult(success=True, data=result)
    except Exception as e:
        logger.error(f"处理失败: {e}")
        return ProcessResult(success=False, error=str(e))
```

## 组件开发指南

### 1. 开发新工具

```python
# 1. 继承BaseTool
class NewTool(BaseTool):
    # 2. 实现必要方法
    # 3. 注册到知识库
    # 4. 编写测试
    # 5. 更新文档
```

### 2. 扩展BaseAgent

```python
# 1. 继承BaseAgent
class SpecializedAgent(BaseAgent):
    # 2. 注册专用工具
    # 3. 实现execute方法
    # 4. 添加专用接口
    # 5. 编写使用示例
```

### 3. 添加新的数据Schema

```python
# 1. 在schemas/目录下定义
# 2. 使用Pydantic BaseModel
# 3. 添加完整的类型注解
# 4. 更新__init__.py导出
```

## 测试策略

### 1. 单元测试

```python
import pytest
from your_module import YourClass

@pytest.mark.asyncio
async def test_your_method():
    instance = YourClass()
    result = await instance.your_method("test_input")
    assert result.success is True
```

### 2. 集成测试

```python
@pytest.mark.asyncio
async def test_agent_workflow():
    agent = TestAgent()
    await agent.initialize()
    
    result = await agent.execute("test_task")
    assert result.success is True
    
    await agent.cleanup()
```

### 3. 测试覆盖率

- 目标：90%+代码覆盖率
- 工具：pytest-cov
- 运行：`pytest --cov=ami --cov-report=html`

## 部署指南

### 1. 本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 安装开发依赖
pip install -r requirements-dev.txt

# 运行测试
pytest

# 启动服务
uvicorn api.main:app --reload
```

### 2. Docker部署

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f ami
```

## 最佳实践

### 1. 错误处理

```python
try:
    result = await risky_operation()
except SpecificException as e:
    logger.error(f"特定错误: {e}")
    return ErrorResult(type="specific", message=str(e))
except Exception as e:
    logger.error(f"未知错误: {e}")
    return ErrorResult(type="unknown", message=str(e))
```

### 2. 日志记录

```python
import logging
logger = logging.getLogger(__name__)

# 不同级别的日志
logger.debug("调试信息")
logger.info("一般信息")
logger.warning("警告信息")
logger.error("错误信息")
logger.critical("严重错误")
```

### 3. 配置管理

```python
from pydantic import BaseSettings

class Settings(BaseSettings):
    database_url: str
    redis_url: str
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"

settings = Settings()
```

## 贡献指南

### 1. 提交流程

1. Fork项目
2. 创建功能分支
3. 编写代码和测试
4. 提交PR
5. 代码审查
6. 合并代码

### 2. 提交规范

```
type(scope): description

feat(agent): 添加新的Agent功能
fix(tool): 修复工具调用Bug  
docs(guide): 更新开发指南
test(core): 添加BaseAgent测试
```

### 3. 代码审查标准

- 功能完整性
- 代码质量
- 测试覆盖率
- 文档完善度
- 性能影响

## 常见问题

### Q: 如何添加新的工具？
A: 继承BaseTool，实现必要方法，注册到知识库，编写测试。

### Q: 如何扩展BaseAgent？
A: 继承BaseAgent，重写execute方法，注册专用工具。

### Q: 如何集成外部AI服务？
A: 参考claude_integration模块，实现标准化的客户端接口。

### Q: 如何调试Agent执行过程？
A: 使用内置的日志系统和执行历史记录功能。

## 相关资源

- [架构设计文档](../ARCHITECTURE.md)
- [API参考文档](../api/README.md)
- [示例代码](../../examples/)
- [测试指南](./TESTING_GUIDE.md)

---

如有问题，请提交Issue或联系开发团队。