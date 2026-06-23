"""Postal identity: load/save .postal/users/<id>.json (public-key only on disk)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict


@dataclass
class Identity:
    id: str
    private_key: str  # hex PEM (None/empty when loaded from public-only file)
    public_key: str   # hex PEM


def save_identity(identity: "Identity", path: str) -> str:
    """Write a public-key-only identity to .postal/users/<id>.json (or custom path).

    `path` may be a directory (the .postal root) or a full file path ending in .json.
    Returns the file path written.
    """
    if os.path.isdir(path) or not path.endswith(".json"):
        file_path = os.path.join(path, "users", f"{identity.id}.json")
    else:
        file_path = path
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    payload = {"id": identity.id, "public_key": identity.public_key}
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    return file_path


def load_identity(id: str, path: str) -> "Identity":
    """Load a public-key-only identity. `path` is the .postal root or full file path.

    Returns Identity with private_key="" (no private material on disk).
    """
    if os.path.isdir(path) or not path.endswith(".json"):
        file_path = os.path.join(path, "users", f"{id}.json")
    else:
        file_path = path
    with open(file_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return Identity(id=payload["id"], private_key="", public_key=payload["public_key"])