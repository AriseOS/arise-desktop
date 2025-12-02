# Ami 系统架构设计文档

**版本**: v2.0  
**日期**: 2025-11-07  
**状态**: 正式版  
**负责人**: 技术团队

---

## 目录

1. [系统概述](#1-系统概述)
2. [整体架构](#2-整体架构)
3. [核心组件设计](#3-核心组件设计)
4. [数据流设计](#4-数据流设计)
5. [数据模型设计](#5-数据模型设计)
6. [API 设计](#6-api-设计)
7. [部署架构](#7-部署架构)
8. [安全设计](#8-安全设计)
9. [性能优化](#9-性能优化)
10. [监控与日志](#10-监控与日志)

---

## 1. 系统概述

### 1.1 产品定位

**Ami** 是首个通过观察学习的可进化 AI Agent。用户只需正常工作一次，Ami 就能学会如何自动化重复性任务，并持续优化和进化。

### 1.2 核心架构原则

- **本地优先**：录制和执行在用户电脑本地，保护隐私，降低成本
- **云端智能**：数据分析和 Workflow 生成在云端，利用强大算力和 LLM
- **职责分离**：App Backend（执行控制）与 Cloud Backend（数据分析）清晰分离
- **用户体验**：Desktop App + Chrome Extension 双界面，满足不同使用场景

### 1.3 技术选型

| 组件 | 技术栈 | 理由 |
|------|--------|------|
| Desktop App | Tauri (Rust + Web) | 轻量、跨平台、原生性能 |
| Chrome Extension | Manifest V3 | 录制真实浏览器环境，保留登录状态 |
| App Backend | Python 3.12 + FastAPI | 复用 BaseAgent，异步支持 |
| Cloud Backend | Python 3.12 + FastAPI | 与本地一致，易于维护 |
| BaseAgent | Python (browser-use) | 成熟的 Workflow 执行引擎 |
| 数据库（云端） | PostgreSQL | 可靠性、扩展性 |
| LLM | Anthropic Claude / OpenAI GPT | 强大的语义理解能力 |
| 对象存储 | S3 / GCS | 录制数据和 Workflow 文件存储 |

### 1.4 平台支持

- **macOS** 12+ (优先)
- **Windows** 10+ (后续支持)
- **Linux** (暂不支持)

---

## 2. 整体架构

### 2.1 四大组件关系

Ami 系统由四个核心组件构成：

```
┌──────────────────────────────────────────────────────────────────┐
│                        User's Computer                           │
│                                                                  │
│  ┌────────────────┐                  ┌─────────────────────┐    │
│  │ Desktop App    │◄────────────────►│ Chrome Extension    │    │
│  │ (Tauri)        │   WebSocket      │ (Manifest V3)       │    │
│  └────────┬───────┘                  └──────────┬──────────┘    │
│           │                                     │                │
│           │ 启动/监控                            │ WebSocket      │
│           ↓                                     ↓                │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │           App Backend (Python + FastAPI)                │   │
│  │           localhost:8000                                 │   │
│  │  ┌──────────────────────────────────────────────────┐    │   │
│  │  │ • Recording Controller (录制控制)                 │    │   │
│  │  │ • Execution Controller (执行控制)                 │    │   │
│  │  │ • Browser Manager (全局浏览器会话)                │    │   │
│  │  │ • Storage Manager (本地文件缓存)                  │    │   │
│  │  │ • Cloud Client (调用云端 API)                     │    │   │
│  │  └──────────────────────────────────────────────────┘    │   │
│  └──────────────────────┬───────────────────────────────────┘   │
└─────────────────────────┼───────────────────────────────────────┘
                          │ HTTPS
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Cloud Backend                                │
│                    (https://api.ami.com)                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ • Auth API (用户认证)                                     │   │
│  │ • Recording Service (接收录制数据)                        │   │
│  │ • Learning Service (Intent 提取 - LLM)                   │   │
│  │ • MetaFlow Service (MetaFlow 生成 - LLM)                 │   │
│  │ • Workflow Service (Workflow 生成 - LLM)                 │   │
│  │ • Storage Service (S3 对象存储管理)                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ PostgreSQL: users, recordings, workflows, intent_graphs  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 组件职责划分

#### **Desktop App (Tauri)**
**定位**：系统主控制中心

**职责**：
- 启动和监控 App Backend（独立进程）
- 提供 Workflow 管理界面（列表、详情、执行控制）
- 系统托盘（后台运行）
- 用户登录界面（调用 Cloud API）
- 本地设置管理

**技术栈**：
- Tauri (Rust Core)
- React + TypeScript (UI)
- 嵌入 Python Backend（打包后随 App 分发）

**与其他组件通信**：
- → App Backend: HTTP/WebSocket (localhost:8000)
- → Cloud Backend: HTTPS (通过 App Backend 转发)

---

#### **Chrome Extension**
**定位**：用户录制和快速执行界面

**职责**：
- 录制用户操作（点击、输入、导航）
- Workflow 快捷列表（在浏览器中快速查看）
- 一键执行 Workflow
- 实时显示执行进度

**技术栈**：
- Manifest V3
- Content Script（捕获页面事件）
- Background Service Worker（WebSocket 客户端）
- Popup UI（用户交互界面）

**与其他组件通信**：
- → App Backend: WebSocket (ws://localhost:8000)
- ❌ 不直接与 Cloud Backend 通信

**为什么不直接调 Cloud API？**
- 安全性：避免暴露 Cloud API Token 在 Extension 代码中
- 一致性：所有云端通信统一由 App Backend 管理
- 离线能力：本地缓存的 Workflow 可以直接执行

---

#### **App Backend**
**定位**：用户电脑上的执行引擎和云端代理

**职责**：
1. **录制控制**
   - 接收 Extension 发送的操作事件
   - 保存到本地文件（临时）
   - 上传到 Cloud Backend

2. **执行控制**
   - 加载本地 Workflow YAML
   - 调用 BaseAgent 执行
   - 管理全局浏览器会话（复用）

3. **云端代理**
   - 统一管理用户 Token
   - 调用 Cloud API（上传、下载、生成）
   - 处理云端响应

4. **本地存储**
   - Workflow 缓存（从云端下载后缓存）
   - 执行历史记录
   - 临时录制数据

**技术栈**：
- Python 3.12 + FastAPI
- WebSocket Server
- BaseAgent（简化版）

**存储位置**：
```
~/Library/Application Support/Ami/  (macOS)
├── users/{user_id}/
│   ├── workflows/           # Workflow YAML 缓存
│   ├── recordings/          # 临时录制数据
│   ├── executions/          # 执行历史
│   └── cache/               # 其他缓存
└── logs/                    # 日志
```

**与其他组件通信**：
- ← Desktop App: HTTP/WebSocket (localhost:8000)
- ← Chrome Extension: WebSocket (ws://localhost:8000)
- → Cloud Backend: HTTPS (api.ami.com)

---

#### **Cloud Backend**
**定位**：云端数据处理和 AI 分析中心

**职责**：
1. **用户管理**
   - 注册、登录、Token 管理

2. **录制数据处理**
   - 接收 operations.json
   - 存储到 S3
   - 元数据保存到 PostgreSQL

3. **AI 分析（核心）**
   - Intent Extraction (调用 Claude/GPT)
   - Intent Graph 构建和更新
   - MetaFlow 生成
   - Workflow YAML 生成

4. **Workflow 管理**
   - 存储 Workflow YAML（S3 + PostgreSQL）
   - 提供下载 API

5. **统计分析**
   - 接收执行上报
   - 分析成功率、耗时等

**技术栈**：
- Python 3.12 + FastAPI
- PostgreSQL（关系数据）
- S3 / GCS（对象存储）
- Anthropic Claude / OpenAI GPT

**与其他组件通信**：
- ← App Backend: HTTPS (api.ami.com)
- ❌ 不直接与 Desktop App 或 Extension 通信

---

### 2.3 完整架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         User's Computer                         │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Chrome Browser (User's Real Environment)                 │ │
│  │  ├── Chrome Extension (User Interface)                    │ │
│  │  │   ├── Popup UI (录制控制 + Workflow 列表)              │ │
│  │  │   ├── Content Script (捕获操作事件)                    │ │
│  │  │   └── Background Service Worker (状态管理)            │ │
│  │  │                                                         │ │
│  │  └── 用户工作环境（登录状态、Cookies、真实页面）         │ │
│  └───────────────────────────────────────────────────────────┘ │
│                          ↕ WebSocket / HTTP                     │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Tauri Desktop App (System Integration)                   │ │
│  │  ├── Tauri Core (Rust)                                    │ │
│  │  │   ├── System Tray (后台运行)                           │ │
│  │  │   ├── Auto Update                                      │ │
│  │  │   └── Process Manager (监控 Backend)                   │ │
│  │  │                                                         │ │
│  │  ├── Web UI (React)                                       │ │
│  │  │   ├── Workflow Manager                                 │ │
│  │  │   ├── Settings                                         │ │
│  │  │   └── Execution Monitor                                │ │
│  │  │                                                         │ │
│  │  └── 嵌入 Python Backend (PyInstaller)                     │ │
│  │      ├── FastAPI Server (localhost:8000)                  │ │
│  │      ├── LearningService (暂不用，云端处理)               │ │
│  │      ├── WorkflowService (执行管理)                       │ │
│  │      ├── StorageService (本地文件管理)                    │ │
│  │      └── BaseAgent (执行引擎)                             │ │
│  │          └── BrowserSessionManager (全局单例)             │ │
│  └───────────────────────────────────────────────────────────┘ │
│                          ↕ HTTPS                                │
└─────────────────────────────────────────────────────────────────┘
                             ↕ HTTPS
┌─────────────────────────────────────────────────────────────────┐
│                        Cloud Backend                            │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  API Gateway (nginx / ALB)                                 │ │
│  └───────────────┬───────────────────────────────────────────┘ │
│                  ↓                                              │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  FastAPI Application Server                                │ │
│  │  ├── Authentication Service                                │ │
│  │  ├── Recording Service (接收 operations.json)              │ │
│  │  ├── LearningService                                       │ │
│  │  │   ├── IntentExtractor (调用 LLM)                        │ │
│  │  │   ├── MetaFlowGenerator (调用 LLM)                      │ │
│  │  │   └── IntentGraphBuilder                                │ │
│  │  ├── WorkflowService                                       │ │
│  │  │   ├── WorkflowGenerator (调用 LLM)                      │ │
│  │  │   └── WorkflowValidator                                 │ │
│  │  └── Storage Service                                       │ │
│  └───────────────┬───────────────────────────────────────────┘ │
│                  ↓                                              │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  PostgreSQL (Relational Data)                              │ │
│  │  ├── users                                                 │ │
│  │  ├── recordings                                            │ │
│  │  ├── workflows                                             │ │
│  │  ├── intent_graphs                                         │ │
│  │  └── executions (统计数据)                                 │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Object Storage (Large Files)                              │ │
│  │  ├── recordings/{user_id}/{session_id}/operations.json     │ │
│  │  └── workflows/{user_id}/{workflow_name}/workflow.yaml     │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  External Services                                          │ │
│  │  ├── Anthropic Claude API                                  │ │
│  │  └── OpenAI GPT API                                        │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流图

```
┌─────────────────────────────────────────────────────────────────┐
│                       Recording Phase                           │
└─────────────────────────────────────────────────────────────────┘

User operates in Chrome
  ↓ (1) 点击、输入、导航
Content Script captures events
  ↓ (2) 封装为 Operation 对象
Background Service Worker
  ↓ (3) HTTP POST
App Backend API (/api/recording/operation)
  ↓ (4) 追加到文件
~/ami/storage/users/{user_id}/learning/{session_id}/operations.json


┌─────────────────────────────────────────────────────────────────┐
│                       Upload & Generate Phase                   │
└─────────────────────────────────────────────────────────────────┘

User clicks "Stop Recording"
  ↓
App Backend reads operations.json
  ↓ (5) HTTPS POST
Cloud API (/api/recordings/upload)
  ↓ (6) 保存到云端存储
PostgreSQL recordings table + Object Storage
  ↓ (7) 触发生成流程（同步）
LearningService.extract_intents(operations)
  ↓ (8) 调用 Claude API
返回 intents.json
  ↓ (9) 更新 Intent Graph
PostgreSQL intent_graphs table
  ↓ (10) 生成 MetaFlow
LearningService.generate_metaflow(intents, intent_graph)
  ↓ (11) 调用 Claude API
返回 metaflow.yaml
  ↓ (12) 生成 Workflow
WorkflowService.generate_workflow(metaflow)
  ↓ (13) 调用 Claude API
返回 workflow.yaml
  ↓ (14) 保存到云端
PostgreSQL workflows table + Object Storage
  ↓ (15) 返回 workflow_name
Client receives response


┌─────────────────────────────────────────────────────────────────┐
│                       Download & Execute Phase                  │
└─────────────────────────────────────────────────────────────────┘

User clicks "Execute" in Extension/App
  ↓ (16) HTTP GET
App Backend (/api/workflows/{name})
  ↓ (17) 检查本地缓存
If not exists:
  ↓ (18) HTTPS GET
Cloud API (/api/workflows/{name}/download)
  ↓ (19) 返回 workflow.yaml
  ↓ (20) 保存到本地
~/ami/storage/users/{user_id}/workflows/{name}/workflow.yaml
  ↓ (21) 加载 workflow
BaseAgent.run_workflow(workflow)
  ↓ (22) 设置 workflow.name = "global"
BrowserSessionManager.get_session("global")
  ↓ (23) 返回全局浏览器实例（复用）
BaseAgent executes each step
  ↓ (24) 操作浏览器
Playwright controls Chrome
  ↓ (25) 保存执行结果
~/ami/storage/users/{user_id}/workflows/{name}/executions/{execution_id}/result.json
  ↓ (26) 上传统计数据到云端（异步）
Cloud API (/api/executions/report)
```

---

## 3. 核心组件设计

### 3.1 Chrome Extension

#### 3.1.1 目录结构

```
chrome-extension/
├── manifest.json
├── popup/
│   ├── popup.html
│   ├── popup.js
│   └── popup.css
├── content/
│   └── content.js (注入到页面，捕获事件)
├── background/
│   └── service-worker.js (状态管理、API 通信)
├── assets/
│   ├── icon-16.png
│   ├── icon-48.png
│   └── icon-128.png
└── utils/
    └── api.js (与本地 Backend 通信)
```

#### 3.1.2 Content Script

**职责**：捕获用户操作事件

```javascript
// content.js

let isRecording = false;
let recordingSessionId = null;

// 监听来自 background 的消息
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'START_RECORDING') {
    isRecording = true;
    recordingSessionId = message.sessionId;
    attachEventListeners();
  } else if (message.type === 'STOP_RECORDING') {
    isRecording = false;
    removeEventListeners();
  }
});

function attachEventListeners() {
  document.addEventListener('click', handleClick, true);
  document.addEventListener('input', handleInput, true);
  // ... 更多事件
}

function handleClick(event) {
  if (!isRecording) return;
  
  const operation = {
    type: 'click',
    selector: getSelector(event.target),
    position: { x: event.clientX, y: event.clientY },
    timestamp: Date.now(),
    url: window.location.href,
  };
  
  // 发送到 background
  chrome.runtime.sendMessage({
    type: 'RECORD_OPERATION',
    operation: operation,
  });
}

function getSelector(element) {
  // 生成稳定的 CSS selector
  // 优先级：id > class > tag + nth-child
  if (element.id) return `#${element.id}`;
  if (element.className) return `.${element.className.split(' ')[0]}`;
  // ... 更复杂的选择器生成逻辑
}
```

#### 3.1.3 Background Service Worker

**职责**：状态管理、与本地 Backend 通信

```javascript
// service-worker.js

const BACKEND_URL = 'http://localhost:8000';
let currentSessionId = null;

// 开始录制
async function startRecording() {
  try {
    const response = await fetch(`${BACKEND_URL}/api/recording/start`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${await getAuthToken()}`,
      },
    });
    
    const { session_id } = await response.json();
    currentSessionId = session_id;
    
    // 通知所有 content scripts
    const tabs = await chrome.tabs.query({ active: true });
    for (const tab of tabs) {
      chrome.tabs.sendMessage(tab.id, {
        type: 'START_RECORDING',
        sessionId: session_id,
      });
    }
    
    return session_id;
  } catch (error) {
    console.error('Failed to start recording:', error);
    // 显示友好错误
    showErrorNotification('Backend 未启动，请打开 Ami 应用');
  }
}

// 记录操作
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'RECORD_OPERATION') {
    recordOperation(message.operation);
  }
});

async function recordOperation(operation) {
  try {
    await fetch(`${BACKEND_URL}/api/recording/operation`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${await getAuthToken()}`,
      },
      body: JSON.stringify({
        session_id: currentSessionId,
        operation: operation,
      }),
    });
  } catch (error) {
    console.error('Failed to record operation:', error);
  }
}

// 停止录制
async function stopRecording() {
  try {
    const response = await fetch(`${BACKEND_URL}/api/recording/stop`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${await getAuthToken()}`,
      },
      body: JSON.stringify({ session_id: currentSessionId }),
    });
    
    const { workflow_name } = await response.json();
    
    // 通知用户
    showSuccessNotification(`Workflow "${workflow_name}" 已生成！`);
    
    currentSessionId = null;
  } catch (error) {
    console.error('Failed to stop recording:', error);
  }
}
```

#### 3.1.4 Popup UI

```html
<!-- popup.html -->
<!DOCTYPE html>
<html>
<head>
  <link rel="stylesheet" href="popup.css">
</head>
<body>
  <div id="app">
    <!-- 未录制状态 -->
    <div id="idle-state">
      <button id="start-record">🔴 开始录制</button>
      <hr>
      <h3>我的 Workflows</h3>
      <div id="workflow-list"></div>
    </div>
    
    <!-- 录制中状态 -->
    <div id="recording-state" style="display:none;">
      <button id="stop-record">⏹️ 停止录制</button>
      <p>已捕获 <span id="op-count">0</span> 个操作</p>
    </div>
    
    <!-- 生成中状态 -->
    <div id="generating-state" style="display:none;">
      <p>⏳ 正在生成 Workflow...</p>
      <div class="progress-bar">
        <div id="progress" style="width:0%"></div>
      </div>
    </div>
  </div>
  <script src="popup.js"></script>
</body>
</html>
```

---

### 3.2 Tauri Desktop App

#### 3.2.1 目录结构

```
desktop-app/
├── src-tauri/
│   ├── src/
│   │   ├── main.rs (Tauri 主进程)
│   │   ├── backend.rs (管理 Python Backend 进程)
│   │   └── tray.rs (系统托盘)
│   ├── Cargo.toml
│   └── tauri.conf.json
├── src/
│   ├── App.tsx (React 主组件)
│   ├── pages/
│   │   ├── Workflows.tsx
│   │   ├── Settings.tsx
│   │   └── Help.tsx
│   ├── components/
│   │   ├── WorkflowCard.tsx
│   │   └── ExecutionMonitor.tsx
│   └── api/
│       └── client.ts (调用本地 Backend)
├── package.json
└── vite.config.ts
```

#### 3.2.2 Backend 进程管理

```rust
// backend.rs

use std::process::{Command, Child};
use std::path::PathBuf;

pub struct BackendManager {
    process: Option<Child>,
    port: u16,
}

impl BackendManager {
    pub fn new() -> Self {
        BackendManager {
            process: None,
            port: 8000,
        }
    }
    
    pub fn start(&mut self) -> Result<(), String> {
        // 获取打包的 Python Backend 路径
        let backend_path = get_backend_executable_path()?;
        
        // 检查端口是否被占用
        if is_port_in_use(self.port) {
            // 尝试其他端口
            for port in 8001..8100 {
                if !is_port_in_use(port) {
                    self.port = port;
                    break;
                }
            }
        }
        
        // 启动 Backend 进程
        let child = Command::new(backend_path)
            .arg("--port")
            .arg(self.port.to_string())
            .spawn()
            .map_err(|e| format!("Failed to start backend: {}", e))?;
        
        self.process = Some(child);
        
        // 等待 Backend 就绪
        wait_for_backend(self.port)?;
        
        Ok(())
    }
    
    pub fn stop(&mut self) {
        if let Some(mut process) = self.process.take() {
            let _ = process.kill();
        }
    }
    
    pub fn is_running(&self) -> bool {
        self.process.is_some()
    }
}

fn get_backend_executable_path() -> Result<PathBuf, String> {
    // macOS: Ami.app/Contents/Resources/backend/main
    // Windows: Ami\resources\backend\main.exe
    #[cfg(target_os = "macos")]
    let path = std::env::current_exe()?
        .parent().unwrap()
        .join("../Resources/backend/main");
    
    #[cfg(target_os = "windows")]
    let path = std::env::current_exe()?
        .parent().unwrap()
        .join("resources/backend/main.exe");
    
    Ok(path)
}
```

#### 3.2.3 React UI

```tsx
// Workflows.tsx

import React, { useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api';
import { WorkflowCard } from '../components/WorkflowCard';
import { apiClient } from '../api/client';

export function Workflows() {
  const [workflows, setWorkflows] = useState([]);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    loadWorkflows();
  }, []);
  
  async function loadWorkflows() {
    try {
      const data = await apiClient.get('/api/workflows');
      setWorkflows(data);
    } catch (error) {
      console.error('Failed to load workflows:', error);
    } finally {
      setLoading(false);
    }
  }
  
  async function executeWorkflow(name: string) {
    try {
      const result = await apiClient.post(`/api/workflows/${name}/execute`);
      // 显示执行监控器
      // ...
    } catch (error) {
      alert('执行失败：' + error.message);
    }
  }
  
  return (
    <div className="workflows-page">
      <h1>我的 Workflows</h1>
      {loading ? (
        <p>加载中...</p>
      ) : (
        <div className="workflow-grid">
          {workflows.map(workflow => (
            <WorkflowCard
              key={workflow.name}
              workflow={workflow}
              onExecute={() => executeWorkflow(workflow.name)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
```

---

### 3.3 后端服务 (FastAPI)

Intent Builder、录制上报和 Workflow 相关 API 现已统一在 `src/cloud_backend/` 中运行，负责与桌面端、Chrome 扩展和 App Backend 交互。

#### 3.3.1 目录结构

```
src/cloud_backend/
├── main.py                   # FastAPI 应用入口，注册所有路由
├── api/
│   └── auth.py               # 登录 / Token 颁发
├── services/
│   ├── learning_service.py   # Intent/MetaFlow 处理
│   ├── workflow_generation_service.py
│   └── storage_service.py    # 本地/对象存储管理
├── config/
│   ├── cloud-backend.yaml    # 配置文件
│   └── README.md             # 配置说明
├── core/
│   └── config_service.py     # 配置加载器
├── database/
│   ├── connection.py         # SQLAlchemy 会话
│   └── models.py             # ORM 模型 (RecordingSessionDB 等)
└── requirements.txt
```

#### 3.3.2 主应用

`src/cloud_backend/main.py` 直接创建 FastAPI 应用并在启动时初始化核心服务：

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.config_service import CloudConfigService
from services.storage_service import StorageService
from services.workflow_generation_service import WorkflowGenerationService

config_service = CloudConfigService()
cors_origins = config_service.get("cors.allow_origins", ["http://localhost:3000"])

app = FastAPI(title="Ami Cloud Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

storage_service: StorageService | None = None
workflow_generation_service: WorkflowGenerationService | None = None

@app.on_event("startup")
async def startup_event():
    """Attach file storage + workflow services"""
    global storage_service, workflow_generation_service
    storage_service = StorageService(
        base_path=config_service.get("storage.base_path", "~/ami-server")
    )
    workflow_generation_service = WorkflowGenerationService(
        llm_provider_name=config_service.get("llm.provider", "anthropic")
    )
```

主应用文件也在同一处定义录制、MetaFlow、Workflow 与 Intent Builder 路由，供桌面端与 Chrome 扩展统一调用。
#### 3.3.3 录制 & Workflow API

`src/cloud_backend/main.py` 同时暴露了录制、MetaFlow 及 Workflow 相关的 REST 接口，核心示例如下：

```python
@app.post("/api/recordings/upload")
async def upload_recording(data: dict):
    user_id = data.get("user_id")
    operations = data.get("operations", [])
    recording_id = data.get("recording_id") or str(uuid.uuid4())

    if not user_id or not operations:
        raise HTTPException(400, "Missing payload")

    file_path = storage_service.save_recording(
        user_id,
        recording_id,
        operations,
        task_description=data.get("task_description", ""),
        user_query=data.get("user_query")
    )
    logger.info(f"Recording saved: {file_path}")
    return {"recording_id": recording_id, "success": True}
```

关键端点：
- `POST /api/recordings/upload` —— 接收桌面端 / 扩展上报的操作序列，并写入服务器文件系统。
- `POST /api/recordings/{recording_id}/generate_metaflow` —— 触发 `LearningService`，从 operations 生成 MetaFlow。
- `POST /api/metaflows/{metaflow_id}/generate_workflow` —— 调用 `WorkflowGenerationService` 产出 YAML Workflow。
- `GET /api/recordings | /api/metaflows | /api/workflows` —— 列举和查询已存档的 artefacts。
- `POST /api/executions/report` —— 汇报 Workflow 执行统计。
- `/api/intent-builder/*` —— 提供 session 管理、流式输出和对话接口，支撑 Intent Builder IDE。

这些 API 取代了过去 legacy client/web/backend 下的拆分模块，现由单一 FastAPI 应用集中维护。

### 3.4 云端 Backend

#### 3.4.1 目录结构

```
cloud-backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py (SQLAlchemy models)
│   ├── schemas.py (Pydantic schemas)
│   ├── api/
│   │   ├── auth.py
│   │   ├── recordings.py
│   │   ├── workflows.py
│   │   └── executions.py
│   ├── services/
│   │   ├── learning_service.py
│   │   ├── workflow_service.py
│   │   └── intent_graph_service.py
│   └── utils/
│       ├── llm_client.py
│       └── storage.py
├── requirements.txt
└── Dockerfile
```

#### 3.4.2 云端生成流程

```python
# recordings.py

from fastapi import APIRouter, Depends, HTTPException
from services.learning_service import LearningService
from services.workflow_service import WorkflowService
from services.intent_graph_service import IntentGraphService

router = APIRouter()
learning_service = LearningService()
workflow_service = WorkflowService()
intent_graph_service = IntentGraphService()

@router.post("/upload")
async def upload_recording(
    operations: List[dict],
    user_id: int = Depends(get_current_user)
):
    """上传录制数据"""
    # 保存到数据库
    recording_id = await db.save_recording(user_id, operations)
    
    return {"recording_id": recording_id}

@router.post("/{recording_id}/generate-workflow")
async def generate_workflow(
    recording_id: str,
    user_id: int = Depends(get_current_user)
):
    """生成 Workflow（同步，30-60 秒）"""
    # 1. 读取 operations
    operations = await db.get_recording(recording_id)
    
    # 2. Intent Extraction (调用 LLM)
    intents = await learning_service.extract_intents(operations)
    
    # 3. 更新 Intent Graph
    intent_graph = await intent_graph_service.get_user_graph(user_id)
    updated_graph = await intent_graph_service.add_intents(
        intent_graph,
        intents
    )
    await db.save_intent_graph(user_id, updated_graph)
    
    # 4. 生成 MetaFlow (调用 LLM)
    metaflow = await learning_service.generate_metaflow(
        intents,
        updated_graph
    )
    
    # 5. 生成 Workflow YAML (调用 LLM)
    workflow_yaml, workflow_name = await workflow_service.generate_workflow(
        metaflow
    )
    
    # 6. 保存到数据库和对象存储
    await db.save_workflow(user_id, workflow_name, workflow_yaml)
    
    return {"workflow_name": workflow_name}
```

---

## 4. 数据模型设计

### 4.1 本地存储（文件系统）

```
~/ami/storage/users/{user_id}/
├── learning/                    # 临时数据（录制阶段）
│   └── {session_id}/
│       ├── operations.json      # 录制的操作序列
│       └── metadata.json        # 录制元数据
│
└── workflows/                   # 持久化数据
    └── {workflow_name}/
        ├── workflow.yaml        # 可执行的 Workflow
        ├── metadata.json        # 创建时间、描述等
        └── executions/          # 执行历史
            └── {execution_id}/
                ├── result.json
                └── logs.txt
```

**operations.json 格式**：

```json
{
  "session_id": "abc-123",
  "created_at": "2025-11-07T10:00:00Z",
  "operations": [
    {
      "type": "navigate",
      "url": "https://allegro.pl",
      "timestamp": 1699347600000
    },
    {
      "type": "input",
      "selector": "#search-box",
      "value": "kawa",
      "timestamp": 1699347605000
    },
    {
      "type": "click",
      "selector": "button[type='submit']",
      "position": { "x": 500, "y": 200 },
      "timestamp": 1699347610000
    }
  ]
}
```

**workflow.yaml 格式**（参考现有格式）：

```yaml
name: global  # 强制设置，复用全局浏览器
description: 从 Allegro 抓取咖啡产品数据
created_at: 2025-11-07T10:05:00Z

steps:
  - id: navigate_allegro
    type: tool
    tool: browser
    action: navigate
    params:
      url: https://allegro.pl
  
  - id: search_coffee
    type: tool
    tool: browser
    action: input
    params:
      selector: "#search-box"
      value: "kawa"
  
  - id: scrape_results
    type: scraper
    config:
      fields:
        - name: product_name
          selector: ".product-title"
        - name: price
          selector: ".price"
```

### 4.2 云端数据库（PostgreSQL）

#### users 表

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);
```

#### recordings 表

```sql
CREATE TABLE recordings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id),
    session_id UUID NOT NULL,
    operations_count INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    storage_path TEXT NOT NULL,  -- S3 路径
    INDEX idx_user_id (user_id)
);
```

#### workflows 表

```sql
CREATE TABLE workflows (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    workflow_name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    storage_path TEXT NOT NULL,  -- S3 路径
    UNIQUE(user_id, workflow_name),
    INDEX idx_user_id (user_id)
);
```

#### intent_graphs 表

```sql
CREATE TABLE intent_graphs (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    graph_data JSONB NOT NULL,  -- Intent Graph 的 JSON 表示
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### executions 表（统计数据）

```sql
CREATE TABLE executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id INTEGER REFERENCES workflows(id),
    user_id INTEGER REFERENCES users(id),
    status VARCHAR(50) NOT NULL,  -- running, completed, failed
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    INDEX idx_workflow_id (workflow_id),
    INDEX idx_user_id (user_id)
);
```

---

## 5. API 设计

### 5.1 本地 Backend API

#### 认证

```
POST /api/auth/login
POST /api/auth/register
POST /api/auth/refresh
```

#### 录制

```
POST /api/recording/start
  Response: { session_id: string }

POST /api/recording/operation
  Request: { session_id: string, operation: Operation }
  Response: { status: "ok" }

POST /api/recording/stop
  Request: { session_id: string }
  Response: { workflow_name: string }
```

#### Workflow

```
GET /api/workflows
  Response: [ { name, description, created_at, execution_count, success_rate } ]

GET /api/workflows/{name}
  Response: { name, description, yaml_content, metadata }

POST /api/workflows/{name}/execute
  Response: { task_id: string, status: "running" }

GET /api/workflows/tasks/{task_id}
  Response: { task_id, status, progress, result?, error? }

DELETE /api/workflows/{name}
  Response: { status: "ok" }
```

#### 系统

```
GET /health
  Response: { status: "ok", browser_sessions: number }

GET /api/system/status
  Response: { backend_version, browser_version, uptime }
```

### 5.2 云端 API

#### 录制与生成

```
POST /api/recordings/upload
  Request: { operations: Operation[] }
  Response: { recording_id: string }

POST /api/recordings/{recording_id}/generate-workflow
  Response: { workflow_name: string }
  (同步接口，30-60 秒)
```

#### Workflow

```
GET /api/workflows/{workflow_name}/download
  Response: { workflow_yaml: string, metadata: object }
```

#### 统计

```
POST /api/executions/report
  Request: { workflow_id, status, started_at, completed_at, error? }
  Response: { status: "ok" }
```

---

## 6. 部署架构

### 6.1 本地部署（用户电脑）

```
Ami.dmg / Ami.exe
├── Tauri App (UI)
├── Python Backend (打包后)
│   ├── main (executable)
│   ├── lib/ (依赖库)
│   └── browser/ (Chromium)
└── Chrome Extension (安装脚本)
```

**打包工具**：
- Tauri: `cargo build --release`
- Python: `pyinstaller main.py --onefile`
- Extension: 手动安装或通过 Desktop App 自动安装

### 6.2 云端部署

```
AWS / GCP / Azure
├── ALB (Load Balancer)
├── ECS / Kubernetes
│   └── FastAPI Containers (Auto Scaling)
├── RDS PostgreSQL (Multi-AZ)
└── S3 / GCS (对象存储)
```

**CI/CD**：
- GitHub Actions
- Docker build & push
- 滚动更新（Zero-downtime）

---

## 7. 安全设计

### 7.1 认证与授权

- **JWT Token**：30 分钟有效期，HttpOnly Cookie
- **Refresh Token**：7 天有效期
- **密码加密**：bcrypt (cost=12)

### 7.2 数据传输

- **本地 Backend ↔ Extension**：HTTP (localhost，不需要 HTTPS)
- **本地 Backend ↔ Cloud**：HTTPS (TLS 1.3)
- **Extension ↔ Cloud**：不直接通信

### 7.3 数据存储

- **本地文件权限**：chmod 600 (用户私有)
- **云端数据隔离**：所有查询带 `WHERE user_id = ?`
- **敏感数据**（MVP 限制）：暂无脱敏，记录为已知风险

---

## 8. 性能优化

### 8.1 浏览器会话复用

```python
# 全局单例，所有 workflow 复用
browser_manager = BrowserSessionManager()
await browser_manager.get_or_create_session("global")

# 成本对比：
# - 每次新建浏览器：$1-2/任务
# - 复用全局浏览器：$0.02-0.05/任务（降低 95%）
```

### 8.2 LLM 调用优化

- **批量处理**：多个 intent 一次 API 调用
- **缓存**：相似操作序列复用 intent
- **Prompt 优化**：减少 token 消耗

### 8.3 本地存储优化

- **增量写入**：operations.json 追加模式
- **定期清理**：超过 30 天的录制数据自动删除
- **压缩**：历史数据 gzip 压缩

---

## 9. 监控与日志

### 9.1 日志级别

```python
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('~/ami/logs/backend.log'),
        logging.StreamHandler()
    ]
)
```

### 9.2 关键指标

**本地 Backend**：
- 录制操作捕获延迟
- Workflow 执行成功率
- Backend 崩溃次数

**云端**：
- LLM API 调用成功率和延迟
- Workflow 生成耗时
- 用户活跃度（DAU/MAU）

### 9.3 错误上报

- **本地**：Extension 和 Backend 的错误日志
- **云端**：Sentry / Datadog
- **用户隐私**：脱敏后上报（不包含用户输入值）

---

## 附录

### A. 技术债务与限制

1. **MVP 不支持敏感数据脱敏**：录制可能包含密码，需在 V2 解决
2. **单浏览器实例**：同时只能执行一个 workflow
3. **无参数化**：每个场景需独立录制
4. **Chrome 限制**：不支持 Firefox、Safari

### B. 扩展性考虑

1. **水平扩展**：云端 API 无状态，可自动扩容
2. **数据库分片**：按 user_id 分片（未来百万用户）
3. **对象存储**：S3 无限容量，按需扩展
4. **浏览器池**：未来支持云端执行时，使用 Browserless 集群

---

**文档版本**: v1.0  
**下一步**: 技术评审 → 架构可行性验证 → 开发排期确定
