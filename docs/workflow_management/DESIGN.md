# Workflow 管理系统 - 设计文档

## 文档信息
- **版本**: 1.0
- **日期**: 2025-11-04
- **状态**: 草稿

---

## 1. 系统架构

### 1.1 整体架构

```
Chrome Extension (前端)
    ↓ HTTP API
Backend Services (FastAPI)
    ├── StorageService (文件管理)
    ├── LearningService (学习阶段)
    └── WorkflowService (Workflow 管理)
    ↓
Intent Builder (已有模块)
Workflow Generator (已有模块)
BaseAgent (已有模块)
    ↓
File System (存储)
```

### 1.2 核心模块

**StorageService**
- 负责所有文件的读写操作
- 管理目录结构
- 提供统一的文件访问接口

**LearningService**
- Intent 提取
- MetaFlow 生成
- Learning session 管理

**WorkflowService**
- Workflow 生成
- Workflow 管理
- Workflow 执行

**API Layer**
- FastAPI 路由
- 用户认证
- 统一响应格式

---

## 2. 文件系统设计

### 2.1 目录结构

```
storage/users/{user_id}/
  ├── learning/                    # 学习阶段（临时）
  │   └── {session_id}/
  │       ├── operations.json      # 录制的操作
  │       ├── intents.json         # 提取的意图
  │       ├── metaflow.yaml        # 生成的 MetaFlow
  │       └── metadata.json        # 元数据
  │
  └── workflows/                   # 生成产物（持久）
      └── {workflow_name}/
          ├── workflow.yaml        # 可执行的 workflow
          ├── metadata.json        # 元数据
          └── executions/          # 执行记录
              └── {task_id}.json
```

### 2.2 文件格式

**learning session metadata.json**:
```json
{
  "session_id": "rec_abc123",
  "title": "Collect Amazon Prices",
  "description": "...",
  "status": "workflow_generated",
  "operations_count": 42,
  "workflow_generated": true,
  "generated_workflow_name": "collect-amazon-prices",
  "created_at": "2024-11-04T12:00:00Z",
  "stopped_at": "2024-11-04T12:05:00Z"
}
```

**workflow metadata.json**:
```json
{
  "workflow_name": "collect-amazon-prices",
  "description": "...",
  "source_session_id": "rec_abc123",
  "execution_count": 5,
  "last_executed_at": "2024-11-04T15:00:00Z",
  "created_at": "2024-11-04T12:00:00Z",
  "updated_at": "2024-11-04T12:00:00Z"
}
```

**execution {task_id}.json**:
```json
{
  "task_id": "task_xxx",
  "workflow_name": "collect-amazon-prices",
  "status": "completed",
  "progress": 100,
  "current_step": "step_3",
  "result": {...},
  "execution_time_ms": 5432,
  "error_message": null,
  "failed_step": null,
  "started_at": "2024-11-04T15:00:00Z",
  "completed_at": "2024-11-04T15:00:05Z"
}
```

---

## 3. StorageService 设计

### 3.1 核心方法

```python
class StorageService:
    def __init__(self, base_storage_path: str = None)

    # Learning Session 操作
    def save_learning_intents(user_id, session_id, intents) -> bool
    def save_learning_metaflow(user_id, session_id, metaflow_yaml) -> bool
    def get_learning_session(user_id, session_id) -> Optional[Dict]
    def get_learning_operations(user_id, session_id) -> Optional[List[Dict]]
    def get_learning_intents(user_id, session_id) -> Optional[List[Dict]]
    def get_learning_metaflow(user_id, session_id) -> Optional[str]
    def list_learning_sessions(user_id) -> List[Dict]
    def delete_learning_session(user_id, session_id) -> bool

    # Workflow 操作
    def save_workflow(user_id, workflow_name, workflow_yaml, source_session_id, description) -> Dict
    def get_workflow(user_id, workflow_name) -> Optional[Dict]
    def list_workflows(user_id) -> List[Dict]
    def delete_workflow(user_id, workflow_name) -> bool
    def update_workflow_execution_stats(user_id, workflow_name) -> bool

    # Execution 操作
    def save_execution(user_id, workflow_name, task_id, execution_data) -> bool
    def get_execution(user_id, workflow_name, task_id) -> Optional[Dict]
    def list_executions(user_id, workflow_name, limit=50) -> List[Dict]
    def cleanup_old_executions(user_id, workflow_name, keep_count=50) -> int
```

### 3.2 路径管理

```python
def _user_path(self, user_id: int) -> Path:
    """用户根目录"""
    return self.base_path / str(user_id)

def _learning_path(self, user_id: int, session_id: str = None) -> Path:
    """学习目录或具体 session 目录"""
    learning_dir = self._user_path(user_id) / "learning"
    if session_id:
        return learning_dir / session_id
    return learning_dir

def _workflow_path(self, user_id: int, workflow_name: str = None) -> Path:
    """workflows 目录或具体 workflow 目录"""
    workflows_dir = self._user_path(user_id) / "workflows"
    if workflow_name:
        return workflows_dir / workflow_name
    return workflows_dir
```

### 3.3 原子性写入

使用 JSON 文件的原子性写入：
```python
import json
from pathlib import Path

def _atomic_write_json(self, path: Path, data: dict):
    """原子性写入 JSON 文件"""
    # 写入内容
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
```

---

## 4. LearningService 设计

### 4.1 Intent 提取

```python
async def extract_intents(self, user_id: int, session_id: str) -> dict:
    # 1. 读取 operations
    operations = self.storage.get_learning_operations(user_id, session_id)
    if not operations:
        raise ValueError("Operations not found")

    # 2. 调用 IntentExtractor
    from src.intent_builder.extractors.intent_extractor import IntentExtractor
    extractor = IntentExtractor()
    intents = await extractor.extract(operations)

    # 3. 保存 intents
    self.storage.save_learning_intents(user_id, session_id, intents)

    return {
        "success": True,
        "intents": intents,
        "intents_count": len(intents)
    }
```

### 4.2 MetaFlow 生成

```python
async def generate_metaflow(self, user_id: int, session_id: str) -> dict:
    # 1. 读取 intents
    intents = self.storage.get_learning_intents(user_id, session_id)
    if not intents:
        raise ValueError("Intents not found")

    # 2. 调用 MetaFlowGenerator
    from src.intent_builder.generators.metaflow_generator import MetaFlowGenerator
    generator = MetaFlowGenerator()
    metaflow = await generator.generate(intents)
    metaflow_yaml = metaflow.to_yaml()

    # 3. 保存 metaflow
    self.storage.save_learning_metaflow(user_id, session_id, metaflow_yaml)

    return {
        "success": True,
        "metaflow_yaml": metaflow_yaml,
        "nodes_count": len(metaflow.nodes)
    }
```

---

## 5. WorkflowService 设计

### 5.1 Workflow 生成

```python
async def generate_workflow(self, user_id: int, session_id: str) -> dict:
    # 1. 读取 metaflow 和 session metadata
    metaflow_yaml = self.storage.get_learning_metaflow(user_id, session_id)
    session = self.storage.get_learning_session(user_id, session_id)

    # 2. 解析 MetaFlow
    from src.intent_builder.core.metaflow import MetaFlow
    metaflow = MetaFlow.from_yaml(metaflow_yaml)

    # 3. 调用 WorkflowGenerator
    from src.intent_builder.generators.workflow_generator import WorkflowGenerator
    generator = WorkflowGenerator()
    workflow_yaml = await generator.generate(metaflow)

    # 4. 生成 workflow_name
    workflow_name = self._title_to_workflow_name(session["title"])

    # 5. 保存 workflow
    result = self.storage.save_workflow(
        user_id, workflow_name, workflow_yaml,
        source_session_id=session_id,
        description=session.get("description", "")
    )

    return {
        "success": True,
        "workflow_name": workflow_name,
        "workflow_yaml": workflow_yaml,
        "overwritten": result["overwritten"]
    }
```

### 5.2 Workflow 命名转换

```python
def _title_to_workflow_name(self, title: str) -> str:
    """将 title 转换为 workflow_name"""
    import re

    # 转小写
    name = title.lower()

    # 空格变连字符
    name = name.replace(" ", "-")

    # 移除特殊字符（保留字母、数字、连字符、下划线、中文）
    name = re.sub(r'[^a-z0-9\-_\u4e00-\u9fff]', '', name)

    # 限制长度
    name = name[:100]

    return name
```

### 5.3 Workflow 执行

```python
async def execute_workflow(self, user_id: int, workflow_name: str) -> dict:
    # 1. 读取 workflow
    workflow_data = self.storage.get_workflow(user_id, workflow_name)
    if not workflow_data:
        raise ValueError(f"Workflow not found: {workflow_name}")

    # 2. 生成 task_id
    import uuid
    task_id = f"task_{workflow_name}_{uuid.uuid4().hex[:8]}"

    # 3. 创建初始执行记录
    execution_data = {
        "task_id": task_id,
        "workflow_name": workflow_name,
        "status": "running",
        "progress": 0,
        "current_step": None,
        "result": None,
        "execution_time_ms": None,
        "error_message": None,
        "failed_step": None,
        "started_at": datetime.utcnow().isoformat(),
        "completed_at": None
    }
    self.storage.save_execution(user_id, workflow_name, task_id, execution_data)

    # 4. 异步执行 workflow
    asyncio.create_task(
        self._run_workflow_async(user_id, workflow_name, task_id, workflow_data["workflow_yaml"])
    )

    # 5. 更新执行统计
    self.storage.update_workflow_execution_stats(user_id, workflow_name)

    return {
        "success": True,
        "task_id": task_id,
        "workflow_name": workflow_name,
        "status": "running",
        "started_at": execution_data["started_at"]
    }
```

### 5.4 异步执行任务

```python
async def _run_workflow_async(self, user_id: int, workflow_name: str,
                               task_id: str, workflow_yaml: str):
    """异步执行 workflow（后台任务）"""
    try:
        # 使用 BaseAgent 执行 workflow
        from src.base_app.base_app.base_agent.core.base_agent import BaseAgent
        # ... 执行逻辑

        # 更新为成功
        execution_data = self.storage.get_execution(user_id, workflow_name, task_id)
        execution_data.update({
            "status": "completed",
            "progress": 100,
            "result": result.final_result,
            "execution_time_ms": result.execution_time_ms,
            "completed_at": datetime.utcnow().isoformat()
        })
        self.storage.save_execution(user_id, workflow_name, task_id, execution_data)

    except Exception as e:
        # 更新为失败
        execution_data = self.storage.get_execution(user_id, workflow_name, task_id)
        execution_data.update({
            "status": "failed",
            "error_message": str(e),
            "completed_at": datetime.utcnow().isoformat()
        })
        self.storage.save_execution(user_id, workflow_name, task_id, execution_data)
```

---

## 6. API 实现

### 6.1 Learning APIs

**提取 Intents**:
```python
@app.post("/api/learning/extract-intents")
async def extract_intents(
    request: ExtractIntentsRequest,
    current_user: User = Depends(get_current_user)
):
    try:
        result = await learning_service.extract_intents(
            current_user.id,
            request.session_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**生成 MetaFlow**:
```python
@app.post("/api/learning/generate-metaflow")
async def generate_metaflow(
    request: GenerateMetaflowRequest,
    current_user: User = Depends(get_current_user)
):
    try:
        result = await learning_service.generate_metaflow(
            current_user.id,
            request.session_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**列出 Sessions**:
```python
@app.get("/api/learning/sessions")
async def list_learning_sessions(
    current_user: User = Depends(get_current_user)
):
    sessions = storage_service.list_learning_sessions(current_user.id)
    return {"sessions": sessions, "total": len(sessions)}
```

**删除 Session**:
```python
@app.delete("/api/learning/sessions/{session_id}")
async def delete_learning_session(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    success = storage_service.delete_learning_session(current_user.id, session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True, "session_id": session_id}
```

### 6.2 Workflow APIs

**生成 Workflow**:
```python
@app.post("/api/workflows/generate")
async def generate_workflow(
    request: GenerateWorkflowRequest,
    current_user: User = Depends(get_current_user)
):
    try:
        result = await workflow_service.generate_workflow(
            current_user.id,
            request.session_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**列出 Workflows**:
```python
@app.get("/api/workflows")
async def list_workflows(
    current_user: User = Depends(get_current_user)
):
    workflows = storage_service.list_workflows(current_user.id)
    return {"workflows": workflows, "total": len(workflows)}
```

**执行 Workflow**:
```python
@app.post("/api/workflows/{workflow_name}/execute")
async def execute_workflow(
    workflow_name: str,
    current_user: User = Depends(get_current_user)
):
    try:
        result = await workflow_service.execute_workflow(
            current_user.id,
            workflow_name
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 6.3 Request/Response Models

```python
from pydantic import BaseModel

class ExtractIntentsRequest(BaseModel):
    session_id: str

class GenerateMetaflowRequest(BaseModel):
    session_id: str

class GenerateWorkflowRequest(BaseModel):
    session_id: str
```

---

## 7. 错误处理

### 7.1 错误类型

**文件不存在**:
```python
if not operations:
    raise HTTPException(
        status_code=404,
        detail=f"Operations not found for session: {session_id}"
    )
```

**LLM 调用失败**:
```python
try:
    intents = await extractor.extract(operations)
except Exception as e:
    raise HTTPException(
        status_code=500,
        detail=f"Intent extraction failed: {str(e)}"
    )
```

**Workflow 验证失败**:
```python
try:
    workflow = MetaFlow.from_yaml(metaflow_yaml)
except Exception as e:
    raise HTTPException(
        status_code=500,
        detail=f"MetaFlow validation failed: {str(e)}"
    )
```

### 7.2 日志记录

```python
import logging
logger = logging.getLogger(__name__)

try:
    result = await extractor.extract(operations)
except Exception as e:
    logger.error(f"Intent extraction failed for session {session_id}: {e}")
    raise
```

---

## 8. 实现步骤

### 8.1 Phase 1: 基础服务

1. 实现 `StorageService`
   - 文件读写操作
   - 路径管理
   - 测试文件操作

2. 实现 `LearningService`
   - Intent 提取
   - MetaFlow 生成
   - 集成测试

3. 实现 `WorkflowService`
   - Workflow 生成
   - Workflow 执行
   - 集成测试

### 8.2 Phase 2: API 集成

1. 添加 API 路由到 `main.py`
2. 添加 Request/Response models
3. 测试 API 端点

### 8.3 Phase 3: 插件集成

1. 插件调用 Learning APIs
2. 插件调用 Workflow APIs
3. 插件展示执行结果

---

## 9. 配置

### 9.1 存储路径配置

在 `baseapp.yaml` 中配置：
```yaml
data:
  storage:
    users: "~/ami/storage/users"
```

代码中读取：
```python
from base_app.server.core.config_service import ConfigService

config = ConfigService()
storage_path = config.get('data.storage.users', './storage/users')
```

---

## 10. 测试计划

### 10.1 单元测试

- StorageService 所有方法
- LearningService 所有方法
- WorkflowService 所有方法
- 错误处理

### 10.2 集成测试

- 完整流程测试（录制 → 执行）
- 并发访问测试
- 文件系统错误测试

### 10.3 API 测试

- 所有 API 端点
- 认证测试
- 错误响应测试
