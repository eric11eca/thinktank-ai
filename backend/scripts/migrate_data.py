"""Data migration script: .think-tank/ file-based data -> PostgreSQL.

Migrates existing file-based data from the .think-tank/ directory into
the PostgreSQL database. This script is idempotent: running it multiple
times will skip records that already exist.

Usage:
    cd backend
    DATABASE_URL=postgresql://thinktank:password@localhost:5432/thinktank \
        python -m scripts.migrate_data

Prerequisites:
    - PostgreSQL database must be running and migrations applied:
        alembic upgrade head
    - DATABASE_URL environment variable must be set
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Ensure the backend directory is in the Python path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)


def migrate_users(store_dir: Path) -> dict[str, str]:
    """Migrate users from users.json to the users table.

    Returns:
        Mapping of old user_id -> new user_id (same in this case).
    """
    from src.db.engine import get_db_session
    from src.db.models import UserModel

    users_file = store_dir / "users.json"
    if not users_file.exists():
        logger.info("No users.json found, skipping user migration")
        return {}

    data = json.loads(users_file.read_text(encoding="utf-8"))
    users = data.get("users", {})
    migrated = 0
    skipped = 0

    for user_id, record in users.items():
        with get_db_session() as session:
            existing = session.query(UserModel).filter(UserModel.id == user_id).first()
            if existing:
                skipped += 1
                continue

            user = UserModel(
                id=record["id"],
                email=record["email"],
                password_hash=record["password_hash"],
                display_name=record.get("display_name"),
                created_at=datetime.fromisoformat(record["created_at"])
                if record.get("created_at")
                else datetime.now(timezone.utc),
            )
            session.add(user)
            migrated += 1

    logger.info(f"Users: migrated {migrated}, skipped {skipped} (already exist)")
    return {uid: uid for uid in users}


def migrate_threads(store_dir: Path) -> None:
    """Migrate thread ownership from thread-ownership.json to the threads table."""
    from src.db.engine import get_db_session
    from src.db.models import ThreadModel

    threads_file = store_dir / "thread-ownership.json"
    if not threads_file.exists():
        logger.info("No thread-ownership.json found, skipping thread migration")
        return

    data = json.loads(threads_file.read_text(encoding="utf-8"))
    threads = data.get("threads", {})
    migrated = 0
    skipped = 0

    for thread_id, entry in threads.items():
        with get_db_session() as session:
            existing = (
                session.query(ThreadModel)
                .filter(ThreadModel.thread_id == thread_id)
                .first()
            )
            if existing:
                skipped += 1
                continue

            thread = ThreadModel(
                thread_id=thread_id,
                user_id=entry["user_id"],
                created_at=datetime.fromisoformat(entry["created_at"])
                if entry.get("created_at")
                else datetime.now(timezone.utc),
            )
            session.add(thread)
            migrated += 1

    logger.info(f"Threads: migrated {migrated}, skipped {skipped} (already exist)")


def migrate_memory(store_dir: Path) -> None:
    """Migrate per-user memory files from memory/ to the user_memory table."""
    from src.db.engine import get_db_session
    from src.db.models import UserMemoryModel

    memory_dir = store_dir / "memory"
    if not memory_dir.exists():
        logger.info("No memory/ directory found, skipping memory migration")
        return

    migrated = 0
    skipped = 0

    for memory_file in memory_dir.glob("*.json"):
        user_id = memory_file.stem  # filename without extension is user_id

        try:
            memory_data = json.loads(memory_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read memory file {memory_file}: {e}")
            continue

        with get_db_session() as session:
            existing = (
                session.query(UserMemoryModel)
                .filter(UserMemoryModel.user_id == user_id)
                .first()
            )
            if existing:
                skipped += 1
                continue

            record = UserMemoryModel(
                user_id=user_id,
                memory_json=memory_data,
            )
            session.add(record)
            migrated += 1

    logger.info(f"Memory: migrated {migrated}, skipped {skipped} (already exist)")


def migrate_api_keys(store_dir: Path) -> None:
    """Migrate encrypted API keys from api-keys.json to the user_api_keys table."""
    import uuid

    from src.db.engine import get_db_session
    from src.db.models import UserApiKeyModel

    keys_file = store_dir / "api-keys.json"
    if not keys_file.exists():
        logger.info("No api-keys.json found, skipping API key migration")
        return

    data = json.loads(keys_file.read_text(encoding="utf-8"))
    users = data.get("users", data.get("devices", {}))
    migrated = 0
    skipped = 0

    for user_id, providers in users.items():
        if not isinstance(providers, dict):
            continue

        for provider, encrypted_key in providers.items():
            if not isinstance(encrypted_key, str):
                continue

            with get_db_session() as session:
                existing = (
                    session.query(UserApiKeyModel)
                    .filter(
                        UserApiKeyModel.user_id == user_id,
                        UserApiKeyModel.provider == provider,
                    )
                    .first()
                )
                if existing:
                    skipped += 1
                    continue

                record = UserApiKeyModel(
                    id=uuid.uuid4().hex,
                    user_id=user_id,
                    provider=provider,
                    encrypted_key=encrypted_key,
                )
                session.add(record)
                migrated += 1

    logger.info(f"API Keys: migrated {migrated}, skipped {skipped} (already exist)")


def main() -> None:
    """Run the full data migration."""
    from src.db.engine import is_db_enabled

    if not is_db_enabled():
        logger.error("DATABASE_URL is not set. Cannot run migration.")
        sys.exit(1)

    store_dir = Path(os.getcwd()) / ".think-tank"
    if not store_dir.exists():
        logger.info("No .think-tank/ directory found. Nothing to migrate.")
        return

    logger.info(f"Starting data migration from {store_dir}")
    logger.info("=" * 60)

    migrate_users(store_dir)
    migrate_threads(store_dir)
    migrate_memory(store_dir)
    migrate_api_keys(store_dir)

    logger.info("=" * 60)
    logger.info("Data migration complete!")
    logger.info(
        "Note: The .think-tank/ directory has NOT been deleted. "
        "Remove it manually after verifying the migration."
    )


if __name__ == "__main__":
    main()
