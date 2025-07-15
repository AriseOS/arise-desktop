# AgentCrafter 数据库架构文档

## 概述

AgentCrafter 系统使用统一的数据库架构，支持用户管理、Agent 管理和聊天历史记录。数据库采用 SQLite（开发环境）或 PostgreSQL（生产环境）。

## 数据库位置

- **主数据库**: `client/web/backend/agentcrafter_users.db` (SQLite)
- **迁移脚本**: `client/web/frontend/database/migrations/001_create_agent_tables.sql`

## 表结构详解

### 1. 用户管理相关表

#### 1.1 users 表（用户基础信息）

**功能**: 存储用户基本信息和认证数据

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,           -- 用户唯一ID
    username VARCHAR(50) UNIQUE NOT NULL,           -- 用户名（唯一）
    email VARCHAR(100) UNIQUE NOT NULL,             -- 邮箱（唯一）
    hashed_password VARCHAR(255) NOT NULL,          -- 密码哈希
    full_name VARCHAR(100),                         -- 全名（可选）
    is_active BOOLEAN DEFAULT TRUE,                 -- 是否激活
    is_admin BOOLEAN DEFAULT FALSE,                 -- 是否管理员
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 创建时间
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 更新时间
    last_login TIMESTAMP                            -- 最后登录时间
);

-- 索引
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_active ON users(is_active);
```

**字段说明**:
- `id`: 主键，自增整数
- `username`: 用户名，用于登录，必须唯一
- `email`: 邮箱地址，用于找回密码等，必须唯一
- `hashed_password`: 使用 bcrypt 加密的密码哈希
- `full_name`: 用户全名，可选字段
- `is_active`: 用户状态，false 表示被禁用
- `is_admin`: 管理员权限标识
- `created_at/updated_at`: 时间戳，自动维护
- `last_login`: 最后登录时间，用于统计

#### 1.2 user_sessions 表（用户会话管理）

**功能**: 管理用户登录会话，支持会话过期和多设备登录

```sql
CREATE TABLE user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,           -- 会话ID
    user_id INTEGER NOT NULL,                       -- 关联用户ID
    session_token VARCHAR(255) UNIQUE NOT NULL,     -- 会话令牌
    expires_at TIMESTAMP NOT NULL,                  -- 过期时间
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 创建时间
    is_active BOOLEAN DEFAULT TRUE,                 -- 是否有效
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 索引
CREATE INDEX idx_sessions_token ON user_sessions(session_token);
CREATE INDEX idx_sessions_user ON user_sessions(user_id);
CREATE INDEX idx_sessions_expires ON user_sessions(expires_at);
```

**字段说明**:
- `session_token`: 32字节随机生成的会话令牌
- `expires_at`: 会话过期时间，默认24小时
- `is_active`: 手动注销时设为 false

#### 1.3 chat_history 表（聊天历史记录）

**功能**: 存储用户与 AI 的对话历史

```sql
CREATE TABLE chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,           -- 记录ID
    user_id INTEGER NOT NULL,                       -- 用户ID
    session_id VARCHAR(100) NOT NULL,               -- 对话会话ID
    message TEXT NOT NULL,                          -- 用户消息
    response TEXT,                                  -- AI回复
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 创建时间
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 索引
CREATE INDEX idx_chat_user ON chat_history(user_id);
CREATE INDEX idx_chat_session ON chat_history(session_id);
CREATE INDEX idx_chat_time ON chat_history(created_at);
```

**字段说明**:
- `session_id`: 对话会话标识，用于分组相关消息
- `message`: 用户输入的消息内容
- `response`: AI 生成的回复内容

### 2. Agent 管理相关表

#### 2.1 agents 表（Agent 实例管理）

**功能**: 管理用户创建的 Agent 实例

```sql
CREATE TABLE agents (
    agent_id VARCHAR(255) PRIMARY KEY,              -- Agent唯一标识
    user_id INTEGER NOT NULL,                       -- 所属用户ID
    port INTEGER UNIQUE NOT NULL,                   -- 监听端口
    name VARCHAR(255) NOT NULL,                     -- Agent名称
    type ENUM('baseapp', 'custom') NOT NULL,        -- Agent类型
    status ENUM('running', 'stopped', 'error') DEFAULT 'stopped', -- 运行状态
    config JSON,                                    -- Agent配置
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 创建时间
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, -- 更新时间
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 索引
CREATE INDEX idx_agents_user ON agents(user_id);
CREATE INDEX idx_agents_port ON agents(port);
CREATE INDEX idx_agents_status ON agents(status);
CREATE INDEX idx_agents_type ON agents(type);
```

**字段说明**:
- `agent_id`: Agent 唯一标识符，如 "baseapp", "user_custom_001"
- `user_id`: 所属用户，支持用户隔离
- `port`: Agent 后端服务监听的端口，全局唯一
- `name`: 用户定义的 Agent 显示名称
- `type`: Agent 类型，baseapp（内置）或 custom（用户自定义）
- `status`: 运行状态，用于监控和管理
- `config`: JSON 格式的 Agent 配置参数

#### 2.2 port_allocation 表（端口分配管理）

**功能**: 管理端口池，确保端口不冲突

```sql
CREATE TABLE port_allocation (
    port INTEGER PRIMARY KEY,                       -- 端口号
    agent_id VARCHAR(255),                          -- 分配给的Agent ID
    allocated_at TIMESTAMP,                         -- 分配时间
    status ENUM('available', 'allocated') DEFAULT 'available', -- 分配状态
    
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id) ON DELETE SET NULL
);

-- 索引
CREATE INDEX idx_port_agent ON port_allocation(agent_id);
CREATE INDEX idx_port_status ON port_allocation(status);
```

**字段说明**:
- `port`: 端口号，作为主键
- `agent_id`: 分配给哪个 Agent，NULL 表示可用
- `allocated_at`: 分配时间戳
- `status`: available（可用）或 allocated（已分配）

**预置数据**:
```sql
-- 开发环境端口池：5001-5020
INSERT INTO port_allocation (port, status) VALUES 
(5001, 'available'), (5002, 'available'), (5003, 'available'),
-- ... 更多端口
(5020, 'available');

-- BaseApp 预置端口
INSERT INTO port_allocation (port, agent_id, allocated_at, status) VALUES 
(8888, 'baseapp', CURRENT_TIMESTAMP, 'allocated');
```

#### 2.3 agent_sessions 表（Agent 会话管理）

**功能**: 支持 Agent 的多会话对话

```sql
CREATE TABLE agent_sessions (
    session_id VARCHAR(255) PRIMARY KEY,            -- 会话ID
    agent_id VARCHAR(255) NOT NULL,                 -- 所属Agent
    user_id INTEGER NOT NULL,                       -- 所属用户
    title VARCHAR(255),                             -- 会话标题
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 创建时间
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, -- 更新时间
    
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 索引
CREATE INDEX idx_agent_sessions_agent ON agent_sessions(agent_id);
CREATE INDEX idx_agent_sessions_user ON agent_sessions(user_id);
CREATE INDEX idx_agent_sessions_time ON agent_sessions(created_at);
```

**字段说明**:
- `session_id`: 会话唯一标识符
- `agent_id`: 所属的 Agent
- `user_id`: 发起会话的用户
- `title`: 用户定义的会话标题，如"数据分析任务"

## 表关系图

```
users (1) ──┐
            ├── user_sessions (N)
            ├── chat_history (N)
            ├── agents (N)
            └── agent_sessions (N)

agents (1) ──┐
             ├── port_allocation (1)
             └── agent_sessions (N)

port_allocation (1) ── agents (0..1)
```

## 数据访问模式

### 1. 用户认证流程

```sql
-- 1. 用户登录验证
SELECT id, username, hashed_password, is_active 
FROM users 
WHERE username = ? AND is_active = TRUE;

-- 2. 创建会话
INSERT INTO user_sessions (user_id, session_token, expires_at) 
VALUES (?, ?, ?);

-- 3. 验证会话
SELECT u.* FROM users u 
JOIN user_sessions s ON u.id = s.user_id 
WHERE s.session_token = ? 
  AND s.is_active = TRUE 
  AND s.expires_at > CURRENT_TIMESTAMP;
```

### 2. Agent 管理流程

```sql
-- 1. 获取用户的所有 Agent
SELECT * FROM agents 
WHERE user_id = ? 
ORDER BY created_at DESC;

-- 2. 创建新 Agent（事务）
BEGIN TRANSACTION;
  -- 分配端口
  UPDATE port_allocation 
  SET status = 'allocated', agent_id = ?, allocated_at = CURRENT_TIMESTAMP 
  WHERE port = (
    SELECT port FROM port_allocation 
    WHERE status = 'available' 
    ORDER BY port LIMIT 1
  );
  
  -- 创建 Agent
  INSERT INTO agents (agent_id, user_id, port, name, type, config) 
  VALUES (?, ?, ?, ?, ?, ?);
COMMIT;

-- 3. Agent 状态更新
UPDATE agents 
SET status = ?, updated_at = CURRENT_TIMESTAMP 
WHERE agent_id = ? AND user_id = ?;
```

### 3. 权限控制查询

```sql
-- 确保用户只能访问自己的 Agent
SELECT a.* FROM agents a 
WHERE a.agent_id = ? AND a.user_id = ?;

-- 获取 Agent 的访问端口（用于请求转发）
SELECT port FROM agents 
WHERE agent_id = ? AND user_id = ? AND status = 'running';
```

## 性能优化

### 1. 索引策略

- **用户表**: username、email 唯一索引，is_active 条件索引
- **会话表**: session_token 唯一索引，expires_at 时间索引
- **Agent表**: user_id、port、status 组合索引
- **端口表**: status 条件索引，便于查找可用端口

### 2. 查询优化

```sql
-- 高效的端口分配查询
SELECT port FROM port_allocation 
WHERE status = 'available' 
ORDER BY port 
LIMIT 1 
FOR UPDATE; -- 防止并发分配

-- 分页查询用户 Agent
SELECT * FROM agents 
WHERE user_id = ? 
ORDER BY created_at DESC 
LIMIT ? OFFSET ?;
```

### 3. 数据清理

```sql
-- 定期清理过期会话
DELETE FROM user_sessions 
WHERE expires_at < CURRENT_TIMESTAMP 
  OR (is_active = FALSE AND created_at < DATE_SUB(NOW(), INTERVAL 7 DAY));

-- 清理旧的聊天记录（可选）
DELETE FROM chat_history 
WHERE created_at < DATE_SUB(NOW(), INTERVAL 90 DAY);
```

## 数据迁移和备份

### 1. 迁移脚本位置

- **初始化脚本**: `client/web/backend/database.py`
- **Agent表迁移**: `client/web/frontend/database/migrations/001_create_agent_tables.sql`

### 2. 备份策略

```bash
# SQLite 备份
cp agentcrafter_users.db agentcrafter_users_backup_$(date +%Y%m%d).db

# PostgreSQL 备份
pg_dump agentcrafter > agentcrafter_backup_$(date +%Y%m%d).sql
```

### 3. 环境配置

```python
# database.py 环境变量配置
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agentcrafter_users.db")

# 生产环境示例
# DATABASE_URL = "postgresql://user:password@localhost/agentcrafter"
```

## 安全考虑

### 1. 数据保护

- **密码**: 使用 bcrypt 哈希，永不存储明文密码
- **会话**: 使用安全随机令牌，定期轮换
- **权限**: 严格的用户数据隔离，防止越权访问

### 2. SQL 注入防护

- 所有查询使用参数化语句
- ORM（SQLAlchemy）提供额外保护层
- 输入验证和类型检查

### 3. 数据访问日志

```python
# 建议添加访问日志表
class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    action = Column(String(100), nullable=False)  # 'login', 'create_agent', etc.
    resource = Column(String(255))  # 操作的资源
    timestamp = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String(45))  # IPv6 兼容
```

## 部署注意事项

### 1. 生产环境配置

- 使用 PostgreSQL 替代 SQLite
- 配置连接池和超时设置
- 启用 SSL 连接
- 定期备份策略

### 2. 监控和维护

- 数据库连接数监控
- 慢查询日志分析
- 存储空间使用监控
- 定期性能优化

## 扩展计划

### 1. 未来可能的表结构

```sql
-- Agent 执行日志
CREATE TABLE agent_execution_logs (
    id INTEGER PRIMARY KEY,
    agent_id VARCHAR(255),
    user_id INTEGER,
    request_data TEXT,
    response_data TEXT,
    execution_time_ms INTEGER,
    status VARCHAR(50),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agent 性能统计
CREATE TABLE agent_metrics (
    id INTEGER PRIMARY KEY,
    agent_id VARCHAR(255),
    metric_name VARCHAR(100),
    metric_value DECIMAL(10,2),
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2. 分片策略

当数据量增长时，可以考虑：
- 按用户 ID 分片
- 按时间分片（聊天历史）
- 读写分离架构

这个数据库架构为 AgentCrafter 提供了坚实的数据基础，支持用户管理、Agent 管理和聊天功能的所有需求。