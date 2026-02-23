"""
User Database System - Auth models for Cloud Backend
"""
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone
import os
from pathlib import Path

from core.config_service import get_config

_config_service = get_config()


def get_database_url() -> str:
    """Get database URL from ConfigService"""
    db_path = _config_service.get('database.sqlite.path')
    if not db_path:
        raise ValueError("Database path not configured: database.sqlite.path")

    db_path = os.path.expanduser(db_path)
    return f"sqlite:///{db_path}"


def get_database_config() -> dict:
    """Get database configuration"""
    db_url = get_database_url()
    config = {"url": db_url}

    if "sqlite" in db_url:
        config["connect_args"] = {"check_same_thread": False}

    return config


DATABASE_URL = get_database_url()
db_config = get_database_config()

engine = create_engine(
    db_config["url"],
    connect_args=db_config.get("connect_args", {})
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime, nullable=True)


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database - check file exists and create tables"""
    db_url = get_database_url()
    print(f"Database URL: {db_url}")

    # Ensure parent directory exists for SQLite
    if "sqlite" in db_url and db_url.startswith("sqlite:///"):
        db_file_path = db_url[10:]
        db_file = Path(db_file_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

    create_tables()
    print("Database initialized")


if __name__ == "__main__":
    init_db()
