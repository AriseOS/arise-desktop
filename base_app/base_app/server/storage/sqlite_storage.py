"""
SQLite会话存储实现
"""
import json
import sqlite3
import aiosqlite
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path
import logging

from .interface import SessionStorage
from .models import SessionModel, MessageModel

logger = logging.getLogger(__name__)


class SQLiteSessionStorage(SessionStorage):
    """SQLite会话存储实现"""

    def __init__(self, database_path: str = "./data/sessions.db"):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = None

    async def initialize(self):
        """初始化数据库表结构"""
        async with aiosqlite.connect(str(self.database_path)) as db:
            # 创建会话表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    metadata TEXT DEFAULT '{}'
                )
            """)
            
            # 创建消息表
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    FOREIGN KEY (session_id) REFERENCES sessions (session_id) ON DELETE CASCADE
                )
            """)
            
            # 创建索引
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_user_id_updated 
                ON sessions(user_id, updated_at DESC)
            """)
            
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_status 
                ON sessions(status)
            """)
            
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session_timestamp 
                ON messages(session_id, timestamp DESC)
            """)
            
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session_id 
                ON messages(session_id)
            """)
            
            await db.commit()
            logger.info(f"Initialized SQLite session storage at {self.database_path}")

    async def create_session(self, session: SessionModel) -> SessionModel:
        """创建新会话"""
        async with aiosqlite.connect(str(self.database_path)) as db:
            await db.execute("""
                INSERT INTO sessions (session_id, user_id, title, created_at, updated_at, status, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                session.session_id,
                session.user_id,
                session.title,
                session.created_at.isoformat(),
                session.updated_at.isoformat(),
                session.status,
                json.dumps(session.metadata)
            ))
            await db.commit()
            logger.debug(f"Created session {session.session_id} for user {session.user_id}")
            return session

    async def get_session(self, session_id: str) -> Optional[SessionModel]:
        """根据ID获取会话"""
        async with aiosqlite.connect(str(self.database_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT session_id, user_id, title, created_at, updated_at, status, metadata
                FROM sessions WHERE session_id = ? AND status != 'deleted'
            """, (session_id,))
            
            row = await cursor.fetchone()
            if row:
                data = dict(row)
                data['metadata'] = json.loads(data['metadata'] or '{}')
                return SessionModel.from_dict(data)
            return None

    async def update_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """更新会话信息"""
        if not updates:
            return False
        
        # 构建更新语句
        set_clauses = []
        values = []
        
        for key, value in updates.items():
            if key in ['title', 'status']:
                set_clauses.append(f"{key} = ?")
                values.append(value)
            elif key == 'metadata':
                set_clauses.append("metadata = ?")
                values.append(json.dumps(value))
        
        # 始终更新 updated_at
        set_clauses.append("updated_at = ?")
        values.append(datetime.now().isoformat())
        
        values.append(session_id)  # WHERE条件
        
        async with aiosqlite.connect(str(self.database_path)) as db:
            cursor = await db.execute(f"""
                UPDATE sessions SET {', '.join(set_clauses)} 
                WHERE session_id = ?
            """, values)
            
            await db.commit()
            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Updated session {session_id}")
            return success

    async def delete_session(self, session_id: str) -> bool:
        """删除会话（软删除）"""
        return await self.update_session(session_id, {'status': 'deleted'})

    async def list_user_sessions(self, user_id: str, limit: int = 50, offset: int = 0) -> List[SessionModel]:
        """获取用户的会话列表"""
        async with aiosqlite.connect(str(self.database_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT session_id, user_id, title, created_at, updated_at, status, metadata
                FROM sessions 
                WHERE user_id = ? AND status = 'active'
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
            """, (user_id, limit, offset))
            
            rows = await cursor.fetchall()
            sessions = []
            for row in rows:
                data = dict(row)
                data['metadata'] = json.loads(data['metadata'] or '{}')
                sessions.append(SessionModel.from_dict(data))
            
            return sessions

    async def add_message(self, message: MessageModel) -> MessageModel:
        """添加消息到会话"""
        async with aiosqlite.connect(str(self.database_path)) as db:
            # 插入消息
            await db.execute("""
                INSERT INTO messages (message_id, session_id, role, content, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                message.message_id,
                message.session_id,
                message.role,
                message.content,
                message.timestamp.isoformat(),
                json.dumps(message.metadata)
            ))
            
            # 更新会话的最后更新时间
            await db.execute("""
                UPDATE sessions SET updated_at = ? WHERE session_id = ?
            """, (datetime.now().isoformat(), message.session_id))
            
            await db.commit()
            logger.debug(f"Added {message.role} message to session {message.session_id}")
            return message

    async def get_session_messages(self, session_id: str, limit: int = 50, offset: int = 0) -> List[MessageModel]:
        """获取会话的消息列表"""
        async with aiosqlite.connect(str(self.database_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT message_id, session_id, role, content, timestamp, metadata
                FROM messages 
                WHERE session_id = ?
                ORDER BY timestamp ASC
                LIMIT ? OFFSET ?
            """, (session_id, limit, offset))
            
            rows = await cursor.fetchall()
            messages = []
            for row in rows:
                data = dict(row)
                data['metadata'] = json.loads(data['metadata'] or '{}')
                messages.append(MessageModel.from_dict(data))
            
            return messages

    async def delete_session_messages(self, session_id: str) -> bool:
        """删除会话的所有消息"""
        async with aiosqlite.connect(str(self.database_path)) as db:
            cursor = await db.execute("""
                DELETE FROM messages WHERE session_id = ?
            """, (session_id,))
            
            await db.commit()
            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Deleted messages for session {session_id}")
            return success

    async def get_message_count(self, session_id: str) -> int:
        """获取会话的消息数量"""
        async with aiosqlite.connect(str(self.database_path)) as db:
            cursor = await db.execute("""
                SELECT COUNT(*) FROM messages WHERE session_id = ?
            """, (session_id,))
            
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def close(self):
        """关闭存储连接"""
        # SQLite连接是按需创建的，不需要持久连接
        logger.debug("SQLite session storage closed")

    async def hard_delete_session(self, session_id: str) -> bool:
        """物理删除会话和相关消息"""
        async with aiosqlite.connect(str(self.database_path)) as db:
            # 删除消息
            await db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            
            # 删除会话
            cursor = await db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            
            await db.commit()
            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Hard deleted session {session_id}")
            return success