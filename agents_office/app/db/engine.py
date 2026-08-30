from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def build_sync_engine(database_url: str):
    """Create synchronous SQLAlchemy engine with appropriate pool settings.
    
    SQLite does not support connection pool parameters (pool_size, max_overflow),
    so we use connect_args for thread safety instead.
    """
    if database_url.startswith("sqlite"):
        # SQLite: use check_same_thread=False for FastAPI compatibility
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
    else:
        # PostgreSQL / MySQL: full connection pool
        return create_engine(
            database_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )


def build_session_factory(database_url: str) -> sessionmaker[Session]:
    """Create a session factory bound to the given database."""
    engine = build_sync_engine(database_url)
    return sessionmaker(bind=engine, expire_on_commit=False)

