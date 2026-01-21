# 移除 Script 子目录层级重构方案

**状态**: 已完成 (2025-01-10)
**更新**: 2025-01-10 - 完全移除 resource_id 概念

## 1. 背景与目标

### 1.1 当前目录结构
```
~/.ami/users/{user_id}/workflows/{workflow_id}/
├── workflow.yaml
├── metadata.json
├── dom_snapshots/
│   ├── url_index.json
│   └── {hash}.json
└── {step_id}/
    ├── scraper_script_{hash}/      <-- 要移除这层
    │   ├── extraction_script.py
    │   ├── requirement.json
    │   ├── dom_tools.py
    │   └── dom_data.json
    └── browser_script_{hash}/      <-- 要移除这层
        ├── find_element.py
        ├── find_element_template.py
        ├── test_operation.py
        ├── task.json
        └── dom_data.json
```

### 1.2 目标目录结构
```
~/.ami/users/{user_id}/workflows/{workflow_id}/
├── workflow.yaml
├── metadata.json
├── dom_snapshots/
│   ├── url_index.json
│   └── {hash}.json
└── {step_id}/
    ├── extraction_script.py       (scraper_agent)
    ├── requirement.json           (scraper_agent)
    ├── dom_tools.py               (scraper_agent)
    ├── find_element.py            (browser_agent)
    ├── find_element_template.py   (browser_agent)
    ├── test_operation.py          (browser_agent)
    ├── task.json                  (browser_agent)
    └── dom_data.json              (共用)
```

### 1.3 改动原因
- 简化目录结构，减少路径嵌套层级
- 每个 step 只有一套脚本，不需要 hash 子目录区分
- 便于直接定位和调试脚本文件

---

## 2. 影响范围分析

### 2.1 核心功能模块

| 模块 | 文件 | 影响说明 |
|------|------|----------|
| ScraperAgent | `base_agent/agents/scraper_agent.py` | 脚本路径生成、缓存查找、脚本保存 |
| BrowserAgent | `base_agent/agents/browser_agent.py` | 脚本路径生成、缓存查找、脚本保存 |
| ScriptPregeneration | `intent_builder/services/script_pregeneration_service.py` | 预生成脚本的保存路径 |
| StorageService | `cloud_backend/services/storage_service.py` | 云端存储、会话复制、同步模式 |
| ResourceManager | `common/services/resource_manager.py` | 本地资源路径管理 |
| MetadataGenerator | `common/services/metadata_generator.py` | 元数据扫描生成 |
| ScraperContextService | `intent_builder/services/scraper_context_service.py` | 脚本目录查找 |

### 2.2 测试模块

| 模块 | 文件 | 影响说明 |
|------|------|----------|
| MockAgents | `test/mock/mock_agents.py` | 脚本目录查找 |
| WorkflowValidator | `test/validator/workflow_validator.py` | 脚本验证路径 |
| TestRunner | `test/runner/test_runner.py` | DOM 文件查找 |

### 2.3 API 和客户端

| 模块 | 文件 | 影响说明 |
|------|------|----------|
| CloudBackend API | `cloud_backend/main.py` | 脚本生成 API 路径参数 |
| CloudClient | `ami_daemon/services/cloud_client.py` | 文件下载路径 |

### 2.4 Skills 和文档

| 文件 | 影响说明 |
|------|----------|
| `skills/repository/scraper-fix/SKILL.md` | 目录结构说明 |
| 各模块 `CONTEXT.md` | 目录结构示例 |

---

## 3. 详细修改清单

### 3.1 ScraperAgent (`scraper_agent.py`)

#### 3.1.1 `_generate_script_key()` 方法 (行 1450-1488)

**当前实现**:
```python
def _generate_script_key(self, data_requirements: Dict) -> str:
    # ... 获取 context 信息 ...

    # 生成 hash
    content = f"scraper:{user_desc}:{json.dumps(output_format, sort_keys=True)}"
    hash_suffix = hashlib.md5(content.encode()).hexdigest()[:8]
    script_key = f"scraper_script_{hash_suffix}"

    # 构建路径: users/{user_id}/workflows/{workflow_id}/{step_id}/scraper_script_{hash}
    script_path = f"users/{user_id}/workflows/{workflow_id}/{step_id}/{script_key}"
    return script_path
```

**修改后**:
```python
def _generate_script_key(self, data_requirements: Dict) -> str:
    # ... 获取 context 信息 ...

    # 生成 hash (仅用于检测脚本是否需要重新生成)
    content = f"scraper:{user_desc}:{json.dumps(output_format, sort_keys=True)}"
    self._current_script_hash = hashlib.md5(content.encode()).hexdigest()[:8]

    # 构建路径: users/{user_id}/workflows/{workflow_id}/{step_id}
    # 不再包含 scraper_script_{hash} 子目录
    script_path = f"users/{user_id}/workflows/{workflow_id}/{step_id}"
    return script_path
```

#### 3.1.2 `_extract_with_script()` 方法 (行 796-927)

**当前实现**:
```python
scripts_root = self.config_service.get_path("data.scripts")
script_workspace = scripts_root / script_key  # script_key 包含 scraper_script_{hash}
script_file = script_workspace / "extraction_script.py"
```

**修改后**:
```python
scripts_root = self.config_service.get_path("data.scripts")
script_workspace = scripts_root / script_key  # script_key 现在直接是 step 目录
script_file = script_workspace / "extraction_script.py"
# 无需改变文件操作逻辑，只是 script_key 路径变短了
```

#### 3.1.3 云端脚本保存 (行 1308-1338)

**当前实现**:
```python
local_script_dir = scripts_root / self._current_script_key
# self._current_script_key = users/.../step_id/scraper_script_xxx
```

**修改后**:
```python
local_script_dir = scripts_root / self._current_script_key
# self._current_script_key = users/.../step_id
# 文件直接保存到 step 目录
```

---

### 3.2 BrowserAgent (`browser_agent.py`)

#### 3.2.1 `_generate_script_key()` 方法 (行 530-575)

**当前实现**:
```python
def _generate_script_key(self, task: str, xpath_hints: Dict[str, str]) -> str:
    # ... 获取 context 信息 ...

    content = f"browser:{task}:{json.dumps(xpath_hints, sort_keys=True)}"
    hash_suffix = hashlib.md5(content.encode()).hexdigest()[:8]
    script_key = f"browser_script_{hash_suffix}"

    # 返回: users/{user_id}/workflows/{workflow_id}/{step_id}/browser_script_{hash}
    return f"users/{user_id}/workflows/{workflow_id}/{step_id}/{script_key}"
```

**修改后**:
```python
def _generate_script_key(self, task: str, xpath_hints: Dict[str, str]) -> str:
    # ... 获取 context 信息 ...

    # hash 仅用于检测是否需要重新生成
    content = f"browser:{task}:{json.dumps(xpath_hints, sort_keys=True)}"
    self._current_script_hash = hashlib.md5(content.encode()).hexdigest()[:8]

    # 返回: users/{user_id}/workflows/{workflow_id}/{step_id}
    return f"users/{user_id}/workflows/{workflow_id}/{step_id}"
```

#### 3.2.2 `_generate_operation_script()` 方法 (行 1040-1187)

无需修改核心逻辑，因为 `working_dir` 的计算方式相同：
```python
working_dir = scripts_root / script_key
```
只是 `script_key` 的值变短了。

---

### 3.3 ScriptPregenerationService (`script_pregeneration_service.py`)

#### 3.3.1 `_generate_browser_script()` 方法 (行 450-494)

**当前实现**:
```python
script_key = self._generate_script_key("browser", task_desc, xpath_hints)
working_dir = workflow_dir / step_id / f"browser_script_{script_key}"
```

**修改后**:
```python
# 不再需要 script_key 作为子目录名
working_dir = workflow_dir / step_id
```

#### 3.3.2 `_generate_scraper_script()` 方法 (行 496-546)

**当前实现**:
```python
script_key = self._generate_script_key("scraper", user_description, output_format)
working_dir = workflow_dir / step_id / f"scraper_script_{script_key}"
```

**修改后**:
```python
# 不再需要 script_key 作为子目录名
working_dir = workflow_dir / step_id
```

#### 3.3.3 `_generate_script_key()` 方法 (行 548-556)

此方法可以保留用于其他用途（如日志），或直接删除。

---

### 3.4 StorageService (`storage_service.py`)

#### 3.4.1 `copy_workflow_to_session()` 方法 (行 208-268)

注释更新:
```python
# 原: {step_id}/scraper_script_xxx/ directories
# 新: {step_id}/ directories (直接包含脚本文件)
```

#### 3.4.2 `_populate_dom_data_from_snapshots()` 方法 (行 270-346)

**当前实现**:
```python
# Find scraper_script_xxx directory
script_dirs = list(step_dir.glob("scraper_script_*"))
if not script_dirs:
    continue
script_dir = script_dirs[0]
dom_data_file = script_dir / "dom_data.json"
```

**修改后**:
```python
# 直接在 step 目录下操作
dom_data_file = step_dir / "dom_data.json"
```

#### 3.4.3 `sync_session_to_workflow()` 方法 (行 347-430)

**当前实现**:
```python
sync_patterns = [
    "workflow.yaml",
    "*/scraper_script_*/extraction_script.py",
    "*/scraper_script_*/dom_tools.py",
]
```

**修改后**:
```python
sync_patterns = [
    "workflow.yaml",
    "*/extraction_script.py",
    "*/dom_tools.py",
]
```

#### 3.4.4 `_scan_workflow_resources()` 方法 (行 1040-1080)

**当前实现**:
```python
for resource_dir in step_dir.iterdir():
    if resource_dir.name.startswith("scraper_script_"):
        extraction_script = resource_dir / "extraction_script.py"
```

**修改后**:
```python
# 直接检查 step 目录下的脚本文件
extraction_script = step_dir / "extraction_script.py"
if extraction_script.exists():
    # 处理资源
```

---

### 3.5 ResourceManager (`resource_manager.py`)

#### 3.5.1 `get_local_resource_path()` 方法 (行 64-74)

**当前签名**:
```python
def get_local_resource_path(
    self,
    user_id: str,
    workflow_id: str,
    step_id: str,
    resource_type: ResourceType,
    resource_id: str  # 如 "scraper_script_abc123"
) -> Path:
    return workflow_path / step_id / resource_id
```

**修改后**:
```python
def get_local_resource_path(
    self,
    user_id: str,
    workflow_id: str,
    step_id: str,
    resource_type: ResourceType
    # 移除 resource_id 参数
) -> Path:
    return workflow_path / step_id
```

#### 3.5.2 相关方法调用更新

需要更新所有调用 `get_local_resource_path()` 的地方，移除 `resource_id` 参数。

---

### 3.6 ResourceTypes (`resource_types.py`)

**当前实现**:
```python
class ResourceConfig:
    SYNC_FILES = {
        ResourceType.SCRAPER_SCRIPT: [
            "extraction_script.py",
            "requirement.json",
            "test_extraction.py"
        ],
        # ...
    }
```

无需修改，同步文件列表保持不变。

---

### 3.7 MetadataGenerator (`metadata_generator.py`)

#### 3.7.1 `_scan_scraper_scripts()` 方法 (行 79-143)

**当前实现**:
```python
for resource_dir in step_dir.iterdir():
    if not resource_dir.name.startswith("scraper_script_"):
        continue
    resource_id = resource_dir.name
    extraction_script = resource_dir / "extraction_script.py"
```

**修改后**:
```python
# 直接检查 step 目录
extraction_script = step_dir / "extraction_script.py"
if extraction_script.exists():
    # step_id 即为资源标识
    resource_id = step_id  # 或直接移除 resource_id 概念
```

---

### 3.8 ScraperContextService (`scraper_context_service.py`)

#### 3.8.1 `ScraperStepInfo` 数据类 (行 30-34)

**当前实现**:
```python
@dataclass
class ScraperStepInfo:
    step_id: str
    script_dir: str  # "step_id/scraper_script_xxx"
```

**修改后**:
```python
@dataclass
class ScraperStepInfo:
    step_id: str
    script_dir: str  # 直接是 step_id
```

#### 3.8.2 `_find_script_dir()` 方法 (行 263-277)

**当前实现**:
```python
def _find_script_dir(self, step_dir: Path) -> Optional[Path]:
    for child in step_dir.iterdir():
        if child.is_dir() and child.name.startswith("scraper_script_"):
            return child
    return None
```

**修改后**:
```python
def _find_script_dir(self, step_dir: Path) -> Optional[Path]:
    # 直接返回 step_dir，如果包含必要的脚本文件
    if (step_dir / "extraction_script.py").exists():
        return step_dir
    return None
```

---

### 3.9 Cloud Backend Main (`main.py`)

#### 3.9.1 脚本生成 API (行 2580-2650)

**当前实现**:
```python
script_key = f"scraper_script_{hashlib.md5(content.encode()).hexdigest()[:8]}"
script_path = f"{step_id}/{script_key}"
working_dir = workflow_dir / step_id / script_key
```

**修改后**:
```python
# 不再生成子目录
script_path = step_id
working_dir = workflow_dir / step_id
```

---

### 3.10 Test Modules

#### 3.10.1 MockAgents (`test/mock/mock_agents.py`)

**当前实现** (行 194-202):
```python
step_dir = Path(self.scripts_dir) / step_id
if step_dir.exists():
    script_dirs = list(step_dir.glob("scraper_script_*"))
    if script_dirs:
        script_dir = script_dirs[0]
        script_file = script_dir / "extraction_script.py"
```

**修改后**:
```python
step_dir = Path(self.scripts_dir) / step_id
if step_dir.exists():
    script_file = step_dir / "extraction_script.py"
    if script_file.exists():
        # 直接使用
```

#### 3.10.2 WorkflowValidator (`test/validator/workflow_validator.py`)

**当前实现** (行 238-249):
```python
script_dirs = list(step_dir.glob("scraper_script_*"))
if not script_dirs:
    return ScriptValidationResult(...)
script_dir = script_dirs[0]
```

**修改后**:
```python
# 直接使用 step_dir
script_file = step_dir / "extraction_script.py"
if not script_file.exists():
    return ScriptValidationResult(...)
script_dir = step_dir
```

**Browser 脚本验证** (行 263-270):
```python
# 原: script_dirs = list(step_dir.glob("find_element_*"))
# 新: 直接检查 find_element.py
script_file = step_dir / "find_element.py"
```

#### 3.10.3 TestRunner (`test/runner/test_runner.py`)

更新遍历逻辑，不再遍历 `scraper_script_*` 或 `browser_script_*` 子目录。

---

### 3.11 Skills 文档

#### `scraper-fix/SKILL.md`

更新目录结构示例:
```markdown
# 原
└── {step_id}/
    └── scraper_script_{hash}/
        ├── extraction_script.py
        └── ...

# 新
└── {step_id}/
    ├── extraction_script.py
    └── ...
```

---

## 4. 修改顺序建议

1. **Phase 1: 核心 Agent 修改**
   - `scraper_agent.py`
   - `browser_agent.py`

2. **Phase 2: 预生成服务修改**
   - `script_pregeneration_service.py`

3. **Phase 3: 存储和同步修改**
   - `storage_service.py`
   - `resource_manager.py`
   - `metadata_generator.py`
   - `scraper_context_service.py`

4. **Phase 4: API 层修改**
   - `cloud_backend/main.py`
   - `cloud_client.py`

5. **Phase 5: 测试模块修改**
   - `mock_agents.py`
   - `workflow_validator.py`
   - `test_runner.py`

6. **Phase 6: 文档更新**
   - 各 `CONTEXT.md`
   - `SKILL.md`

---

## 5. 兼容性考虑

### 5.1 已有数据迁移

如果有已存在的 workflow 数据使用旧结构，需要:
1. 编写迁移脚本，将文件从 `step_id/scraper_script_xxx/` 移动到 `step_id/`
2. 或者在代码中添加向后兼容逻辑（不推荐）

### 5.2 云端数据同步

确保云端和本地使用相同的目录结构，避免同步冲突。

---

## 6. 测试计划

1. 单元测试: 验证路径生成逻辑
2. 集成测试: 验证脚本生成和执行流程
3. 端到端测试: 验证完整的 workflow 执行
4. 回归测试: 确保现有功能不受影响

---

## 7. 第二阶段：完全移除 resource_id

### 7.1 背景

在第一阶段完成后，代码中仍然保留了 `resource_id` 的概念，但实际上 `resource_id` 的值被设置为与 `step_id` 相同。这导致了路径重复嵌套的问题（如 `step_id/step_id/filename`）。

为了彻底简化代码，第二阶段完全移除了 `resource_id` 概念。

### 7.2 修改的文件

#### 7.2.1 storage_service.py

**移除的参数:**
- `get_resource_path()` - 移除 `resource_id` 参数
- `save_workflow_resource()` - 移除 `resource_id` 参数
- `load_workflow_resource()` - 移除 `resource_id` 参数

**路径变化:**
```python
# 旧: workflow_path / step_id / resource_id
# 新: workflow_path / step_id
```

**元数据结构变化:**
```python
# 旧
{
    "step_id": "step_1",
    "resource_id": "step_1",  # 冗余
    "files": [...]
}

# 新
{
    "step_id": "step_1",
    "files": [...]
}
```

#### 7.2.2 resource_manager.py

**移除的参数:**
- `get_local_resource_path()` - 移除 `resource_id` 参数
- `save_resource_local()` - 移除 `resource_id` 参数
- `load_resource_local()` - 移除 `resource_id` 参数
- `update_workflow_metadata()` - 移除 `resource_id` 参数

**ResourceInfo 数据类更新:**
```python
# 旧
@dataclass
class ResourceInfo:
    step_id: str
    resource_id: str  # 已移除
    resource_type: ResourceType
    files: List[str]
    created_at: str
    updated_at: str

# 新
@dataclass
class ResourceInfo:
    step_id: str
    resource_type: ResourceType
    files: List[str]
    created_at: str
    updated_at: str
```

**upload_resources() 和 download_resources() 方法更新:**
- 移除了对 `resource_id` 的读取和使用
- 日志信息从 `Resource: {step_id}/{resource_id}` 改为 `Resource: step {step_id}`

#### 7.2.3 metadata_generator.py

**生成的元数据结构更新:**
```python
# 旧
scraper_scripts.append({
    "step_id": step_id,
    "resource_id": step_id,  # 已移除
    "files": files,
    ...
})

# 新
scraper_scripts.append({
    "step_id": step_id,
    "files": files,
    ...
})
```

#### 7.2.4 main.py (cloud_backend)

**API 返回的资源条目更新:**
```python
# 旧
resource_entry = {
    "step_id": request.step_id,
    "resource_id": request.step_id,  # 已移除
    "files": files_to_sync
}

# 新
resource_entry = {
    "step_id": request.step_id,
    "files": files_to_sync
}
```

#### 7.2.5 daemon.py

**下载逻辑更新:**
```python
# 旧
step_id = resource.get("step_id")
resource_id = resource.get("resource_id")
file_path = f"{step_id}/{resource_id}/{filename}"
local_file_path = local_workflow_path / step_id / resource_id / filename

# 新
step_id = resource.get("step_id")
file_path = f"{step_id}/{filename}"
local_file_path = local_workflow_path / step_id / filename
```

**上传逻辑更新:**
```python
# 旧
step_id = resource.get("step_id")
resource_id = resource.get("resource_id")
resource_path = local_workflow_path / step_id / resource_id
file_path = f"{step_id}/{resource_id}/{rel_path}"

# 新
step_id = resource.get("step_id")
resource_path = local_workflow_path / step_id
file_path = f"{step_id}/{rel_path}"
```

### 7.3 最终目录结构

```
~/.ami/users/{user_id}/workflows/{workflow_id}/
├── workflow.yaml
├── metadata.json
├── dom_snapshots/
│   ├── url_index.json
│   └── {hash}.json
└── {step_id}/                      # 直接是 step 目录
    ├── extraction_script.py        # scraper 脚本
    ├── requirement.json            # scraper 需求定义
    ├── dom_tools.py                # DOM 工具
    ├── find_element.py             # browser 脚本
    ├── task.json                   # browser 任务定义
    └── dom_data.json               # DOM 数据
```

### 7.4 metadata.json 结构

```json
{
    "workflow_id": "workflow_123",
    "created_at": "2025-01-10T10:00:00Z",
    "updated_at": "2025-01-10T12:00:00Z",
    "resources": {
        "scraper_script": [
            {
                "step_id": "step_1",
                "files": ["extraction_script.py", "requirement.json", "dom_tools.py"],
                "created_at": "2025-01-10T10:00:00Z",
                "updated_at": "2025-01-10T12:00:00Z"
            }
        ],
        "browser_script": [
            {
                "step_id": "step_2",
                "files": ["find_element.py", "task.json"],
                "created_at": "2025-01-10T11:00:00Z",
                "updated_at": "2025-01-10T12:00:00Z"
            }
        ]
    }
}
```

### 7.5 缓存验证机制

为防止 workflow 需求变更时使用过期脚本，已在 Agent 中添加缓存验证：

**ScraperAgent._is_cache_valid():**
- 比较当前 requirement.json 的哈希与已保存的哈希
- 哈希不匹配时强制重新生成脚本

**BrowserAgent._is_cache_valid():**
- 比较当前 task.json 的哈希与已保存的哈希
- 哈希不匹配时强制重新生成脚本

### 7.6 不兼容变更

此次重构是 **破坏性变更**，不保留向后兼容性：

1. 旧的 metadata.json 中包含 `resource_id` 字段的数据将被忽略
2. 旧的嵌套目录结构需要手动迁移或重新生成
3. 云端和本地需要同时更新以避免同步问题

### 7.7 数据迁移

如需迁移旧数据，可以：

1. 删除本地 `~/.ami/` 目录，让系统从云端重新同步
2. 或编写迁移脚本将文件从 `step_id/scraper_script_xxx/` 移动到 `step_id/`
3. 更新 metadata.json，移除 `resource_id` 字段

---

## 8. 后续修复

### 8.1 dom_tools.py 同步问题

**问题**: `dom_tools.py` 未包含在 `SYNC_FILES` 中，导致云端和本地同步时缺少此文件。

**修复**: 在 `resource_types.py` 的 `SYNC_FILES` 中添加 `dom_tools.py`：

```python
SYNC_FILES = {
    ResourceType.SCRAPER_SCRIPT: [
        "extraction_script.py",
        "requirement.json",
        "test_extraction.py",
        "dom_tools.py"  # 新增
    ],
    ...
}
```

### 8.2 timestamp 不必要更新问题

**问题**: `storage_service.py` 的 `update_workflow_resources()` 方法每次调用都会更新 `updated_at`，即使资源没有实际变化，可能导致不必要的同步循环。

**修复**: 添加资源变化检测，只有在资源确实变化时才更新时间戳：

```python
# Check if resources actually changed
old_resources = metadata.get("resources", {})
resources_changed = old_resources != resources

# Only update updated_at if resources actually changed
if resources_changed:
    metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
```
