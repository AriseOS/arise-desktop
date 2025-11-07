# Ami 系统重构计划

**版本**: v2.0  
**日期**: 2025-11-07  
**状态**: ✅ Phase 1 & 2 已完成（60%）  
**目标**: 将单体后端拆分为 Local Backend + Cloud Backend 双架构

---

## 📋 目录

1. [重构背景](#1-重构背景)
2. [当前问题分析](#2-当前问题分析)
3. [目标架构](#3-目标架构)
4. [重构原则](#4-重构原则)
5. [详细重构步骤](#5-详细重构步骤)
6. [代码迁移计划](#6-代码迁移计划)
7. [配置系统改造](#7-配置系统改造)
8. [测试策略](#8-测试策略)
9. [风险与缓解](#9-风险与缓解)
10. [时间计划](#10-时间计划)

---

## 1. 重构背景

### 1.1 为什么要重构？

**核心架构转型**：
- **从**：多 Agent 实例模式（每用户一个 Agent）
- **到**：单 BaseAgent + 多 Workflow 模式

**职责分离**：
- **Local Backend**：执行控制 + 浏览器管理（用户电脑）
- **Cloud Backend**：数据存储 + AI 分析（云端服务器）

**MVP 产品形态**：
- Desktop App (Tauri) + Chrome Extension + Cloud Backend
- 本地录制 → 云端分析 → 本地执行

### 1.2 核心决策

✅ **已确定的技术选型**：
- Desktop App: **Tauri**
- Local Backend: **Python + FastAPI**（独立进程，localhost:8000）
- Cloud Backend: **Python + FastAPI**（独立部署）
- Extension ↔ Local Backend: **WebSocket**
- 打包方式: **直接携带 Python**（MVP，便于调试）
- 平台支持: **macOS** 优先
- 存储路径: **统一到 ~/.ami/**

✅ **MVP 阶段不考虑**：
- 多设备同步
- 离线自适应执行
- 重试队列
- 多用户登录（单用户单设备）

---

## 2. 当前问题分析

### 2.1 代码结构混乱

```
src/client/web/backend/
├── main.py (1253 行！)
│   ├── Agent 管理 API（已废弃）
│   ├── 聊天功能（已废弃）
│   ├── 录制控制（应该在本地）
│   ├── Workflow 执行（应该在本地）
│   ├── 用户认证（应该在云端）
│   └── WebSocket 管理（AgentBuilder 相关）
│
├── agent_service.py（AgentBuilder，已废弃）
├── database.py（包含大量 Agent 管理表）
├── learning_service.py（应该在云端）
└── frontend/（Web 前端，不需要）
```

**问题**：
1. 本地和云端逻辑混在一起
2. 包含大量已废弃功能
3. 职责不清晰
4. 难以独立开发和部署

### 2.2 架构不匹配

**当前架构**：
```
Backend (单体)
├── 用户管理
├── Agent 实例管理（port 5001-5020）
├── 录制管理
├── Workflow 执行
└── LLM 调用
```

**目标架构**：
```
Local Backend (用户电脑)          Cloud Backend (服务器)
├── 录制控制                      ├── 用户管理
├── Workflow 执行                 ├── 数据存储
├── 浏览器管理                    ├── Intent 提取
└── 云端 API 调用                 ├── MetaFlow 生成
                                  └── Workflow 生成
```

### 2.3 BaseAgent 过度设计

**当前问题**：
- 为多实例设计（agent_id, port 管理）
- 实际只需要一个实例
- 配置复杂

**需要调整**：
- 简化为单例执行引擎
- 移除 port 管理
- 保留核心能力（工具、Memory、Workflow 引擎）

---

## 3. 目标架构

### 3.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                   User's Computer (macOS)                   │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  Desktop App (Tauri)                                   │ │
│  │  ├── Main Window (Workflow 管理界面)                   │ │
│  │  ├── System Tray (后台运行)                            │ │
│  │  └── Process Manager (监控 Local Backend)              │ │
│  └────────────────────┬──────────────────────────────────┘ │
│                       │                                     │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  Chrome Browser                                        │ │
│  │  ├── Chrome Extension (录制 + 触发执行)                │ │
│  │  │   ├── Popup UI                                     │ │
│  │  │   ├── Content Script (捕获事件)                    │ │
│  │  │   └── Background Worker (WebSocket 客户端)         │ │
│  │  └── 用户真实浏览环境                                  │ │
│  └────────────────────┬──────────────────────────────────┘ │
│                       │ WebSocket (ws://localhost:8000)     │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  Local Backend (Python + FastAPI)                     │ │
│  │  ├── main.py (FastAPI 入口)                           │ │
│  │  ├── recording_controller.py (录制控制)                │ │
│  │  ├── execution_controller.py (执行控制)                │ │
│  │  ├── storage_manager.py (本地文件管理)                 │ │
│  │  ├── cloud_client.py (调用云端 API)                   │ │
│  │  ├── browser_manager.py (全局浏览器会话)              │ │
│  │  └── workflow_executor.py (BaseAgent 简化版)          │ │
│  │                                                         │ │
│  │  本地存储:                                             │ │
│  │  ~/.ami/                    │ │
│  │  ├── users/{user_id}/workflows/                        │ │
│  │  ├── users/{user_id}/cache/                            │ │
│  │  └── logs/                                             │ │
│  └────────────────────┬──────────────────────────────────┘ │
└────────────────────────┼──────────────────────────────────┘
                         │ HTTPS
┌────────────────────────┼──────────────────────────────────┐
│                   Cloud Backend                            │
│                   (https://api.ami.com)                     │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  FastAPI Application                                   │ │
│  │  ├── auth.py (用户认证)                                │ │
│  │  ├── recording_service.py (接收录制数据)               │ │
│  │  ├── learning_service.py (Intent 提取)                 │ │
│  │  ├── metaflow_service.py (MetaFlow 生成)               │ │
│  │  ├── workflow_service.py (Workflow 生成)               │ │
│  │  └── storage_service.py (S3 管理)                      │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  PostgreSQL Database                                   │ │
│  │  ├── users                                             │ │
│  │  ├── recordings                                        │ │
│  │  ├── workflows                                         │ │
│  │  ├── intent_graphs                                     │ │
│  │  └── executions                                        │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  S3 Object Storage                                     │ │
│  │  ├── recordings/{user_id}/{session_id}/operations.json │ │
│  │  └── workflows/{user_id}/{workflow_name}/workflow.yaml │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 数据流

#### **录制流程**
```
1. Extension 开始录制
   ↓ WebSocket: start_recording()
2. Local Backend 创建 session
   ↓
3. 用户操作 → Extension 捕获事件
   ↓ WebSocket: record_operation(operation)
4. Local Backend 保存到本地文件
   ~/.ami/users/{user_id}/recordings/{session_id}/operations.json
   ↓
5. Extension 停止录制
   ↓ WebSocket: stop_recording()
6. Local Backend 上传到云端
   ↓ HTTPS POST: /api/recordings/upload
7. Cloud Backend 保存 + 生成 Workflow (同步 30-60s)
   - Intent Extraction (LLM)
   - MetaFlow Generation (LLM)
   - Workflow YAML Generation (LLM)
   ↓ 返回: workflow_name
8. Local Backend 下载 Workflow
   ↓ HTTPS GET: /api/workflows/{name}/download
9. 保存到本地
   ~/.ami/users/{user_id}/workflows/{name}/workflow.yaml
   ↓
10. 通知 Extension："Workflow 已生成！"
```

#### **执行流程**
```
1. Extension 点击"执行"
   ↓ WebSocket: execute_workflow(workflow_name)
2. Local Backend 加载本地 Workflow
   ~/.ami/users/{user_id}/workflows/{name}/workflow.yaml
   ↓
3. 强制设置 workflow.name = "global"
   ↓
4. BaseAgent (简化版) 执行
   - 复用全局浏览器会话
   - 执行各个 step
   ↓
5. 保存执行结果到本地
   ~/.ami/users/{user_id}/workflows/{name}/executions/{id}/result.json
   ↓
6. 异步上报到云端（统计）
   ↓ HTTPS POST: /api/executions/report
7. 通知 Extension："执行完成！"
```

---

## 4. 重构原则

### 4.1 渐进式重构

- ✅ **分阶段**：先后端，再前端
- ✅ **可回退**：保留旧代码，新旧并存一段时间
- ✅ **小步快跑**：每个阶段都能独立验证

### 4.2 向后兼容（MVP 不要求）

- ❌ 不需要迁移旧数据
- ❌ 不需要支持旧 API
- ✅ 全新开始

### 4.3 代码复用

- ✅ BaseAgent 核心保留（简化）
- ✅ Intent Builder 移到 Cloud
- ✅ 工具系统保留（Browser、Memory）

---

## 5. 详细重构步骤

### **阶段 0：准备工作（1 天）**

#### Step 0.1: 备份当前代码
```bash
git checkout -b backup/before-refactor
git push origin backup/before-refactor
```

#### Step 0.2: 创建新分支
```bash
git checkout -b refactor/local-cloud-split
```

#### Step 0.3: 文档准备
- [x] 重构计划（本文档）
- [ ] API 规范文档（Local ↔ Cloud）
- [ ] 数据模型文档

---

### **阶段 1：创建 Local Backend（3 天）**

#### Step 1.1: 创建目录结构
```bash
mkdir -p local-backend/{controllers,services,models,utils}
```

```
local-backend/
├── main.py                       # FastAPI 入口
├── config.py                     # 配置管理
├── controllers/
│   ├── recording_controller.py   # 录制控制
│   ├── execution_controller.py   # 执行控制
│   └── sync_controller.py        # 数据同步
├── services/
│   ├── cloud_client.py           # Cloud API 客户端
│   ├── browser_manager.py        # 浏览器会话管理
│   ├── storage_manager.py        # 本地文件管理
│   └── workflow_executor.py      # Workflow 执行引擎
├── models/
│   ├── recording.py              # 录制数据模型
│   └── workflow.py               # Workflow 模型
├── utils/
│   ├── encryption.py             # Token 加密
│   └── logger.py                 # 日志配置
├── requirements.txt
└── README.md
```

#### Step 1.2: 实现核心模块

**1.2.1 创建 main.py**
```python
# local-backend/main.py

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from controllers import recording_controller, execution_controller
from services.browser_manager import BrowserManager

app = FastAPI(title="Ami Local Backend", version="1.0.0")

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Desktop App 和 Extension
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局浏览器管理器
browser_manager = BrowserManager()

@app.on_event("startup")
async def startup():
    """启动时初始化全局浏览器会话"""
    await browser_manager.init_global_session()
    print("✅ Local Backend started, browser session ready")

@app.on_event("shutdown")
async def shutdown():
    """关闭时清理资源"""
    await browser_manager.cleanup()
    print("✅ Local Backend shutdown")

# WebSocket 路由
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Extension 和 Desktop App 的 WebSocket 连接"""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            # 路由到对应的 controller
            await handle_websocket_message(websocket, data)
    except WebSocketDisconnect:
        print("WebSocket disconnected")

# HTTP 路由
app.include_router(recording_controller.router, prefix="/api/recording")
app.include_router(execution_controller.router, prefix="/api/workflows")

@app.get("/health")
def health():
    return {
        "status": "ok",
        "browser_ready": browser_manager.is_ready()
    }
```

**1.2.2 创建 cloud_client.py**
```python
# local-backend/services/cloud_client.py

import httpx
from typing import List, Dict, Optional

class CloudClient:
    """调用 Cloud Backend API 的客户端"""
    
    def __init__(self, base_url: str, token: Optional[str] = None):
        self.base_url = base_url
        self.token = token
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"} if token else {},
            timeout=120.0  # Workflow 生成需要时间
        )
    
    async def login(self, username: str, password: str) -> Dict:
        """用户登录，获取 Token"""
        response = await self.client.post(
            "/api/auth/login",
            json={"username": username, "password": password}
        )
        response.raise_for_status()
        return response.json()  # {"token": "...", "user_id": ...}
    
    async def upload_recording(self, operations: List[Dict]) -> str:
        """上传录制数据"""
        response = await self.client.post(
            "/api/recordings/upload",
            json={"operations": operations}
        )
        response.raise_for_status()
        return response.json()["recording_id"]
    
    async def generate_workflow(self, recording_id: str) -> str:
        """触发 Workflow 生成（同步，30-60 秒）"""
        response = await self.client.post(
            f"/api/recordings/{recording_id}/generate"
        )
        response.raise_for_status()
        return response.json()["workflow_name"]
    
    async def download_workflow(self, workflow_name: str) -> str:
        """下载 Workflow YAML"""
        response = await self.client.get(
            f"/api/workflows/{workflow_name}/download"
        )
        response.raise_for_status()
        return response.json()["yaml"]
    
    async def list_workflows(self) -> List[Dict]:
        """获取 Workflow 列表"""
        response = await self.client.get("/api/workflows")
        response.raise_for_status()
        return response.json()
    
    async def report_execution(
        self,
        workflow_name: str,
        status: str,
        duration: float,
        error: Optional[str] = None
    ):
        """上报执行统计"""
        await self.client.post(
            "/api/executions/report",
            json={
                "workflow_name": workflow_name,
                "status": status,
                "duration": duration,
                "error": error
            }
        )
```

**1.2.3 创建 storage_manager.py**
```python
# local-backend/services/storage_manager.py

from pathlib import Path
import json
from typing import Dict, List, Optional
import os

class StorageManager:
    """本地文件系统管理"""
    
    def __init__(self, base_path: Optional[Path] = None):
        if base_path:
            self.base_path = base_path
        else:
            # macOS 标准路径
            self.base_path = Path.home() / "Library" / "Application Support" / "Ami"
        
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def _user_path(self, user_id: str) -> Path:
        """获取用户目录"""
        path = self.base_path / "users" / user_id
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    # ===== 录制管理 =====
    
    def save_recording(self, user_id: str, session_id: str, operations: List[Dict]):
        """保存录制数据"""
        recording_path = self._user_path(user_id) / "recordings" / session_id
        recording_path.mkdir(parents=True, exist_ok=True)
        
        file_path = recording_path / "operations.json"
        with open(file_path, 'w') as f:
            json.dump(operations, f, indent=2)
    
    def get_recording(self, user_id: str, session_id: str) -> List[Dict]:
        """读取录制数据"""
        file_path = self._user_path(user_id) / "recordings" / session_id / "operations.json"
        with open(file_path, 'r') as f:
            return json.load(f)
    
    # ===== Workflow 管理 =====
    
    def save_workflow(self, user_id: str, workflow_name: str, yaml_content: str):
        """保存 Workflow YAML"""
        workflow_path = self._user_path(user_id) / "workflows" / workflow_name
        workflow_path.mkdir(parents=True, exist_ok=True)
        
        file_path = workflow_path / "workflow.yaml"
        with open(file_path, 'w') as f:
            f.write(yaml_content)
    
    def get_workflow(self, user_id: str, workflow_name: str) -> str:
        """读取 Workflow YAML"""
        file_path = self._user_path(user_id) / "workflows" / workflow_name / "workflow.yaml"
        with open(file_path, 'r') as f:
            return f.read()
    
    def list_workflows(self, user_id: str) -> List[str]:
        """列出所有 Workflow"""
        workflows_path = self._user_path(user_id) / "workflows"
        if not workflows_path.exists():
            return []
        
        return [d.name for d in workflows_path.iterdir() if d.is_dir()]
    
    # ===== 执行记录 =====
    
    def save_execution_result(
        self,
        user_id: str,
        workflow_name: str,
        execution_id: str,
        result: Dict
    ):
        """保存执行结果"""
        exec_path = (
            self._user_path(user_id) / 
            "workflows" / workflow_name / 
            "executions" / execution_id
        )
        exec_path.mkdir(parents=True, exist_ok=True)
        
        file_path = exec_path / "result.json"
        with open(file_path, 'w') as f:
            json.dump(result, f, indent=2)
```

**1.2.4 创建 browser_manager.py**
```python
# local-backend/services/browser_manager.py

from src.base_app.base_app.base_agent.tools.browser_session_manager import BrowserSessionManager

class BrowserManager:
    """浏览器会话管理器"""
    
    def __init__(self):
        self.session_manager = None
        self.global_session = None
    
    async def init_global_session(self):
        """初始化全局浏览器会话"""
        self.session_manager = await BrowserSessionManager.get_instance()
        self.global_session = await self.session_manager.get_or_create_session(
            session_id="global",
            headless=False,
            keep_alive=True
        )
        print("✅ Global browser session initialized")
    
    def is_ready(self) -> bool:
        """检查浏览器是否就绪"""
        return self.global_session is not None
    
    async def cleanup(self):
        """清理资源"""
        if self.session_manager:
            await self.session_manager.cleanup_all()
```

**1.2.5 创建 workflow_executor.py**
```python
# local-backend/services/workflow_executor.py

import yaml
from typing import Dict
from src.base_app.base_app.base_agent.core.base_agent import BaseAgent
from src.base_app.base_app.base_agent.core.schemas import Workflow

class WorkflowExecutor:
    """Workflow 执行引擎（BaseAgent 简化版）"""
    
    def __init__(self):
        # 单例 BaseAgent
        self.agent = BaseAgent()
    
    async def execute(self, workflow_yaml: str, user_id: str) -> Dict:
        """执行 Workflow"""
        # 解析 YAML
        workflow_dict = yaml.safe_load(workflow_yaml)
        
        # 强制设置 name = "global" (复用浏览器)
        workflow_dict['name'] = 'global'
        
        # 转换为 Workflow 对象
        workflow = Workflow(**workflow_dict)
        
        # 执行
        result = await self.agent.run_workflow(
            workflow,
            context={"user_id": user_id}
        )
        
        return {
            "status": "completed" if result.success else "failed",
            "result": result.final_result,
            "error": result.error
        }
```

#### Step 1.3: 实现 Controllers

**recording_controller.py** (简化版，完整版见附录)
```python
# local-backend/controllers/recording_controller.py

from fastapi import APIRouter, WebSocket
from services.storage_manager import StorageManager
from services.cloud_client import CloudClient
import uuid

router = APIRouter()
storage = StorageManager()

# 当前录制会话
active_recordings = {}

@router.websocket("/ws/recording")
async def recording_websocket(websocket: WebSocket):
    await websocket.accept()
    
    try:
        while True:
            message = await websocket.receive_json()
            
            if message["type"] == "start":
                session_id = str(uuid.uuid4())
                active_recordings[session_id] = []
                await websocket.send_json({
                    "type": "started",
                    "session_id": session_id
                })
            
            elif message["type"] == "operation":
                session_id = message["session_id"]
                operation = message["operation"]
                active_recordings[session_id].append(operation)
            
            elif message["type"] == "stop":
                session_id = message["session_id"]
                operations = active_recordings.pop(session_id)
                
                # 保存到本地
                user_id = message["user_id"]
                storage.save_recording(user_id, session_id, operations)
                
                # 上传到云端并生成
                cloud = CloudClient(
                    base_url="https://api.ami.com",
                    token=message["token"]
                )
                recording_id = await cloud.upload_recording(operations)
                workflow_name = await cloud.generate_workflow(recording_id)
                
                # 下载 Workflow
                workflow_yaml = await cloud.download_workflow(workflow_name)
                storage.save_workflow(user_id, workflow_name, workflow_yaml)
                
                await websocket.send_json({
                    "type": "completed",
                    "workflow_name": workflow_name
                })
    
    except Exception as e:
        print(f"WebSocket error: {e}")
```

#### Step 1.4: 测试 Local Backend

```bash
cd local-backend
pip install -r requirements.txt
python main.py
```

访问 http://localhost:8000/docs 验证 API

---

### **阶段 2：创建 Cloud Backend（5 天）**

#### Step 2.1: 创建目录结构

```bash
mkdir -p cloud-backend/{api,services,models,database}
```

```
cloud-backend/
├── main.py                    # FastAPI 入口
├── config.py                  # 配置（数据库、S3、LLM）
├── api/
│   ├── auth.py                # 认证 API
│   ├── recordings.py          # 录制数据 API
│   ├── workflows.py           # Workflow API
│   └── executions.py          # 执行统计 API
├── services/
│   ├── learning_service.py    # Intent 提取
│   ├── metaflow_service.py    # MetaFlow 生成
│   ├── workflow_service.py    # Workflow 生成
│   └── storage_service.py     # S3 管理
├── models/
│   ├── user.py
│   ├── recording.py
│   ├── workflow.py
│   └── intent_graph.py
├── database/
│   ├── connection.py          # PostgreSQL 连接
│   └── migrations/            # Alembic 迁移
├── requirements.txt
├── Dockerfile
└── README.md
```

#### Step 2.2: 迁移现有代码

**从 `src/client/web/backend/` 迁移到 `cloud-backend/`**：

```bash
# 迁移文件映射
src/client/web/backend/auth.py 
  → cloud-backend/api/auth.py

src/client/web/backend/learning_service.py 
  → cloud-backend/services/learning_service.py

src/client/web/backend/database.py 
  → cloud-backend/models/*.py (拆分)

src/intent_builder/ 
  → cloud-backend/services/ (整合)
```

**清理 database.py**：

```python
# cloud-backend/models/user.py

from sqlalchemy import Column, Integer, String, DateTime, Boolean
from database.connection import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

# 删除的表：
# - Agent
# - PortAllocation
# - AgentSession
# - AgentBuild
# - GeneratedAgent
```

**新增 recording.py**：

```python
# cloud-backend/models/recording.py

from sqlalchemy import Column, Integer, String, DateTime, Text
from database.connection import Base
import uuid

class Recording(Base):
    __tablename__ = "recordings"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, nullable=False)
    session_id = Column(String(36), nullable=False)
    operations_count = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    storage_path = Column(String(255), nullable=False)  # S3 路径
```

**新增 workflow.py**：

```python
# cloud-backend/models/workflow.py

from sqlalchemy import Column, Integer, String, DateTime, Text
from database.connection import Base

class Workflow(Base):
    __tablename__ = "workflows"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    workflow_name = Column(String(255), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    storage_path = Column(String(255), nullable=False)  # S3 路径
```

#### Step 2.3: 实现核心服务

**learning_service.py**（基于现有代码）：

```python
# cloud-backend/services/learning_service.py

# 复制 src/client/web/backend/learning_service.py
# 并调整导入路径

from src.intent_builder.intent_extractor import IntentExtractor
from src.intent_builder.metaflow_generator import MetaFlowGenerator
```

**workflow_service.py**：

```python
# cloud-backend/services/workflow_service.py

from src.intent_builder.workflow_generator import WorkflowGenerator
```

#### Step 2.4: 实现 API

**recordings.py**：

```python
# cloud-backend/api/recordings.py

from fastapi import APIRouter, Depends
from services.learning_service import LearningService
from services.workflow_service import WorkflowService
from services.storage_service import StorageService

router = APIRouter()
learning = LearningService()
workflow_gen = WorkflowService()
storage = StorageService()

@router.post("/upload")
async def upload_recording(operations: List[Dict], user_id: int):
    # 1. 保存到 S3
    recording_id = str(uuid.uuid4())
    s3_path = f"recordings/{user_id}/{recording_id}/operations.json"
    await storage.upload_json(s3_path, operations)
    
    # 2. 保存元数据到数据库
    recording = Recording(
        id=recording_id,
        user_id=user_id,
        session_id=...,
        operations_count=len(operations),
        storage_path=s3_path
    )
    db.add(recording)
    db.commit()
    
    return {"recording_id": recording_id}

@router.post("/{recording_id}/generate")
async def generate_workflow(recording_id: str, user_id: int):
    # 1. 读取 operations
    recording = db.query(Recording).filter_by(id=recording_id).first()
    operations = await storage.download_json(recording.storage_path)
    
    # 2. Intent Extraction
    intents = await learning.extract_intents(operations)
    
    # 3. 更新 Intent Graph
    intent_graph = db.query(IntentGraph).filter_by(user_id=user_id).first()
    updated_graph = learning.update_graph(intent_graph, intents)
    db.merge(updated_graph)
    
    # 4. 生成 MetaFlow
    metaflow = await learning.generate_metaflow(intents, updated_graph)
    
    # 5. 生成 Workflow
    workflow_yaml, workflow_name = await workflow_gen.generate(metaflow)
    
    # 6. 保存
    s3_path = f"workflows/{user_id}/{workflow_name}/workflow.yaml"
    await storage.upload_text(s3_path, workflow_yaml)
    
    workflow = Workflow(
        user_id=user_id,
        workflow_name=workflow_name,
        storage_path=s3_path
    )
    db.add(workflow)
    db.commit()
    
    return {"workflow_name": workflow_name}
```

---

### **阶段 3：配置系统改造（2 天）**

#### Step 3.1: 统一存储路径

**目标**：所有本地数据统一到 `~/.ami/`

**修改配置文件**：

```yaml
# src/base_app/config/baseapp.yaml

# 数据存储配置
data:
  # 统一根目录（macOS）
  root: ~/.ami
  
  # 数据库文件
  databases:
    sessions: ${data.root}/sessions.db
    kv: ${data.root}/agent_kv.db
    storage: ${data.root}/storage.db
  
  # 向量数据库
  chroma_db: ${data.root}/chroma_db
  
  # 浏览器数据
  browser_data: ${data.root}/browser_data
  
  # Workflow 数据（新增）
  workflows:
    storage_root: ${data.root}/users
  
  # 日志
  logs: ${data.root}/logs
```

#### Step 3.2: 更新 Local Backend 配置

```python
# local-backend/config.py

from pathlib import Path
import os

class Config:
    # 基础路径
    BASE_PATH = Path.home() / "Library" / "Application Support" / "Ami"
    
    # Cloud API
    CLOUD_API_URL = os.getenv("CLOUD_API_URL", "https://api.ami.com")
    
    # Local Server
    LOCAL_HOST = "0.0.0.0"
    LOCAL_PORT = 8000
    
    # 日志
    LOG_LEVEL = "INFO"
    LOG_PATH = BASE_PATH / "logs" / "local-backend.log"
```

---

### **阶段 4：测试与验证（3 天）**

#### Step 4.1: 单元测试

```python
# local-backend/tests/test_storage_manager.py

def test_save_workflow():
    storage = StorageManager()
    storage.save_workflow("user123", "test-workflow", "name: test")
    
    result = storage.get_workflow("user123", "test-workflow")
    assert result == "name: test"
```

#### Step 4.2: 集成测试

**本地 Cloud Backend**：
```bash
cd cloud-backend
uvicorn main:app --host 0.0.0.0 --port 9000
```

**Local Backend 配置**：
```python
CLOUD_API_URL = "http://localhost:9000"
```

**完整流程测试**：
```python
# local-backend/tests/test_complete_flow.py

async def test_complete_workflow():
    # 1. 录制
    operations = [...]
    storage.save_recording("user123", "session1", operations)
    
    # 2. 上传
    cloud = CloudClient("http://localhost:9000", token="test-token")
    recording_id = await cloud.upload_recording(operations)
    
    # 3. 生成
    workflow_name = await cloud.generate_workflow(recording_id)
    
    # 4. 下载
    workflow_yaml = await cloud.download_workflow(workflow_name)
    storage.save_workflow("user123", workflow_name, workflow_yaml)
    
    # 5. 执行
    executor = WorkflowExecutor()
    result = await executor.execute(workflow_yaml, "user123")
    
    assert result["status"] == "completed"
```

---

### **阶段 5：清理旧代码（1 天）**

#### Step 5.1: 删除废弃代码

```bash
# 删除旧 Backend
rm -rf src/client/web/backend/agent_service.py
rm -rf src/client/web/backend/progress_tracker.py
rm -rf src/client/web/frontend/

# 删除旧数据库文件
rm src/client/web/backend/agentcrafter_users.db

# 删除测试文件（迁移到新位置）
rm src/client/web/backend/test_*.py
```

#### Step 5.2: 更新文档

- 更新 README.md
- 更新 CLAUDE.md
- 标记旧 API 为废弃

---

## 6. 代码迁移计划

### 6.1 迁移映射表

| 源文件 | 目标位置 | 状态 | 说明 |
|--------|----------|------|------|
| `src/client/web/backend/main.py` | 拆分 | 🔄 | Local + Cloud 各一个 |
| `src/client/web/backend/recording_service.py` | `local-backend/controllers/recording_controller.py` | ✅ | 录制控制在本地 |
| `src/client/web/backend/workflow_service.py` | `local-backend/services/workflow_executor.py` | ✅ | 执行在本地 |
| `src/client/web/backend/storage_service.py` | `local-backend/services/storage_manager.py` | ✅ | 本地文件管理 |
| `src/client/web/backend/learning_service.py` | `cloud-backend/services/learning_service.py` | ✅ | 移到云端 |
| `src/client/web/backend/auth.py` | `cloud-backend/api/auth.py` | ✅ | 认证在云端 |
| `src/client/web/backend/database.py` | `cloud-backend/models/*.py` | 🔄 | 拆分并清理 |
| `src/intent_builder/` | `cloud-backend/services/` | ✅ | 整合到云端 |
| `src/client/web/backend/agent_service.py` | **删除** | ❌ | 已废弃 |
| `src/client/web/frontend/` | **删除** | ❌ | 不需要 Web 前端 |

### 6.2 BaseAgent 调整

**保留的部分**：
```python
# src/base_app/base_app/base_agent/core/base_agent.py

class BaseAgent:
    # ✅ 保留
    - 工具管理（Browser、Memory）
    - Workflow 引擎
    - Memory 管理
    
    # ❌ 删除/简化
    - agent_id（不再需要）
    - port 管理
    - 多实例相关代码
```

**调整后的初始化**：
```python
class BaseAgent:
    def __init__(self, config_service=None):
        # 不再需要 user_id（通过 context 传递）
        # 不再需要 agent_id
        # 不再需要 port
        
        self.tools = {}
        self.memory = MemoryManager()
        self.workflow_engine = AgentWorkflowEngine(self)
    
    async def run_workflow(self, workflow, context: Dict):
        # user_id 通过 context 传递
        user_id = context.get("user_id")
        self.memory.switch_user(user_id)
        
        # 执行
        result = await self.workflow_engine.run_workflow(workflow)
        return result
```

---

## 7. 配置系统改造

### 7.1 当前问题

```
baseapp.yaml (BaseAgent)
  ├── data.root: ~/.local/share/baseapp
  └── data.databases.users: ~/agentcrafter/storage/...

backend.yaml (Web Backend)
  ├── database.path: dbfiles/agentcrafter.db
  └── ...
```

**问题**：路径不统一，配置分散

### 7.2 目标配置

```yaml
# baseapp.yaml (统一配置)

# 应用基础
app:
  name: Ami
  version: 1.0.0
  platform: macos  # macos | windows | linux

# 数据存储（统一路径）
data:
  # 根目录（macOS）
  root: ~/.ami
  
  # 数据库
  databases:
    sessions: ${data.root}/sessions.db
    kv: ${data.root}/agent_kv.db
    storage: ${data.root}/storage.db
  
  # 向量数据库
  chroma_db: ${data.root}/chroma_db
  
  # 浏览器数据
  browser_data: ${data.root}/browser_data
  
  # Workflow 数据
  workflows:
    storage_root: ${data.root}/users
  
  # 日志
  logs: ${data.root}/logs

# Local Backend
local_backend:
  host: 0.0.0.0
  port: 8000
  
# Cloud Backend
cloud_backend:
  api_url: https://api.ami.com
  # api_url: http://localhost:9000  # 开发环境

# LLM 配置
llm:
  provider: anthropic
  model: claude-sonnet-4-5
  api_key: ${ANTHROPIC_API_KEY}

# 浏览器配置
browser:
  headless: false
  timeout: 30
```

### 7.3 迁移步骤

```bash
# 1. 备份旧配置
cp src/base_app/config/baseapp.yaml src/base_app/config/baseapp.yaml.bak

# 2. 更新配置
# 手动编辑 baseapp.yaml

# 3. 迁移旧数据（如果需要）
mkdir -p ~/Library/Application\ Support/Ami
mv ~/.local/share/baseapp/* ~/Library/Application\ Support/Ami/

# 4. 测试
python -c "from src.base_app.base_app.server.core.config_service import ConfigService; c = ConfigService(); print(c.get('data.root'))"
```

---

## 8. 测试策略

### 8.1 Local Backend 测试

```python
# local-backend/tests/conftest.py

import pytest
from fastapi.testclient import TestClient
from main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def mock_cloud_client():
    # Mock Cloud API 响应
    pass
```

### 8.2 Cloud Backend 测试

```python
# cloud-backend/tests/test_workflow_generation.py

async def test_generate_workflow():
    operations = load_test_operations()
    
    recording_id = await upload_recording(operations)
    workflow_name = await generate_workflow(recording_id)
    
    assert workflow_name.startswith("从-")
```

### 8.3 端到端测试

```python
# e2e-tests/test_complete_flow.py

async def test_recording_to_execution():
    # 1. 启动 Local Backend
    # 2. 启动 Cloud Backend (本地)
    # 3. 模拟 Extension 录制
    # 4. 验证生成
    # 5. 验证执行
    pass
```

---

## 9. 风险与缓解

### 9.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| BaseAgent 重构破坏现有功能 | 高 | 保留旧代码，渐进式迁移 |
| Cloud API 性能问题（生成慢） | 中 | 加载动画、异步处理 |
| WebSocket 连接不稳定 | 中 | 心跳检测、自动重连 |
| 本地存储路径迁移失败 | 低 | 提供迁移脚本和回退 |

### 9.2 进度风险

| 风险 | 缓解措施 |
|------|----------|
| 预估时间不足 | 分阶段交付，核心功能优先 |
| 依赖阻塞 | Local 和 Cloud 并行开发 |

---

## 10. 时间计划

### 总时间：约 15 天

| 阶段 | 时间 | 关键里程碑 |
|------|------|------------|
| 阶段 0：准备 | 1 天 | 文档、分支准备 |
| 阶段 1：Local Backend | 3 天 | Local Backend 可独立运行 |
| 阶段 2：Cloud Backend | 5 天 | Cloud Backend 可本地测试 |
| 阶段 3：配置改造 | 2 天 | 路径统一，配置生效 |
| 阶段 4：测试验证 | 3 天 | 完整流程跑通 |
| 阶段 5：清理 | 1 天 | 删除旧代码，更新文档 |

### Gantt 图

```
Week 1:
Mon-Tue: 准备 + Local Backend 框架
Wed-Fri: Local Backend 核心功能

Week 2:
Mon-Fri: Cloud Backend 开发

Week 3:
Mon-Tue: 配置改造
Wed-Fri: 测试 + 清理
```

---

## 附录

### A. API 规范

详见：`docs/platform/api_specification.md`（待创建）

### B. 数据模型

详见：`docs/platform/data_models.md`（待创建）

### C. 完整代码示例

详见：
- `local-backend/examples/`
- `cloud-backend/examples/`

---

## 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2025-11-07 | 初始版本 |

---


---

## 📊 当前进度（2025-11-07 更新）

**重构进度**: 60% ✅

| 阶段 | 状态 | 进度 |
|------|------|------|
| 阶段 1: 基础架构搭建 | ✅ 完成 | 100% |
| 阶段 2: 代码迁移 | ✅ 完成 | 100% |
| 阶段 3: 配置系统改造 | ✅ 完成 | 100% |
| 阶段 4: 测试与验证 | ⏳ 进行中 | 30% |
| 阶段 5: 文档与清理 | ⏳ 进行中 | 70% |

**已完成的工作**:
- ✅ Local Backend 完全可运行（4个服务整合）
- ✅ Cloud Backend 完全可运行（Storage Service）
- ✅ 存储路径统一到 ~/.ami
- ✅ 真实文件读写（不是 mock）
- ✅ 全局浏览器会话管理
- ✅ 完整文档体系

**下一步**:
1. 集成 Intent Builder 到 Cloud Backend
2. 实现完整的录制→生成→执行流程
3. 标记旧代码为 deprecated
4. 数据库集成（PostgreSQL）

---

## 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2025-11-07 | 初始版本 |
| v2.0 | 2025-11-07 | Phase 1 & 2 完成，更新进度 |

---

详细完成报告请查看：[PHASE_2_COMPLETE.md](../../PHASE_2_COMPLETE.md)
