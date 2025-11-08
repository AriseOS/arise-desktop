# Ami Cloud Backend

云端数据处理和 AI 分析中心

## 职责

1. **用户管理** - 注册、登录、Token 管理
2. **录制数据处理** - 接收 operations.json，存储到 S3
3. **AI 分析** - Intent 提取、Intent Graph 构建、MetaFlow 生成、Workflow 生成
4. **Workflow 管理** - 存储 Workflow YAML，提供下载 API
5. **统计分析** - 接收执行上报，分析成功率

## 目录结构

```
cloud-backend/
├── main.py                    # FastAPI 入口
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
│   └── workflow.py
└── database/
    ├── models.py              # SQLAlchemy 模型
    └── connection.py          # 数据库连接
```

## 启动

```bash
cd cloud-backend
python main.py
```

访问：http://localhost:9000/docs

## 环境变量

```bash
# 数据库
export DATABASE_URL=postgresql://user:password@localhost/ami

# LLM API Keys
export ANTHROPIC_API_KEY=sk-...
export OPENAI_API_KEY=sk-...

# 存储路径（服务器本地文件系统）
export STORAGE_PATH=/var/lib/ami/storage
```

## 与其他组件通信

- ← **App Backend**: HTTPS (api.ami.com 或 localhost:9000)
- ❌ 不直接与 Desktop App 或 Extension 通信
