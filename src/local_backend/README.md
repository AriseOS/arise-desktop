# Ami Local Backend

用户电脑上的执行引擎和云端代理

## 职责

1. **录制控制** - 接收 Extension 发送的操作事件
2. **执行控制** - 使用 BaseAgent 执行 Workflow  
3. **云端代理** - 统一管理与 Cloud Backend 的通信
4. **本地存储** - 缓存 Workflow 和执行记录

## 目录结构

```
local-backend/
├── main.py                       # FastAPI 入口
├── controllers/
│   └── recording_controller.py   # 录制控制
├── services/
│   ├── cloud_client.py           # Cloud API 客户端
│   ├── storage_manager.py        # 本地文件管理
│   └── workflow_executor.py      # Workflow 执行
├── models/
│   └── ...                       # 数据模型
└── utils/
    └── ...                       # 工具函数
```

## 启动

```bash
cd local-backend
python main.py
```

访问：http://localhost:8000/docs

## 环境变量

```bash
# Cloud Backend URL
export CLOUD_API_URL=https://api.ami.com
# 或本地开发
export CLOUD_API_URL=http://localhost:9000
```

## 与其他组件通信

- ← **Desktop App**: HTTP/WebSocket (localhost:8000)
- ← **Chrome Extension**: WebSocket (ws://localhost:8000)
- → **Cloud Backend**: HTTPS (api.ami.com)
