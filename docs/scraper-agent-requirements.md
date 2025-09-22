# ScraperAgent 需求文档 v4.0 (双模式版本)

## 1. 概述

ScraperAgent v4.0 是一个基于 browser-use 库的智能爬虫代理，支持**脚本模式**和**大模型模式**两种数据提取方式。脚本模式通过生成可重用的提取脚本实现高效数据提取，大模型模式通过直接分析DOM结构实现灵活的实时提取。

### 1.1 核心目标

- **双模式支持**: 支持脚本模式和大模型模式两种数据提取方式
- **脚本重用性**: 脚本模式实现一次生成、多次使用的高效提取
- **实时适应性**: 大模型模式可实时适应页面变化
- **人性化浏览**: 模拟真实用户的浏览行为和路径导航
- **复杂交互支持**: 处理需要点击、滚动、表单填写等交互的页面
- **动态内容处理**: 支持 JavaScript 渲染的动态网页内容

### 1.2 应用场景

- **电商数据采集**: 产品信息、价格、评价等
- **新闻内容抓取**: 文章标题、正文、发布时间等
- **社交媒体监控**: 用户动态、评论、互动数据
- **招聘信息收集**: 职位信息、公司数据、薪资范围
- **学术研究支持**: 论文信息、引用数据、研究动态

## 2. 功能性需求

### 2.1 工作模式

#### 2.1.1 Initialize 模式（测试提取）

**输入参数:**
```json
{
    "mode": "initialize",
    "sample_path": "string | array<string>",  // 样本页面路径
    "data_requirements": "string",            // 数据需求（逗号分隔字段列表）
    "interaction_steps": "array<object>",     // 可选：页面交互步骤
    "options": {
        "timeout": "number"                   // 超时设置
    }
}
```

**功能要求:**
- 支持单页面和多步骤路径导航
- 自动检测页面加载完成状态
- 处理需要交互才能获取数据的页面（如点击加载更多）
- **脚本模式**: 生成提取脚本并存储到KV，执行测试提取
- **大模型模式**: 直接使用LLM分析DOM进行测试提取
- 支持调试模式保存DOM和脚本文件

#### 2.1.2 Execute 模式（生产提取）

**输入参数:**
```json
{
    "mode": "execute", 
    "target_path": "string | array<string>",  // 目标页面路径
    "data_requirements": "string",            // 数据需求（逗号分隔字段列表）
    "interaction_steps": "array<object>",     // 可选：页面交互步骤
    "options": {
        "max_items": "number",                // 最大提取数量
        "timeout": "number"                   // 执行超时
    }
}
```

**功能要求:**
- **脚本模式**: 从KV加载存储的脚本执行数据提取
- **大模型模式**: 直接使用LLM分析当前DOM进行数据提取
- 执行复杂的页面导航序列
- 处理动态内容加载
- 智能错误恢复和重试
- 数据质量验证和清洗

### 2.2 创建时配置需求

#### 2.2.1 代理创建参数
- **extraction_method**: 提取方法 ('script' 或 'llm')
- **debug_mode**: 调试模式开关 (True/False)
- **模式固定性**: 创建后提取方法不可更改
- **组件初始化**: 自动初始化browser-use核心组件

### 2.3 Browser-Use 集成需求

#### 2.3.1 BrowserSession 管理
- 维护持久化的浏览器会话
- 支持多标签页管理和切换
- 处理浏览器异常和恢复
- 资源优化和内存管理

#### 2.3.2 Controller 动作支持
- **导航动作**: `SearchGoogleAction`, `GoToUrlAction`, `GoBackAction`
- **交互动作**: `ClickElementAction`, `InputTextAction`, `ScrollAction`
- **数据提取**: `ExtractStructuredDataAction`
- **表单操作**: `SelectDropdownOptionAction`, `UploadFileAction`
- **键盘操作**: `SendKeysAction`

#### 2.3.3 DOM Service 集成
- 获取完整的 DOM 树结构
- 提取元素可见性和交互性信息
- 生成元素索引映射
- 支持多帧和 iframe 处理

### 2.4 数据提取模式需求

#### 2.4.1 脚本模式需求
- **Initialize阶段**: 生成Python提取脚本并存储到KV
- **Execute阶段**: 从KV加载脚本并执行提取
- **脚本重用**: 同一脚本可多次执行于不同页面
- **脚本格式**: 包含完整执行环境的Python代码
- **存储键值**: 基于数据需求的MD5哈希生成

#### 2.4.2 大模型模式需求
- **直接提取**: 每次都使用LLM分析DOM结构
- **实时适应**: 可适应页面结构变化
- **JSON输出**: 标准JSON数组格式返回
- **提示优化**: 包含数据要求和DOM结构的完整提示

### 2.5 人性化浏览行为

#### 2.5.1 路径导航模拟
- 按顺序访问路径中的每个 URL
- 模拟用户的页面停留时间
- 添加自然的操作延迟
- 处理页面跳转和重定向

#### 2.5.2 交互行为模拟
- 智能滚动策略（渐进式加载内容）
- 自然的点击和输入操作
- 处理弹窗、模态框等干扰元素
- 模拟用户的浏览习惯

### 2.6 调试和监控需求

#### 2.6.1 调试模式需求
- **DOM保存**: 调试模式下保存DOM结构到文本文件
- **脚本保存**: 调试模式下保存生成的脚本到Python文件
- **详细日志**: 记录各阶段执行状态和结果
- **文件命名**: 使用时间戳和模式标识的文件名

#### 2.6.2 错误处理需求
- **统一错误格式**: 标准化的错误响应结构
- **详细错误信息**: 包含具体的失败原因和调试信息
- **异常恢复**: 网络异常、页面变更等情况的智能处理
- **超时处理**: 完整的超时控制和错误提示

## 3. 非功能性需求

### 3.1 性能需求

- **响应时间**: 脚本生成 < 60秒，执行 < 30秒/页面
- **并发处理**: 支持至少 10 个并发脚本执行
- **内存占用**: 单个 Agent 实例 < 512MB
- **网络效率**: 最小化不必要的请求和资源下载

### 3.2 可靠性需求

- **成功率**: 常见网站类型 > 90% 数据提取成功率
- **容错能力**: 网络异常、页面变更等情况下的智能恢复
- **数据一致性**: 提取数据的完整性和准确性验证
- **异常处理**: 完整的错误分类和处理机制

### 3.3 可维护性需求

- **脚本版本管理**: 支持脚本的版本控制和回滚
- **监控和日志**: 详细的执行日志和性能监控
- **配置管理**: 灵活的配置参数和环境适配
- **调试支持**: 丰富的调试信息和故障排查工具

### 3.4 安全性需求

- **访问控制**: 支持代理、User-Agent 等反爬措施
- **速率限制**: 智能的请求频率控制
- **数据保护**: 敏感数据的安全处理和存储
- **合规性**: 遵守网站的 robots.txt 和使用条款

## 4. 技术约束

### 4.1 依赖库要求

- **Core**: browser-use >= 2.0
- **LLM**: Anthropic API (主要) 或 OpenAI API
- **DOM 解析**: browser-use 内置 DomService
- **存储**: KV 存储接口 (MemoryManager)
- **异步**: asyncio 异步编程模型
- **执行环境**: Python exec() 动态代码执行

### 4.2 系统环境

- **Python**: >= 3.11
- **浏览器**: Chromium/Chrome (通过 Playwright)
- **内存**: >= 2GB 可用内存
- **网络**: 稳定的互联网连接

### 4.3 兼容性要求

- 支持主流操作系统 (Linux, macOS, Windows)
- 兼容容器化部署 (Docker)
- 支持分布式架构部署

## 5. 接口规范 v4.0

### 5.1 创建时配置接口

```python
class ScraperAgent(BaseStepAgent):
    def __init__(self,
                 metadata: Optional[AgentMetadata] = None,
                 browser_session: Optional[BrowserSession] = None,
                 controller: Optional[Controller] = None,
                 debug_mode: bool = False,
                 extraction_method: str = 'script'):
        """
        创建 ScraperAgent 实例
        
        Args:
            debug_mode: 调试模式开关
            extraction_method: 提取方法 ('script' 或 'llm')
        """
```

### 5.2 输入接口

```python
class ScraperAgentInput(BaseModel):
    mode: Literal["initialize", "execute"]
    sample_path: Union[str, List[str]]  # initialize 模式
    target_path: Union[str, List[str]]  # execute 模式
    data_requirements: str  # 逗号分隔的字段列表
    interaction_steps: Optional[List[InteractionStep]] = []
    options: Optional[ScraperOptions] = ScraperOptions()

class InteractionStep(BaseModel):
    action_type: str  # click, scroll, input, wait
    target_selector: Optional[str]
    parameters: Dict[str, Any]
    description: Optional[str] = None
    
class ScraperOptions(BaseModel):
    max_items: int = 100
    timeout: int = 90
```

### 5.3 输出接口

```python
class ScraperAgentOutput(BaseModel):
    success: bool
    mode: str
    message: str
    extraction_method: str  # 'script' 或 'llm'
    
    # Initialize 模式输出
    test_data: Optional[List[Dict[str, Any]]] = None
    total_count: Optional[int] = None
    
    # Execute 模式输出
    extracted_data: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None
    
    error: Optional[str] = None

class ScraperMetadata(BaseModel):
    total_items: int
    target_path: Union[str, List[str]]
    extraction_method: str
    execution_time: str
```

### 5.4 KV存储接口

```python
class StoredScript(BaseModel):
    script_content: str  # LLM 生成的完整脚本
    data_requirements: str
    created_at: str
    version: str = "4.0"
```

## 6. 质量属性 v4.0

### 6.1 可用性
- **双模式支持**: 用户可根据需求选择脚本或大模型模式
- **调试友好**: 调试模式下提供详细的DOM和脚本文件
- **错误提示**: 清晰的错误信息和调试指导
- **统一接口**: 两种模式使用相同的输入输出格式

### 6.2 可扩展性
- **提取方法**: 可扩展支持更多提取方式
- **LLM提供商**: 支持Anthropic和OpenAI，可扩展其他提供商
- **交互步骤**: 灵活的交互步骤配置和扩展
- **存储后端**: KV存储接口可扩展支持不同后端

### 6.3 可观测性
- **详细日志**: 记录初始化和执行各阶段的状态
- **文件调试**: 调试模式下生成DOM和脚本文件
- **性能监控**: 记录执行时间和提取数据量
- **错误追踪**: 完整的异常和错误堆栈追踪

## 7. 验收标准 v4.0

### 7.1 功能验收
- [ ] **双模式支持**: 脚本模式和大模型模式都能正常工作
- [ ] **脚本重用**: 初始化阶段生成的脚本在执行阶段可重复使用
- [ ] **KV存储**: 脚本可正常存储到KV并从KV加载
- [ ] **大模型提取**: LLM模式可直接提取数据不依赖脚本
- [ ] **调试支持**: 调试模式下可正常生成DOM和脚本文件
- [ ] **交互处理**: 支持点击、滚动、输入等交互操作

### 7.2 性能验收
- [ ] **初始化时间**: < 60秒（包括页面导航和脚本生成）
- [ ] **执行时间**: < 30秒/页面（脚本模式），< 45秒/页面（LLM模式）
- [ ] **数据提取速度**: > 50条/分钟（脚本模式）
- [ ] **内存使用**: 单个实例 < 512MB
- [ ] **资源清理**: 正常结束后无资源泄漏

### 7.3 质量验收
- [ ] **数据准确率**: > 95%（在测试的电商网站上）
- [ ] **脚本生成成功率**: > 90%（常见网站类型）
- [ ] **错误处理**: 网络异常、页面变更等情况下的智能恢复
- [ ] **测试覆盖**: 核心功能测试覆盖率 > 85%
- [ ] **合规性**: 遵守网站robots.txt和使用条款


## 8. 实现总结 v4.0

ScraperAgent v4.0 已成功实现双模式数据提取架构：

### 8.1 核心创新
- **创建时配置**: 在代理创建时确定提取方法和调试模式，后续不可更改
- **脚本模式**: 实现"一次生成，多次使用"的高效提取方案
- **大模型模式**: 提供实时适应的灵活提取能力
- **统一接口**: 两种模式共享相同的API设计

### 8.2 技术特点
- **Browser-Use集成**: 直接使用BrowserSession、Controller、DomService核心组件
- **KV存储**: 脚本持久化存储和加载机制
- **调试友好**: 完整的DOM和脚本文件保存功能
- **错误处理**: 统一的异常处理和恢复策略

### 8.3 应用价值
- **性能优化**: 脚本模式避免重复LLM调用，提高执行效率
- **灵活适应**: 大模型模式可适应页面结构变化
- **开发效率**: 统一的接口设计降低学习和使用成本
- **调试便利**: 调试模式提供详细的执行状态和中间文件

本需求文档v4.0反映了ScraperAgent的最新实现，为智能爬虫的双模式数据提取提供了完整的功能规范和质量标准。