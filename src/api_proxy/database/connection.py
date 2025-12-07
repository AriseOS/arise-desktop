"""
Database connection and session management
"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from ..config import get_config


# Base class for all models
Base = declarative_base()


# Database engine (will be initialized on first use)
_engine = None
_SessionLocal = None


def init_db():
    """Initialize database engine and session factory

    This should be called once at application startup
    """
    global _engine, _SessionLocal

    if _engine is not None:
        return  # Already initialized

    config = get_config()

    # Get database URL from config service
    db_url = config.get_db_url()
    pool_size = config.get("database.postgresql.pool_size", 10)
    max_overflow = config.get("database.postgresql.max_overflow", 20)
    # Use separate config for SQL logging, default to False to reduce noise
    echo = config.get("database.echo_sql", False)

    # Create engine
    _engine = create_engine(
        db_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        echo=echo,  # Log SQL queries only if explicitly enabled
    )

    # Create session factory
    _SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=_engine
    )


def get_engine():
    """Get database engine"""
    if _engine is None:
        init_db()
    return _engine


def get_session_factory():
    """Get session factory"""
    if _SessionLocal is None:
        init_db()
    return _SessionLocal


def create_all_tables():
    """Create all database tables

    This should be called after all models are imported
    """
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def drop_all_tables():
    """Drop all database tables

    WARNING: This will delete all data!
    """
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Get database session (context manager)

    Usage:
        with get_db() as db:
            user = db.query(User).first()
    """
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db_session() -> Session:
    """Get database session (for dependency injection in FastAPI)

    Usage:
        @app.get("/users")
        def get_users(db: Session = Depends(get_db_session)):
            users = db.query(User).all()
            return users
    """
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
