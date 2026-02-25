"""Tests for production secrets enforcement (Phase 6.8)."""

from __future__ import annotations

import importlib
import os
from unittest.mock import patch

import pytest


class TestJWTSecretHardening:
    """Test JWT secret key production enforcement."""

    def test_uses_env_var_when_set(self, tmp_store_dir):
        """JWT secret from env var should be used directly."""
        import src.gateway.auth.jwt as jwt_mod

        with patch.dict(os.environ, {"JWT_SECRET_KEY": "my-test-secret"}, clear=False):
            secret = jwt_mod._get_secret_key()
            assert secret == "my-test-secret"

    def test_raises_when_require_env_secrets_and_no_jwt_key(self, tmp_store_dir):
        """In production mode, missing JWT_SECRET_KEY should raise RuntimeError."""
        import src.gateway.auth.jwt as jwt_mod

        env = {"REQUIRE_ENV_SECRETS": "true"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("JWT_SECRET_KEY", None)
            with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
                jwt_mod._get_secret_key()

    def test_falls_back_to_file_in_dev(self, tmp_store_dir):
        """Without REQUIRE_ENV_SECRETS, file fallback should work."""
        import src.gateway.auth.jwt as jwt_mod

        os.environ.pop("JWT_SECRET_KEY", None)
        os.environ.pop("REQUIRE_ENV_SECRETS", None)
        secret = jwt_mod._get_secret_key()
        assert isinstance(secret, str)
        assert len(secret) > 0

    def test_file_fallback_persists(self, tmp_store_dir):
        """Generated secret should be persisted and reused."""
        import src.gateway.auth.jwt as jwt_mod

        os.environ.pop("JWT_SECRET_KEY", None)
        os.environ.pop("REQUIRE_ENV_SECRETS", None)
        secret1 = jwt_mod._get_secret_key()
        secret2 = jwt_mod._get_secret_key()
        assert secret1 == secret2


class TestEncryptionKeyHardening:
    """Test encryption key production enforcement."""

    def test_uses_env_var_when_set(self, tmp_store_dir):
        """ENCRYPTION_KEY env var should be used directly."""
        from cryptography.fernet import Fernet

        import src.security.api_key_store as store

        test_key = Fernet.generate_key().decode("utf-8")
        with patch.dict(os.environ, {"ENCRYPTION_KEY": test_key}, clear=False):
            key = store._get_or_create_master_key()
            assert key == test_key.encode("utf-8")

    def test_raises_when_require_env_secrets_and_no_encryption_key(self, tmp_store_dir):
        """In production mode, missing ENCRYPTION_KEY should raise RuntimeError."""
        import src.security.api_key_store as store

        env = {"REQUIRE_ENV_SECRETS": "true"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("ENCRYPTION_KEY", None)
            with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
                store._get_or_create_master_key()

    def test_falls_back_to_file_in_dev(self, tmp_store_dir):
        """Without REQUIRE_ENV_SECRETS, file fallback should work."""
        import src.security.api_key_store as store

        os.environ.pop("ENCRYPTION_KEY", None)
        os.environ.pop("REQUIRE_ENV_SECRETS", None)
        key = store._get_or_create_master_key()
        assert isinstance(key, bytes)
        assert len(key) > 0


class TestSecureCookie:
    """Test refresh cookie secure flag."""

    def test_production_sets_secure_cookie(self):
        """In production mode, secure flag should be True."""
        from src.gateway.auth.routes import _is_production

        with patch.dict(os.environ, {"REQUIRE_ENV_SECRETS": "true"}):
            assert _is_production() is True

    def test_dev_does_not_set_secure_cookie(self):
        """In dev mode, secure flag should be False."""
        from src.gateway.auth.routes import _is_production

        os.environ.pop("REQUIRE_ENV_SECRETS", None)
        assert _is_production() is False
