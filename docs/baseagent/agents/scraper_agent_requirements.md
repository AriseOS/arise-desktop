# ScraperAgent 需求文档 v5.0 (简化版本)

## 1. 概述

ScraperAgent v5.0 是一个基于 browser-use 库的智能爬虫代理，支持**脚本模式**和**LLM模式**两种数据提取方式。

### 1.1 核心目标

- **双模式支持**: 支持脚本模式和LLM模式两种数据提取方式
- **自动脚本管理**: 脚本模式自动检查KV缓存，无需手动区分初始化/执行阶段
- **DOM范围控制**: LLM模式仅支持partial DOM，脚本模式支持partial/full DOM
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

### 2.1 统一工作模式

**输入参数:**
```json
{
    "target_path": "string | array<string>",     // 目标页面路径
    "data_requirements": "dict",                 // 数据需求（字典格式）
    "extraction_method": "script | llm",         // 提取方法
    "dom_scope": "partial | full",               // DOM范围（仅script模式支持full）
    "interaction_steps": "array<object>",        // 可选：页面交互步骤
    "options": {
        "max_items": "number",                   // 最大提取数量
        "timeout": "number",                     // 执行超时
        "debug_mode": "boolean"                  // 调试模式
    }
}
```

**data_requirements 格式:**
```json
{
    "user_description": "string",                // 数据提取需求描述
    "output_format": {                           // 输出字段定义
        "field_name": "field_description"
    },
    "sample_data": []                            // 可选：样例数据
}
```

**功能要求:**
- 支持单页面和多步骤路径导航
- 自动检测页面加载完成状态
- 处理需要交互才能获取数据的页面（如点击加载更多）
- **脚本模式**: 自动检查KV缓存，无缓存则生成脚本并存储
- **LLM模式**: 直接使用LLM分析DOM进行数据提取（仅支持partial DOM）
- 支持调试模式保存DOM和脚本文件

### 2.2 运行时配置

#### 2.2.1 配置参数
- **extraction_method**: 提取方法 ('script' 或 'llm')，默认 'llm'
- **dom_scope**: DOM范围 ('partial' 或 'full')，默认 'partial'
  - LLM模式强制使用 'partial'
  - script模式支持 'partial' 和 'full'
- **debug_mode**: 调试模式开关，默认 False
- **配置灵活性**: 每次调用时可通过输入参数覆盖默认配置

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
- **Token优化**: 脚本生成始终使用 partial DOM，大幅降低 token 消耗
- **自动脚本管理**: 首次调用自动生成脚本并存储到KV，后续调用直接使用缓存
- **KV缓存检查**: 基于数据需求生成唯一key（不包含dom_scope）
- **脚本重用**: 同一脚本可多次执行于不同页面
- **脚本格式**: 包含完整执行环境的Python代码
- **执行灵活性**:
  - 生成阶段：强制使用 partial DOM（节省token）
  - 执行阶段：支持 partial 或 full DOM（根据配置）

#### 2.4.2 LLM模式需求
- **直接提取**: 每次都使用LLM分析DOM结构
- **实时适应**: 可适应页面结构变化
- **JSON输出**: 标准JSON数组格式返回
- **DOM限制**: 仅支持 partial DOM（强制）
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

## 5. 接口规范 v5.0

### 5.1 创建时配置接口

```python
class ScraperAgent(BaseStepAgent):
    def __init__(self,
                 config_service=None,
                 metadata: Optional[AgentMetadata] = None,
                 extraction_method: str = 'llm',
                 dom_scope: str = 'partial',
                 debug_mode: bool = False):
        """
        创建 ScraperAgent 实例

        Args:
            config_service: 配置服务
            metadata: Agent元数据
            extraction_method: 默认提取方法 ('script' 或 'llm')
            dom_scope: 默认DOM范围 ('partial' 或 'full')
            debug_mode: 默认调试模式
        """
```

### 5.2 输入接口

```python
class ScraperAgentInput(BaseModel):
    target_path: Union[str, List[str]]  # 目标页面路径
    data_requirements: Dict  # 数据需求（字典格式）
    extraction_method: Optional[str] = None  # 运行时覆盖
    dom_scope: Optional[str] = None  # 运行时覆盖
    debug_mode: Optional[bool] = None  # 运行时覆盖
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
    message: str
    extraction_method: str  # 'script' 或 'llm'

    # 数据输出
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
    data_requirements: Dict  # 数据需求字典
    dom_config: Dict  # DOM配置
        # generation_dom_scope: "partial" (始终partial)
        # execution_dom_scope: "partial" | "full" (记录首次执行时的配置)
    created_at: str
    version: str = "7.1"

# 注意：script key 仅基于 data_requirements，不包含 dom_scope
# 因为脚本生成始终使用 partial DOM，生成的脚本是通用的
```

## 6. 质量属性 v5.0

### 6.1 可用性
- **自动化**: 脚本模式自动管理KV缓存，无需手动区分阶段
- **灵活配置**: 运行时可覆盖默认配置
- **调试友好**: 调试模式下提供详细的DOM和脚本文件
- **错误提示**: 清晰的错误信息和调试指导

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

## 7. 验收标准 v5.0

### 7.1 功能验收
- [ ] **双模式支持**: 脚本模式和LLM模式都能正常工作
- [ ] **自动脚本管理**: 脚本模式自动检查KV缓存并生成/复用脚本
- [ ] **KV存储**: 脚本可正常存储到KV并从KV加载
- [ ] **LLM模式限制**: LLM模式自动强制使用partial DOM
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


## 8. 实现总结 v5.0

ScraperAgent v5.0 简化了工作模式，提供更自动化的使用体验：

### 8.1 核心改进
- **自动脚本管理**: 移除init/execute模式区分，自动检查KV缓存
- **Token优化**: 脚本生成强制使用partial DOM，大幅降低成本
- **运行时配置**: 支持灵活的运行时参数覆盖
- **DOM范围控制**: LLM模式强制partial，脚本模式生成用partial、执行可用full
- **统一接口**: 单一的execute入口，简化调用流程

### 8.2 技术特点
- **Browser-Use集成**: 直接使用BrowserSession、Controller、DomService核心组件
- **KV自动缓存**: 脚本基于data_requirements自动缓存（不含dom_scope）
- **智能DOM选择**: 生成用partial（省token），执行支持full（获取隐藏数据）
- **调试友好**: 完整的DOM和脚本文件保存功能
- **错误处理**: 统一的异常处理和恢复策略

### 8.3 应用价值
- **使用简单**: 无需区分阶段，自动管理脚本生命周期
- **成本优化**: 脚本生成强制partial DOM，token消耗降低50-80%
- **性能优化**: 脚本模式自动复用，避免重复LLM调用
- **灵活配置**: 运行时可随时调整提取策略
- **调试便利**: 调试模式提供详细的执行状态和中间文件

本需求文档v5.0反映了ScraperAgent的简化设计和token优化策略，为智能爬虫提供了更自动化、经济、易用的功能规范。