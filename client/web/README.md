# AgentCrafter Web Application

一个完整的 Web 应用程序，提供用户注册、登录和 AI 聊天功能。

## 功能特性

### 用户系统
- ✅ 用户注册和登录
- ✅ JWT 身份验证
- ✅ 用户会话管理
- ✅ 密码安全加密

### 聊天系统
- ✅ 实时 AI 聊天
- ✅ 聊天历史记录
- ✅ 会话管理
- ✅ 响应式界面

### 技术栈
- **后端**: FastAPI + SQLAlchemy + SQLite
- **前端**: React + TypeScript + Ant Design + Tailwind CSS
- **状态管理**: Redux Toolkit
- **身份验证**: JWT + bcrypt

## 项目结构

```
client/web/
├── backend/                 # 后端 API 服务
│   ├── __init__.py
│   ├── main.py             # FastAPI 应用主文件
│   ├── database.py         # 数据库模型和连接
│   ├── auth.py             # 用户认证服务
│   └── requirements.txt    # Python 依赖
├── frontend/               # React 前端应用
│   ├── public/            # 静态文件
│   ├── src/
│   │   ├── components/    # React 组件
│   │   ├── pages/        # 页面组件
│   │   ├── services/     # API 服务
│   │   ├── store/        # Redux 状态管理
│   │   └── hooks/        # 自定义 Hooks
│   ├── package.json      # 前端依赖
│   └── tailwind.config.js
├── start_backend.py       # 后端启动脚本
├── start_frontend.sh      # 前端启动脚本
└── README.md
```

## 快速开始

### 环境要求
- Python 3.9+
- Node.js 16+
- npm 或 yarn

### 启动后端服务

1. 运行后端启动脚本：
```bash
python start_backend.py
```

后端服务将在 `http://localhost:8000` 启动。

### 启动前端服务

1. 运行前端启动脚本：
```bash
./start_frontend.sh
```

前端服务将在 `http://localhost:3000` 启动。

### 手动启动（可选）

#### 后端
```bash
cd backend
pip install -r requirements.txt
python main.py
```

#### 前端
```bash
cd frontend
npm install
npm start
```

## API 文档

启动后端服务后，可以在以下地址查看 API 文档：
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 数据库

项目使用 SQLite 数据库，数据库文件会自动创建在 `backend/agentcrafter_users.db`。

### 数据表结构
- `users`: 用户信息表
- `user_sessions`: 用户会话表
- `chat_history`: 聊天历史表

## 使用说明

1. **注册账户**: 访问 `/register` 页面创建新账户
2. **登录**: 使用用户名和密码登录
3. **聊天**: 在主页面右侧聊天框中与 AI 助手对话
4. **退出**: 点击右上角头像菜单中的"退出登录"

## 开发指南

### 添加新的 API 端点

1. 在 `backend/main.py` 中添加新的路由
2. 在 `frontend/src/services/` 中添加对应的 API 调用
3. 在 Redux store 中添加相应的状态管理

### 自定义样式

项目使用 Ant Design + Tailwind CSS，可以：
- 修改 `frontend/src/App.css` 进行全局样式调整
- 在组件中使用 Tailwind 类名
- 通过 Ant Design 的 ConfigProvider 自定义主题

### 数据库迁移

如需修改数据库结构：
1. 修改 `backend/database.py` 中的模型
2. 删除现有数据库文件
3. 重新运行后端服务自动创建新表

## 部署

### 生产环境部署

1. **后端部署**:
```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

2. **前端部署**:
```bash
cd frontend
npm run build
# 将 build 文件夹部署到 Web 服务器
```

### 环境变量配置

创建 `.env` 文件配置环境变量：
```env
DATABASE_URL=sqlite:///./agentcrafter_users.db
SECRET_KEY=your-secret-key-here
REACT_APP_API_URL=http://localhost:8000
```

## 故障排除

### 常见问题

1. **后端启动失败**
   - 检查 Python 版本（需要 3.9+）
   - 确保依赖包正确安装

2. **前端启动失败**
   - 检查 Node.js 版本（需要 16+）
   - 删除 `node_modules` 文件夹重新安装

3. **API 请求失败**
   - 检查后端服务是否正常运行
   - 验证 API 端点地址是否正确

4. **数据库连接错误**
   - 确保有写入权限
   - 检查数据库文件路径

## 贡献指南

1. Fork 项目
2. 创建功能分支
3. 提交更改
4. 创建 Pull Request

## 许可证

MIT License