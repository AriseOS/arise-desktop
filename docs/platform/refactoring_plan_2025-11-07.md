# Ami 系统重构计划

**版本**: v3.0 - Desktop App Only
**日期**: 2025-11-08 (更新)
**状态**: 📝 v3.0 规划中
**目标**: Desktop App 完整方案（录制 + 生成 + 执行），基于 CDP 注入脚本

---

## 🎯 v3.0 核心策略调整

**产品形态变更**:
- ❌ v2.0: Desktop App + Chrome Extension 双前端
- ✅ v3.0: **仅 Desktop App**，使用 CDP 注入脚本录制
- 📦 未来可选: Extension 版本作为独立产品线

**技术方案变更**:
- ✅ CDP 注入脚本录制（复用现有 `behavior_tracker.js`）
- ✅ Desktop App (Tauri) 包含完整能力
- ✅ 不依赖 Chrome Extension

---

# 原计划（v2.0，已更新为 v3.0）

**版本**: v2.0
**日期**: 2025-11-07
**状态**: ⚠️ 已调整为 v3.0
**目标**: ~~Desktop App + Extension~~ → Desktop App Only

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
- **App Backend**：执行控制 + 浏览器管理（用户电脑）
- **Cloud Backend**：数据存储 + AI 分析（云端服务器）

**MVP 产品形态** (v3.0 更新)：
- ~~Desktop App + Chrome Extension + Cloud Backend~~ (v2.0)
- **Desktop App (Tauri) + App Backend + Cloud Backend** (v3.0)
- **CDP 注入脚本录制** → 云端分析 → 本地执行

### 1.2 核心决策 (v3.0 更新)

✅ **已确定的技术选型**：
- Desktop App: **Tauri** (React/Vue + Rust)
- App Backend: **Python + FastAPI**（独立进程，localhost:8000）
- **录制方式**: **CDP 注入脚本**（复用 `behavior_tracker.js`）
- ~~Extension ↔ App Backend: WebSocket~~ (已移除)
- Desktop App ↔ App Backend: **HTTP/WebSocket**
- Cloud Backend: **Python + FastAPI**（独立部署）
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
legacy client/web/backend/
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
Desktop App (Tauri)              App Backend (用户电脑)           Cloud Backend (服务器)
├── UI 界面                      ├── CDP 录制控制                  ├── 用户管理
├── 进程管理                     ├── Workflow 执行                 ├── 数据存储
└── API 调用                     ├── 浏览器管理 (复用 base_app)    ├── Intent 提取
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

### 3.1 整体架构图 (v3.0 - Desktop App Only)

```
┌─────────────────────────────────────────────────────────────┐
│                   User's Computer (macOS)                   │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  Desktop App (Tauri)                                   │ │
│  │  ┌─────────────────────────────────────────────────┐  │ │
│  │  │ Frontend (React/Vue)                             │  │ │
│  │  │  ├─ 录制控制面板                                  │  │ │
│  │  │  ├─ Workflow 列表页                              │  │ │
│  │  │  └─ 执行监控面板                                  │  │ │
│  │  └──────────────────┬──────────────────────────────┘  │ │
│  │                     │ Tauri Commands                   │ │
│  │  ┌──────────────────┴──────────────────────────────┐  │ │
│  │  │ Backend (Rust)                                   │  │ │
│  │  │  Tauri Commands:                                 │  │ │
│  │  │  ├─ start_recording(url)                         │  │ │
│  │  │  ├─ stop_recording(session_id)                   │  │ │
│  │  │  ├─ execute_workflow(name)                       │  │ │
│  │  │  └─ get_workflow_status(task_id)                 │  │ │
│  │  │                                                   │  │ │
│  │  │  调用 Python (PyO3 或 subprocess)                 │  │ │
│  │  └──────────────────┬──────────────────────────────┘  │ │
│  └─────────────────────┼─────────────────────────────────┘ │
│                        │ Python 函数调用 (非 HTTP)         │
│  ┌─────────────────────┴─────────────────────────────────┐ │
│  │  App Backend (Python 库，非 HTTP 服务)               │ │
│  │  ├── cdp_recorder.py (CDP 注入脚本) **新增**         │ │
│  │  ├── storage_manager.py (本地文件管理)                 │ │
│  │  ├── cloud_client.py (调用云端 API)                   │ │
│  │  ├── browser_manager.py (复用 base_app)              │ │
│  │  └── workflow_executor.py (复用 base_app)            │ │
│  │                                                         │ │
│  │  复用现有代码:                                          │ │
│  │  ├── behavior_tracker.js (CDP 注入,需适配)           │ │
│  │  └── base_app/base_agent/ (Workflow 执行引擎)        │ │
│  │                                                         │ │
│  │  本地存储:                                             │ │
│  │  ~/.ami/                                               │ │
│  │  ├── users/{user_id}/workflows/                        │ │
│  │  ├── users/{user_id}/recordings/                       │ │
│  │  └── logs/                                             │ │
│  └────────────────────┬──────────────────────────────────┘ │
│                       │ CDP Binding                         │
│  ┌────────────────────┴──────────────────────────────────┐ │
│  │  Chrome Browser (Playwright + CDP)                    │ │
│  │  ├── 注入 behavior_tracker.js                         │ │
│  │  ├── window.reportUserBehavior() → Python            │ │
│  │  └── 用户浏览器环境                                    │ │
│  └───────────────────────────────────────────────────────┘ │
└────────────────────────┼──────────────────────────────────┘
                         │ HTTPS (App Backend → Cloud)
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

### 3.2 数据流 (v3.0 更新)

#### **录制流程 (CDP 注入脚本 + Tauri IPC)**
```
1. Desktop App Frontend: 用户点击"开始录制"
   ↓ invoke("start_recording", {url: "https://..."})
2. Desktop App Rust Backend: 接收 Tauri Command
   ↓ 调用 Python 函数: start_recording(url)
3. App Backend (Python): cdp_recorder.py
   ↓ 启动 CDP 浏览器 (Playwright + CDP)
   ↓ 设置 CDP Binding (window.reportUserBehavior)
   ↓ 注入 behavior_tracker.js (复用现有代码)
   ↓ 导航到 url
   ↓ 返回: {"session_id": "xxx"}
4. 用户在浏览器中操作
   ↓ behavior_tracker.js 捕获事件
   ↓ window.reportUserBehavior(JSON.stringify({type: "click", ...}))
   ↓ CDP Binding → Python handle_runtime_binding()
   ↓ operations.append(operation)
5. Desktop App Frontend: 用户点击"停止录制"
   ↓ invoke("stop_recording", {session_id: "xxx"})
6. Desktop App Rust Backend: 接收 Tauri Command
   ↓ 调用 Python 函数: stop_recording(session_id)
7. App Backend (Python):
   ↓ 停止监控，关闭浏览器
   ↓ 保存 operations.json 到本地
     ~/.ami/users/{user_id}/recordings/{session_id}/operations.json
   ↓ 返回: {"operations_count": 42, "local_file_path": "..."}
8. Desktop App Frontend: 用户填写意图 (title + description)
   ↓ invoke("generate_workflow", {recording_id, title, description})
9. Desktop App Rust Backend:
   ↓ 调用 Python 函数: generate_workflow(...)
10. App Backend (Python):
    ↓ 上传到 Cloud Backend: HTTPS POST /api/recordings/upload
    ↓ 调用生成 API: HTTPS POST /api/recordings/{id}/generate
    ↓ 等待生成完成 (30-60s)
    ↓ 下载 workflow.yaml: HTTPS GET /api/workflows/{name}/download
    ↓ 保存到本地: ~/.ami/users/{user_id}/workflows/{name}/workflow.yaml
    ↓ 返回: {"workflow_name": "xxx"}
11. Desktop App: 显示 "Workflow 已生成！"
```

#### **执行流程 (复用 base_app + Tauri IPC)**
```
1. Desktop App Frontend: 用户点击"执行"
   ↓ invoke("execute_workflow", {workflow_name: "xxx"})
2. Desktop App Rust Backend: 接收 Tauri Command
   ↓ 调用 Python 函数: execute_workflow(workflow_name)
   ↓ 返回: {"task_id": "xxx", "status": "running"}
3. App Backend (Python): workflow_executor.py
   ↓ 加载本地 workflow.yaml
     ~/.ami/users/{user_id}/workflows/{name}/workflow.yaml
   ↓ 创建 BaseAgent 实例 (复用 base_app)
   ↓ 异步执行 workflow (不阻塞)
4. BaseAgent 执行 Workflow:
   - 复用全局浏览器会话 (BrowserSessionManager)
   - 执行各个 step (TextAgent, ToolAgent, etc.)
5. Desktop App Frontend: 轮询查询执行状态
   ↓ invoke("get_workflow_status", {task_id: "xxx"})
   ↓ 每 2 秒查询一次
6. App Backend (Python): 返回实时状态
   ↓ {"status": "running", "progress": 50, "current_step": "step_2"}
7. 执行完成:
   ↓ 保存结果到本地
     ~/.ami/users/{user_id}/workflows/{name}/executions/{id}/result.json
   ↓ (可选) 异步上报到云端: HTTPS POST /api/executions/report
8. Desktop App Frontend: 获取最终结果
   ↓ invoke("get_workflow_result", {task_id: "xxx"})
   ↓ 显示执行结果
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

### **阶段 1：创建 App Backend with CDP 录制（3 天）** v3.0 更新

#### Step 1.1: 创建目录结构
```bash
mkdir -p src/clients/app_backend/{config,controllers,services,models,static}
```

```
src/clients/app_backend/          # 位置更新
├── main.py                       # FastAPI 入口
├── config/
│   └── app-backend.yaml          # 配置文件
├── controllers/
│   ├── recording_controller.py   # CDP 录制控制 **更新**
│   └── execution_controller.py   # 执行控制
├── services/
│   ├── cdp_recorder.py           # CDP 浏览器启动、注入脚本 **新增**
│   ├── cloud_client.py           # Cloud API 客户端
│   ├── browser_manager.py        # 复用 base_app **更新**
│   ├── storage_manager.py        # 本地文件管理
│   └── workflow_executor.py      # 复用 base_app **更新**
├── models/
│   ├── recording.py              # 录制数据模型
│   └── execution.py              # 执行数据模型
├── static/
│   └── recorder.js               # 适配后的 behavior_tracker.js **新增**
├── core/
│   ├── config_service.py         # 配置管理
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

app = FastAPI(title="Ami App Backend", version="1.0.0")

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
    print("✅ App Backend started, browser session ready")

@app.on_event("shutdown")
async def shutdown():
    """关闭时清理资源"""
    await browser_manager.cleanup()
    print("✅ App Backend shutdown")

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

#### Step 1.4: 测试 App Backend

```bash
cd app-backend
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

**（已完成）Legacy client/web/backend → `src/cloud_backend/`**：

```bash
# 迁移文件映射
legacy client/web/backend/auth.py 
  → `src/cloud_backend/api/auth.py`

legacy client/web/backend/learning_service.py 
  → `src/cloud_backend/services/learning_service.py`

legacy client/web/backend/database.py 
  → `src/cloud_backend/database/models.py`

`src/intent_builder/` 
  → `src/cloud_backend/services/` (整合)
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

# 复制 legacy client/web/backend/learning_service.py
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

#### Step 3.2: 更新 App Backend 配置

```python
# app-backend/config.py

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

**App Backend 配置**：
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

### **阶段 5：Desktop App 开发（5 天）** v3.0 新增

#### Step 5.1: Tauri 项目初始化
```bash
cd src/clients
npm create tauri-app
# 选择: desktop_app, React/Vue, TypeScript
```

#### Step 5.2: Tauri Backend (Rust)
```rust
// src-tauri/src/app_backend.rs

use std::process::{Command, Child};

pub fn start_app_backend() -> Result<Child, std::io::Error> {
    // 启动 App Backend 进程
    Command::new("python")
        .arg("../../app_backend/main.py")
        .spawn()
}

pub fn stop_app_backend(child: &mut Child) {
    child.kill().ok();
}
```

```rust
// src-tauri/src/main.rs

#[tauri::command]
async fn start_recording(url: String) -> Result<String, String> {
    // 调用 App Backend API
    let client = reqwest::Client::new();
    let res = client.post("http://localhost:8000/api/recording/start")
        .json(&serde_json::json!({"start_url": url}))
        .send()
        .await
        .map_err(|e| e.to_string())?;

    let body = res.json::<serde_json::Value>().await.map_err(|e| e.to_string())?;
    Ok(body["session_id"].as_str().unwrap().to_string())
}

#[tauri::command]
async fn stop_recording(session_id: String) -> Result<String, String> {
    let client = reqwest::Client::new();
    let res = client.post("http://localhost:8000/api/recording/stop")
        .json(&serde_json::json!({"session_id": session_id}))
        .send()
        .await
        .map_err(|e| e.to_string())?;

    let body = res.json::<serde_json::Value>().await.map_err(|e| e.to_string())?;
    Ok(body["recording_id"].as_str().unwrap().to_string())
}
```

#### Step 5.3: Frontend UI (React/Vue)
```typescript
// src/pages/RecordingPage.tsx

import { useState } from 'react';
import { invoke } from '@tauri-apps/api/tauri';

export function RecordingPage() {
    const [isRecording, setIsRecording] = useState(false);
    const [sessionId, setSessionId] = useState('');

    const startRecording = async () => {
        const sid = await invoke('start_recording', { url: 'https://google.com' });
        setSessionId(sid);
        setIsRecording(true);
    };

    const stopRecording = async () => {
        await invoke('stop_recording', { sessionId });
        setIsRecording(false);
    };

    return (
        <div>
            <h1>录制控制</h1>
            {!isRecording ? (
                <button onClick={startRecording}>开始录制</button>
            ) : (
                <button onClick={stopRecording}>停止录制</button>
            )}
        </div>
    );
}
```

#### Step 5.4: 集成测试
- Desktop App → App Backend 通信测试
- 完整流程测试（录制 → 生成 → 执行）

---

### **阶段 6：清理旧代码（1 天）**

#### Step 6.1: 暂停 Extension 开发
```bash
# 标记为暂停开发
echo "# 暂停开发 - v3.0 优先 Desktop App" > src/clients/chrome-extension/PAUSED.md
```

#### Step 6.2: 删除废弃代码
```bash
# 删除旧 Backend
rm -rf src/app_backend/  # 如果存在 v1.0/v2.0 的错误位置代码

# 删除旧数据库文件（如果需要）
# rm legacy client/web/backend/ami_users.db
```

#### Step 6.3: 更新文档
- 更新 README.md
- 更新 CLAUDE.md
- 标记 Extension 为暂停开发

---

## 6. 代码迁移计划 (v3.0 更新)

### 6.1 迁移/复用映射表

| 源文件/模块 | 目标位置 | 复用方式 | 说明 |
|------------|---------|---------|------|
| **CDP 录制脚本** (新增) | | | |
| `chrome-extension/public/behavior_tracker.js` | `app_backend/static/recorder.js` | 复制&适配 | 修改发送端点到 localhost:8000 |
| `chrome-extension/public/recorder.js` | `app_backend/static/recorder.js` | 复制&适配 | 添加 session_id 支持 |
| **base_app 复用** | | | |
| `base_app/base_agent/core/base_agent.py` | `app_backend/services/workflow_executor.py` | 直接调用 | Workflow 执行引擎 |
| `base_app/base_agent/tools/browser_session_manager.py` | `app_backend/services/browser_manager.py` | 直接调用 | 浏览器会话管理 |
| `base_app/base_agent/core/schemas.py` | `app_backend/models/` | 导入使用 | Workflow 数据模型 |
| `base_app/server/core/config_service.py` | `app_backend/core/config_service.py` | 复制&简化 | 配置管理 |
| **旧代码迁移** | | | |
| `client/web/backend/learning_service.py` | `cloud_backend/services/learning_service.py` | 迁移 | 移到云端 |
| `client/web/backend/auth.py` | `cloud_backend/api/auth.py` | 迁移 | 认证在云端 |
| `intent_builder/` | `cloud_backend/services/` | 整合 | Intent 提取、MetaFlow 生成 |
| **新实现** | | | |
| N/A | `app_backend/services/cdp_recorder.py` | 新实现 | CDP 浏览器启动、注入脚本 |
| N/A | `app_backend/services/cloud_client.py` | 新实现 | Cloud API 客户端 |
| N/A | `app_backend/services/storage_manager.py` | 新实现 | 本地文件管理 |
| N/A | `clients/desktop_app/` | 新实现 | Tauri Desktop App |
| **暂停/删除** | | | |
| `clients/chrome-extension/` | 暂停开发 | ⏸️ | v3.0 优先 Desktop App |
| `client/web/backend/agent_service.py` | **删除** | ❌ | 已废弃 |
| `client/web/frontend/` | **删除** | ❌ | 不需要 Web 前端 |

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
  └── data.databases.users: ~/ami/storage/...

backend.yaml (Web Backend)
  ├── database.path: dbfiles/ami.db
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

# App Backend
app_backend:
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

## 8. 测试策略（v3.0）

### 8.1 App Backend 测试

```python
# src/clients/app_backend/tests/conftest.py

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

@pytest.fixture
async def cdp_browser():
    # Mock CDP browser for testing
    from services.cdp_recorder import CDPRecorder
    recorder = CDPRecorder()
    await recorder.start_browser("https://example.com")
    yield recorder.browser
    await recorder.stop_browser()
```

**测试用例**：
```python
# test_recording.py
async def test_cdp_recording():
    """Test CDP script injection and recording"""
    recorder = CDPRecorder()
    session_id = await recorder.start_recording("https://example.com")

    # Simulate user operations
    await recorder.page.click("#button")

    operations = await recorder.get_operations()
    assert len(operations) > 0
    assert operations[0]["type"] == "click"

# test_workflow_executor.py
async def test_workflow_execution():
    """Test BaseAgent workflow execution"""
    from services.workflow_executor import WorkflowExecutor

    executor = WorkflowExecutor()
    result = await executor.execute(workflow_yaml, user_id="test_user")

    assert result["success"] == True
```

### 8.2 Cloud Backend 测试

```python
# src/clients/cloud_backend/tests/test_workflow_generation.py

async def test_generate_workflow():
    operations = load_test_operations()

    recording_id = await upload_recording(operations)
    workflow_name = await generate_workflow(recording_id)

    assert workflow_name.startswith("从-")
```

### 8.3 Desktop App 测试

```rust
// src/clients/desktop_app/src-tauri/tests/test_commands.rs

#[tokio::test]
async fn test_start_recording() {
    let url = "https://example.com".to_string();
    let result = start_recording(url).await;

    assert!(result.is_ok());
    let session_id = result.unwrap();
    assert!(!session_id.is_empty());
}

#[tokio::test]
async fn test_app_backend_connection() {
    // Test if Desktop App can connect to App Backend
    let client = reqwest::Client::new();
    let res = client.get("http://localhost:8000/health")
        .send()
        .await
        .unwrap();

    assert_eq!(res.status(), 200);
}
```

### 8.4 端到端测试

```python
# tests/e2e/test_complete_flow.py

async def test_recording_to_execution():
    # v3.0: Desktop App + CDP recording flow

    # 1. 启动 App Backend
    app_backend = await start_app_backend()

    # 2. 启动 Cloud Backend (本地)
    cloud_backend = await start_cloud_backend()

    # 3. 模拟 Desktop App CDP 录制
    recorder = CDPRecorder()
    session_id = await recorder.start_recording("https://example.com")

    # Simulate operations
    await recorder.page.click("#login")
    await recorder.page.fill("#username", "test")

    operations = await recorder.stop_recording()

    # 4. 验证生成
    workflow_yaml = await cloud_backend.generate_workflow(
        operations=operations,
        title="登录测试",
        description="自动登录系统"
    )
    assert "steps:" in workflow_yaml

    # 5. 验证执行
    result = await app_backend.execute_workflow(workflow_yaml)
    assert result["success"] == True
```

---

## 9. 风险与缓解（v3.0）

### 9.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| CDP 脚本注入失败或不稳定 | 高 | 复用已验证的 behavior_tracker.js，增加错误重试 |
| Desktop App (Tauri) 学习曲线 | 中 | 先实现最小原型，参考官方示例 |
| BaseAgent 接口不兼容 | 中 | 保留旧代码，通过适配层调用 |
| Cloud API 性能问题（生成慢） | 中 | 加载动画、异步处理 |
| 浏览器会话管理复杂度 | 中 | 复用 BrowserSessionManager，全局单例 |
| 本地存储路径迁移失败 | 低 | 提供迁移脚本和回退 |

### 9.2 进度风险

| 风险 | 缓解措施 |
|------|----------|
| Desktop App 开发时间超预期 | 先完成 App Backend + CDP，Desktop UI 可简化 |
| 代码复用适配工作量大 | 优先直接调用 base_app 接口，避免重写 |
| Extension 暂停导致功能缺失 | v3.0 完全替代 Extension 能力 |
| 预估时间不足 | 分阶段交付，核心功能优先 |

### 9.3 产品风险

| 风险 | 缓解措施 |
|------|----------|
| 用户需要安装桌面应用（vs 浏览器插件） | 强调 Desktop App 更强大、无权限限制 |
| Desktop App 跨平台兼容性 | Tauri 天然支持 macOS/Windows/Linux |
| Extension 用户流失 | 未来可独立开发 Extension 版本 |

---

## 10. 时间计划（v3.0）

### 总时间：约 18 天（新增 Desktop App 开发）

| 阶段 | 时间 | 关键里程碑 |
|------|------|------------|
| 阶段 0：准备 | 1 天 | 文档、分支准备 |
| 阶段 1：App Backend（CDP 录制） | 4 天 | CDP 录制功能可用，脚本注入成功 |
| 阶段 2：App Backend（执行） | 2 天 | BaseAgent 集成，workflow 执行 |
| 阶段 3：Cloud Backend | 5 天 | Workflow 生成可本地测试 |
| 阶段 4：Desktop App（Tauri） | 4 天 | 桌面应用基本界面和 API 调用 |
| 阶段 5：配置改造 | 1 天 | 路径统一，配置生效 |
| 阶段 6：测试验证 | 2 天 | 端到端流程跑通 |
| 阶段 7：清理 | 1 天 | 标记旧代码，更新文档 |

### Gantt 图

```
Week 1 (Days 1-5):
Day 1: 准备 + 文档更新
Day 2-3: App Backend CDP 录制框架
Day 4-5: CDP 脚本注入和录制测试

Week 2 (Days 6-10):
Day 6-7: App Backend Workflow 执行集成
Day 8-10: Cloud Backend 基础框架

Week 3 (Days 11-15):
Day 11-13: Cloud Backend Workflow 生成
Day 14-15: Desktop App Tauri 初始化

Week 4 (Days 16-18):
Day 16-17: Desktop App UI 和 API 集成
Day 18: 测试 + 清理
```

### 关键路径

```
准备 (1天)
   ↓
App Backend CDP 录制 (4天) ← 关键：复用 behavior_tracker.js
   ↓
App Backend 执行 (2天) ← 关键：调用 base_app
   ↓
Cloud Backend (5天) || Desktop App (4天) ← 可并行
   ↓
集成测试 (2天)
   ↓
清理 (1天)
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
| v1.0 | 2025-11-07 | 初始版本 (Extension + Desktop App 双产品线) |
| v2.0 | 2025-11-07 | Phase 1 & 2 完成，更新进度 |
| v3.0 | 2025-11-08 | **重大变更**: 暂停 Extension，专注 Desktop App Only。使用 CDP 注入脚本录制，无需浏览器插件。新增 Desktop App (Tauri) 和 cdp_recorder.py 组件 |

---

## 📊 当前进度（2025-11-08 更新 - v3.0）

**重构进度**: 5% ⏳ (v3.0 重新规划)

| 阶段 | 状态 | 进度 |
|------|------|------|
| 阶段 0: 准备与文档更新 | ⏳ 进行中 | 80% |
| 阶段 1: App Backend (CDP 录制) | ⏸️ 待开始 | 0% |
| 阶段 2: App Backend (执行) | ⏸️ 待开始 | 0% |
| 阶段 3: Cloud Backend | ⏸️ 待开始 | 0% |
| 阶段 4: Desktop App (Tauri) | ⏸️ 待开始 | 0% |
| 阶段 5: 配置改造 | ⏸️ 待开始 | 0% |
| 阶段 6: 测试验证 | ⏸️ 待开始 | 0% |
| 阶段 7: 清理 | ⏸️ 待开始 | 0% |

**v3.0 核心变更**:
- 🎯 **产品策略**: 暂停 Extension，专注 Desktop App
- 🔧 **录制方式**: CDP 注入 behavior_tracker.js（无需 Extension）
- 📦 **代码复用**: 直接调用 base_app，复用 behavior_tracker.js
- 🖥️ **新增组件**: Desktop App (Tauri)，cdp_recorder.py

**已完成的工作** (v3.0):
- ✅ v3.0 策略文档更新（refactoring_plan_2025-11-07.md）
- ✅ 架构图更新（Desktop App + CDP）
- ✅ 数据流更新（CDP 录制流程）
- ✅ 代码复用映射表

**下一步** (v3.0):
1. 更新 app_backend_requirements.md（CDP 录制需求）
2. 更新 app_backend_design.md（CDP 架构设计）
3. 创建 PAUSED.md 在 chrome-extension 目录
4. 开始实现 App Backend CDP 录制功能

