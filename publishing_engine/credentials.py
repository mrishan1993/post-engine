from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from config.settings import get_settings


def _key_bytes() -> bytes:
    raw = get_settings().credentials_key.encode("utf-8")
    return hashlib.sha256(raw).digest()


def _xor(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def store_secret(payload: dict[str, Any]) -> str:
    """Persist credential payload encrypted-at-rest; return opaque reference."""
    settings = get_settings()
    secrets_dir = Path(settings.storage_root) / ".credentials"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    # Restrictive perms where supported
    try:
        os.chmod(secrets_dir, 0o700)
    except OSError:
        pass
    secret_id = str(uuid4())
    raw = json.dumps(payload).encode("utf-8")
    blob = base64.urlsafe_b64encode(_xor(raw, _key_bytes()))
    path = secrets_dir / f"{secret_id}.bin"
    path.write_bytes(blob)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return f"secret://{secret_id}"


def load_secret(reference: str) -> dict[str, Any]:
    if not reference.startswith("secret://"):
        raise ValueError("invalid credential reference")
    secret_id = reference.removeprefix("secret://")
    path = Path(get_settings().storage_root) / ".credentials" / f"{secret_id}.bin"
    if not path.exists():
        raise FileNotFoundError(f"credential missing: {reference}")
    blob = base64.urlsafe_b64decode(path.read_bytes())
    raw = _xor(blob, _key_bytes())
    return json.loads(raw.decode("utf-8"))


def delete_secret(reference: str) -> None:
    if not reference.startswith("secret://"):
        return
    secret_id = reference.removeprefix("secret://")
    path = Path(get_settings().storage_root) / ".credentials" / f"{secret_id}.bin"
    if path.exists():
        path.unlink()
