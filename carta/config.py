"""Global Carta configuration stored in ``~/.carta/config.yaml``.

Provides a lightweight key/value store for settings that apply across all
projects — notably ``api_key`` so the user never has to pass ``--api-key``
again once it has been set.

:func:`inject_env` is called at CLI startup to push stored values into
``os.environ``, so ``$OLLAMA_API_KEY`` references in agent-specs resolve
even when the variable was not exported in the current shell session.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

_CONFIG_DIR = Path.home() / ".carta"
_CONFIG_FILE = _CONFIG_DIR / "config.yaml"

KNOWN_KEYS = {
    "api_key": "Default API key sent as Bearer token to model endpoints.",
    "base_url": "Default model base URL used by carta init when --base-url is omitted.",
    "preset": "Default preset (ollama-cloud | ollama-local) used by carta init.",
}


def load() -> dict:
    """Return the stored config dict (empty dict if file does not exist)."""
    if not _CONFIG_FILE.exists():
        return {}
    with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save(data: dict) -> None:
    """Persist ``data`` to ``~/.carta/config.yaml``."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def get(key: str, default: str = "") -> str:
    """Return the stored value for ``key``, or ``default`` if absent."""
    return str(load().get(key, default))


def set_value(key: str, value: str) -> None:
    """Store ``key=value`` in the global config."""
    data = load()
    data[key] = value
    save(data)


def unset(key: str) -> bool:
    """Remove ``key`` from the global config. Returns True if it existed."""
    data = load()
    if key not in data:
        return False
    del data[key]
    save(data)
    return True


def inject_env() -> None:
    """Push config values into ``os.environ`` for keys not already set.

    Called once at CLI startup so ``$OLLAMA_API_KEY`` references in
    agent-specs resolve correctly even without a shell-level export.
    Existing env vars are never overwritten.
    """
    cfg = load()
    api_key = cfg.get("api_key", "")
    if api_key and not os.environ.get("OLLAMA_API_KEY"):
        os.environ["OLLAMA_API_KEY"] = api_key
