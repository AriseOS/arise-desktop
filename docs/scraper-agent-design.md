# ScraperAgent 设计文档 v4.0

## 1. 系统架构设计

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    ScraperAgent v4.0                       │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │   Initialize    │  │    Execute      │  │ Extraction   │ │
│  │     Phase       │  │     Phase       │  │   Methods    │ │
│  │ (Generate &     │  │ (Load & Run)    │  │ (Script/LLM) │ │
│  │  Store Script)  │  │                 │  │              │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ Script Storage  │  │ DOM Analysis    │  │ LLM Provider │ │
│  │ (KV Manager)    │  │   Service       │  │ (Anthropic)  │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    Browser-Use Library                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ BrowserSession  │  │   Controller    │  │ DomService   │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 核心组件

#### 1.2.1 ScraperAgent 主类
继承自 BaseStepAgent，支持两种数据提取模式：
- **创建时配置**: 在构造函数中设置 `extraction_method` ('script' 或 'llm') 和 `debug_mode`
- **双模式支持**: 脚本模式和大模型直接提取模式

#### 1.2.2 数据提取模式

**脚本模式 (Script Mode):**
- **Initialize**: 生成Python脚本并存储到KV
- **Execute**: 从KV加载脚本执行（可多次复用）
- **优势**: 一次生成，多次使用，性能高效

**大模型模式 (LLM Mode):**
- **Initialize**: 直接使用LLM分析DOM提取测试数据  
- **Execute**: 每次都使用LLM分析DOM并提取数据
- **优势**: 无需生成脚本，适应性强

#### 1.2.3 核心服务组件
- **DOM Analysis Service**: 基于 browser-use DomService 分析页面结构
- **KV Storage Manager**: 脚本持久化存储和管理
- **Navigation Service**: 页面导航和交互步骤执行
- **Debug Service**: 调试模式下的DOM和脚本文件保存

## 2. 详细设计

### 2.1 ScraperAgent 主类设计

```python
class ScraperAgent(BaseStepAgent):
    """Browser-use v4.0 智能爬虫代理 - 支持脚本和LLM双模式"""
    
    def __init__(self, 
                 metadata: Optional[AgentMetadata] = None,
                 browser_session: Optional[BrowserSession] = None,
                 controller: Optional[Controller] = None,
                 debug_mode: bool = False,
                 extraction_method: str = 'script'):
        """
        初始化 ScraperAgent
        
        Args:
            metadata: 代理元数据
            browser_session: browser-use BrowserSession 实例
            controller: browser-use Controller 实例
            debug_mode: 调试模式开关
            extraction_method: 提取方法 ('script' 或 'llm')
        """
        super().__init__(metadata)
        
        # 配置参数 - 创建时确定，后续不可更改
        self.debug_mode = debug_mode
        self.extraction_method = extraction_method
        
        # 验证提取方法
        if extraction_method not in ['script', 'llm']:
            raise ValueError(f"不支持的提取方法: {extraction_method}")
        
        # 直接使用 browser-use 核心组件
        self.browser_session = browser_session or self._create_browser_session()
        self.controller = controller or Controller()
        self.dom_service = DomService(self.browser_session)
        
    async def execute(self, input_data: Any, context: AgentContext) -> Any:
        """执行代理任务"""
        mode = input_data.get('mode')
        
        if mode == 'initialize':
            return await self._handle_initialize(input_data, context)
        elif mode == 'execute':
            return await self._handle_execute(input_data, context)
        else:
            raise ValueError(f"不支持的模式: {mode}")
```

### 2.2 核心模式处理

#### 2.2.1 Initialize 模式处理 (简化的统一流程)

```python
async def _handle_initialize(self, input_data: Dict, context: AgentContext) -> Dict:
    """初始化模式: 访问样本页面并使用配置的方法提取数据"""
    sample_path = input_data['sample_path']
    data_requirements = input_data['data_requirements']
    interaction_steps = input_data.get('interaction_steps', [])
    
    try:
        # 执行页面导航和交互
        navigate_result = await self._navigate_to_pages(sample_path, interaction_steps)
        
        if navigate_result.success is False:
            return self._create_response(
                False, 'initialize', '页面导航失败',
                error=navigate_result.error
            )
        
        # 获取DOM数据并调用对应的提取方法
        extraction_result = await self._extract_data_from_current_page(
            data_requirements, 
            max_items=10,  # 初始化阶段只测试提取少量数据
            timeout=30,
            context=context,
            is_initialize=True  # 标识为初始化阶段
        )
        
        # 返回结果
        if extraction_result["success"]:
            return self._create_response(
                True, 'initialize', 
                f'初始化成功，使用{self.extraction_method}模式提取了{extraction_result["total_count"]}条测试数据',
                extraction_method=self.extraction_method,
                test_data=extraction_result["data"],
                total_count=extraction_result["total_count"]
            )
        else:
            return self._create_response(
                False, 'initialize', f'初始化失败，{self.extraction_method}模式提取数据失败',
                extraction_method=self.extraction_method,
                error=extraction_result["error"]
            )
            
    except Exception as e:
        logger.error(f"Initialize 模式执行失败: {e}")
        return self._create_response(
            False, 'initialize', '初始化失败',
            error=str(e)
        )

#### 2.2.2 Execute 模式处理 (简化的统一流程)

```python
async def _handle_execute(self, input_data: Dict, context: AgentContext) -> Dict:
    """执行模式: 访问目标页面并使用配置的方法提取数据"""
    target_path = input_data['target_path']
    data_requirements = input_data['data_requirements']
    interaction_steps = input_data.get('interaction_steps', [])
    
    try:
        # 提取执行参数
        options = input_data.get('options', {})
        max_items = options.get('max_items', 100)
        timeout = options.get('timeout', 90)
        
        # 导航到目标页面并执行交互
        navigate_result = await self._navigate_to_pages(target_path, interaction_steps)
        
        if navigate_result.success is False:
            return self._create_response(
                False, 'execute', '无法访问目标页面',
                error=f'页面导航失败: {navigate_result.error}'
            )
        
        # 获取DOM数据并调用对应的提取方法
        extraction_result = await self._extract_data_from_current_page(
            data_requirements, 
            max_items,
            timeout,
            context=context,
            is_initialize=False  # 标识为执行阶段
        )
        
        # 返回执行结果
        if extraction_result["success"]:
            return self._create_response(
                True, 'execute', 
                f'成功提取{extraction_result["total_count"]}条数据，使用{self.extraction_method}模式',
                extraction_method=self.extraction_method,
                extracted_data=extraction_result["data"],
                metadata={
                    'total_items': extraction_result["total_count"],
                    'target_path': target_path,
                    'extraction_method': self.extraction_method,
                    'execution_time': datetime.now().isoformat()
                }
            )
        else:
            return self._create_response(
                False, 'execute', f'数据提取失败，{self.extraction_method}模式',
                extraction_method=self.extraction_method, 
                error=extraction_result["error"]
            )
            
    except Exception as e:
        logger.error(f"Execute 模式执行失败: {e}")
        return self._create_response(
            False, 'execute', '数据提取失败',
            error=str(e)
        )
```

### 2.3 核心提取逻辑设计

#### 2.3.1 统一提取入口

```python
async def _extract_data_from_current_page(
    self, 
    data_requirements: str, 
    max_items: int,
    timeout: int,
    context: Optional[AgentContext] = None,
    is_initialize: bool = False
) -> Dict[str, Any]:
    """从当前页面提取数据的统一入口"""
    
    try:
        # Get current page DOM structure
        serialized_dom, enhanced_dom, timing = await self.dom_service.get_serialized_dom_tree()
        
        # 调试模式: 保存DOM结构
        if self.debug_mode:
            logger.info("=== DOM 结构分析 ===")
            dom_representation = serialized_dom.llm_representation()
            logger.info(f"DOM元素总数: {len(serialized_dom.selector_map)}")
            
            # 保存DOM到文件
            debug_key = f"extraction_{self.extraction_method}_{int(time.time())}"
            await self._save_dom_to_file(dom_representation, debug_key)
        
        # 根据配置的提取方法调用对应函数
        if self.extraction_method == 'script':
            # 脚本模式：根据阶段决定是生成还是加载脚本
            return await self._extract_with_script(
                serialized_dom, enhanced_dom, data_requirements, max_items, timeout, context, is_initialize
            )
        else:
            # LLM模式：直接使用大模型提取
            return await self._extract_with_llm(
                serialized_dom, enhanced_dom, data_requirements, max_items, timeout
            )
            
    except Exception as e:
        logger.error(f"数据提取失败: {e}")
        return self._create_error_result(str(e))
```

#### 2.3.2 脚本模式提取逻辑

```python
async def _extract_with_script(
    self,
    serialized_dom,
    enhanced_dom, 
    data_requirements: str,
    max_items: int,
    timeout: int,
    context: Optional[AgentContext] = None,
    is_initialize: bool = False
) -> Dict[str, Any]:
    """使用脚本模式提取数据"""
    try:
        script_key = self._generate_script_key(data_requirements)
        
        if is_initialize:
            # init阶段：生成脚本并存储到KV
            dom_analysis = {
                'serialized_dom': serialized_dom,
                'enhanced_dom': enhanced_dom
            }
            
            generated_script = await self._generate_extraction_script_with_llm(
                dom_analysis, data_requirements, [], None
            )
            
            # 存储脚本到KV
            if context and context.memory_manager:
                script_data = {
                    "script_content": generated_script,
                    "data_requirements": data_requirements,
                    "created_at": datetime.now().isoformat(),
                    "version": "4.0"
                }
                await context.memory_manager.set_data(script_key, script_data)
                logger.info(f"脚本已存储到KV，键值: {script_key}")
            
            # 调试模式: 保存到文件
            if self.debug_mode:
                logger.info("=== init阶段生成脚本 ===")
                await self._save_script_to_file(generated_script, script_key)
            
            # init阶段也执行一次测试
            return await self._execute_generated_script_direct(
                generated_script, serialized_dom, enhanced_dom, max_items
            )
            
        else:
            # exec阶段：从KV获取脚本执行
            if context and context.memory_manager:
                script_data = await context.memory_manager.get_data(script_key)
                if script_data and 'script_content' in script_data:
                    generated_script = script_data['script_content']
                    logger.info(f"exec阶段从KV加载脚本，键值: {script_key}")
                    
                    return await self._execute_generated_script_direct(
                        generated_script, serialized_dom, enhanced_dom, max_items
                    )
                else:
                    return self._create_error_result(f"未找到脚本: {script_key}，请先运行init阶段")
            else:
                return self._create_error_result("无法访问KV存储")
        
    except Exception as e:
        logger.error(f"脚本模式提取失败: {e}")
        return self._create_error_result(str(e))
```

#### 2.3.3 大模型模式提取逻辑

```python
async def _extract_with_llm(
    self,
    serialized_dom,
    enhanced_dom,
    data_requirements: str,
    max_items: int,
    timeout: int
) -> Dict[str, Any]:
    """使用大模型直接提取数据"""
    try:
        dom_text = serialized_dom.llm_representation()
        
        # 准备大模型提取的提示
        prompt = f"""
从以下HTML DOM结构中提取数据：

数据要求: {data_requirements}
最大数量: {max_items}

HTML DOM结构:
{dom_text}

请提取符合要求的数据，以JSON数组格式返回，每个对象包含要求的字段。
只返回JSON数组，不要其他文字。
"""
        
        llm_provider = AnthropicProvider()
        response = await llm_provider.generate_response(
            system_prompt="你是数据提取专家，从HTML中提取结构化数据并返回有效的JSON格式。",
            user_prompt=prompt
        )
        
        # 解析JSON响应
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            try:
                extracted_data = json.loads(json_match.group())
                if isinstance(extracted_data, list):
                    limited_data = extracted_data[:max_items] if max_items > 0 else extracted_data
                    return {
                        "success": True,
                        "data": limited_data,
                        "total_count": len(limited_data),
                        "error": None
                    }
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析失败: {e}")
                
        return self._create_error_result("LLM未返回有效的JSON格式")
        
    except Exception as e:
        logger.error(f"LLM模式提取失败: {e}")
        return self._create_error_result(str(e))
```

#### 2.3.4 脚本生成器（简化版）

```python
async def _generate_extraction_script_with_llm(self, 
                                             dom_analysis: Dict, 
                                             data_requirements: str,
                                             interaction_steps: List[Dict],
                                             example_data: Optional[str] = None) -> str:
    """Generate data extraction script using LLM - simplified version"""
    
    try:
        serialized_dom = dom_analysis['serialized_dom']
        dom_text = serialized_dom.llm_representation()
        
        prompt = f"""
基于以下DOM结构生成数据提取脚本：

数据要求: {data_requirements}

DOM结构:
{dom_text}

生成一个完整的Python函数，要求：
1. 函数名为 extract_data_from_page(serialized_dom, enhanced_dom)
2. 返回 List[Dict[str, Any]] 格式的数据
3. 包含错误处理
4. 只返回Python代码，不要其他解释
"""
        
        llm_provider = AnthropicProvider()
        response = await llm_provider.generate_response(
            system_prompt="你是Python代码生成专家，生成高效的数据提取脚本。只返回代码，不要解释。",
            user_prompt=prompt
        )
        
        return self._extract_and_wrap_code(response)
        
    except Exception as e:
        logger.error(f"LLM script generation failed: {e}")
        raise Exception(f"LLM script generation failed: {e}")
```

### 2.4 简化的数据模型

基于当前实现的核心数据结构：

```python
# 创建时配置
class ScraperAgentConfig:
    debug_mode: bool = False
    extraction_method: Literal['script', 'llm'] = 'script'

# 输入数据格式（简化版）
class ScraperInput:
    mode: Literal['initialize', 'execute']
    sample_path: Union[str, List[str]]  # initialize 模式
    target_path: Union[str, List[str]]  # execute 模式  
    data_requirements: str  # 简化为逗号分隔的字段列表
    interaction_steps: List[Dict] = []
    options: Dict[str, Any] = {}  # max_items, timeout 等

# 输出数据格式（统一版）  
class ScraperOutput:
    success: bool
    mode: str
    message: str
    extraction_method: str
    # Initialize 模式特有
    test_data: Optional[List[Dict]] = None
    total_count: Optional[int] = None
    # Execute 模式特有
    extracted_data: Optional[List[Dict]] = None
    metadata: Optional[Dict] = None
    error: Optional[str] = None

# 脚本存储格式（KV存储）
class StoredScript:
    script_content: str  # LLM 生成的完整脚本
    data_requirements: str
    created_at: str
    version: str = "4.0"
```

### 2.5 关键特性

#### 2.5.1 脚本模式优势
- **一次生成，多次使用**: init阶段生成的脚本可以被多个exec调用重复使用
- **性能优化**: 避免每次都调用LLM，执行速度更快
- **脚本持久化**: 脚本存储在KV中，可以跨会话使用
- **调试友好**: 调试模式下保存生成的脚本文件

#### 2.5.2 大模型模式优势
- **无需脚本**: 直接分析DOM结构提取数据
- **适应性强**: 每次都重新分析，适应页面变化
- **简单直接**: 无需初始化阶段，可直接使用
- **灵活配置**: 可以随时调整提取要求

#### 2.5.3 统一设计优势
- **一致的API**: 两种模式使用相同的输入输出接口
- **相同的导航**: 使用统一的页面导航和交互逻辑
- **调试支持**: 两种模式都支持调试模式和DOM结构保存
- **错误处理**: 统一的错误处理和响应格式

### 2.6 辅助方法

```python
def _generate_script_key(self, data_requirements: str) -> str:
    """生成脚本存储key（基于数据需求）"""
    hash_suffix = hashlib.md5(data_requirements.encode()).hexdigest()[:8]
    return f"scraper_script_{hash_suffix}"

async def _save_dom_to_file(self, dom_representation: str, debug_key: str):
    """调试模式：保存DOM结构到文件"""
    if self.debug_mode:
        dom_file = f"debug_dom_{debug_key}.txt"
        with open(dom_file, 'w', encoding='utf-8') as f:
            f.write(dom_representation)
        logger.info(f"DOM结构已保存到: {dom_file}")

async def _save_script_to_file(self, script_content: str, script_key: str):
    """调试模式：保存生成的脚本到文件"""
    if self.debug_mode:
        script_file = f"debug_script_{script_key}.py"
        with open(script_file, 'w', encoding='utf-8') as f:
            f.write(script_content)
        logger.info(f"生成的脚本已保存到: {script_file}")
## 3. 实现要点

### 3.1 双模式架构
- **创建时配置**: 在构造函数中设置 `extraction_method` ('script' 或 'llm') 和 `debug_mode`
- **模式固定性**: 提取方法在创建时确定，后续不可更改
- **统一接口**: 两种模式使用相同的输入输出格式

### 3.2 脚本模式实现
- **Init阶段**: 生成脚本并存储到KV存储中，键值基于数据需求的MD5哈希
- **Exec阶段**: 从KV加载相同的脚本执行，支持多次重复使用
- **脚本格式**: LLM生成包含完整执行环境的Python代码

### 3.3 大模型模式实现
- **直接提取**: 每次都使用LLM分析当前DOM结构并提取数据
- **实时适应**: 无需预生成脚本，可适应页面变化
- **JSON格式**: LLM返回标准JSON数组格式的提取结果

### 3.4 Browser-Use集成
- **核心组件**: 直接使用BrowserSession、Controller、DomService
- **DOM分析**: 通过 `dom_service.get_serialized_dom_tree()` 获取页面结构
- **交互操作**: 通过 `controller.act()` 执行页面交互

### 3.5 调试支持
- **DOM保存**: 调试模式下将DOM结构保存为文本文件
- **脚本保存**: 调试模式下将生成的脚本保存为Python文件
- **详细日志**: 记录各阶段的执行状态和结果

### 3.6 错误处理策略
```python
try:
    # 执行提取逻辑
    result = await self._extract_data_from_current_page(...)
    if result["success"]:
        return self._create_response(True, mode, success_message, **result)
    else:
        return self._create_response(False, mode, fail_message, error=result["error"])
except Exception as e:
    logger.error(f"执行失败: {e}")
    return self._create_response(False, mode, "执行异常", error=str(e))
```

## 4. 测试和验证

### 4.1 测试用例设计
- **脚本模式测试**: 验证init阶段生成脚本，exec阶段加载执行
- **脚本复用测试**: 验证同一脚本可用于不同页面的数据提取
- **调试模式测试**: 验证DOM和脚本文件的正确保存

### 4.2 测试流程
1. **Initialize测试**: 访问样本页面，生成并存储脚本
2. **Execute测试**: 访问目标页面，加载脚本执行提取
3. **复用测试**: 使用相同脚本对不同目标页面进行提取

### 4.3 验证标准
- 脚本生成成功率 > 90%
- 数据提取准确率 > 95%
- 脚本复用成功率 > 90%
- 错误恢复能力验证

本设计文档反映了 ScraperAgent v4.0 的最新实现，支持脚本和LLM双模式数据提取，提供了完整的功能架构和实现指导。