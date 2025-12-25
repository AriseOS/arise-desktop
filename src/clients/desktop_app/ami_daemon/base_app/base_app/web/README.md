# BaseApp Frontend

BaseApp 的 React 前端应用，提供与 AI 助手的对话界面。

## 功能特性

- 📱 响应式对话界面
- 💬 实时消息发送和接收
- 📝 会话管理（创建、选择、历史记录）
- 🔄 自动滚动到最新消息
- 🎨 现代化 UI 设计
- 🚀 React 18 + Hooks

## 技术栈

- React 18
- Axios (HTTP 客户端)
- UUID (唯一标识符生成)
- CSS3 (样式设计)

## 项目结构

```
src/
├── components/          # React 组件
│   ├── MessageList.js   # 消息列表组件
│   ├── MessageInput.js  # 消息输入组件
│   └── SessionList.js   # 会话列表组件
├── services/           # API 服务
│   └── api.js          # API 接口封装
├── App.js              # 主应用组件
├── App.css             # 应用样式
├── index.js            # 应用入口
└── index.css           # 全局样式
```

## 开发指南

### 启动开发服务器

```bash
# 进入 web 目录
cd base_app/base_app/web

# 安装依赖
npm install

# 启动开发服务器
npm start
```

应用将在 http://localhost:3000 启动

### 构建生产版本

```bash
npm run build
```

### 运行测试

```bash
npm test
```

## API 接口

前端通过以下 API 与后端通信：

- `POST /api/v1/chat/message` - 发送消息
- `POST /api/v1/chat/session` - 创建会话
- `GET /api/v1/chat/sessions` - 获取会话列表
- `GET /api/v1/chat/sessions/{session_id}/history` - 获取会话历史

## 配置

- 后端 API 地址：`http://localhost:8000` (可通过环境变量 `REACT_APP_API_URL` 配置)
- 默认用户 ID：`default-user`

## 使用说明

1. 应用启动后会自动加载已有的会话列表
2. 点击"新建对话"创建新的对话会话
3. 点击左侧会话列表切换不同的对话
4. 在底部输入框输入消息，按 Enter 发送
5. 支持 Shift+Enter 换行

## 开发注意事项

- 确保后端 FastAPI 服务器已启动并运行在 port 8000
- 开发时会自动代理 API 请求到后端服务器
- 所有组件都是函数组件，使用 React Hooks
- 响应式设计，支持移动端访问