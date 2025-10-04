# Agent 后端架构设计方案

## 📋 需求分析

### 场景约束
- **开发阶段**：每个 Agent 后端绑定固定端口
- **固定端口运行**：所有 Agent 后端服务始终运行，无需按需启动
- **动态创建**：用户可以通过平台创建新的 Agent，系统自动分配端口
- **统一访问**：前端通过统一路径 `/users/:userId/agents/:agentId/api/*` 访问所有 Agent

### 目标
- ✅ 统一访问入口：前端接口始终为 `/users/:userId/agents/:agentId/api/:function`
- ✅ 请求转发机制：后端统一接收请求，转发给对应端口上的 Agent
- ✅ 动态扩展 Agent：用户创建 Agent 时，系统分配端口并注册
- ✅ 简单高效实现：使用内存缓存 + 数据库存储 Agent ↔ 端口映射

## 🧭 架构总览

```
前端应用 (/users/:userId/agents/:agentId/api/*)
    ↓
主后端服务 (API Gateway - 端口 8000)
├── 解析 userId, agentId, function
├── 查询 Agent 注册表 (agentId → port)
├── 构造目标 URL (http://localhost:port/api/function)
└── 转发请求并返回响应
    ↓
Agent 注册表 (内存缓存 + SQLite/PostgreSQL)
├── agent_id → port 映射
├── Agent 元信息 (name, created_at, etc.)
└── 动态注册新 Agent
    ↓
独立 Agent 后端服务
├── Agent 1 (端口 5001)
├── Agent 2 (端口 5002)
├── BaseApp (端口 8888) - 已存在
└── 新创建的 Agent (端口 5003+)
```

## 🛠️ 代码修改方案

### 1. 后端主服务修改

#### 1.1 新增 Agent 注册表数据结构
```typescript
// 数据库表结构
interface AgentRegistry {
  agent_id: string;      // 主键，Agent唯一标识
  user_id: string;       // 所属用户ID
  port: number;          // 监听端口 (唯一)
  name: string;          // Agent名称
  status: 'running' | 'stopped' | 'error';
  created_at: Date;
  updated_at: Date;
}

// 内存缓存结构
const agentPortMap = new Map<string, number>();
const portUsageSet = new Set<number>();
```

#### 1.2 新增 Agent 管理 API 端点
```typescript
// src/services/agentAPI.ts 需要实现的后端端点

// 获取用户所有 Agent
GET /api/users/:userId/agents
Response: AgentRegistry[]

// 获取特定 Agent 信息
GET /api/users/:userId/agents/:agentId
Response: AgentRegistry

// 创建新 Agent
POST /api/users/:userId/agents
Request: { name: string, type: 'baseapp' | 'custom', config?: any }
Response: AgentRegistry

// 启动/停止 Agent
POST /api/users/:userId/agents/:agentId/start
POST /api/users/:userId/agents/:agentId/stop

// 删除 Agent
DELETE /api/users/:userId/agents/:agentId

// ⭐ 核心：Agent API 代理转发
ALL /api/users/:userId/agents/:agentId/api/*
- 解析 agentId，查找对应端口
- 转发请求到 http://localhost:port/api/*
- 返回 Agent 后端的响应
```

#### 1.3 请求转发逻辑实现
```typescript
// 伪代码示例 (Express.js)
app.all('/api/users/:userId/agents/:agentId/api/*', async (req, res) => {
  const { userId, agentId } = req.params;
  const apiPath = req.path.replace(`/api/users/${userId}/agents/${agentId}/api`, '');
  
  // 1. 权限检查：确保用户只能访问自己的 Agent
  if (!checkUserPermission(req.user, userId)) {
    return res.status(403).json({ error: 'Forbidden' });
  }
  
  // 2. 查找 Agent 端口
  const agentPort = await getAgentPort(agentId);
  if (!agentPort) {
    return res.status(404).json({ error: 'Agent not found' });
  }
  
  // 3. 构造目标 URL 并转发请求
  const targetUrl = `http://localhost:${agentPort}/api${apiPath}`;
  const proxyResponse = await axios({
    method: req.method,
    url: targetUrl,
    data: req.body,
    params: req.query,
    headers: { ...req.headers, host: undefined }
  });
  
  // 4. 返回 Agent 响应
  res.status(proxyResponse.status).json(proxyResponse.data);
});
```

### 2. 前端代码修改

#### 2.1 更新 AgentContainer 组件
```typescript
// src/pages/AgentContainer.tsx

// 修改 fetchAgentConfig 方法，调用真实 API
const fetchAgentConfig = useCallback(async () => {
  try {
    // 调用后端 API 获取真实 Agent 配置
    const agentInfo = await agentService.getAgentInfo(userId!, agentId!);
    setAgentConfig({
      id: agentInfo.agent_id,
      name: agentInfo.name,
      type: agentInfo.type,
      status: agentInfo.status,
      // 不再需要 frontend_url，因为都通过统一路由访问
    });
  } catch (err) {
    setError(err.message);
  }
}, [userId, agentId]);
```

#### 2.2 修改 BaseApp API 服务
```typescript
// src/services/baseappAPI.ts 

// 修改 baseURL，通过统一路由访问
const createBaseAppAPI = (userId: string, agentId: string = 'baseapp') => {
  return axios.create({
    baseURL: `/api/users/${userId}/agents/${agentId}/api`,
    headers: { 'Content-Type': 'application/json' }
  });
};

// 更新 baseappService 使用动态 API 客户端
export const createBaseAppService = (userId: string, agentId: string = 'baseapp') => {
  const api = createBaseAppAPI(userId, agentId);
  
  return {
    sendMessage: (data) => api.post('/v1/chat/message', data),
    createSession: (data) => api.post('/v1/chat/session', data),
    // ... 其他方法保持不变
  };
};
```

#### 2.3 实现 Agent 管理界面
```typescript
// 新增：src/pages/AgentManagePage.tsx
// 功能：
// - 显示用户所有 Agent 列表
// - Agent 状态监控 (running/stopped/error)
// - 创建新 Agent 的表单
// - 启动/停止/删除 Agent 操作
// - 访问 Agent 的链接

// 新增：src/components/AgentCreateModal.tsx  
// 功能：
// - Agent 创建表单 (名称、类型选择)
// - 调用创建 API
// - 自动分配端口并启动 Agent 后端
```

### 3. Agent 后端服务标准化

#### 3.1 Agent 后端接口规范
```typescript
// 所有 Agent 后端必须实现的标准接口

// 健康检查
GET /health
Response: { status: 'ok', service: 'agent-name', port: number }

// 核心 API (根据 Agent 类型不同而不同)
POST /api/v1/chat/message    // Chat类型 Agent
POST /api/v1/process         // 处理类型 Agent
GET  /api/v1/status          // 状态查询
```

#### 3.2 Agent 启动脚本
```bash
# 新增：scripts/start-agent.sh
#!/bin/bash
AGENT_ID=$1
PORT=$2
AGENT_TYPE=$3

echo "Starting Agent $AGENT_ID on port $PORT"

case $AGENT_TYPE in
  "baseapp")
    # BaseApp 已有启动逻辑，指定端口启动
    cd /path/to/baseapp && python main.py --port=$PORT
    ;;
  "custom")
    # 自定义 Agent，从模板创建并启动
    cp -r /templates/custom-agent /agents/$AGENT_ID
    cd /agents/$AGENT_ID && npm start -- --port=$PORT
    ;;
esac
```

### 4. 数据库表设计

#### 4.1 使用现有用户数据库
**推荐方案：与用户管理共享同一数据库，增加新表**

```sql
-- 假设现有用户表结构
-- users 表 (已存在)
-- CREATE TABLE users (
--     id INTEGER PRIMARY KEY AUTOINCREMENT,
--     username VARCHAR(255) UNIQUE NOT NULL,
--     email VARCHAR(255) UNIQUE NOT NULL,
--     password_hash VARCHAR(255) NOT NULL,
--     full_name VARCHAR(255),
--     is_active BOOLEAN DEFAULT true,
--     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
-- );

-- ⭐ 新增：agents 表
CREATE TABLE agents (
    agent_id VARCHAR(255) PRIMARY KEY,
    user_id INTEGER NOT NULL,           -- 关联到 users.id
    port INTEGER UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    type ENUM('baseapp', 'custom') NOT NULL,
    status ENUM('running', 'stopped', 'error') DEFAULT 'stopped',
    config JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 外键约束，确保数据一致性
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    
    INDEX idx_user_id (user_id),
    INDEX idx_port (port),
    INDEX idx_status (status)
);

-- ⭐ 新增：端口分配表 (可选，用于管理端口池)
CREATE TABLE port_allocation (
    port INTEGER PRIMARY KEY,
    agent_id VARCHAR(255),
    allocated_at TIMESTAMP,
    status ENUM('available', 'allocated') DEFAULT 'available',
    
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id) ON DELETE SET NULL,
    INDEX idx_agent_id (agent_id),
    INDEX idx_status (status)
);

-- ⭐ 新增：Agent 会话表 (支持多会话)
CREATE TABLE agent_sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    agent_id VARCHAR(255) NOT NULL,
    user_id INTEGER NOT NULL,
    title VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    
    INDEX idx_agent_id (agent_id),
    INDEX idx_user_id (user_id)
);

-- ⭐ 预置端口池数据 (开发阶段端口范围)
INSERT INTO port_allocation (port, status) VALUES 
(5001, 'available'), (5002, 'available'), (5003, 'available'),
(5004, 'available'), (5005, 'available'), (5006, 'available'),
(5007, 'available'), (5008, 'available'), (5009, 'available'),
(5010, 'available');

-- ⭐ 预置 BaseApp Agent (端口 8888)
INSERT INTO agents (agent_id, user_id, port, name, type, status) VALUES 
('baseapp', 1, 8888, 'BaseApp Chat Agent', 'baseapp', 'running');
```

#### 4.2 数据库架构优势

| 优势 | 说明 |
|------|------|
| ✅ 数据一致性 | 外键约束确保 Agent 与用户的关联关系 |
| ✅ 事务支持 | 创建 Agent 时可以在同一事务中处理用户验证和端口分配 |
| ✅ 简化部署 | 只需管理一个数据库实例 |
| ✅ 权限统一 | 基于用户 ID 的权限控制，与现有认证系统无缝集成 |
| ✅ 数据迁移简单 | 利用现有数据库备份和迁移机制 |

#### 4.3 查询示例

```sql
-- 获取用户所有 Agent
SELECT a.*, u.username 
FROM agents a 
JOIN users u ON a.user_id = u.id 
WHERE a.user_id = ?;

-- 获取可用端口
SELECT port FROM port_allocation 
WHERE status = 'available' 
ORDER BY port LIMIT 1;

-- 创建新 Agent (事务)
BEGIN TRANSACTION;
  -- 分配端口
  UPDATE port_allocation SET status = 'allocated', agent_id = ? WHERE port = ?;
  -- 创建 Agent
  INSERT INTO agents (agent_id, user_id, port, name, type) VALUES (?, ?, ?, ?, ?);
COMMIT;
```

## 📊 实施优先级

### Phase 1: 核心转发机制 (高优先级)
1. ✅ 实现 Agent 注册表 (内存 + SQLite)
2. ✅ 实现 API 转发逻辑 (`/api/users/:userId/agents/:agentId/api/*`)
3. ✅ 修改现有 BaseApp 通过新路由访问
4. ✅ 测试 BaseApp 在新架构下的功能完整性

### Phase 2: Agent 管理功能 (中优先级)  
1. ✅ 实现 Agent CRUD API
2. ✅ 创建 Agent 管理界面
3. ✅ 实现动态 Agent 创建和端口分配
4. ✅ 添加 Agent 状态监控

### Phase 3: 扩展和优化 (低优先级)
1. ✅ Agent 模板系统
2. ✅ 批量 Agent 操作
3. ✅ Agent 性能监控
4. ✅ 错误处理和日志记录

## 🎯 预期效果

实施完成后：

1. **用户体验**：通过统一界面管理所有 Agent，访问路径一致
2. **开发效率**：每个 Agent 独立开发，端口自动分配
3. **系统可维护性**：清晰的架构分层，易于调试和扩展
4. **向后兼容**：现有 BaseApp 无缝迁移到新架构

## 🚀 后续扩展方向

- **容器化部署**：替换固定端口为动态容器调度
- **服务发现**：引入 Redis/etcd 作为服务注册中心  
- **负载均衡**：支持同一 Agent 的多实例部署
- **监控告警**：Agent 健康检查和故障恢复机制