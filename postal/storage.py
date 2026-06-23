"""Postal storage: dir hashing + message persistence."""
from __future__ import annotations

import hashlib
import json
import os
from typing import List, Dict, Any

from .message import verify_message


def compute_dir_sha(path: str) -> str:
    """Deterministic SHA-256 over all files in a directory (sorted relative paths).

    Each file contributes: "<relpath>\\0<sha256_of_file_bytes>\\0" to the hash stream.
    Walks recursively; ignores empty dirs. Deterministic regardless of OS walk order.
    """
    h = hashlib.sha256()
    files: List[str] = []
    for root, _dirs, names in os.walk(path):
        for n in names:
            full = os.path.join(root, n)
            rel = os.path.relpath(full, path).replace(os.sep, "/")
            files.append((rel, full))
    files.sort(key=lambda t: t[0])
    for rel, full in files:
        with open(full, "rb") as f:
            file_sha = hashlib.sha256(f.read()).hexdigest()
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        h.update(file_sha.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def save_message(message: Dict[str, Any], repo_path: str) -> str:
    """Write message to <repo_path>/.postal/messages/<id>.json. Returns file path."""
    file_path = os.path.join(repo_path, ".postal", "messages", f"{message['id']}.json")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(message, f, indent=2, sort_keys=True)
    return file_path


def list_messages(repo_path: str, to_id: str) -> List[Dict[str, Any]]:
    """List messages whose 'to' field equals to_id. Empty 'to' never matches.

    If to_id is empty, returns messages with unset/empty 'to'.
    """
    dir_path = os.path.join(repo_path, ".postal", "messages")
    if not os.path.isdir(dir_path):
        return []
    out: List[Dict[str, Any]] = []
    for n in sorted(os.listdir(dir_path)):
        if not n.endswith(".json"):
            continue
        with open(os.path.join(dir_path, n), "r", encoding="utf-8") as f:
            msg = json.load(f)
        if msg.get("to", "") == to_id:
            out.append(msg)
    return out