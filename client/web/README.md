# ami.dev Web 客户端

基于 React + FastAPI 的 AI 代理构建平台，提供直观的用户界面来创建和管理智能代理应用。

## 功能特性

- 🏠 **现代化首页** - 类似 Loveable/v0/base44 的 AI 构建界面
- 🔧 **工作台** - 三栏式代理构建页面，包含输出日志、工作流展示、预览区
- 🔐 **用户系统** - 完整的注册/登录/用户管理
- 📱 **响应式设计** - 支持桌面和移动端
- 🎨 **现代 UI** - Ant Design + Tailwind CSS

## 项目结构

```
web/
├── frontend/          # React 前端应用
├── backend/           # FastAPI 后端服务
├── start_backend.py   # 后端启动脚本
└── start_frontend.sh  # 前端启动脚本
```

## 安装步骤

### 1. 克隆仓库
```bash
git clone <repository-url>
cd agentcloud/agentcrafter/client/web
```

### 2. 安装后端依赖
```bash
cd backend
pip install -r requirements.txt
cd ..
```

### 3. 安装前端依赖
```bash
cd frontend
npm install
cd ..
```

## 启动服务

### 方法一：使用启动脚本（推荐）

**启动后端服务：**
```bash
# 在 web 目录下执行
python start_backend.py
```

**启动前端服务：**
```bash
# 在 web 目录下执行
./start_frontend.sh
# 或者手动进入前端目录
cd frontend && npm start
```

### 方法二：手动启动

**启动后端服务：**
```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**启动前端服务：**
```bash
cd frontend
npm start
```

### 服务地址
- 前端应用：`http://localhost:3000`
- 后端 API：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`

## 页面说明

- **首页** (`/`) - AI 代理构建入口页面
- **工作台** (`/workspace`) - 代理生成和管理工作区
- **登录** (`/login`) - 用户登录页面
- **注册** (`/register`) - 用户注册页面
- **控制台** (`/dashboard`) - 用户管理控制台

## 技术栈

- **前端**: React 18 + TypeScript + Ant Design + Tailwind CSS
- **后端**: FastAPI + SQLAlchemy + SQLite
- **认证**: JWT + bcrypt 密码加密
- **状态管理**: Redux Toolkit

## 开发说明

### 前端代理配置
前端已配置代理到后端：`"proxy": "http://localhost:8000"`

### API 接口
- `POST /api/login` - 用户登录
- `POST /api/register` - 用户注册  
- `GET /api/me` - 获取用户信息

### 数据库
- 自动初始化 SQLite 数据库
- 位置：`backend/agentcrafter_users.db`

## 故障排除

1. **端口占用**: 确保 3000 和 8000 端口未被占用
2. **依赖问题**: 删除 `node_modules` 重新 `npm install`
3. **数据库问题**: 删除 `.db` 文件重新初始化
4. **登录失败**: 检查后端控制台的认证日志