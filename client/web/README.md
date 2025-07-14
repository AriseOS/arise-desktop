# ami.dev Web 客户端

基于 React + FastAPI 的 AI 代理构建平台，提供直观的用户界面来创建和管理智能代理应用。

## 功能特性

- 🏠 **现代化首页** - 类似 Loveable/v0/base44 的 AI 构建界面
- 🔧 **工作台** - 三栏式代理构建页面，包含输出日志、工作流展示、预览区
- 🔐 **用户系统** - 完整的注册/登录/用户管理
- 🌍 **国际化支持** - 中英文自动切换，支持系统语言检测
- 📱 **响应式设计** - 支持桌面和移动端
- 🎨 **现代 UI** - Ant Design + Tailwind CSS
- ⚡ **快速开发** - Vite 构建工具，热模块替换

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
# 或使用新的 dev 命令
cd frontend && npm run dev
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
npm start  # 或 npm run dev
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

- **前端**: React 18 + TypeScript 5 + Vite + Ant Design + Tailwind CSS
- **后端**: FastAPI + SQLAlchemy + SQLite
- **认证**: JWT + bcrypt 密码加密
- **状态管理**: Redux Toolkit
- **国际化**: react-i18next (支持中英文切换)

## 开发说明

### 前端配置

**构建工具**: 使用 Vite 替代 Create React App，提供更快的开发体验

**代理配置**: Vite 配置文件中已设置 API 代理到后端
```javascript
// vite.config.ts
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
  },
}
```

**环境变量**: Vite 使用 `import.meta.env` 替代 `process.env`
- `VITE_API_URL` - 后端 API 地址
- `VITE_BASEAPP_API_URL` - BaseApp API 地址

### API 接口
- `POST /api/login` - 用户登录
- `POST /api/register` - 用户注册  
- `GET /api/me` - 获取用户信息

### 国际化 (i18n)

**语言支持**: 
- 中文 (zh-CN) 
- English (en-US)

**自动检测**: 根据用户浏览器/系统语言自动选择
**手动切换**: 页面右上角语言切换器
**持久化**: 语言偏好保存在 localStorage

### 数据库
- 自动初始化 SQLite 数据库
- 位置：`backend/agentcrafter_users.db`

## 故障排除

1. **端口占用**: 确保 3000 和 8000 端口未被占用
2. **依赖问题**: 删除 `node_modules` 重新 `npm install`
3. **数据库问题**: 删除 `.db` 文件重新初始化
4. **登录失败**: 检查后端控制台的认证日志
5. **JavaScript 错误**: 检查浏览器控制台，确保 JavaScript 已启用
6. **环境变量**: Vite 项目使用 `VITE_` 前缀，不是 `REACT_APP_`