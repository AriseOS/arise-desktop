# 统一同步服务设计方案

**状态**: 设计中
**创建**: 2025-01-10
**作者**: Claude

## 1. 背景与问题

### 1.1 当前同步机制的问题

通过代码分析，发现当前的文件同步系统存在以下问题：

#### Bug 列表

| # | 位置 | 问题描述 | 严重程度 |
|---|------|---------|---------|
| 1 | `resource_manager.py:285-290` | 时间戳使用字符串比较而非解析后比较 | 高 |
| 2 | `cloud_client.py:186` | `workflow_id is not None or workflow_id == ""` 逻辑错误（永远为 True） | 高 |
| 3 | `storage_manager.py:111-115` | workflow_id 清除逻辑混乱，无法通过 `None` 清除 | 中 |
| 4 | `storage_service.py:337-403` | `sync_session_to_workflow` 后只更新顶层时间戳，不更新 resources 时间戳 | 低 |

#### 设计问题

| # | 问题 | 影响 |
|---|------|-----|
| 1 | `ResourceManager` 已实现但未使用 | 代码冗余，维护成本 |
| 2 | `SimpleSync` 已实现但未使用 | 代码冗余 |
| 3 | 同步逻辑分散在 5+ 个位置 | 难以维护，容易出错 |
| 4 | Recording 元数据存储在两个文件 | 数据不一致风险 |
| 5 | 三套并行的存储管理服务 | 职责不清，重复实现 |

### 1.2 当前同步触发点

| # | 场景 | 触发条件 | 位置 | 方向 |
|---|------|---------|------|-----|
| 1 | Recording 上传 | 用户点击上传 | daemon.py:1256 | 上传 |
| 2 | Recording 元数据更新 | 修改描述 | daemon.py:1036/1162 | 上传 |
| 3 | Recording 时间戳同步 | 获取详情 | daemon.py:1150-1172 | 双向 |
| 4 | Recording 删除 | 删除本地 | daemon.py:1209 | 上传删除 |
| 5 | Workflow 自动同步 | 打开详情 | daemon.py:2392 | 双向 |
| 6 | Workflow 下载 | 云端更新 | daemon.py:1382/1419 | 下载 |
| 7 | Workflow 上传 | 本地更新 | daemon.py:1497/1544 | 上传 |
| 8 | 会话→Workflow 同步 | 对话完成 | main.py:1546 | 上传 |
| 9 | 脚本生成后更新 | 脚本生成 | main.py:1304 | 更新元数据 |
| 10 | 显式同步 | 用户点击 | daemon.py:1660 | 双向 |

---

## 2. 设计目标

1. **单一入口**: 所有同步操作通过统一的 `SyncService` 处理
2. **统一时间戳逻辑**: 使用 `parse_timestamp()` 确保正确的时间比较
3. **消除冗余**: 删除未使用的 `ResourceManager` 和 `SimpleSync`
4. **简化元数据**: 每个资源只有一个 `updated_at`
5. **向后兼容**: 保持现有 API 端点不变

---

## 3. 系统架构

### 3.1 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Desktop App (daemon.py)                   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    SyncService (新)                        │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │   │
│  │  │ Recording   │  │ Workflow    │  │ Execution Log   │   │   │
│  │  │ Sync        │  │ Sync        │  │ Upload          │   │   │
│  │  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘   │   │
│  │         │                │                   │            │   │
│  │         └────────────────┼───────────────────┘            │   │
│  │                          │                                 │   │
│  │                   ┌──────▼──────┐                         │   │
│  │                   │ CloudClient │ (HTTP)                  │   │
│  │                   └──────┬──────┘                         │   │
│  └──────────────────────────┼────────────────────────────────┘   │
│                              │                                    │
│  ┌──────────────────────────┼────────────────────────────────┐   │
│  │                   StorageManager                           │   │
│  │           (本地文件系统: ~/.ami)                            │   │
│  └────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
                               │
                               │ HTTPS
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Cloud Backend (main.py)                      │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                     StorageService                          │  │
│  │             (云端文件系统: ~/ami-server)                     │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 模块职责

| 模块 | 职责 | 变更 |
|------|-----|-----|
| `SyncService` | 统一同步入口，协调所有同步操作 | **新增** |
| `StorageManager` | 本地文件 CRUD 操作 | 保留，简化 |
| `CloudClient` | HTTP API 调用 | 保留，修复 bug |
| `StorageService` | 云端文件 CRUD 操作 | 保留 |
| `ResourceManager` | - | **删除** |
| `SimpleSync` | - | **删除** |

---

## 4. SyncService 接口设计

### 4.1 核心类型定义

```python
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime


class SyncDirection(Enum):
    """同步方向"""
    UPLOAD = "upload"      # 本地 → 云端
    DOWNLOAD = "download"  # 云端 → 本地
    NONE = "none"          # 无需同步
    CONFLICT = "conflict"  # 冲突


class ResourceType(Enum):
    """可同步的资源类型"""
    RECORDING = "recording"
    WORKFLOW = "workflow"
    EXECUTION_LOG = "execution_log"


@dataclass
class SyncStatus:
    """同步状态"""
    resource_type: ResourceType
    resource_id: str
    direction: SyncDirection
    local_updated_at: Optional[datetime]
    cloud_updated_at: Optional[datetime]
    needs_sync: bool
    message: str


@dataclass
class SyncResult:
    """同步结果"""
    success: bool
    direction: SyncDirection
    synced_files: List[str]
    errors: List[str]
    message: str
```

### 4.2 SyncService 类

```python
class SyncService:
    """统一同步服务"""

    def __init__(
        self,
        storage_manager: "StorageManager",
        cloud_client: "CloudClient"
    ):
        self.storage = storage_manager
        self.cloud = cloud_client

    # ===== 核心公开方法 =====

    async def check_sync_status(
        self,
        resource_type: ResourceType,
        resource_id: str,
        user_id: str
    ) -> SyncStatus:
        """检查资源的同步状态"""
        pass

    async def sync(
        self,
        resource_type: ResourceType,
        resource_id: str,
        user_id: str,
        force_direction: Optional[SyncDirection] = None
    ) -> SyncResult:
        """执行同步"""
        pass

    async def sync_all_pending(
        self,
        user_id: str
    ) -> Dict[str, SyncResult]:
        """同步所有待同步的资源"""
        pass

    # ===== 内部方法 =====

    def _compare_timestamps(
        self,
        local_dt: Optional[datetime],
        cloud_dt: Optional[datetime]
    ) -> SyncDirection:
        """
        统一的时间戳比较逻辑

        规则:
        - 都为空 → NONE
        - 本地为空 → DOWNLOAD
        - 云端为空 → UPLOAD
        - 本地更新 → UPLOAD
        - 云端更新 → DOWNLOAD
        - 相同 → NONE
        """
        pass
```

### 4.3 时间戳比较逻辑（关键）

```python
from src.common.timestamp_utils import parse_timestamp

def _compare_timestamps(
    self,
    local_dt: Optional[datetime],
    cloud_dt: Optional[datetime]
) -> SyncDirection:
    """统一的时间戳比较 - 解决 Bug #1"""

    if local_dt is None and cloud_dt is None:
        return SyncDirection.NONE
    elif local_dt is None:
        return SyncDirection.DOWNLOAD
    elif cloud_dt is None:
        return SyncDirection.UPLOAD
    elif local_dt > cloud_dt:
        return SyncDirection.UPLOAD
    elif cloud_dt > local_dt:
        return SyncDirection.DOWNLOAD
    else:
        return SyncDirection.NONE
```

---

## 5. 元数据结构简化

### 5.1 Recording 元数据

**当前问题**: 元数据分散在 `operations.json` 和 `metadata.json` 两个文件中。

**新结构**: 统一到 `metadata.json`

```
~/.ami/users/{user_id}/recordings/{recording_id}/
├── operations.json     # 只存储操作数据
└── metadata.json       # 所有元数据（新）
```

**metadata.json 内容**:
```json
{
  "recording_id": "session_abc123",
  "workflow_id": "workflow_xyz789",
  "task_description": "Extract product prices",
  "user_query": "Get all prices and save to Excel",
  "name": "Product Price Extraction",
  "created_at": "2025-01-10T10:30:00+00:00",
  "updated_at": "2025-01-10T11:45:00+00:00"
}
```

**operations.json 内容**（简化后）:
```json
{
  "recording_id": "session_abc123",
  "operations": [...]
}
```

### 5.2 Workflow 元数据

**当前问题**: 每个 resource 有独立的 `updated_at`，导致时间戳管理复杂。

**新结构**: 只保留顶层 `updated_at`

```json
{
  "workflow_id": "workflow_xyz789",
  "workflow_name": "Product Price Extractor",
  "source_recording_id": "session_abc123",
  "created_at": "2025-01-10T10:30:00+00:00",
  "updated_at": "2025-01-10T11:45:00+00:00",
  "resources": {
    "scraper_scripts": [
      {
        "step_id": "extract-prices",
        "files": ["extraction_script.py", "dom_tools.py", "requirement.json"]
      }
    ],
    "browser_scripts": [
      {
        "step_id": "navigate-to-page",
        "files": ["find_element.py", "task.json"]
      }
    ]
  }
}
```

**删除的字段**:
- `resources.scraper_scripts[].created_at`
- `resources.scraper_scripts[].updated_at`
- `script_pregeneration`（临时状态，不需要持久化）

---

## 6. API 设计

### 6.1 新增 API 端点（daemon.py）

```python
# ===== 同步 API =====

@app.get("/api/v1/sync/status")
async def get_sync_status(
    resource_type: str,  # "recording" | "workflow"
    resource_id: str,
    user_id: str
) -> SyncStatus:
    """获取资源的同步状态"""
    pass


@app.post("/api/v1/sync")
async def sync_resource(
    resource_type: str,
    resource_id: str,
    user_id: str,
    direction: Optional[str] = None  # "upload" | "download" | null
) -> SyncResult:
    """同步指定资源"""
    pass


@app.post("/api/v1/sync/all")
async def sync_all(user_id: str) -> Dict[str, SyncResult]:
    """同步所有待同步的资源"""
    pass
```

### 6.2 保留的现有端点

以下端点保留，内部实现改为调用 `SyncService`：

```
# Recording
POST   /api/v1/recordings/{session_id}/upload
PATCH  /api/v1/recordings/{recording_id}
DELETE /api/v1/recordings/{session_id}/workflow

# Workflow
GET    /api/v1/workflows/{workflow_id}/metadata
PUT    /api/v1/workflows/{workflow_id}/metadata
GET    /api/v1/workflows/{workflow_id}/files
PUT    /api/v1/workflows/{workflow_id}/files
POST   /api/v1/workflows/{workflow_id}/sync
```

---

## 7. 同步策略

### 7.1 自动同步时机

| 时机 | 触发条件 | 操作 |
|------|---------|-----|
| 打开 Recording 详情 | 用户点击 | `sync_service.sync(RECORDING, ...)` |
| 打开 Workflow 详情 | 用户点击 | `sync_service.sync(WORKFLOW, ...)` |
| 保存 Recording 元数据 | 用户修改 | `sync_service.sync(RECORDING, ..., UPLOAD)` |
| Workflow 生成完成 | AI 生成后 | 云端更新 metadata |
| Workflow 会话结束 | 关闭会话 | `storage_service.sync_session_to_workflow()` |

### 7.2 手动同步

用户可在 UI 中选择：
- **Auto**: 根据时间戳自动决定
- **Upload**: 强制上传
- **Download**: 强制下载

### 7.3 后台同步（可选）

```python
async def background_sync_task():
    """每 5 分钟检查待同步资源"""
    while True:
        try:
            await sync_service.sync_all_pending(default_user_id)
        except Exception as e:
            logger.warning(f"Background sync failed: {e}")
        await asyncio.sleep(300)
```

---

## 8. 实现计划

### Phase 1: 创建 SyncService（不破坏现有代码）

**文件变更**:
- 新增: `src/clients/desktop_app/ami_daemon/services/sync_service.py`

**步骤**:
1. 创建 `SyncService` 类，实现所有核心方法
2. 在 `daemon.py` 的 lifespan 中初始化
3. 添加新的 `/api/v1/sync/*` 端点
4. 测试新端点

**预计工作量**: 1-2 天

### Phase 2: 迁移现有同步代码

**文件变更**:
- 修改: `daemon.py`（多处）

**步骤**:
1. Recording 同步迁移
   - `get_recording_detail()` 中的同步逻辑
   - `update_recording_metadata()` 中的同步逻辑
   - `clear_recording_workflow()` 中的同步逻辑
2. Workflow 同步迁移
   - `get_workflow_detail()` 中的同步逻辑
   - `sync_workflow()` 中的逻辑
3. 端到端测试

**预计工作量**: 2-3 天

### Phase 3: 清理冗余代码

**文件变更**:
- 删除: `src/common/services/resource_manager.py`
- 删除: `src/common/services/simple_sync.py`
- 修改: `src/clients/desktop_app/ami_daemon/services/storage_manager.py`
- 修改: `src/clients/desktop_app/ami_daemon/services/cloud_client.py`

**步骤**:
1. 删除未使用的模块
2. 简化 `StorageManager`
3. 修复 `cloud_client.py:186` bug
4. 修复 `storage_manager.py:111-115` bug
5. 简化元数据结构（可选，需要数据迁移）

**预计工作量**: 1-2 天

### Phase 4: 文档和优化

**文件变更**:
- 更新: 各模块 `CONTEXT.md`
- 更新: 本文档状态

**步骤**:
1. 添加同步日志格式规范
2. 更新相关 CONTEXT.md
3. 可选：添加后台同步任务

**预计工作量**: 0.5 天

---

## 9. 文件变更汇总

```
新增:
+ src/clients/desktop_app/ami_daemon/services/sync_service.py

修改:
~ src/clients/desktop_app/ami_daemon/daemon.py           # 集成 SyncService
~ src/clients/desktop_app/ami_daemon/services/storage_manager.py  # 简化
~ src/clients/desktop_app/ami_daemon/services/cloud_client.py     # 修复 bug

删除:
- src/common/services/resource_manager.py
- src/common/services/simple_sync.py
```

---

## 10. 向后兼容性

### 10.1 API 兼容

所有现有 API 端点保留，内部改为调用 `SyncService`。

### 10.2 数据兼容

元数据结构变更采用渐进式迁移：

```python
def _migrate_recording_metadata(recording_data: dict) -> dict:
    """迁移旧格式的 Recording 元数据"""
    if "task_metadata" in recording_data:
        # 旧格式：元数据在 operations.json 中
        return {
            "recording_id": recording_data.get("session_id"),
            "workflow_id": recording_data.get("workflow_id"),
            "task_description": recording_data.get("task_metadata", {}).get("task_description"),
            "user_query": recording_data.get("task_metadata", {}).get("user_query"),
            "name": recording_data.get("task_metadata", {}).get("name"),
            "created_at": recording_data.get("created_at"),
            "updated_at": recording_data.get("updated_at")
        }
    return recording_data  # 新格式
```

---

## 11. 讨论点

### 11.1 是否需要后台同步？

**方案 A**: 只在用户操作时触发同步（当前方案）
- 优点：简单，资源消耗低
- 缺点：用户可能看到过期数据

**方案 B**: 添加后台定时同步
- 优点：数据更及时
- 缺点：增加复杂性，可能有并发问题

**建议**: Phase 1-3 不实现后台同步，Phase 4 根据需求决定。

### 11.2 元数据迁移策略

**方案 A**: 渐进式迁移（读取时兼容旧格式）
- 优点：无需批量迁移
- 缺点：代码需要处理两种格式

**方案 B**: 一次性迁移（编写迁移脚本）
- 优点：代码简洁
- 缺点：需要停机迁移

**建议**: 采用方案 A，长期逐步过渡。

### 11.3 冲突处理策略

**当前设计**: 检测到冲突时，要求用户指定方向。

**是否需要更复杂的合并策略？**
- Recording：元数据冲突概率低，简单覆盖即可
- Workflow：脚本文件冲突需要考虑，但通常由单一方修改

**建议**: 保持简单策略，冲突时让用户选择。

---

## 12. 附录

### 12.1 当前代码中的同步逻辑位置

```
daemon.py:
  - 1036: clear_recording_workflow → cloud_client.update_recording_metadata
  - 1150-1172: get_recording_detail → 双向同步
  - 1162: get_recording_detail → cloud_client.update_recording_metadata
  - 1209: delete_recording → cloud_client.delete_recording
  - 1256: upload_recording → cloud_client.upload_recording
  - 1320-1344: sync_workflow_resources → 检查方向
  - 1356-1460: download_from_cloud → cloud_client.download_workflow_file
  - 1465-1560: upload_to_cloud → cloud_client.upload_workflow_file
  - 1660-1707: sync_workflow → 显式同步
  - 2392: get_workflow_detail → sync_workflow_resources

main.py:
  - 656-665: 脚本预生成后更新 metadata
  - 1304: 生成后 update_workflow_resources
  - 1546: chat 后 sync_session_to_workflow
```

### 12.2 相关文件路径

```
src/
├── clients/desktop_app/ami_daemon/
│   ├── daemon.py                      # 主应用
│   └── services/
│       ├── cloud_client.py            # HTTP 客户端
│       ├── storage_manager.py         # 本地存储
│       └── sync_service.py            # 新增
├── cloud_backend/
│   ├── main.py                        # API 端点
│   └── services/
│       └── storage_service.py         # 云端存储
└── common/
    ├── timestamp_utils.py             # 时间戳工具
    └── services/
        ├── resource_manager.py        # 删除
        └── simple_sync.py             # 删除
```
