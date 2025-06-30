# Web 客户端

基于现代Web技术栈的可视化Agent构建界面。

## 架构设计

### 纯前端应用
- **技术栈**: React + TypeScript + Tailwind CSS
- **状态管理**: Redux Toolkit
- **UI组件**: Ant Design + 自定义组件
- **代码编辑**: Monaco Editor (VS Code引擎)

### 通信方式
- **REST API**: 与 AgentBuilder Backend 的HTTP通信
- **WebSocket**: 实时状态更新和协作功能
- **认证**: JWT Token 或 OAuth2 集成

## 功能特性

### 1. 可视化Agent构建器
- 拖拽式工具选择和配置
- 实时预览Agent结构
- 可视化工作流编辑器
- 参数配置表单生成

### 2. 实时开发体验
- 在线代码编辑器
- 实时语法检查和智能提示
- Agent调试和测试工具
- 执行结果实时显示

### 3. 协作功能
- 多用户实时协作
- Agent模板分享
- 版本控制和历史记录
- 评论和审核系统

## 目录结构

```
web/
└── frontend/                  # React 前端应用
    ├── src/
    │   ├── components/       # 可复用组件
    │   │   ├── AgentBuilder/ # Agent构建组件
    │   │   ├── CodeEditor/   # 代码编辑器组件
    │   │   └── Common/       # 通用组件
    │   ├── pages/           # 页面组件
    │   │   ├── Dashboard/    # 仪表板页面
    │   │   ├── AgentCreate/  # Agent创建页面
    │   │   └── AgentManage/  # Agent管理页面
    │   ├── store/           # Redux状态管理
    │   │   ├── agent/       # Agent相关状态
    │   │   ├── tool/        # 工具相关状态
    │   │   └── ui/          # UI状态管理
    │   ├── services/        # API服务层
    │   │   ├── agentAPI.ts  # Agent相关API
    │   │   ├── toolAPI.ts   # 工具相关API
    │   │   └── websocket.ts # WebSocket连接
    │   ├── hooks/           # 自定义Hooks
    │   ├── utils/           # 工具函数
    │   └── types/           # TypeScript类型定义
    ├── public/              # 静态资源
    ├── package.json         # 依赖配置
    └── .env.example         # 环境变量示例
```

## 开发计划

### Phase 1: 基础界面
- [ ] 项目初始化和环境搭建
- [ ] 基础UI框架和组件库
- [ ] Agent创建向导界面
- [ ] 与AgentBuilder的API集成

### Phase 2: 高级功能
- [ ] 可视化工作流编辑器
- [ ] 代码编辑器集成
- [ ] 实时调试功能
- [ ] Agent测试工具

### Phase 3: 协作功能
- [ ] 用户系统和权限管理
- [ ] 实时协作编辑
- [ ] Agent模板市场
- [ ] 分享和导出功能