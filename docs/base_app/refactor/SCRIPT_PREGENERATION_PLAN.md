# Script Pre-generation: 从运行时生成改为 Workflow 生成时

## 目标

把 scraper_agent 和 browser_agent 的脚本生成逻辑，从"第一次运行 workflow 时生成"改为"在生成 workflow 时一并生成"。

## 设计决策

1. **脚本生成时机**: 在 WorkflowBuilder 生成 workflow 时同步生成脚本
2. **容错策略**: 任一脚本生成失败 → 整体失败（让 Claude 重新思考方案）
3. **关键价值**: Claude 在生成时就能知道脚本是否可行，失败时可以调整策略
   - 例如：hover 按钮点击失败 → 改为 scraper_agent 提取 URL + browser_agent navigate

## 当前架构问题

1. 录制时 `SimpleUserBehaviorMonitor.capture_dom_snapshot()` 捕获 DOM 到**内存**
2. 录制结束时 `upload_recording()` **没有传递 `dom_snapshots`**
3. 结果：云端无 DOM 快照 → 脚本预生成被跳过

## 实施任务 (共 9 个)

| # | 任务 | 修改文件 | 依赖 | 状态 |
|---|------|---------|------|------|
| 1 | Desktop App - 本地保存 DOM 快照 | `cdp_recorder.py` | 无 | ✅ DONE |
| 2 | Desktop App - 读取 DOM 快照 | `storage_manager.py` | 任务1 | ✅ DONE |
| 3 | Desktop App - 上传 DOM 到云端 | `daemon.py` | 任务2 | ✅ DONE |
| 4 | Cloud Backend - 验证 DOM 存储 | 无需修改 | 任务3 | ✅ DONE |
| 5 | Cloud Backend - 脚本生成设计 | 设计文档 | 无 | ✅ DONE |
| 6 | Cloud Backend - WorkflowService 传递 DOM | `workflow_service.py` | 任务4 | ✅ DONE |
| 7 | Cloud Backend - WorkflowBuilder 实现脚本生成 | `workflow_builder.py` | 任务5,6 | ✅ DONE |
| 8 | Cloud Backend - 更新 Skill 文档 | `SKILL.md` | 任务7 | ✅ DONE |
| 9 | Cloud Backend - 清理后台任务 | `main.py` | 任务7 | ✅ DONE |

---

## 任务 1: Desktop App - 本地保存 DOM 快照

**目标**: 录制结束时，DOM 快照保存到本地 recording 目录

**修改文件**: `src/clients/desktop_app/ami_daemon/services/cdp_recorder.py`

**具体修改**:
在 `stop_recording()` 方法中，cleanup 之前：
1. 调用 `self.monitor.get_dom_snapshots()` 获取 DOM
2. 保存到 `recording_path / "dom_snapshots/"` 目录
3. 格式：每个 URL 一个文件 `{url_hash}.json`，内容 `{"url": ..., "dom": ...}`

**验证**:
```bash
ls ~/.ami/users/{user_id}/recordings/{session_id}/dom_snapshots/
```

---

## 任务 2: Desktop App - 读取 DOM 快照

**目标**: `get_recording()` 返回时包含 `dom_snapshots` 字段

**修改文件**: `src/clients/desktop_app/ami_daemon/services/storage_manager.py`

**具体修改**:
1. 修改 `get_recording()` 方法
2. 检查 `recording_path / "dom_snapshots/"` 目录
3. 读取所有 JSON 文件并组装成 `dom_snapshots: Dict[URL, dom_dict]`

---

## 任务 3: Desktop App - 上传 DOM 快照到云端

**目标**: `upload_recording()` 调用时传递 `dom_snapshots` 参数

**修改文件**: `src/clients/desktop_app/ami_daemon/daemon.py`

**位置**: 约 1116 行

**修改**:
```python
dom_snapshots = recording_data.get("dom_snapshots", {})
recording_id = await cloud_client.upload_recording(
    ...,
    dom_snapshots=dom_snapshots
)
```

---

## 任务 4: Cloud Backend - 验证 DOM 存储

**无需修改**: 云端 `save_recording()` 已支持 `dom_snapshots`

**验证**:
```bash
ls ~/ami-server/users/{user_id}/recordings/{recording_id}/dom_snapshots/
```

---

## 任务 5: Cloud Backend - WorkflowBuilder 集成脚本生成 (设计) ✅

### 设计决策

**选择方案 B**: 在 `WorkflowBuilderSession.generate()` 方法中添加脚本生成循环

**理由**:
1. Claude 在生成 workflow 后立即知道脚本是否可行
2. 脚本生成失败时，可以通过 session.chat() 让 Claude 调整策略
3. 复用现有的 `ScriptPregenerationService`，只需添加失败反馈循环

### 流程设计

```
WorkflowService.generate_stream()
  ↓
  WorkflowBuilderSession.generate()
    ↓ (生成 workflow YAML)
    ↓
  _generate_scripts_for_workflow()   ← 新增方法
    ├─ 解析 workflow，找到需要脚本的 steps
    ├─ 对每个 step 调用 ScriptPregenerationService
    ├─ 如果任一脚本失败：
    │     ↓
    │   session.chat(feedback)  ← 让 Claude 调整 step
    │     ↓
    │   重新解析 workflow，重试脚本生成
    └─ 返回最终 workflow + 脚本生成结果
```

### 接口变更

#### WorkflowBuilderSession.generate() 新增参数

```python
async def generate(
    self,
    task_description: str,
    intent_sequence: List[Dict[str, Any]],
    on_progress: Optional[Callable[[StreamEvent], None]] = None,
    user_query: Optional[str] = None,
    dom_snapshots: Optional[Dict[str, Dict]] = None,  # 新增
    workflow_dir: Optional[Path] = None  # 新增：脚本保存目录
) -> GenerationResult:
```

#### GenerationResult 扩展

```python
@dataclass
class GenerationResult:
    success: bool
    workflow: Optional[Dict[str, Any]] = None
    workflow_yaml: Optional[str] = None
    error: Optional[str] = None
    iterations: int = 0
    session_id: Optional[str] = None
    script_generation: Optional[Dict[str, Any]] = None  # 新增：脚本生成结果
```

### 脚本生成失败反馈格式

当脚本生成失败时，发送以下 feedback 给 Claude：

```
Script generation failed for step "{step_id}":
- Agent type: browser_agent
- Operation: click
- Error: No interactive element found for xpath "//button[@class='hover-menu']"

The element might be:
1. Inside a hover/dropdown menu (not visible in initial DOM)
2. Dynamically loaded after page interaction

Suggested alternatives:
- Use scraper_agent to extract the target URL, then browser_agent to navigate
- Add a preceding step to trigger the hover/dropdown
- Use a different selector strategy

Please modify the workflow to handle this case.
```

### 容错策略

**整体失败**: 任一步骤的脚本生成失败 → 给 Claude 反馈 → Claude 调整方案 → 重试

**最大重试次数**: 3 次（与现有 validation 重试逻辑一致）

---

## 任务 6: Cloud Backend - WorkflowService 传递 DOM

**修改文件**: `src/cloud_backend/intent_builder/services/workflow_service.py`

**修改**: 从 recording 加载 DOM 快照，传递给 WorkflowBuilderSession

---

## 任务 7: Cloud Backend - WorkflowBuilder 实现脚本生成

**修改文件**: `src/cloud_backend/intent_builder/agents/workflow_builder.py`

**修改**:
1. 添加 `_generate_step_script()` 方法
2. workflow 生成后遍历 steps 并生成脚本
3. 实现失败反馈循环

---

## 任务 8: Cloud Backend - 更新 Skill 文档

**修改文件**: `src/cloud_backend/intent_builder/.claude/skills/workflow-generation/SKILL.md`

---

## 任务 9: Cloud Backend - 清理后台任务

**修改文件**: `src/cloud_backend/main.py`

**修改**: 移除 `_pregenerate_scripts_background()` 调用

---

## 关键文件

### Desktop App
- `src/clients/desktop_app/ami_daemon/services/cdp_recorder.py`
- `src/clients/desktop_app/ami_daemon/services/storage_manager.py`
- `src/clients/desktop_app/ami_daemon/daemon.py`
- `src/clients/desktop_app/ami_daemon/base_agent/tools/browser_use/user_behavior/monitor.py` (已有 get_dom_snapshots)

### Cloud Backend
- `src/cloud_backend/intent_builder/agents/workflow_builder.py`
- `src/cloud_backend/intent_builder/services/workflow_service.py`
- `src/cloud_backend/main.py`

### 可复用组件
- `src/common/script_generation/browser_script_generator.py`
- `src/common/script_generation/scraper_script_generator.py`
