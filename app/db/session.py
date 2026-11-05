"""Database connection. Nothing connects at import time, so the stateless API runs without a database."""
from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..core import config


@lru_cache(maxsize=1)
def engine() -> Engine:
    if not config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return create_engine(config.DATABASE_URL, pool_pre_ping=True, hide_parameters=True)


def new_session() -> Session:
    return sessionmaker(engine())()


def get_db():
    """FastAPI dependency: one session per request."""
    with new_session() as session:
        yield session
