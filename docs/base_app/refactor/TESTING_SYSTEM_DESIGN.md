# Workflow 自动化测试系统设计文档

## 1. 目标

### 1.1 核心目标

1. **质量评估**：批量运行测试，判断 workflow 生成质量
   - 每个 recording 运行 N 次（默认 3 次，可配置）
   - 评估代码改动对生成质量和速度的影响

2. **持续改进**：收集和分析日志，提供改进建议
   - 解析生成过程日志为人可读格式
   - AI 分析失败原因和改进方向

### 1.2 验证范围

| 验证层次 | 验证内容 | 实现方式 |
|---------|---------|---------|
| Workflow 结构 | YAML 语法、必填字段、变量引用 | 复用 `RuleValidator` |
| Workflow 语义 | 是否能完成用户任务、步骤合理性 | 复用 `SemanticValidator` |
| 脚本执行 | 脚本能否正确提取数据 | 执行脚本 + AI 分析 |
| Workflow 执行 | engine 能否正确运行 workflow | Mock 执行验证 |

---

## 2. 数据结构

### 2.1 现有数据结构（参考）

#### Recording（生产环境）
```
~/ami-server/users/{user}/recordings/{session_id}/
├── metadata.json
├── operations.json         # 用户操作序列，每个 operation 有 dom_id
└── dom_snapshots/
    ├── url_index.json
    └── {dom_id}.json       # DOM 数据 {"url": ..., "dom": {...}}
```

#### Workflow（生产环境）
```
~/ami-server/users/{user}/workflows/{workflow_id}/
├── metadata.json
├── workflow.yaml
├── dom_snapshots/          # 复制过来的 DOM 快照
└── {step_id}/              # 每个步骤的脚本目录（脚本直接存放）
    ├── extraction_script.py   # 生成的提取脚本
    ├── dom_data.json          # 用于生成脚本的 DOM
    ├── dom_tools.py           # 辅助工具
    └── requirement.json       # 提取需求
```

### 2.2 测试系统目录结构

所有测试数据和报告都在配置的 `storage_dir` 下，与代码目录分离：

```
{storage_dir}/                          # 配置指定，如 ~/ami-test/
├── config.yaml                         # 主配置文件
│
├── test_data/                          # 测试数据目录（固定，不被运行污染）
│   └── recordings/                     # 测试用的 recording 数据
│       ├── ces_keynote_speakers/       # case 名称
│       │   ├── operations.json
│       │   └── dom_snapshots/
│       │       └── *.json
│       └── watcha_rank/
│           └── ...
│
└── test_runs/                          # 测试运行目录
    └── {run_id}/                       # 每次运行一个目录，如 20260109_153022
        │
        ├── config_snapshot.yaml        # 本次运行的配置快照
        ├── summary.md                  # 汇总报告（人读）
        ├── summary.json                # 汇总数据（机器读）
        │
        └── cases/
            └── {case_name}/            # 一个测试用例
                │
                ├── case_report.md      # 用例报告
                ├── case_summary.json   # 用例汇总数据
                │
                ├── run_1/              # 第 1 次运行
                │   │
                │   ├── workflow.yaml   # 生成的 workflow
                │   ├── metadata.json   # 运行元数据（耗时等）
                │   │
                │   ├── generation_log/ # 提取的生成日志（人可读）
                │   │   ├── trace.md    # 完整生成过程
                │   │   └── raw_logs.json
                │   │
                │   ├── steps/          # 每个步骤的执行结果
                │   │   └── {step_id}/
                │   │       ├── extraction_script.py
                │   │       ├── dom_data.json
                │   │       ├── dom_tools.py
                │   │       ├── output.json
                │   │       └── validation.json
                │   │
                │   ├── execution/      # Mock 执行结果
                │   │   ├── result.json
                │   │   └── variables.json
                │   │
                │   ├── run_result.json # 本次运行结果汇总
                │   │
                │   └── analysis/       # 验证 Agent 工作区（仅失败时）
                │       └── analysis.md
                │
                ├── run_2/
                │   └── ...
                │
                └── run_3/
                    └── ...
```

---

## 3. 配置文件

### 3.1 主配置文件

配置文件位于 `{storage_dir}/config.yaml`：

```yaml
# ~/ami-test/config.yaml

# 全局配置
runs_per_case: 3                        # 每个 case 运行次数
max_parallel: 3                         # 最大并行数
timeout: 300                            # 单次运行超时（秒）

# API 配置
api_key_env: ANTHROPIC_API_KEY          # 从环境变量读取
# 或直接配置: api_key: sk-...
api_base_url: https://api.anthropic.com # 可选，支持代理
model: claude-sonnet-4-5                # 可选，默认 claude-sonnet-4-5

# 目录配置（相对于 config.yaml 所在目录）
test_data_dir: test_data                # 测试数据目录
test_runs_dir: test_runs                # 测试运行目录

# 测试用例列表
cases:
  - name: ces_keynote_speakers
    description: "提取 CES 网站上的演讲者信息"
    # recording 目录名，默认和 name 相同
    recording: ces_keynote_speakers
    # 可选：覆盖全局运行次数
    runs: 5

  - name: watcha_rank
    description: "获取观猹排行榜数据"
    # 不指定 recording，则使用 name 作为目录名
```

### 3.2 并行策略

`max_parallel` 控制全局并行数，所有 case 的所有 run 共享并行池：

```
max_parallel: 3 时：

任务队列: [A-run1, A-run2, A-run3, B-run1, B-run2, B-run3]

时间线:
├── A-run1 ──────> 并行槽 1
├── A-run2 ──────> 并行槽 2
├── A-run3 ──────> 并行槽 3
│   (A-run1 完成)
├── B-run1 ──────> 并行槽 1
...
```

---

## 4. 测试流程

### 4.1 完整流程图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           单次 Run 执行流程                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐                                                       │
│  │  Recording   │  test_data/recordings/{case_name}/                    │
│  │  (输入数据)   │  ├── operations.json                                  │
│  └──────┬───────┘  └── dom_snapshots/                                   │
│         │                                                               │
│         ▼                                                               │
│  ┌──────────────┐                                                       │
│  │ IntentExtractor │  提取用户意图                                       │
│  └──────┬───────┘                                                       │
│         │                                                               │
│         ▼  保存 intents.json                                            │
│  ┌──────────────┐                                                       │
│  │ WorkflowBuilder │  生成 workflow.yaml                                │
│  └──────┬───────┘                                                       │
│         │                                                               │
│         ▼                                                               │
│  ┌──────────────┐                                                       │
│  │ ScriptPregen │  为 scraper/browser 步骤生成脚本                       │
│  └──────┬───────┘                                                       │
│         │                                                               │
│         ▼                                                               │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                        验证阶段                                    │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │  │
│  │  │ Layer 1     │  │ Layer 2     │  │ Layer 3     │  │ Layer 4  │ │  │
│  │  │ 结构验证    │→│ 语义验证    │→│ 脚本执行    │→│ Mock执行 │ │  │
│  │  │ RuleValidator│  │ SemanticVal │  │ 验证        │  │ 验证     │ │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └──────────┘ │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│         │                                                               │
│         ▼  (如果任一层失败)                                              │
│  ┌──────────────┐                                                       │
│  │ ValidationAgent│  分析失败原因                                        │
│  └──────┬───────┘                                                       │
│         │                                                               │
│         ▼                                                               │
│  ┌──────────────┐                                                       │
│  │ 生成报告     │  run_result.json + trace.md                           │
│  └──────────────┘                                                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 输出产物

每次 Run 完成后，输出目录结构：

```
run_N/
├── intents.json              # 提取的 Intent（新增）
├── workflow.yaml             # 生成的 Workflow
├── metadata.json             # 运行元数据（耗时等）
├── generation_log/
│   ├── trace.md              # 人可读的生成过程
│   └── raw_logs.json
├── steps/                    # 每个步骤的脚本和执行结果
│   └── {step_id}/
│       ├── extraction_script.py
│       ├── dom_tools.py
│       ├── output.json
│       └── validation.json
├── execution/                # Mock 执行结果
│   ├── result.json
│   └── variables.json
├── run_result.json           # 本次运行结果汇总
└── analysis/                 # 失败分析（仅失败时）
    └── analysis.md
```

### 4.3 Intent 保存

Intent 在生成 Workflow 之前提取，保存到 `intents.json`：

```json
// run_N/intents.json
{
  "intents": [
    {
      "id": "intent_1",
      "description": "导航到 CES 网站",
      "type": "navigation",
      "target_url": "https://www.ces.tech/"
    },
    {
      "id": "intent_2",
      "description": "提取 Keynotes 页面链接",
      "type": "extraction",
      "data_requirements": {...}
    }
  ],
  "extraction_time_ms": 2100
}
```

用途：
1. **SemanticValidator 输入**：判断 Workflow 是否能完成这些 Intent
2. **报告展示**：显示用户意图 vs 生成的步骤
3. **调试分析**：对比 Intent 和 Workflow 的差异

---

## 5. 验证方案

### 5.1 Layer 1: 结构验证（复用 RuleValidator）

**已有能力**：
- YAML 语法检查
- 必填字段检查（apiVersion, name, steps）
- Agent 类型验证
- 变量引用检查（`{{var}}` 是否有定义）
- 控制流结构检查（foreach, if, while）
- Step ID 唯一性检查

**代码位置**：
- `src/cloud_backend/intent_builder/agents/tools/validate.py`
- `RuleValidator` 类

### 4.2 Layer 2: 语义验证（复用 SemanticValidator）

**已有能力**：
- AI 评估 workflow 是否能完成用户任务
- 检查步骤覆盖度、顺序、数据流
- 返回 score (0-100) 和 issues 列表

**代码位置**：
- `src/cloud_backend/intent_builder/validators/semantic_validator.py`
- `SemanticValidator` 类

### 4.3 Layer 3: 脚本执行验证

#### 4.3.1 Scraper 脚本验证

```python
async def validate_scraper_script(script_dir: Path, workflow_step: dict) -> ValidationResult:
    """验证 scraper 脚本执行结果"""

    # 1. 执行脚本
    # 脚本有 if __name__ == "__main__" 入口
    # 读取 dom_data.json，调用 extract_data_from_page()
    result = run_extraction_script(script_dir)

    # 2. 检查是否有输出
    if result is None or result == {}:
        return ValidationResult(success=False, error="No output")

    # 3. 从 workflow step 的 output_format 获取期望字段
    expected_fields = workflow_step["inputs"]["data_requirements"]["output_format"].keys()

    # 4. 检查字段是否完整
    missing_fields = [f for f in expected_fields if f not in result]

    # 5. 如果缺少字段，调用 AI 检查 DOM 中是否有数据
    if missing_fields:
        analysis = await analyze_missing_data(
            dom_data_path=script_dir / "dom_data.json",
            missing_fields=missing_fields,
            script_output=result
        )
        return ValidationResult(
            success=False,
            error="Missing fields",
            missing_fields=missing_fields,
            ai_analysis=analysis
        )

    return ValidationResult(success=True, output=result)
```

#### 4.3.2 Browser 脚本验证 (find_element.py)

```python
async def validate_browser_script(script_dir: Path) -> ValidationResult:
    """验证 find_element 脚本"""

    # 1. 执行脚本
    result = run_find_element_script(script_dir)

    # 2. 检查返回了 interactive_index
    if "interactive_index" not in result:
        return ValidationResult(success=False, error="No interactive_index")

    index = result["interactive_index"]

    # 3. 验证 index 在 DOM 中存在
    dom_data = load_json(script_dir / "dom_data.json")
    element = find_element_by_interactive_index(dom_data, index)

    if element is None:
        return ValidationResult(
            success=False,
            error=f"interactive_index {index} not found in DOM"
        )

    return ValidationResult(
        success=True,
        output=result,
        found_element=element
    )
```

### 4.4 Layer 4: Mock 执行验证

#### 4.4.1 目标

验证 workflow engine 能否正确执行 workflow：
- 变量解析和传递
- 控制流执行
- 步骤顺序
- 错误处理

#### 4.4.2 方案：继承创建 MockAgent

创建 `MockScraperAgent` 和 `MockBrowserAgent`，继承原 Agent 类，只重写涉及浏览器调用的方法：

```python
class DOMProvider:
    """DOM 数据提供者，用预存数据替代真实浏览器"""

    def __init__(self, dom_snapshots: Dict[str, dict]):
        self.dom_snapshots = dom_snapshots
        self.current_url = None
        self._url_index = self._build_url_index()

    def _build_url_index(self) -> Dict[str, str]:
        """构建 URL -> dom_id 索引"""
        index = {}
        for dom_id, data in self.dom_snapshots.items():
            url = data.get("url")
            if url:
                index[url] = dom_id
        return index

    def get_dom_for_url(self, url: str) -> Optional[dict]:
        """根据 URL 获取 DOM 数据"""
        dom_id = self._url_index.get(url)
        if dom_id:
            return self.dom_snapshots[dom_id].get("dom")
        return None

    def set_current_url(self, url: str):
        """设置当前 URL（模拟导航）"""
        self.current_url = url

    def get_current_dom(self) -> Optional[dict]:
        """获取当前页面的 DOM"""
        if self.current_url:
            return self.get_dom_for_url(self.current_url)
        return None


class MockScraperAgent(ScraperAgent):
    """Mock ScraperAgent，使用预存 DOM 替代浏览器调用"""

    def __init__(self, dom_provider: DOMProvider):
        super().__init__()
        self.dom_provider = dom_provider

    # 重写获取 DOM 的方法
    async def _get_enhanced_dom_tree(self) -> dict:
        """返回预存的 DOM 数据"""
        return self.dom_provider.get_current_dom() or {}

    async def _get_current_page_url(self) -> str:
        """返回当前 URL"""
        return self.dom_provider.current_url or ""


class MockBrowserAgent(BrowserAgent):
    """Mock BrowserAgent，使用预存 DOM 替代浏览器调用"""

    def __init__(self, dom_provider: DOMProvider):
        super().__init__()
        self.dom_provider = dom_provider

    # 重写导航方法
    async def _navigate_to_url(self, url: str):
        """模拟导航，只切换 URL 状态"""
        self.dom_provider.set_current_url(url)

    # 重写获取 DOM 的方法
    async def _get_enhanced_dom_tree(self) -> dict:
        """返回预存的 DOM 数据"""
        return self.dom_provider.get_current_dom() or {}

    async def _get_current_page_url(self) -> str:
        """返回当前 URL"""
        return self.dom_provider.current_url or ""

    # 重写交互方法（点击、输入等）
    async def _perform_interaction(self, action: str, element_index: int, **kwargs):
        """模拟交互，不执行实际操作"""
        # 只记录操作，不执行
        pass
```

#### 4.4.3 Mock 执行器

```python
class MockWorkflowExecutor:
    """使用 MockAgent 执行 workflow"""

    def __init__(self, dom_snapshots: Dict[str, dict]):
        self.dom_provider = DOMProvider(dom_snapshots)

    async def execute(self, workflow: dict) -> ExecutionResult:
        """执行 workflow"""

        # 1. 创建 Mock Agent 映射
        mock_agent_types = {
            "scraper_agent": lambda: MockScraperAgent(self.dom_provider),
            "browser_agent": lambda: MockBrowserAgent(self.dom_provider),
            "storage_agent": StorageAgent,  # 可以用真实的，或也 mock
        }

        # 2. 使用 WorkflowEngine 执行
        engine = WorkflowEngine(agent_types=mock_agent_types)

        result = await engine.execute_workflow(
            steps=parse_steps(workflow),
            workflow_id="test",
            input_data={}
        )

        return ExecutionResult(
            success=result.success,
            steps=result.steps,
            final_variables=result.variables
        )
```

#### 4.4.4 方案优势

1. **隔离性好**：不需要深入理解 Agent 内部实现细节
2. **改动集中**：所有 mock 逻辑在继承类里，而不是分散的 patch 点
3. **更稳定**：原 Agent 代码改动不会轻易破坏 mock（只要接口不变）
4. **易于维护**：如果 Agent 新增了浏览器调用，继承方式更容易发现和处理

#### 4.4.5 执行结果记录

Mock 执行后记录：
- 每个步骤的执行状态（成功/失败）
- 变量的值（验证数据传递是否正确）
- 错误信息和堆栈（如果有）
- 最终结果（是否有 `storage_agent` 保存了数据）

---

## 6. 验证 Agent（失败分析）

### 6.1 触发条件

只在以下情况调用验证 Agent：
- 脚本执行失败
- 脚本输出缺少字段
- Mock 执行失败

### 6.2 Agent 设计

```python
class ValidationAgent:
    """验证失败时调用，分析缺失数据的原因"""

    def __init__(self, working_dir: Path, api_key: str):
        self.working_dir = working_dir
        self.api_key = api_key

        # 复用现有 skills
        self.skills_dir = working_dir / ".claude" / "skills"
        self._setup_skills()

    def _setup_skills(self):
        """复制需要的 skills"""
        copy_skills(
            src=Path("src/cloud_backend/services/skills/repository"),
            dst=self.skills_dir,
            skills=["dom-extraction", "element-finder"]
        )

    async def analyze_failure(
        self,
        workflow_path: Path,
        failed_step_id: str,
        dom_data_path: Path,
        script_output: dict,
        expected_fields: list,
        generation_trace_path: Path
    ) -> str:
        """分析失败原因"""

        prompt = f"""
        脚本执行后缺少以下字段: {expected_fields}

        请分析原因:
        1. 检查 DOM 数据中是否本来就没有这些数据
           - 使用 dom_tools 中的函数搜索
        2. 如果 DOM 中有数据，查看生成日志
           - 分析脚本生成过程中是否有问题

        脚本当前输出: {json.dumps(script_output)}

        请给出:
        1. 数据是否存在于 DOM 中
        2. 如果存在，为什么脚本没有提取到
        3. 改进建议
        """

        result = await self._run_agent(prompt)

        # 保存分析结果
        (self.working_dir / "analysis.md").write_text(result)

        return result
```

### 6.3 Agent 输入

验证 Agent 工作目录包含：
- `workflow.yaml` - 生成的 workflow
- `dom_data.json` - 失败步骤的 DOM 数据
- `output.json` - 脚本输出
- `generation_log/trace.md` - 生成过程日志
- `.claude/skills/` - 复制的 skills

---

## 7. 日志系统

### 7.1 独立日志文件

测试系统使用独立的日志文件，不依赖 cloud backend 日志：

```
{storage_dir}/test_runs/{run_id}/
├── logs/
│   └── test_run.log              # 本次运行的完整日志
└── cases/{case_name}/run_N/
    └── generation_log/
        ├── trace.md              # 解析后的人可读日志
        └── raw_logs.json         # 该 run 的原始日志片段
```

### 7.2 日志格式

测试系统输出的日志保持与 cloud backend 相同的 JSON 格式，便于复用解析逻辑：

```json
{
  "timestamp": "2026-01-09T03:45:22.521951+00:00",
  "level": "INFO",
  "service": "ami_test",
  "module": "workflow_generator",
  "message": "📨 [event_generator] Received event #2: type=tool_use",
  "request_id": "run_20260109_153022_case1_1",
  "case_name": "ces_keynote_speakers",
  "run_number": 1
}
```

### 7.3 request_id 格式

每次 run 生成唯一的 request_id，格式：`run_{run_id}_{case_name}_{run_number}`

用途：
- 日志过滤：从完整日志中提取特定 run 的日志
- 日志解析：复用现有解析逻辑

### 7.4 解析输出

```markdown
# 生成过程日志 - Run 1

## Intent 提取阶段 (2.1s)
- 输入: 22 个 operations
- 输出: 3 个 intents
  1. 导航到 CES 网站
  2. 提取 Keynotes 链接
  3. 提取所有演讲者信息

## Workflow 生成阶段 (10.3s)
### 工具调用
1. [0.5s] Read: workflow-generation/SKILL.md
2. [0.3s] Read: agent-specs/browser.md
3. [0.2s] Read: agent-specs/scraper.md
4. [8.0s] 生成 workflow.yaml

### AI 思考过程
> 用户想要提取 CES 网站的演讲者信息...
> 需要先导航到 Keynotes 页面...

## 验证阶段 (1.2s)
- Rule validation: PASSED
- Semantic validation: PASSED (score: 85)

## 脚本预生成阶段 (5.2s)
- extract-keynotes-url: 生成成功
- extract-speaker-cards: 生成成功
```

---

## 8. 报告生成

### 8.1 报告组成

**脚本自动生成**：
- 运行统计（成功率、耗时）
- 脚本执行结果（输出、错误）
- 验证结果（找到/未找到元素）
- 原始数据（workflow、DOM 片段）

**AI 分析**（仅失败时）：
- 失败原因分析
- 改进建议

### 8.2 case_report.md 示例

```markdown
# Test Case: ces_keynote_speakers

## 运行汇总

| Run | 生成耗时 | 脚本成功率 | 执行结果 | 状态 |
|-----|---------|-----------|---------|------|
| 1   | 15.2s   | 3/3 (100%) | ✅ Pass | ✅ Pass |
| 2   | 14.8s   | 3/3 (100%) | ✅ Pass | ✅ Pass |
| 3   | 16.1s   | 2/3 (67%)  | ❌ Fail | ❌ Fail |

**总体成功率: 67% (2/3)**
**平均生成时间: 15.4s**

---

## Run 3 详情（失败）

### 验证结果

#### 结构验证 (RuleValidator)
✅ PASSED

#### 语义验证 (SemanticValidator)
✅ PASSED (score: 82)

#### 脚本执行验证

| Step | 类型 | 状态 | 详情 |
|------|-----|------|------|
| extract-keynotes-url | scraper | ✅ Pass | 提取到 URL |
| click-attend-button | browser | ✅ Pass | 找到元素 index=42 |
| extract-speaker-cards | scraper | ❌ Fail | 缺少字段 |

### 失败步骤: extract-speaker-cards

**脚本输出:**
```json
[
  {"name": "Jensen Huang", "title": "CEO"},
  {"name": "Lisa Su", "company": "AMD"}
]
```

**问题:** 部分记录缺少字段 (title, company)

### 失败原因分析 (by Validation Agent)

经检查 DOM 数据:
- DOM 中确实包含所有 speaker 的 name, title, company 信息
- 数据位于 `//div[@class="speaker-card"]` 下的子元素中

问题原因:
- 生成的脚本使用了不完整的 xpath 选择器
- 某些 speaker card 的 HTML 结构略有不同

**改进建议:**
1. 在生成脚本时，确保 DOM 样本包含多种结构变体
2. 使用更鲁棒的选择器

---

## 生成日志摘要 (Run 3)

[完整日志见 run_3/generation_log/trace.md]
```

---

## 9. 生成过程分析 (GenerationAnalyzer)

### 9.1 目标

持续改进系统需要分析 WorkflowBuilder 和 Script 生成的详细过程，找出可以优化的地方：

1. **理解 AI 决策过程** - 分析生成日志中的工具调用和思考过程
2. **识别失败模式** - 找出导致失败的常见原因
3. **提供改进建议** - 生成可操作的优化建议

### 9.2 分析类型

#### 9.2.1 单次运行分析 (analyze_run)

分析单个 run 的生成过程：

**输入数据**：
- `trace.md` - 生成过程日志（工具调用、AI 思考）
- `workflow.yaml` - 生成的 workflow
- `intents.json` - 提取的用户意图
- `validation_result.json` - 验证结果
- `execution/result.json` - Mock 执行结果

**分析重点**：
- **Intent Extraction**: 用户意图是否被正确识别？
- **Workflow Structure**: 生成的 workflow 结构是否合理？
- **Step Mapping**: workflow 步骤是否正确映射用户意图？
- **Script Generation**: 提取脚本是否正确定位元素？
- **Data Flow**: 变量是否正确传递？

**输出**：
```
run_N/analysis/
├── generation_analysis.md    # 人可读分析报告
└── generation_analysis.json  # 机器可读数据
```

#### 9.2.2 跨运行模式分析 (analyze_case_patterns)

分析同一 case 多个 run 的模式：

**分析重点**：
- **一致性问题**: 结果是否一致？还是高度变化？
- **系统性问题**: 哪些问题在所有 run 中都出现？
- **根因分析**: 识别导致问题的根本原因

**输出**：
```
cases/{case_name}/analysis/
├── generation_analysis.md    # 跨 run 模式分析
└── generation_analysis.json
```

### 9.3 分析结果结构

```python
@dataclass
class AnalysisResult:
    success: bool
    workflow_analysis: Optional[str]      # Workflow 生成分析
    script_analysis: Optional[str]        # Script 生成分析
    improvement_suggestions: List[str]    # 改进建议列表
    patterns_identified: List[str]        # 识别的模式
    error: Optional[str]
```

### 9.4 generation_analysis.md 示例

```markdown
# Generation Process Analysis

## Workflow Generation Analysis

The workflow correctly identifies the main user intent to extract speaker information
from the CES website. However, there are some observations:

1. The navigation steps are well-structured, going from Google search to CES homepage
   to the keynotes page
2. The extraction step correctly targets the speaker cards section

Potential issues:
- The xpath_hints use absolute paths which may break if page structure changes
- No fallback mechanism for elements that may not be present

## Script Generation Analysis

The extraction script targets `//div[@class="speaker-card"]` which is correct.
However:
- The script extracts only the first level of nested elements
- Some speaker cards have different structures (e.g., "title" vs "role" field names)

## Patterns Identified

- Workflow tends to generate redundant navigation steps for redirects
- Script selectors use absolute xpaths instead of more robust CSS selectors
- Data requirements don't specify optional vs required fields

## Improvement Suggestions

1. **Use relative selectors**: Instead of absolute xpaths like `/html/body/div[3]/...`,
   use relative selectors like `//div[contains(@class, 'speaker')]`

2. **Add fallback selectors**: For critical elements, provide multiple selector options
   in the xpath_hints

3. **Specify field requirements**: In data_requirements, mark fields as optional/required
   to handle cases where some data may not be present

4. **Simplify navigation**: Consider combining consecutive click operations into a
   single navigation step when the intermediate pages are just redirects
```

### 9.5 与报告系统集成

**summary.md 改进建议部分**：

GenerationAnalyzer 的建议会自动整合到 summary.md 的"改进建议"部分：

```markdown
## 改进建议

- **Structure Issues** (2 failures): Review WorkflowBuilder prompts for correct YAML syntax
- **Script Issues** (1 failure): Review script generation for correct xpath selectors
- [ces_keynote_speakers] Use relative selectors instead of absolute xpaths
- [ces_keynote_speakers] Add fallback selectors for critical elements
- See AI analysis: `cases/ces_keynote_speakers/run_1/analysis/generation_analysis.md`
```

### 9.6 触发条件

| 分析类型 | 触发条件 |
|---------|---------|
| 单次运行分析 | 每个 run 完成后自动执行（需要 API Key） |
| 跨运行模式分析 | case 有多个 run 时，在报告生成阶段执行 |

### 9.7 代码位置

```
test/analyzer/
├── __init__.py
├── log_parser.py           # 日志解析
├── trace_formatter.py      # trace.md 格式化
└── generation_analyzer.py  # 生成过程 AI 分析（新增）
```

---

## 10. 模块复用

### 10.1 可直接复用的模块

| 模块 | 位置 | 依赖 |
|-----|------|------|
| `WorkflowService` | `intent_builder/services/workflow_service.py` | API Key |
| `ScriptPregenerationService` | `intent_builder/services/script_pregeneration_service.py` | API Key |
| `IntentExtractor` | `intent_builder/extractors/intent_extractor.py` | LLM Provider |
| `WorkflowValidator` | `intent_builder/validators/__init__.py` | API Key |
| `RuleValidator` | `intent_builder/agents/tools/validate.py` | 无 |
| `SemanticValidator` | `intent_builder/validators/semantic_validator.py` | API Key |

### 10.2 复用方式

所有模块都可以独立 import 使用，不依赖 FastAPI 或数据库：

```python
from src.cloud_backend.intent_builder.services import WorkflowService
from src.cloud_backend.intent_builder.validators import WorkflowValidator, RuleValidator

# 直接初始化
service = WorkflowService(api_key="sk-...")
validator = WorkflowValidator(api_key="sk-...")
rule_validator = RuleValidator()  # 无需 API key
```

---

## 11. DOM 映射逻辑抽取

### 11.1 背景

现有的 `ScriptPregenerationService._find_matching_dom()` 实现了 step → DOM 的映射逻辑，但：
- 错误率较高，经常找不到对应的 xpath
- 逻辑嵌在 service 中，不便于复用

### 10.2 抽取目标

将 DOM 映射逻辑抽取为独立模块，供以下场景复用：
1. `ScriptPregenerationService` - 脚本预生成时查找 DOM
2. 测试系统 - Mock 执行时查找 DOM
3. 未来优化 - 统一改进映射算法

### 10.3 抽取方案

```python
# src/common/dom_mapper.py

class DOMMapper:
    """DOM 映射器 - 根据 step 信息查找对应的 DOM snapshot"""

    def __init__(self, dom_snapshots: Dict[str, dict]):
        """
        Args:
            dom_snapshots: dom_id -> {"url": str, "dom": dict} 映射
        """
        self.dom_snapshots = dom_snapshots
        self._url_index = self._build_url_index()

    def _build_url_index(self) -> Dict[str, str]:
        """构建 URL -> dom_id 索引"""
        index = {}
        for dom_id, data in self.dom_snapshots.items():
            url = data.get("url")
            if url:
                index[url] = dom_id
        return index

    def find_dom_for_step(
        self,
        step: dict,
        intents: Optional[List] = None
    ) -> Optional[dict]:
        """为 step 查找匹配的 DOM

        匹配策略（按优先级）：
        1. URL 精确匹配
        2. xpath_hints 匹配（TODO: 后续优化）

        Returns:
            DOM data {"url": str, "dom": dict} 或 None
        """
        # 策略 1: URL 匹配
        step_url = self._extract_step_url(step)
        if step_url and step_url in self._url_index:
            dom_id = self._url_index[step_url]
            return self.dom_snapshots[dom_id]

        # 策略 2: xpath_hints 匹配（TODO）
        # 现有逻辑错误率高，待优化

        return None

    def _extract_step_url(self, step: dict) -> Optional[str]:
        """从 step 中提取目标 URL"""
        inputs = step.get("inputs", {})
        return inputs.get("target_url") or inputs.get("url")


# 工厂函数，方便使用
def create_dom_mapper(recording_dir: Path) -> DOMMapper:
    """从 recording 目录创建 DOMMapper"""
    dom_snapshots = {}
    snapshots_dir = recording_dir / "dom_snapshots"

    if snapshots_dir.exists():
        for f in snapshots_dir.glob("*.json"):
            if f.name == "url_index.json":
                continue
            dom_id = f.stem
            dom_snapshots[dom_id] = json.loads(f.read_text())

    return DOMMapper(dom_snapshots)
```

### 10.4 迁移计划

1. 创建 `src/common/dom_mapper.py`
2. 修改 `ScriptPregenerationService` 使用 `DOMMapper`
3. 测试系统使用 `DOMMapper`
4. 后续优化 xpath_hints 匹配逻辑

---

## 11. CLI 命令设计

### 11.1 命令格式

```bash
# 运行所有 case
ami-test run --config ~/ami-test/config.yaml

# 运行指定 case
ami-test run --config ~/ami-test/config.yaml --case ces_keynote_speakers

# 运行多个指定 case
ami-test run --config ~/ami-test/config.yaml --case ces_keynote_speakers --case watcha_rank

# 覆盖并行数
ami-test run --config ~/ami-test/config.yaml --parallel 5

# 覆盖运行次数
ami-test run --config ~/ami-test/config.yaml --runs 10

# 查看可用 cases
ami-test list --config ~/ami-test/config.yaml

# 查看历史运行
ami-test history --config ~/ami-test/config.yaml
```

### 11.2 命令说明

| 命令 | 说明 |
|------|------|
| `run` | 运行测试 |
| `list` | 列出配置中的所有 case |
| `history` | 列出历史运行记录 |

### 11.3 run 命令参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--config` | 配置文件路径 | 必填 |
| `--case` | 指定运行的 case（可多次使用） | 全部 |
| `--parallel` | 覆盖最大并行数 | 配置文件中的值 |
| `--runs` | 覆盖每个 case 运行次数 | 配置文件中的值 |

---

## 12. 已确认决策汇总

| 决策项 | 决策 |
|--------|------|
| 模块复用 | 所有 intent_builder 模块可独立使用，无 FastAPI/DB 依赖 |
| DOM 映射 | 先用 URL 匹配，抽取为 `DOMMapper` 类复用 |
| Mock 执行 | 继承创建 MockAgent（方案 B），只重写浏览器调用方法 |
| 并行执行 | 所有 run 共享并行池，`max_parallel` 控制 |
| 测试数据 | 存放在 `{storage_dir}/test_data/recordings/` |
| 报告存储 | 存放在 `{storage_dir}/test_runs/{run_id}/` |
| API Key | 从配置文件读取（环境变量或直接配置） |
| 失败重试 | 不重试，直接记录失败 |
| 日志系统 | 独立日志文件，格式与 cloud backend 相同 |
| request_id | 每次 run 生成唯一 ID，格式 `run_{run_id}_{case}_{N}` |
| Intent 保存 | 每次 run 保存 intents.json，供 SemanticValidator 使用 |
| 报告格式 | 仅 Markdown |

---

## 13. 实现路径

### Phase 1: 基础框架
1. CLI 入口 (`cli.py`)
2. 配置加载 (`config.py`)
3. 复用 WorkflowService 生成 workflow

### Phase 2: 验证能力
1. 复用 RuleValidator + SemanticValidator
2. 实现脚本执行验证
3. 实现验证 Agent（失败分析）

### Phase 3: Mock 执行
1. 实现 DOMProvider
2. 实现 MockScraperAgent / MockBrowserAgent
3. 实现 MockWorkflowExecutor

### Phase 4: 报告生成
1. 日志解析器
2. 报告模板
3. AI 分析集成（仅失败时）

---

## 14. 代码目录结构

```
test/
├── __init__.py
├── cli.py                           # CLI 入口
├── config.py                        # 配置加载
│
├── runner/
│   ├── __init__.py
│   ├── test_runner.py               # 主编排器
│   ├── workflow_generator.py        # 复用 WorkflowService
│   └── parallel_executor.py         # 并行执行管理
│
├── validator/
│   ├── __init__.py
│   ├── script_validator.py          # 脚本执行验证
│   └── validation_agent.py          # 验证 Agent（失败分析）
│
├── mock/
│   ├── __init__.py
│   ├── dom_provider.py              # DOM 数据提供者
│   ├── mock_agents.py               # MockScraperAgent, MockBrowserAgent
│   └── mock_executor.py             # Mock 执行器
│
├── analyzer/
│   ├── __init__.py
│   ├── log_parser.py                # 日志解析器
│   └── trace_formatter.py           # 格式化为人可读
│
└── reporter/
    ├── __init__.py
    ├── summary_report.py            # 汇总报告
    └── case_report.py               # 用例报告
```

---

## 15. 进程隔离与安全

### 15.1 与生产系统隔离

测试系统设计为**完全独立的进程**，不影响生产系统：

| 隔离点 | 说明 |
|--------|------|
| 进程隔离 | `ami-test` 是独立 CLI，不依赖 cloud backend 服务 |
| 数据隔离 | 测试数据和报告存放在独立的 `{storage_dir}/`，不写入 `~/ami-server/` |
| 模块复用 | 直接 import Python 类，不调用生产 HTTP API |
| Mock 执行 | 使用 MockAgent + 预存 DOM，不连接真实浏览器 |
| API 调用 | 只调用 Anthropic API（LLM），不调用内部服务 |

### 15.2 不会影响的内容

- `~/ami-server/` 下的所有数据（recordings, workflows, sessions）
- cloud backend 服务进程
- 真实浏览器会话
- 生产数据库（如果有）

### 15.3 会使用的资源

- Anthropic API（消耗 token）
- 本地磁盘（`{storage_dir}/` 目录）
- CPU/内存（本地执行）

---

## 16. 任务完成标准

### 16.1 代码完成标准

1. **语法检查通过**：所有 Python 文件无语法错误
2. **import 检查通过**：所有依赖模块可正常导入
3. **CLI 可运行**：`ami-test --help` 正常显示帮助信息

### 16.2 基本功能验证

```bash
# 1. CLI 帮助
ami-test --help
ami-test run --help

# 2. 配置加载
ami-test list --config ~/ami-test/config.yaml

# 3. 空运行（dry-run，如果实现）
ami-test run --config ~/ami-test/config.yaml --dry-run
```

---

## 17. 人类测试指南

### 17.1 环境准备

#### 17.1.1 依赖安装

```bash
# 确保在项目根目录
cd /path/to/2ami

# 安装依赖（如果尚未安装）
pip install pyyaml
```

#### 17.1.2 创建测试数据目录

```bash
# 创建测试存储目录
mkdir -p ~/ami-test/test_data/recordings
mkdir -p ~/ami-test/test_runs
```

#### 17.1.3 准备测试 Recording

从生产环境复制一个 recording 作为测试数据：

```bash
# 复制现有 recording（示例）
cp -r ~/ami-server/users/{user}/recordings/{session_id}/ \
      ~/ami-test/test_data/recordings/my_test_case/

# 确保目录结构正确
ls ~/ami-test/test_data/recordings/my_test_case/
# 应该看到: operations.json  dom_snapshots/
```

#### 17.1.4 创建配置文件

```bash
cat > ~/ami-test/config.yaml << 'EOF'
# 全局配置
runs_per_case: 3
max_parallel: 2
timeout: 300

# API 配置
api_key_env: ANTHROPIC_API_KEY
api_base_url: https://api.anthropic.com  # 可选
model: claude-sonnet-4-5                 # 可选

# 目录配置
test_data_dir: test_data
test_runs_dir: test_runs

# 测试用例
cases:
  - name: my_test_case
    description: "测试用例描述"
EOF
```

#### 17.1.5 设置环境变量

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### 17.2 功能测试清单

#### 17.2.1 CLI 基本功能

```bash
# 测试 1: 查看帮助信息
python3 -m test --help
# 预期: 显示 ami-test 帮助信息，包含 run/list/history 子命令

# 测试 2: 查看 run 命令帮助
python3 -m test run --help
# 预期: 显示 run 命令的所有参数

# 测试 3: 列出配置的 cases
python3 -m test list --config ~/ami-test/config.yaml
# 预期: 显示配置信息和用例列表，标记每个 case 的 recording 是否存在
```

#### 17.2.2 配置验证

```bash
# 测试 4: 配置文件不存在
python3 -m test list --config ~/nonexistent.yaml
# 预期: 报错 "配置文件不存在"

# 测试 5: Recording 目录不存在
# 编辑 config.yaml，添加一个不存在的 case，然后运行 list
python3 -m test list --config ~/ami-test/config.yaml
# 预期: 对应 case 显示 [✗]，底部显示验证警告

# 测试 6: API Key 未设置
unset ANTHROPIC_API_KEY
python3 -m test run --config ~/ami-test/config.yaml --dry-run
# 预期: 报错 "未设置 API Key"
```

#### 17.2.3 Dry-run 模式

```bash
# 设置回 API Key
export ANTHROPIC_API_KEY="sk-ant-..."

# 测试 7: Dry-run 模式
python3 -m test run --config ~/ami-test/config.yaml --dry-run
# 预期: 显示将要执行的任务数量，不实际运行

# 测试 8: 指定 case 的 dry-run
python3 -m test run --config ~/ami-test/config.yaml --case my_test_case --dry-run
# 预期: 只显示指定 case 的任务

# 测试 9: 覆盖运行次数
python3 -m test run --config ~/ami-test/config.yaml --runs 5 --dry-run
# 预期: 显示每个 case 运行 5 次
```

#### 17.2.4 实际运行测试

```bash
# 测试 10: 运行单个 case 一次
python3 -m test run --config ~/ami-test/config.yaml --case my_test_case --runs 1
# 预期:
# - 控制台显示运行进度
# - 创建 ~/ami-test/test_runs/{run_id}/ 目录
# - 生成 summary.md 和 summary.json
# - 生成 cases/my_test_case/case_report.md

# 测试 11: 检查生成的报告
cat ~/ami-test/test_runs/{最新run_id}/summary.md
# 预期: 显示测试运行报告，包含概览和用例汇总

# 测试 12: 查看历史运行
python3 -m test history --config ~/ami-test/config.yaml
# 预期: 列出刚才的运行记录
```

### 17.3 隔离性验证

#### 17.3.1 数据隔离

```bash
# 验证 1: 检查没有写入生产目录
ls -la ~/ami-server/users/
# 预期: 运行前后内容完全一致，没有新文件

# 验证 2: 检查输出只在测试目录
ls ~/ami-test/test_runs/
# 预期: 只有测试系统创建的 run 目录
```

#### 17.3.2 进程隔离

```bash
# 验证 3: 检查没有依赖 cloud backend 服务
# 确保 cloud backend 未运行
ps aux | grep uvicorn
# 然后运行测试
python3 -m test run --config ~/ami-test/config.yaml --runs 1
# 预期: 正常运行，不报告连接错误
```

### 17.4 报告检查要点

#### 17.4.1 目录结构检查

运行完成后，检查输出目录结构：

```bash
tree ~/ami-test/test_runs/{run_id}/
```

预期结构：

```
{run_id}/
├── config_snapshot.yaml      # 配置快照
├── summary.md                # 汇总报告（Markdown）
├── summary.json              # 汇总数据（JSON）
├── logs/
│   └── test_run.log          # 运行日志
└── cases/
    └── {case_name}/
        ├── case_report.md    # 用例报告
        ├── case_summary.json # 用例汇总
        └── run_1/
            ├── intents.json      # 提取的 Intent
            ├── workflow.yaml     # 生成的 Workflow
            ├── run_result.json   # 运行结果
            ├── validation_result.json  # 验证结果
            ├── steps/            # 脚本目录
            │   └── {step_id}/    # 脚本直接存放在 step 目录
            │       ├── extraction_script.py
            │       └── dom_tools.py
            └── execution/        # Mock 执行结果（如有）
                └── result.json
```

#### 17.4.2 报告内容检查

1. **summary.md**: 检查是否包含
   - 运行 ID 和时间
   - 总体成功率
   - 用例汇总表格
   - 失败详情（如有）

2. **case_report.md**: 检查是否包含
   - 每个 run 的验证结果表格
   - 耗时分解
   - 错误信息（如有）

3. **run_result.json**: 检查是否包含
   - 各阶段耗时 (`intent_extraction_time_ms`, `workflow_generation_time_ms` 等)
   - 验证结果 (`rule_validation_passed`, `semantic_validation_passed` 等)
   - 错误信息（如有）

### 17.5 异常测试场景

#### 17.5.1 网络异常

```bash
# 断开网络后运行（测试 API 调用失败处理）
python3 -m test run --config ~/ami-test/config.yaml --runs 1
# 预期: 报告连接错误，记录失败状态
```

#### 17.5.2 无效配置

```bash
# 创建无效配置
echo "invalid: yaml: content" > ~/ami-test/bad_config.yaml
python3 -m test run --config ~/ami-test/bad_config.yaml
# 预期: 报错 "配置格式错误"
```

#### 17.5.3 空 Recording

```bash
# 创建空 recording 目录
mkdir -p ~/ami-test/test_data/recordings/empty_case
touch ~/ami-test/test_data/recordings/empty_case/operations.json
# 添加到 config.yaml 后运行
python3 -m test run --config ~/ami-test/config.yaml --case empty_case --runs 1
# 预期: 验证阶段报错
```

#### 17.5.4 超时测试

```bash
# 设置很短的超时时间
# 编辑 config.yaml: timeout: 5
python3 -m test run --config ~/ami-test/config.yaml --runs 1
# 预期: 如果生成时间超过 5 秒，记录超时错误
```

### 17.6 性能验证

```bash
# 测试并行执行
python3 -m test run --config ~/ami-test/config.yaml --runs 3 --parallel 3
# 观察:
# - 3 个 run 是否同时开始（查看日志时间戳）
# - 总耗时是否接近单次耗时（而非 3 倍）
```

### 17.7 清理

```bash
# 清理测试运行结果
rm -rf ~/ami-test/test_runs/*

# 保留测试数据以便后续使用
# ~/ami-test/test_data/ 可以保留
```

### 17.8 已知限制

1. **Mock 执行**：当前实现是简化版，只验证脚本能执行，不完全模拟 WorkflowEngine
2. **日志解析**：`analyzer/` 模块是占位符，完整日志解析待后续实现
3. **验证 Agent**：失败分析 Agent 未完整实现，当前只记录错误

### 17.9 测试通过标准

- [ ] CLI 帮助正常显示
- [ ] 配置加载和验证正常
- [ ] Dry-run 模式正常
- [ ] 至少一个 case 完整运行成功
- [ ] 生成的报告结构和内容正确
- [ ] 输出只在 `~/ami-test/test_runs/`，未影响生产数据
- [ ] 历史记录命令正常显示
