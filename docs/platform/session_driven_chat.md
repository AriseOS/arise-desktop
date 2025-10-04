# 会话驱动聊天API设计文档

## 概述

本文档描述将BaseApp的聊天API从当前的半无状态设计重构为明确的会话驱动设计，以解决多轮对话上下文管理的一致性问题。

## 当前问题分析

### 1. 设计不一致性
- **API层面**：`session_id` 为可选字段，暗示支持无状态交互
- **实现层面**：`AgentService` 自动创建会话，实际是有状态的
- **用户期望**：多轮对话需要明确的会话管理

### 2. 双重上下文管理
- **AgentService**：通过 `Session` 类管理会话历史
- **BaseAgent**：通过 `memory_manager` 管理对话上下文
- **问题**：重复的状态管理，职责不清晰

### 3. 数据持久化缺失
- 会话数据仅存储在内存中
- 服务重启后会话历史丢失
- 无法支持长期会话管理

## 目标设计

### 核心原则
1. **明确会话生命周期**：所有多轮对话必须基于明确创建的会话
2. **单一职责**：AgentService 负责会话管理，BaseAgent 负责消息处理
3. **数据持久化**：会话数据持久化存储，支持服务重启
4. **向后兼容**：提供迁移路径，不破坏现有客户端

## 详细设计

### 1. API接口变更

#### 1.1 聊天消息接口（修改）
```python
# 修改前
class ChatMessageRequest(BaseModel):
    message: str = Field(..., description="用户消息")
    session_id: Optional[str] = Field(None, description="会话ID")  # 可选
    user_id: str = Field(..., description="用户ID")

# 修改后
class ChatMessageRequest(BaseModel):
    message: str = Field(..., description="用户消息")
    session_id: str = Field(..., description="会话ID")  # 必填
    user_id: str = Field(..., description="用户ID")
```

#### 1.2 会话创建接口（保持不变）
```python
POST /api/v1/chat/session
{
    "user_id": "user_123",
    "title": "天气查询对话"  # 可选
}

Response:
{
    "session_id": "sess_uuid_here",
    "title": "天气查询对话",
    "created_at": "2024-01-01T10:00:00Z",
    "updated_at": "2024-01-01T10:00:00Z",
    "message_count": 0
}
```

#### 1.3 标准工作流程
```
1. 客户端创建新对话：POST /chat/session
2. 服务端返回session_id
3. 客户端发送消息：POST /chat/message (必须包含session_id)
4. 继续多轮对话，都使用相同session_id
5. 可选：查看历史 GET /chat/sessions/{session_id}/history
```

### 2. 数据模型设计

#### 2.1 会话数据结构
```python
class SessionModel(BaseModel):
    """持久化会话模型"""
    session_id: str = Field(..., description="会话唯一标识")
    user_id: str = Field(..., description="用户ID")
    title: str = Field(..., description="会话标题")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")
    status: str = Field(default="active", description="会话状态：active/archived/deleted")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="会话元数据")

class MessageModel(BaseModel):
    """持久化消息模型"""
    message_id: str = Field(..., description="消息唯一标识")
    session_id: str = Field(..., description="所属会话ID")
    role: str = Field(..., description="角色：user/assistant")
    content: str = Field(..., description="消息内容")
    timestamp: datetime = Field(..., description="消息时间")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="消息元数据")
```

#### 2.2 存储层设计
```python
class SessionStorage:
    """会话存储接口"""
    async def create_session(self, session: SessionModel) -> SessionModel
    async def get_session(self, session_id: str) -> Optional[SessionModel]
    async def update_session(self, session_id: str, updates: Dict) -> bool
    async def delete_session(self, session_id: str) -> bool
    async def list_user_sessions(self, user_id: str) -> List[SessionModel]
    
    async def add_message(self, message: MessageModel) -> MessageModel
    async def get_session_messages(self, session_id: str, limit: int = 50) -> List[MessageModel]
    async def delete_session_messages(self, session_id: str) -> bool

# 实现选项：
# - SQLiteSessionStorage：开发环境，使用SQLite
# - PostgreSQLSessionStorage：生产环境，使用PostgreSQL
# - InMemorySessionStorage：测试环境，内存存储
```

### 3. 架构层次重构

#### 3.1 职责重新分工

**AgentService 职责**：
- 会话生命周期管理（创建、查询、删除）
- 会话历史持久化
- 消息格式化和API适配
- 并发控制和错误处理

**BaseAgent 职责**：
- 处理单个消息的AI逻辑
- 工具调用和结果处理
- 可选的短期记忆管理（通过memory_manager）

#### 3.2 新的处理流程
```
1. 客户端请求 → API路由层
2. 验证session_id存在性 → AgentService
3. 加载会话上下文 → SessionStorage
4. 调用BaseAgent处理消息 → BaseAgent.process_user_input()
5. 保存消息到会话历史 → SessionStorage
6. 返回格式化响应 → 客户端
```

### 4. 实现步骤

#### 阶段1：数据层实现
- [ ] 创建 `SessionStorage` 接口和 `SQLiteSessionStorage` 实现
- [ ] 创建数据库表结构和迁移脚本
- [ ] 实现会话和消息的CRUD操作

#### 阶段2：服务层重构
- [ ] 重构 `AgentService.send_message()` 方法
- [ ] 移除内存 `Session` 类，使用持久化存储
- [ ] 添加会话验证逻辑

#### 阶段3：API层修改
- [ ] 修改 `ChatMessageRequest` 模型，使 `session_id` 必填
- [ ] 更新API文档和错误处理
- [ ] 添加会话不存在的错误处理

#### 阶段4：兼容性和测试
- [ ] 提供临时的向后兼容模式（可配置）
- [ ] 编写单元测试和集成测试
- [ ] 更新客户端示例代码

### 5. 配置变更

#### 5.1 新增配置项
```yaml
# baseapp.yaml
storage:
  session:
    type: "sqlite"  # sqlite | postgresql | memory
    database_url: "sqlite:///./data/sessions.db"
    # 或者
    # database_url: "postgresql://user:pass@localhost/sessions"
  
  # 向后兼容模式（可选）
  compatibility:
    auto_create_session: false  # 是否自动创建会话（兼容旧客户端）
```

### 6. 错误处理

#### 6.1 新增错误类型
```python
class SessionNotFoundError(HTTPException):
    """会话不存在错误"""
    def __init__(self, session_id: str):
        super().__init__(
            status_code=404,
            detail=f"Session {session_id} not found"
        )

class SessionPermissionError(HTTPException):
    """会话权限错误"""
    def __init__(self, session_id: str, user_id: str):
        super().__init__(
            status_code=403,
            detail=f"User {user_id} has no access to session {session_id}"
        )
```

#### 6.2 API错误响应示例
```json
{
    "detail": "Session sess_123 not found",
    "error_code": "SESSION_NOT_FOUND",
    "session_id": "sess_123"
}
```

### 7. 性能考虑

#### 7.1 缓存策略
- 活跃会话信息缓存（Redis或内存）
- 最近消息缓存，减少数据库查询
- 会话列表分页和索引优化

#### 7.2 数据库优化
```sql
-- 会话表索引
CREATE INDEX idx_sessions_user_id_updated ON sessions(user_id, updated_at DESC);
CREATE INDEX idx_sessions_status ON sessions(status);

-- 消息表索引
CREATE INDEX idx_messages_session_timestamp ON messages(session_id, timestamp DESC);
CREATE INDEX idx_messages_session_id ON messages(session_id);
```

### 8. 迁移策略

#### 8.1 现有数据迁移
由于当前数据仅在内存中，无需数据迁移。新系统启动后：
- 所有新对话都必须通过新API创建会话
- 可提供兼容模式支持旧客户端

#### 8.2 客户端迁移指南
```javascript
// 旧客户端代码
const response = await fetch('/api/v1/chat/message', {
    method: 'POST',
    body: JSON.stringify({
        message: "你好",
        user_id: "user_123"
        // session_id 可选
    })
});

// 新客户端代码
// 1. 先创建会话
const sessionResp = await fetch('/api/v1/chat/session', {
    method: 'POST',
    body: JSON.stringify({
        user_id: "user_123",
        title: "新对话"
    })
});
const { session_id } = await sessionResp.json();

// 2. 发送消息
const messageResp = await fetch('/api/v1/chat/message', {
    method: 'POST',
    body: JSON.stringify({
        message: "你好",
        user_id: "user_123",
        session_id: session_id  // 必填
    })
});
```

## 总结

这个重构将解决以下问题：
1. **明确的API语义**：多轮对话必须基于明确的会话
2. **数据持久化**：会话历史不会因服务重启而丢失
3. **清晰的职责分工**：AgentService专注会话管理，BaseAgent专注消息处理
4. **更好的扩展性**：支持会话级别的功能（分享、导出、标签等）

实施这个设计将使BaseApp具备更robust的多轮对话能力，为后续功能扩展奠定坚实基础。