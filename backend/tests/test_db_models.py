"""Tests for database ORM models and schema."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.db.models import (
    ThreadModel,
    UploadModel,
    UsageLogModel,
    UserApiKeyModel,
    UserMemoryModel,
    UserModel,
)


class TestUserModel:
    """Tests for the User ORM model."""

    def test_create_user(self, db_session: Session):
        """A user can be created and retrieved."""
        user = UserModel(
            id=uuid.uuid4().hex,
            email="test@example.com",
            password_hash="$2b$12$abc",
            display_name="Test User",
        )
        db_session.add(user)
        db_session.commit()

        fetched = db_session.query(UserModel).filter(UserModel.email == "test@example.com").first()
        assert fetched is not None
        assert fetched.email == "test@example.com"
        assert fetched.display_name == "Test User"
        assert fetched.password_hash == "$2b$12$abc"

    def test_user_email_unique(self, db_session: Session):
        """Duplicate emails raise an integrity error."""
        import sqlalchemy.exc

        user1 = UserModel(id=uuid.uuid4().hex, email="dup@test.com", password_hash="hash1")
        user2 = UserModel(id=uuid.uuid4().hex, email="dup@test.com", password_hash="hash2")
        db_session.add(user1)
        db_session.commit()
        db_session.add(user2)

        try:
            db_session.commit()
            assert False, "Expected IntegrityError for duplicate email"
        except sqlalchemy.exc.IntegrityError:
            db_session.rollback()

    def test_to_dict_without_password(self, db_session: Session):
        """to_dict() excludes password_hash by default."""
        user = UserModel(
            id="abc123",
            email="dict@test.com",
            password_hash="secret",
            display_name="Dict User",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        db_session.add(user)
        db_session.commit()

        d = user.to_dict()
        assert "password_hash" not in d
        assert d["email"] == "dict@test.com"
        assert d["id"] == "abc123"

    def test_to_dict_with_password(self, db_session: Session):
        """to_dict(include_password=True) includes password_hash."""
        user = UserModel(
            id="xyz789",
            email="pw@test.com",
            password_hash="my_hash",
        )
        db_session.add(user)
        db_session.commit()

        d = user.to_dict(include_password=True)
        assert d["password_hash"] == "my_hash"


class TestThreadModel:
    """Tests for the Thread ORM model."""

    def test_create_thread(self, db_session: Session):
        """A thread can be created with ownership."""
        thread = ThreadModel(
            thread_id="thread-001",
            user_id="user-abc",
            title="My Thread",
        )
        db_session.add(thread)
        db_session.commit()

        fetched = db_session.query(ThreadModel).filter(ThreadModel.thread_id == "thread-001").first()
        assert fetched is not None
        assert fetched.user_id == "user-abc"
        assert fetched.title == "My Thread"

    def test_filter_by_user(self, db_session: Session):
        """Threads can be filtered by user_id."""
        db_session.add(ThreadModel(thread_id="t1", user_id="user-A"))
        db_session.add(ThreadModel(thread_id="t2", user_id="user-B"))
        db_session.add(ThreadModel(thread_id="t3", user_id="user-A"))
        db_session.commit()

        user_a_threads = db_session.query(ThreadModel).filter(ThreadModel.user_id == "user-A").all()
        assert len(user_a_threads) == 2


class TestUserMemoryModel:
    """Tests for the UserMemory ORM model."""

    def test_create_memory(self, db_session: Session):
        """User memory can be created with JSON data."""
        memory = UserMemoryModel(
            user_id="user-mem-1",
            memory_json={"version": "1.0", "facts": [{"id": "f1", "content": "test"}]},
        )
        db_session.add(memory)
        db_session.commit()

        fetched = db_session.query(UserMemoryModel).filter(UserMemoryModel.user_id == "user-mem-1").first()
        assert fetched is not None
        assert fetched.memory_json["version"] == "1.0"
        assert len(fetched.memory_json["facts"]) == 1

    def test_update_memory_json(self, db_session: Session):
        """Memory JSON can be updated."""
        memory = UserMemoryModel(
            user_id="user-upd",
            memory_json={"facts": []},
        )
        db_session.add(memory)
        db_session.commit()

        memory.memory_json = {"facts": [{"id": "new-fact"}]}
        db_session.commit()

        fetched = db_session.query(UserMemoryModel).filter(UserMemoryModel.user_id == "user-upd").first()
        assert len(fetched.memory_json["facts"]) == 1


class TestUserApiKeyModel:
    """Tests for the UserApiKey ORM model."""

    def test_create_api_key(self, db_session: Session):
        """An encrypted API key can be stored."""
        key = UserApiKeyModel(
            id=uuid.uuid4().hex,
            user_id="user-key-1",
            provider="openai",
            encrypted_key="gAAAAABencrypted...",
        )
        db_session.add(key)
        db_session.commit()

        fetched = (
            db_session.query(UserApiKeyModel)
            .filter(
                UserApiKeyModel.user_id == "user-key-1",
                UserApiKeyModel.provider == "openai",
            )
            .first()
        )
        assert fetched is not None
        assert fetched.encrypted_key == "gAAAAABencrypted..."

    def test_unique_user_provider(self, db_session: Session):
        """The (user_id, provider) pair must be unique."""
        import sqlalchemy.exc

        key1 = UserApiKeyModel(id=uuid.uuid4().hex, user_id="user-dup", provider="openai", encrypted_key="key1")
        key2 = UserApiKeyModel(id=uuid.uuid4().hex, user_id="user-dup", provider="openai", encrypted_key="key2")
        db_session.add(key1)
        db_session.commit()
        db_session.add(key2)

        try:
            db_session.commit()
            assert False, "Expected IntegrityError for duplicate (user_id, provider)"
        except sqlalchemy.exc.IntegrityError:
            db_session.rollback()


class TestUploadModel:
    """Tests for the Upload ORM model."""

    def test_create_upload(self, db_session: Session):
        """Upload metadata can be stored."""
        upload = UploadModel(
            id=uuid.uuid4().hex,
            thread_id="thread-up-1",
            user_id="user-up-1",
            filename="report.pdf",
            content_type="application/pdf",
            size_bytes=1024000,
            storage_path="/uploads/thread-up-1/report.pdf",
        )
        db_session.add(upload)
        db_session.commit()

        fetched = db_session.query(UploadModel).filter(UploadModel.thread_id == "thread-up-1").first()
        assert fetched is not None
        assert fetched.filename == "report.pdf"
        assert fetched.size_bytes == 1024000


class TestUsageLogModel:
    """Tests for the UsageLog ORM model."""

    def test_create_usage_log(self, db_session: Session):
        """Usage log entries can be created."""
        log = UsageLogModel(
            user_id="user-log-1",
            thread_id="thread-log-1",
            model_name="gpt-4",
            input_tokens=100,
            output_tokens=200,
        )
        db_session.add(log)
        db_session.commit()

        assert log.id is not None
        fetched = db_session.query(UsageLogModel).filter(UsageLogModel.user_id == "user-log-1").first()
        assert fetched is not None
        assert fetched.input_tokens == 100
        assert fetched.output_tokens == 200

    def test_usage_log_auto_increment(self, db_session: Session):
        """Usage log IDs auto-increment."""
        log1 = UsageLogModel(user_id="u1", input_tokens=10, output_tokens=20)
        log2 = UsageLogModel(user_id="u1", input_tokens=30, output_tokens=40)
        db_session.add_all([log1, log2])
        db_session.commit()

        assert log1.id < log2.id
