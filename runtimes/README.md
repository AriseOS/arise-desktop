# AgentCrafter Docker 配置

## 概述

AgentCrafter 项目包含两套独立的 Docker 配置：

## 目录结构

```
docker/
├── agentcrafter-platform/      # AgentCrafter 平台本身的 Docker 配置
│   ├── docker-compose.yml     # 平台服务编排
│   ├── Dockerfile             # 平台主应用镜像
│   ├── nginx/                 # 反向代理配置
│   ├── postgres/              # 数据库初始化
│   └── README.md
└── agent-runtime/              # 用户生成的 Agent 运行时配置
    ├── base/                  # Agent 基础运行环境
    ├── templates/             # Agent 容器模板
    ├── tools/                 # 工具运行环境镜像
    ├── configs/               # 安全和资源配置
    ├── scripts/               # 管理脚本
    └── README.md
```

## 两套配置的用途

### 🏢 agentcrafter-platform
**用途**: 部署和运行 AgentCrafter 平台本身

**包含**: API服务、Web界面、数据库、缓存、反向代理等

### 🤖 agent-runtime  
**用途**: 运行用户生成的 Agent

**包含**: Agent运行环境、工具镜像、安全配置、资源限制等

## 使用方式

1. **启动平台**: 使用 `agentcrafter-platform` 配置启动 AgentCrafter 系统
2. **Agent运行**: 平台自动使用 `agent-runtime` 配置运行用户生成的 Agent

详细说明请参考各目录下的 README.md 文件。