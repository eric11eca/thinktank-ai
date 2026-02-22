from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_LOCK = threading.Lock()
_STORE_DIR = Path(os.getcwd()) / ".think-tank"
_KEY_FILE = _STORE_DIR / "api-keys.key"
_DATA_FILE = _STORE_DIR / "api-keys.json"


def _ensure_store_dir() -> None:
    _STORE_DIR.mkdir(parents=True, exist_ok=True)


def _read_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _write_file(path: Path, content: str) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Best-effort permissions; ignore on unsupported platforms.
        pass


def _get_or_create_master_key() -> bytes:
    _ensure_store_dir()
    existing = _read_file(_KEY_FILE)
    if existing:
        return existing.encode("utf-8")
    key = Fernet.generate_key()
    _write_file(_KEY_FILE, key.decode("utf-8"))
    return key


def _load_store() -> dict:
    _ensure_store_dir()
    raw = _read_file(_DATA_FILE)
    if not raw:
        return {"schema_version": 1, "devices": {}}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"schema_version": 1, "devices": {}}
    if not isinstance(data, dict) or "devices" not in data:
        return {"schema_version": 1, "devices": {}}
    if not isinstance(data.get("devices"), dict):
        data["devices"] = {}
    return data


def _save_store(data: dict) -> None:
    _ensure_store_dir()
    _write_file(_DATA_FILE, json.dumps(data, indent=2))


def _get_cipher() -> Fernet:
    key = _get_or_create_master_key()
    return Fernet(key)


def set_api_key(device_id: str, provider: str, api_key: str) -> None:
    if not device_id or not provider:
        raise ValueError("device_id and provider are required")
    api_key = api_key.strip()
    if not api_key:
        raise ValueError("api_key must be non-empty")
    cipher = _get_cipher()
    token = cipher.encrypt(api_key.encode("utf-8")).decode("utf-8")
    with _LOCK:
        data = _load_store()
        devices = data.setdefault("devices", {})
        device_entry = devices.setdefault(device_id, {})
        device_entry[provider] = token
        _save_store(data)


def delete_api_key(device_id: str, provider: str) -> None:
    if not device_id or not provider:
        raise ValueError("device_id and provider are required")
    with _LOCK:
        data = _load_store()
        devices = data.get("devices", {})
        device_entry = devices.get(device_id)
        if not isinstance(device_entry, dict):
            return
        device_entry.pop(provider, None)
        if not device_entry:
            devices.pop(device_id, None)
        _save_store(data)


def has_api_key(device_id: str, provider: str) -> bool:
    if not device_id or not provider:
        return False
    with _LOCK:
        data = _load_store()
        device_entry = data.get("devices", {}).get(device_id, {})
        return isinstance(device_entry, dict) and bool(device_entry.get(provider))


def get_api_key(device_id: str, provider: str) -> str | None:
    if not device_id or not provider:
        return None
    cipher = _get_cipher()
    with _LOCK:
        data = _load_store()
        device_entry = data.get("devices", {}).get(device_id, {})
        if not isinstance(device_entry, dict):
            return None
        token = device_entry.get(provider)
        if not isinstance(token, str):
            return None
    try:
        return cipher.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None
