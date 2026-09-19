"""SQLAlchemy engine and session factory (sync, psycopg3)."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import SQLALCHEMY_DATABASE_URL

# pool_pre_ping: managed Postgres drops idle connections; this swaps a dead one for a
# fresh one instead of failing the request. Pool is kept small -- Aiven plans cap
# max_connections, and the LangGraph checkpointer holds its own psycopg pool (app/core/db.py).
engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=5)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """One unit of work: commit on success, roll back on error, always close."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
