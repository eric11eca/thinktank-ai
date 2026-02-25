"""Shared test fixtures for the test suite."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Generator
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def tmp_store_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Provide a temporary directory for file-based stores.

    Patches all store modules to use the temporary directory instead of
    the real .think-tank directory. Also forces file-based mode by
    disabling the database path (in case DATABASE_URL is set via .env).
    This ensures tests are fully isolated.
    """
    store_dir = tmp_path / ".think-tank"
    store_dir.mkdir()

    # Save and remove DATABASE_URL so is_db_enabled() returns False
    saved_db_url = os.environ.pop("DATABASE_URL", None)

    patches = [
        # Force file-based mode regardless of environment
        patch("src.db.engine.is_db_enabled", return_value=False),
        patch("src.gateway.auth.user_store._STORE_DIR", store_dir),
        patch("src.gateway.auth.user_store._DATA_FILE", store_dir / "users.json"),
        patch("src.gateway.auth.thread_store._STORE_DIR", store_dir),
        patch("src.gateway.auth.thread_store._DATA_FILE", store_dir / "thread-ownership.json"),
        patch("src.gateway.auth.jwt._STORE_DIR", store_dir),
        patch("src.gateway.auth.jwt._SECRET_FILE", store_dir / "jwt-secret.key"),
        patch("src.security.api_key_store._STORE_DIR", store_dir),
        patch("src.security.api_key_store._KEY_FILE", store_dir / "api-keys.key"),
        patch("src.security.api_key_store._DATA_FILE", store_dir / "api-keys.json"),
    ]

    for p in patches:
        p.start()

    yield store_dir

    for p in patches:
        p.stop()

    # Restore DATABASE_URL if it was previously set
    if saved_db_url is not None:
        os.environ["DATABASE_URL"] = saved_db_url


@pytest.fixture()
def jwt_secret(tmp_store_dir: Path) -> str:
    """Set a deterministic JWT secret for testing."""
    secret = "test-jwt-secret-key-for-unit-tests-only"
    os.environ["JWT_SECRET_KEY"] = secret
    yield secret
    os.environ.pop("JWT_SECRET_KEY", None)


@pytest.fixture()
def sample_user_data() -> dict[str, str]:
    """Provide sample user registration data."""
    return {
        "email": "test@example.com",
        "password": "SecurePass1",
        "display_name": "Test User",
    }


# ---------------------------------------------------------------------------
# Database test fixtures (SQLite in-memory for fast, isolated testing)
# ---------------------------------------------------------------------------
@pytest.fixture()
def db_engine():
    """Create a SQLite in-memory engine for testing.

    Creates all tables from ORM models and yields the engine.
    """
    from src.db.engine import Base

    # Import models to register them with Base
    import src.db.models  # noqa: F401

    engine = create_engine("sqlite:///:memory:", echo=False)

    # Enable foreign key support in SQLite
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine) -> Generator[Session, None, None]:
    """Provide a database session for testing.

    Each test gets a clean session. Rolls back after each test.
    """
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = factory()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def db_enabled(db_engine) -> Generator[None, None, None]:
    """Enable database mode for tests by patching the engine module.

    This patches:
    - is_db_enabled() to return True
    - get_engine() to return the test SQLite engine
    - get_session_factory() to return a session factory bound to the test engine
    """
    import src.db.engine as engine_module

    factory = sessionmaker(bind=db_engine, expire_on_commit=False)

    patches = [
        patch.object(engine_module, "_engine", db_engine),
        patch.object(engine_module, "_session_factory", factory),
        patch("src.db.engine.is_db_enabled", return_value=True),
    ]

    # Also set a fake DATABASE_URL so is_db_enabled checks pass in stores
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

    for p in patches:
        p.start()

    yield

    for p in patches:
        p.stop()

    os.environ.pop("DATABASE_URL", None)
