"""Tests for password hashing and verification."""

from src.gateway.auth.password import hash_password, verify_password


class TestPasswordHashing:
    """Tests for bcrypt password hashing."""

    def test_hash_password_returns_string(self):
        """Hash output is a non-empty string."""
        hashed = hash_password("testpass123")
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_hash_password_is_bcrypt_format(self):
        """Hash output starts with $2b$ (bcrypt marker)."""
        hashed = hash_password("testpass123")
        assert hashed.startswith("$2b$")

    def test_hash_password_different_for_same_input(self):
        """Two hashes of the same password should differ (random salt)."""
        h1 = hash_password("testpass123")
        h2 = hash_password("testpass123")
        assert h1 != h2

    def test_verify_password_correct(self):
        """Correct password verification returns True."""
        hashed = hash_password("SecurePass1")
        assert verify_password("SecurePass1", hashed) is True

    def test_verify_password_incorrect(self):
        """Wrong password verification returns False."""
        hashed = hash_password("SecurePass1")
        assert verify_password("WrongPassword2", hashed) is False

    def test_verify_password_empty(self):
        """Empty password fails verification against a real hash."""
        hashed = hash_password("SecurePass1")
        assert verify_password("", hashed) is False

    def test_unicode_password(self):
        """Unicode characters in passwords work correctly."""
        hashed = hash_password("Pässwörd1")
        assert verify_password("Pässwörd1", hashed) is True
        assert verify_password("Password1", hashed) is False
