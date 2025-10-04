# Technical Debt Backlog

> 技术债务清理任务清单 - 按优先级和工作量组织
>
> **最后更新**: 2025-01-04
> **预计总工作量**: ~64小时 (2-4周)

---

## 📊 概览统计

| 类别 | 数量 | 优先级 | 预计工作量 |
|------|------|--------|-----------|
| **代码质量** | 6项 | 🔴🟡 | 8h |
| **代码重构** | 3项 | 🟡 | 40h |
| **质量保障** | 4项 | 🔴🟡 | 16h |
| **文档完善** | 1项 | 🟢 | 4h |

**总计**: 14项任务，约 64 小时

---

## 🔥 第1周：快速修复 (8小时)

### 1. 移除 Wildcard Imports
- **优先级**: 🔴 高
- **工作量**: 0.5h
- **文件**: `base_app/base_app/base_agent/agents/scraper_agent.py:20`
- **问题**: `from browser_use.tools.views import *` 污染命名空间

**修改方案**:
```python
# 当前 (line 20)
from browser_use.tools.views import *

# 修改为
from browser_use.tools.views import (
    GoToUrlAction,
    ClickAction,
    InputTextAction,
    ScrollAction,
    ExtractAction,
    # ... 明确列出所有需要的类
)
```

---

### 2. 替换 Print 为 Logger
- **优先级**: 🟡 中
- **工作量**: 2h
- **影响范围**: 139处 print() 调用
- **主要文件**:
  - `base_app/base_app/base_agent/tools/browser_use/enhanced_browser_use.py`
  - `base_app/base_app/base_agent/tools/browser_use/user_behavior/monitor.py`

**修改规则**:
```python
# 修改前
print(f"❌ Failed to set up: {e}")
print(f"🎯 User behavior monitoring started")

# 修改后
logger.error(f"Failed to set up: {e}", exc_info=True)
logger.info("User behavior monitoring started")
```

**批量替换脚本**:
```bash
# 查找所有 print 语句
grep -rn "print(" base_app/base_app/base_agent --include="*.py" > print_statements.txt

# 使用 sed 批量替换（需要根据实际情况调整）
```

---

### 3. 提取配置常量
- **优先级**: 🟡 中
- **工作量**: 1h
- **文件**: 创建 `base_app/base_app/base_agent/agents/scraper_config.py`

**当前硬编码值**:
- `250000` - MAX_DOM_CHARS (scraper_agent.py:655)
- `100` - DOM_EMPTY_THRESHOLD (scraper_agent.py:438)
- `2` - DEFAULT_SLEEP_SECONDS (scraper_agent.py:373)
- `0.5` - BrowserStateRequest 等待时间

**配置文件结构**:
```python
# scraper_config.py
from dataclasses import dataclass

@dataclass
class ScraperConfig:
    """ScraperAgent Configuration"""

    # DOM Processing
    MAX_DOM_CHARS: int = 250_000  # ~140k tokens
    DOM_EMPTY_THRESHOLD: int = 100  # chars

    # Timing
    DEFAULT_SLEEP_SECONDS: float = 2.0
    PAGE_LOAD_WAIT_MIN: float = 0.25
    PAGE_LOAD_WAIT_MAX: float = 5.0

    # Retry
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0

    # LLM
    DEFAULT_MODEL: str = "claude-3-5-sonnet-20241022"
    MAX_TOKENS: int = 4096

    # XPath
    INCLUDE_XPATH_FOR_SCRIPT_MODE: bool = True
    INCLUDE_XPATH_FOR_LLM_MODE: bool = False
```

---

### 4. 设置 Pre-commit Hooks
- **优先级**: 🟡 中
- **工作量**: 0.5h
- **文件**: 创建 `.pre-commit-config.yaml`

**配置内容**:
```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
        args: ['--maxkb=500']

  - repo: https://github.com/psf/black
    rev: 23.12.1
    hooks:
      - id: black
        language_version: python3.11

  - repo: https://github.com/PyCQA/isort
    rev: 5.13.2
    hooks:
      - id: isort
        args: ["--profile", "black"]

  - repo: https://github.com/PyCQA/flake8
    rev: 7.0.0
    hooks:
      - id: flake8
        args: [
          '--max-line-length=120',
          '--ignore=E203,W503'  # black compatibility
        ]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        args: [--ignore-missing-imports, --no-strict-optional]
        additional_dependencies: [types-all]
```

**安装步骤**:
```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files  # 初次运行
```

---

### 5. 测量测试覆盖率
- **优先级**: 🔴 高
- **工作量**: 0.5h
- **目标**: 建立覆盖率基准

**执行步骤**:
```bash
# 1. 安装依赖
pip install coverage pytest-cov

# 2. 运行覆盖率测试
pytest tests/ \
  --cov=base_app/base_app/base_agent \
  --cov-report=html \
  --cov-report=term \
  --cov-report=json

# 3. 查看结果
open htmlcov/index.html  # 查看详细报告
cat coverage.json | jq '.totals.percent_covered'  # 查看总覆盖率

# 4. 生成覆盖率徽章
coverage-badge -o coverage.svg -f
```

**预期结果**:
- 当前估计覆盖率: 40-50%
- 目标覆盖率: >80%
- 差距分析文档: `docs/test_coverage_gap_analysis.md`

---

### 6. 添加 Type Hints
- **优先级**: 🟡 中
- **工作量**: 3.5h
- **影响范围**: 缺少返回类型的函数约 50+

**需要添加类型提示的函数** (scraper_agent.py):
```python
# Line 126: _parse_runtime_config
def _parse_runtime_config(self, input_data: Dict) -> Dict:

# Line 161: _get_user_id
def _get_user_id(self, context: AgentContext) -> str:

# Line 181: _get_kv_storage
def _get_kv_storage(self, context: AgentContext) -> SQLiteKVStorage:

# Line 260: _navigate_to_pages
async def _navigate_to_pages(
    self,
    actions: List[Dict[str, Any]],
    timeout: int
) -> None:

# Line 344: _extract_data_from_current_page
async def _extract_data_from_current_page(
    self,
    data_requirements: Dict[str, Any],
    max_items: int,
    timeout: int
) -> Dict[str, Any]:

# ... 更多函数
```

**Mypy 配置** (`mypy.ini`):
```ini
[mypy]
python_version = 3.11
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = False  # 渐进式启用
ignore_missing_imports = True

[mypy-tests.*]
ignore_errors = True
```

---

## 🔄 第2-3周：代码重构 (40小时)

### 7. 重构 scraper_agent.py (1064行)
- **优先级**: 🟡 中
- **工作量**: 16h
- **目标**: 拆分为 4 个模块

**拆分方案**:

```
base_app/base_app/base_agent/agents/
├── scraper_agent.py              # 核心 Agent 类 (~300行)
│   └── ScraperAgent
│       - __init__()
│       - initialize()
│       - execute()
│       - validate_input()
│
├── scraper/
│   ├── __init__.py
│   ├── config.py                 # 配置类 (~50行)
│   ├── llm_extractor.py         # LLM 提取器 (~250行)
│   │   └── ScraperLLMExtractor
│   │       - _extract_with_llm()
│   │       - _build_extraction_prompt()
│   │       - _parse_llm_json()
│   │
│   ├── script_generator.py       # 脚本生成器 (~300行)
│   │   └── ScraperScriptGenerator
│   │       - _extract_with_script()
│   │       - _generate_script()
│   │       - _execute_generated_script_direct()
│   │
│   └── dom_processor.py          # DOM 处理器 (~150行)
│       └── ScraperDOMProcessor
│           - _get_stable_dom()
│           - _save_dom_to_file()
```

**迁移步骤**:
1. 创建新模块结构 (2h)
2. 提取 LLM 提取逻辑到 `llm_extractor.py` (4h)
3. 提取脚本生成逻辑到 `script_generator.py` (4h)
4. 提取 DOM 处理逻辑到 `dom_processor.py` (2h)
5. 更新 `scraper_agent.py` 主类，组合各模块 (2h)
6. 更新测试和文档 (2h)

---

### 8. 重构 base_agent.py (945行)
- **优先级**: 🟡 中
- **工作量**: 12h
- **目标**: 拆分为 3 个模块

**拆分方案**:

```
base_app/base_app/base_agent/core/
├── base_agent.py                 # 基础 Agent 类 (~300行)
│   └── BaseAgent, BaseStepAgent
│
├── agent_execution.py            # 执行引擎 (~350行)
│   └── AgentExecutionEngine
│       - execute_step()
│       - handle_errors()
│       - manage_timeout()
│
└── agent_state.py                # 状态管理 (~250行)
    └── AgentStateManager
        - save_state()
        - load_state()
        - clean_state()
```

**迁移步骤**:
1. 创建 `agent_execution.py` (4h)
2. 创建 `agent_state.py` (3h)
3. 重构 `base_agent.py` (3h)
4. 更新所有引用 (2h)

---

### 9. 重构 dom_extractor.py (828行)
- **优先级**: 🟢 低
- **工作量**: 12h
- **目标**: 提升可读性和可维护性

**优化方向**:
1. 拆分超长方法 (>100行)
2. 提取重复逻辑到辅助函数
3. 添加更多注释说明算法逻辑
4. 优化 DOM 树遍历性能

---

## ✅ 第4周：质量保障 (16小时)

### 10. 补充单元测试 - ScraperAgent
- **优先级**: 🔴 高
- **工作量**: 6h
- **目标**: 核心方法覆盖率 >80%

**待测试的方法**:
```python
# tests/unit/baseagent/agents/test_scraper_agent.py

class TestScraperAgent:
    def test_parse_runtime_config():
        """测试配置解析"""

    def test_get_user_id_from_context():
        """测试用户ID提取"""

    async def test_extract_with_llm_success():
        """测试 LLM 提取成功场景"""

    async def test_extract_with_llm_empty_dom():
        """测试空 DOM 处理"""

    async def test_extract_with_script_cache_hit():
        """测试脚本缓存命中"""

    async def test_extract_with_script_generation():
        """测试脚本生成"""

    def test_parse_llm_json_valid():
        """测试 JSON 解析成功"""

    def test_parse_llm_json_with_markdown():
        """测试带 markdown 的 JSON"""

    def test_build_extraction_prompt():
        """测试提示词构建"""

    async def test_dom_empty_detection():
        """测试 DOM 为空检测 (len <= 100)"""
```

---

### 11. 补充集成测试 - Workflow Engine
- **优先级**: 🟡 中
- **工作量**: 4h
- **目标**: 边界条件和异常场景覆盖

**测试场景**:
```python
# tests/integration/workflow/test_workflow_edge_cases.py

async def test_foreach_empty_list():
    """测试 foreach 空列表"""

async def test_foreach_nested_loop():
    """测试嵌套 foreach"""

async def test_browser_session_sharing():
    """测试浏览器会话共享"""

async def test_agent_failure_recovery():
    """测试 Agent 失败恢复"""

async def test_workflow_timeout():
    """测试 workflow 超时"""

async def test_variable_chain_complex():
    """测试复杂变量链"""
```

---

### 12. 错误处理测试
- **优先级**: 🔴 高
- **工作量**: 4h
- **目标**: 异常场景全覆盖

**测试点**:
- DOM 为空或损坏
- LLM API 超时/失败
- 浏览器崩溃
- 网络错误
- 内存溢出
- 数据验证失败

---

### 13. 性能基准测试
- **优先级**: 🟡 中
- **工作量**: 2h
- **目标**: 建立性能基线

**基准指标**:
```python
# tests/performance/test_scraper_benchmarks.py

def test_dom_extraction_time():
    """DOM 提取时间 < 2s"""

def test_llm_extraction_time():
    """LLM 提取时间 < 10s"""

def test_script_generation_time():
    """脚本生成时间 < 15s"""

def test_memory_usage():
    """内存使用 < 500MB"""

def test_token_usage():
    """Token 使用 < 150k per page"""
```

---

## 📝 文档完善 (4小时)

### 14. 更新开发文档
- **优先级**: 🟢 低
- **工作量**: 4h

**需要更新的文档**:

1. **代码风格指南** (`docs/CODING_STYLE.md`)
   - Type hints 规范
   - Logger 使用规范
   - 配置管理规范

2. **测试指南** (`docs/TESTING_GUIDE.md`)
   - 单元测试编写规范
   - 集成测试最佳实践
   - Mock 使用指南

3. **重构日志** (`docs/REFACTORING_LOG.md`)
   - 记录所有重构变更
   - API 变更说明
   - 迁移指南

4. **性能优化指南** (`docs/PERFORMANCE.md`)
   - 性能基准数据
   - 优化建议
   - 瓶颈分析

---

## 📋 执行检查清单

### Week 1: 快速修复 ✅
- [ ] 移除 wildcard imports
- [ ] 替换 139 个 print() 为 logger
- [ ] 创建 scraper_config.py
- [ ] 设置 pre-commit hooks
- [ ] 测量测试覆盖率基准
- [ ] 添加关键函数 type hints

### Week 2-3: 代码重构 ✅
- [ ] 重构 scraper_agent.py (4 模块)
- [ ] 重构 base_agent.py (3 模块)
- [ ] 优化 dom_extractor.py

### Week 4: 质量保障 ✅
- [ ] 补充 ScraperAgent 单元测试
- [ ] 补充 Workflow 集成测试
- [ ] 添加错误处理测试
- [ ] 建立性能基准

### 文档完善 ✅
- [ ] 更新代码风格指南
- [ ] 更新测试指南
- [ ] 创建重构日志
- [ ] 创建性能优化指南

---

## 🎯 成功指标

完成所有技术债务清理后，项目应达到：

### 代码质量
- ✅ 无 wildcard imports
- ✅ 无 print() 语句（全部使用 logger）
- ✅ 单文件代码行数 < 500
- ✅ 配置全部提取到配置文件
- ✅ 全部函数有 type hints

### 测试覆盖
- ✅ 单元测试覆盖率 > 80%
- ✅ 集成测试覆盖核心场景
- ✅ 错误场景全覆盖

### 开发体验
- ✅ Pre-commit hooks 自动检查
- ✅ Mypy 类型检查通过
- ✅ 代码格式统一（black + isort）
- ✅ 新人上手文档完善

### 性能指标
- ✅ DOM 提取时间 < 2s
- ✅ LLM 提取时间 < 10s
- ✅ Token 使用优化 30%+

---

## 📌 注意事项

1. **渐进式重构**: 不要一次性重构所有文件，按模块逐步进行
2. **保持测试通过**: 每次重构后确保所有测试通过
3. **向后兼容**: 尽量保持 API 兼容，必要时添加 deprecation 警告
4. **Code Review**: 重要重构需要 code review
5. **文档同步**: 代码变更及时更新文档

---

## 🔗 相关资源

- **Python Type Hints**: https://mypy.readthedocs.io/
- **Pre-commit Hooks**: https://pre-commit.com/
- **Pytest Coverage**: https://pytest-cov.readthedocs.io/
- **Refactoring Patterns**: https://refactoring.guru/

---

**维护者**: AgentCrafter Team
**下次审查**: 完成后 1 个月
