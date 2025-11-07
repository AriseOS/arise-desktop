# Ami 四大核心组件概述

**版本**: v1.0  
**日期**: 2025-11-07  
**目的**: 清晰说明四大组件的职责、关系和通信方式

---

## 📦 四大核心组件

Ami 系统由四个核心组件构成，职责清晰分离：

```
┌─────────────────────────────────────────────┐
│          User's Computer (本地)             │
│                                             │
│  ┌──────────────┐      ┌─────────────────┐ │
│  │  Desktop App │      │ Chrome Extension│ │
│  │   (Tauri)    │      │  (Manifest V3)  │ │
│  └──────┬───────┘      └────────┬────────┘ │
│         │                       │          │
│         ↓                       ↓          │
│  ┌─────────────────────────────────────┐  │
│  │     Local Backend                   │  │
│  │     (Python + FastAPI)              │  │
│  │     localhost:8000                  │  │
│  └───────────────┬─────────────────────┘  │
└──────────────────┼────────────────────────┘
                   │ HTTPS
                   ↓
┌──────────────────────────────────────────────┐
│          Cloud Backend                       │
│          (Python + FastAPI)                  │
│          api.ami.com                         │
└──────────────────────────────────────────────┘
```

---

## 1️⃣ Desktop App (Tauri)

### **定位**
系统主控制中心，用户的主要操作界面

### **职责**
- ✅ 启动和监控 Local Backend（独立进程）
- ✅ 提供 Workflow 管理界面
  - Workflow 列表（显示所有可用的自动化流程）
  - Workflow 详情（查看步骤、执行历史）
  - 执行控制（开始、停止、查看进度）
- ✅ 用户登录界面
- ✅ 系统设置
- ✅ 系统托盘（后台运行）

### **技术栈**
- **Tauri** (Rust + Web)
- **React + TypeScript** (UI)
- 嵌入 **Python Backend**（打包在一起分发）

### **与其他组件的关系**
- → **Local Backend**: HTTP/WebSocket (localhost:8000)
  - 启动 Backend 进程
  - 调用 API 管理 Workflow
  - 监控 Backend 健康状态
  
- → **Cloud Backend**: HTTPS（通过 Local Backend 转发）
  - 不直接调用 Cloud API
  - 所有云端请求通过 Local Backend

- → **Chrome Extension**: 无直接通信
  - Extension 独立工作
  - 都通过 Local Backend 协调

### **用户场景**
```
用户打开 Desktop App
  ↓
登录账号（调用 Cloud API）
  ↓
查看 Workflow 列表
  ↓
选择一个 Workflow 点击"执行"
  ↓
查看执行进度和结果
```

---

## 2️⃣ Chrome Extension

### **定位**
用户在浏览器中的录制和快速执行界面

### **职责**
- ✅ **录制**用户操作
  - 捕获点击、输入、导航等事件
  - 实时发送到 Local Backend
  
- ✅ **快速执行** Workflow
  - 在浏览器中直接触发执行
  - 显示执行进度
  
- ✅ Workflow 快捷列表
  - 在 Popup 中显示常用 Workflow
  - 一键执行

### **技术栈**
- **Manifest V3**
- **Content Script**（注入到页面，捕获事件）
- **Background Service Worker**（WebSocket 客户端）
- **Popup UI**（用户交互）

### **与其他组件的关系**
- → **Local Backend**: WebSocket (ws://localhost:8000)
  - 发送录制事件
  - 触发 Workflow 执行
  - 接收执行进度更新
  
- ❌ **不直接**与 Cloud Backend 通信
  - 原因 1：安全性（避免暴露 Token）
  - 原因 2：一致性（统一由 Local Backend 管理）
  
- → **Desktop App**: 无直接通信
  - 独立工作
  - 都通过 Local Backend 协调

### **为什么不让 Extension 直接调 Cloud API？**
1. **安全性**：Extension 代码容易被查看，不应包含 Cloud API Token
2. **一致性**：所有云端通信统一由 Local Backend 管理（Token、重试、错误处理）
3. **离线能力**：本地缓存的 Workflow 可以在 Extension 中直接执行，无需云端

### **用户场景**
```
用户在浏览器中工作
  ↓
点击 Extension 图标 → "开始录制"
  ↓
正常操作网页（搜索、点击、填表单）
  ↓
点击 "停止录制"
  ↓
Extension 显示："正在生成 Workflow..."
  ↓
生成完成，提示："Workflow 已生成！点击执行"
  ↓
用户点击 Workflow → 自动执行，查看结果
```

---

## 3️⃣ Local Backend

### **定位**
用户电脑上的执行引擎和云端代理

### **核心价值**
- **执行引擎**：在本地执行 Workflow（控制浏览器）
- **云端代理**：统一管理与 Cloud Backend 的通信
- **数据缓存**：缓存 Workflow 和执行记录

### **四大职责**

#### **3.1 录制控制**
```
接收 Extension 发送的操作事件
  ↓
保存到本地文件（临时）
  ~/.ami/users/{user_id}/recordings/{session_id}/
  └── operations.json
  ↓
用户停止录制后，上传到 Cloud Backend
```

#### **3.2 执行控制**
```
加载本地 Workflow YAML
  ~/.ami/users/{user_id}/workflows/{name}/workflow.yaml
  ↓
强制设置 workflow.name = "global"（复用浏览器）
  ↓
调用 BaseAgent 执行
  ↓
管理全局浏览器会话（单例，所有 Workflow 共享）
  ↓
保存执行结果
```

#### **3.3 云端代理**
```
统一管理用户 Token
  ↓
调用 Cloud API
  - 上传录制数据
  - 触发 Workflow 生成
  - 下载 Workflow YAML
  - 上报执行统计
  ↓
处理云端响应（错误处理、重试）
```

#### **3.4 本地存储**
```
~/.ami/  (macOS)
├── users/{user_id}/
│   ├── workflows/           # Workflow YAML 缓存
│   ├── recordings/          # 临时录制数据
│   ├── executions/          # 执行历史
│   └── cache/               # 其他缓存
└── logs/                    # 日志
```

### **技术栈**
- **Python 3.12** + **FastAPI**
- **WebSocket Server**（与 Extension 通信）
- **BaseAgent**（简化版，Workflow 执行引擎）
- **BrowserSessionManager**（全局浏览器会话管理）

### **与其他组件的关系**
- ← **Desktop App**: HTTP/WebSocket (localhost:8000)
  - 接收 API 调用（管理 Workflow）
  
- ← **Chrome Extension**: WebSocket (ws://localhost:8000)
  - 接收录制事件
  - 接收执行请求
  - 推送执行进度
  
- → **Cloud Backend**: HTTPS (api.ami.com)
  - 上传、下载、生成
  - 统计上报

### **为什么需要 Local Backend？**
1. **执行控制**：需要 Python 的 BaseAgent 来控制浏览器（Extension 做不到）
2. **安全代理**：统一管理 Cloud Token，Extension 和 Desktop App 不直接暴露
3. **本地缓存**：离线时也能执行已有 Workflow
4. **性能优化**：全局浏览器会话复用（降低 95% 成本）

---

## 4️⃣ Remote Backend (原 Cloud Backend)

### **定位**
远程服务器上的数据处理和 AI 分析中心

**说明**：
- 这是运行在**远程服务器**上的后端（不是"云"服务，是普通服务器）
- 使用**服务器本地文件系统** + **PostgreSQL**
- 不依赖 AWS S3 / GCS 等云存储服务

### **核心价值**
- **AI 分析**：调用 LLM 提取 Intent、生成 Workflow
- **数据存储**：使用服务器文件系统 + PostgreSQL
- **知识积累**：构建 Intent Graph（未来可跨用户共享）

### **五大职责**

#### **4.1 用户管理**
```
注册、登录
  ↓
生成 JWT Token
  ↓
Token 管理（刷新、过期）
```

#### **4.2 录制数据处理**
```
接收 operations.json（从 Local Backend）
  ↓
保存到服务器文件系统
  /var/lib/ami/recordings/{user_id}/{session_id}/operations.json
  ↓
元数据保存到 PostgreSQL
  recordings 表（user_id, session_id, created_at, file_path）
```

#### **4.3 AI 分析（核心）**
```
读取 operations.json
  ↓
Intent Extraction（调用 Claude/GPT）
  提取用户操作的语义意图
  ↓
更新 Intent Graph（每用户独立）
  构建意图之间的关系网络
  ↓
生成 MetaFlow（调用 LLM）
  中间表示，连接 Intent 和 Workflow
  ↓
生成 Workflow YAML（调用 LLM）
  可执行的 Workflow 定义
  ↓
保存到 S3 + PostgreSQL
```

#### **4.4 Workflow 管理**
```
存储 Workflow YAML
  - 服务器文件系统: /var/lib/ami/workflows/{user_id}/{name}/workflow.yaml
  - PostgreSQL: 元数据（名称、创建时间等）
  ↓
提供下载 API（供 Local Backend 拉取）
```

#### **4.5 统计分析**
```
接收执行上报（从 Local Backend）
  - workflow_name
  - status (success/failed)
  - duration
  - error (if any)
  ↓
分析：
  - 成功率
  - 平均耗时
  - 常见错误
  ↓
未来用于改进 Workflow 生成
```

### **技术栈**
- **Python 3.12** + **FastAPI**
- **PostgreSQL**（关系数据）
- **服务器文件系统**（存储 YAML、JSON）
- **Anthropic Claude** / **OpenAI GPT**

### **与其他组件的关系**
- ← **Local Backend**: HTTPS (api.ami.com)
  - 接收上传、生成请求
  - 提供下载、查询 API
  
- ❌ **不直接**与 Desktop App 或 Extension 通信
  - 所有通信通过 Local Backend 中转

### **为什么数据要在远程服务器？**
1. **AI 分析**：需要调用 LLM（本地网络不稳定）
2. **知识积累**：构建 Intent Graph（未来可跨用户共享）
3. **数据备份**：用户换设备，Workflow 仍然可用
4. **网络效应**：用户越多，数据越丰富，模型越准（长期价值）

---

## 🔄 组件间数据流

### **完整流程：从录制到执行**

```
┌─────────────────────────────────────────────────────────────────┐
│  1. 录制阶段（完全本地）                                         │
└─────────────────────────────────────────────────────────────────┘
Extension 捕获操作
  ↓ WebSocket
Local Backend 保存到本地文件
  ~/.ami/users/123/recordings/abc/operations.json

┌─────────────────────────────────────────────────────────────────┐
│  2. 上传阶段（本地 → 云端）                                       │
└─────────────────────────────────────────────────────────────────┘
用户停止录制
  ↓
Local Backend 上传 operations.json
  ↓ HTTPS POST /api/recordings/upload
Cloud Backend 保存到 S3 + PostgreSQL
  返回 recording_id

┌─────────────────────────────────────────────────────────────────┐
│  3. 生成阶段（云端 AI 分析，30-60 秒）                            │
└─────────────────────────────────────────────────────────────────┘
Local Backend 触发生成
  ↓ HTTPS POST /api/recordings/{id}/generate
Cloud Backend:
  ├─ Intent Extraction (Claude API)
  ├─ Update Intent Graph
  ├─ Generate MetaFlow (Claude API)
  └─ Generate Workflow YAML (Claude API)
  ↓
保存到 S3 + PostgreSQL
  返回 workflow_name

┌─────────────────────────────────────────────────────────────────┐
│  4. 下载阶段（云端 → 本地）                                       │
└─────────────────────────────────────────────────────────────────┘
Local Backend 下载 Workflow
  ↓ HTTPS GET /api/workflows/{name}/download
Cloud Backend 返回 workflow.yaml
  ↓
Local Backend 保存到本地
  ~/.ami/users/123/workflows/从-allegro-抓取咖啡/workflow.yaml

┌─────────────────────────────────────────────────────────────────┐
│  5. 执行阶段（完全本地）                                         │
└─────────────────────────────────────────────────────────────────┘
用户触发执行（Extension 或 Desktop App）
  ↓ WebSocket / HTTP
Local Backend:
  ├─ 加载本地 workflow.yaml
  ├─ 强制设置 workflow.name = "global"
  └─ BaseAgent 执行（复用全局浏览器）
  ↓
执行完成，保存结果到本地
  ~/.ami/users/123/workflows/.../executions/xyz/result.json

┌─────────────────────────────────────────────────────────────────┐
│  6. 上报阶段（本地 → 云端，异步）                                │
└─────────────────────────────────────────────────────────────────┘
Local Backend 后台上报统计
  ↓ HTTPS POST /api/executions/report
Cloud Backend 记录：
  - workflow_name
  - status
  - duration
  - error
```

---

## 🎯 为什么这样设计？

### **职责分离的好处**

| 组件 | 职责 | 优势 |
|------|------|------|
| **Desktop App** | 用户界面 | 完整的 Workflow 管理体验 |
| **Extension** | 录制 + 快捷执行 | 在浏览器中便捷操作 |
| **Local Backend** | 执行 + 代理 | 控制浏览器、保护隐私、本地缓存 |
| **Cloud Backend** | AI + 存储 | 强大算力、数据积累、知识网络 |

### **关键设计决策**

1. **为什么录制在本地？**
   - 隐私保护（敏感操作不立即上传）
   - 离线可用（网络断了也能录制）

2. **为什么 AI 分析在云端？**
   - 需要 LLM（本地无法运行 Claude/GPT）
   - 需要算力（Intent Graph 构建复杂）
   - 数据积累（未来跨用户共享）

3. **为什么执行在本地？**
   - 效率高（无需远程浏览器）
   - 成本低（不需要云端浏览器实例）
   - 隐私好（登录状态在本地）

4. **为什么需要 Local Backend？**
   - Extension 是 JavaScript，无法运行 Python BaseAgent
   - 需要统一管理 Cloud Token（安全）
   - 需要本地缓存（离线执行）

---

## 📌 总结

**四大组件，各司其职**：
- 🖥️ **Desktop App**：主控制中心
- 🌐 **Chrome Extension**：录制和快速执行
- ⚙️ **Local Backend**：执行引擎 + 云端代理
- ☁️ **Cloud Backend**：AI 分析 + 数据存储

**数据流向**：
- **录制**：本地（隐私）
- **分析**：云端（AI）
- **执行**：本地（效率）

**设计理念**：
- 本地优先，云端协同
- 职责清晰，边界明确
- 用户隐私，AI 赋能

---

**相关文档**：
- [完整架构设计](./architecture.md)
- [需求分析](./requirements.md)
- [重构计划](./refactoring_plan_2025-11-07.md)
