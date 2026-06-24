"""Mailbox mode: process pending Postal-style messages from disk.

Pure helpers (no module-level side effects) used by ``python -m carta run``
when no ``--task`` is given and the agent declares a ``type: mailbox``
trigger. A "mailbox" is just a directory of ``.json`` message files; a
parallel "processed" directory records which messages have already been
handled so re-runs are idempotent.
"""
from __future__ import annotations

import datetime as _dt
import json
import os


def list_unprocessed(mailbox_dir: str, processed_dir: str) -> list[dict]:
    """List deserialized messages in ``mailbox_dir`` not yet processed.

    A message is skipped when ``processed_dir/<message_id>.json`` already
    exists, where ``<message_id>`` is the message's ``id`` field or, when
    absent, the file stem. Returns ``[]`` when ``mailbox_dir`` does not
    exist or holds no ``.json`` files. Files that fail to parse as JSON
    or whose top-level value is not an object are ignored.
    """
    if not os.path.isdir(mailbox_dir):
        return []

    out: list[dict] = []
    for name in sorted(os.listdir(mailbox_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(mailbox_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        msg_id = data.get("id") or os.path.splitext(name)[0]
        if os.path.isfile(os.path.join(processed_dir, f"{msg_id}.json")):
            continue
        out.append(data)
    return out


def mark_processed(message_id: str, processed_dir: str, result: dict) -> str:
    """Write ``processed_dir/<message_id>.json`` recording ``result``.

    Creates ``processed_dir`` if missing. The payload is
    ``{message_id, processed_at (ISO UTC), result}``. Returns the path
    written.
    """
    os.makedirs(processed_dir, exist_ok=True)
    payload = {
        "message_id": message_id,
        "processed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "result": result,
    }
    path = os.path.join(processed_dir, f"{message_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return path


def extract_task(message: dict) -> str | None:
    """Extract a task string from a message.

    Order: ``message["task"]`` (if a string), then ``message["plaintext"]``.
    When ``plaintext`` is ``bytes`` or a JSON-encoded string, it is parsed
    and a ``task`` key is looked up inside. Returns ``None`` when no task
    can be found.
    """
    task = message.get("task")
    if isinstance(task, str) and task:
        return task

    plaintext = message.get("plaintext")
    if isinstance(plaintext, bytes):
        try:
            plaintext = plaintext.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(plaintext, str):
        if plaintext:
            try:
                parsed = json.loads(plaintext)
            except ValueError:
                return None
            if isinstance(parsed, dict):
                inner = parsed.get("task")
                if isinstance(inner, str) and inner:
                    return inner
        return None
    return None