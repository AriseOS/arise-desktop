"""
用户认证系统
"""
from datetime import datetime, timedelta
from typing import Optional
import secrets
import hashlib
from passlib.context import CryptContext
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from database import User, UserSession, get_db

# 密码加密配置
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT配置
SECRET_KEY = secrets.token_urlsafe(32)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

class AuthService:
    def __init__(self):
        self.pwd_context = pwd_context
        
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return self.pwd_context.verify(plain_password, hashed_password)
    
    def get_password_hash(self, password: str) -> str:
        """生成密码哈希"""
        return self.pwd_context.hash(password)
    
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None):
        """创建访问令牌"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    def verify_token(self, token: str) -> Optional[dict]:
        """验证令牌"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except JWTError:
            return None
    
    def authenticate_user(self, db: Session, username: str, password: str) -> Optional[User]:
        """验证用户"""
        print(f"[AUTH] 开始验证用户: username='{username}', password_length={len(password)}")
        
        user = db.query(User).filter(User.username == username).first()
        if not user:
            print(f"[AUTH] 用户不存在: username='{username}'")
            return None
        
        print(f"[AUTH] 找到用户: id={user.id}, username='{user.username}', email='{user.email}'")
        print(f"[AUTH] 存储的密码哈希: {user.hashed_password[:50]}...")
        
        password_valid = self.verify_password(password, user.hashed_password)
        print(f"[AUTH] 密码验证结果: {password_valid}")
        
        if not password_valid:
            print(f"[AUTH] 密码验证失败: username='{username}'")
            return None
        
        print(f"[AUTH] 认证成功: username='{username}'")
        return user
    
    def create_user(self, db: Session, username: str, email: str, password: str, full_name: str = None) -> User:
        """创建用户"""
        # 检查用户名是否已存在
        if db.query(User).filter(User.username == username).first():
            raise ValueError("用户名已存在")
        
        # 检查邮箱是否已存在
        if db.query(User).filter(User.email == email).first():
            raise ValueError("邮箱已存在")
        
        # 创建用户
        hashed_password = self.get_password_hash(password)
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            full_name=full_name
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    
    def get_current_user(self, db: Session, token: str) -> Optional[User]:
        """获取当前用户"""
        payload = self.verify_token(token)
        if payload is None:
            return None
        
        username = payload.get("sub")
        if username is None:
            return None
        
        user = db.query(User).filter(User.username == username).first()
        return user
    
    def create_session(self, db: Session, user_id: int) -> str:
        """创建用户会话"""
        session_token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=24)
        
        session = UserSession(
            user_id=user_id,
            session_token=session_token,
            expires_at=expires_at
        )
        db.add(session)
        db.commit()
        return session_token
    
    def verify_session(self, db: Session, session_token: str) -> Optional[User]:
        """验证会话"""
        session = db.query(UserSession).filter(
            UserSession.session_token == session_token,
            UserSession.is_active == True,
            UserSession.expires_at > datetime.utcnow()
        ).first()
        
        if not session:
            return None
        
        user = db.query(User).filter(User.id == session.user_id).first()
        return user
    
    def logout_session(self, db: Session, session_token: str):
        """注销会话"""
        session = db.query(UserSession).filter(
            UserSession.session_token == session_token
        ).first()
        
        if session:
            session.is_active = False
            db.commit()

# 全局认证服务实例
auth_service = AuthService()