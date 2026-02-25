"""Tests for file upload validation (Phase 6.6)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.gateway.routers.uploads import (
    ALLOWED_EXTENSIONS,
    CONVERTIBLE_EXTENSIONS,
    MAX_SINGLE_FILE_SIZE,
    _validate_upload,
)


class TestExtensionValidation:
    """Test file extension allowlist."""

    @pytest.mark.parametrize(
        "filename",
        [
            "report.pdf",
            "data.csv",
            "photo.png",
            "script.py",
            "archive.zip",
            "notes.md",
            "config.yaml",
            "page.html",
        ],
    )
    def test_allowed_extensions_pass(self, filename):
        """Valid extensions should pass validation."""
        _validate_upload(filename, "application/octet-stream", 100)

    @pytest.mark.parametrize(
        "filename",
        [
            "malware.exe",
            "script.bat",
            "library.dll",
            "binary.bin",
            "app.app",
            "payload.scr",
            "macro.vbs",
            "script.cmd",
            "disk.iso",
            "archive.tar.gz",
        ],
    )
    def test_rejected_extensions_fail(self, filename):
        """Dangerous file extensions should be rejected."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_upload(filename, "application/octet-stream", 100)
        assert exc_info.value.status_code == 400
        assert "not allowed" in exc_info.value.detail

    def test_extension_case_insensitive(self):
        """Extension check should be case-insensitive."""
        _validate_upload("image.PNG", "image/png", 100)
        _validate_upload("doc.PDF", "application/pdf", 100)

    def test_no_extension_rejected(self):
        """Files without extensions should be rejected."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_upload("Makefile", "text/plain", 100)
        assert exc_info.value.status_code == 400


class TestMIMETypeValidation:
    """Test MIME type validation."""

    @pytest.mark.parametrize(
        "mime_type",
        [
            "application/pdf",
            "text/plain",
            "image/png",
            "image/jpeg",
            "application/json",
            "application/zip",
        ],
    )
    def test_allowed_mime_types_pass(self, mime_type):
        """Valid MIME types should pass validation."""
        _validate_upload("file.pdf", mime_type, 100)

    @pytest.mark.parametrize(
        "mime_type",
        [
            "application/x-executable",
            "application/x-msdownload",
            "application/x-shellscript",
        ],
    )
    def test_rejected_mime_types_fail(self, mime_type):
        """Dangerous MIME types should be rejected."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_upload("file.pdf", mime_type, 100)
        assert exc_info.value.status_code == 400
        assert "MIME type" in exc_info.value.detail

    def test_none_mime_type_passes(self):
        """None MIME type should pass (browser may not always send it)."""
        _validate_upload("file.txt", None, 100)

    def test_octet_stream_allowed(self):
        """application/octet-stream should be allowed as fallback."""
        _validate_upload("file.txt", "application/octet-stream", 100)


class TestSizeValidation:
    """Test file size limits."""

    def test_under_limit_passes(self):
        """Files under the size limit should pass."""
        _validate_upload("file.txt", "text/plain", 1024)

    def test_at_limit_passes(self):
        """Files exactly at the size limit should pass."""
        _validate_upload("file.txt", "text/plain", MAX_SINGLE_FILE_SIZE)

    def test_over_limit_fails(self):
        """Files over the size limit should be rejected."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_upload("file.txt", "text/plain", MAX_SINGLE_FILE_SIZE + 1)
        assert exc_info.value.status_code == 413
        assert "exceeds maximum size" in exc_info.value.detail


class TestConvertibleSubset:
    """Test that CONVERTIBLE_EXTENSIONS is a subset of ALLOWED_EXTENSIONS."""

    def test_convertible_is_subset_of_allowed(self):
        """All convertible extensions must also be allowed."""
        assert CONVERTIBLE_EXTENSIONS.issubset(ALLOWED_EXTENSIONS), f"Convertible extensions not in allowed: {CONVERTIBLE_EXTENSIONS - ALLOWED_EXTENSIONS}"
