"""Database module for Thinktank.ai.

Provides SQLAlchemy engine, session management, and ORM models.
When DATABASE_URL environment variable is set, PostgreSQL is used;
otherwise, the system falls back to file-based storage.
"""

from src.db.engine import check_db_connection, get_db_session, get_engine, init_db, is_db_enabled

__all__ = [
    "check_db_connection",
    "get_db_session",
    "get_engine",
    "init_db",
    "is_db_enabled",
]
